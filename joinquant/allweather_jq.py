"""
全季节策略 — 聚宽版（桥水全天候中国化）
===========================================
策略: 逆波动率/风险平价 + 趋势过滤(SMA) + HS300 AND抄底
资产: 6-7只中国ETF，覆盖增长/债券/通胀三大宏观场景

三版本可选（修改 STRATEGY 变量切换）:
  V3c        - 6资产逆波动率60d + nonferr/gold/sp500 75d趋势 + HS300 AND抄底
  V3-B Con   - 7资产逆波动率20d + nonferr 75d趋势 + HS300 AND抄底
  V3-B RP    - 4桶HRP 20d + 四重趋势 + HS300 AND抄底 + target_vol=9%

回测起点默认 2020-01-01（确保所有ETF有数据）。
更早期回测需处理30Y国债/有色金属ETF的合成数据。

使用方法:
  1. 打开聚宽 → 策略列表 → 新建策略
  2. 将本文件全部粘贴到代码编辑区
  3. 设置回测时间: 2020-01-01 ~ 最新
  4. 初始资金默认 100万
  5. 点击"运行回测"

参考: allweather/config.py, allweather/risk.py, allweather/backtest.py
"""

import datetime
import numpy as np
import pandas as pd


# ============================================================
# 0. 兼容垫片 — 聚宽环境适配
# ============================================================

def _resolve_jq_func(name):
    """安全解析聚宽注入的全局函数。"""
    obj = globals().get(name)
    if obj is not None:
        return obj
    try:
        import builtins
        return getattr(builtins, name, None)
    except Exception:
        return None


def _safe_order_target_percent(context, code, weight):
    """降级链下单封装。

    ETF 最小交易单位 100 份。权重 = 目标市值 / 总资产。
    优先级: order_target_percent → order_target_value → order_target → order
    """
    total_value = context.portfolio.total_value

    fn = _resolve_jq_func('order_target_percent')
    if fn is not None:
        return fn(code, weight)

    fn = _resolve_jq_func('order_target_value')
    if fn is not None:
        return fn(code, total_value * weight)

    # 手动计算目标股数（ETF 100 份整数倍）
    current_date = context.current_dt.strftime('%Y-%m-%d')
    try:
        df = get_price(code, end_date=current_date, count=1,
                       fields=['close'], skip_paused=False)
        price = float(df.iloc[-1]['close']) if df is not None and not df.empty else None
    except Exception:
        price = None

    positions = context.portfolio.positions
    pos = positions.get(code)
    current_amount = pos.total_amount if pos is not None else 0

    fn = _resolve_jq_func('order_target')
    if fn is not None:
        if price is None or price <= 0:
            raise RuntimeError('无法获取 %s 价格' % code)
        target_shares = int(total_value * weight / price / 100) * 100
        return fn(code, target_shares)

    fn = _resolve_jq_func('order')
    if fn is not None:
        if price is None or price <= 0:
            raise RuntimeError('无法获取 %s 价格' % code)
        target_shares = int(total_value * weight / price / 100) * 100
        delta = target_shares - current_amount
        if delta != 0:
            return fn(code, delta)
        return None

    raise RuntimeError('聚宽交易函数均未注入，请确认在聚宽回测环境中运行')


# ============================================================
# 1. 策略选择 — 修改这里切换版本
# ============================================================

STRATEGY = "v3c"      # "v3c" | "con" | "rp"
CASH_TIER = 0.00      # 现金比例: 0.00(100%风险资产) | 0.15(85%) | 0.30(70%)
START_DATE = "2020-01-01"  # 回测起点

# ============================================================
# 2. ETF 代码定义 + 30Y 债券合成参数
# ============================================================

# 上海: .XSHG, 深圳: .XSHE
ETF = {
    "hs300":     "510300.XSHG",  # 沪深300ETF
    "us_sp500":  "513500.XSHG",  # 标普500ETF(QDII)
    "credit":    "511220.XSHG",  # 城投债ETF
    "bond_10y":  "511260.XSHG",  # 10年国债ETF
    "bond_30y":  "511130.XSHG",  # 30年国债ETF（2024-03上市）
    "gold":      "518880.XSHG",  # 黄金ETF
    "nonferr":   "159980.XSHE",  # 有色金属ETF
    "wti":       "501018.XSHG",  # 南方原油LOF
}

# 30Y 国债合成: 511130 上市前用 10Y × 久期倍数
BOND_30Y_SYNTH_START = "2017-08-01"   # 10Y ETF 上市日（合成段起点）
BOND_30Y_REAL_START  = "2024-03-20"   # 30Y ETF 上市日（切换真实数据）
BOND_30Y_DURATION_MULT = 3.0          # 久期放大系数

