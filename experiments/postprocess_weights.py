"""V3-B RP 权重后处理修正实验 — 解决风险集中度 7.88x

对比策略（100% RP）：
  1) 基准：当前无后处理 (post_process_max_w=None)
  2) 硬上限：所有资产 ≤ 0.20
  3) 软上限：所有资产 ≤ 0.25

输出：核心指标 + 事件期 + 宏观情景 + 权重统计
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
print("  V3-B RP 权重后处理修正实验 — 100% RP")
print(LINE)

panel = load_panel()
rets = panel.pct_change().dropna()
print(f"  数据: {panel.index.min().date()} ~ {panel.index.max().date()}, {len(panel)} 交易日\n")

configs = [
    ("基准 (无后处理)", dict(post_process_max_w=None)),
    ("硬上限 max_w=0.20", dict(post_process_max_w=0.20)),
    ("软上限 max_w=0.25", dict(post_process_max_w=0.25)),
]

results = {}
for label, extra in configs:
    print(f"  运行: {label} ...")
    nv, n, wh, sl = backtest_b(
        rets[V3B_RP_ASSETS], cash_ratio=0.0, rp_window=20,
        rp_buckets=V3B_RP_BUCKETS,
        nonferr_control="trend_filter", nonferr_trend_window=75,
        gold_trend_filter=True, gold_trend_window=75,
        equity_trend_assets=["us_sp500"], equity_trend_window=120,
        hs300_value_dip=True,
        track_weights=True, track_signals=True, signal_label=label,
        **extra,
    )
    results[label] = {"nv": nv, "wh": wh}

# --- 核心指标 + 权重统计 ---
vols = rets.std() * (252 ** 0.5)  # 年化波动率

print(f"\n{'变体':<24}{'累计收益':>10}{'CAGR':>9}{'波动':>8}{'MDD':>10}{'Sharpe':>8}{'Calmar':>8}"
      f"{'月换手':>8}{'成本':>8}")
print("  " + "-" * 105)
for label, r in results.items():
    m = perf_metrics(r["nv"])
    wh = r["wh"]
    turnover = wh.diff().abs().sum(axis=1).mean() / 2
    cost = turnover * 12 * (20 / 10000)
    print(f"  {label:<22}"
          f"{m['cum_return']*100:>9.2f}%"
          f"{m['cagr']*100:>8.2f}%"
          f"{m['vol']*100:>7.2f}%"
          f"{m['mdd']*100:>9.2f}%"
          f"{m['sharpe']:>8.2f}"
          f"{m['calmar']:>8.2f}"
          f"{turnover*100:>7.2f}%"
          f"{cost*100:>7.3f}%")

# --- 平均权重 + 风险贡献估算（波动率加权） ---
print(f"\n  平均持仓权重（调仓日均值） + 近似风险贡献（波动率加权）")
print(f"  {'资产':<12}{'波动率':>8}", end="")
for label in results:
    print(f"{label:>22}", end="")
    print(f"{'风险贡献':>14}", end="")
print()
for asset in V3B_RP_ASSETS:
    vol = vols.get(asset, 0)
    print(f"  {asset:<12}{vol*100:>7.2f}%", end="")
    for label, r in results.items():
        wh = r["wh"]
        avg_w = wh[asset].mean() if asset in wh.columns else 0
        # 近似风险贡献：w * σ / sum(w_i * σ_i)
        total_risk = sum(wh[a].mean() * vols.get(a, 0) for a in V3B_RP_ASSETS)
        rc_approx = avg_w * vol / total_risk if total_risk > 0 else 0
        print(f"{avg_w*100:>11.2f}%  {rc_approx*100:>7.1f}%", end=" ")
    print()

# 合计行
print(f"  {'合计':<12}{'':>8}", end="")
for label, r in results.items():
    wh = r["wh"]
    print(f"{'':>22}{'':>14}", end="")
print()

# 风险集中度（基于波动率加权）
print()
for label, r in results.items():
    wh = r["wh"]
    total_risk = sum(wh[a].mean() * vols.get(a, 0) for a in V3B_RP_ASSETS)
    rcs = []
    for bucket_name, bucket_assets in [("A股", ["hs300"]), ("美股", ["us_sp500"]),
                                        ("信用债", ["credit"]), ("长债", ["bond_30y"]),
                                        ("黄金", ["gold"]), ("有色", ["nonferr"])]:
        bucket_rc = sum(wh[a].mean() * vols.get(a, 0) for a in bucket_assets if a in wh.columns) / total_risk
        rcs.append((bucket_name, bucket_rc))
    positive_rcs = [rc for _, rc in rcs if rc > 0.01]
    ratio = max(positive_rcs) / min(positive_rcs) if positive_rcs else float("nan")
    print(f"  {label:<22} 波动率加权集中度 (max/min): {ratio:.2f}x")
    for name, rc in rcs:
        print(f"    {name:<12}{rc*100:>5.1f}%")

# --- 事件期收益 ---
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
