"""图表生成 — NAV 曲线、回撤、滚动收益等。"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from pathlib import Path
from .config import OUTPUT_DIR

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["SimHei", "Microsoft YaHei", "Noto Sans SC"],
    "axes.unicode_minus": False,
    "figure.dpi": 150,
    "savefig.dpi": 150,
    "savefig.bbox": "tight",
    "savefig.facecolor": "white",
})

CHART_DIR = OUTPUT_DIR / "charts"

TIER_COLORS = {"100% RP": "#2c3e50", "85% RP": "#7f8c8d", "70% RP": "#bdc3c7"}
PORT_COLORS = {
    "V3c 多元": "#3498db",
    "V3-B 风险平价(20d)": "#e74c3c",
    "V3-B 保守增强(20d)": "#2ecc71",
}
PORT_LINESTYLES = {
    "V3c 多元": "-",
    "V3-B 风险平价(20d)": "--",
    "V3-B 保守增强(20d)": "-.",
}


def _ensure_dir():
    CHART_DIR.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════
# Priority 1: NAV curves + Drawdown curves
# ═══════════════════════════════════════════════════════════

def plot_nav_and_dd(nv_results: dict, tier: str = "100% RP"):
    """净值曲线（上）+ 回撤曲线（下）双面板图。"""
    _ensure_dir()
    ports = ["V3c 多元", "V3-B 风险平价(20d)", "V3-B 保守增强(20d)"]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True,
                                    gridspec_kw={"height_ratios": [3, 2], "hspace": 0.05})

    for p in ports:
        key = (p, tier)
        if key not in nv_results:
            continue
        nv = nv_results[key]
        color = PORT_COLORS[p]
        ls = PORT_LINESTYLES[p]
        ax1.plot(nv.index, nv.values, color=color, ls=ls, lw=1.2, label=p)
        dd = nv / nv.cummax() - 1
        ax2.fill_between(dd.index, 0, dd.values, color=color, alpha=0.15)
        ax2.plot(dd.index, dd.values, color=color, ls=ls, lw=0.8)

    ax1.set_ylabel("净值")
    ax1.set_title(f"净值曲线与回撤（{tier}）", fontsize=13, fontweight="bold")
    ax1.legend(loc="upper left", frameon=False, fontsize=9)
    ax1.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.1f"))
    ax1.grid(True, alpha=0.3)

    ax2.set_ylabel("回撤")
    ax2.set_xlabel("")
    ax2.yaxis.set_major_formatter(mticker.PercentFormatter(1.0))
    ax2.grid(True, alpha=0.3)
    ax2.axhline(0, color="black", lw=0.5)

    _draw_events([ax1, ax2], ax1)

    fig.autofmt_xdate()
    path = CHART_DIR / f"nav_drawdown_{tier.replace(' ', '_')}.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_all_tiers_nv(nv_results: dict):
    """三策略各自分面板，每面板三条现金档位净值曲线。"""
    _ensure_dir()
    ports = ["V3c 多元", "V3-B 风险平价(20d)", "V3-B 保守增强(20d)"]
    tiers = ["100% RP", "85% RP", "70% RP"]

    fig, axes = plt.subplots(1, 3, figsize=(18, 6), sharey=False)
    for ax, p in zip(axes, ports):
        color = PORT_COLORS[p]
        for t in tiers:
            key = (p, t)
            if key not in nv_results:
                continue
            nv = nv_results[key]
            alpha = 1.0 if t == "100% RP" else 0.5
            lw = 1.5 if t == "100% RP" else 0.8
            ax.plot(nv.index, nv.values, color=color, alpha=alpha, lw=lw, label=t)
        ax.set_title(p, fontsize=11, fontweight="bold")
        ax.legend(loc="upper left", frameon=False, fontsize=8)
        ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.1f"))
        ax.grid(True, alpha=0.3)

    fig.autofmt_xdate()
    fig.suptitle("净值曲线 — 三档现金对比", fontsize=13, fontweight="bold", y=1.01)
    path = CHART_DIR / "nav_all_tiers.png"
    fig.savefig(path)
    plt.close(fig)
    return path


# ═══════════════════════════════════════════════════════════
# Priority 2: Rolling 1-year returns
# ═══════════════════════════════════════════════════════════

def plot_rolling_returns(metrics: dict):
    """滚动 1 年年化收益 + 回撤曲线。"""
    _ensure_dir()
    rolling = metrics.get("rolling", {})
    ports = ["V3c 多元", "V3-B 风险平价(20d)", "V3-B 保守增强(20d)"]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True,
                                    gridspec_kw={"height_ratios": [3, 2], "hspace": 0.05})

    for p in ports:
        if p not in rolling or "rolling_ann" not in rolling[p]:
            continue
        r = rolling[p]
        color = PORT_COLORS[p]
        ls = PORT_LINESTYLES[p]
        ax1.plot(r["rolling_ann"].index, r["rolling_ann"].values * 100,
                 color=color, ls=ls, lw=0.8, label=p)
        ax2.plot(r["rolling_dd"].index, r["rolling_dd"].values * 100,
                 color=color, ls=ls, lw=0.8)

    ax1.set_ylabel("年化收益 (%)")
    ax1.set_title("滚动 1 年收益与回撤（100% RP）", fontsize=13, fontweight="bold")
    ax1.legend(loc="upper right", frameon=False, fontsize=8)
    ax1.axhline(0, color="black", lw=0.5)
    ax1.grid(True, alpha=0.3)

    ax2.set_ylabel("滚动回撤 (%)")
    ax2.axhline(0, color="black", lw=0.5)
    ax2.grid(True, alpha=0.3)

    _draw_events([ax1, ax2], ax1, label_y=0.78)

    fig.autofmt_xdate()
    path = CHART_DIR / "rolling_returns.png"
    fig.savefig(path)
    plt.close(fig)
    return path


# ═══════════════════════════════════════════════════════════
# Priority 3: Monthly returns comparison (line chart + box plot)
# ═══════════════════════════════════════════════════════════

def plot_monthly_returns_comparison(nv_results: dict):
    """三策略月度收益对比 — 上半时序线图 + 下半箱线图。"""
    _ensure_dir()
    ports = ["V3c 多元", "V3-B 风险平价(20d)", "V3-B 保守增强(20d)"]
    tier = "100% RP"

    monthly_data = {}
    for p in ports:
        key = (p, tier)
        if key not in nv_results:
            continue
        nv = nv_results[key]
        m = nv.resample("ME").apply(lambda x: x.iloc[-1] / x.iloc[0] - 1) * 100
        monthly_data[p] = m

    if not monthly_data:
        return

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10),
                                    gridspec_kw={"height_ratios": [3, 2], "hspace": 0.15})

    for p in ports:
        if p not in monthly_data:
            continue
        m = monthly_data[p]
        color = PORT_COLORS[p]
        ls = PORT_LINESTYLES[p]
        ax1.plot(m.index, m.values, color=color, ls=ls, lw=0.6, alpha=0.9, label=p)

    ax1.axhline(0, color="black", lw=0.5)
    ax1.set_ylabel("月收益 (%)")
    ax1.set_title("月度收益对比（100% RP）", fontsize=13, fontweight="bold")
    ax1.legend(loc="upper right", frameon=False, fontsize=6.5, ncol=1,
               handlelength=1.0, handletextpad=0.3)
    ax1.grid(True, alpha=0.3)

    box_data = [monthly_data[p].values for p in ports if p in monthly_data]
    box_labels = [p for p in ports if p in monthly_data]
    bp = ax2.boxplot(box_data, vert=False, patch_artist=True, labels=box_labels,
                     medianprops={"color": "black", "lw": 1.2},
                     flierprops={"marker": "o", "markersize": 3, "alpha": 0.5})
    for patch, p in zip(bp["boxes"], box_labels):
        patch.set_facecolor(PORT_COLORS[p])
        patch.set_alpha(0.4)

    ax2.axvline(0, color="black", lw=0.5)
    ax2.set_xlabel("月收益 (%)")
    ax2.set_title("月度收益分布", fontsize=12)
    ax2.grid(True, alpha=0.3, axis="x")

    _draw_events([ax1], ax1)

    fig.autofmt_xdate()
    path = CHART_DIR / "monthly_returns_comparison.png"
    fig.savefig(path)
    plt.close(fig)
    return path


# ═══════════════════════════════════════════════════════════
# Priority 4: Monthly return heatmap
# ═══════════════════════════════════════════════════════════

def plot_yearly_returns(metrics: dict, nv_results: dict = None):
    """月度收益热力图 — 行=年份，列=月份，颜色=月收益。"""
    _ensure_dir()
    ports = ["V3c 多元", "V3-B 风险平价(20d)", "V3-B 保守增强(20d)"]
    import calendar

    for p in ports:
        key = (p, "100% RP")
        if nv_results is None or key not in nv_results:
            continue
        nv = nv_results[key]
        monthly = nv.resample("ME").apply(lambda x: x.iloc[-1] / x.iloc[0] - 1)
        table = {}
        yearly_sum = {}
        for d, r in monthly.items():
            if d.year not in table:
                table[d.year] = {}
            table[d.year][d.month] = r * 100
            yearly_sum[d.year] = yearly_sum.get(d.year, 0) + r

        years = sorted(table.keys())
        months = list(range(1, 13))
        data = np.full((len(years), len(months)), np.nan)
        for i, y in enumerate(years):
            for j, m in enumerate(months):
                data[i, j] = table[y].get(m, np.nan)

        fig, ax = plt.subplots(figsize=(14, max(7, len(years) * 0.45)))
        vmax = max(abs(np.nanpercentile(data, 1)), abs(np.nanpercentile(data, 99)), 3)
        im = ax.imshow(data, cmap="RdYlGn", aspect="auto", vmin=-vmax, vmax=vmax)

        for i in range(len(years)):
            for j in range(len(months)):
                v = data[i, j]
                if not np.isnan(v):
                    ax.text(j, i, f"{v:.1f}", ha="center", va="center",
                            fontsize=7, color="black" if abs(v) < vmax * 0.65 else "white")

        ax.set_xticks(range(len(months)))
        ax.set_xticklabels([calendar.month_abbr[m] for m in months], fontsize=8)
        ax.set_yticks(range(len(years)))
        ylabels = [f"{y}  {yearly_sum.get(y, 0):+.1f}%" for y in years]
        ax.set_yticklabels(ylabels, fontsize=8, fontfamily="monospace")

        ax.set_title(f"{p} — 月度收益热力图（100% RP）", fontsize=13, fontweight="bold")
        cbar = fig.colorbar(im, ax=ax, shrink=0.85, pad=0.01)
        cbar.set_label("%", fontsize=9)

        fname = p.replace(" ", "_").replace("(", "").replace(")", "")
        path = CHART_DIR / f"monthly_heatmap_{fname}.png"
        fig.savefig(path)
        plt.close(fig)


# ═══════════════════════════════════════════════════════════
# Priority 5: Weight allocation stacked area
# ═══════════════════════════════════════════════════════════

ASSET_COLORS = {
    "credit":   "#1a5276",
    "bond_10y": "#2e86c1",
    "bond_30y": "#85c1e9",
    "hs300":    "#e74c3c",
    "us_sp500": "#e67e22",
    "gold":     "#d4a017",
    "nonferr":  "#8e44ad",
}

ASSET_LABELS = {
    "hs300": "沪深300", "us_sp500": "标普500", "credit": "信用债",
    "bond_10y": "10年国债", "bond_30y": "30年国债",
    "gold": "黄金", "nonferr": "有色金属",
}

FIXED_INCOME = ["credit", "bond_10y", "bond_30y"]
RISK_ASSETS = ["hs300", "us_sp500", "gold", "nonferr"]

_CHART_EVENTS = [
    ("2008 GFC",     "2008-09-15", "2009-03-09"),
    ("2015 股灾",    "2015-06-12", "2015-08-26"),
    ("2018 大熊市",  "2018-01-24", "2018-10-19"),
    ("2020 疫情",    "2020-02-19", "2020-03-23"),
    ("2022 股债双杀","2022-01-04", "2022-11-30"),
    ("2024-924",     "2024-09-23", "2024-10-08"),
]


def _draw_events(axes, top_ax, label_y=0.97):
    """在多个子图上绘制事件标注 — 灰底 + 虚线框 + 标签。"""
    for label, start, end in _CHART_EVENTS:
        s = pd.Timestamp(start)
        e = pd.Timestamp(end)
        for ax in axes:
            ax.axvspan(s, e, color="gray", alpha=0.12, lw=0, zorder=0.5)
            ax.axvline(s, color="#999999", lw=0.8, ls="--", alpha=0.5, zorder=0.5)
            ax.axvline(e, color="#999999", lw=0.8, ls="--", alpha=0.5, zorder=0.5)
        ymax = top_ax.get_ylim()[1]
        mid = s + (e - s) / 2
        top_ax.text(mid, ymax * label_y, label,
                    fontsize=7, color="#555555", ha="center", va="top",
                    bbox=dict(boxstyle="round,pad=0.15", facecolor="white",
                              edgecolor="#cccccc", alpha=0.85))


def plot_weight_stack(weight_history: dict):
    """各策略权重图 — 上：固收堆叠 + 下：风险资产折线 + 事件标注。"""
    _ensure_dir()

    for port, wh in weight_history.items():
        if wh.empty:
            continue
        wh_pct = wh * 100

        fi_cols = [c for c in FIXED_INCOME if c in wh_pct.columns]
        risk_cols = [c for c in RISK_ASSETS if c in wh_pct.columns]

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 8), sharex=True,
                                        gridspec_kw={"hspace": 0.08})

        if fi_cols:
            ax1.stackplot(wh_pct.index, *[wh_pct[c] for c in fi_cols],
                          colors=[ASSET_COLORS[c] for c in fi_cols],
                          labels=[ASSET_LABELS.get(c, c) for c in fi_cols],
                          alpha=0.85, lw=0.3, edgecolor="white")
            ax1.set_ylim(0, 100)
        ax1.set_ylabel("固收权重 (%)", fontsize=10)
        ax1.legend(loc="upper left", frameon=False, fontsize=6.5, ncol=len(fi_cols),
                   handlelength=1.0, handletextpad=0.3, columnspacing=0.5)
        ax1.grid(True, alpha=0.3, axis="y")
        ax1.set_title(f"{port} — 权重配置变化（100% RP）", fontsize=12, fontweight="bold")

        if risk_cols:
            for c in risk_cols:
                ax2.plot(wh_pct.index, wh_pct[c], color=ASSET_COLORS[c],
                         label=ASSET_LABELS.get(c, c), lw=0.8, alpha=0.85)
            ymax = max(wh_pct[risk_cols].max(axis=1).max() * 1.3, 10)
            ax2.set_ylim(-0.5, ymax)
        ax2.set_ylabel("风险权重 (%)", fontsize=10)
        ax2.legend(loc="upper left", frameon=False, fontsize=6.5, ncol=len(risk_cols),
                   handlelength=1.0, handletextpad=0.3, columnspacing=0.5)
        ax2.grid(True, alpha=0.3, axis="y")

        _draw_events([ax1, ax2], ax1)

        fig.autofmt_xdate()
        fname = port.replace(" ", "_").replace("(", "").replace(")", "")
        path = CHART_DIR / f"weights_{fname}.png"
        fig.savefig(path)
        plt.close(fig)
