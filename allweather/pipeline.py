"""主流程编排 - 从数据到报告的 6 步流水线。

每步独立，可单独调用；run_full_pipeline 是默认编排。
"""
import time
import pandas as pd
from .data import load_panel

from .backtest import backtest_iv
from .stats import (
    perf_metrics, yearly_returns, event_returns,
    regime_returns, rolling_stats,
    block_bootstrap, d_significance,
    weight_stability, risk_contribution_time_varying,
)
from .config import (
    CASH_TIERS, STRESS_EVENTS, OUTPUT_DIR,
    RISK_PARITY_WINDOW, RISK_PARITY_MAX_WEIGHT, RISK_PARITY_MIN_WEIGHT,
    V3C_ASSETS, BUCKETS, BUCKET_GROUPS,
    SP500_TREND_WINDOW, GOLD_DIP_THRESHOLD,
)

V3B_ASSETS = [a for assets in BUCKET_GROUPS.values() for a in assets]
V3B_RP_BUCKETS = {
    "增长↑":   ["hs300", "us_sp500"],
    "收益垫":  ["credit"],
    "增长↓":   ["bond_30y"],
    "通胀↑":   ["gold", "nonferr"],
}
V3B_RP_ASSETS = [a for assets in V3B_RP_BUCKETS.values() for a in assets]
from . import reports
DOCS_DIR = OUTPUT_DIR.parent / "docs"
from .update_docs import save_docs_json, patch_index_html


def step_1_load_data():
    """Step 1: 加载历史数据（8 活跃资产 + wti 备选）。"""
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
    """Step 2: 3 策略 × 3 现金档 = 9 回测（+3 动态现金 = 12）。"""
    print("\n" + "─" * 60)
    print("Step 2/6: 跑组合回测")
    print("─" * 60)
    t0 = time.time()
    nv_results = {}
    weight_history = {}
    signal_logs = {}
    n_rebal_total = 0

    # --- V3c: 逆波动率加权（60d，6 资产）+ nonferr 趋势过滤 ---
    for tier_label, c in CASH_TIERS:
        track = (tier_label == "100% RP")
        result = backtest_iv(rets, cash_ratio=c, iv_window=60, max_w=0.30, min_w=0.03,
                            nonferr_trend_window=75, assets=V3C_ASSETS,
                            gold_dip_threshold=GOLD_DIP_THRESHOLD, gold_dip_cap=0.20,
                            hs300_value_dip=True,
                            track_weights=track,
                            track_signals=track,
                            signal_label="V3c 多元")
        if track:
            nv, n, wh, sl = result
            weight_history["V3c 多元"] = wh
            signal_logs["V3c 多元"] = sl
        else:
            nv, n = result
        nv_results[("V3c 多元", tier_label)] = nv
        n_rebal_total += n

    nv, n = backtest_iv(rets, cash_ratio=0.0, iv_window=60, max_w=0.30, min_w=0.03,
                        nonferr_trend_window=75, assets=V3C_ASSETS,
                        gold_dip_threshold=GOLD_DIP_THRESHOLD, gold_dip_cap=0.20,
                        hs300_value_dip=True,
                        dynamic_cash=True)
    nv_results[("V3c 多元", "动态")] = nv
    n_rebal_total += n

    # --- 方案 B: 分层风险平价（20d, 4 桶）+ nonferr 趋势过滤 + gold 趋势过滤 ---
    from .strategy_b import backtest_b
    for tier_label, c in CASH_TIERS:
        track = (tier_label == "100% RP")
        result = backtest_b(rets[V3B_RP_ASSETS], cash_ratio=c, rp_window=20,
                            rp_buckets=V3B_RP_BUCKETS,
                            nonferr_control="trend_filter",
                            nonferr_trend_window=75,
                            gold_trend_filter=True,
                            gold_trend_window=75,
                            equity_trend_assets=["us_sp500"],
                            equity_trend_window=SP500_TREND_WINDOW,
                            hs300_value_dip=True,
                            track_weights=track,
                            track_signals=track,
                            signal_label="V3-B 风险平价")
        if track:
            nv, n, wh, sl = result
            weight_history["V3-B 风险平价(20d)"] = wh
            signal_logs["V3-B 风险平价"] = sl
        else:
            nv, n = result
        nv_results[("V3-B 风险平价(20d)", tier_label)] = nv
        n_rebal_total += n

    nv, n = backtest_b(rets[V3B_RP_ASSETS], cash_ratio=0.0, rp_window=20,
                        rp_buckets=V3B_RP_BUCKETS,
                        nonferr_control="trend_filter",
                        nonferr_trend_window=75,
                        gold_trend_filter=True,
                        gold_trend_window=75,
                        equity_trend_assets=["us_sp500"],
                        equity_trend_window=SP500_TREND_WINDOW,
                        hs300_value_dip=True,
                        dynamic_cash=True)
    nv_results[("V3-B 风险平价(20d)", "动态")] = nv
    n_rebal_total += n

    # --- 方案 B 增强: 逆波動率 + nonferr 趋势过滤 ---
    for tier_label, c in CASH_TIERS:
        track = (tier_label == "100% RP")
        result = backtest_b(rets[V3B_ASSETS], cash_ratio=c, rp_window=20,
                            max_w=0.25,
                            nonferr_control="trend_filter",
                            nonferr_trend_window=75,
                            weighting_method="inverse_vol",
                            gold_dip_threshold=GOLD_DIP_THRESHOLD, gold_dip_cap=0.20,
                            hs300_value_dip=True,
                            track_weights=track,
                            track_signals=track,
                            signal_label="V3-B 保守增强")
        if track:
            nv, n, wh, sl = result
            weight_history["V3-B 保守增强(20d)"] = wh
            signal_logs["V3-B 保守增强"] = sl
        else:
            nv, n = result
        nv_results[("V3-B 保守增强(20d)", tier_label)] = nv
        n_rebal_total += n

    nv, n = backtest_b(rets[V3B_ASSETS], cash_ratio=0.0, rp_window=20,
                        max_w=0.25,
                        nonferr_control="trend_filter",
                        nonferr_trend_window=75,
                        weighting_method="inverse_vol",
                        gold_dip_threshold=GOLD_DIP_THRESHOLD, gold_dip_cap=0.20,
                        hs300_value_dip=True,
                        dynamic_cash=True)
    nv_results[("V3-B 保守增强(20d)", "动态")] = nv
    n_rebal_total += n

    total = len(nv_results)
    print(f"  ok 完成 {total} 个回测")
    print(f"  ok 总调仓次数: {n_rebal_total}")
    print(f"  ok 用时: {time.time()-t0:.2f}s")
    return nv_results, weight_history, signal_logs


