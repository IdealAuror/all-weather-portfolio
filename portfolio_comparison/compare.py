"""竞品组合 vs 全天候策略 全维度对比

竞品：城投债50% + 标普500 20% + 纳指100 10% + 黄金10% + 华宝油气5%，年度再平衡
全天候：V3-B Con / V3-B RP / V3c，月度再平衡 + 趋势过滤 + 抄底
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import time as _time
import math
import requests
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.ticker import PercentFormatter

from allweather.data import load_panel, load_hs300_pb, load_hs300_pe
from allweather.risk import _precompute_percentile
from allweather.stats import perf_metrics, yearly_returns, event_returns, rolling_stats
from allweather.config import (
    STRATEGY_PARAMS, V3B_RP_BUCKETS, V3B_RP_ASSETS, V3B_CON_ASSETS, V3C_ASSETS,
    SP500_TREND_WINDOW, HS300_TREND_WINDOW, RISK_PARITY_TARGET_VOL, RISK_PARITY_COV_WINDOW,
    RISK_FREE_ANNUAL,
)

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

START_DATE = "2019-10-13"
# ──────────────────────────────────────────────────────────
# 1. 拉取竞品独有 ETF 数据
# ──────────────────────────────────────────────────────────
def _fetch_etf_nav(code, start, end):
    url = "https://api.fund.eastmoney.com/f10/lsjz"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": f"https://fundf10.eastmoney.com/jjjz_{code}.html",
    }
    params = {
        "fundCode": code, "pageIndex": "1", "pageSize": "20",
        "startDate": "-".join([start[:4], start[4:6], start[6:]]),
        "endDate": "-".join([end[:4], end[4:6], end[6:]]),
        "_": round(_time.time() * 1000),
    }
    r = requests.get(url, params=params, headers=headers, timeout=30)
    data_json = r.json()
    total_page = math.ceil(data_json["TotalCount"] / 20)
    df_list = []
    for page in range(1, total_page + 1):
        if page > 1:
            params["pageIndex"] = str(page)
            params["_"] = round(_time.time() * 1000)
            r = requests.get(url, params=params, headers=headers, timeout=30)
            data_json = r.json()
        temp_df = pd.DataFrame(data_json["Data"]["LSJZList"])
        df_list.append(temp_df)
    big_df = pd.concat(df_list, ignore_index=True)
    col_map = {"FSRQ": "date", "LJJZ": "close"}
    big_df = big_df[list(col_map.keys())].rename(columns=col_map)
    big_df["date"] = pd.to_datetime(big_df["date"], errors="coerce")
    big_df["close"] = pd.to_numeric(big_df["close"], errors="coerce")
    big_df = big_df.dropna(subset=["date", "close"])
    return big_df[["date", "close"]].sort_values("date").reset_index(drop=True)


def fetch_competitor_etfs():
    """拉取竞品五只 ETF 真实净值，不走 load_panel 代理数据。"""
    today = pd.Timestamp.now().strftime("%Y%m%d")
    start = "20190101"

    etfs = {
        "credit": "511220",
        "sp500": "513500",
        "nasdaq": "513100",
        "gold": "518880",
        "oil": "162411",
    }
    result = {}
    for name, code in etfs.items():
        print(f"拉取 {code} {name}...")
        df = _fetch_etf_nav(code, start, today)
        print(f"  ok {df['date'].min().date()} ~ {df['date'].max().date()}  n={len(df)}")
        result[name] = df
    return result


# ──────────────────────────────────────────────────────────
# 2. 构建竞品组合 NAV（年度再平衡）
# ──────────────────────────────────────────────────────────
def build_competitor_nav(prices, weights, rebalance_month=10, rebalance_day=13):
    """固定权重 + 年度再平衡。首次建仓日即 rebalance_day 所在月日。

    prices: DataFrame, columns = assets, index = date
    weights: dict {asset: weight}
    """
    w = pd.Series(weights)
    common = [c for c in w.index if c in prices.columns]
    w = w[common]
    w = w / w.sum()
    px = prices[common].copy()

    nv_series = pd.Series(index=px.index, dtype=float)
    current_w = None
    nv = 1.0
    last_rebal_year = None

    for i, (d, row) in enumerate(px.iterrows()):
        if current_w is None or (d.year != last_rebal_year and d.month == rebalance_month and d.day >= rebalance_day):
            current_w = w.copy()
            last_rebal_year = d.year
        elif i > 0:
            prev_px = px.iloc[i - 1]
            curr_px = row
            daily_ret = curr_px / prev_px - 1
            daily_ret = daily_ret.fillna(0)
            current_w = current_w * (1 + daily_ret)
            s = current_w.sum()
            if s > 0:
                current_w = current_w / s

        if nv_series.index[i] >= pd.Timestamp(START_DATE):
            nv_series.iloc[i] = nv

        if i < len(px) - 1:
            next_ret = px.iloc[i + 1] / row - 1
            port_ret = (current_w * next_ret).sum()
            nv *= (1 + port_ret)

    nv_series = nv_series.dropna()
    nv_series.iloc[0] = 1.0
    return nv_series


# ──────────────────────────────────────────────────────────
# 3. 构建竞品组合 NAV（年度再平衡）
# ──────────────────────────────────────────────────────────
def build_competitor_prices(etf_data):
    """从 ETF 数据构建竞品五资产价格面板。QDII ETF 用 ffill 对齐非重叠交易日。"""
    assets = {name: df.set_index("date")["close"] for name, df in etf_data.items()}
    prices = pd.DataFrame(assets).sort_index().ffill().dropna()
    return prices


# ──────────────────────────────────────────────────────────
# 4. 运行全天候策略（同期）
# ──────────────────────────────────────────────────────────
def run_allweather_backtests(rets_full):
    from allweather.backtest import backtest_iv
    from allweather.strategy_b import backtest_b

    rets = rets_full.copy()
    hs300_pb_data = load_hs300_pb()
    hs300_pe_data = load_hs300_pe()
    hs300_pb_pct = _precompute_percentile(hs300_pb_data)
    hs300_pe_pct = _precompute_percentile(hs300_pe_data)

    _common = dict(
        cash_ratio=0.0,
        nonferr_trend_window=75,
        hs300_value_dip=True,
        track_weights=False, track_signals=False,
        hs300_pb_data=hs300_pb_data, hs300_pe_data=hs300_pe_data,
        hs300_pb_pct=hs300_pb_pct, hs300_pe_pct=hs300_pe_pct,
    )

    results = {}

    # V3-B RP
    _b_rp = dict(
        rp_window=STRATEGY_PARAMS["rp"]["window"],
        gold_trend_filter=True, gold_trend_window=75,
        equity_trend_assets=["us_sp500", "hs300"],
        equity_trend_windows={"us_sp500": SP500_TREND_WINDOW, "hs300": HS300_TREND_WINDOW},
        target_vol=RISK_PARITY_TARGET_VOL, vol_target_window=RISK_PARITY_COV_WINDOW,
        gold_dip_threshold=None,
    )
    nv_rp, _, _, _, _ = backtest_b(
        rets[V3B_RP_ASSETS], rp_buckets=V3B_RP_BUCKETS,
        signal_label="V3-B 风险平价", **_common, **_b_rp)
    results["V3-B 风险平价"] = nv_rp

    # V3-B Con
    _b_con = dict(
        rp_window=STRATEGY_PARAMS["con"]["window"],
        max_w=STRATEGY_PARAMS["con"]["max_w"],
        weighting_method="inverse_vol",
        gold_dip_threshold=None, gold_dip_cap=0.20,
    )
    nv_con, _, _, _, _ = backtest_b(
        rets[V3B_CON_ASSETS], signal_label="V3-B 保守增强", **_common, **_b_con)
    results["V3-B 保守增强"] = nv_con

    # V3c
    _iv = dict(
        iv_window=STRATEGY_PARAMS["v3c"]["window"],
        max_w=STRATEGY_PARAMS["v3c"]["max_w"],
        min_w=STRATEGY_PARAMS["v3c"]["min_w"],
        gold_trend_filter=True, gold_trend_window=75,
        gold_dip_threshold=None, gold_dip_cap=0.20,
        equity_trend_assets=["us_sp500"], equity_trend_window=75,
    )
    nv_v3c, _, _, _, _ = backtest_iv(
        rets, assets=V3C_ASSETS, signal_label="V3c 多元", **_common, **_iv)
    results["V3c 多元"] = nv_v3c

    return results


# ──────────────────────────────────────────────────────────
# 5. 指标对比
# ──────────────────────────────────────────────────────────
def compute_all_metrics(nv_dict):
    """为所有 NAV 序列计算指标。CAGR/Sharpe 统一用 365 自然日口径。"""
    metrics = {}
    yearly = {}
    for name, nv in nv_dict.items():
        r = nv.pct_change().dropna()
        m = perf_metrics(nv, rets=r)
        calendar_days = (nv.index[-1] - nv.index[0]).days
        cal_years = calendar_days / 365.25
        cagr_cal = (1 + m["cum_return"]) ** (1 / cal_years) - 1 if cal_years > 0 else 0
        m["cagr"] = cagr_cal
        m["sharpe"] = (cagr_cal - RISK_FREE_ANNUAL) / m["vol"] if m["vol"] > 0 else float("nan")
        m["n_years"] = cal_years
        m["calendar_days"] = calendar_days
        metrics[name] = m
        yearly[name] = yearly_returns(nv, rets=r)
    return metrics, yearly


def print_comparison_table(metrics, yearly, nv_dict):
    """打印全维度对比表。"""
    names = list(metrics.keys())
    header = f"{'指标':<22}"
    for n in names:
        header += f" {n:>16}"
    print(header)
    print("-" * len(header))

    rows = [
        ("累计收益", "cum_return", "{:.2%}"),
        ("CAGR (365d口径)", "cagr", "{:.2%}"),
        ("年化波动率", "vol", "{:.2%}"),
        ("最大回撤 (MDD)", "mdd", "{:.2%}"),
        ("Sharpe (修正,365d)", "sharpe", "{:.2f}"),
        ("Calmar", "calmar", "{:.2f}"),
        ("几何超额 D", "geometric_excess_d", "{:.3f}"),
        ("样本年数(365d)", "n_years", "{:.1f}"),
    ]
    for label, key, fmt in rows:
        line = f"{label:<22}"
        for n in names:
            val = metrics[n][key]
            line += f" {fmt.format(val):>16}"
        print(line)

    print(f"\n{'逐年收益对比':=<60}")
    years = sorted(set.union(*[set(y.index) for y in yearly.values()]))
    header2 = f"{'年份':<8}"
    for n in names:
        header2 += f" {n:>12}"
    print(header2)
    print("-" * len(header2))
    for y in years:
        line = f"{y:<8}"
        for n in names:
            ret = yearly[n].get(y, float("nan"))
            if pd.isna(ret):
                line += f" {'N/A':>12}"
            else:
                line += f" {ret:>11.2%}"
        print(line)

    # 汇总行
    print("-" * len(header2))
    line = f"{'正收益年':<8}"
    for n in names:
        pos_years = sum(1 for v in yearly[n] if v > 0)
        total_years = len(yearly[n])
        line += f" {f'{pos_years}/{total_years}':>12}"
    print(line)

    # 最差年份
    line = f"{'最差年份':<8}"
    for n in names:
        worst = yearly[n].min()
        line += f" {worst:>11.2%}"
    print(line)

    print(f"\n{'最大回撤期间':=<60}")
    for n in names:
        nv = nv_dict[n]
        dd = nv / nv.cummax() - 1
        mdd_end = dd.idxmin()
        peak = nv[:mdd_end].idxmax()
        print(f"  {n:<16} {peak.date()} → {mdd_end.date()}  MDD={dd.min():.2%}")

    # 总评
    print(f"\n{'总结':=<60}")
    best_cagr = max(metrics.items(), key=lambda x: x[1]["cagr"])
    best_sharpe = max(metrics.items(), key=lambda x: x[1]["sharpe"])
    lowest_mdd = min(metrics.items(), key=lambda x: abs(x[1]["mdd"]))
    print(f"  最高 CAGR:   {best_cagr[0]} ({best_cagr[1]['cagr']:.2%})")
    print(f"  最高 Sharpe: {best_sharpe[0]} ({best_sharpe[1]['sharpe']:.2f})")
    print(f"  最低 MDD:   {lowest_mdd[0]} ({lowest_mdd[1]['mdd']:.2%})")


# ──────────────────────────────────────────────────────────
# 6. 图表
# ──────────────────────────────────────────────────────────
def set_style():
    plt.rcParams.update({
        "figure.facecolor": "white", "axes.facecolor": "white",
        "axes.edgecolor": "#cccccc", "axes.grid": True,
        "grid.alpha": 0.3, "grid.color": "#cccccc",
        "font.family": "sans-serif",
        "font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "font.size": 10, "axes.titlesize": 13, "axes.labelsize": 11,
        "figure.dpi": 150, "savefig.dpi": 150, "savefig.bbox": "tight",
    })

COLORS = {
    "竞品组合": "#e74c3c",
    "V3-B 保守增强": "#3498db",
    "V3-B 风险平价": "#2ecc71",
    "V3c 多元": "#9b59b6",
}


def plot_nav_comparison(nv_dict, metrics):
    set_style()
    fig, axes = plt.subplots(2, 1, figsize=(16, 10))

    ax = axes[0]
    for name, nv in nv_dict.items():
        ax.plot(nv.index, nv, label=name, color=COLORS.get(name), linewidth=1.2)
    ax.set_title("NAV 对比 (2019-10-13 → )")
    ax.set_ylabel("净值 (起始=1)")
    ax.legend(loc="upper left", fontsize=8)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))

    ax = axes[1]
    for name, nv in nv_dict.items():
        dd = nv / nv.cummax() - 1
        ax.plot(dd.index, dd * 100, label=name, color=COLORS.get(name), linewidth=1.2)
    ax.set_title("回撤对比")
    ax.set_ylabel("回撤 (%)")
    ax.legend(loc="lower left", fontsize=8)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.0f%%'))

    fig.tight_layout()
    path = OUTPUT_DIR / "nav_comparison.png"
    fig.savefig(path)
    plt.close(fig)
    print(f"  ok {path.name}")


def plot_yearly_comparison(yearly):
    set_style()
    names = list(yearly.keys())
    years = sorted(set.union(*[set(y.index) for y in yearly.values()]))
    x = np.arange(len(years))
    width = 0.2
    n = len(names)

    fig, ax = plt.subplots(figsize=(16, 5))
    for i, name in enumerate(names):
        vals = [yearly[name].get(y, 0) * 100 for y in years]
        offset = (i - (n - 1) / 2) * width
        bars = ax.bar(x + offset, vals, width, label=name, color=COLORS.get(name))
        for bar, val in zip(bars, vals):
            if val != 0:
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_height() + (0.3 if val >= 0 else -1.2),
                        f"{val:.1f}%", ha="center", fontsize=7)

    ax.set_title("逐年收益对比")
    ax.set_xticks(x)
    ax.set_xticklabels(years)
    ax.axhline(y=0, color="black", linewidth=0.5)
    ax.legend(fontsize=8)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.0f%%'))

    fig.tight_layout()
    path = OUTPUT_DIR / "yearly_comparison.png"
    fig.savefig(path)
    plt.close(fig)
    print(f"  ok {path.name}")


def plot_rolling_1y(nv_dict):
    set_style()
    fig, ax = plt.subplots(figsize=(16, 5))
    for name, nv in nv_dict.items():
        r1y = nv.pct_change(252).dropna()
        ax.plot(r1y.index, r1y * 100, label=name, color=COLORS.get(name), linewidth=1.0)
    ax.set_title("滚动 1 年收益对比")
    ax.set_ylabel("滚动 1 年收益 (%)")
    ax.axhline(y=0, color="black", linewidth=0.5)
    ax.legend(fontsize=8)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.0f%%'))
    fig.tight_layout()
    path = OUTPUT_DIR / "rolling_1y_comparison.png"
    fig.savefig(path)
    plt.close(fig)
    print(f"  ok {path.name}")


# ──────────────────────────────────────────────────────────
# 7. 主流程
# ──────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  竞品组合 vs 全天候策略 · 全维度对比")
    print("=" * 60)

    # Step 1: 拉取竞品 ETF
    print("\n[1/5] 拉取竞品 ETF 真实净值...")
    etf_data = fetch_competitor_etfs()

    # Step 2: 加载全天候数据
    print("\n[2/5] 加载全天候数据...")
    panel = load_panel()
    print(f"  ok 全天候数据: {panel.index.min().date()} ~ {panel.index.max().date()}")

    # Step 3: 构建竞品价格面板 + NAV
    print("\n[3/5] 构建竞品组合 NAV...")
    comp_prices = build_competitor_prices(etf_data)
    comp_weights = {"credit": 0.50, "sp500": 0.20, "nasdaq": 0.10, "gold": 0.10, "oil": 0.05}
    comp_nv = build_competitor_nav(comp_prices, comp_weights)
    print(f"  ok 竞品 NAV: {comp_nv.index.min().date()} ~ {comp_nv.index.max().date()}")

    # Step 4: 运行全天候策略
    print("\n[4/5] 运行全天候策略回测...")
    rets_full = panel.pct_change().dropna()
    aw_nv = run_allweather_backtests(rets_full)

    # 对齐所有 NAV 到竞品起始日
    common_start = max(comp_nv.index.min(), *(nv.index.min() for nv in aw_nv.values()))
    common_end = min(comp_nv.index.max(), *(nv.index.max() for nv in aw_nv.values()))
    print(f"  ok 对齐区间: {common_start.date()} ~ {common_end.date()}")

    nv_dict = {"竞品组合": comp_nv[common_start:common_end]}
    for name, nv in aw_nv.items():
        nv_dict[name] = nv[common_start:common_end]

    # 统一从 1 开始
    for name in nv_dict:
        nv_dict[name] = nv_dict[name] / nv_dict[name].iloc[0]

    # Step 5: 指标 + 图表
    print("\n[5/5] 计算指标 + 生成图表...")
    metrics, yearly = compute_all_metrics(nv_dict)
    print_comparison_table(metrics, yearly, nv_dict)
    plot_nav_comparison(nv_dict, metrics)
    plot_yearly_comparison(yearly)
    plot_rolling_1y(nv_dict)

    print(f"\n图表输出: {OUTPUT_DIR}")
    print("完成！")


if __name__ == "__main__":
    main()
