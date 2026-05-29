"""回测引擎 - 双触发再平衡 + 现金降杠杆 + nonferr 趋势过滤 + gold/hs300 抄底。"""
import pandas as pd
import numpy as np
from .config import (
    REBAL_FREQ, REBAL_THRESHOLD, RISK_FREE_RATE,
    GOLD_DIP_THRESHOLD, GOLD_DIP_BOOST,
    HS300_DIP_THRESHOLD, HS300_DIP_BOOST,
    HS300_DIP_SMA, HS300_DIP_EXIT_RECOVERY,
    HS300_PB_ENTRY, HS300_PE_EXIT,
)



def backtest_iv(
    rets: pd.DataFrame,
    cash_ratio: float = 0.0,
    rebal_freq: str = REBAL_FREQ,
    rebal_threshold: float = REBAL_THRESHOLD,
    rf_daily: float = RISK_FREE_RATE,
    iv_window: int = 60,
    max_w: float = 0.25,
    min_w: float = 0.03,
    nonferr_trend_window: int = 75,
    gold_dip_threshold: float | None = GOLD_DIP_THRESHOLD,
    gold_dip_boost: float = GOLD_DIP_BOOST,
    gold_dip_cap: float | None = None,
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
    hs300_pb_entry: float = HS300_PB_ENTRY,
    hs300_pe_exit: float = HS300_PE_EXIT,
    track_signals: bool = False,
    signal_label: str = "",
    dynamic_cash: bool = False,
):
    """逆波动率加权 + 月度再平衡 + nonferr 趋势过滤 + gold/hs300 抄底。

    每月按过去 iv_window 日逆波动率重新计算权重，简单直接，无需分桶。
    assets 为空则用全部列。
    track_weights=True 时额外返回权重历史 DataFrame（调仓日 × 资产）。
    """
    from .risk import inverse_vol_weights, hs300_dip_check, hs300_signal_snapshot
    from .data import load_hs300_pb, load_hs300_pe

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

    pb_data = load_hs300_pb() if hs300_value_dip else None
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
            eff_cr = cash_ratio
            if dynamic_cash and hs300_idx >= 0:
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
                        if gold_dip_cap is not None and w["gold"] > gold_dip_cap:
                            excess = w["gold"] - gold_dip_cap
                            w["gold"] = gold_dip_cap
                            w["credit"] += excess

            # --- hs300 抄底：价格回撤 + 基本面确认 同时满足 ---
            if hs300_value_dip and hs300_idx >= 0 and w.get("hs300", 0) > 0 and i > hs300_dip_sma:
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

            # --- 信号触发日志 ---
            if track_signals and hs300_idx >= 0:
                snap = hs300_signal_snapshot(pb_data, pe_data, prices, d, i, hs300_peak, hs300_boosted, hs300_dip_boost)
                signal_log.append({
                    'date': d,
                    'label': signal_label,
                    **snap,
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


