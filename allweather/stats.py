"""统计指标 - 收益、波动、回撤、Sharpe、Calmar、风险贡献、Bootstrap。"""
import numpy as np
import pandas as pd
from .config import (
    BUCKETS, BOOTSTRAP_N_SIM, BOOTSTRAP_HORIZON_DAYS,
    BOOTSTRAP_BLOCK_DAYS, BOOTSTRAP_SEED, RISK_FREE_ANNUAL,
)


def perf_metrics(nv: pd.Series) -> dict:
    """从净值序列算核心指标。"""
    r = nv.pct_change().dropna()
    n = len(r)
    n_years = n / 252.0
    cum = nv.iloc[-1] - 1
    cagr = (1 + cum) ** (1 / n_years) - 1 if n_years > 0 else 0
    vol = r.std() * np.sqrt(252)
    mdd = ((nv / nv.cummax()) - 1).min()
    sharpe_raw = cagr / vol if vol > 0 else float("nan")
    sharpe = (cagr - RISK_FREE_ANNUAL) / vol if vol > 0 else float("nan")
    calmar = cagr / abs(mdd) if mdd < 0 else float("nan")
    return {
        "n_years": n_years,
        "cum_return": cum,
        "cagr": cagr,
        "vol": vol,
        "mdd": mdd,
        "sharpe": sharpe,
        "sharpe_raw": sharpe_raw,
        "calmar": calmar,
        "final_nv": nv.iloc[-1],
    }


def yearly_returns(nv: pd.Series) -> pd.Series:
    """按自然年聚合收益率。"""
    r = nv.pct_change().dropna()
    return r.groupby(r.index.year).apply(lambda x: (1 + x).prod() - 1)


def event_returns(nv: pd.Series, events: list) -> dict:
    """按事件期切片，返回每段的累计收益。"""
    out = {}
    for label, start, end in events:
        seg = nv.loc[start:end]
        if len(seg) > 1:
            out[label] = seg.iloc[-1] / seg.iloc[0] - 1
        else:
            out[label] = float("nan")
    return out


def bucket_risk_contribution(weights: pd.Series, rets: pd.DataFrame) -> dict:
    """协方差视角下，各桶的风险贡献占比。"""
    cov = rets.cov().values * 252
    w = weights.values
    pv = w @ cov @ w
    rc = w * (cov @ w) / pv
    rc_s = pd.Series(rc, index=weights.index)
    return {bucket: sum(rc_s[a] for a in lst if a in rc_s.index)
            for bucket, lst in BUCKETS.items()}


def regime_returns(nv: pd.Series, rets: pd.DataFrame) -> dict:
    """4 宏观情景（股牛/熊 × 债牛/熊）平均季度收益。"""
    qhs = rets["hs300"].resample("QE").apply(lambda x: (1 + x).prod() - 1)
    qbond = rets["bond_10y"].resample("QE").apply(lambda x: (1 + x).prod() - 1)
    regime = pd.Series(index=qhs.index, dtype=object)
    for d in qhs.index:
        s = "股牛" if qhs[d] > 0 else "股熊"
        b = "债牛" if qbond[d] > 0 else "债熊"
        regime[d] = f"{s}+{b}"

    qret = nv.pct_change().dropna().resample("QE").apply(
        lambda x: (1 + x).prod() - 1)
    out = {}
    for r_label in ["股牛+债牛", "股牛+债熊", "股熊+债牛", "股熊+债熊"]:
        mask = regime == r_label
        n = int(mask.sum())
        if n > 0:
            out[r_label] = {"avg": qret[mask].mean(), "n": n}
        else:
            out[r_label] = {"avg": float("nan"), "n": 0}
    return out


def rolling_stats(nv: pd.Series, window: int = 252) -> dict:
    """滚动 1 年期统计。"""
    r = nv.pct_change().dropna()
    rolling_ann = (1 + r).rolling(window).apply(
        lambda x: x.prod() ** (252 / window) - 1, raw=True).dropna()
    rolling_dd = (nv / nv.rolling(window).max() - 1).dropna()
    return {
        "ann_min": rolling_ann.min(),
        "ann_med": rolling_ann.median(),
        "ann_max": rolling_ann.max(),
        "dd_min": rolling_dd.min(),
        "neg_year_pct": (rolling_ann < 0).mean(),
    }


def block_bootstrap(weights: pd.Series, rets: pd.DataFrame,
                    n_sim: int = None, horizon: int = None,
                    block: int = None, seed: int = None) -> dict:
    """块自助法模拟 5 年期累计收益分布。"""
    n_sim = n_sim or BOOTSTRAP_N_SIM
    horizon = horizon or BOOTSTRAP_HORIZON_DAYS
    block = block or BOOTSTRAP_BLOCK_DAYS
    seed = seed if seed is not None else BOOTSTRAP_SEED

    rng = np.random.RandomState(seed)
    arr = rets.values
    n_days = len(arr)
    w = weights.values

    samples = []
    for _ in range(n_sim):
        n_blocks = horizon // block
        starts = rng.randint(0, n_days - block, size=n_blocks)
        block_idxs = np.concatenate(
            [np.arange(s, s + block) for s in starts])[:horizon]
        sim = arr[block_idxs]
        cum = np.prod(1 + (sim * w).sum(axis=1)) - 1
        samples.append(cum)

    s = pd.Series(samples)
    qs = s.quantile([0.05, 0.25, 0.5, 0.75, 0.95])
    return {
        "p05": qs[0.05], "p25": qs[0.25], "p50": qs[0.5],
        "p75": qs[0.75], "p95": qs[0.95],
        "ann_median": (1 + qs[0.5]) ** (1 / 5) - 1,
        "loss_prob": (s < 0).mean(),
    }
