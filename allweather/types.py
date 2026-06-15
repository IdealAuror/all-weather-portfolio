"""TypedDict 形式化接口契约 — 跨模块返回值类型标注。"""
from __future__ import annotations

from typing import TypedDict

import pandas as pd


class PerfMetrics(TypedDict):
    """perf_metrics() 返回值。"""
    n_years: float
    cum_return: float
    cagr: float
    vol: float
    mdd: float
    sharpe: float
    sharpe_raw: float
    calmar: float
    final_nv: float
    G_real: float
    G_theoretical: float
    geometric_excess_d: float


class RollingStats(TypedDict):
    """rolling_stats() 返回值。"""
    ann_min: float
    ann_med: float
    ann_max: float
    dd_min: float
    neg_year_pct: float
    rolling_ann: pd.Series
    rolling_dd: pd.Series


class DExcessResult(TypedDict):
    """d_significance() 返回值。"""
    d_actual: float
    d_null_mean: float
    d_null_std: float
    ci_95_low: float
    ci_95_high: float
    percentile: float
    significant_05: bool


class BootstrapResult(TypedDict):
    """block_bootstrap() 返回值。"""
    p05: float | None
    p25: float | None
    p50: float | None
    p75: float | None
    p95: float | None
    ann_median: float | None
    loss_prob: float | None
    samples: list[float]


class WeightStability(TypedDict):
    """weight_stability() 返回值。"""
    monthly_turnover_mean: float
    monthly_turnover_max: float
    annual_churn: float
    effective_n_mean: float
    effective_n_min: float
    cost_drag_annual: float
    cost_bp_assumed: int


class RiskContribBucketStats(TypedDict):
    """risk_contribution_time_varying() 每个桶的统计。"""
    mean: float
    std: float
    min: float
    max: float


class RegimeStats(TypedDict):
    """regime_returns() 每个情景的统计。"""
    avg: float
    n: int


class Step3Metrics(TypedDict):
    """step_3_compute_metrics() 返回值。"""
    perf: dict[tuple[str, str], PerfMetrics]
    yearly: dict[str, pd.Series]
    risk_contrib: dict
    regime: dict[str, dict[str, RegimeStats]]
    events: dict[str, dict[str, float]]
    rolling: dict[str, RollingStats]
    d_sig: dict[str, DExcessResult]
    weight_stability: dict[str, WeightStability]
    risk_contrib_tv: dict[str, dict[str, RiskContribBucketStats | int]]
