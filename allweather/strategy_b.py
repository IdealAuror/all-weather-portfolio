"""方案 B：分层风险平价（月度再平衡），不做择时。"""
import pandas as pd
from .config import (
    RISK_FREE_RATE, RISK_PARITY_WINDOW, RISK_PARITY_WINDOW_LONG,
    RISK_PARITY_MAX_WEIGHT, RISK_PARITY_MIN_WEIGHT, BUCKET_GROUPS,
)
from .risk import hierarchical_rp_weights

def _compute_weights(rets_rp, rp_buckets, window):
    """Compute full weight vector from hierarchical RP."""
    rp_w = hierarchical_rp_weights(
        rets_rp, rp_buckets, window,
        RISK_PARITY_MAX_WEIGHT, RISK_PARITY_MIN_WEIGHT,
    )
    return rp_w


def backtest_b(
    rets: pd.DataFrame,
    cash_ratio: float = 0.0,
    rp_window: int = RISK_PARITY_WINDOW,
) -> tuple:
    """Plan B backtest — 纯分层风险平价，无波动率降仓/相关断路器/择时。

    Returns:
        nv (pd.Series), n_rebal (int)
    """
    cols = list(rets.columns)
    rets_rp = rets[cols]
    rp_buckets = {k: list(v) for k, v in BUCKET_GROUPS.items()}

    nv = pd.Series(index=rets.index, dtype=float)
    n_rebal = 0

    initial_w = _compute_weights(
        rets_rp.iloc[:rp_window], rp_buckets, rp_window)
    target = initial_w.values * (1 - cash_ratio)
    h = pd.Series(target, index=cols)
    v = 1.0

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

        # Monthly rebalance
        if d.month != rets.index[i - 1].month and i > rp_window:
            window = rets_rp.iloc[max(0, i - rp_window):i]
            new_w = _compute_weights(window, rp_buckets, rp_window)
            target = new_w.values * (1 - cash_ratio)
            h = pd.Series(target, index=cols)
            n_rebal += 1

    return nv, n_rebal
