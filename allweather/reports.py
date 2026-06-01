"""控制台 / 文件报告渲染。"""
import io
import json
from pathlib import Path
import pandas as pd
from .config import (
    OUTPUT_DIR,
)

LINE = "=" * 100


def _fmt_pct(v, w=8, d=2, sign=False):
    if pd.isna(v):
        return f"{'n/a':>{w}}"
    sign_str = "+" if sign else ""
    return f"{v*100:>{sign_str}{w-1}.{d}f}%"


def _fmt_num(v, w=8, d=2):
    if pd.isna(v):
        return f"{'n/a':>{w}}"
    return f"{v:>{w}.{d}f}"


# ============================================================
# 控制台输出 (供 main.py 主流程使用)
# ============================================================

def print_header(text, char="=", width=100):
    print(char * width)
    print(f"  {text}")
    print(char * width)


def print_subheader(text):
    print(f"\n  >> {text}")
    print("  " + "-" * 80)


def print_perf_table(perf_results: dict):
    """三策略 × 三档现金 核心指标表。

    perf_results: {(port, tier_label): perf_metrics dict, ...}
    """
    print_header("【1】三策略 × 三档现金 核心收益指标")
    print(f"  {'方案':<14}{'档位':<10}{'累计收益':>10}{'CAGR':>9}"
          f"{'波动':>8}{'最大回撤':>10}{'Sharpe':>8}{'Calmar':>8}{'期末净值':>10}{'D_excess':>10}")
    last_port = None
    for (port, tier), m in perf_results.items():
        if port != last_port and last_port is not None:
            print()
        last_port = port
        print(f"  {port:<14}{tier:<10}"
              f"{_fmt_pct(m['cum_return'], w=10):>10}"
              f"{_fmt_pct(m['cagr'], w=9):>9}"
              f"{_fmt_pct(m['vol'], w=8):>8}"
              f"{_fmt_pct(m['mdd'], w=10):>10}"
              f"{_fmt_num(m['sharpe']):>8}"
              f"{_fmt_num(m['calmar']):>8}"
              f"{m['final_nv']:>10.4f}"
              f"{_fmt_pct(m['geometric_excess_d'], w=10, d=3, sign=True):>10}")


def print_d_significance(d_sig: dict):
    """D_excess 统计显著性表。d_sig: {port: d_significance dict, ...}"""
    if not d_sig:
        return
    print_header("D_excess 统计显著性（正态参数 Bootstrap × 10000）")
    print(f"  {'方案':<25}{'D_actual':>10}{'null均值':>10}{'95% CI低':>10}{'95% CI高':>10}{'分位':>8}{'显著?':>8}")
    for port, ds in d_sig.items():
        sig = "**" if ds["significant_05"] else "—"
        print(f"  {port:<25}"
              f"{_fmt_pct(ds['d_actual'], w=10, d=3, sign=True):>10}"
              f"{_fmt_pct(ds['d_null_mean'], w=10, d=3, sign=True):>10}"
              f"{_fmt_pct(ds['ci_95_low'], w=10, d=3, sign=True):>10}"
              f"{_fmt_pct(ds['ci_95_high'], w=10, d=3, sign=True):>10}"
              f"{ds['percentile']*100:>7.1f}%"
              f"{sig:>8}")
    print()
    print("  D ≈ null 均值 + 分位 ≈ 50% → 收益分布与正态无异，零尾部风险证据")
    print("  D << null 低分位(>97.5%) → 显著负偏/肥尾，存在隐藏风险")
    print("  ** 表示在 5% 水平上统计显著")


def print_yearly_table(yearly_results: dict, years=None):
    """分年化收益表。yearly_results: {port: pd.Series}"""
    print_header("【2】分年化收益（100% RP 档）")
    if years is None:
        years = list(range(2008, 2026))
    print(f"  {'方案':<14}" + "".join(f"{y:>9}" for y in years))
    for port, s in yearly_results.items():
        line = f"  {port:<14}"
        for y in years:
            line += _fmt_pct(s.get(y, float("nan")), w=9, sign=True)
        print(line)


