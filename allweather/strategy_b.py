"""方案 B：分层风险平价（月度再平衡），可选 nonferr 风控增强。"""
import numpy as np
import pandas as pd
from .config import (
    RISK_FREE_RATE, RISK_PARITY_WINDOW, RISK_PARITY_WINDOW_LONG,
    RISK_PARITY_MAX_WEIGHT, RISK_PARITY_MIN_WEIGHT, BUCKET_GROUPS,
)
from .risk import hierarchical_rp_weights

def _compute_weights(rets_rp, rp_buckets, window,
                     bucket_method="equal",
                     max_w=RISK_PARITY_MAX_WEIGHT,
                     min_w=RISK_PARITY_MIN_WEIGHT):
    """Compute full weight vector from hierarchical RP."""
    rp_w = hierarchical_rp_weights(
        rets_rp, rp_buckets, window,
        max_w, min_w,
        bucket_method=bucket_method,
    )
    return rp_w


def backtest_b(
    rets: pd.DataFrame,
    cash_ratio: float = 0.0,
    rp_window: int = RISK_PARITY_WINDOW,
    bucket_method: str = "equal",
    max_w: float = RISK_PARITY_MAX_WEIGHT,
    min_w: float = RISK_PARITY_MIN_WEIGHT,
    nonferr_control: str | None = None,
    nonferr_dd_threshold: float = -0.10,
    nonferr_trend_window: int = 90,
) -> tuple:
    """Plan B backtest — 分层风险平价 + 可选 nonferr 风控。

    Args:
        nonferr_control: None, "dd_stop" (回撤刹车), or "trend_filter" (趋势过滤)
        nonferr_dd_threshold: dd_stop 模式的回撤触发阈值
        nonferr_trend_window: trend_filter 模式的 SMA 窗口（交易日）

    Returns:
        nv (pd.Series), n_rebal (int)
    """
    cols = list(rets.columns)
    rets_rp = rets[cols]
    rp_buckets = {k: list(v) for k, v in BUCKET_GROUPS.items()}

    nv = pd.Series(index=rets.index, dtype=float)
    n_rebal = 0

    initial_w = _compute_weights(
        rets_rp.iloc[:rp_window], rp_buckets, rp_window,
        bucket_method=bucket_method, max_w=max_w, min_w=min_w)
    target = initial_w.values * (1 - cash_ratio)
    h = pd.Series(target, index=cols)
    v = 1.0

    # --- Nonferr risk control state ---
    prices = None
    nferr_peak = 1.0
    nferr_stopped = False
    if nonferr_control is not None and "nonferr" in cols:
        prices = (1 + rets_rp).cumprod()
        nferr_peak = prices.iloc[0]["nonferr"]

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

        # --- Update nonferr peak ---
        if prices is not None:
            curr_nf = prices.iloc[i]["nonferr"]
            if curr_nf > nferr_peak:
                nferr_peak = curr_nf
                nferr_stopped = False

        # Monthly rebalance
        if d.month != rets.index[i - 1].month and i > rp_window:
            window = rets_rp.iloc[max(0, i - rp_window):i]
            new_w = _compute_weights(window, rp_buckets, rp_window,
                                     bucket_method=bucket_method,
                                     max_w=max_w, min_w=min_w)
            w = pd.Series(new_w.values * (1 - cash_ratio), index=cols)

            # --- Apply nonferr risk control ---
            if nonferr_control == "dd_stop" and prices is not None:
                nf_dd = (prices.iloc[i]["nonferr"] / nferr_peak) - 1
                if nf_dd <= nonferr_dd_threshold:
                    nferr_stopped = True
                if nferr_stopped and w.get("nonferr", 0) > 0:
                    w["credit"] = w.get("credit", 0) + w["nonferr"]
                    w["nonferr"] = 0.0

            elif nonferr_control == "trend_filter" and prices is not None:
                curr_nf = prices.iloc[i]["nonferr"]
                nf_sma = prices["nonferr"].iloc[max(0, i - nonferr_trend_window):i].mean()
                if curr_nf < nf_sma and w.get("nonferr", 0) > 0:
                    w["credit"] = w.get("credit", 0) + w["nonferr"]
                    w["nonferr"] = 0.0

            h = w
            n_rebal += 1

    return nv, n_rebal
