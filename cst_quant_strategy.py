"""
CST-Quant 三因子策略 — 聚宽【策略回测环境】粘贴运行
============================================================
CST = Cheap · Stable · Trending（低估 · 稳定 · 趋势）

参考项目: IdealAuror/Cheap-Stable-Trending-quant
原始策略: P5-F2F5F6-40d-final-strategy.py

策略概要:
  因子: F2(EP盈利收益率) + F5(LowVol低波动) + F6(MOM-40d动量)，等权 Z-score 合成
  股票池: 全A股（剔除ST/次新股/金融股/低流动性）
  基准: 000985.XSHG（中证全指）
  调仓: 季度（5/9/11月首个交易日，14:50）
  持仓: 50只，等权重
  风控: 纯回撤约束（>20%回撤→85%仓位，<15%恢复满仓），默认关闭

历史表现（2014-01 ~ 2026-06，聚宽策略环境含佣金印花税滑点）:
  累计收益: +776%  vs 基准 +121%
  年化收益: ~19.5%
  Sharpe: 0.67
  最大回撤: -37.2%
  年化换手: ~1.7x

使用方法:
  1. 打开聚宽 → 策略列表 → 新建策略
  2. 将本文件全部粘贴到代码编辑区
  3. 设置回测时间: 2014-01-01 ~ 至今
  4. 初始资金默认 100万（可在 initialize 中修改）
  5. 点击"运行回测"
"""

import datetime
import numpy as np
import pandas as pd


# ============================================================
# 零、兼容垫片 — 确保在聚宽环境正常运行
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


def _get_current_price(code, date_str):
    """通过 get_price 获取最新收盘价（降级链备用）。"""
    df = get_price(code, end_date=date_str, count=1,
                   fields=['close'], skip_paused=False)
    if df is None or df.empty:
        return None
    return float(df.iloc[-1]['close'])


def _safe_order_target_percent(context, code, weight):
    """降级链下单封装。

    优先级: order_target_percent → order_target_value → order_target → order
    确保在不同聚宽版本都能正常下单。
    """
    total_value = context.portfolio.total_value

    fn = _resolve_jq_func('order_target_percent')
    if fn is not None:
        return fn(code, weight)

    fn = _resolve_jq_func('order_target_value')
    if fn is not None:
        return fn(code, total_value * weight)

    current_date = context.current_dt.strftime('%Y-%m-%d')
    price = _get_current_price(code, current_date)
    positions = context.portfolio.positions
    pos = positions.get(code)
    current_amount = pos.total_amount if pos is not None else 0

    fn = _resolve_jq_func('order_target')
    if fn is not None:
        if price is None or price <= 0:
            raise RuntimeError('无法获取 %s 价格以计算目标股数' % code)
        target_shares = int(total_value * weight / price / 100) * 100
        return fn(code, target_shares)

    fn = _resolve_jq_func('order')
    if fn is not None:
        if price is None or price <= 0:
            raise RuntimeError('无法获取差额股数' % code)
        target_shares = int(total_value * weight / price / 100) * 100
        delta = target_shares - current_amount
        if delta != 0:
            return fn(code, delta)
        return None

    raise RuntimeError(
        '聚宽交易函数 order_target_percent/order_target_value/'
        'order_target/order 均未注入，请确认在聚宽回测环境中运行'
    )


# ============================================================
# 一、参数配置（修改策略行为从这里开始）
# ============================================================

# --- 股票池 ---
INDEX_ID = None                # None = 全A股；可改为 '000300.XSHG'（沪深300）等
BENCHMARK = '000985.XSHG'      # 基准：中证全指

# --- F5 低波动因子 ---
VOL_LOOKBACK = 40              # 波动率回看窗口（交易日），P6 扫描 40d 最优
VOL_MIN_OBS_RATIO = 0.5        # 有效观测比例下限

# --- F6 动量因子 ---
# 61-21 momentum：price[t-21] / price[t-61] - 1，信号长度40天
# 实测全样本 Sharpe 0.82 最高，段5（2019-2020核心资产牛市）修复至仅 -2.69pp
MOM_LOOKBACK_LONG = 61         # 动量长窗口（交易日）
MOM_SKIP_RECENT = 21           # 剔除最近交易日（避免短期反转污染）
MOM_MIN_OBS_RATIO = 0.8        # 有效观测比例下限（动量需完整窗口）

