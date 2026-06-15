"""统计指标 - 收益、波动、回撤、Sharpe、Calmar、风险贡献、Bootstrap。"""
import numpy as np
import pandas as pd
from .config import (
    BUCKETS, BOOTSTRAP_N_SIM, BOOTSTRAP_HORIZON_DAYS,
    BOOTSTRAP_BLOCK_DAYS, BOOTSTRAP_SEED, RISK_FREE_ANNUAL,
)
from .types import PerfMetrics, RollingStats, DExcessResult, WeightStability, BootstrapResult

def perf_metrics(nv: pd.Series, rets: pd.Series | None = None) -> PerfMetrics:
    """从净值序列算核心指标。

    注：sharpe = (CAGR - RISK_FREE_ANNUAL) / vol, 与 CLAUDE.md 一致。
    """
    r = rets if rets is not None else nv.pct_change().dropna()
    n = len(r)
    n_years = n / 252.0
    cum = nv.iloc[-1] - 1
    cagr = (1 + cum) ** (1 / n_years) - 1 if n_years > 0 else 0
    vol = r.std() * np.sqrt(252)
    mdd = ((nv / nv.cummax()) - 1).min()
    sharpe_raw = cagr / vol if vol > 0 else float("nan")
    sharpe = (cagr - RISK_FREE_ANNUAL) / vol if vol > 0 else float("nan")
    calmar = cagr / abs(mdd) if mdd < 0 else float("nan")
    # 以下为诊断用：算术超额 vs 几何超额的差异
    rf_daily = RISK_FREE_ANNUAL / 252
    excess = r - rf_daily
    arith_mean_excess = excess.mean() * 252
    G_real = cagr - RISK_FREE_ANNUAL
    G_theo = arith_mean_excess - vol**2 / 2
    geometric_excess_d = G_real - G_theo
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
        "G_real": G_real,
        "G_theoretical": G_theo,
        "geometric_excess_d": geometric_excess_d,
    }


def yearly_returns(nv: pd.Series, rets: pd.Series | None = None) -> pd.Series:
    """按自然年聚合收益率。"""
    r = rets if rets is not None else nv.pct_change().dropna()
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
    common = weights.index.intersection(rets.columns)
    w = weights[common].values
    r = rets[common]
    cov = r.cov().values * 252
    pv = w @ cov @ w
    rc = w * (cov @ w) / pv
    rc_s = pd.Series(rc, index=common)
    return {bucket: sum(rc_s[a] for a in lst if a in rc_s.index)
            for bucket, lst in BUCKETS.items()}


def weight_stability(weight_history: pd.DataFrame, cost_bp: float = 10) -> dict:
    """权重稳定性指标：换手率、有效资产数、成本拖累。

    weight_history: 调仓日 × 资产的权重 DataFrame。
    cost_bp: 单边交易成本基点（默认 10bp = 0.1%）。
    """
    if weight_history.empty:
        return {"monthly_turnover_mean": 0, "monthly_turnover_max": 0,
                "annual_churn": 0, "effective_n_mean": 0,
                "cost_drag_annual": 0}

    # 月均换手率：每个调仓日权重变动之和 / 2
    w_diff = weight_history.diff().abs().sum(axis=1)
    turnover = w_diff / 2
    monthly_turnover_mean = turnover.mean()
    monthly_turnover_max = turnover.max()

    # 年化换手率（月度调仓 → ×12）
    annual_churn = monthly_turnover_mean * 12

    # 有效资产数：1 / sum(w_i^2)
    eff_n = 1 / (weight_history ** 2).sum(axis=1)
    effective_n_mean = eff_n.mean()
    effective_n_min = eff_n.min()

    # 成本拖累：年化换手 × 双边成本
    cost_drag_annual = annual_churn * (cost_bp * 2 / 10000)

    return {
        "monthly_turnover_mean": monthly_turnover_mean,
        "monthly_turnover_max": monthly_turnover_max,
        "annual_churn": annual_churn,
        "effective_n_mean": effective_n_mean,
        "effective_n_min": effective_n_min,
        "cost_drag_annual": cost_drag_annual,
        "cost_bp_assumed": cost_bp,
    }


