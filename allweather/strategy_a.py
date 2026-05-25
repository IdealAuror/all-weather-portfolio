"""方案 A：固定权重（含 short_bond）+ 阈值再平衡。"""
import pandas as pd
from .config import REBAL_THRESHOLD, RISK_FREE_RATE


def backtest_a(weights: pd.Series, rets: pd.DataFrame,
               cash_ratio: float = 0.0) -> tuple:
    """Plan A backtest — 纯固定权重，无择时层。

    Returns:
        nv (pd.Series), n_rebal (int)
    """
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

        triggered = abs(h.values - target).max() > REBAL_THRESHOLD
        if triggered:
            h = pd.Series(target, index=cols)
            n_rebal += 1

    return nv, n_rebal
