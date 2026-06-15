"""回测引擎 - 统一版本（逆波动率/分层风险平价 + 趋势过滤 + 抄底）。"""
from __future__ import annotations

from typing import NamedTuple

import pandas as pd
import numpy as np
from .config import (
    RISK_FREE_RATE, RISK_PARITY_WINDOW, BUCKET_GROUPS,
    GOLD_DIP_THRESHOLD, GOLD_DIP_BOOST,
    HS300_DIP_THRESHOLD, HS300_DIP_BOOST,
    HS300_DIP_SMA, HS300_DIP_EXIT_RECOVERY,
    HS300_PB_ENTRY, HS300_PE_EXIT,
)
from .risk import inverse_vol_weights, erc_weights, hierarchical_rp_weights, hs300_dip_check, hs300_signal_snapshot, dynamic_cash_ratio


class BacktestResult(NamedTuple):
    """backtest() 统一返回类型。nv_dyn 在未跟踪时为 None。"""
    nv: pd.Series
    nv_dyn: pd.Series | None
    n_rebal: int
    weight_df: pd.DataFrame | None
    signal_df: pd.DataFrame | None



def adjust_nav_for_cash(nv_base: pd.Series, cash_ratio: float, rf_daily: float = RISK_FREE_RATE) -> pd.Series:
    """从 0% 现金的 NAV 推导任意现金比例的 NAV。"""
    ratio = nv_base / nv_base.shift(1)
    nv = nv_base.copy()
    v = 1.0
    nv.iloc[0] = v
    for i in range(1, len(nv_base)):
        factor = (1 - cash_ratio) * ratio.iloc[i] + cash_ratio * (1 + rf_daily)
        v *= factor
        nv.iloc[i] = v
    return nv


def _apply_trend_dip(w: np.ndarray, price_arr: np.ndarray, i: int,
                     col_idx: dict, sma_params: dict, dip_params: dict,
                     post_process_max_w: float | None) -> np.ndarray:
    """Apply trend filters + dip logic + post-process on numpy weight array.
    Modifies w in-place and returns it.
    """
    nf_idx = col_idx.get("nonferr", -1)
    gold_idx = col_idx.get("gold", -1)
    hs300_idx = col_idx.get("hs300", -1)
    credit_idx = col_idx.get("credit", -1)
    s = sma_params
    d = dip_params

    if s["nf_window"] > 0 and nf_idx >= 0 and w[nf_idx] > 0 and s["nf_sma"] is not None:
        if price_arr[i, nf_idx] < s["nf_sma"] and credit_idx >= 0:
            w[credit_idx] += w[nf_idx]
            w[nf_idx] = 0.0

    if s["eq_smas"] and credit_idx >= 0:
        for eq, sma_val in s["eq_smas"].items():
            eq_idx = col_idx.get(eq)
            if eq_idx is not None and w[eq_idx] > 0 and price_arr[i, eq_idx] < sma_val:
                w[credit_idx] += w[eq_idx]
                w[eq_idx] = 0.0

    if d["gold_trend"] and gold_idx >= 0 and w[gold_idx] > 0 and s["au_sma"] is not None:
        if price_arr[i, gold_idx] < s["au_sma"] and credit_idx >= 0:
            w[credit_idx] += w[gold_idx]
            w[gold_idx] = 0.0

    if d["gold_dip_threshold"] is not None and gold_idx >= 0 and w[gold_idx] > 0:
        gold_dd = price_arr[i, gold_idx] / d["gold_peak"] - 1
        if gold_dd <= -d["gold_dip_threshold"]:
            if not d["gold_boosted"]:
                boost = w[gold_idx] * d["gold_dip_boost"]
                if credit_idx >= 0 and w[credit_idx] >= boost:
                    w[gold_idx] += boost
                    w[credit_idx] -= boost
                    d["gold_boosted_flag"] = True
                    if d["gold_dip_cap"] is not None and w[gold_idx] > d["gold_dip_cap"]:
                        excess = w[gold_idx] - d["gold_dip_cap"]
                        w[gold_idx] = d["gold_dip_cap"]
                        if credit_idx >= 0:
                            w[credit_idx] += excess
        else:
            d["gold_boosted_flag"] = False

    if d["hs300_value_dip"] and hs300_idx >= 0 and w[hs300_idx] > 0:
        if d["hs300_boost"] is not None:
            boost = w[hs300_idx] * (d["hs300_boost"] - 1)
            if credit_idx >= 0 and w[credit_idx] >= boost:
                w[hs300_idx] += boost
                w[credit_idx] -= boost

    if post_process_max_w is not None:
        orig_sum = w.sum()
        w = np.clip(w, None, post_process_max_w)
        w = w / w.sum() * orig_sum if w.sum() > 0 else w

    return w


