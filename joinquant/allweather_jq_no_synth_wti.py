"""
全季节策略 — 聚宽版（无合成数据 + 原油 · 测试版）
====================================================
策略: V3c — 7资产逆波动率20d + nonferr/gold/sp500 75d趋势 + HS300 AND抄底
资产: 7只中国ETF（含原油），全部使用真实数据，不做久期合成

回测起点: 2024-03-20（30Y国债ETF 511130 上市日，所有ETF有真实数据）

使用方法:
  1. 打开聚宽 → 策略列表 → 新建策略
  2. 将本文件全部粘贴到代码编辑区
  3. 设置回测时间: 2024-03-20 ~ 最新
  4. 初始资金默认 100万
  5. 点击"运行回测"

与正式版的区别:
  - 去掉 30Y 国债久期合成（10Y×3.0），只用真实 ETF 数据
  - 回测起点从 2020-01-01 推迟到 2024-03-20
  - 仅保留 V3c 单策略，代码更短
  - 原油：南方原油LOF(501018)，作为第7资产加入通胀↑桶，无独立趋势过滤

参考: joinquant/allweather_jq.py, allweather/config.py
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
# 1. 策略参数
# ============================================================

STRATEGY = "v3c"
CASH_TIER = 0.00       # 现金比例: 0.00(100%) | 0.15(85%) | 0.30(70%)
START_DATE = "2024-03-20"  # 30Y国债ETF上市日，所有ETF有真实数据

# ============================================================
# 2. ETF 代码定义
# ============================================================

# 上海: .XSHG, 深圳: .XSHE
ETF = {
    "hs300":     "510300.XSHG",  # 沪深300ETF
    "us_sp500":  "513500.XSHG",  # 标普500ETF(QDII)
    "credit":    "511220.XSHG",  # 城投债ETF
    "bond_30y":  "511130.XSHG",  # 30年国债ETF（2024-03-20上市，真实数据）
    "gold":      "518880.XSHG",  # 黄金ETF
    "nonferr":   "159980.XSHE",  # 有色金属ETF
    "wti":       "501018.XSHG",  # 南方原油LOF（2019-04上市，真实数据）
}

ETF_NAMES = {
    "hs300": "沪深300", "us_sp500": "标普500", "credit": "城投债",
    "bond_30y": "30Y国债", "gold": "黄金", "nonferr": "有色",
    "wti": "原油",
}

# V3c 策略配置（硬编码，不切换）
# 注：wti 加入通胀↑桶，无独立趋势过滤 — 与正式版 V3C_ASSETS 保持一致
CFG = {
    "assets": ["hs300", "us_sp500", "credit", "bond_30y", "gold", "nonferr", "wti"],
    "weighting": "inverse_vol",
    "window": 20,
    "max_w": 0.25,
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

# HS300 AND 抄底参数
HS300_DIP_THRESHOLD = 0.25
HS300_DIP_BOOST = 1.8
HS300_DIP_SMA = 120
HS300_DIP_EXIT_RECOVERY = 0.15

# 溢价率过滤
PREMIUM_FILTER_ENABLED = True
PREMIUM_THRESHOLD = 0.05
PREMIUM_MAX_BACK_DAYS = 5

# 成交量异常过滤
VOLUME_ANOMALY_ENABLED = True
VOLUME_LOOKBACK = 60
VOLUME_SPIKE_THRESHOLD = 3.0

# 基准
BENCHMARK = "000300.XSHG"


# ============================================================
# 3. 核心数学 — 权重计算
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
    """逆波动率加权。1/vol 归一化后用 _clip_normalize 限制上下限。"""
    if len(returns_df) < max(20, window // 3):
        n = returns_df.shape[1]
        return np.full(n, 1.0 / n)

    recent = returns_df.tail(window)
    vols = recent.std() * np.sqrt(252)
    inv_vol = 1.0 / vols.replace(0, np.nan)
    raw = inv_vol / inv_vol.sum()
    return _clip_normalize(raw.values, min_w, max_w)


# ============================================================
# 4. 趋势过滤 + HS300 抄底状态机
# ============================================================

def apply_trend_filters(weights_dict, prices_dict, sma_store, current_date):
    """趋势过滤：跌破 SMA 的资产权重转入 credit。

    注：wti/原油无独立趋势过滤，仅 nonferr/gold/sp500 三条。
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

    return weights_dict


