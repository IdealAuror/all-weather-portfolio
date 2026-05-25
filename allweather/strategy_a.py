"""方案 A：固定权重 + 三层风控（久期调整 + 趋势过滤 + 回撤止损）。"""
import pandas as pd
import numpy as np
from .config import (
    REBAL_THRESHOLD, RISK_FREE_RATE,
    TREND_LOOKBACK_MONTHS, DRAWDOWN_STOP as DD_STOP,
    DRAWDOWN_RECOVER, DRAWDOWN_TARGET_CAP,
)
from .risk import trend_filter, drawdown_stop


def backtest_a(weights: pd.Series, rets: pd.DataFrame,
               cash_ratio: float = 0.0) -> tuple:
    """Plan A backtest.

    Three-layer protection:
    1. Duration restructured (done at weight level in portfolios.py)
    2. Monthly trend filter: any asset 12m momentum negative → move to cash
    3. Drawdown stop: portfolio DD > 8% → cap position at 50%

    Returns:
        nv (pd.Series): Net value series (starts at 1.0)
        n_rebal (int): Total rebalance count
        n_trend_trig (int): Trend filter trigger count
        n_dd_trig (int): Drawdown stop trigger count
    """
    cols = list(weights.index)
    target = weights.values * (1 - cash_ratio)
    nv = pd.Series(index=rets.index, dtype=float)
    h = pd.Series(target, index=cols)
    v = 1.0
    n_rebal = 0
    n_trend_trig = 0
    n_dd_trig = 0
    in_drawdown_stop = False

    rebal_dates = set()  # 纯阈值触发，无日历节点

    for i, d in enumerate(rets.index):
        if i == 0:
            nv.loc[d] = 1.0
            continue

        v *= 1 + (h * rets.loc[d, cols]).sum() + cash_ratio * RISK_FREE_RATE
        nv.loc[d] = v
        h = h * (1 + rets.loc[d, cols])
        s = h.sum()
        if s > 0:
            h = h / s * (1 - cash_ratio)

        # === Monthly trend filter check ===
        if d.month != rets.index[i - 1].month:
            lookback_days = TREND_LOOKBACK_MONTHS * 21
            for a in cols:
                asset_ret = rets.loc[:d, a].tail(lookback_days)
                if trend_filter(asset_ret):
                    h[a] = 0.0
                    n_trend_trig += 1
            for a in cols:
                if h[a] == 0.0:
                    asset_ret = rets.loc[:d, a].tail(lookback_days)
                    if not trend_filter(asset_ret):
                        h[a] = target[a]
            s = h.sum()
            if s > 0:
                h = h / s * (1 - cash_ratio)

        # === Drawdown stop ===
        if in_drawdown_stop:
            if not drawdown_stop(nv.loc[:d], DRAWDOWN_RECOVER):
                in_drawdown_stop = False
                h = pd.Series(target, index=cols)
                n_rebal += 1
        else:
            if drawdown_stop(nv.loc[:d], DD_STOP):
                in_drawdown_stop = True
                h = h * DRAWDOWN_TARGET_CAP
                n_dd_trig += 1
                n_rebal += 1

        # === Base rebalancing (threshold only) ===
        if not in_drawdown_stop:
            triggered = abs(h.values - target).max() > REBAL_THRESHOLD
            if (d in rebal_dates) or triggered:
                h = pd.Series(target, index=cols)
                n_rebal += 1

    return nv, n_rebal, n_trend_trig, n_dd_trig
