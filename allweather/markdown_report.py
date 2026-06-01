"""Markdown 综合报告 - 把控制台 9 张表渲染成 GitHub 友好的 Markdown。

输出 output/report.md。
"""
from datetime import datetime
import pandas as pd

from .config import BUCKET_GROUPS, ETF_META, OUTPUT_DIR
from .config import PORTFOLIO_TAGS


def _pct(v, d=2, sign=False):
    """百分比格式化。"""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "n/a"
    s = f"{v*100:+.{d}f}%" if sign else f"{v*100:.{d}f}%"
    return s


def _num(v, d=2):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "n/a"
    return f"{v:.{d}f}"


def _money(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "n/a"
    return f"{v:,.0f}"


def _md_table(headers, rows):
    """渲染一张 Markdown 表。"""
    out = ["| " + " | ".join(str(h) for h in headers) + " |"]
    out.append("|" + "|".join(["---"] * len(headers)) + "|")
    for row in rows:
        out.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(out)


# ============================================================
# 各章节
# ============================================================

def _section_header():
    return [
        "# 桥水全天候策略 · 中国版 · 回测综合报告",
        "",
        f"> 自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "> 完整文档见 [GitHub Pages](https://idealauror.github.io/all-weather-portfolio/)",
        "",
    ]


def _section_recommendation():
    items = sorted(PORTFOLIO_TAGS.items(), key=lambda kv: -len(kv[1]["stars"]))
    notes = {
        "V3c 多元": "实战派 — 6资产逆波动率 60d + nonferr 趋势过滤 + HS300抄底，CAGR 9.37%",
        "V3-B 风险平价(20d)": "学院派 — 4桶分层风险平价(30Y) + nonferr/gold/sp500 趋势过滤 + Gold/HS300抄底，CAGR 11.40%",
        "V3-B 保守增强(20d)": "保守增强 — 逆波动率+nonferr趋势过滤+HS300抄底，Sharpe 最高（1.68）",
    }
    rows = [(tag["stars"], port, tag["label"], notes.get(port, ""))
            for port, tag in items]
    return [
        "## 方案推荐",
        "",
        _md_table(["推荐度", "方案", "标签", "说明"], rows),
        "",
        "> **V3c** 和 **V3-B** 是两条不同路线的 ★★★ 推荐：V3-B 4桶(30Y) CAGR 最高（11.40%），V3c 落地最简单，保守增强 Sharpe 最高（1.68）适合低波动偏好。",
        "",
    ]


def _section_perf(perf_results):
    rows = []
    for (port, tier), m in perf_results.items():
        rows.append([
            port, tier,
            _pct(m["cum_return"]),
            _pct(m["cagr"]),
            _pct(m["vol"]),
            _pct(m["mdd"]),
            _num(m["sharpe"]),
            _num(m["calmar"]),
            _num(m["final_nv"], d=4),
            _pct(m["geometric_excess_d"], d=3, sign=True),
        ])
    return [
        "## 1. 核心指标（三策略 × 三档现金）",
        "",
        _md_table(
            ["方案", "档位", "累计收益", "CAGR", "波动", "最大回撤", "Sharpe", "Calmar", "期末净值", "D_excess"],
            rows,
        ),
        "",
    ]


def _section_yearly(yearly_results, years=None):
    if years is None:
        years = list(range(2008, 2026))
    rows = []
    for port, s in yearly_results.items():
        row = [port] + [_pct(s.get(y, None), sign=True) for y in years]
        rows.append(row)
    return [
        "## 2. 分年化收益（100% RP 档）",
        "",
        _md_table(["方案"] + [str(y) for y in years], rows),
        "",
    ]


def _section_risk_contrib(rc_results):
    if not rc_results:
        return []
    # 判断是静态快照还是时变结果
    sample = next(iter(rc_results.values()))
    is_tv = isinstance(sample, dict) and any(
        isinstance(v, dict) and "mean" in v for v in sample.values()
    )

    if is_tv:
        ports = list(rc_results.keys())
        buckets = [k for k in list(rc_results[ports[0]].keys()) if not k.startswith("_")]
        rows = []
        for b in buckets:
            row = [b]
            for p in ports:
                v = rc_results[p][b]
                row.append(f"{_pct(v['mean'])} ± {_pct(v['std'])}")
            rows.append(row)
        # 风险集中度
        conc_rows = []
        for p in ports:
            vals = [rc_results[p][b]["mean"] for b in buckets]
            positive_vals = [v for v in vals if v > 0.001]
            if positive_vals:
                ratio = max(positive_vals) / min(positive_vals)
            else:
                ratio = float("nan")
            conc_rows.append(f"- **{p}** 风险集中度 (max/min): {ratio:.2f}x"
                             if not pd.isna(ratio)
                             else f"- **{p}** 风险集中度: n/a")
        return [
            "## 3. 桶级风险贡献归因（时变 · 日均值 ± 1σ）",
            "",
            _md_table(["桶"] + ports, rows),
            "",
        ] + conc_rows + [""]

    ports = list(rc_results.keys())
    buckets = list(rc_results[ports[0]].keys())
    rows = []
    for b in buckets:
        rows.append([b] + [_pct(rc_results[p][b]) for p in ports])
    return [
        "## 3. 桶级风险贡献（协方差视角）",
        "",
        _md_table(["桶"] + ports, rows),
        "",
    ]


def _section_weight_stability(ws_results):
    if not ws_results:
        return []
    rows = []
    for port, s in ws_results.items():
        rows.append([
            port,
            _pct(s["monthly_turnover_mean"]),
            _pct(s["monthly_turnover_max"]),
            _num(s["annual_churn"]),
            _num(s["effective_n_mean"], d=2),
            _num(s.get("effective_n_min", 0), d=2),
            _pct(s["cost_drag_annual"]),
        ])
    return [
        "## 3b. 权重稳定性分析（假设单边成本 10bp）",
        "",
        _md_table(
            ["方案", "月均换手", "月最大换手", "年化换手", "有效资产N", "有效N-min", "年成本拖累"],
            rows,
        ),
        "",
    ]


def _section_signal_summary(signal_logs: dict):
    """信号触发频率汇总（Markdown）。"""
    if not signal_logs:
        return []

    signal_cols = {
        "nonferr_filtered":     "有色趋势过滤",
        "gold_filtered":        "黄金趋势过滤",
        "us_sp500_filtered":    "SP500趋势过滤",
        "gold_dip_active":      "黄金抄底",
        "active":               "HS300抄底",
    }

    parts = ["## 3c. 风控信号触发频率汇总（年均次数）", ""]

    for label, sl in signal_logs.items():
        if sl.empty:
            continue
        sl = sl.copy()
        if "date" in sl.columns:
            sl["year"] = pd.to_datetime(sl["date"]).dt.year
        else:
            continue

        avail = {k: v for k, v in signal_cols.items() if k in sl.columns}
        if not avail:
            continue

        parts.append(f"### {label}")
        parts.append("")

        years_list = sorted(sl["year"].unique())
        headers = ["年度"] + list(avail.values())
        rows = []
        for y in years_list:
            ydata = sl[sl["year"] == y]
            row = [str(y)]
            for k in avail:
                if sl[k].dtype == bool or sl[k].dropna().isin([0, 1]).all():
                    row.append(str(int(ydata[k].sum())))
                else:
                    row.append(str(int((ydata[k] > 0).sum())))
            rows.append(row)

        # 合计行
        total_row = ["合计"]
        for k in avail:
            series = sl[k]
            if series.dtype == bool or series.dropna().isin([0, 1]).all():
                total_row.append(str(int(series.sum())))
            else:
                total_row.append(str(int((series > 0).sum())))
        rows.append(total_row)

        parts.append(_md_table(headers, rows))
        parts.append("")

    return parts


def _section_regime(regime_results):
    ports = list(regime_results.keys())
    regimes = ["股牛+债牛", "股牛+债熊", "股熊+债牛", "股熊+债熊"]
    first = regime_results[ports[0]]
    headers = ["方案"] + [f"{r}（n={first[r]['n']}）" for r in regimes]
    rows = []
    for p in ports:
        row = [p] + [_pct(regime_results[p][r]["avg"], sign=True) for r in regimes]
        rows.append(row)
    return [
        "## 4. 4 宏观情景平均季度收益（100% RP 档）",
        "",
        _md_table(headers, rows),
        "",
    ]


def _section_events(event_results):
    ports = list(event_results.keys())
    events = list(event_results[ports[0]].keys())
    rows = []
    for ev in events:
        row = [ev] + [_pct(event_results[p][ev], sign=True) for p in ports]
        rows.append(row)
    return [
        "## 5. 关键事件期累计收益（100% RP 档）",
        "",
        _md_table(["事件"] + ports, rows),
        "",
    ]


def _section_rolling(rolling_results):
    rows = []
    for port, s in rolling_results.items():
        rows.append([
            port,
            _pct(s["ann_min"], sign=True),
            _pct(s["ann_med"], sign=True),
            _pct(s["ann_max"], sign=True),
            _pct(s["dd_min"], sign=True),
            _pct(s["neg_year_pct"]),
        ])
    return [
        "## 6. 滚动 1 年统计（100% RP 档）",
        "",
        _md_table(
            ["方案", "年化-min", "年化-中位", "年化-max", "1y回撤-最差", "负收益年%"],
            rows,
        ),
        "",
    ]


def _section_bootstrap(boot_results):
    rows = []
    for port, b in boot_results.items():
        rows.append([
            port,
            _pct(b["p05"], sign=True),
            _pct(b["p25"], sign=True),
            _pct(b["p50"], sign=True),
            _pct(b["p75"], sign=True),
            _pct(b["p95"], sign=True),
            _pct(b["ann_median"]),
            _pct(b["loss_prob"]),
        ])
    return [
        "## 7. Block Bootstrap 5 年累计收益分布（1000 次模拟）",
        "",
        _md_table(
            ["方案", "5%分位", "25%分位", "中位数", "75%分位", "95%分位", "年化中位", "亏损概率"],
            rows,
        ),
        "",
    ]


def _section_holdings(weights_dict, principal=1_000_000):
    ports = list(weights_dict.keys())
    rows = []
    for bk, lst in BUCKET_GROUPS.items():
        for asset in lst:
            meta = ETF_META[asset]
            row = [bk, meta["name"], meta["code"]]
            for p in ports:
                row.append(_money(weights_dict[p].get(asset, 0) * principal))
            rows.append(row)
    rows.append(["**合计**", "", ""] + [_money(principal) for _ in ports])
    return [
        f"## 8. 持仓清单（按 {principal:,.0f} 本金，100% RP 档）",
        "",
        _md_table(["桶", "资产", "代码"] + ports, rows),
        "",
    ]


def _section_weights(weights_dict):
    if not weights_dict:
        return []
    ports = list(weights_dict.keys())
    assets = list(weights_dict[ports[0]].index)
    rows = []
    for a in assets:
        rows.append([a] + [_pct(weights_dict[p][a]) for p in ports])
    rows.append(["**合计**"] + [_pct(weights_dict[p].sum()) for p in ports])
    return [
        "## 9. 权重明细",
        "",
        _md_table(["资产"] + ports, rows),
        "",
    ]


def _section_footer():
    return [
        "---",
        "",
        "## 输出文件清单",
        "",
        "| 文件 | 说明 |",
        "|---|---|",
        "| `output/report.xlsx` | Excel 多 sheet 综合报告（11 sheet）|",
        "| `output/report.md` | 本文件 |",
        "| `output/nv_curves.csv` | 9 条净值曲线（宽表）|",
        "| `output/summary.json` | 核心指标汇总 |",
        "| `output/weights.csv` | 三策略权重 |",
        "| `experiments.jsonl` | 实验日志（`--note` 可附带结论）|",
        "",
    ]


# ============================================================
# 主入口
# ============================================================

def save_markdown_report(
    nv_results,
    perf_results,
    yearly_results,
    rc_results,
    regime_results,
    event_results,
    rolling_results,
    boot_results,
    weights_dict,
    filename="report.md",
    ws_results=None,
    signal_logs=None,
    rc_tv_results=None,
):
    """生成 output/report.md。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    parts = []
    parts.extend(_section_header())
    parts.extend(_section_recommendation())
    parts.extend(_section_perf(perf_results))
    parts.extend(_section_yearly(yearly_results))
    parts.extend(_section_risk_contrib(rc_results))
    parts.extend(_section_weight_stability(ws_results or {}))
    parts.extend(_section_signal_summary(signal_logs or {}))
    parts.extend(_section_regime(regime_results))
    parts.extend(_section_events(event_results))
    parts.extend(_section_rolling(rolling_results))
    parts.extend(_section_bootstrap(boot_results))
    parts.extend(_section_holdings(weights_dict))
    parts.extend(_section_weights(weights_dict))
    parts.extend(_section_footer())

    path = OUTPUT_DIR / filename
    path.write_text("\n".join(parts), encoding="utf-8")
    return path