# ETF 名称（日志用）
ETF_NAMES = {
    "hs300": "沪深300", "us_sp500": "标普500", "credit": "城投债",
    "bond_10y": "10Y国债", "bond_30y": "30Y国债",
    "gold": "黄金", "nonferr": "有色", "wti": "原油",
}

# ============================================================
# 3. 参数配置 — 根据 STRATEGY 自动切换
# ============================================================

def _get_strategy_config():
    """根据策略选择返回参数 dict。"""
    if STRATEGY == "v3c":
        return {
            "assets": ["hs300", "us_sp500", "credit", "bond_30y", "gold", "nonferr"],
            "weighting": "inverse_vol",
            "window": 60,
            "max_w": 0.30,
            "min_w": 0.03,
            "nonferr_trend": 75,
            "gold_trend": 75,
            "gold_trend_enabled": True,
            "sp500_trend": 75,
            "sp500_trend_enabled": True,
            "hs300_trend": 0,
            "hs300_trend_enabled": False,
            "target_vol": None,
            "vol_target_window": 60,
            "buckets": None,
            "bucket_method": "equal",
        }
    elif STRATEGY == "con":
        return {
            "assets": ["hs300", "us_sp500", "credit", "bond_10y", "bond_30y", "gold", "nonferr"],
            "weighting": "inverse_vol",
            "window": 20,
            "max_w": 0.25,
            "min_w": 0.02,
            "nonferr_trend": 75,
            "gold_trend": 0,
            "gold_trend_enabled": False,
            "sp500_trend": 0,
            "sp500_trend_enabled": False,
            "hs300_trend": 0,
            "hs300_trend_enabled": False,
            "target_vol": None,
            "vol_target_window": 60,
            "buckets": None,
            "bucket_method": "equal",
        }
    elif STRATEGY == "rp":
        return {
            "assets": ["hs300", "us_sp500", "credit", "bond_30y", "gold", "nonferr"],
            "weighting": "hierarchical_rp",
            "window": 20,
            "max_w": 0.20,
            "min_w": 0.02,
            "nonferr_trend": 75,
            "gold_trend": 75,
            "gold_trend_enabled": True,
            "sp500_trend": 75,
            "sp500_trend_enabled": True,
            "hs300_trend": 30,
            "hs300_trend_enabled": True,
            "target_vol": 0.09,
            "vol_target_window": 60,
            "buckets": {
                "增长↑":   ["hs300", "us_sp500"],
                "收益垫":  ["credit"],
                "增长↓":   ["bond_30y"],
                "通胀↑":   ["gold", "nonferr"],
            },
            "bucket_method": "equal",
        }
    else:
        raise ValueError("STRATEGY 必须是 'v3c', 'con', 或 'rp'")


CFG = _get_strategy_config()

# HS300 AND 抄底参数（三策略共用）
HS300_DIP_THRESHOLD = 0.25       # 回撤超过 25% 触发入场
HS300_DIP_BOOST = 1.8            # 触发后 HS300 权重 ×1.8
HS300_DIP_SMA = 120              # 价格需 > SMA120 确认入场
HS300_DIP_EXIT_RECOVERY = 0.15   # 恢复到 peak-15% 退出

# 溢价率过滤（买入保护：不为流动性溢价买单）
PREMIUM_FILTER_ENABLED = True   # 是否启用溢价率过滤
PREMIUM_THRESHOLD = 0.05        # 溢价率阈值（5%），超此值权重转 credit
PREMIUM_MAX_BACK_DAYS = 5       # 净值向前搜索天数（非交易日无净值）

# 成交量异常过滤（恐慌抛售/主力出货保护）
VOLUME_ANOMALY_ENABLED = True   # 是否启用成交量异常过滤
VOLUME_LOOKBACK = 60            # 正常量均线周期（交易日）
VOLUME_SPIKE_THRESHOLD = 3.0    # 放量倍数阈值（当日量/均量 > 3x → 异常）

# 基准
BENCHMARK = "000300.XSHG"  # 沪深300指数

# 是否需要合成 30Y 国债
NEED_BOND30_SYNTH = "bond_30y" in CFG["assets"]


# ============================================================
# 4. 核心数学 — 权重计算
# ============================================================

def _clip_normalize(w_arr, min_w, max_w, max_iter=10):
    """迭代 clip→normalize 直到所有权重落在 [min_w, max_w] 内。"""
    arr = np.asarray(w_arr, dtype=float).copy()
    np.nan_to_num(arr, copy=False)
    for _ in range(max_iter):
        np.clip(arr, min_w, max_w, out=arr)
        s = arr.sum()
        if s > 0:
            arr /= s
        if arr.max() <= max_w * (1 + 1e-10) and arr.min() >= min_w * (1 - 1e-10):
            break
    return arr


