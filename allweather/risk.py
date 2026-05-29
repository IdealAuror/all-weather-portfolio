"""风控模块 —— 逆波动率加权、分层风险平价、HS300 AND抄底。"""
import numpy as np
import pandas as pd


def inverse_vol_weights(returns: pd.DataFrame, window: int = 60,
                        max_w: float = 0.25, min_w: float = 0.02) -> pd.Series:
    if len(returns) < 20:
        n = returns.shape[1]
        return pd.Series(1.0 / n, index=returns.columns)
    recent = returns.tail(window)
    vols = recent.std() * np.sqrt(252)
    inv_vol = 1 / vols.replace(0, np.nan)
    raw = inv_vol / inv_vol.sum()
    capped = raw.clip(lower=min_w, upper=max_w)
    return capped / capped.sum()


def hierarchical_rp_weights(
    returns: pd.DataFrame,
    bucket_groups: dict,
    window: int = 60,
    max_w: float = 0.25,
    min_w: float = 0.02,
    bucket_method: str = "equal",
) -> pd.Series:
    if len(returns) < 20:
        n = returns.shape[1]
        return pd.Series(1.0 / n, index=returns.columns)

    recent = returns.tail(window)
    n_buckets = len(bucket_groups)

    bucket_w = {}
    bucket_vol = {}
    for bname, assets in bucket_groups.items():
        valid = [a for a in assets if a in recent.columns]
        if not valid:
            continue
        brets = recent[valid]
        vols = brets.std() * np.sqrt(252)
        inv = 1 / vols.replace(0, np.nan)
        w = inv / inv.sum()
        bucket_w[bname] = w
        port_r = (brets * w.values).sum(axis=1)
        bucket_vol[bname] = port_r.std() * np.sqrt(252)

    if bucket_method == "equal":
        bucket_alloc = {k: 1.0 / n_buckets for k in bucket_w}
    else:
        inv_vols = {k: 1.0 / v for k, v in bucket_vol.items() if v > 0.001}
        total = sum(inv_vols.values())
        bucket_alloc = {k: v / total for k, v in inv_vols.items()}

    raw = pd.Series(0.0, index=returns.columns)
    for bname, bw in bucket_alloc.items():
        for asset in bucket_w[bname].index:
            raw[asset] = bw * bucket_w[bname][asset]

    capped = raw.clip(lower=min_w, upper=max_w)
    return capped / capped.sum()


def hs300_dip_check(pe_data, prices, d, i, hs300_peak, hs300_boosted,
                    threshold, sma_window, exit_recovery,
                    pe_entry, pe_exit, boost_mult):
    """HS300 AND抄底 — 价格回撤 + PE 低估同时满足才触发。
    返回 (hs300_boosted, boost_multiplier | None)。
    """
    pe_to_date = pe_data[pe_data.index <= d]
    if len(pe_to_date) < 252:
        return hs300_boosted, None

    pe_pct = (pe_to_date < pe_to_date.iloc[-1]).sum() / len(pe_to_date) * 100
    hs300_dd = prices.iloc[i]["hs300"] / hs300_peak - 1
    curr_hs = prices.iloc[i]["hs300"]
    dip_sma = prices["hs300"].iloc[max(0, i - sma_window):i].mean()

    if hs300_boosted:
        if hs300_dd > -exit_recovery and pe_pct > pe_exit:
            return False, None
    elif (hs300_dd <= -threshold and pe_pct < pe_entry
          and curr_hs > dip_sma):
        hs300_boosted = True

    if hs300_boosted:
        return True, boost_mult
    return False, None


def hs300_signal_snapshot(pe_data, prices, d, i, hs300_peak, hs300_boosted, boost_mult):
    sig_dd = round(float(prices.iloc[i]["hs300"] / hs300_peak - 1), 4)
    sig_pe_val, sig_pe_pct = None, None
    pe_to = pe_data[pe_data.index <= d]
    if len(pe_to) >= 252:
        sig_pe_val = float(pe_to.iloc[-1])
        sig_pe_pct = round((pe_to < sig_pe_val).sum() / len(pe_to) * 100, 1)
    return {
        'dd_pct': sig_dd,
        'pe_pctile': sig_pe_pct,
        'pe_value': sig_pe_val,
        'active': hs300_boosted,
        'boost': boost_mult if hs300_boosted else None,
    }