def step_3_compute_metrics(nv_results, rets, weight_history=None, signal_logs=None):
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
    ws = {}
    rc_tv = {}

    # V3c / V3-B 无固定权重，跳过风险贡献分解
    for (p, tier), nv_s in nv_results.items():
        if ("V3-B" in p or "V3c" in p) and tier == "100% RP":
            yearly[p] = yearly_returns(nv_s)
            regime[p] = regime_returns(nv_s, rets)
            events[p] = event_returns(nv_s, STRESS_EVENTS)
            rolling[p] = rolling_stats(nv_s)

    # 权重稳定性（使用 weight_history 中的动态权重）
    if weight_history:
        for p, wh in weight_history.items():
            ws[p] = weight_stability(wh)
            rc_tv[p] = risk_contribution_time_varying(wh, rets, BUCKETS)

    print(f"  ok 用时: {time.time()-t0:.2f}s")
    d_sig = {}
    for (p, tier), nv_s in nv_results.items():
        if tier == "100% RP":
            d_sig[p] = d_significance(nv_s)
    return {
        "perf": perf, "yearly": yearly, "risk_contrib": rc,
        "regime": regime, "events": events, "rolling": rolling,
        "d_sig": d_sig,
        "weight_stability": ws,
        "risk_contrib_tv": rc_tv,
    }


