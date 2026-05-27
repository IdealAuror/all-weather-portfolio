"""主流程编排 - 从数据到报告的 6 步流水线。

每步独立，可单独调用；run_full_pipeline 是默认编排。
"""
import time
import pandas as pd
from .data import load_panel
from .portfolios import get_weights
from .backtest import backtest, backtest_iv
from .stats import (
    perf_metrics, yearly_returns, event_returns,
    bucket_risk_contribution, regime_returns, rolling_stats,
    block_bootstrap,
)
from .config import (
    CASH_TIERS, STRESS_EVENTS,
    RISK_PARITY_WINDOW, RISK_PARITY_MAX_WEIGHT, RISK_PARITY_MIN_WEIGHT,
    V3C_ASSETS, BUCKET_GROUPS,
)

V3B_ASSETS = [a for assets in BUCKET_GROUPS.values() for a in assets]
from . import reports


def step_1_load_data():
    """Step 1: 加载历史数据（9 资产）。"""
    print("\n" + "─" * 60)
    print("Step 1/6: 加载历史数据")
    print("─" * 60)
    t0 = time.time()
    panel = load_panel()
    rets = panel.pct_change().dropna()
    print(f"  ok 数据期间: {panel.index.min().date()} ~ {panel.index.max().date()}")
    print(f"  ok 资产数: {panel.shape[1]}, 交易日数: {len(panel)}")
    print(f"  ok 用时: {time.time()-t0:.2f}s")
    return panel, rets


def step_2_run_backtests(rets):
    """Step 2: V3c + V3-B × 三档现金 = 9 回测。"""
    print("\n" + "─" * 60)
    print("Step 2/6: 跑组合回测")
    print("─" * 60)
    t0 = time.time()
    weights = get_weights()
    nv_results = {}
    n_rebal_total = 0

    # --- V3c: 逆波动率加权（60d，6 资产精简）+ nonferr 趋势过滤 + 抄底 ---
    for tier_label, c in CASH_TIERS:
        nv, n = backtest_iv(rets, cash_ratio=c, iv_window=60, max_w=0.30, min_w=0.03,
                            nonferr_trend_window=60, assets=V3C_ASSETS)
        nv_results[("V3c 多元", tier_label)] = nv
        n_rebal_total += n


    # --- 方案 B: 分层风险平价（20d）+ nonferr 趋势过滤 ---
    from .strategy_b import backtest_b
    for tier_label, c in CASH_TIERS:
        nv, n = backtest_b(rets[V3B_ASSETS], cash_ratio=c, rp_window=20,
                            nonferr_control="trend_filter",
                            nonferr_trend_window=75)
        nv_results[("V3-B 风险平价(20d)", tier_label)] = nv
        n_rebal_total += n

    # --- 方案 B 增强: 逆波动率 + nonferr 趋势过滤 ---
    for tier_label, c in CASH_TIERS:
        nv, n = backtest_b(rets[V3B_ASSETS], cash_ratio=c, rp_window=20,
                            max_w=0.25,
                            nonferr_control="trend_filter",
                            nonferr_trend_window=75,
                            weighting_method="inverse_vol")
        nv_results[("V3-B 保守增强(20d)", tier_label)] = nv
        n_rebal_total += n

    total = len(nv_results)
    print(f"  ok 完成 {total} 个回测")
    print(f"  ok 总调仓次数: {n_rebal_total}")
    print(f"  ok 用时: {time.time()-t0:.2f}s")
    return weights, nv_results


def step_3_compute_metrics(nv_results, weights, rets):
    """Step 3: 计算所有衍生指标。"""
    print("\n" + "─" * 60)
    print("Step 3/6: 计算衍生指标")
    print("─" * 60)
    t0 = time.time()
    perf = {key: perf_metrics(nv) for key, nv in nv_results.items()}

    yearly = {}
    rc = {}
    regime = {}
    events = {}
    rolling = {}

    for p in weights:
        key = (p, "100% RP")
        if key not in nv_results:
            continue
        rets_for_p = rets[list(weights[p].index)]
        yearly[p] = yearly_returns(nv_results[key])
        rc[p] = bucket_risk_contribution(weights[p], rets_for_p)
        regime[p] = regime_returns(nv_results[key], rets)
        events[p] = event_returns(nv_results[key], STRESS_EVENTS)
        rolling[p] = rolling_stats(nv_results[key])

    # V3c / V3-B 无固定权重，跳过风险贡献分解
    for (p, tier), nv_s in nv_results.items():
        if ("V3-B" in p or "V3c" in p) and tier == "100% RP":
            yearly[p] = yearly_returns(nv_s)
            regime[p] = regime_returns(nv_s, rets)
            events[p] = event_returns(nv_s, STRESS_EVENTS)
            rolling[p] = rolling_stats(nv_s)

    print(f"  ok 用时: {time.time()-t0:.2f}s")
    return {
        "perf": perf, "yearly": yearly, "risk_contrib": rc,
        "regime": regime, "events": events, "rolling": rolling,
    }


