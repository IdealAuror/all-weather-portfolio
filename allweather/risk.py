"""风控模块 —— 趋势过滤、回撤止损、波动率目标、相关性断路器、逆波动率加权。"""

import numpy as np
import pandas as pd


def trend_filter(returns_12m: pd.Series) -> bool:
    """过去 12 个月总收益为负 → True（触发避险）。"""
    if len(returns_12m) < 20:
        return False
    cum = (1 + returns_12m).prod() - 1
    return cum < 0


def drawdown_stop(nv: pd.Series, threshold: float = 0.08) -> bool:
    """当前回撤超过 threshold → True（触发降仓）。"""
    if len(nv) < 20:
        return False
    dd = (nv / nv.cummax()) - 1
    return dd.iloc[-1] < -threshold


def vol_target_scale(returns, target_vol: float = 0.06,
                     window: int = 60) -> float:
    """返回仓位缩放系数：实际波动 vs 目标波动。上限 1.0（不加杠杆）。"""
    if isinstance(returns, pd.DataFrame):
        recent = returns.tail(window)
    else:
        recent = returns.iloc[-window:]
    if len(recent) < 20:
        return 1.0
    if isinstance(recent, pd.DataFrame):
        ann_vol = recent.std().mean() * np.sqrt(252)
    else:
        ann_vol = recent.std() * np.sqrt(252)
    if ann_vol < 0.001:
        return 1.0
    scale = target_vol / ann_vol
    return min(scale, 1.0)


def correlation_breaker(returns: pd.DataFrame, threshold: float = 0.30,
                        window: int = 60) -> bool:
    """平均两两相关性 > threshold → True（触发降仓）。"""
    recent = returns.tail(window)
    if len(recent) < 20:
        return False
    corr = recent.corr().values
    n = corr.shape[0]
    upper = corr[np.triu_indices(n, k=1)]
    return upper.mean() > threshold


def inverse_vol_weights(returns: pd.DataFrame, window: int = 60,
                        max_w: float = 0.25, min_w: float = 0.02) -> pd.Series:
    """用过去 window 日逆波动率算权重，再截断到 [min_w, max_w]。"""
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
    """分层风险平价：桶间等权/等风险 + 桶内逆波动率。"""
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
