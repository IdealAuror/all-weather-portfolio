"""方案 B：分层风险平价 / 逆波动率（月度再平衡），可选 nonferr 风控增强。"""
import numpy as np
import pandas as pd
from .config import (
    RISK_FREE_RATE, RISK_PARITY_WINDOW,
    RISK_PARITY_MAX_WEIGHT, RISK_PARITY_MIN_WEIGHT, BUCKET_GROUPS,
    GOLD_DIP_THRESHOLD, GOLD_DIP_BOOST,
    HS300_DIP_THRESHOLD, HS300_DIP_BOOST,
    HS300_DIP_SMA, HS300_DIP_EXIT_RECOVERY,
    HS300_PB_ENTRY, HS300_PE_EXIT,
)
from .risk import hierarchical_rp_weights, inverse_vol_weights, hs300_dip_check, hs300_signal_snapshot
from .data import load_hs300_pb, load_hs300_pe


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
    rp_buckets: dict | None = None,
    nonferr_control: str | None = None,
    nonferr_trend_window: int = 90,
    weighting_method: str = "hierarchical_rp",
    gold_dip_threshold: float | None = GOLD_DIP_THRESHOLD,
    gold_dip_boost: float = GOLD_DIP_BOOST,
    gold_dip_cap: float | None = None,
    hs300_dip_threshold: float | None = HS300_DIP_THRESHOLD,
    hs300_dip_boost: float = HS300_DIP_BOOST,
    hs300_dip_sma: int = HS300_DIP_SMA,
    hs300_dip_exit_recovery: float = HS300_DIP_EXIT_RECOVERY,
    gold_trend_filter: bool = False,
    gold_trend_window: int = 75,
    track_weights: bool = False,
    equity_trend_assets: list | None = None,
    equity_trend_window: int = 120,
    hs300_value_dip: bool = False,
    hs300_pb_entry: float = HS300_PB_ENTRY,
    hs300_pe_exit: float = HS300_PE_EXIT,
    track_signals: bool = False,
    signal_label: str = "",
    dynamic_cash: bool = False,
) -> tuple:
    """Plan B backtest — 分层风险平价 / 逆波动率 + 可选 nonferr 风控 + gold 抄底 + hs300 抄底。

    Args:
        weighting_method: "hierarchical_rp" (default) or "inverse_vol"
        rp_buckets: 自定义桶结构（None=默认 BUCKET_GROUPS）
        nonferr_control: None or "trend_filter" (趋势过滤)
        nonferr_trend_window: trend_filter 模式的 SMA 窗口（交易日）
        gold_dip_threshold: 黄金回撤阈值（None=禁用抄底）
        gold_dip_boost: 触发后黄金权重增幅倍数（1.5=增加50%）
        hs300_dip_threshold: 沪深300回撤阈值（None=禁用，默认35%仅史诗级股灾触发）
        gold_trend_filter: 黄金SMA趋势过滤，跌破SMA则清仓转入credit（默认False）
        gold_trend_window: 黄金SMA回看窗口（交易日，默认75）
        track_weights: 为True时额外返回权重历史DataFrame（调仓日 × 资产）

    Returns:
        nv (pd.Series), n_rebal (int), [weight_history (pd.DataFrame)]
    """
    cols = list(rets.columns)
    rets_rp = rets[cols]
    rp_buckets = {k: list(v) for k, v in (rp_buckets or BUCKET_GROUPS).items()}

    nv = pd.Series(index=rets.index, dtype=float)
    n_rebal = 0

    initial_w = _compute_weights(
        rets_rp.iloc[:rp_window], rp_buckets, rp_window,
        bucket_method=bucket_method, max_w=max_w, min_w=min_w,
        weighting_method=weighting_method)
    target = initial_w.values * (1 - cash_ratio)
    h = pd.Series(target, index=cols)
    v = 1.0
    eff_cash = cash_ratio
    weight_log = {} if track_weights else None
    signal_log = [] if track_signals else None

    # --- Nonferr risk control state ---
    prices = None
    if nonferr_control is not None and "nonferr" in cols:
        prices = (1 + rets_rp).cumprod()

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

    pb_data = load_hs300_pb() if hs300_value_dip else None
    pe_data = load_hs300_pe() if hs300_value_dip else None
    hs300_boosted = False

    for i, d in enumerate(rets.index):
        if i == 0:
            nv.loc[d] = 1.0
            continue

        v *= 1 + (h * rets.loc[d, cols]).sum() + eff_cash * RISK_FREE_RATE
        nv.loc[d] = v

        h = h * (1 + rets.loc[d, cols])
        s = h.sum()
        if s > 0:
            h = h / s * (1 - eff_cash)

        # --- Update gold peak ---
        if gold_dip_threshold is not None and prices is not None and "gold" in prices.columns:
            curr_au = prices.iloc[i]["gold"]
            if curr_au > gold_peak:
                gold_peak = curr_au

        # --- Update hs300 peak ---
        if hs300_dip_threshold is not None and prices is not None and "hs300" in prices.columns:
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
            eff_cr = cash_ratio
            if dynamic_cash and prices is not None and "hs300" in prices.columns:
                hs3 = prices["hs300"]
                peak_3y = hs3.iloc[max(0, i-756):i+1].max()
                dd_3y = hs3.iloc[i] / peak_3y - 1
                if dd_3y <= -0.20:
                    eff_cr = 0.0
                elif dd_3y >= -0.05:
                    eff_cr = 0.30
                else:
                    eff_cr = 0.15
            w = pd.Series(new_w.values * (1 - eff_cr), index=cols)

            # --- Apply nonferr risk control ---
            if nonferr_control == "trend_filter" and prices is not None:
                curr_nf = prices.iloc[i]["nonferr"]
                nf_sma = prices["nonferr"].iloc[max(0, i - nonferr_trend_window):i].mean()
                if curr_nf < nf_sma and w.get("nonferr", 0) > 0:
                    w["credit"] = w.get("credit", 0) + w["nonferr"]
                    w["nonferr"] = 0.0

            # --- Gold trend filter: 金价跌破SMA → 清仓转入 credit ---
            if gold_trend_filter and prices is not None and w.get("gold", 0) > 0:
                curr_au = prices.iloc[i]["gold"]
                au_sma = prices["gold"].iloc[max(0, i - gold_trend_window):i].mean()
                if curr_au < au_sma:
                    w["credit"] = w.get("credit", 0) + w["gold"]
                    w["gold"] = 0.0

            # --- Equity trend filter: 权益跌破SMA → 清仓转入 credit ---
            if equity_trend_assets and prices is not None and i > equity_trend_window:
                for eq in equity_trend_assets:
                    if eq in w.index and w.get(eq, 0) > 0:
                        curr = prices.iloc[i][eq]
                        sma = prices[eq].iloc[max(0, i - equity_trend_window):i].mean()
                        if curr < sma:
                            w["credit"] = w.get("credit", 0) + w[eq]
                            w[eq] = 0.0

            # --- Gold dip-buying: 回撤超阈值 → 翻倍增持，从 credit 提取 ---
            if gold_dip_threshold is not None and prices is not None and w.get("gold", 0) > 0:
                gold_dd = prices.iloc[i]["gold"] / gold_peak - 1
                if gold_dd <= -gold_dip_threshold:
                    boost = w["gold"] * gold_dip_boost
                    if w.get("credit", 0) >= boost:
                        w["gold"] += boost
                        w["credit"] = w["credit"] - boost
                        if gold_dip_cap is not None and w["gold"] > gold_dip_cap:
                            excess = w["gold"] - gold_dip_cap
                            w["gold"] = gold_dip_cap
                            w["credit"] = w["credit"] + excess

            # --- hs300 抄底：价格回撤 + 基本面确认 同时满足 ---
            if hs300_value_dip and w.get("hs300", 0) > 0 and i > hs300_dip_sma:
                hs300_boosted, hs300_boost = hs300_dip_check(
                    pb_data, pe_data, prices, d, i, hs300_peak, hs300_boosted,
                    hs300_dip_threshold, hs300_dip_sma, hs300_dip_exit_recovery,
                    hs300_pb_entry, hs300_pe_exit, hs300_dip_boost,
                )
                if hs300_boost is not None:
                    boost = w["hs300"] * (hs300_boost - 1)
                    if w.get("credit", 0) >= boost:
                        w["hs300"] += boost
                        w["credit"] -= boost

            # --- 信号触发日志（每月调仓日记录全部风控状态）---
            if track_signals:
                entry = {'date': d, 'label': signal_label}
                # Nonferr 趋势过滤
                if nonferr_control == "trend_filter" and prices is not None and "nonferr" in prices.columns:
                    nf_sma = prices["nonferr"].iloc[max(0, i - nonferr_trend_window):i].mean()
                    entry['nonferr_below_sma'] = bool(prices.iloc[i]["nonferr"] < nf_sma)
                    entry['nonferr_filtered'] = w.get("nonferr", 0) == 0
                # Gold 趋势过滤
                if gold_trend_filter and prices is not None and "gold" in prices.columns:
                    au_sma = prices["gold"].iloc[max(0, i - gold_trend_window):i].mean()
                    entry['gold_below_sma'] = bool(prices.iloc[i]["gold"] < au_sma)
                    entry['gold_filtered'] = w.get("gold", 0) == 0
                # SP500 趋势过滤
                if equity_trend_assets and prices is not None and i > equity_trend_window:
                    for eq in equity_trend_assets:
                        if eq in prices.columns:
                            eq_sma = prices[eq].iloc[max(0, i - equity_trend_window):i].mean()
                            entry[f'{eq}_below_sma'] = bool(prices.iloc[i][eq] < eq_sma)
                            entry[f'{eq}_filtered'] = w.get(eq, 0) == 0
                # Gold 抄底
                if gold_dip_threshold is not None and prices is not None and "gold" in prices.columns:
                    gold_dd = float(prices.iloc[i]["gold"] / gold_peak - 1)
                    entry['gold_dd_pct'] = round(gold_dd, 4)
                    entry['gold_dip_active'] = gold_dd <= -gold_dip_threshold and w.get("gold", 0) > 0
                # HS300 AND 抄底
                if "hs300" in cols:
                    snap = hs300_signal_snapshot(pb_data, pe_data, prices, d, i, hs300_peak, hs300_boosted, hs300_dip_boost)
                    entry.update(snap)
                signal_log.append(entry)

            eff_cash = 1.0 - w.sum()

            h = w
            n_rebal += 1
            if track_weights:
                weight_log[d] = w.copy()

    if track_weights and track_signals:
        return nv, n_rebal, pd.DataFrame(weight_log).T, pd.DataFrame(signal_log)
    if track_weights:
        return nv, n_rebal, pd.DataFrame(weight_log).T
    if track_signals:
        return nv, n_rebal, pd.DataFrame(signal_log)
    return nv, n_rebal
