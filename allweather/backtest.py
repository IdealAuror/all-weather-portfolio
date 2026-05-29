"""回测引擎 - 双触发再平衡 + 现金降杠杆 + nonferr 趋势过滤 + gold/hs300 抄底。"""
import pandas as pd
import numpy as np
from .config import (
    REBAL_FREQ, REBAL_THRESHOLD, RISK_FREE_RATE,
    GOLD_DIP_THRESHOLD, GOLD_DIP_BOOST,
    HS300_DIP_THRESHOLD, HS300_DIP_BOOST,
    HS300_DIP_SMA, HS300_DIP_EXIT_RECOVERY,
    HS300_PE_ENTRY, HS300_PE_EXIT,
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
    hs300_dip_sma: int = HS300_DIP_SMA,
    hs300_dip_exit_recovery: float = HS300_DIP_EXIT_RECOVERY,
    assets: list | None = None,
    gold_trend_filter: bool = False,
    gold_trend_window: int = 75,
    track_weights: bool = False,
    vol_target: float | None = None,
    vol_target_window: int = 60,
    hs300_value_dip: bool = False,
    hs300_pe_entry: float = HS300_PE_ENTRY,
    hs300_pe_exit: float = HS300_PE_EXIT,
    track_signals: bool = False,
    signal_label: str = "",
):
    """逆波动率加权 + 月度再平衡 + nonferr 趋势过滤 + gold/hs300 抄底。

    每月按过去 iv_window 日逆波动率重新计算权重，简单直接，无需分桶。
    assets 为空则用全部列。
    track_weights=True 时额外返回权重历史 DataFrame（调仓日 × 资产）。
    """
    from .risk import inverse_vol_weights
    from .data import load_hs300_pe

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

    pe_data = load_hs300_pe() if hs300_value_dip else None
    hs300_boosted = False

    w = inverse_vol_weights(rets.iloc[:max(iv_window, len(rets))], window=iv_window, max_w=max_w, min_w=min_w)
    target = w.values * (1 - cash_ratio)
    h = pd.Series(target, index=cols)
    v = 1.0
    eff_cash = cash_ratio
    weight_log = {} if track_weights else None
    signal_log = [] if track_signals else None

    for i, d in enumerate(rets.index):
        if i == 0:
            nv.loc[d] = 1.0
            continue

        v *= 1 + (h * rets.loc[d, cols]).sum() + eff_cash * rf_daily
        nv.loc[d] = v

        h = h * (1 + rets.loc[d, cols])
        s = h.sum()
        if s > 0:
            h = h / s * (1 - eff_cash)

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

            # --- hs300 抄底：价格回撤 AND PE 低估 同时满足 ---
            if hs300_value_dip and pe_data is not None and hs300_idx >= 0 and w.get("hs300", 0) > 0 and i > hs300_dip_sma:
                pe_to_date = pe_data[pe_data.index <= d]
                if len(pe_to_date) >= 252:
                    pe_pct = (pe_to_date < pe_to_date.iloc[-1]).sum() / len(pe_to_date) * 100
                    hs300_dd = prices.iloc[i]["hs300"] / hs300_peak - 1
                    curr_hs = prices.iloc[i]["hs300"]
                    dip_sma = prices["hs300"].iloc[max(0, i - hs300_dip_sma):i].mean()
                    if hs300_boosted:
                        if hs300_dd > -hs300_dip_exit_recovery and pe_pct > hs300_pe_exit:
                            hs300_boosted = False
                    elif (hs300_dd <= -hs300_dip_threshold and pe_pct < hs300_pe_entry
                          and curr_hs > dip_sma):
                        hs300_boosted = True
                    if hs300_boosted:
                        boost = w["hs300"] * (hs300_dip_boost - 1)
                        if w.get("credit", 0) >= boost:
                            w["hs300"] += boost
                            w["credit"] -= boost

            # --- 信号触发日志 ---
            if track_signals:
                sig_dd, sig_pe_pct, sig_pe_val, sig_boost = None, None, None, None

                if hs300_dip_threshold is not None and hs300_idx >= 0:
                    sig_dd = round(float(prices.iloc[i]["hs300"] / hs300_peak - 1), 4)

                if pe_data is not None and hs300_idx >= 0:
                    pe_to = pe_data[pe_data.index <= d]
                    if len(pe_to) >= 252:
                        sig_pe_val = float(pe_to.iloc[-1])
                        sig_pe_pct = round((pe_to < sig_pe_val).sum() / len(pe_to) * 100, 1)

                if hs300_boosted:
                    sig_boost = hs300_dip_boost

                signal_log.append({
                    'date': d,
                    'label': signal_label,
                    'active': hs300_boosted,
                    'dd_pct': sig_dd,
                    'pe_pctile': sig_pe_pct,
                    'pe_value': sig_pe_val,
                    'boost': sig_boost,
                })

            if vol_target is not None and i > max(iv_window, vol_target_window):
                past = rets.iloc[max(0, i - vol_target_window):i][cols]
                port_ret = past @ w.values
                port_vol = port_ret.std() * np.sqrt(252)
                if port_vol > 0.001 and port_vol > vol_target:
                    w = w * (vol_target / port_vol)
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