def print_risk_contribution(rc_results: dict):
    if not rc_results:
        return
    # 判断是静态快照还是时变结果
    sample = next(iter(rc_results.values()))
    # 时变格式：值嵌套 {"mean": ..., "std": ...}
    is_tv = isinstance(sample, dict) and any(
        isinstance(v, dict) and "mean" in v for v in sample.values()
    )
    if is_tv:
        print_header("【3】桶级风险贡献归因（时变 · 日均值 ± 1σ）")
        ports = list(rc_results.keys())
        buckets = [k for k in list(rc_results[ports[0]].keys()) if not k.startswith("_")]
        print(f"  {'桶':<22}" + "".join(f"{p:>22}" for p in ports))
        for b in buckets:
            line = f"  {b:<22}"
            for p in ports:
                v = rc_results[p][b]
                line += f"{_fmt_pct(v['mean'], w=8)}±{_fmt_pct(v['std'], w=8)}"
            print(line)
        # 风险集中度：max/min 非零桶均值
        for p in ports:
            vals = [rc_results[p][b]["mean"] for b in buckets]
            positive_vals = [v for v in vals if v > 0.001]
            if positive_vals:
                ratio = max(positive_vals) / min(positive_vals)
            else:
                ratio = float("nan")
            print(f"    {p} 风险集中度(max/min): {ratio:.2f}x" if not pd.isna(ratio)
                  else f"    {p} 风险集中度: n/a")
    else:
        print_header("【3】桶级风险贡献分解（协方差视角）")
        ports = list(rc_results.keys())
        buckets = list(rc_results[ports[0]].keys())
        print(f"  {'桶':<22}" + "".join(f"{p:>14}" for p in ports))
        for b in buckets:
            line = f"  {b:<22}"
            for p in ports:
                line += _fmt_pct(rc_results[p][b], w=14)
            print(line)


def print_weight_stability_table(ws_results: dict):
    """权重稳定性表。ws_results: {port: weight_stability dict}"""
    if not ws_results:
        return
    print_header("【3b】权重稳定性分析（假设单边成本 10bp）")
    print(f"  {'方案':<22}{'月均换手':>10}{'月最大换手':>10}{'年化换手':>10}"
          f"{'有效资产N':>12}{'有效N-min':>10}{'年成本拖累':>12}")
    for port, s in ws_results.items():
        print(f"  {port:<22}"
              f"{_fmt_pct(s['monthly_turnover_mean'], w=10)}"
              f"{_fmt_pct(s['monthly_turnover_max'], w=10)}"
              f"{_fmt_num(s['annual_churn'], w=10)}"
              f"{_fmt_num(s['effective_n_mean'], w=12, d=2)}"
              f"{_fmt_num(s['effective_n_min'], w=10, d=2)}"
              f"{_fmt_pct(s['cost_drag_annual'], w=12)}")


