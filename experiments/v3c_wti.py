"""V3c + 原油（WTI）实验

单变量对比：
  1) V3c 基准（6 资产）
  2) V3c + WTI（7 资产）

假设：原油与现有资产低相关（实测全部 <0.30），在通胀↑桶中补充供给冲击维度，
逆波动率框架下波动率 40% 会被自然压制，预期在不恶化其他指标的前提下改善 CAGR。
"""
import sys
sys.path.insert(0, ".")
import pandas as pd
from allweather.data import load_panel
from allweather.stats import perf_metrics, event_returns, regime_returns, yearly_returns
from allweather.config import STRESS_EVENTS, V3C_ASSETS
from allweather.backtest import backtest_iv

LINE = "=" * 110
print(LINE)
print("  V3c + 原油(WTI) 实验")
print(LINE)

panel = load_panel()
rets = panel.pct_change().dropna()
print(f"  数据: {panel.index.min().date()} ~ {panel.index.max().date()}, {len(panel)} 交易日\n")

# V3c 基准 + WTI
V3C_WTI_ASSETS = V3C_ASSETS + ["wti"]

configs = [
    ("V3c 基准",   V3C_ASSETS, {}),
    ("V3c+WTI",    V3C_WTI_ASSETS, {}),
]

# 通用参数
KWARGS = dict(
    cash_ratio=0.0, iv_window=60, max_w=0.30, min_w=0.03,
    nonferr_trend_window=75, gold_dip_threshold=0.15, gold_dip_cap=0.20,
    hs300_value_dip=True, track_weights=True, track_signals=True,
)

results = {}
for label, assets, extra in configs:
    print(f"  运行: {label} (n={len(assets)} 资产) ...")
    kwargs = {**KWARGS, **extra, "assets": assets,
              "signal_label": label}
    result = backtest_iv(rets, **kwargs)
    if len(result) == 4:
        nv, n, wh, sl = result
    else:
        nv, n = result
        wh = sl = None
    results[label] = {"nv": nv, "n": n, "wh": wh, "sl": sl}

# --- 核心指标 ---
print(f"\n{'变体':<20}{'累计收益':>10}{'CAGR':>9}{'波动':>8}{'MDD':>10}{'Sharpe':>8}{'Calmar':>8}"
      f"{'hs300均权':>10}{'us500均权':>10}{'月换手':>9}{'资产数':>7}")
print("  " + "-" * 120)
for label, r in results.items():
    m = perf_metrics(r["nv"])
    wh = r["wh"]
    hs_avg = wh["hs300"].mean() if wh is not None and "hs300" in wh.columns else 0
    us_avg = wh["us_sp500"].mean() if wh is not None and "us_sp500" in wh.columns else 0
    turnover = wh.diff().abs().sum(axis=1).mean() / 2 if wh is not None else 0
    n_assets = len(wh.columns) if wh is not None else 0
    print(f"  {label:<18}"
          f"{m['cum_return']*100:>9.2f}%"
          f"{m['cagr']*100:>8.2f}%"
          f"{m['vol']*100:>7.2f}%"
          f"{m['mdd']*100:>9.2f}%"
          f"{m['sharpe']:>8.2f}"
          f"{m['calmar']:>8.2f}"
          f"{hs_avg*100:>7.1f}%"
          f"{us_avg*100:>7.1f}%"
          f"{turnover*100:>8.2f}%"
          f"{n_assets:>7d}")

# WTI 均权
for label, r in results.items():
    wh = r["wh"]
    if wh is not None and "wti" in wh.columns:
        wti_avg = wh["wti"].mean()
        print(f"    (其中 {label} wti均权={wti_avg*100:.1f}%)")

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
            print(f"{ret*100:>16.2f}%", end="")
        else:
            print(f"{'n/a':>16}", end="")
    print()

# --- 宏观情景 ---
print(f"\n  4 宏观情景（季度均值）")
for rl in ["股牛+债牛", "股牛+债熊", "股熊+债牛", "股熊+债熊"]:
    print(f"  {rl:<20}", end="")
    for label, r in results.items():
        reg = regime_returns(r["nv"], rets)
        v = reg.get(rl, {}).get("avg", float("nan"))
        print(f"{v*100:>16.2f}%", end="")
    print()

print(f"\n{LINE}")
print("  完成")
print(LINE)