def risk_contribution_time_varying(
    weight_history: pd.DataFrame, rets: pd.DataFrame,
    buckets: dict, window: int = 252,
) -> dict:
    """时变风险贡献归因 — 在每个调仓日计算桶级风险贡献，然后取时间序列均值。

    weight_history: 调仓日 × 资产的权重 DataFrame。
    rets: 完整日收益率 DataFrame。
    buckets: {桶名: [资产列表]}。
    window: 协方差估计窗口（交易日，默认 252 ≈ 1 年）。
    """
    if weight_history.empty:
        return {}

    bucket_series = {b: [] for b in buckets}
    n_valid = 0

    for date in weight_history.index:
        w = weight_history.loc[date]
        # 只取有收益数据的资产
        valid_assets = [a for a in w.index if a in rets.columns]
        if len(valid_assets) < 2:
            continue
        wv = w[valid_assets].values

        # 取调仓日前 window 个交易日估计协方差
        end_idx = rets.index.get_loc(date) if date in rets.index else -1
        if end_idx < window:
            continue
        r = rets[valid_assets].iloc[end_idx - window:end_idx]
        cov = r.cov().values * 252
        port_var = wv @ cov @ wv
        if port_var <= 0:
            continue

        # 边际风险贡献：w * (Σw) / σ²
        mc = wv * (cov @ wv) / port_var
        mc_s = pd.Series(mc, index=valid_assets)

        for bucket, assets in buckets.items():
            valid = [a for a in assets if a in mc_s.index]
            bucket_series[bucket].append(mc_s[valid].sum() if valid else 0.0)
        n_valid += 1

    result = {}
    for bucket, vals in bucket_series.items():
        if vals:
            arr = np.array(vals)
            result[bucket] = {
                "mean": float(arr.mean()),
                "std": float(arr.std()),
                "min": float(arr.min()),
                "max": float(arr.max()),
            }
    result["_n_observations"] = n_valid
    return result


def regime_returns(nv: pd.Series, rets: pd.DataFrame = None,
                   regime_labels: pd.Series = None) -> dict:
    """4 宏观情景（股牛/熊 × 债牛/熊）平均季度收益。

    regime_labels: 预计算的季度情景标签（复用避免重复计算）。
    """
    if regime_labels is None:
        if rets is None or "hs300" not in rets.columns or "bond_10y" not in rets.columns:
            return {}
        qhs = rets["hs300"].resample("QE").apply(lambda x: (1 + x).prod() - 1)
        qbond = rets["bond_10y"].resample("QE").apply(lambda x: (1 + x).prod() - 1)
        regime = pd.Series(index=qhs.index, dtype=object)
        for d in qhs.index:
            s = "股牛" if qhs[d] > 0 else "股熊"
            b = "债牛" if qbond[d] > 0 else "债熊"
            regime[d] = f"{s}+{b}"
    else:
        regime = regime_labels

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


def rolling_stats(nv: pd.Series, window: int = 252,
                  rets: pd.Series | None = None) -> dict:
    """滚动 1 年期统计。"""
    r = rets if rets is not None else nv.pct_change().dropna()
    cum = (1 + r).cumprod()
    rolling_ann = (cum / cum.shift(window) - 1).dropna()
    rolling_dd = (nv / nv.rolling(window).max() - 1).dropna()
    return {
        "ann_min": rolling_ann.min(),
        "ann_med": rolling_ann.median(),
        "ann_max": rolling_ann.max(),
        "dd_min": rolling_dd.min(),
        "neg_year_pct": (rolling_ann < 0).mean(),
        "rolling_ann": rolling_ann,
        "rolling_dd": rolling_dd,
    }