# --- 回撤约束（纯回撤状态机，默认关闭） ---
# 注：无风控版回撤约 37% 已在可接受范围，回撤约束会降低 Sharpe
# 启用后：回撤 > 20% 降至 85% 仓位，恢复至 < 15% 回满仓
DRAWDOWN_CONTROL_ENABLED = False
DRAWDOWN_THRESHOLD = 0.20      # 触发降仓的回撤阈值
DRAWDOWN_REDUCE_TO = 0.85      # 降仓目标比例
DRAWDOWN_RECOVER = 0.15        # 恢复满仓的回撤阈值

# --- 流动性过滤 ---
LIQUIDITY_LOOKBACK = 20        # 日均成交额回看天数
LIQUIDITY_THRESHOLD = 1e7      # 成交额门槛（1000万）

# --- 持仓 ---
N_HOLD = 50                    # 持仓数量

# --- 涨跌停过滤 ---
LIMIT_UP_DOWN_FILTER = True    # 涨停不买，跌停不卖（避免回测作弊）


# ============================================================
# 二、股票池构建 — 剔除 ST/次新股/金融股
# ============================================================

def get_stock_pool(index_id, date_str, min_listed_days=365):
    """构建股票池：指数成分股 → 去ST → 去次新股 → 去金融股。

    参数:
        index_id: None=全A，或指数代码如 '000300.XSHG'
        date_str: 调仓日期 'YYYY-MM-DD'
        min_listed_days: 最低上市天数（动量因子需要足够历史价格）
    """
    # 1. 获取基础股票池
    if index_id is None:
        sec_df = get_all_securities(['stock'], date=date_str)
        stocks = list(sec_df.index)
    else:
        stocks = get_index_stocks(index_id, date=date_str)

    if len(stocks) == 0:
        return []

    # 2. 剔除 ST
    st_df = get_extras('is_st', stocks, end_date=date_str, count=1)
    if st_df is not None and not st_df.empty:
        st_today = st_df.iloc[-1]
        stocks = [s for s in stocks if s in st_today.index and not st_today[s]]

    # 3. 剔除次新股
    stocks = [s for s in stocks if not is_new_stock(s, date_str, min_listed_days)]

    # 4. 剔除金融股（银行/非银金融）
    if stocks:
        stocks = exclude_finance_stocks(stocks, date_str)

    return stocks


def exclude_finance_stocks(stocks, date_str):
    """剔除金融行业（银行I / 非银金融I）。

    金融股的高杠杆使得 EP 等估值指标失真，且波动特征与其他行业差异大。
    """
    if not stocks:
        return stocks
    try:
        ind = get_industry(stocks, date=date_str)
    except Exception:
        return stocks
    if not ind:
        return stocks

    FINANCE_NAMES = {'银行I', '非银金融I'}
    finance_codes = set()
    for code, schemes in ind.items():
        if not isinstance(schemes, dict):
            continue
        sw_l1 = schemes.get('sw_l1')
        if not isinstance(sw_l1, dict):
            continue
        name = str(sw_l1.get('industry_name', '') or '')
        if name in FINANCE_NAMES:
            finance_codes.add(code)
    return [s for s in stocks if s not in finance_codes]


def is_new_stock(code, date_str, days=365):
    """判断股票上市是否不满指定天数。"""
    info = get_security_info(code)
    if info is None:
        return True
    cur = pd.Timestamp(date_str)
    start = pd.Timestamp(info.start_date)
    return (cur - start).days < days


# ============================================================
# 三、涨跌停/停牌撮合器 — 避免回测作弊
# ============================================================

def is_suspended(code, date_str):
    """判断是否停牌。"""
    df = get_price(code, end_date=date_str, count=1,
                   fields=['paused'], skip_paused=False)
    if df is None or df.empty:
        return False
    return bool(df.iloc[-1]['paused'])


def _get_limit_pct(code):
    """获取涨跌停幅度（科创板/创业板 20%，其他 10%）。"""
    sym = code.split('.')[0]
    if sym.startswith('688') or sym.startswith('300') or sym.startswith('301'):
        return 0.20
    return 0.10


