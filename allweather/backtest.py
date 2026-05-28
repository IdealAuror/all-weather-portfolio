"""回测引擎 - 双触发再平衡 + 现金降杠杆 + nonferr 趋势过滤 + gold/hs300 抄底。"""
import pandas as pd
import numpy as np
from .config import (
    REBAL_FREQ, REBAL_THRESHOLD, RISK_FREE_RATE,
    GOLD_DIP_THRESHOLD, GOLD_DIP_BOOST,
    HS300_DIP_THRESHOLD, HS300_DIP_BOOST,
)


def backtest(
    weights: pd.Series,
    rets: pd.DataFrame,
    cash_ratio: float = 0.0,
    rebal_freq: str = REBAL_FREQ,
    rebal_threshold: float = REBAL_THRESHOLD,
    rf_daily: float = RISK_FREE_RATE,
    nonferr_trend_window: int = 0,
    gold_dip_threshold: float | None = GOLD_DIP_THRESHOLD,
    gold_dip_boost: float = GOLD_DIP_BOOST,
    hs300_dip_threshold: float | None = HS300_DIP_THRESHOLD,
    hs300_dip_boost: float = HS300_DIP_BOOST,
):
    """跑一个组合的净值序列。

    再平衡规则：日历节点 + 阈值偏离双触发，任一满足即调仓。
    nonferr_trend_window > 0 时，调仓日检查 nonferr vs SMA，跌破则权重转入 credit。
    gold/hs300 回撤超阈值时从 credit 提取权重抄底。

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
    has_nf = nonferr_trend_window > 0 and "nonferr" in cols
    has_gold = gold_dip_threshold is not None and "gold" in cols
    has_hs300 = hs300_dip_threshold is not None and "hs300" in cols
    prices = (1 + rets).cumprod()
    credit_idx = cols.index("credit") if "credit" in cols else None
    nonferr_idx = cols.index("nonferr") if "nonferr" in cols else None
    gold_idx = cols.index("gold") if "gold" in cols else None
    hs300_idx = cols.index("hs300") if "hs300" in cols else None

    gold_peak = prices.iloc[0]["gold"] if has_gold else 1.0
    hs300_peak = prices.iloc[0]["hs300"] if has_hs300 else 1.0

    for i, d in enumerate(rets.index):
        if i == 0:
            nv.loc[d] = 1.0
            continue
        v *= 1 + (h * rets.loc[d, cols]).sum() + cash_ratio * rf_daily
        nv.loc[d] = v
        h = h * (1 + rets.loc[d, cols])
        s = h.sum()
        if s > 0:
            h = h / s * (1 - cash_ratio)

        if has_gold:
            curr_au = prices.iloc[i]["gold"]
            if curr_au > gold_peak:
                gold_peak = curr_au
        if has_hs300:
            curr_hs = prices.iloc[i]["hs300"]
            if curr_hs > hs300_peak:
                hs300_peak = curr_hs

        triggered = (h.values - target).__abs__().max() > rebal_threshold
        if (d in rebal_dates) or triggered:
            adj_target = target.copy()

            if has_nf and nonferr_idx is not None:
                curr_nf = prices.iloc[i]["nonferr"]
                nf_sma = prices["nonferr"].iloc[max(0, i - nonferr_trend_window):i].mean()
                if curr_nf < nf_sma and adj_target[nonferr_idx] > 0:
                    adj_target[credit_idx] += adj_target[nonferr_idx]
                    adj_target[nonferr_idx] = 0.0

            if has_gold and gold_idx is not None and adj_target[gold_idx] > 0:
                gold_dd = prices.iloc[i]["gold"] / gold_peak - 1
                if gold_dd <= -gold_dip_threshold:
                    boost = adj_target[gold_idx] * gold_dip_boost
                    if adj_target[credit_idx] >= boost:
                        adj_target[gold_idx] += boost
                        adj_target[credit_idx] -= boost

            if has_hs300 and hs300_idx is not None and adj_target[hs300_idx] > 0:
                hs300_dd = prices.iloc[i]["hs300"] / hs300_peak - 1
                if hs300_dd <= -hs300_dip_threshold:
                    boost = adj_target[hs300_idx] * hs300_dip_boost
                    if adj_target[credit_idx] >= boost:
                        adj_target[hs300_idx] += boost
                        adj_target[credit_idx] -= boost

            h = pd.Series(adj_target, index=cols)
            n_rebal += 1

    return nv, n_rebal


def backtest_iv(
    rets: pd.DataFrame,
    cash_ratio: float = 0.0,
    rebal_freq: str = REBAL_FREQ,
    rebal_threshold: float = REBAL_THRESHOLD,
    rf_daily: float = RISK_FREE_RATE,
    iv_window: int = 60,
    max_w: float = 0.25,
    min_w: float = 0.03,
    nonferr_trend_window: int = 60,
    gold_dip_threshold: float | None = GOLD_DIP_THRESHOLD,
    gold_dip_boost: float = GOLD_DIP_BOOST,
    hs300_dip_threshold: float | None = HS300_DIP_THRESHOLD,
    hs300_dip_boost: float = HS300_DIP_BOOST,
    assets: list | None = None,
    gold_trend_filter: bool = False,
    gold_trend_window: int = 75,
):
    """逆波动率加权 + 月度再平衡 + nonferr 趋势过滤 + gold/hs300 抄底。

    每月按过去 iv_window 日逆波动率重新计算权重，简单直接，无需分桶。
    assets 为空则用全部列。
    """
    from .risk import inverse_vol_weights

    if assets is not None:
        rets = rets[assets]
    cols = list(rets.columns)
    nv = pd.Series(index=rets.index, dtype=float)
    n_rebal = 0

    prices = (1 + rets).cumprod()
    credit_idx = cols.index("credit") if "credit" in cols else -1
    nonferr_idx = cols.index("nonferr") if "nonferr" in cols else -1
    gold_idx = cols.index("gold") if "gold" in cols else -1
    hs300_idx = cols.index("hs300") if "hs300" in cols else -1

    gold_peak = prices.iloc[0]["gold"] if gold_idx >= 0 else 1.0
    hs300_peak = prices.iloc[0]["hs300"] if hs300_idx >= 0 else 1.0

    w = inverse_vol_weights(rets.iloc[:max(iv_window, len(rets))], window=iv_window, max_w=max_w, min_w=min_w)
    target = w.values * (1 - cash_ratio)
    h = pd.Series(target, index=cols)
    v = 1.0

    for i, d in enumerate(rets.index):
        if i == 0:
            nv.loc[d] = 1.0
            continue

        v *= 1 + (h * rets.loc[d, cols]).sum() + cash_ratio * rf_daily
        nv.loc[d] = v

        h = h * (1 + rets.loc[d, cols])
        s = h.sum()
        if s > 0:
            h = h / s * (1 - cash_ratio)

        if gold_idx >= 0:
            curr_au = prices.iloc[i]["gold"]
            if curr_au > gold_peak:
                gold_peak = curr_au
        if hs300_idx >= 0:
            curr_hs = prices.iloc[i]["hs300"]
            if curr_hs > hs300_peak:
                hs300_peak = curr_hs

        if d.month != rets.index[i - 1].month and i > iv_window:
            window = rets.iloc[max(0, i - iv_window):i]
            new_w = inverse_vol_weights(window, window=iv_window, max_w=max_w, min_w=min_w)
            w = pd.Series(new_w.values * (1 - cash_ratio), index=cols)

            if nonferr_trend_window > 0 and nonferr_idx >= 0 and w.get("nonferr", 0) > 0:
                curr_nf = prices.iloc[i]["nonferr"]
                nf_sma = prices["nonferr"].iloc[max(0, i - nonferr_trend_window):i].mean()
                if curr_nf < nf_sma:
                    w["credit"] = w.get("credit", 0) + w["nonferr"]
                    w["nonferr"] = 0.0

            if gold_trend_filter and gold_idx >= 0 and w.get("gold", 0) > 0:
                curr_au = prices.iloc[i]["gold"]
                au_sma = prices["gold"].iloc[max(0, i - gold_trend_window):i].mean()
                if curr_au < au_sma:
                    w["credit"] = w.get("credit", 0) + w["gold"]
                    w["gold"] = 0.0

            if gold_dip_threshold is not None and gold_idx >= 0 and w.get("gold", 0) > 0:
                gold_dd = prices.iloc[i]["gold"] / gold_peak - 1
                if gold_dd <= -gold_dip_threshold:
                    boost = w["gold"] * gold_dip_boost
                    if w.get("credit", 0) >= boost:
                        w["gold"] += boost
                        w["credit"] -= boost

            if hs300_dip_threshold is not None and hs300_idx >= 0 and w.get("hs300", 0) > 0:
                hs300_dd = prices.iloc[i]["hs300"] / hs300_peak - 1
                if hs300_dd <= -hs300_dip_threshold:
                    boost = w["hs300"] * hs300_dip_boost
                    if w.get("credit", 0) >= boost:
                        w["hs300"] += boost
                        w["credit"] -= boost

            h = w
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