def _compute_weights(
    rets_window: pd.DataFrame,
    weighting_method: str,
    iv_window: int,
    rp_window: int,
    max_w: float,
    min_w: float,
    bucket_method: str = "equal",
    rp_buckets_frozen: dict | None = None,
) -> pd.Series:
    """Compute weighted portfolio from a window of returns.
    rp_buckets_frozen should be pre-frozen dict (lists not views).
    """
    if weighting_method == "hierarchical_rp":
        return hierarchical_rp_weights(rets_window, rp_buckets_frozen, rp_window, max_w, min_w, bucket_method=bucket_method)
    elif weighting_method == "erc":
        return erc_weights(rets_window, window=rp_window if rp_window else iv_window, max_w=max_w, min_w=min_w)
    else:
        return inverse_vol_weights(rets_window, window=iv_window, max_w=max_w, min_w=min_w)


def _apply_target_vol(w_arr: np.ndarray, recent_rets: pd.DataFrame, target_vol: float) -> np.ndarray:
    """Scale down weights when estimated portfolio vol exceeds target."""
    cov = recent_rets.cov().values * 252
    port_var = w_arr @ cov @ w_arr
    port_vol = np.sqrt(max(port_var, 1e-10))
    if port_vol > target_vol:
        return w_arr * (target_vol / port_vol)
    return w_arr


def _lookup_sma_params(
    i: int, price_arr: np.ndarray, col_idx: dict, sma_cache: dict,
    nonferr_trend_window: int, nonferr_idx: int,
    gold_trend_filter: bool, gold_idx: int, gold_trend_window: int,
    equity_trend_assets: list | None, equity_trend_windows: dict | None, equity_trend_window: int,
) -> tuple:
    """Lookup SMA values for trend filters from precomputed cache."""
    nf_sma = None
    au_sma = None
    eq_smas = {}
    if nonferr_trend_window > 0 and nonferr_idx >= 0 and i > nonferr_trend_window:
        nf_sma = float(sma_cache[nonferr_trend_window][i, nonferr_idx])
    if gold_trend_filter and gold_idx >= 0 and i > gold_trend_window:
        au_sma = float(sma_cache[gold_trend_window][i, gold_idx])
    if equity_trend_assets:
        for eq in equity_trend_assets:
            eq_idx = col_idx.get(eq)
            if eq_idx is not None:
                wdw = equity_trend_windows.get(eq, equity_trend_window) if equity_trend_windows else equity_trend_window
                if i > wdw:
                    eq_smas[eq] = float(sma_cache[wdw][i, eq_idx])
    return nf_sma, au_sma, eq_smas


def _apply_drift(h: np.ndarray, ret: np.ndarray, eff_cash: float) -> np.ndarray:
    """Position value drifts with returns, then renormalize to (1 - eff_cash)."""
    h = h * (1 + ret)
    s = h.sum()
    if s > 0:
        h = h / s * (1 - eff_cash)
    return h