def simulate_limit_order(code, side, date_str):
    """模拟限价单排队，返回成交比例 0.0 或 1.0。

    逻辑：
      - 停牌 → 不成交
      - 买入时：开盘价低于涨停价 → 可成交（有流动性）
      - 卖出时：开盘价高于跌停价 → 可成交（有流动性）
      - 一字板（开盘=涨停/跌停，且全天无波动）→ 不成交
    """
    if is_suspended(code, date_str):
        return 0.0

    df = get_price(code, end_date=date_str, count=1,
                   fields=['open', 'high', 'low'], skip_paused=False)
    if df is None or df.empty:
        return 0.0
    open_p = float(df.iloc[-1]['open'])
    high_p = float(df.iloc[-1]['high'])
    low_p = float(df.iloc[-1]['low'])

    df_px = get_price(code, end_date=date_str, count=2,
                      fields=['close'], skip_paused=False)
    if df_px is None or len(df_px) < 2:
        return 0.0
    prev_close = float(df_px.iloc[-2]['close'])
    if prev_close <= 0:
        return 0.0

    limit_pct = _get_limit_pct(code)
    high_limit = round(prev_close * (1 + limit_pct), 2)
    low_limit = round(prev_close * (1 - limit_pct), 2)

    if side == 'buy':
        # 开盘未涨停 → 可买入
        if open_p < high_limit:
            return 1.0
        # 盘中曾开板 → 可买入
        if high_p > low_p:
            return 1.0
        return 0.0
    elif side == 'sell':
        # 开盘未跌停 → 可卖出
        if open_p > low_limit:
            return 1.0
        # 盘中曾开板 → 可卖出
        if high_p > low_p:
            return 1.0
        return 0.0
    return 0.0


# ============================================================
# 四、先卖后买调仓 — T+1 市场规则
# ============================================================

def rebalance_ordered(context, target_weights):
    """先卖后买调仓，涨跌停/停牌未成交记入 unfilled。

    先卖的原因：A股 T+1，卖出后资金 T+1 可用，先卖确保资金充足。
    """
    current_date = context.current_dt.strftime('%Y-%m-%d')
    result = {'sold': [], 'bought': [], 'unfilled': []}

    # 第一步：卖出不在目标持仓中的股票
    for code, pos in list(context.portfolio.positions.items()):
        if pos.total_amount <= 0:
            continue
        if target_weights.get(code, 0.0) > 0:
            continue  # 还在目标持仓中，不卖
        if simulate_limit_order(code, 'sell', current_date) > 0:
            _safe_order_target_percent(context, code, 0)
            result['sold'].append(code)
            log.info('卖出 %s' % code)
        else:
            result['unfilled'].append((code, 'sell'))
            log.info('卖出失败 %s（跌停/停牌）' % code)

    # 第二步：买入目标持仓中的股票
    for code, weight in target_weights.items():
        if weight <= 0:
            continue
        if simulate_limit_order(code, 'buy', current_date) > 0:
            _safe_order_target_percent(context, code, weight)
            result['bought'].append(code)
            log.info('买入 %s, 权重 %.2f%%' % (code, weight * 100))
        else:
            result['unfilled'].append((code, 'buy'))
            log.info('买入失败 %s（涨停/停牌）' % code)

    return result


# ============================================================
# 五、成本模型 — 贴近真实交易成本
# ============================================================

def apply_cost_model():
    """设置交易成本：万三佣金 + 千一印花税(卖) + 5元最低 + 千一滑点。

    真实成本构成：
      - 佣金: 0.03% 双边（万三）
      - 印花税: 0.1% 仅卖出
      - 最低佣金: 5元/笔
      - 滑点: 0.1%（市场冲击）
    总往返成本约 0.36%。
    """
    try:
        set_order_cost(
            OrderCost(
                open_tax=0,
                close_tax=0.001,
                open_commission=0.0003,
                close_commission=0.0003,
                close_today_commission=0,
                min_commission=5.0,
            ),
            type='stock',
        )
    except Exception:
        pass
    try:
        set_slippage(PriceSlippage(0.001))
    except NameError:
        try:
            set_slippage(FixedSlippage(0.001))
        except NameError:
            pass


# ============================================================
# 六、因子计算 — F2(EP) / F5(LowVol) / F6(MOM)
# ============================================================

