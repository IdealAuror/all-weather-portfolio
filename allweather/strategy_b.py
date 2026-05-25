"""方案 B：分层风险平价 + 动态配置 + 三级防护。"""
import pandas as pd
from .config import (
    RISK_FREE_RATE, RISK_PARITY_WINDOW, RISK_PARITY_MAX_WEIGHT,
    RISK_PARITY_MIN_WEIGHT, CORR_BREAKER_THRESHOLD, CORR_BREAKER_RECOVER,
    CORR_BREAKER_CAP, VOL_TARGET, BUCKET_GROUPS,
)
from .risk import (
    hierarchical_rp_weights, correlation_breaker, vol_target_scale,
)

SHORT_BOND_FIXED = 0.05  # short_bond 固定 5%，不参与风险预算


def _compute_weights(rets_rp, rp_buckets, has_short_bond, rets_cols):
    """Compute full weight vector: RP weights for risk assets + fixed short_bond."""
    rp_w = hierarchical_rp_weights(
        rets_rp, rp_buckets,
        RISK_PARITY_WINDOW, RISK_PARITY_MAX_WEIGHT, RISK_PARITY_MIN_WEIGHT,
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
    horizon: str = "long",
) -> tuple:
    """Plan B backtest.

    Mechanisms:
    1. Monthly hierarchical risk parity (equal bucket weight, inv vol within)
    2. Correlation breaker: avg pairwise corr > 0.3 -> cap at 70%
    3. Vol targeting: annualized target 6%
    4. Investment horizon tiers control max risk asset exposure

    Returns:
        nv (pd.Series), n_rebal (int), n_corr_break (int)
    """
    horizon_caps = {"short": 0.40, "mid": 0.70, "long": 1.00}
    risk_cap = horizon_caps.get(horizon, 1.00)

    cols = list(rets.columns)
    has_short = "short_bond" in cols

    # RP universe excludes short_bond (cash equivalent)
    rp_cols = [c for c in cols if c != "short_bond"]
    rets_rp = rets[rp_cols]
    rp_buckets = {
        k: [a for a in v if a != "short_bond"]
        for k, v in BUCKET_GROUPS.items()
    }
    rp_buckets = {k: v for k, v in rp_buckets.items() if v}

    nv = pd.Series(index=rets.index, dtype=float)
    n_rebal = 0
    n_corr_break = 0
    in_corr_break = False

    # Initial weights
    initial_w = _compute_weights(
        rets_rp.iloc[:RISK_PARITY_WINDOW], rp_buckets, has_short, cols)
    target = initial_w.values * (1 - cash_ratio)
    h = pd.Series(target, index=cols)
    v = 1.0

    for i, d in enumerate(rets.index):
        if i == 0:
            nv.loc[d] = 1.0
            continue

        # Vol targeting on portfolio-level returns
        if i > RISK_PARITY_WINDOW:
            w = h / h.sum()
            port_rets = (rets.iloc[i - RISK_PARITY_WINDOW:i] * w.values).sum(axis=1)
            scale = vol_target_scale(port_rets, VOL_TARGET, RISK_PARITY_WINDOW)
        else:
            scale = 1.0

        effective_h = h * scale * risk_cap
        v *= 1 + (effective_h * rets.loc[d, cols]).sum() + cash_ratio * RISK_FREE_RATE
        nv.loc[d] = v

        h = h * (1 + rets.loc[d, cols])
        s = h.sum()
        if s > 0:
            h = h / s * (1 - cash_ratio)

        # Monthly rebalance
        if d.month != rets.index[i - 1].month and i > RISK_PARITY_WINDOW:
            window = rets_rp.iloc[max(0, i - RISK_PARITY_WINDOW):i]
            if in_corr_break:
                if not correlation_breaker(window, CORR_BREAKER_RECOVER,
                                          RISK_PARITY_WINDOW):
                    in_corr_break = False
            else:
                if correlation_breaker(window, CORR_BREAKER_THRESHOLD,
                                      RISK_PARITY_WINDOW):
                    in_corr_break = True
                    n_corr_break += 1

            new_w = _compute_weights(window, rp_buckets, has_short, cols)

            if in_corr_break:
                new_w = new_w * CORR_BREAKER_CAP

            target = new_w.values * (1 - cash_ratio)
            h = pd.Series(target, index=cols)
            n_rebal += 1

    return nv, n_rebal, n_corr_break
