"""V3-B RP 换手平滑实验 — target_weight_smoothing

对比 alpha：
  1.0 = 无平滑（基准）
  0.7 = 轻度
  0.5 = 中度
  0.3 = 重度

输出：核心指标 + 换手率 + 成本 + 事件期 + 宏观情景
"""
import sys
sys.path.insert(0, ".")
import pandas as pd
from allweather.data import load_panel
from allweather.stats import perf_metrics, event_returns, regime_returns
from allweather.config import STRESS_EVENTS
from allweather.strategy_b import backtest_b

V3B_RP_BUCKETS = {
    "增长↑":   ["hs300", "us_sp500"],
    "收益垫":  ["credit"],
    "增长↓":   ["bond_30y"],
    "通胀↑":   ["gold", "nonferr"],
}
V3B_RP_ASSETS = [a for assets in V3B_RP_BUCKETS.values() for a in assets]

LINE = "=" * 110
print(LINE)
print("  V3-B RP 换手平滑实验 — 100% RP")
print(LINE)

panel = load_panel()
rets = panel.pct_change().dropna()
print(f"  数据: {panel.index.min().date()} ~ {panel.index.max().date()}, {len(panel)} 交易日\n")

configs = [
    ("alpha=1.0 (基准)", 1.0),
    ("alpha=0.7 (轻度)", 0.7),
    ("alpha=0.5 (中度)", 0.5),
    ("alpha=0.3 (重度)", 0.3),
]

results = {}
for label, alpha in configs:
    print(f"  运行: {label} ...")
    nv, n, wh, sl = backtest_b(
        rets[V3B_RP_ASSETS], cash_ratio=0.0, rp_window=20,
        rp_buckets=V3B_RP_BUCKETS,
        nonferr_control="trend_filter", nonferr_trend_window=75,
        gold_trend_filter=True, gold_trend_window=75,
        equity_trend_assets=["us_sp500"], equity_trend_window=120,
        hs300_value_dip=True,
        track_weights=True, track_signals=True, signal_label=label,
        target_weight_smoothing=alpha if alpha < 1.0 else None,
    )
    results[label] = {"nv": nv, "n": n, "wh": wh}

# --- 核心指标 + 换手 ---
print(f"\n{'变体':<24}{'累计收益':>10}{'CAGR':>9}{'波动':>8}{'MDD':>10}{'Sharpe':>8}{'Calmar':>8}"
      f"{'月均换手':>10}{'月最大换手':>10}{'年成本拖累':>12}")
print("  " + "-" * 120)
for label, r in results.items():
    m = perf_metrics(r["nv"])
    wh = r["wh"]
    turnover = wh.diff().abs().sum(axis=1) / 2
    mth_mean = turnover.mean()
    mth_max = turnover.max()
    cost = mth_mean * 12 * (20 / 10000)
    print(f"  {label:<22}"
          f"{m['cum_return']*100:>9.2f}%"
          f"{m['cagr']*100:>8.2f}%"
          f"{m['vol']*100:>7.2f}%"
          f"{m['mdd']*100:>9.2f}%"
          f"{m['sharpe']:>8.2f}"
          f"{m['calmar']:>8.2f}"
          f"{mth_mean*100:>9.2f}%"
          f"{mth_max*100:>9.2f}%"
          f"{cost*100:>11.4f}%")

# --- 事件期 ---
print(f"\n  关键事件期收益")
for ev_name, start, end in STRESS_EVENTS:
    print(f"  {ev_name:<20}", end="")
    for label, r in results.items():
        seg = r["nv"].loc[start:end]
        if len(seg) > 1:
            ret = seg.iloc[-1] / seg.iloc[0] - 1
            print(f"{ret*100:>18.2f}%", end="")
        else:
            print(f"{'n/a':>18}", end="")
    print()

# --- 4 宏观情景 ---
print(f"\n  4 宏观情景（季度均值）")
for rl in ["股牛+债牛", "股牛+债熊", "股熊+债牛", "股熊+债熊"]:
    print(f"  {rl:<20}", end="")
    for label, r in results.items():
        reg = regime_returns(r["nv"], rets)
        v = reg.get(rl, {}).get("avg", float("nan"))
        print(f"{v*100:>18.2f}%", end="")
    print()

print(f"\n{LINE}")
print("  完成")
print(LINE)