def step_4_bootstrap(rets, nv_results=None):
    """Step 4: Block Bootstrap 蒙特卡洛模拟。

    V3-B 用最近窗口逆波动率权重作动态权重代理。
    """
    print("\n" + "─" * 60)
    print("Step 4/6: Block Bootstrap 蒙特卡洛（1000 次 × 5 年）")
    print("─" * 60)
    t0 = time.time()

    boot = {}

    # V3c / V3-B: 用最近窗口权重作 Bootstrap 代理
    from .risk import hierarchical_rp_weights, inverse_vol_weights
    rp_buckets_boot_rp = {k: list(v) for k, v in V3B_RP_BUCKETS.items()}
    for (portfolio, tier), _nv in (nv_results or {}).items():
        if ("V3-B" in portfolio or "V3c" in portfolio) and tier == "100% RP":
            boot_rets = rets
            if "保守增强" in portfolio:
                proxy_w = inverse_vol_weights(
                    boot_rets[V3B_ASSETS].tail(20), window=20, max_w=0.25, min_w=RISK_PARITY_MIN_WEIGHT)
            elif "风险平价桶" in portfolio:
                proxy_w = hierarchical_rp_weights(
                    boot_rets[V3B_RP_ASSETS].tail(20), rp_buckets_boot_rp, 20,
                    RISK_PARITY_MAX_WEIGHT, RISK_PARITY_MIN_WEIGHT,
                    bucket_method="risk_parity",
                )
            elif "V3c" in portfolio:
                proxy_w = inverse_vol_weights(
                    boot_rets[V3C_ASSETS].tail(60), window=60, max_w=0.30, min_w=0.03)
            else:
                proxy_w = hierarchical_rp_weights(
                    boot_rets[V3B_RP_ASSETS].tail(20), rp_buckets_boot_rp, 20,
                    RISK_PARITY_MAX_WEIGHT, RISK_PARITY_MIN_WEIGHT,
                    bucket_method="equal",
                )
            rets_for_p = rets[list(proxy_w.index)]
            boot[portfolio] = block_bootstrap(proxy_w, rets_for_p)

    # 沪深300满仓基准
    hs300_w = pd.Series([1.0], index=["hs300"])
    boot["沪深300"] = block_bootstrap(hs300_w, rets[["hs300"]])

    print(f"  ok 用时: {time.time()-t0:.2f}s")
    return boot


def step_5_print_reports(metrics, boot, weight_history=None, signal_logs=None):
    """Step 5: 打印控制台报告。"""
    print("\n" + "─" * 60)
    print("Step 5/6: 输出报告")
    print("─" * 60)
    print()
    reports.print_perf_table(metrics["perf"])
    print()
    reports.print_d_significance(metrics.get("d_sig", {}))
    print()
    reports.print_yearly_table(metrics["yearly"])
    print()
    reports.print_risk_contribution(metrics["risk_contrib"])
    print()
    reports.print_risk_contribution(metrics.get("risk_contrib_tv", {}))
    print()
    reports.print_weight_stability_table(metrics.get("weight_stability", {}))
    print()
    if signal_logs:
        reports.print_signal_summary(signal_logs)
        print()
    reports.print_regime_table(metrics["regime"])
    print()
    reports.print_event_table(metrics["events"])
    print()
    reports.print_rolling_table(metrics["rolling"])
    print()
    reports.print_bootstrap_table(boot)
    print()
    reports.print_summary_recommendation()