def inverse_vol_weights(returns_df, window, max_w, min_w):
    """逆波动率加权。1/vol 归一化后用 _clip_normalize 限制上下限。

    Args:
        returns_df: DataFrame, 各资产日收益率
        window: 回看窗口（交易日）
    Returns:
        np.array, 归一化权重
    """
    if len(returns_df) < max(20, window // 3):
        n = returns_df.shape[1]
        return np.full(n, 1.0 / n)

    recent = returns_df.tail(window)
    vols = recent.std() * np.sqrt(252)
    inv_vol = 1.0 / vols.replace(0, np.nan)
    raw = inv_vol / inv_vol.sum()
    return _clip_normalize(raw.values, min_w, max_w)


def hierarchical_rp_weights(returns_df, bucket_groups, window, max_w, min_w,
                            bucket_method="equal"):
    """分层风险平价：桶间等权/逆波动率 × 桶内逆波动率。

    Args:
        bucket_groups: dict, {桶名: [资产列名列表]}
    Returns:
        np.array, 归一化权重（顺序与 returns_df.columns 一致）
    """
    cols = list(returns_df.columns)
    n_assets = len(cols)

    if len(returns_df) < max(20, window // 3):
        return np.full(n_assets, 1.0 / n_assets)

    recent = returns_df.tail(window)
    n_buckets = len(bucket_groups)

    # 桶内逆波动率
    bucket_w = {}   # {桶名: Series(资产→权重)}
    bucket_vol = {}  # {桶名: 桶组合波动率}
    for bname, assets in bucket_groups.items():
        valid = [a for a in assets if a in recent.columns]
        if not valid:
            continue
        brets = recent[valid]
        vols = brets.std() * np.sqrt(252)
        inv = 1.0 / vols.replace(0, np.nan)
        w = inv / inv.sum()
        bucket_w[bname] = w
        port_r = (brets * w).sum(axis=1)
        bucket_vol[bname] = port_r.std() * np.sqrt(252)

    # 桶间分配
    if bucket_method == "equal":
        bucket_alloc = {k: 1.0 / n_buckets for k in bucket_w}
    else:
        inv_vols = {k: 1.0 / v for k, v in bucket_vol.items() if v > 1e-12}
        total = sum(inv_vols.values())
        bucket_alloc = {k: v / total for k, v in inv_vols.items()}

    # 桶内 × 桶间 = 最终权重
    raw = np.zeros(n_assets)
    col_to_idx = {c: i for i, c in enumerate(cols)}
    for bname, bw in bucket_alloc.items():
        if bname not in bucket_w:
            continue
        for asset, aw in bucket_w[bname].items():
            if asset in col_to_idx:
                raw[col_to_idx[asset]] = bw * aw

    return _clip_normalize(raw, min_w, max_w)


def apply_target_vol(w_arr, returns_window, target_vol):
    """如果组合估计波动率超过目标，等比降敞口。"""
    if target_vol is None:
        return w_arr
    cov = returns_window.cov().values * 252
    port_var = w_arr @ cov @ w_arr
    port_vol = np.sqrt(max(port_var, 1e-10))
    if port_vol > target_vol:
        return w_arr * (target_vol / port_vol)
    return w_arr


# ============================================================
# 5. 趋势过滤 + HS300 抄底状态机
# ============================================================

def apply_trend_filters(weights_dict, prices_dict, sma_store, current_date):
    """趋势过滤：跌破 SMA 的资产权重转入 credit。

    Args:
        weights_dict: {asset_key: weight}，会被原地修改
        prices_dict: {asset_key: current_price}
        sma_store: {window: {asset_key: sma_value}}
        current_date: 当前日期
    Returns:
        weights_dict (原地修改后)
    """
    credit = "credit"
    if credit not in weights_dict:
        return weights_dict

    date_str = current_date.strftime('%Y-%m-%d') if hasattr(current_date, 'strftime') else str(current_date)

    # nonferr 趋势
    nf_w = CFG["nonferr_trend"]
    if nf_w > 0 and "nonferr" in weights_dict and weights_dict["nonferr"] > 0:
        sma = sma_store.get(nf_w, {}).get("nonferr")
        px = prices_dict.get("nonferr")
        if sma is not None and px is not None and px < sma:
            log.info('[%s] nonferr 跌破 SMA%d，权重转 credit' % (date_str, nf_w))
            weights_dict[credit] += weights_dict["nonferr"]
            weights_dict["nonferr"] = 0.0

    # gold 趋势
    if CFG["gold_trend_enabled"] and "gold" in weights_dict and weights_dict.get("gold", 0) > 0:
        gw = CFG["gold_trend"]
        sma = sma_store.get(gw, {}).get("gold")
        px = prices_dict.get("gold")
        if sma is not None and px is not None and px < sma:
            log.info('[%s] gold 跌破 SMA%d，权重转 credit' % (date_str, gw))
            weights_dict[credit] += weights_dict["gold"]
            weights_dict["gold"] = 0.0

    # sp500 趋势
    if CFG["sp500_trend_enabled"] and "us_sp500" in weights_dict and weights_dict.get("us_sp500", 0) > 0:
        sw = CFG["sp500_trend"]
        sma = sma_store.get(sw, {}).get("us_sp500")
        px = prices_dict.get("us_sp500")
        if sma is not None and px is not None and px < sma:
            log.info('[%s] sp500 跌破 SMA%d，权重转 credit' % (date_str, sw))
            weights_dict[credit] += weights_dict["us_sp500"]
            weights_dict["us_sp500"] = 0.0

    # hs300 趋势
    if CFG["hs300_trend_enabled"] and "hs300" in weights_dict and weights_dict.get("hs300", 0) > 0:
        hw = CFG["hs300_trend"]
        sma = sma_store.get(hw, {}).get("hs300")
        px = prices_dict.get("hs300")
        if sma is not None and px is not None and px < sma:
            log.info('[%s] hs300 跌破 SMA%d，权重转 credit' % (date_str, hw))
            weights_dict[credit] += weights_dict["hs300"]
            weights_dict["hs300"] = 0.0

    return weights_dict


def hs300_dip_check(hs300_price, hs300_sma120, state):
    """HS300 AND抄底状态机（价格版，不含 PB/PE）。

    入场: drawdown > 25% AND price > SMA120 → boost = 1.8x
    出场: 已入场 AND 恢复到 peak-15% 以内 → 退出

    Args:
        hs300_price: 当前 HS300 价格
        hs300_sma120: SMA120 值（可为 None）
        state: dict, {'peak', 'boosted'}
    Returns:
        (new_boosted, boost_multiplier_or_None)
    """
    peak = state.get('peak', hs300_price)
    if hs300_price > peak:
        peak = hs300_price
        state['peak'] = peak

    dd = hs300_price / peak - 1.0

    if state.get('boosted', False):
        if dd > -HS300_DIP_EXIT_RECOVERY:
            state['boosted'] = False
            return False, None
        return True, None

    # 入场条件
    sma_ok = hs300_sma120 is not None and hs300_price > hs300_sma120
    if dd <= -HS300_DIP_THRESHOLD and sma_ok:
        state['boosted'] = True
        return True, HS300_DIP_BOOST

    return False, None


def hs300_dip_apply(weights_dict, hs300_price, hs300_sma120, hs300_state, date_str):
    """应用 HS300 抄底：入场时从 credit 借权重给 hs300 × boost。"""
    credit = "credit"
    hs = "hs300"
    if hs not in weights_dict or credit not in weights_dict:
        return weights_dict
    if weights_dict.get(hs, 0) <= 0:
        return weights_dict

    boosted, boost = hs300_dip_check(hs300_price, hs300_sma120, hs300_state)
    if boost is not None and boosted:
        # 入场：hs300 权重 × boost，差额从 credit 扣除
        extra = weights_dict[hs] * (boost - 1.0)
        if weights_dict[credit] >= extra:
            weights_dict[hs] *= boost
            weights_dict[credit] -= extra
            log.info('[%s] HS300 抄底触发！回撤>%.0f%%, 1.8x boost, hs300=%.2f%%' % (
                date_str, HS300_DIP_THRESHOLD * 100, weights_dict[hs] * 100))

    return weights_dict


# ============================================================
# 5b. 安全过滤器 — 溢价率 + 成交量异常
# ============================================================

def _get_net_value(code, date, max_back=5):
    """获取基金净值，若当天无则向前搜索最多 max_back 个交易日。

    先用 get_extras('unit_net_value') 查，失败则用 finance.run_query 兜底。

    Returns:
        (net_value, used_date) 或 (None, None)
    """
    # 方法1: get_extras
    try:
        start = date - datetime.timedelta(days=max_back * 3)
        net_df = get_extras('unit_net_value', code, start_date=start, end_date=date, df=True)
        if net_df is not None and not net_df.empty:
            vals = net_df[code].dropna()
            if len(vals) > 0:
                return float(vals.iloc[-1]), vals.index[-1]
    except Exception:
        pass

    # 方法2: finance.run_query (兜底)
    try:
        q = query(finance.FUND_NET_VALUE).filter(
            finance.FUND_NET_VALUE.code == code,
            finance.FUND_NET_VALUE.day <= date
        ).order_by(finance.FUND_NET_VALUE.day.desc()).limit(1)
        net_df = finance.run_query(q)
        if net_df is not None and not net_df.empty:
            return float(net_df['net_value'].iloc[0]), net_df['day'].iloc[0]
    except Exception:
        pass

    return None, None


def check_premium(etf_code, current_date):
    """检查溢价率是否超过阈值。

    Returns:
        (premium_rate, is_excessive) — 溢价率和是否超标
        premium_rate=None 表示获取失败（不过滤）
    """
    if not PREMIUM_FILTER_ENABLED:
        return None, False

    # 获取当前价格
    try:
        px_df = get_price(etf_code, end_date=current_date, count=1,
                          fields=['close'], skip_paused=False)
        if px_df is None or px_df.empty:
            return None, False
        price = float(px_df.iloc[-1]['close'])
    except Exception:
        return None, False

    net_value, used_date = _get_net_value(etf_code, current_date, PREMIUM_MAX_BACK_DAYS)
    if net_value is None or net_value <= 0:
        return None, False

    premium = (price - net_value) / net_value
    is_excessive = premium > PREMIUM_THRESHOLD
    return premium, is_excessive


def check_volume_anomaly(etf_code, current_date):
    """检查近期成交量是否异常放大（恐慌信号）。

    用法: 调仓日检查前一日成交量/60日均量，>阈值则返回True。

    Returns:
        (vol_ratio, is_anomaly) — 量比和是否异常
        vol_ratio=None 表示数据不足（不过滤）
    """
    if not VOLUME_ANOMALY_ENABLED:
        return None, False

    try:
        hist = get_price(etf_code, end_date=current_date, count=VOLUME_LOOKBACK + 5,
                         fields=['volume'], skip_paused=False)
        if hist is None or len(hist) < VOLUME_LOOKBACK:
            return None, False

        vols = hist['volume']
        avg_vol = vols.tail(VOLUME_LOOKBACK).mean()
        latest_vol = vols.iloc[-1]

        if avg_vol <= 0:
            return None, False

        ratio = latest_vol / avg_vol
        is_anomaly = ratio > VOLUME_SPIKE_THRESHOLD
        return ratio, is_anomaly
    except Exception:
        return None, False


def apply_safety_filters(weights_dict, current_date):
    """安全过滤器：溢价过高或量异常放大的资产，权重转入 credit。

    在趋势过滤之后、target_vol 之前调用。

    Args:
        weights_dict: {asset_key: weight}，原地修改
        current_date: 当前日期 (datetime)
    Returns:
        weights_dict (原地修改)
    """
    credit = "credit"
    if credit not in weights_dict:
        return weights_dict

    date_str = current_date.strftime('%Y-%m-%d') if hasattr(current_date, 'strftime') else str(current_date)

    for asset in list(weights_dict.keys()):
        if asset == credit or weights_dict.get(asset, 0) <= 0:
            continue

        code = ETF.get(asset)
        if code is None:
            continue

        # 1. 溢价率检查
        premium, excessive = check_premium(code, current_date)
        if excessive:
            log.info('[%s] ⚠ %s 溢价率 %.1f%% > %.0f%%，权重转 credit' % (
                date_str, asset, premium * 100, PREMIUM_THRESHOLD * 100))
            weights_dict[credit] += weights_dict[asset]
            weights_dict[asset] = 0.0
            continue  # 已排除，跳过成交量检查

        # 2. 成交量异常检查
        vol_ratio, anomaly = check_volume_anomaly(code, current_date)
        if anomaly:
            log.info('[%s] ⚠ %s 成交量异常放大 %.1fx，权重转 credit' % (
                date_str, asset, vol_ratio))
            weights_dict[credit] += weights_dict[asset]
            weights_dict[asset] = 0.0

    return weights_dict


# ============================================================
# 6. SMA 预计算
# ============================================================

def precompute_smas(prices_dict):
    """预计算所有需要的 SMA 窗口。

    Args:
        prices_dict: {asset_key: pd.Series(price, index=日期)}
    Returns:
        {window: {asset_key: pd.Series(sma, index=日期)}}
    """
    windows = set()
    for w in [CFG["nonferr_trend"], CFG["gold_trend"], CFG["sp500_trend"],
              CFG["hs300_trend"], HS300_DIP_SMA]:
        if w > 0:
            windows.add(w)
    # HS300抄底始终需要 SMA120
    if HS300_DIP_SMA > 0:
        windows.add(HS300_DIP_SMA)

    sma_store = {}
    for w in windows:
        sma_store[w] = {}
        for asset, px_series in prices_dict.items():
            if px_series is None or len(px_series) < w:
                sma_store[w][asset] = None
            else:
                sma = px_series.rolling(window=w, min_periods=1).mean().shift(1)
                sma_store[w][asset] = sma
    return sma_store


def get_sma_at(sma_store, window, asset, date):
    """从预计算结果中查询某日期的 SMA 值。"""
    w_dict = sma_store.get(window, {})
    sma_series = w_dict.get(asset)
    if sma_series is None:
        return None
    try:
        val = sma_series.loc[date]
        if pd.isna(val):
            return None
        return float(val)
    except (KeyError, TypeError):
        return None


# ============================================================
# 7. 数据加载 + 30Y 债券合成
# ============================================================

def load_price_series(etf_code, start, end):
    """安全加载 ETF 日频收盘价，返回 pd.Series 或 None。"""
    try:
        df = get_price(etf_code, start_date=start, end_date=end,
                       fields=['close'], skip_paused=False, fq='post')
        if df is None or df.empty:
            return None
        if 'time' in df.columns:
            df = df.set_index('time')
        elif 'date' in df.columns:
            df = df.set_index('date')
        df.index = pd.to_datetime(df.index)
        s = df['close']
        s.name = etf_code
        return s
    except Exception:
        return None


def load_bond_30y(start, end):
    """加载 30Y 国债价格序列（合成段 + 真实段拼接）。

    2024-03-20 前: 10Y 国债指数日收益 × 3.0 合成
    2024-03-20 起: 真实 511130 ETF
    """
    # 10Y 基准
    bond10 = load_price_series(ETF["bond_10y"], start, end)
    # 30Y 真实 ETF
    bond30_real = load_price_series(ETF["bond_30y"], max(start, BOND_30Y_REAL_START), end)

    if bond10 is None:
        try:
            log.info('[数据] 无法加载 10Y 国债数据，30Y 债券不可用')
        except Exception:
            pass
        return None

    # 构建合成序列
    synth_returns = bond10.pct_change() * BOND_30Y_DURATION_MULT
    synth_price = (1.0 + synth_returns.fillna(0)).cumprod()
    synth_price.name = "bond_30y_synth"

    if bond30_real is not None and len(bond30_real) > 0:
        # 拼接：合成段（~2024-03-20前）+ 真实段
        real_start = bond30_real.index[0]
        synth_seg = synth_price[synth_price.index < real_start]
        # 对齐：真实 ETF 首日 NAV 继承合成段最后值
        if len(synth_seg) > 0:
            ratio = synth_seg.iloc[-1] / bond30_real.iloc[0]
            real_scaled = bond30_real * ratio
            combined = pd.concat([synth_seg, real_scaled])
        else:
            combined = bond30_real
    else:
        combined = synth_price

    combined.name = "bond_30y"
    return combined


def load_all_prices(start, end):
    """加载全部所需 ETF 价格序列。

    Returns:
        prices_dict: {asset_key: pd.Series}
        rets_df: pd.DataFrame, 日收益率（列=资产，index=日期）
    """
    prices = {}
    failed = []

    for asset in CFG["assets"]:
        if asset == "bond_30y":
            px = load_bond_30y(start, end)
        else:
            code = ETF.get(asset)
            if code is None:
                failed.append(asset)
                continue
            px = load_price_series(code, start, end)

        if px is not None and len(px) > 20:
            prices[asset] = px
        else:
            failed.append(asset)

    if failed:
        try:
            log.info('[数据] 以下资产加载失败，将跳过: %s' % ', '.join(failed))
        except Exception:
            pass

    # 构建日收益率 DataFrame（统一对齐）
    if not prices:
        raise RuntimeError('所有资产加载失败，请检查回测时间范围')

    px_df = pd.DataFrame(prices)
    rets = px_df.pct_change().dropna(how='all')

    # 对齐到有数据的日期范围
    common_start = rets.dropna(how='any').index[0] if len(rets.dropna(how='any')) > 0 else rets.index[0]

    log.info('[数据] 成功加载 %d/%d 个资产: %s' % (
        len(prices), len(CFG["assets"]), ', '.join(prices.keys())))
    log.info('[数据] 有效数据起点: %s' % common_start.strftime('%Y-%m-%d'))

    return prices, rets


# ============================================================
# 8. 策略主体 — initialize()
# ============================================================

def _safe_get_end_date(context):
    """安全获取回测结束日期（兼容聚宽不同版本的返回类型）。"""
    end = context.run_params.end_date
    if hasattr(end, 'strftime'):
        return end.strftime('%Y-%m-%d')
    return str(end)


def initialize(context):
    """策略初始化。"""
    set_benchmark(BENCHMARK)
    apply_cost_model()

    # 策略名
    names = {"v3c": "V3c 多元", "con": "V3-B 保守增强", "rp": "V3-B 风险平价"}
    g.strategy_name = names.get(STRATEGY, STRATEGY)
    g.cash_tier = CASH_TIER
    g.assets = CFG["assets"]

    log.info('=' * 50)
    log.info('全季节策略 — 聚宽版: %s' % g.strategy_name)
    log.info('资产: %s' % ', '.join(g.assets))
    log.info('加权方式: %s, 窗口: %dd' % (CFG["weighting"], CFG["window"]))
    log.info('现金比例: %.0f%%' % (CASH_TIER * 100))
    log.info('安全过滤: 溢价率>%.0f%%=%s | 成交量>%.0fx=%s' % (
        PREMIUM_THRESHOLD * 100, 'ON' if PREMIUM_FILTER_ENABLED else 'OFF',
        VOLUME_SPIKE_THRESHOLD, 'ON' if VOLUME_ANOMALY_ENABLED else 'OFF'))
    log.info('=' * 50)

    # --- 加载数据 + 预计算 SMA ---
    end_date_str = _safe_get_end_date(context)
    prices_dict, rets_df = load_all_prices(START_DATE, end_date_str)
    g.prices = prices_dict        # {asset: Series}
    g.rets = rets_df              # DataFrame, 日收益率
    g.sma_store = precompute_smas(prices_dict)

    # --- 初始化状态 ---
    g.target_weights = {}          # 最近一次目标权重 {asset: weight}
    g.target_position = 1.0        # 总仓位（1.0 - CASH_TIER）
    g.hs300_state = {              # HS300抄底状态机
        'peak': 1.0,
        'boosted': False,
    }
    g.first_rebalance = True

    # --- 月频调仓（每月首个交易日 14:50） ---
    run_monthly(monthly_rebalance, monthday=1, time='14:50')


def apply_cost_model():
    """ETF 交易成本：万1佣金 + 免印花税 + 万1滑点。"""
    try:
        set_order_cost(
            OrderCost(
                open_tax=0,
                close_tax=0,              # ETF 免印花税
                open_commission=0.0001,   # 万1
                close_commission=0.0001,
                close_today_commission=0,
                min_commission=0.1,       # ETF 最低佣金低
            ),
            type='fund',
        )
    except Exception:
        pass
    try:
        set_slippage(PriceSlippage(0.0001))  # 万1滑点
    except NameError:
        try:
            set_slippage(FixedSlippage(0.0001))
        except NameError:
            pass


# ============================================================
# 9. 策略主体 — monthly_rebalance()
# ============================================================

def monthly_rebalance(context):
    """月频调仓主逻辑。"""
    current_date = context.current_dt
    date_str = current_date.strftime('%Y-%m-%d')

    # --- 1. 获取可用资产（当日有数据） ---
    available = []
    for asset in g.assets:
        if asset in g.prices:
            px_series = g.prices[asset]
            if date_str in px_series.index:
                available.append(asset)
    if not available:
        log.info('[%s] 无可用资产数据，跳过调仓' % date_str)
        return

    # --- 2. 准备收益率窗口 ---
    available_rets = g.rets[available].dropna(how='all')
    if len(available_rets) < 20:
        log.info('[%s] 收益率数据不足，跳过调仓' % date_str)
        return

    # 截取到当前日期
    rets_to_date = available_rets[available_rets.index <= current_date]
    if len(rets_to_date) < 20:
        log.info('[%s] 当前日期前数据不足，跳过调仓' % date_str)
        return

    # --- 3. 计算权重 ---
    window = CFG["window"]
    max_w = CFG["max_w"]
    min_w = CFG["min_w"]

    if CFG["weighting"] == "hierarchical_rp" and CFG["buckets"] is not None:
        w_arr = hierarchical_rp_weights(
            rets_to_date[available], CFG["buckets"],
            window, max_w, min_w, CFG["bucket_method"])
    else:
        w_arr = inverse_vol_weights(rets_to_date[available], window, max_w, min_w)

    weights = {a: float(w) for a, w in zip(available, w_arr) if w > 0.001}

    # --- 4. 获取当日价格 + SMA ---
    prices_today = {}
    sma_today = {}
    for asset in weights:
        px_s = g.prices.get(asset)
        if px_s is not None and date_str in px_s.index:
            prices_today[asset] = float(px_s.loc[date_str])
    # SMA 查询
    sma_dict = {}
    for w in set([CFG["nonferr_trend"], CFG["gold_trend"], CFG["sp500_trend"],
                  CFG["hs300_trend"]]):
        if w > 0:
            for asset in weights:
                v = get_sma_at(g.sma_store, w, asset, current_date)
                if v is not None:
                    sma_dict.setdefault(w, {})[asset] = v
    # HS300 SMA120 单独查
    hs300_sma120 = get_sma_at(g.sma_store, HS300_DIP_SMA, "hs300", current_date)

    # --- 5. 趋势过滤 ---
    weights = apply_trend_filters(weights, prices_today, sma_dict, current_date)

    # --- 5b. 安全过滤器（溢价率 + 成交量异常）---
    weights = apply_safety_filters(weights, current_date)

    # --- 6. Target Vol（仅 RP 版） ---
    if CFG["target_vol"] is not None and len(rets_to_date) >= CFG["vol_target_window"]:
        w_arr = np.array([weights.get(a, 0.0) for a in available])
        vol_window_rets = rets_to_date[available].tail(CFG["vol_target_window"])
        w_arr = apply_target_vol(w_arr, vol_window_rets, CFG["target_vol"])
        weights = {a: float(w) for a, w in zip(available, w_arr) if w > 0.001}

    # --- 7. HS300 AND 抄底 ---
    hs300_px = prices_today.get("hs300")
    if hs300_px is not None and "hs300" in weights and "credit" in weights:
        weights = hs300_dip_apply(weights, hs300_px, hs300_sma120,
                                  g.hs300_state, date_str)
        # 更新 peak
        if hs300_px > g.hs300_state.get('peak', 0):
            g.hs300_state['peak'] = hs300_px

    # --- 8. 应用现金比例 ---
    cash_scale = 1.0 - CASH_TIER
    target_weights = {a: w * cash_scale for a, w in weights.items()}
    g.target_weights = weights  # 存原始（未乘现金比例）供参考

    # --- 9. 日志 ---
    log.info('[%s] === %s 月频调仓 ===' % (date_str, g.strategy_name))
    log.info('[%s] 现金比例 %.0f%%, 有效仓位 %.0f%%' % (
        date_str, CASH_TIER * 100, cash_scale * 100))
    # 按权重排序打印
    sorted_w = sorted(target_weights.items(), key=lambda x: -x[1])
    for asset, w in sorted_w[:6]:
        name = ETF_NAMES.get(asset, asset)
        log.info('  %s (%s): %.2f%%' % (name, asset, w * 100))

    if g.hs300_state.get('boosted'):
        log.info('  [HS300抄底] 激活中, peak=%.4f' % g.hs300_state['peak'])

    # --- 10. 调仓 ---
    rebalance_ordered(context, target_weights)
    log.info('[%s] 调仓完成' % date_str)


# ============================================================
# 10. 调仓执行
# ============================================================

def rebalance_ordered(context, target_weights):
    """先卖后买调仓。

    Args:
        target_weights: {asset_key: final_weight}
    """
    current_date = context.current_dt.strftime('%Y-%m-%d')
    # 资产key → ETF代码
    target_by_code = {}
    for asset, weight in target_weights.items():
        code = ETF.get(asset)
        if code is not None and weight > 0:
            target_by_code[code] = weight

    # 第一步：卖出不在目标中的持仓
    for code, pos in list(context.portfolio.positions.items()):
        if pos.total_amount <= 0:
            continue
        if code in target_by_code:
            continue  # 还在目标持仓中
        _safe_order_target_percent(context, code, 0)
        log.info('  卖出 %s' % code)

    # 第二步：买入/调整目标持仓
    for code, weight in target_by_code.items():
        if weight <= 0:
            continue
        _safe_order_target_percent(context, code, weight)


# ============================================================
# 策略说明（聚宽控制台输出）
# ============================================================

def _build_trend_desc():
    parts = []
    if CFG["nonferr_trend"] > 0:
        parts.append('nonferr SMA%d' % CFG["nonferr_trend"])
    if CFG["gold_trend_enabled"]:
        parts.append('gold SMA%d' % CFG["gold_trend"])
    if CFG["sp500_trend_enabled"]:
        parts.append('sp500 SMA%d' % CFG["sp500_trend"])
    if CFG["hs300_trend_enabled"]:
        parts.append('hs300 SMA%d' % CFG["hs300_trend"])
    return ', '.join(parts) if parts else '无'


_STRATEGY_DESC = """
╔══════════════════════════════════════════════════════════╗
║       全季节策略 — 桥水全天候中国化（聚宽版）          ║
╠══════════════════════════════════════════════════════════╣
║                                                        ║
║  策略: {name}                                           ║
║  加权: {weighting} 窗口{window}d  max_w={max_w}         ║
║  资产: {assets}                                         ║
║  趋势过滤: {trends}                                     ║
║  HS300抄底: drawdown>{dip_thres}%+SMA{dip_sma} → {dip_boost}x    ║
║  安全过滤: 溢价率>{prem}% | 成交量>{vol_spike}x均量 → credit   ║
║  现金比例: {cash}%                                       ║
║  调仓: 每月首个交易日 14:50                              ║
║                                                        ║
║  修改 STRATEGY 变量切换版本: v3c / con / rp             ║
╚══════════════════════════════════════════════════════════╝
""".format(
    name={"v3c": "V3c 多元", "con": "V3-B 保守增强", "rp": "V3-B 风险平价"}[STRATEGY],
    weighting={"inverse_vol": "逆波动率", "hierarchical_rp": "分层风险平价"}[CFG["weighting"]],
    window=CFG["window"],
    max_w=CFG["max_w"],
    assets=', '.join(CFG["assets"]),
    trends=_build_trend_desc(),
    dip_thres=int(HS300_DIP_THRESHOLD * 100),
    dip_sma=HS300_DIP_SMA,
    dip_boost=HS300_DIP_BOOST,
    prem=int(PREMIUM_THRESHOLD * 100),
    vol_spike=VOLUME_SPIKE_THRESHOLD,
    cash=int(CASH_TIER * 100),
)
