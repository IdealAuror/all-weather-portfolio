"""方案 B：分层风险平价（月度再平衡），不做择时。"""
import pandas as pd
from .config import (
    RISK_FREE_RATE, RISK_PARITY_WINDOW, RISK_PARITY_WINDOW_LONG,
    RISK_PARITY_MAX_WEIGHT, RISK_PARITY_MIN_WEIGHT, BUCKET_GROUPS,
)
from .risk import hierarchical_rp_weights

SHORT_BOND_FIXED = 0.05  # short_bond 固定 5%，不参与风险预算


def _compute_weights(rets_rp, rp_buckets, has_short_bond, rets_cols, window):
    """Compute full weight vector: RP weights for risk assets + fixed short_bond."""
    rp_w = hierarchical_rp_weights(
        rets_rp, rp_buckets, window,
        RISK_PARITY_MAX_WEIGHT, RISK_PARITY_MIN_WEIGHT,
    )
    full = pd.Series(0.0, index=rets_cols)
    for a in rp_w.index:
        full[a] = rp_w[a] * (1 - SHORT_BOND_FIXED) if has_short_bond else rp_w[a]
    if has_short_bond and "short_bond" in rets_cols:
        full["short_bond"] = SHORT_BOND_FIXED
    return full


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
    has_short = "short_bond" in cols

    rp_cols = [c for c in cols if c != "short_bond"]
    rets_rp = rets[rp_cols]
    rp_buckets = {
        k: [a for a in v if a != "short_bond"]
        for k, v in BUCKET_GROUPS.items()
    }
    rp_buckets = {k: v for k, v in rp_buckets.items() if v}

    nv = pd.Series(index=rets.index, dtype=float)
    n_rebal = 0

    initial_w = _compute_weights(
        rets_rp.iloc[:rp_window], rp_buckets, has_short, cols, rp_window)
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
            new_w = _compute_weights(window, rp_buckets, has_short, cols, rp_window)
            target = new_w.values * (1 - cash_ratio)
            h = pd.Series(target, index=cols)
            n_rebal += 1

    return nv, n_rebal
