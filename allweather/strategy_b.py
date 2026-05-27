"""方案 B：分层风险平价 / 逆波动率（月度再平衡），可选 nonferr 风控增强。"""
import numpy as np
import pandas as pd
from .config import (
    RISK_FREE_RATE, RISK_PARITY_WINDOW,
    RISK_PARITY_MAX_WEIGHT, RISK_PARITY_MIN_WEIGHT, BUCKET_GROUPS,
    GOLD_DIP_THRESHOLD, GOLD_DIP_BOOST,
    HS300_DIP_THRESHOLD, HS300_DIP_BOOST,
)
from .risk import hierarchical_rp_weights, inverse_vol_weights


def _compute_weights(rets_rp, rp_buckets, window,
                     bucket_method="equal",
                     max_w=RISK_PARITY_MAX_WEIGHT,
                     min_w=RISK_PARITY_MIN_WEIGHT,
                     weighting_method="hierarchical_rp"):
    """Compute full weight vector."""
    if weighting_method == "inverse_vol":
        return inverse_vol_weights(rets_rp, window=window, max_w=max_w, min_w=min_w)
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
    weighting_method: str = "hierarchical_rp",
    gold_dip_threshold: float | None = GOLD_DIP_THRESHOLD,
    gold_dip_boost: float = GOLD_DIP_BOOST,
    hs300_dip_threshold: float | None = HS300_DIP_THRESHOLD,
    hs300_dip_boost: float = HS300_DIP_BOOST,
) -> tuple:
    """Plan B backtest — 分层风险平价 / 逆波动率 + 可选 nonferr 风控 + gold 抄底 + hs300 抄底。

    Args:
        weighting_method: "hierarchical_rp" (default) or "inverse_vol"
        nonferr_control: None, "dd_stop" (回撤刹车), or "trend_filter" (趋势过滤)
        nonferr_dd_threshold: dd_stop 模式的回撤触发阈值
        nonferr_trend_window: trend_filter 模式的 SMA 窗口（交易日）
        gold_dip_threshold: 黄金回撤阈值（None=禁用抄底）
        gold_dip_boost: 触发后黄金权重增幅倍数（1.5=增加50%）
        hs300_dip_threshold: 沪深300回撤阈值（None=禁用，默认35%仅史诗级股灾触发）
        hs300_dip_boost: 触发后沪深300权重增幅倍数

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
        bucket_method=bucket_method, max_w=max_w, min_w=min_w,
        weighting_method=weighting_method)
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

    # --- Gold dip-buying state ---
    gold_peak = 1.0
    if gold_dip_threshold is not None and "gold" in cols:
        if prices is None:
            prices = (1 + rets_rp).cumprod()
        gold_peak = prices.iloc[0]["gold"]

    # --- hs300 dip-buying state ---
    hs300_peak = 1.0
    if hs300_dip_threshold is not None and "hs300" in cols:
        if prices is None:
            prices = (1 + rets_rp).cumprod()
        hs300_peak = prices.iloc[0]["hs300"]

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

        # --- Update gold peak ---
        if gold_dip_threshold is not None and prices is not None:
            curr_au = prices.iloc[i]["gold"]
            if curr_au > gold_peak:
                gold_peak = curr_au

        # --- Update hs300 peak ---
        if hs300_dip_threshold is not None and prices is not None:
            curr_hs = prices.iloc[i]["hs300"]
            if curr_hs > hs300_peak:
                hs300_peak = curr_hs

        # Monthly rebalance
        if d.month != rets.index[i - 1].month and i > rp_window:
            window = rets_rp.iloc[max(0, i - rp_window):i]
            new_w = _compute_weights(window, rp_buckets, rp_window,
                                     bucket_method=bucket_method,
                                     max_w=max_w, min_w=min_w,
                                     weighting_method=weighting_method)
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

            # --- Gold dip-buying: 回撤超阈值 → 翻倍增持，从 credit 提取 ---
            if gold_dip_threshold is not None and prices is not None and w.get("gold", 0) > 0:
                gold_dd = prices.iloc[i]["gold"] / gold_peak - 1
                if gold_dd <= -gold_dip_threshold:
                    boost = w["gold"] * gold_dip_boost
                    if w.get("credit", 0) >= boost:
                        w["gold"] += boost
                        w["credit"] = w["credit"] - boost

            # --- hs300 dip-buying: 史诗级股灾(35%)才触发，从 credit 提取 ---
            if hs300_dip_threshold is not None and prices is not None and w.get("hs300", 0) > 0:
                hs300_dd = prices.iloc[i]["hs300"] / hs300_peak - 1
                if hs300_dd <= -hs300_dip_threshold:
                    boost = w["hs300"] * hs300_dip_boost
                    if w.get("credit", 0) >= boost:
                        w["hs300"] += boost
                        w["credit"] = w["credit"] - boost

            h = w
            n_rebal += 1

    return nv, n_rebal