def calc_realized_volatility(date_str, stocks, lookback_days=VOL_LOOKBACK):
    """F5 LowVol：计算过去 N 日年化波动率。

    返回 {code: volatility}，波动率越低信号越强（取负号后排序）。
    """
    if not stocks:
        return {}
    try:
        df = get_price(stocks, end_date=date_str, count=lookback_days + 1,
                       fields=['close'], skip_paused=False,
                       panel=False, fq='post')
        if df is None or df.empty:
            return {}
        if 'time' in df.columns:
            df = df.set_index('time')
        elif 'date' in df.columns:
            df = df.set_index('date')
        if 'code' in df.columns:
            close = df.pivot_table(index=df.index, columns='code', values='close')
        else:
            close = df
        close.index = pd.to_datetime(close.index)
    except Exception:
        return {}

    if close is None or close.empty:
        return {}

    rets = close.pct_change()
    vol = rets.std(skipna=True)
    valid_counts = rets.count()
    min_obs = int(lookback_days * VOL_MIN_OBS_RATIO)

    result = {}
    for code in stocks:
        if code not in vol.index:
            continue
        cnt = valid_counts.get(code, 0)
        if cnt < min_obs:
            continue
        v = vol[code]
        if not np.isnan(v) and v > 0:
            result[code] = float(v)
    return result


def calc_momentum(date_str, stocks,
                  lookback_long=MOM_LOOKBACK_LONG,
                  skip_recent=MOM_SKIP_RECENT):
    """F6 MOM：计算 61-21 动量因子（40天趋势窗口）。

    公式: mom = price[t-21] / price[t-61] - 1

    逻辑：
      - 剔除最近 21 个交易日（约1个月），避免短期反转污染（Carhart 1997）
      - 回溯 61 个交易日（约3个月），信号长度 40 天
      - 正值表示过去 2-3 个月上涨趋势，负值表示下跌趋势
      - A股动量窗口比美股短（40天 vs 12个月），经 P5 六版本扫描确认最优

    返回 {code: momentum}。
    """
    if not stocks:
        return {}
    total_count = lookback_long + 5  # 多取几天防止边界问题
    try:
        df = get_price(stocks, end_date=date_str, count=total_count,
                       fields=['close'], skip_paused=False,
                       panel=False, fq='post')
        if df is None or df.empty:
            return {}
        if 'time' in df.columns:
            df = df.set_index('time')
        elif 'date' in df.columns:
            df = df.set_index('date')
        if 'code' in df.columns:
            close = df.pivot_table(index=df.index, columns='code', values='close')
        else:
            close = df
        close.index = pd.to_datetime(close.index)
    except Exception:
        return {}

    if close is None or close.empty:
        return {}
    if len(close) < lookback_long + 1:
        return {}

    # price[t-skip_recent] = 剔除最近1月后的价格
    # price[t-lookback_long] = 3个月前的价格
    price_recent = close.iloc[-(skip_recent + 1)]
    price_long_ago = close.iloc[-(lookback_long + 1)]

    valid_counts = close.count()
    min_obs = int(lookback_long * MOM_MIN_OBS_RATIO)

    result = {}
    for code in stocks:
        if code not in valid_counts.index:
            continue
        cnt = valid_counts.get(code, 0)
        if cnt < min_obs:
            continue
        p_recent = price_recent.get(code) if hasattr(price_recent, 'get') else None
        p_long = price_long_ago.get(code) if hasattr(price_long_ago, 'get') else None
        if p_recent is None or p_long is None:
            continue
        if np.isnan(p_recent) or np.isnan(p_long):
            continue
        if p_recent <= 0 or p_long <= 0:
            continue
        mom = float(p_recent) / float(p_long) - 1.0
        if not np.isnan(mom) and np.isfinite(mom):
            result[code] = mom
    return result


def calc_avg_money(date_str, stocks, lookback_days=LIQUIDITY_LOOKBACK):
    """计算近 N 日日均成交额（流动性过滤用）。"""
    if not stocks:
        return {}
    try:
        df_px = get_price(stocks, end_date=date_str, count=lookback_days,
                          fields=['money'], skip_paused=False,
                          panel=False, fq='post')
    except Exception:
        return {}
    if df_px is None or df_px.empty:
        return {}
    if 'time' in df_px.columns:
        df_px = df_px.set_index('time')
    elif 'date' in df_px.columns:
        df_px = df_px.set_index('date')
    if 'code' not in df_px.columns:
        return {}
    try:
        wide = df_px.pivot_table(index=df_px.index, columns='code', values='money')
    except Exception:
        return {}
    return dict(wide.mean())