def _build_signal_entry(
    d, w: np.ndarray, price_arr: np.ndarray, i: int,
    col_idx: dict, nf_sma, au_sma, eq_smas: dict,
    nonferr_trend_window: int, nonferr_idx: int,
    gold_trend_filter: bool, gold_idx: int, gold_dip_threshold: float | None, gold_peak: float,
    equity_trend_assets: list | None,
    hs300_idx: int, pb_data, pe_data, hs300_peak: float, hs300_boosted: bool, hs300_dip_boost: float,
    hs300_pb_pct, hs300_pe_pct,
    signal_label: str,
) -> dict:
    """Build a signal log entry for the current rebalance day."""
    entry = {'date': d, 'label': signal_label}
    if nonferr_trend_window > 0 and nonferr_idx >= 0:
        entry['nonferr_below_sma'] = bool(price_arr[i, nonferr_idx] < nf_sma) if nf_sma is not None else False
        entry['nonferr_filtered'] = w[nonferr_idx] == 0
    if gold_trend_filter and gold_idx >= 0:
        entry['gold_below_sma'] = bool(price_arr[i, gold_idx] < au_sma) if au_sma is not None else False
        entry['gold_filtered'] = w[gold_idx] == 0
    if equity_trend_assets:
        for eq in equity_trend_assets:
            eq_idx = col_idx.get(eq)
            if eq_idx is not None:
                entry[f'{eq}_below_sma'] = bool(price_arr[i, eq_idx] < eq_smas.get(eq, -np.inf))
                entry[f'{eq}_filtered'] = w[eq_idx] == 0
    if gold_dip_threshold is not None and gold_idx >= 0:
        gold_dd = float(price_arr[i, gold_idx] / gold_peak - 1)
        entry['gold_dd_pct'] = round(gold_dd, 4)
        entry['gold_dip_active'] = gold_dd <= -gold_dip_threshold and w[gold_idx] > 0
    if hs300_idx >= 0:
        hs300_px = float(price_arr[i, hs300_idx])
        snap = hs300_signal_snapshot(pb_data, pe_data, hs300_peak, hs300_boosted, hs300_dip_boost,
                                      pb_pct_series=hs300_pb_pct, pe_pct_series=hs300_pe_pct,
                                      hs300_price_val=hs300_px, date=d)
        entry.update(snap)
    return entry


def _build_dip_params(
    gold_trend_filter, gold_dip_threshold, gold_dip_boost, gold_dip_cap,
    gold_peak, gold_boosted, hs300_value_dip, hs300_boost,
) -> dict:
    """Build dip_params dict for _apply_trend_dip. gold_boosted_flag resets each call."""
    return {
        "gold_trend": gold_trend_filter,
        "gold_dip_threshold": gold_dip_threshold,
        "gold_dip_boost": gold_dip_boost,
        "gold_dip_cap": gold_dip_cap,
        "gold_peak": gold_peak,
        "gold_boosted": gold_boosted,
        "gold_boosted_flag": False,
        "hs300_value_dip": hs300_value_dip,
        "hs300_boost": hs300_boost,
    }