def step_4_bootstrap(weights, rets, nv_results=None):
    """Step 4: Block Bootstrap 蒙特卡洛模拟。

    固定权重策略直接用；V3-B 用最近窗口逆波动率权重作代理。
    """
    print("\n" + "─" * 60)
    print("Step 4/6: Block Bootstrap 蒙特卡洛（1000 次 × 5 年）")
    print("─" * 60)
    t0 = time.time()

    boot = {}
    for p, w in weights.items():
        rets_for_p = rets[list(w.index)]
        boot[p] = block_bootstrap(w, rets_for_p)

    # V3c / V3-B: 用最近窗口权重作 Bootstrap 代理
    from .risk import hierarchical_rp_weights, inverse_vol_weights
    from .config import BUCKET_GROUPS as BOOT_BG
    rp_buckets_boot = {k: list(v) for k, v in BOOT_BG.items()}
    for (portfolio, tier), _nv in (nv_results or {}).items():
        if ("V3-B" in portfolio or "V3c" in portfolio) and tier == "100% RP":
            boot_rets = rets
            if "保守增强" in portfolio:
                proxy_w = inverse_vol_weights(
                    boot_rets[V3B_ASSETS].tail(20), window=20, max_w=0.25, min_w=RISK_PARITY_MIN_WEIGHT)
            elif "V3c" in portfolio:
                proxy_w = inverse_vol_weights(
                    boot_rets[V3C_ASSETS].tail(60), window=60, max_w=0.30, min_w=0.03)
            else:
                proxy_w = hierarchical_rp_weights(
                    boot_rets[V3B_ASSETS].tail(20), rp_buckets_boot, 20,
                    RISK_PARITY_MAX_WEIGHT, RISK_PARITY_MIN_WEIGHT,
                    bucket_method="equal",
                )
            rets_for_p = rets[list(proxy_w.index)]
            boot[portfolio] = block_bootstrap(proxy_w, rets_for_p)

    print(f"  ok 用时: {time.time()-t0:.2f}s")
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


def step_6_save_outputs(nv_results, metrics, weights, boot=None,
                         excel: bool = True, markdown: bool = True):
    """Step 6: 保存净值曲线 / 汇总 JSON / 权重 CSV / Excel / Markdown。

    excel 和 markdown 都需要 boot（蒙特卡洛结果）。如果只想跑基础三件套，
    传 boot=None 并把两个开关关掉即可。
    """
    print("\n" + "─" * 60)
    print("Step 6/6: 保存结果文件")
    print("─" * 60)
    t0 = time.time()
    p1 = reports.save_nv_curves(nv_results)
    p2 = reports.save_summary_json(metrics["perf"])
    p3 = reports.save_weights_csv(weights)
    print(f"  ok {p1.name}")
    print(f"  ok {p2.name}")
    print(f"  ok {p3.name}")

    if (excel or markdown) and boot is None:
        print("  [WARN] boot 结果缺失，跳过 Excel/Markdown 综合报告")
        excel = markdown = False

    common_args = dict(
        nv_results=nv_results,
        perf_results=metrics["perf"],
        yearly_results=metrics["yearly"],
        rc_results=metrics["risk_contrib"],
        regime_results=metrics["regime"],
        event_results=metrics["events"],
        rolling_results=metrics["rolling"],
        boot_results=boot,
        weights_dict=weights,
    )

    if excel:
        try:
            from .excel_export import save_excel_report
            p4 = save_excel_report(**common_args)
            print(f"  ok {p4.name}（Excel 多 sheet 综合报告）")
        except ImportError as e:
            print(f"  [WARN] 跳过 Excel：{e}（请 pip install openpyxl）")
    if markdown:
        from .markdown_report import save_markdown_report
        p5 = save_markdown_report(**common_args)
        print(f"  ok {p5.name}（Markdown 综合报告）")

    print(f"  ok 输出目录: {p1.parent}")
    print(f"  ok 用时: {time.time()-t0:.2f}s")


def run_full_pipeline(excel: bool = True, markdown: bool = True):
    """跑完整流程：6 步串联。

    excel/markdown 控制是否在 step6 写综合报告（默认全开）。
    """
    overall = time.time()
    print("\n" + "=" * 60)
    print("  桥水全天候策略 · 中国版回测")
    print("=" * 60)

    panel, rets = step_1_load_data()
    weights, nv_results = step_2_run_backtests(rets)
    metrics = step_3_compute_metrics(nv_results, weights, rets)
    boot = step_4_bootstrap(weights, rets, nv_results=nv_results)
    step_5_print_reports(metrics, boot, weights)
    step_6_save_outputs(nv_results, metrics, weights, boot=boot,
                         excel=excel, markdown=markdown)

    print("\n" + "=" * 60)
    print(f"  完成！总耗时 {time.time()-overall:.1f}s")
    print("=" * 60)
