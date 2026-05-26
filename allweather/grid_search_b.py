"""V3-B 参数网格搜索 — 36 组合 × 3 现金档，找 Pareto 最优。"""
import itertools
import time
import pandas as pd
from .data import load_panel
from .strategy_b import backtest_b
from .stats import perf_metrics
from .config import CASH_TIERS, RISK_PARITY_MIN_WEIGHT


def run_grid_search():
    """Run full grid search and print ranked results + Pareto frontier."""
    # Parameter grid
    windows = [30, 60, 90, 120, 180, 252]
    max_ws = [0.20, 0.25, 0.30]
    bucket_methods = ["equal", "risk_parity"]

    print("=" * 80)
    print("  V3-B 参数网格搜索")
    print("=" * 80)
    print(f"  窗口: {windows}")
    print(f"  max_w: {max_ws}")
    print(f"  bucket_method: {bucket_methods}")
    print(f"  总组合: {len(windows) * len(max_ws) * len(bucket_methods)} × 3 现金档 = 108 回测")
    print()

    # Load data
    t0 = time.time()
    panel = load_panel()
    rets = panel.pct_change().dropna()
    print(f"  数据加载: {time.time()-t0:.1f}s, {len(rets)} 交易日")
    print()

    # Run all combinations (100% RP first)
    results = []
    t0 = time.time()
    for win, max_w, bm in itertools.product(windows, max_ws, bucket_methods):
        nv, n_rebal = backtest_b(
            rets, cash_ratio=0.0, rp_window=win,
            bucket_method=bm, max_w=max_w, min_w=RISK_PARITY_MIN_WEIGHT,
        )
        m = perf_metrics(nv)
        results.append({
            "window": win, "max_w": max_w, "bucket_method": bm,
            "cagr": m["cagr"], "vol": m["vol"], "mdd": m["mdd"],
            "sharpe": m["sharpe"], "calmar": m["calmar"],
            "cum_return": m["cum_return"], "n_rebal": n_rebal,
            "nv": nv,
        })
    elapsed = time.time() - t0
    print(f"  36 组合回测完成: {elapsed:.1f}s")
    print()

    # --- Top 10 by MDD (shallowest first) ---
    sorted_by_mdd = sorted(results, key=lambda r: r["mdd"], reverse=True)
    print("─" * 80)
    print("  Top 10 — 回撤最浅 (100% RP)")
    print("─" * 80)
    print(f"  {'#':<3} {'窗口':<6} {'max_w':<6} {'桶方法':<12} {'CAGR':<8} {'MDD':<9} {'Sharpe':<7} {'Calmar':<7} {'调仓':<5}")
    print("  " + "-" * 70)
    for i, r in enumerate(sorted_by_mdd[:10], 1):
        bm_label = "等权" if r["bucket_method"] == "equal" else "风险平价"
        print(f"  {i:<3} {r['window']:<6} {r['max_w']:<6.2f} {bm_label:<12} "
              f"{r['cagr']*100:>6.2f}%  {r['mdd']*100:>7.2f}%  "
              f"{r['sharpe']:>5.2f}   {r['calmar']:>5.2f}   {r['n_rebal']:<5}")
    print()

    # --- Pareto frontier (MDD vs CAGR) ---
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
    print("  Pareto 前沿 (MDD vs CAGR, 100% RP)")
    print("─" * 80)
    print(f"  {'窗口':<6} {'max_w':<6} {'桶方法':<12} {'CAGR':<8} {'MDD':<9} {'Sharpe':<7} {'Calmar':<7}")
    print("  " + "-" * 65)
    for r in pareto:
        bm_label = "等权" if r["bucket_method"] == "equal" else "风险平价"
        print(f"  {r['window']:<6} {r['max_w']:<6.2f} {bm_label:<12} "
              f"{r['cagr']*100:>6.2f}%  {r['mdd']*100:>7.2f}%  "
              f"{r['sharpe']:>5.2f}   {r['calmar']:>5.2f}")
    print()

    # --- Pareto winners: full 3-tier ---
    print("─" * 80)
    print("  Pareto 最优组合 — 完整三档指标")
    print("─" * 80)
    for r in pareto:
        bm_label = "等权" if r["bucket_method"] == "equal" else "风险平价"
        print(f"\n  >> 窗口={r['window']}d, max_w={r['max_w']}, 桶方法={bm_label}")
        print(f"  {'档位':<10} {'CAGR':<8} {'波动':<8} {'回撤':<9} {'Sharpe':<7} {'Calmar':<7} {'累计':<9}")
        print("  " + "-" * 60)
        for tier_label, c in CASH_TIERS:
            nv, _ = backtest_b(
                rets, cash_ratio=c, rp_window=r["window"],
                bucket_method=r["bucket_method"], max_w=r["max_w"],
                min_w=RISK_PARITY_MIN_WEIGHT,
            )
            m = perf_metrics(nv)
            print(f"  {tier_label:<10} {m['cagr']*100:>6.2f}%  {m['vol']*100:>6.2f}%  "
                  f"{m['mdd']*100:>7.2f}%  {m['sharpe']:>5.2f}   {m['calmar']:>5.2f}   "
                  f"{m['cum_return']*100:>+7.2f}%")
    print()

    # --- Best of each category ---
    print("─" * 80)
    print("  各类别最优 (100% RP)")
    print("─" * 80)
    best_mdd = max(results, key=lambda r: r["mdd"])
    best_cagr = max(results, key=lambda r: r["cagr"])
    best_sharpe = max(results, key=lambda r: r["sharpe"])
    for label, r in [("回撤最浅", best_mdd), ("CAGR 最高", best_cagr), ("Sharpe 最高", best_sharpe)]:
        bm_label = "等权" if r["bucket_method"] == "equal" else "风险平价"
        print(f"  {label}: 窗口={r['window']}d, max_w={r['max_w']}, 桶={bm_label}  "
              f"CAGR={r['cagr']*100:.2f}%  MDD={r['mdd']*100:.2f}%  Sharpe={r['sharpe']:.2f}")
    print()

    # Compare to baseline
    print("─" * 80)
    print("  基线对比 (60d, max_w=0.25, 等权)")
    print("─" * 80)
    baseline = next(r for r in results if r["window"] == 60 and r["max_w"] == 0.25 and r["bucket_method"] == "equal")
    print(f"  基线: CAGR={baseline['cagr']*100:.2f}%  MDD={baseline['mdd']*100:.2f}%  "
          f"Sharpe={baseline['sharpe']:.2f}  Calmar={baseline['calmar']:.2f}")

    print(f"\n  总耗时: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    run_grid_search()