def backtest(
    rets: pd.DataFrame,
    cash_ratio: float = 0.0,
    rf_daily: float = RISK_FREE_RATE,
    weighting_method: str = "inverse_vol",
    iv_window: int = 60,
    rp_window: int = RISK_PARITY_WINDOW,
    bucket_method: str = "equal",
    max_w: float = 0.30,
    min_w: float = 0.03,
    rp_buckets: dict | None = None,
    nonferr_trend_window: int = 75,
    gold_trend_filter: bool = False,
    gold_trend_window: int = 75,
    gold_dip_threshold: float | None = GOLD_DIP_THRESHOLD,
    gold_dip_boost: float = GOLD_DIP_BOOST,
    gold_dip_cap: float | None = None,
    hs300_dip_threshold: float | None = HS300_DIP_THRESHOLD,
    hs300_dip_boost: float = HS300_DIP_BOOST,
    hs300_dip_sma: int = HS300_DIP_SMA,
    hs300_dip_exit_recovery: float = HS300_DIP_EXIT_RECOVERY,
    hs300_value_dip: bool = False,
    hs300_pb_entry: float = HS300_PB_ENTRY,
    hs300_pe_exit: float = HS300_PE_EXIT,
    equity_trend_assets: list | None = None,
    equity_trend_window: int = 120,
    equity_trend_windows: dict | None = None,
    target_vol: float | None = None,
    vol_target_window: int = 60,
    assets: list | None = None,
    track_weights: bool = False,
    track_signals: bool = False,
    signal_label: str = "",
    post_process_max_w: float | None = None,
    hs300_pb_data: pd.Series | None = None,
    hs300_pe_data: pd.Series | None = None,
    hs300_pb_pct: pd.Series | None = None,
    hs300_pe_pct: pd.Series | None = None,
    track_dynamic_nav: bool = False,
) -> BacktestResult:
    """统一回测引擎 — 逆波动率/分层风险平价 + 趋势过滤 + 抄底。

    When track_dynamic_nav=True, returns (nv, nv_dynamic, n_rebal, weight_df, signal_df).
    """
    from .data import load_hs300_pb, load_hs300_pe

    if assets is not None:
        rets_rp = rets[assets]
    else:
        rets_rp = rets
    cols = list(rets_rp.columns)
    n_assets = len(cols)

    # --- Pre-compute numpy arrays for hot path ---
    rets_arr = rets_rp.values  # (n_days, n_assets)
    prices = (1 + rets_rp).cumprod()
    price_arr = prices.values
    col_idx = {c: i for i, c in enumerate(cols)}
    idx_cols = [col_idx[c] for c in cols]  # ordered list

    nv = pd.Series(index=rets_rp.index, dtype=float)
    n_rebal = 0
    nonferr_idx = col_idx.get("nonferr", -1)
    gold_idx = col_idx.get("gold", -1)
    hs300_idx = col_idx.get("hs300", -1)
    credit_idx = col_idx.get("credit", -1)

    # --- Precompute all SMAs for trend windows ---
    sma_cache = {}
    _needed_windows = set()
    if nonferr_trend_window > 0:
        _needed_windows.add(nonferr_trend_window)
    if gold_trend_filter and gold_trend_window > 0:
        _needed_windows.add(gold_trend_window)
    if hs300_value_dip and hs300_idx >= 0 and hs300_dip_sma > 0:
        _needed_windows.add(hs300_dip_sma)
    if equity_trend_assets:
        for eq in equity_trend_assets:
            eq_idx = col_idx.get(eq)
            if eq_idx is not None:
                wdw = equity_trend_windows.get(eq, equity_trend_window) if equity_trend_windows else equity_trend_window
                if wdw > 0:
                    _needed_windows.add(wdw)
    for w in _needed_windows:
        sma = prices.rolling(window=w, min_periods=1).mean().shift(1)
        sma_cache[w] = sma.values  # (n_days, n_assets), NaN when i < w

    gold_peak = float(price_arr[0, gold_idx]) if gold_idx >= 0 else 1.0
    gold_boosted = False
    hs300_peak = float(price_arr[0, hs300_idx]) if hs300_idx >= 0 else 1.0
    pb_data = hs300_pb_data if hs300_pb_data is not None else (load_hs300_pb() if hs300_value_dip else None)
    pe_data = hs300_pe_data if hs300_pe_data is not None else (load_hs300_pe() if hs300_value_dip else None)
    hs300_boosted = False

    if track_dynamic_nav:
        nv_dyn = pd.Series(index=rets_rp.index, dtype=float)

    lookback = rp_window if weighting_method in ("hierarchical_rp", "erc") else iv_window
    rp_buckets_frozen = {k: list(v) for k, v in (rp_buckets or BUCKET_GROUPS).items()}
    initial_w = _compute_weights(rets_rp.iloc[:lookback], weighting_method, iv_window, rp_window, max_w, min_w, bucket_method, rp_buckets_frozen)

    # h sums to (1 - cash_ratio), numpy array for fast dot product
    h = initial_w.values * (1 - cash_ratio)
    v = 1.0
    eff_cash = cash_ratio
    weight_log = {} if track_weights else None
    signal_log = [] if track_signals else None

    if track_dynamic_nav:
        h_dyn = h.copy()
        eff_cash_dyn = cash_ratio
        v_dyn = 1.0

    for i, d in enumerate(rets_rp.index):
        if i == 0:
            nv.loc[d] = 1.0
            if track_dynamic_nav:
                nv_dyn.loc[d] = 1.0
            continue

        # --- Daily return ---
        daily_ret = np.dot(h, rets_arr[i])
        v *= 1 + daily_ret + eff_cash * rf_daily
        nv.loc[d] = v

        if track_dynamic_nav:
            daily_ret_dyn = np.dot(h_dyn, rets_arr[i])
            v_dyn *= 1 + daily_ret_dyn + eff_cash_dyn * rf_daily
            nv_dyn.loc[d] = v_dyn

        # --- Drift (position drifts with returns, then renormalize) ---
        h = _apply_drift(h, rets_arr[i], eff_cash)
        if track_dynamic_nav:
            h_dyn = _apply_drift(h_dyn, rets_arr[i], eff_cash_dyn)

        # --- Peak tracking ---
        if gold_idx >= 0:
            if price_arr[i, gold_idx] > gold_peak:
                gold_peak = float(price_arr[i, gold_idx])
        if hs300_idx >= 0:
            if price_arr[i, hs300_idx] > hs300_peak:
                hs300_peak = float(price_arr[i, hs300_idx])

        # --- Rebalance ---
        if d.month != rets_rp.index[i - 1].month and i > lookback:
            window_df = rets_rp.iloc[max(0, i - lookback):i]

            new_w = _compute_weights(window_df, weighting_method, iv_window, rp_window, max_w, min_w, bucket_method, rp_buckets_frozen)
            new_w_arr = new_w.values  # sums to ~1 (normalized)

            # --- Target volatility: scale down when estimated vol > target ---
            if target_vol is not None and i > vol_target_window:
                new_w_arr = _apply_target_vol(new_w_arr, rets_rp.iloc[i - vol_target_window:i], target_vol)

            # --- Lookup SMA conditions from precomputed cache ---
            nf_sma, au_sma, eq_smas = _lookup_sma_params(
                i, price_arr, col_idx, sma_cache,
                nonferr_trend_window, nonferr_idx,
                gold_trend_filter, gold_idx, gold_trend_window,
                equity_trend_assets, equity_trend_windows, equity_trend_window,
            )

            # --- Compute HS300 dip condition once ---
            hs300_boost = None
            if hs300_value_dip and hs300_idx >= 0 and i > hs300_dip_sma:
                hs300_sma_v = float(sma_cache[hs300_dip_sma][i, hs300_idx])
                hs300_px = float(price_arr[i, hs300_idx])
                hs300_boosted, hs300_boost = hs300_dip_check(
                    pb_data, pe_data, hs300_peak, hs300_boosted,
                    hs300_dip_threshold, hs300_dip_exit_recovery,
                    hs300_pb_entry, hs300_pe_exit, hs300_dip_boost,
                    pb_pct_series=hs300_pb_pct, pe_pct_series=hs300_pe_pct,
                    hs300_sma_val=hs300_sma_v, hs300_price_val=hs300_px, date=d,
                )
            sma_params = {"nf_window": nonferr_trend_window, "nf_sma": nf_sma,
                          "au_sma": au_sma, "eq_smas": eq_smas}
            _gb_before = gold_boosted

            # --- Apply trend filters + dip on base weights ---
            w = new_w_arr * (1 - cash_ratio)
            dip_base = _build_dip_params(gold_trend_filter, gold_dip_threshold, gold_dip_boost, gold_dip_cap,
                                          gold_peak, _gb_before, hs300_value_dip, hs300_boost)
            w = _apply_trend_dip(w, price_arr, i, col_idx, sma_params, dip_base, post_process_max_w)
            gold_boosted = dip_base["gold_boosted_flag"]
            eff_cash = 1.0 - w.sum()
            h = w

            # --- Dynamic variant (if tracking) ---
            if track_dynamic_nav:
                dyn_cr = dynamic_cash_ratio(prices["hs300"], i) if hs300_idx >= 0 else cash_ratio
                w_dyn = new_w_arr * (1 - dyn_cr)
                dip_dyn = _build_dip_params(gold_trend_filter, gold_dip_threshold, gold_dip_boost, gold_dip_cap,
                                             gold_peak, _gb_before, hs300_value_dip, hs300_boost)
                w_dyn = _apply_trend_dip(w_dyn, price_arr, i, col_idx, sma_params, dip_dyn, post_process_max_w)
                eff_cash_dyn = 1.0 - w_dyn.sum()
                h_dyn = w_dyn

            # --- Signal logging ---
            if track_signals:
                entry = _build_signal_entry(
                    d, w, price_arr, i, col_idx,
                    nf_sma, au_sma, eq_smas,
                    nonferr_trend_window, nonferr_idx,
                    gold_trend_filter, gold_idx, gold_dip_threshold, gold_peak,
                    equity_trend_assets,
                    hs300_idx, pb_data, pe_data, hs300_peak, hs300_boosted, hs300_dip_boost,
                    hs300_pb_pct, hs300_pe_pct, signal_label,
                )
                signal_log.append(entry)

            n_rebal += 1
            if track_weights:
                weight_log[d] = pd.Series(w, index=cols)

    weight_df = pd.DataFrame(weight_log).T if track_weights else None
    signal_df = pd.DataFrame(signal_log) if track_signals else None
    return BacktestResult(
        nv=nv,
        nv_dyn=nv_dyn if track_dynamic_nav else None,
        n_rebal=n_rebal,
        weight_df=weight_df,
        signal_df=signal_df,
    )


