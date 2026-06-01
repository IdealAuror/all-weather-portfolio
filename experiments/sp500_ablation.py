"""SP500 趋势过滤消融实验 — V3-B RP 100% RP

对比策略：
  1) 基准：SP500 SMA120 趋势过滤（当前）
  2) 消融：完全移除 SP500 趋势过滤
  3) 修复：SMA200 替代 SMA120

输出：控制台对比表
"""
import sys
sys.path.insert(0, ".")
import pandas as pd
from allweather.data import load_panel
from allweather.stats import perf_metrics, yearly_returns, event_returns, regime_returns
from allweather.config import BUCKETS, STRESS_EVENTS
from allweather.strategy_b import backtest_b

V3B_RP_BUCKETS = {
    "增长↑":   ["hs300", "us_sp500"],
    "收益垫":  ["credit"],
    "增长↓":   ["bond_30y"],
    "通胀↑":   ["gold", "nonferr"],
}
V3B_RP_ASSETS = [a for assets in V3B_RP_BUCKETS.values() for a in assets]

print("=" * 110)
print("  SP500 趋势过滤消融实验 — V3-B 风险平价(20d) 100% RP")
print("=" * 110)

panel = load_panel()
rets = panel.pct_change().dropna()
print(f"\n数据期间: {panel.index.min().date()} ~ {panel.index.max().date()}")
print(f"交易日数: {len(panel)}\n")

configs = [
    ("基准 SMA120",  dict(equity_trend_assets=["us_sp500"], equity_trend_window=120)),
    ("消融-完全移除", dict(equity_trend_assets=None)),
    ("修复 SMA200",  dict(equity_trend_assets=["us_sp500"], equity_trend_window=200)),
]

results = {}

for label, extra in configs:
    nv, n, wh, sl = backtest_b(
        rets[V3B_RP_ASSETS], cash_ratio=0.0, rp_window=20,
        rp_buckets=V3B_RP_BUCKETS,
        nonferr_control="trend_filter", nonferr_trend_window=75,
        gold_trend_filter=True, gold_trend_window=75,
        hs300_value_dip=True,
        track_weights=True, track_signals=True, signal_label=label,
        **{k: v for k, v in extra.items() if k in ["equity_trend_assets", "equity_trend_window"]},
    )
    results[label] = {"nv": nv, "n": n, "wh": wh, "sl": sl}

# --- 核心指标 ---
print(f"{'变体':<20}{'累计收益':>10}{'CAGR':>9}{'波动':>8}{'MDD':>10}{'Sharpe':>8}{'Calmar':>8}"
      f"{'us_sp500均权':>14}{'非ferr均权':>14}{'换手率':>8}{'成本拖累':>10}")
print("  " + "-" * 120)
for label, r in results.items():
    m = perf_metrics(r["nv"])
    wh = r["wh"]
    us_avg = wh["us_sp500"].mean() if "us_sp500" in wh.columns else 0
    nf_avg = wh["nonferr"].mean() if "nonferr" in wh.columns else 0
    turnover = wh.diff().abs().sum(axis=1).mean() / 2
    cost = turnover * 12 * (10 * 2 / 10000)
    print(f"  {label:<18}"
          f"{m['cum_return']*100:>9.2f}%"
          f"{m['cagr']*100:>8.2f}%"
          f"{m['vol']*100:>7.2f}%"
          f"{m['mdd']*100:>9.2f}%"
          f"{m['sharpe']:>8.2f}"
          f"{m['calmar']:>8.2f}"
          f"{us_avg*100:>8.1f}%"
          f"{nf_avg*100:>8.1f}%"
          f"{turnover*100:>7.2f}%"
          f"{cost*100:>9.2f}%")

# --- 分年收益 ---
print(f"\n{'':>20}", end="")
years = list(range(2008, 2026))
for y in years:
    print(f"{y:>8}", end="")
print()
for label, r in results.items():
    yr = yearly_returns(r["nv"])
    print(f"  {label:<18}", end="")
    for y in years:
        v = yr.get(y, float("nan"))
        if pd.isna(v):
            print(f"{'n/a':>8}", end="")
        else:
            print(f"{v*100:>7.1f}%", end="")
    print()

# --- 事件期收益 ---
print(f"\n{'事件':<22}", end="")
for label in results:
    print(f"{label:>20}", end="")
print()
for ev_name, start, end in STRESS_EVENTS:
    print(f"  {ev_name:<20}", end="")
    for label, r in results.items():
        seg = r["nv"].loc[start:end]
        if len(seg) > 1:
            ret = seg.iloc[-1] / seg.iloc[0] - 1
            print(f"{ret*100:>19.2f}%", end="")
        else:
            print(f"{'n/a':>20}", end="")
    print()

# --- 4 宏观情景 ---
print(f"\n{'情景':<22}", end="")
for label in results:
    print(f"{label:>20}", end="")
print()
regimes_list = ["股牛+债牛", "股牛+债熊", "股熊+债牛", "股熊+债熊"]
for regime_label in regimes_list:
    print(f"  {regime_label:<20}", end="")
    for label, r in results.items():
        reg = regime_returns(r["nv"], rets)
        v = reg.get(regime_label, {}).get("avg", float("nan"))
        if pd.isna(v):
            print(f"{'n/a':>20}", end="")
        else:
            print(f"{v*100:>19.2f}%", end="")
    print()