def print_signal_summary(signal_logs: dict):
    """信号触发频率汇总。signal_logs: {label: pd.DataFrame}"""
    if not signal_logs:
        return
    print_header("【3c】风控信号触发频率汇总（年均次数）")

    # 定义各策略关心的信号列
    signal_cols = {
        "nonferr_filtered":     "有色趋势过滤",
        "gold_filtered":        "黄金趋势过滤",
        "us_sp500_filtered":    "SP500趋势过滤",
        "gold_dip_active":      "黄金抄底",
        "active":               "HS300抄底",
    }

    for label, sl in signal_logs.items():
        if sl.empty:
            continue
        sl = sl.copy()
        if "date" in sl.columns:
            sl["year"] = pd.to_datetime(sl["date"]).dt.year
        else:
            continue

        print_subheader(f"{label}")
        # 只取该策略实际存在的信号列
        avail = {k: v for k, v in signal_cols.items() if k in sl.columns}
        if not avail:
            print("    （无信号列）")
            continue

        yearly = sl.groupby("year")
        years_list = sorted(sl["year"].unique())
        print(f"  {'年度':<8}" + "".join(f"{v:>14}" for v in avail.values()))
        for y in years_list:
            ydata = yearly.get_group(y)
            line = f"  {y:<8}"
            for k in avail:
                if k in sl.columns:
                    if sl[k].dtype == bool or sl[k].dropna().isin([0, 1]).all():
                        count = ydata[k].sum()
                    else:
                        count = (ydata[k] > 0).sum()
                    line += f"{int(count):>14}"
                else:
                    line += f"{'n/a':>14}"
            print(line)

        # 合计行
        line = f"  {'合计':<8}"
        for k in avail:
            if k in sl.columns:
                total = int(sl[k].sum()) if sl[k].dtype == bool or sl[k].dropna().isin([0, 1]).all() else int((sl[k] > 0).sum())
                line += f"{total:>14}"
            else:
                line += f"{'n/a':>14}"
        print(line)


def print_regime_table(regime_results: dict):
    print_header("【4】4 宏观情景平均季度收益（100% RP 档）")
    ports = list(regime_results.keys())
    first = regime_results[ports[0]]
    headers = [f"{r}({first[r]['n']})" for r in
               ["股牛+债牛", "股牛+债熊", "股熊+债牛", "股熊+债熊"]]
    print(f"  {'方案':<22}" + "".join(f"{h:>14}" for h in headers))
    for p, regimes in regime_results.items():
        line = f"  {p:<22}"
        for r in ["股牛+债牛", "股牛+债熊", "股熊+债牛", "股熊+债熊"]:
            line += _fmt_pct(regimes[r]["avg"], w=14, sign=True)
        print(line)


def print_event_table(event_results: dict):
    print_header("【5】关键事件期收益（100% RP 档）")
    ports = list(event_results.keys())
    print(f"  {'事件':<22}" + "".join(f"{p:>14}" for p in ports))
    events = list(event_results[ports[0]].keys())
    for ev in events:
        line = f"  {ev:<22}"
        for p in ports:
            line += _fmt_pct(event_results[p][ev], w=14, sign=True)
        print(line)


def print_rolling_table(rolling_results: dict):
    print_header("【6】滚动 1 年表现统计（100% RP 档）")
    print(f"  {'方案':<14}{'年化-min':>10}{'年化-中位':>10}{'年化-max':>10}"
          f"{'1y回撤-最差':>14}{'负收益年%':>12}")
    for port, s in rolling_results.items():
        print(f"  {port:<14}"
              f"{_fmt_pct(s['ann_min'], w=10, sign=True)}"
              f"{_fmt_pct(s['ann_med'], w=10, sign=True)}"
              f"{_fmt_pct(s['ann_max'], w=10, sign=True)}"
              f"{_fmt_pct(s['dd_min'], w=14, sign=True)}"
              f"{_fmt_pct(s['neg_year_pct'], w=12)}")


def print_bootstrap_table(boot_results: dict):
    print_header("【7】Block Bootstrap 5 年期累计收益分布（1000 次模拟）")
    print(f"  {'方案':<14}{'5%分位':>10}{'25%分位':>10}{'中位数':>10}"
          f"{'75%分位':>10}{'95%分位':>10}{'年化中位':>10}{'亏损概率':>10}")
    for port, b in boot_results.items():
        print(f"  {port:<14}"
              f"{_fmt_pct(b['p05'], w=10, sign=True)}"
              f"{_fmt_pct(b['p25'], w=10, sign=True)}"
              f"{_fmt_pct(b['p50'], w=10, sign=True)}"
              f"{_fmt_pct(b['p75'], w=10, sign=True)}"
              f"{_fmt_pct(b['p95'], w=10, sign=True)}"
              f"{_fmt_pct(b['ann_median'], w=10)}"
              f"{_fmt_pct(b['loss_prob'], w=10)}")