def hs300_dip_check(hs300_price, hs300_sma120, state):
    """HS300 AND抄底状态机（价格版，不含 PB/PE）。

    入场: drawdown > 25% AND price > SMA120 → boost = 1.8x
    出场: 已入场 AND 恢复到 peak-15% 以内 → 退出
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
        extra = weights_dict[hs] * (boost - 1.0)
        if weights_dict[credit] >= extra:
            weights_dict[hs] *= boost
            weights_dict[credit] -= extra
            log.info('[%s] HS300 抄底触发！回撤>%.0f%%, 1.8x boost, hs300=%.2f%%' % (
                date_str, HS300_DIP_THRESHOLD * 100, weights_dict[hs] * 100))

    return weights_dict


# ============================================================
# 5. 安全过滤器 — 溢价率 + 成交量异常
# ============================================================

def _get_net_value(code, date, max_back=5):
    """获取基金净值，若当天无则向前搜索最多 max_back 个交易日。"""
    try:
        start = date - datetime.timedelta(days=max_back * 3)
        net_df = get_extras('unit_net_value', code, start_date=start, end_date=date, df=True)
        if net_df is not None and not net_df.empty:
            vals = net_df[code].dropna()
            if len(vals) > 0:
                return float(vals.iloc[-1]), vals.index[-1]
    except Exception:
        pass

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
    """检查溢价率是否超过阈值。"""
    if not PREMIUM_FILTER_ENABLED:
        return None, False

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
    """检查近期成交量是否异常放大（恐慌信号）。"""
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
    """安全过滤器：溢价过高或量异常放大的资产，权重转入 credit。"""
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

        premium, excessive = check_premium(code, current_date)
        if excessive:
            log.info('[%s] %s 溢价率 %.1f%% > %.0f%%, 权重转 credit' % (
                date_str, asset, premium * 100, PREMIUM_THRESHOLD * 100))
            weights_dict[credit] += weights_dict[asset]
            weights_dict[asset] = 0.0
            continue

        vol_ratio, anomaly = check_volume_anomaly(code, current_date)
        if anomaly:
            log.info('[%s] %s 成交量异常放大 %.1fx, 权重转 credit' % (
                date_str, asset, vol_ratio))
            weights_dict[credit] += weights_dict[asset]
            weights_dict[asset] = 0.0

    return weights_dict


# ============================================================
# 6. SMA 预计算
# ============================================================

def precompute_smas(prices_dict):
    """预计算所有需要的 SMA 窗口。"""
    windows = set()
    for w in [CFG["nonferr_trend"], CFG["gold_trend"], CFG["sp500_trend"],
              CFG["hs300_trend"], HS300_DIP_SMA]:
        if w > 0:
            windows.add(w)
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
# 7. 数据加载 — 全部真实 ETF，无合成
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


def load_all_prices(start, end):
    """加载全部所需 ETF 价格序列（全部真实数据，无合成）。

    Returns:
        prices_dict: {asset_key: pd.Series}
        rets_df: pd.DataFrame, 日收益率
    """
    prices = {}
    failed = []

    for asset in CFG["assets"]:
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

    if not prices:
        raise RuntimeError('所有资产加载失败，请检查回测时间范围')

    px_df = pd.DataFrame(prices)
    rets = px_df.pct_change().dropna(how='all')

    common_start = rets.dropna(how='any').index[0] if len(rets.dropna(how='any')) > 0 else rets.index[0]

    log.info('[数据] 成功加载 %d/%d 个资产: %s' % (
        len(prices), len(CFG["assets"]), ', '.join(prices.keys())))
    log.info('[数据] 有效数据起点: %s' % common_start.strftime('%Y-%m-%d'))

    return prices, rets


# ============================================================
# 8. 策略主体 — initialize()
# ============================================================

def _safe_get_end_date(context):
    """安全获取回测结束日期。"""
    end = context.run_params.end_date
    if hasattr(end, 'strftime'):
        return end.strftime('%Y-%m-%d')
    return str(end)


def initialize(context):
    """策略初始化。"""
    set_benchmark(BENCHMARK)
    apply_cost_model()

    g.strategy_name = "V3c+原油 (无合成·测试版)"
    g.cash_tier = CASH_TIER
    g.assets = CFG["assets"]

    log.info('=' * 50)
    log.info('全季节策略 — 聚宽版(无合成+原油): %s' % g.strategy_name)
    log.info('资产(%d): %s' % (len(g.assets), ', '.join(g.assets)))
    log.info('加权方式: %s, 窗口: %dd' % (CFG["weighting"], CFG["window"]))
    log.info('现金比例: %.0f%%' % (CASH_TIER * 100))
    log.info('数据: 全部真实ETF, 起点 %s, 无久期合成' % START_DATE)
    log.info('原油: 南方原油LOF(501018) — 通胀↑桶, 无独立趋势过滤')
    log.info('安全过滤: 溢价率>%.0f%%=%s | 成交量>%.0fx=%s' % (
        PREMIUM_THRESHOLD * 100, 'ON' if PREMIUM_FILTER_ENABLED else 'OFF',
        VOLUME_SPIKE_THRESHOLD, 'ON' if VOLUME_ANOMALY_ENABLED else 'OFF'))
    log.info('=' * 50)

    # --- 加载数据 + 预计算 SMA ---
    end_date_str = _safe_get_end_date(context)
    prices_dict, rets_df = load_all_prices(START_DATE, end_date_str)
    g.prices = prices_dict
    g.rets = rets_df
    g.sma_store = precompute_smas(prices_dict)

    # --- 初始化状态 ---
    g.target_weights = {}
    g.target_position = 1.0
    g.hs300_state = {
        'peak': 1.0,
        'boosted': False,
    }
    g.first_rebalance = True

    # --- 月频调仓（每月首个交易日 14:50） ---
    run_monthly(monthly_rebalance, monthday=-1, time='14:50')  # 月末最后交易日


def apply_cost_model():
    """ETF 交易成本：万1佣金 + 免印花税 + 万1滑点。"""
    try:
        set_order_cost(
            OrderCost(
                open_tax=0,
                close_tax=0,
                open_commission=0.0001,
                close_commission=0.0001,
                close_today_commission=0,
                min_commission=0.1,
            ),
            type='fund',
        )
    except Exception:
        pass
    try:
        set_slippage(PriceSlippage(0.0001))
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

    # --- 1. 获取可用资产 ---
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

    rets_to_date = available_rets[available_rets.index <= current_date]
    if len(rets_to_date) < 20:
        log.info('[%s] 当前日期前数据不足，跳过调仓' % date_str)
        return

    # --- 3. 计算权重 ---
    w_arr = inverse_vol_weights(rets_to_date[available],
                                CFG["window"], CFG["max_w"], CFG["min_w"])
    weights = {a: float(w) for a, w in zip(available, w_arr) if w > 0.001}

    # --- 4. 获取当日价格 + SMA ---
    prices_today = {}
    for asset in weights:
        px_s = g.prices.get(asset)
        if px_s is not None and date_str in px_s.index:
            prices_today[asset] = float(px_s.loc[date_str])

    sma_dict = {}
    for w in set([CFG["nonferr_trend"], CFG["gold_trend"], CFG["sp500_trend"]]):
        if w > 0:
            for asset in weights:
                v = get_sma_at(g.sma_store, w, asset, current_date)
                if v is not None:
                    sma_dict.setdefault(w, {})[asset] = v

    hs300_sma120 = get_sma_at(g.sma_store, HS300_DIP_SMA, "hs300", current_date)

    # --- 5. 趋势过滤 ---
    weights = apply_trend_filters(weights, prices_today, sma_dict, current_date)

    # --- 6. 安全过滤器 ---
    weights = apply_safety_filters(weights, current_date)

    # --- 7. HS300 AND 抄底 ---
    hs300_px = prices_today.get("hs300")
    if hs300_px is not None and "hs300" in weights and "credit" in weights:
        weights = hs300_dip_apply(weights, hs300_px, hs300_sma120,
                                  g.hs300_state, date_str)
        if hs300_px > g.hs300_state.get('peak', 0):
            g.hs300_state['peak'] = hs300_px

    # --- 8. 应用现金比例 ---
    cash_scale = 1.0 - CASH_TIER
    target_weights = {a: w * cash_scale for a, w in weights.items()}
    g.target_weights = weights

    # --- 9. 日志 ---
    log.info('[%s] === V3c+原油 月频调仓 ===' % date_str)
    sorted_w = sorted(target_weights.items(), key=lambda x: -x[1])
    for asset, w in sorted_w[:7]:
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
    """先卖后买调仓。"""
    current_date = context.current_dt.strftime('%Y-%m-%d')
    target_by_code = {}
    for asset, weight in target_weights.items():
        code = ETF.get(asset)
        if code is not None and weight > 0:
            target_by_code[code] = weight

    # 卖出不在目标中的持仓
    for code, pos in list(context.portfolio.positions.items()):
        if pos.total_amount <= 0:
            continue
        if code in target_by_code:
            continue
        _safe_order_target_percent(context, code, 0)
        log.info('  卖出 %s' % code)

    # 买入/调整目标持仓
    for code, weight in target_by_code.items():
        if weight <= 0:
            continue
        _safe_order_target_percent(context, code, weight)