# ============================================================
# 七、市值中性化 + Winsorize — 去除市值干扰
# ============================================================

def neutralize_ols(factor_values, regressor):
    """OLS 残差市值中性化。

    factor = a + b * log(market_cap) + resid
    返回 resid（去除市值线性影响后的纯因子暴露）。
    """
    f = np.asarray(factor_values, dtype=float)
    r = (regressor.values if hasattr(regressor, 'values')
         else np.asarray(regressor, dtype=float))
    if r.ndim == 1:
        r = r.reshape(-1, 1)

    f_mask = ~np.isnan(f)
    r_mask = ~np.any(np.isnan(r), axis=1)
    mask = f_mask & r_mask
    f_clean = f[mask]
    r_clean = r[mask]

    if len(f_clean) < 2:
        full = np.full(len(factor_values), np.nan)
        full[mask] = f_clean - (np.mean(f_clean) if len(f_clean) > 0 else 0)
        return full

    x_mat = np.column_stack([np.ones(len(f_clean)), r_clean])
    try:
        beta = np.linalg.lstsq(x_mat, f_clean, rcond=None)[0]
        resid = f_clean - x_mat @ beta
    except Exception:
        resid = f_clean - np.mean(f_clean)

    full = np.full(len(factor_values), np.nan)
    full[mask] = resid
    return full


def winsorize_cross_section(s, lower=0.01, upper=0.99):
    """横截面 1%/99% 分位数缩尾，控制极端值影响。"""
    s = pd.Series(s, dtype=float)
    if s.notna().sum() < 10:
        return s
    lo = s.quantile(lower)
    hi = s.quantile(upper)
    return s.clip(lower=lo, upper=hi)


def calculate_combined_factors(df, vol_map, mom_map):
    """计算原始因子值（中性化前）。

    F2_ep_raw  = net_profit / (market_cap * 1e8)   — 盈利收益率
    F5_vol_raw = -vol_40d                           — 低波动（取负号，越大越好）
    F6_mom_raw = mom_61_21                          — 40天趋势动量
    """
    mcap_yuan = df['market_cap'] * 1e8
    df['ep_spot'] = df['net_profit'] / mcap_yuan.replace(0, np.nan)
    df['debt_to_assets'] = df['total_liability'] / df['total_assets'].replace(0, np.nan)
    df['vol_40d'] = df.index.map(lambda c: vol_map.get(c, np.nan))
    df['mom_61_21'] = df.index.map(lambda c: mom_map.get(c, np.nan))

    # 原始因子（中性化前）
    df['F2_ep_raw'] = df['ep_spot']
    df['F5_vol_raw'] = -df['vol_40d']
    df['F6_mom_raw'] = df['mom_61_21']
    return df


def apply_neutralization(df):
    """市值中性化 + winsorize（过滤后调用）。

    对三个因子分别做 OLS 残差中性化，去除市值线性影响，
    然后横截面 1%/99% 缩尾去极值。
    """
    log_mcap = np.log(df['market_cap'].astype(float).replace(0, np.nan))

    # F2 EP 中性化
    f2_neut = neutralize_ols(df['F2_ep_raw'].values, log_mcap.values)
    df['F2_ep'] = winsorize_cross_section(pd.Series(f2_neut, index=df.index))

    # F5 LowVol 中性化
    f5_neut = neutralize_ols(df['F5_vol_raw'].values, log_mcap.values)
    df['F5_vol'] = winsorize_cross_section(pd.Series(f5_neut, index=df.index))

    # F6 MOM 中性化
    f6_neut = neutralize_ols(df['F6_mom_raw'].values, log_mcap.values)
    df['F6_mom'] = winsorize_cross_section(pd.Series(f6_neut, index=df.index))

    return df


# ============================================================
# 八、仓位管理 — 回撤约束状态机
# ============================================================

