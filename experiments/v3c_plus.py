"""V3c+ 实验 — V3c 加 SP500 趋势过滤

对比：
  1) V3c 基准 (current)
  2) V3c+ SP500 SMA120
  3) V3-B RP 基准 (参考)

假设：V3c+ 可能用最简方案接近 V3-B RP 的回报
"""
import sys
sys.path.insert(0, ".")
import pandas as pd
from allweather.data import load_panel
from allweather.stats import perf_metrics, event_returns, regime_returns
from allweather.config import STRESS_EVENTS, V3C_ASSETS
from allweather.backtest import backtest_iv
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
print("  V3c+ 实验 — V3c + SP500 趋势过滤")
print(LINE)

panel = load_panel()
rets = panel.pct_change().dropna()
print(f"  数据: {panel.index.min().date()} ~ {panel.index.max().date()}, {len(panel)} 交易日\n")

configs = [
    ("V3c 基准",   lambda: backtest_iv(rets, cash_ratio=0.0, iv_window=60, max_w=0.30, min_w=0.03,
                                       nonferr_trend_window=75, assets=V3C_ASSETS,
                                       gold_dip_threshold=0.15, gold_dip_cap=0.20,
                                       hs300_value_dip=True,
                                       track_weights=True, track_signals=True, signal_label="V3c 基准")),
    ("V3c+ SMA120", lambda: backtest_iv(rets, cash_ratio=0.0, iv_window=60, max_w=0.30, min_w=0.03,
                                        nonferr_trend_window=75, assets=V3C_ASSETS,
                                        gold_dip_threshold=0.15, gold_dip_cap=0.20,
                                        hs300_value_dip=True,
                                        equity_trend_assets=["us_sp500"], equity_trend_window=120,
                                        track_weights=True, track_signals=True, signal_label="V3c+ SMA120")),
    ("V3-B RP 基准", lambda: backtest_b(rets[V3B_RP_ASSETS], cash_ratio=0.0, rp_window=20,
                                        rp_buckets=V3B_RP_BUCKETS,
                                        nonferr_control="trend_filter", nonferr_trend_window=75,
                                        gold_trend_filter=True, gold_trend_window=75,
                                        equity_trend_assets=["us_sp500"], equity_trend_window=120,
                                        hs300_value_dip=True,
                                        track_weights=True, track_signals=True, signal_label="V3-B RP")),
]

results = {}
for label, fn in configs:
    print(f"  运行: {label} ...")
    result = fn()
    if len(result) == 4:
        nv, n, wh, sl = result
    else:
        nv, n = result
        wh = sl = None
    results[label] = {"nv": nv, "n": n, "wh": wh, "sl": sl}

# --- 核心指标 ---
print(f"\n{'变体':<24}{'累计收益':>10}{'CAGR':>9}{'波动':>8}{'MDD':>10}{'Sharpe':>8}{'Calmar':>8}"
      f"{'hs300均权':>12}{'us500均权':>12}{'月换手':>10}{'资产数':>8}")
print("  " + "-" * 130)
for label, r in results.items():
    m = perf_metrics(r["nv"])
    wh = r["wh"]
    hs_avg = wh["hs300"].mean() if wh is not None and "hs300" in wh.columns else 0
    us_avg = wh["us_sp500"].mean() if wh is not None and "us_sp500" in wh.columns else 0
    turnover = wh.diff().abs().sum(axis=1).mean() / 2 if wh is not None else 0
    n_assets = len(wh.columns) if wh is not None else 0
    print(f"  {label:<22}"
          f"{m['cum_return']*100:>9.2f}%"
          f"{m['cagr']*100:>8.2f}%"
          f"{m['vol']*100:>7.2f}%"
          f"{m['mdd']*100:>9.2f}%"
          f"{m['sharpe']:>8.2f}"
          f"{m['calmar']:>8.2f}"
          f"{hs_avg*100:>7.1f}%"
          f"{us_avg*100:>7.1f}%"
          f"{turnover*100:>9.2f}%"
          f"{n_assets:>8d}")

# --- 分年收益 ---
print(f"\n{'':>24}", end="")
years = list(range(2008, 2026))
for y in years:
    print(f"{y:>8}", end="")
print()
from allweather.stats import yearly_returns
for label, r in results.items():
    yr = yearly_returns(r["nv"])
    print(f"  {label:<22}", end="")
    for y in years:
        v = yr.get(y, float("nan"))
        print(f"{v*100:>7.1f}%" if not pd.isna(v) else f"{'n/a':>8}", end="")
    print()

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

# --- 宏观情景 ---
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