def backtest_iv(
    rets: pd.DataFrame,
    cash_ratio: float = 0.0,
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
    hs300_value_dip: bool = False,
    hs300_pb_entry: float = HS300_PB_ENTRY,
    hs300_pe_exit: float = HS300_PE_EXIT,
    track_signals: bool = False,
    signal_label: str = "",
    equity_trend_assets: list | None = None,
    equity_trend_window: int = 120,
    equity_trend_windows: dict | None = None,
    post_process_max_w: float | None = None,
    hs300_pb_data: pd.Series | None = None,
    hs300_pe_data: pd.Series | None = None,
    hs300_pb_pct: pd.Series | None = None,
    hs300_pe_pct: pd.Series | None = None,
    track_dynamic_nav: bool = False,
    **kwargs,
) -> BacktestResult:
    """逆波动率加权 — 委托给 backtest()。"""
    return backtest(
        rets, cash_ratio=cash_ratio, rf_daily=rf_daily,
        weighting_method="inverse_vol", iv_window=iv_window,
        max_w=max_w, min_w=min_w,
        nonferr_trend_window=nonferr_trend_window,
        gold_trend_filter=gold_trend_filter, gold_trend_window=gold_trend_window,
        gold_dip_threshold=gold_dip_threshold, gold_dip_boost=gold_dip_boost,
        gold_dip_cap=gold_dip_cap,
        hs300_dip_threshold=hs300_dip_threshold, hs300_dip_boost=hs300_dip_boost,
        hs300_dip_sma=hs300_dip_sma, hs300_dip_exit_recovery=hs300_dip_exit_recovery,
        hs300_value_dip=hs300_value_dip, hs300_pb_entry=hs300_pb_entry,
        hs300_pe_exit=hs300_pe_exit,
        equity_trend_assets=equity_trend_assets,
        equity_trend_window=equity_trend_window,
        equity_trend_windows=equity_trend_windows,
        assets=assets,
        track_weights=track_weights, track_signals=track_signals,
        signal_label=signal_label, post_process_max_w=post_process_max_w,
        hs300_pb_data=hs300_pb_data, hs300_pe_data=hs300_pe_data,
        hs300_pb_pct=hs300_pb_pct, hs300_pe_pct=hs300_pe_pct,
        track_dynamic_nav=track_dynamic_nav,
        **kwargs,
    )