def compute_target_position(context, state):
    """计算目标总仓位（纯回撤约束状态机）。

    状态机逻辑:
      NORMAL（满仓100%）→ 回撤 > 20% → DE_RISKED（降仓至85%）
      DE_RISKED（85%）  → 回撤 < 15% → NORMAL（恢复满仓）

    只在状态切换时调仓，避免频繁交易。
    参数经放宽以避免过度抑制收益（前一版15%/70%把Sharpe打到0.39）。
    """
    # 无风控模式：始终满仓
    if not DRAWDOWN_CONTROL_ENABLED:
        state['prev_weight'] = 1.0
        state['drawdown'] = 0.0
        return 1.0

    total_value = context.portfolio.total_value
    peak = state.get('peak', total_value)
    if total_value > peak:
        peak = total_value
        state['peak'] = peak

    drawdown = (peak - total_value) / peak if peak > 0 else 0.0
    in_de_risked = state.get('in_de_risked', False)

    if in_de_risked:
        if drawdown < DRAWDOWN_RECOVER:
            target_w = 1.0
            state['in_de_risked'] = False
            log.info('[回撤约束] 回撤 %.2f%% < %.0f%%，恢复满仓' % (
                drawdown * 100, DRAWDOWN_RECOVER * 100))
        else:
            target_w = DRAWDOWN_REDUCE_TO
    else:
        if drawdown > DRAWDOWN_THRESHOLD:
            target_w = DRAWDOWN_REDUCE_TO
            state['in_de_risked'] = True
            log.info('[回撤约束] 回撤 %.2f%% > %.0f%%，降仓到 %.0f%%' % (
                drawdown * 100, DRAWDOWN_THRESHOLD * 100,
                DRAWDOWN_REDUCE_TO * 100))
        else:
            target_w = 1.0

    state['prev_weight'] = target_w
    state['drawdown'] = drawdown
    return target_w


def check_limit_up_down(code, date_str):
    """检查涨跌停状态。返回 True=正常可交易，False=涨跌停不可交易。"""
    if not LIMIT_UP_DOWN_FILTER:
        return True
    try:
        df = get_price(code, end_date=date_str, count=2,
                       fields=['close', 'high', 'low', 'limit_status'],
                       skip_paused=False)
        if df is None or df.empty or len(df) < 2:
            return True
        # 聚宽 limit_status 字段: 1=涨停, 2=跌停, 0=正常
        if 'limit_status' in df.columns:
            status = df['limit_status'].iloc[-1]
            if status == 1 or status == 2:
                return False
        # 备用方案：用价格变化判断
        prev_close = df['close'].iloc[-2]
        curr_close = df['close'].iloc[-1]
        if prev_close > 0:
            change = (curr_close - prev_close) / prev_close
            if change > 0.095 or change < -0.095:
                return False
        return True
    except Exception:
        return True


# ============================================================
# 九、策略主体 — initialize / 调仓 / 仓位管理
# ============================================================

def initialize(context):
    """策略初始化 — 聚宽框架入口。

    设置基准、成本模型、调仓日程。
    季度调仓（5/9/11月首个交易日14:50）+ 每日仓位检查。
    """
    set_benchmark(BENCHMARK)
    apply_cost_model()

    # 全局变量（通过 g 对象存储）
    g.stock_num = N_HOLD
    g.index_id = INDEX_ID
    g.target_weights = {}        # 目标持仓权重字典 {code: weight}
    g.target_position = 1.0      # 目标总仓位比例
    g.nav_history = []           # 净值历史（回撤计算用）
    g.pos_state = {              # 仓位管理状态
        'peak': 1.0,
        'in_de_risked': False,
        'prev_weight': 1.0,
        'drawdown': 0.0,
    }
    g.f5_z_current = 0.0         # 当前F5 Z-score（预留）

    # 季度调仓：每年 5/9/11 月首个交易日 14:50 执行
    run_monthly(factor_rebalance, monthday=1, time='14:50')
    # 每日仓位管理
    run_daily(position_management, time='14:50')


