"""主流程编排 - 从数据到报告的 6 步流水线。

每步独立，可单独调用；run_full_pipeline 是默认编排。
"""
import time
import pandas as pd
from .data import load_panel
from .portfolios import get_weights
from .backtest import backtest
from .stats import (
    perf_metrics, yearly_returns, event_returns,
    bucket_risk_contribution, regime_returns, rolling_stats,
    block_bootstrap,
)
from .config import CASH_TIERS, STRESS_EVENTS
from . import reports


def step_1_load_data():
    """Step 1: 加载历史数据。"""
    print("\n" + "─" * 60)
    print("Step 1/6: 加载历史数据")
    print("─" * 60)
    t0 = time.time()
    panel = load_panel()
    rets = panel.pct_change().dropna()
    print(f"  ✓ 数据期间: {panel.index.min().date()} ~ {panel.index.max().date()}")
    print(f"  ✓ 资产数: {panel.shape[1]}, 交易日数: {len(panel)}")
    print(f"  ✓ 用时: {time.time()-t0:.2f}s")
    return panel, rets


def step_2_run_backtests(rets):
    """Step 2: 三策略 × 三档现金共 9 组回测。"""
    print("\n" + "─" * 60)
    print("Step 2/6: 跑 9 个组合回测（3 策略 × 3 现金档）")
    print("─" * 60)
    t0 = time.time()
    weights = get_weights()
    nv_results = {}
    n_rebal_total = 0
    for port, w in weights.items():
        for tier_label, c in CASH_TIERS:
            nv, n = backtest(w, rets, cash_ratio=c)
            nv_results[(port, tier_label)] = nv
            n_rebal_total += n
    print(f"  ✓ 完成 {len(nv_results)} 个回测")
    print(f"  ✓ 总调仓次数: {n_rebal_total}")
    print(f"  ✓ 用时: {time.time()-t0:.2f}s")
    return weights, nv_results


def step_3_compute_metrics(nv_results, weights, rets):
    """Step 3: 计算所有衍生指标。"""
    print("\n" + "─" * 60)
    print("Step 3/6: 计算衍生指标")
    print("─" * 60)
    t0 = time.time()
    perf = {key: perf_metrics(nv) for key, nv in nv_results.items()}
    yearly = {p: yearly_returns(nv_results[(p, "100% RP")]) for p in weights}
    rc = {p: bucket_risk_contribution(weights[p], rets) for p in weights}
    regime = {p: regime_returns(nv_results[(p, "100% RP")], rets) for p in weights}
    events = {p: event_returns(nv_results[(p, "100% RP")], STRESS_EVENTS)
              for p in weights}
    rolling = {p: rolling_stats(nv_results[(p, "100% RP")]) for p in weights}
    print(f"  ✓ 用时: {time.time()-t0:.2f}s")
    return {
        "perf": perf, "yearly": yearly, "risk_contrib": rc,
        "regime": regime, "events": events, "rolling": rolling,
    }


def step_4_bootstrap(weights, rets):
    """Step 4: Block Bootstrap 蒙特卡洛模拟。"""
    print("\n" + "─" * 60)
    print("Step 4/6: Block Bootstrap 蒙特卡洛（1000 次 × 5 年）")
    print("─" * 60)
    t0 = time.time()
    boot = {p: block_bootstrap(w, rets) for p, w in weights.items()}
    print(f"  ✓ 用时: {time.time()-t0:.2f}s")
    return boot


def step_5_print_reports(metrics, boot, weights):
    """Step 5: 打印控制台报告。"""
    print("\n" + "─" * 60)
    print("Step 5/6: 输出报告")
    print("─" * 60)
    print()
    reports.print_perf_table(metrics["perf"])
    print()
    reports.print_yearly_table(metrics["yearly"])
    print()
    reports.print_risk_contribution(metrics["risk_contrib"])
    print()
    reports.print_regime_table(metrics["regime"])
    print()
    reports.print_event_table(metrics["events"])
    print()
    reports.print_rolling_table(metrics["rolling"])
    print()
    reports.print_bootstrap_table(boot)
    print()
    reports.print_holdings(weights)
    print()
    reports.print_summary_recommendation()


def step_6_save_outputs(nv_results, metrics, weights):
    """Step 6: 保存净值曲线、汇总 JSON、权重 CSV。"""
    print("\n" + "─" * 60)
    print("Step 6/6: 保存结果文件")
    print("─" * 60)
    t0 = time.time()
    p1 = reports.save_nv_curves(nv_results)
    p2 = reports.save_summary_json(metrics["perf"])
    p3 = reports.save_weights_csv(weights)
    print(f"  ✓ {p1.name}")
    print(f"  ✓ {p2.name}")
    print(f"  ✓ {p3.name}")
    print(f"  ✓ 输出目录: {p1.parent}")
    print(f"  ✓ 用时: {time.time()-t0:.2f}s")


def run_full_pipeline():
    """跑完整流程：6 步串联。"""
    overall = time.time()
    print("\n" + "=" * 60)
    print("  桥水全天候策略 · 中国版回测")
    print("=" * 60)

    panel, rets = step_1_load_data()
    weights, nv_results = step_2_run_backtests(rets)
    metrics = step_3_compute_metrics(nv_results, weights, rets)
    boot = step_4_bootstrap(weights, rets)
    step_5_print_reports(metrics, boot, weights)
    step_6_save_outputs(nv_results, metrics, weights)

    print("\n" + "=" * 60)
    print(f"  ✅ 完成！总耗时 {time.time()-overall:.1f}s")
    print("=" * 60)