def step_6_save_outputs(nv_results, metrics, boot=None,
                         excel: bool = True, markdown: bool = True,
                         weight_history: dict = None,
                         signal_logs: dict = None,
                         benchmark_nv: pd.Series = None):
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
    print(f"  ok {p1.name}")
    print(f"  ok {p2.name}")

    if signal_logs:
        all_logs = []
        for label, sl in signal_logs.items():
            sl_copy = sl.copy()
            sl_copy['label'] = label
            all_logs.append(sl_copy)
        combined = pd.concat(all_logs, ignore_index=True)
        sl_path = OUTPUT_DIR / "signal_log.csv"
        combined.to_csv(sl_path, index=False, encoding="utf-8-sig")
        print(f"  ok {sl_path.name}（信号触发日志，{len(combined)} 条）")

    if (excel or markdown) and boot is None:
        print("  [WARN] boot 结果缺失，跳过 Excel/Markdown 综合报告")
        excel = markdown = False

    common_args = dict(
        nv_results=nv_results,
        perf_results=metrics["perf"],
        yearly_results=metrics["yearly"],
        rc_results=metrics.get("risk_contrib_tv", metrics["risk_contrib"]),
        regime_results=metrics["regime"],
        event_results=metrics["events"],
        rolling_results=metrics["rolling"],
        boot_results=boot,
        weights_dict={},
        ws_results=metrics.get("weight_stability"),
        rc_tv_results=metrics.get("risk_contrib_tv"),
        signal_logs=signal_logs,
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

    # --- 权重历史 & 图表 ---
    if weight_history:
        from .charts import (
            plot_nav_and_dd, plot_all_tiers_nv,
            plot_rolling_returns, plot_monthly_returns_comparison,
            plot_yearly_returns, plot_weight_stack,
            plot_bootstrap_distribution,
            plot_yearly_bar,
        )
        for p, wh in weight_history.items():
            wh_path = OUTPUT_DIR / f"weight_history_{p.replace(' ', '_').replace('(', '').replace(')', '')}.csv"
            wh.to_csv(wh_path, encoding="utf-8-sig")
            print(f"  ok {wh_path.name}（{p} 权重历史）")

        plot_nav_and_dd(nv_results)                              # 无基准
        plot_nav_and_dd(nv_results, benchmark_nv=benchmark_nv)   # 带沪深300
        plot_all_tiers_nv(nv_results)
        plot_rolling_returns(metrics)
        plot_monthly_returns_comparison(nv_results)
        plot_yearly_returns(metrics, nv_results=nv_results)
        plot_weight_stack(weight_history)
        plot_bootstrap_distribution(boot, perf_results=metrics["perf"])
        plot_yearly_bar(metrics, nv_results=nv_results)
        print(f"  ok charts/（8 张图表）")

    # --- 同步 docs/data.json + 图表到 docs/charts/ ---
    save_docs_json(
        perf_results=metrics["perf"],
        yearly_results=metrics["yearly"],
        event_results=metrics["events"],
        regime_results=metrics["regime"],
        rolling_results=metrics["rolling"],
        boot_results=boot,
        weight_history=weight_history or {},
    )
    patch_index_html()

    import shutil
    chart_src = OUTPUT_DIR / "charts"
    chart_dst = DOCS_DIR / "charts"
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    chart_dst.mkdir(parents=True, exist_ok=True)
    for f in chart_src.glob("*.png"):
        shutil.copy2(f, chart_dst / f.name)
    print(f"  ok docs/data.json + docs/charts/（GitHub Pages 同步）")

    print(f"  ok 输出目录: {p1.parent}")
    print(f"  ok 用时: {time.time()-t0:.2f}s")


def run_full_pipeline(excel: bool = True, markdown: bool = True,
                       note: str = ""):
    """跑完整流程：6 步串联。

    excel/markdown 控制是否在 step6 写综合报告（默认全开）。
    note 将写入实验日志（experiments.jsonl）。
    """
    overall = time.time()
    print("\n" + "=" * 60)
    print("  桥水全天候策略 · 中国版回测")
    print("=" * 60)

    panel, rets = step_1_load_data()
    nv_results, weight_history, signal_logs = step_2_run_backtests(rets)
    metrics = step_3_compute_metrics(nv_results, rets,
                                     weight_history=weight_history,
                                     signal_logs=signal_logs)
    boot = step_4_bootstrap(rets, nv_results=nv_results)
    step_5_print_reports(metrics, boot,
                         weight_history=weight_history,
                         signal_logs=signal_logs)
    hs300_nv = panel["hs300"] / panel["hs300"].iloc[0]
    step_6_save_outputs(nv_results, metrics, boot=boot,
                         excel=excel, markdown=markdown,
                         weight_history=weight_history,
                         signal_logs=signal_logs,
                         benchmark_nv=hs300_nv)

    # 追加实验日志
    from .experiment_log import save_run
    log_path = save_run(metrics["perf"], metrics, conclusion=note)
    print(f"  ok {log_path.name}（实验日志）")

    print("\n" + "=" * 60)
    print(f"  完成！总耗时 {time.time()-overall:.1f}s")
    print("=" * 60)