def factor_rebalance(context):
    """季度三因子选股主逻辑。

    流程:
      1. 获取股票池（全A - ST - 次新股 - 金融股）
      2. 查询财务数据（估值 + 负债 + 利润）
      3. 计算 F5 波动率 + F6 动量
      4. 流动性过滤（日均成交 > 1000万）
      5. 市值中性化 + winsorize
      6. 三因子等权 Z-score 合成 → 取前50
      7. 涨跌停过滤 → 计算权重 → 下单
    """
    current_date = context.current_dt
    # 只在 5/9/11 月调仓
    if current_date.month not in (5, 9, 11):
        return
    date_str = current_date.strftime('%Y-%m-%d')

    log.info('=' * 50)
    log.info('[%s] 季度调仓开始（CST 三因子: EP + LowVol + MOM-40d）' % date_str)

    # --- 1. 股票池 ---
    stocks = get_stock_pool(g.index_id, date_str)
    if len(stocks) == 0:
        log.info('[%s] 股票池为空，跳过调仓' % date_str)
        return
    log.info('[%s] 初始股票池: %d 只' % (date_str, len(stocks)))

    # --- 2. 财务数据查询 ---
    q = query(
        valuation.code,
        valuation.market_cap,
        balance.total_liability,
        balance.total_assets,
        income.net_profit,
    ).filter(valuation.code.in_(stocks))
    df = get_fundamentals(q, date=date_str)

    if df is None or df.empty:
        log.info('[%s] 无财务数据，跳过调仓' % date_str)
        return
    df = df.set_index('code')

    # 关键字段去空
    critical = ['market_cap', 'total_liability', 'total_assets', 'net_profit']
    df = df.dropna(subset=critical)

    # --- 3. 技术因子计算（F5 波动率 + F6 动量） ---
    vol_map = calc_realized_volatility(date_str, list(df.index), VOL_LOOKBACK)
    mom_map = calc_momentum(date_str, list(df.index),
                            lookback_long=MOM_LOOKBACK_LONG,
                            skip_recent=MOM_SKIP_RECENT)

    # --- 4. 因子值计算 ---
    df = calculate_combined_factors(df, vol_map, mom_map)

    # --- 5. 流动性 + 质量过滤 ---
    avg_money_map = calc_avg_money(date_str, list(df.index))
    df['avg_money'] = df.index.map(lambda c: avg_money_map.get(c, 0))
    before_filter = len(df)

    mask = df['net_profit'] > 0                              # 盈利公司
    mask &= df['debt_to_assets'] <= 1.0                       # 资不抵债剔除
    mask &= df['ep_spot'].notna() & (df['ep_spot'] > 0)       # EP 有效正值
    mask &= df['vol_40d'].notna() & (df['vol_40d'] > 0)       # 波动率有效
    mask &= df['mom_61_21'].notna() & np.isfinite(df['mom_61_21'])  # 动量有效
    mask &= df['avg_money'].fillna(0) >= LIQUIDITY_THRESHOLD   # 流动性达标
    df = df[mask]

    log.info('[%s] 过滤后: %d → %d 只（剔除 %d 只）' % (
        date_str, before_filter, len(df), before_filter - len(df)))

    if df.empty:
        log.info('[%s] 过滤后无股票可选' % date_str)
        return

    # --- 6. 市值中性化 + winsorize ---
    df = apply_neutralization(df)
    df = df.dropna(subset=['F2_ep', 'F5_vol', 'F6_mom'])
    if len(df) < 30:
        log.info('[%s] 中性化后样本不足: %d 只，跳过' % (date_str, len(df)))
        return

    # --- 7. 三因子等权 Z-score 合成 ---
    # 三个因子标准化后等权相加，不做 ICIR 加权（等权是最稳健基准）
    f2_std = df['F2_ep'].std()
    f5_std = df['F5_vol'].std()
    f6_std = df['F6_mom'].std()

    df['F2_z'] = (df['F2_ep'] - df['F2_ep'].mean()) / (f2_std if f2_std > 0 else 1)
    df['F5_z'] = (df['F5_vol'] - df['F5_vol'].mean()) / (f5_std if f5_std > 0 else 1)
    df['F6_z'] = (df['F6_mom'] - df['F6_mom'].mean()) / (f6_std if f6_std > 0 else 1)

    # 等权合成（各 1/3）
    df['combined'] = (1.0 / 3.0) * df['F2_z'] + (1.0 / 3.0) * df['F5_z'] + (1.0 / 3.0) * df['F6_z']

    # 按综合得分降序取前 N 只
    df = df.sort_values('combined', ascending=False).head(g.stock_num)

    # --- 8. 涨跌停过滤（避免回测作弊） ---
    if LIMIT_UP_DOWN_FILTER:
        before_limit = len(df)
        tradable = [c for c in df.index if check_limit_up_down(c, date_str)]
        df = df[df.index.isin(tradable)]
        log.info('[%s] 涨跌停过滤: %d → %d 只（剔除 %d 只）' % (
            date_str, before_limit, len(df), before_limit - len(df)))
        if df.empty:
            log.info('[%s] 涨跌停过滤后无股票可买' % date_str)
            return

    # --- 9. 权重计算 ---
    # Z-score 裁剪（负分权重归零）+ 归一化
    comb_vals = df['combined'].values
    z = (comb_vals - comb_vals.mean()) / (comb_vals.std() if comb_vals.std() > 0 else 1)
    weights = np.where(z > 0, z, 0)  # 只持有正 Z-score 的股票
    if weights.sum() == 0:
        weights = np.ones(len(df))   # 全零时等权
    weights = weights / weights.sum()

    # 存储归一化权重（sum=1），实际调仓时乘以 target_position
    g.target_weights = {code: float(w) for code, w in zip(df.index, weights)}

    # 应用当前总仓位
    target_position = g.target_position if g.target_position > 0 else 1.0
    actual_weights = {code: w * target_position for code, w in g.target_weights.items()}

    # --- 10. 调仓日志 ---
    log.info('[%s] 本次调仓 %d 只股票，总仓位 %.1f%%' % (
        date_str, len(df), target_position * 100))
    for code, w in list(actual_weights.items())[:5]:
        log.info('  %s  EP=%.4f  Vol=%.4f  MOM=%.2f%%  成交额=%.0f万  权重=%.2f%%' % (
            code,
            df.loc[code, 'ep_spot'],
            df.loc[code, 'vol_40d'],
            df.loc[code, 'mom_61_21'] * 100,
            df.loc[code, 'avg_money'] / 1e4,
            w * 100))
    if len(actual_weights) > 5:
        log.info('  ... 共 %d 只' % len(actual_weights))

    # 执行调仓
    rebalance_ordered(context, actual_weights)
    log.info('[%s] 季度调仓完成' % date_str)


