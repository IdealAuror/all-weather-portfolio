"""回测引擎 - 双触发再平衡 + 现金降杠杆。"""
import pandas as pd
import numpy as np
from .config import REBAL_FREQ, REBAL_THRESHOLD, RISK_FREE_RATE


def backtest(
    weights: pd.Series,
    rets: pd.DataFrame,
    cash_ratio: float = 0.0,
    rebal_freq: str = REBAL_FREQ,
    rebal_threshold: float = REBAL_THRESHOLD,
    rf_daily: float = RISK_FREE_RATE,
):
    """跑一个组合的净值序列。

    再平衡规则：日历节点 + 阈值偏离双触发，任一满足即调仓。

    返回：
        nv (pd.Series): 净值序列（起点 1.0）
        n_rebal (int): 实际触发的调仓次数
    """
    cols = list(weights.index)
    target = weights.values * (1 - cash_ratio)
    nv = pd.Series(index=rets.index, dtype=float)
    h = pd.Series(target, index=cols)
    v = 1.0
    n_rebal = 0

    rebal_dates = set(rets.resample(rebal_freq).last().index)

    for i, d in enumerate(rets.index):
        if i == 0:
            nv.loc[d] = 1.0
            continue
        # 当日收益 = 各持仓收益 + 现金部分无风险收益
        v *= 1 + (h * rets.loc[d, cols]).sum() + cash_ratio * rf_daily
        nv.loc[d] = v
        # 持仓权重漂移
        h = h * (1 + rets.loc[d, cols])
        s = h.sum()
        if s > 0:
            h = h / s * (1 - cash_ratio)
        # 触发再平衡
        triggered = (h.values - target).__abs__().max() > rebal_threshold
        if (d in rebal_dates) or triggered:
            h = pd.Series(target, index=cols)
            n_rebal += 1

    return nv, n_rebal


def backtest_calendar(weights, rets, freq, cash_ratio=0.0):
    """纯日历再平衡（没有阈值），用于规则对比。freq=None 表示永不调仓。"""
    cols = list(weights.index)
    target = weights.values * (1 - cash_ratio)
    nv = pd.Series(index=rets.index, dtype=float)
    h = pd.Series(target, index=cols)
    v = 1.0
    n_rebal = 0
    rebal_dates = set(rets.resample(freq).last().index) if freq else set()
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
        if d in rebal_dates:
            h = pd.Series(target, index=cols)
            n_rebal += 1
    return nv, n_rebal


def backtest_threshold_only(weights, rets, threshold, cash_ratio=0.0):
    """纯阈值再平衡，用于规则对比。"""
    cols = list(weights.index)
    target = weights.values * (1 - cash_ratio)
    nv = pd.Series(index=rets.index, dtype=float)
    h = pd.Series(target, index=cols)
    v = 1.0
    n_rebal = 0
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
        if (h.values - target).__abs__().max() > threshold:
            h = pd.Series(target, index=cols)
            n_rebal += 1
    return nv, n_rebal