def d_significance(nv: pd.Series, n_sim: int = 2000, seed: int | None = None,
                   rets: pd.Series | None = None) -> dict:
    """D_excess 统计显著性 — 正态参数 Bootstrap。

    在收益正态分布的零假设下，模拟 n_sim 条路径，
    计算 D 的零分布。返回实际 D 在其中的百分位。
    """
    r = rets if rets is not None else nv.pct_change().dropna()
    n_days = len(r)
    if n_days < 2:
        return {"d_actual": float("nan"), "d_null_mean": float("nan"),
                "d_null_std": float("nan"), "ci_95_low": float("nan"),
                "ci_95_high": float("nan"), "percentile": float("nan"),
                "significant_05": False}
    n_years = n_days / 252.0
    vol = r.std() * np.sqrt(252)
    cagr = nv.iloc[-1] ** (1 / n_years) - 1

    excess = r - RISK_FREE_ANNUAL / 252
    arith_actual = excess.mean() * 252
    d_actual = (cagr - RISK_FREE_ANNUAL) - (arith_actual - vol**2 / 2)

    sigma_d = vol / np.sqrt(252)
    mu_log_daily = np.log(1 + cagr) / 252 - sigma_d**2 / 2
    rf_daily = RISK_FREE_ANNUAL / 252

    rng = np.random.RandomState(seed if seed is not None else BOOTSTRAP_SEED)
    log_r = rng.normal(mu_log_daily, sigma_d, (n_sim, n_days))
    sim_r = np.exp(log_r) - 1
    sim_excess = sim_r - rf_daily
    sim_arith = sim_excess.mean(axis=1) * 252
    sim_nv_end = (1 + sim_r).prod(axis=1)
    sim_cagr = sim_nv_end ** (1 / n_years) - 1
    D_sim = (sim_cagr - RISK_FREE_ANNUAL) - (sim_arith - vol**2 / 2)

    percentile = float((D_sim < d_actual).mean())
    return {
        "d_actual": d_actual,
        "d_null_mean": float(D_sim.mean()),
        "d_null_std": float(D_sim.std()),
        "ci_95_low": float(np.percentile(D_sim, 2.5)),
        "ci_95_high": float(np.percentile(D_sim, 97.5)),
        "percentile": percentile,
        "significant_05": percentile > 0.975 or percentile < 0.025,
    }


def block_bootstrap(weights: pd.Series, rets: pd.DataFrame,
                    n_sim: int = None, horizon: int = None,
                    block: int = None, seed: int = None) -> dict:
    """块自助法模拟 5 年期累计收益分布（向量化）。"""
    n_sim = n_sim or BOOTSTRAP_N_SIM
    horizon = horizon or BOOTSTRAP_HORIZON_DAYS
    block = block or BOOTSTRAP_BLOCK_DAYS
    seed = seed if seed is not None else BOOTSTRAP_SEED

    rng = np.random.RandomState(seed)
    arr = rets.values
    n_days = len(arr)

    if n_days < block:
        return {"p05": None, "p25": None, "p50": None,
                "p75": None, "p95": None,
                "ann_median": None, "loss_prob": None, "samples": []}

    w = weights.values

    # 全向量化: 一次生成所有起始索引
    n_blocks = horizon // block
    starts_all = rng.randint(0, n_days - block, size=(n_sim, n_blocks))
    offsets = np.arange(block)
    all_idxs = starts_all[:, :, None] + offsets[None, None, :]
    all_idxs = all_idxs.reshape(n_sim, -1)[:, :horizon]
    sim_arr = arr[all_idxs]
    port_rets = (sim_arr * w[None, None, :]).sum(axis=2)
    samples_arr = np.prod(1 + port_rets, axis=1) - 1

    qs = np.percentile(samples_arr, [5, 25, 50, 75, 95])
    return {
        "p05": qs[0], "p25": qs[1], "p50": qs[2],
        "p75": qs[3], "p95": qs[4],
        "ann_median": (1 + qs[2]) ** (1 / 5) - 1,
        "loss_prob": (samples_arr < 0).mean(),
        "samples": samples_arr.tolist(),
    }