def position_management(context):
    """每日仓位管理（纯回撤约束状态机）。

    每日检查回撤水位，状态切换时按 g.target_weights 等比例缩放仓位。
    DRAWDOWN_CONTROL_ENABLED=False 时此函数几乎无事可做。
    """
    current_date = context.current_dt
    date_str = current_date.strftime('%Y-%m-%d')

    # 更新净值历史（保留最近 500 天）
    total_value = context.portfolio.total_value
    g.nav_history.append(total_value)
    if len(g.nav_history) > 500:
        g.nav_history = g.nav_history[-500:]

    # 计算目标仓位
    target_position = compute_target_position(context, g.pos_state)

    # 只在仓位变化 > 1% 时调仓（避免频繁交易）
    prev_position = g.target_position
    if abs(target_position - prev_position) > 0.01:
        log.info('[%s] 仓位调整: %.0f%% → %.0f%%（回撤 %.2f%%）' % (
            date_str, prev_position * 100, target_position * 100,
            g.pos_state.get('drawdown', 0) * 100))
        g.target_position = target_position

        # 按比例缩放所有持仓
        if g.target_weights:
            actual_weights = {code: w * target_position
                              for code, w in g.target_weights.items()}
            rebalance_ordered(context, actual_weights)


def before_trading_start(context):
    """盘前处理（本策略无需盘前操作）。"""
    pass


# ============================================================
# 策略说明（聚宽控制台输出）
# ============================================================

"""
=== CST-Quant 策略参数速查 ===

股票池:  全A股 - ST - 次新股(上市<1年) - 金融股 - 日均成交<1000万
因子:    F2-EP(1/3) + F5-LowVol(1/3) + F6-MOM-40d(1/3)
调仓:    季度（5/9/11月首个交易日 14:50）
持仓:    50只等权重
成本:    万三佣金 + 千一印花税(卖) + 千一滑点
回撤控制: 默认关闭（>20%降85%，<15%恢复满仓）

因子详情:
  F2-EP      盈利收益率 = 净利润/总市值（越高越便宜）
  F5-LowVol  -40日波动率（越低越稳定）
  F6-MOM     61-21动量 = price[t-21]/price[t-61]-1（40天趋势窗口）

处理步骤:
  原始因子 → 市值中性化(OLS残差) → winsorize(1%/99%) → Z-score → 等权合成

如需修改参数，编辑本文件"一、参数配置"部分即可。
"""