def print_summary_recommendation():
    print_header("【9】策略评估与推荐", char="*", width=100)
    print()

    cards = [
        ("V3c 多元", "★★★", "简约派", "6资产逆波动率 60d + nonferr趋势过滤(75d) + HS300 AND抄底",
         ["+ 资产最少(6个)，执行最简单",
          "+ 回撤可控(-7.01%)，回报稳健(8.93%)",
          "+ 每月调仓一次，交易频率低",
          "- 无桶级风控，单资产上限 30% 较宽松",
          "- 长期回报低于 V3-B RP"],
         "适合：初入全天候、不想研究桶逻辑、追求简单透明"),

        ("V3-B 风险平价(20d)", "★★★", "学院派", "4桶等权 HRP + nonferr(75d) + Gold(75d) + SP500(120d) + HS300 AND抄底",
         ["+ 长期回报最高 CAGR 10.03%，累计 799%",
          "+ 四桶真正等权(25%x4)，全天候理念最纯正",
          "+ 桶级分散 + 资产级分散 + 三趋势过滤三重风控",
          "- 回撤(-9.48%)，最差年份 2011 -1.22%",
          "- 4桶逻辑比另外两个策略复杂"],
         "适合：长期持有者(5年+)、认同正统全天候理念、能承受短期波动"),

        ("V3-B 风险平价桶(20d)", "★★★", "预算派", "4桶逆波动率 HRP + 同三趋势过滤 + HS300 AND抄底",
         ["+ 桶风险最均衡(max/min 3.85x)，实际落地风险平价",
          "+ Sharpe 最高(1.66)，风险调整后效率最优",
          "+ 所有年份正收益，波动率最低(3.71%)",
          "+ Bootstrap 5年亏损概率 0.00%",
          "- CAGR 8.38% 低于等权版(10.03%)",
          "- 无杠杆，债券风险贡献仍低于权益"],
         "适合：追求风险均衡、Sharpe优先、无法接受负收益年份"),

        ("V3-B 保守增强(20d)", "★★★", "保守增强", "逆波动率 20d + nonferr趋势(75d) + HS300 AND抄底，max_w=0.25",
         ["+ 回撤最低(-6.40%)，Sharpe 最高(1.75)",
          "+ 熊市表现最好(2008 +14.95%，2022 +3.42%)",
          "+ 风险调整后效率最优",
          "- 牛市可能跑输(2019 +7.58%，2017 +2.67%)",
          "- 长期累计回报最低(369%)"],
         "适合：保守型资金、退休/教育金、无法承受大幅回撤"),
    ]

    for name, stars, tagline, desc, items, audience in cards:
        print(f"  {stars} {name} ({tagline})")
        print(f"     {desc}")
        for item in items:
            print(f"     {item}")
        print(f"     {audience}")
        print()

    print("  ── 一句话选策略 ──")
    print("  要简单 → V3c   要高回报 → V3-B RP   要均衡 → V3-B 风险平价桶   要不亏钱 → V3-B 保守增强")
    print()


# ============================================================
# 持久化输出
# ============================================================

def save_nv_curves(nv_dict: dict, filename: str = "nv_curves.csv"):
    """nv_dict: {(port, tier): pd.Series}, 转成宽表保存。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # 列名: V3c 多元_100% RP
    df = pd.DataFrame({f"{p}_{t}": nv for (p, t), nv in nv_dict.items()})
    path = OUTPUT_DIR / filename
    df.to_csv(path, encoding="utf-8-sig")
    return path


def save_summary_json(perf_results: dict, filename: str = "summary.json"):
    """保存汇总指标 JSON。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = {}
    for (port, tier), m in perf_results.items():
        out[f"{port}_{tier}"] = {k: float(v) if pd.notna(v) else None
                                  for k, v in m.items()}
    path = OUTPUT_DIR / filename
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return path

