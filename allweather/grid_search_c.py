"""方案 C 参数网格搜索 — 12 组合 × 100% 总仓位，找最优触发/补仓/退出参数。"""
import itertools
import time
from .data import load_panel
from .strategy_c import backtest_c
from .stats import perf_metrics


def run_grid_search():
    """Grid search over trigger/deploy/exit thresholds."""
    trigger_thresholds = [-0.10, -0.15, -0.20]
    deploy_pcts = [0.03, 0.05]
    exit_thresholds = [0.10, 0.15]

    print("=" * 80)
    print("  方案 C 参数网格搜索 — 动态现金补仓")
    print("=" * 80)
    print(f"  触发阈值: {[f'{t*100:.0f}%' for t in trigger_thresholds]}")
    print(f"  单次补仓: {[f'{p*100:.0f}%' for p in deploy_pcts]}")
    print(f"  退出阈值: {[f'{t*100:.0f}%' for t in exit_thresholds]}")
    print(f"  总组合: {len(trigger_thresholds) * len(deploy_pcts) * len(exit_thresholds)}")
    print(f"  固定参数: core_ratio=70%, window=90d, max_w=0.30, cooldown=60d")
    print()

    # Load data
    t0 = time.time()
    panel = load_panel()
    rets = panel.pct_change().dropna()
    print(f"  数据: {len(rets)} 交易日, {panel.shape[1]} 资产")
    print()

    # Run all combinations
    results = []
    for trig, dep_pct, exit_pct in itertools.product(
        trigger_thresholds, deploy_pcts, exit_thresholds
    ):
        r = backtest_c(
            rets,
            trigger_threshold=trig,
            deploy_pct=dep_pct,
            exit_threshold=exit_pct,
        )
        m = perf_metrics(r["nv"])
        results.append({
            "trigger": trig,
            "deploy_pct": dep_pct,
            "exit_pct": exit_pct,
            "cagr": m["cagr"],
            "vol": m["vol"],
            "mdd": m["mdd"],
            "sharpe": m["sharpe"],
            "calmar": m["calmar"],
            "cum_return": m["cum_return"],
            "n_deploy": r["n_deploy"],
            "n_exit": r["n_exit"],
            "nv": r["nv"],
        })

    elapsed = time.time() - t0
    print(f"  12 组合回测完成: {elapsed:.1f}s")
    print()

    # --- Top 12 by MDD ---
    sorted_by_mdd = sorted(results, key=lambda r: r["mdd"], reverse=True)
    print("─" * 80)
    print("  Top 12 — 回撤最浅")
    print("─" * 80)
    header = f"  {'#':<3} {'触发':<7} {'补仓%':<7} {'退出%':<7} {'CAGR':<8} {'MDD':<9} {'Sharpe':<7} {'部署':<5} {'退出':<5}"
    print(header)
    print("  " + "-" * 70)
    for i, r in enumerate(sorted_by_mdd, 1):
        print(f"  {i:<3} {r['trigger']*100:>5.0f}%  {r['deploy_pct']*100:>4.0f}%   {r['exit_pct']*100:>4.0f}%   "
              f"{r['cagr']*100:>6.2f}%  {r['mdd']*100:>7.2f}%  "
              f"{r['sharpe']:>5.2f}   {r['n_deploy']:<5} {r['n_exit']:<5}")
    print()

    # --- Pareto frontier ---
    pareto = []
    for r in results:
        dominated = False
        for other in results:
            if (other["mdd"] >= r["mdd"] and other["cagr"] >= r["cagr"]) and \
               (other["mdd"] > r["mdd"] or other["cagr"] > r["cagr"]):
                dominated = True
                break
        if not dominated:
            pareto.append(r)
    pareto.sort(key=lambda r: r["mdd"], reverse=True)

    print("─" * 80)
    print("  Pareto 前沿 (MDD vs CAGR)")
    print("─" * 80)
    for r in pareto:
        print(f"  触发={r['trigger']*100:>4.0f}%  补仓={r['deploy_pct']*100:.0f}%  退出={r['exit_pct']*100:.0f}%  "
              f"CAGR={r['cagr']*100:.2f}%  MDD={r['mdd']*100:.2f}%  "
              f"Sharpe={r['sharpe']:.2f}  部署{r['n_deploy']}次  退出{r['n_exit']}次")
    print()

    # --- Baselines ---
    print("─" * 80)
    print("  对比基线")
    print("─" * 80)
    print(f"  V3-B risk_parity 100% (无现金):  CAGR=5.74%  MDD=-3.55%  Sharpe=1.56")
    print(f"  V3-B equal 100% (当前月度RP):    CAGR=7.27%  MDD=-6.29%  Sharpe=1.14")
    print(f"  V3c 多元 100% (固定权重):        CAGR=7.45%  MDD=-6.71%  Sharpe=1.26")

    # --- Best of each ---
    print()
    print("─" * 80)
    print("  各类别最优")
    print("─" * 80)
    best_mdd = max(results, key=lambda r: r["mdd"])
    best_cagr = max(results, key=lambda r: r["cagr"])
    best_sharpe = max(results, key=lambda r: r["sharpe"])
    for label, r in [("回撤最浅", best_mdd), ("CAGR 最高", best_cagr), ("Sharpe 最高", best_sharpe)]:
        print(f"  {label}: 触发={r['trigger']*100:>4.0f}%  补仓={r['deploy_pct']*100:.0f}%  "
              f"退出={r['exit_pct']*100:.0f}%  "
              f"CAGR={r['cagr']*100:.2f}%  MDD={r['mdd']*100:.2f}%  "
              f"Sharpe={r['sharpe']:.2f}  部署{r['n_deploy']}次")

    print(f"\n  总耗时: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    run_grid_search()
