"""过拟合分析 — 训练集 vs 全量集对比 + 参数消融。

方法论:
- 训练集: 全量数据去掉最近约 14 个月 — 调参、消融在此完成，禁止 peek 验证集
- 全量集: 完整数据 — 参数锁定后跑一次，若指标不崩则未过拟合
"""
import time
import pandas as pd
import numpy as np
from allweather.data import load_panel
from allweather.config import CASH_TIERS, OUTPUT_DIR
from allweather.backtest import backtest_iv
from allweather.strategy_b import backtest_b
from allweather.stats import perf_metrics

from allweather.config import BUCKET_GROUPS, V3C_ASSETS

V3B_RP_BUCKETS = {
    "增长↑":   ["hs300", "us_sp500"],
    "收益垫":  ["credit"],
    "增长↓":   ["bond_30y"],
    "通胀↑":   ["gold", "nonferr"],
}
V3B_RP_ASSETS = [a for assets in V3B_RP_BUCKETS.values() for a in assets]
V3B_ASSETS = [a for assets in BUCKET_GROUPS.values() for a in assets]

TRAIN_RATIO = 0.80  # 训练集比例，剩余 20% 为验证集


def run_all():
    panel = load_panel()
    rets = panel.pct_change().dropna()
    split_idx = int(len(rets) * TRAIN_RATIO)
    train_end = rets.index[split_idx]
    print(f"数据: {panel.index.min().date()} ~ {panel.index.max().date()}, {len(panel)} 天")
    print(f"训练集: {rets.index.min().date()} ~ {train_end.date()} ({split_idx}天)")
    print(f"验证集: {train_end.date()} ~ {rets.index.max().date()} ({len(rets) - split_idx}天)\n")

    train_rets = rets.iloc[:split_idx]

    # ── 1. 训练集: 当前 vs 纯策略 ──
    print("=" * 80)
    print(f"训练集 ({rets.index.min().date()} ~ {train_end.date()}) — 当前 vs 纯策略")
    print("=" * 80)
    train_results = compare_strategies(train_rets)

    # ── 2. 全量集: 当前 vs 纯策略 ──
    print("\n" + "=" * 80)
    print(f"全量集 ({rets.index.min().date()} ~ {rets.index.max().date()}) — 当前 vs 纯策略")
    print("=" * 80)
    full_results = compare_strategies(rets)

    # ── 3. 过拟合检测: 训练 → 全量 差异 ──
    print("\n" + "=" * 80)
    print("过拟合检测 — 训练集 → 全量集 指标变化")
    print("=" * 80)
    print_overfit_table(train_results, full_results)

    # ── 4. 参数消融 (仅训练集) ──
    print("\n" + "=" * 80)
    print(f"参数消融 — 训练集 ({rets.index.min().date()} ~ {train_end.date()})")
    print("=" * 80)
    ablation_results = ablation_study(train_rets)
    for strategy_name, variants in ablation_results.items():
        print(f"\n{strategy_name}:")
        print(f"  {'变体':35s}  {'CAGR':>7s}  {'MDD':>8s}  {'Sharpe':>7s}")
        print(f"  {'-'*35}  {'-'*7}  {'-'*8}  {'-'*7}")
        for label, m in variants.items():
            print(f"  {label:35s}  {m['cagr']:6.2%}  {m['mdd']:7.2%}  {m['sharpe']:6.2f}")

    save_ablation_csv(ablation_results)


def compare_strategies(rets):
    """跑三策略 × (当前 vs 纯策略) × 三档现金。"""
    results = {}

    # V3c
    for tier_label, c in CASH_TIERS:
        nv_curr, _ = backtest_iv(rets, cash_ratio=c, iv_window=60, max_w=0.30, min_w=0.03,
                                 nonferr_trend_window=60, assets=V3C_ASSETS,
                                 gold_dip_threshold=None,
                                 hs300_value_dip=True)
        nv_nodip, _ = backtest_iv(rets, cash_ratio=c, iv_window=60, max_w=0.30, min_w=0.03,
                                 nonferr_trend_window=60, assets=V3C_ASSETS,
                                 hs300_dip_threshold=None, gold_dip_threshold=None,
                                 hs300_value_dip=True)
        nv_pure, _ = backtest_iv(rets, cash_ratio=c, iv_window=60, max_w=0.30, min_w=0.03,
                                 nonferr_trend_window=0, assets=V3C_ASSETS,
                                 hs300_dip_threshold=None, gold_dip_threshold=None,
                                 gold_trend_filter=False)
        results[("V3c 当前", tier_label)] = perf_metrics(nv_curr)
        results[("V3c w/o 价格回撤", tier_label)] = perf_metrics(nv_nodip)
        results[("V3c 纯IV", tier_label)] = perf_metrics(nv_pure)

    # V3-B RP
    for tier_label, c in CASH_TIERS:
        nv_curr, _ = backtest_b(rets[V3B_RP_ASSETS], cash_ratio=c, rp_window=20,
                                rp_buckets=V3B_RP_BUCKETS,
                                nonferr_control="trend_filter", nonferr_trend_window=75,
                                gold_trend_filter=True, gold_trend_window=75,
                                equity_trend_assets=["us_sp500"], equity_trend_window=120,
                                hs300_value_dip=True)
        nv_nodip, _ = backtest_b(rets[V3B_RP_ASSETS], cash_ratio=c, rp_window=20,
                                rp_buckets=V3B_RP_BUCKETS,
                                nonferr_control="trend_filter", nonferr_trend_window=75,
                                hs300_dip_threshold=None,
                                gold_trend_filter=True, gold_trend_window=75,
                                equity_trend_assets=["us_sp500"], equity_trend_window=120,
                                hs300_value_dip=True)
        nv_pure, _ = backtest_b(rets[V3B_RP_ASSETS], cash_ratio=c, rp_window=20,
                                rp_buckets=V3B_RP_BUCKETS,
                                nonferr_control=None,
                                hs300_dip_threshold=None, gold_dip_threshold=None,
                                gold_trend_filter=False)
        results[("V3-B RP 当前", tier_label)] = perf_metrics(nv_curr)
        results[("V3-B RP w/o 价格回撤", tier_label)] = perf_metrics(nv_nodip)
        results[("V3-B RP 纯HRP", tier_label)] = perf_metrics(nv_pure)

    # V3-B Con
    for tier_label, c in CASH_TIERS:
        nv_curr, _ = backtest_b(rets[V3B_ASSETS], cash_ratio=c, rp_window=20,
                                max_w=0.25,
                                nonferr_control="trend_filter", nonferr_trend_window=75,
                                weighting_method="inverse_vol",
                                gold_dip_threshold=None,
                                hs300_value_dip=True)
        nv_nodip, _ = backtest_b(rets[V3B_ASSETS], cash_ratio=c, rp_window=20,
                                max_w=0.25,
                                nonferr_control="trend_filter", nonferr_trend_window=75,
                                weighting_method="inverse_vol",
                                hs300_dip_threshold=None, gold_dip_threshold=None,
                                hs300_value_dip=True)
        nv_pure, _ = backtest_b(rets[V3B_ASSETS], cash_ratio=c, rp_window=20,
                                max_w=0.25,
                                nonferr_control=None,
                                weighting_method="inverse_vol",
                                hs300_dip_threshold=None, gold_dip_threshold=None,
                                gold_trend_filter=False)
        results[("V3-B Con 当前", tier_label)] = perf_metrics(nv_curr)
        results[("V3-B Con w/o 价格回撤", tier_label)] = perf_metrics(nv_nodip)
        results[("V3-B Con 纯IV", tier_label)] = perf_metrics(nv_pure)

    # Print 100% RP
    print(f"  {'策略':25s}  {'CAGR':>7s}  {'MDD':>8s}  {'Sharpe':>7s}  {'Calmar':>7s}")
    print(f"  {'-'*25}  {'-'*7}  {'-'*8}  {'-'*7}  {'-'*7}")
    for (name, tier), m in results.items():
        if tier == "100% RP":
            print(f"  {name:25s}  {m['cagr']:6.2%}  {m['mdd']:7.2%}  {m['sharpe']:6.2f}  {m['calmar']:6.2f}")

    return results


def print_overfit_table(train_results, full_results):
    """训练 → 全量 指标变化，检测过拟合。"""
    strategies = [
        "V3c 当前", "V3c w/o 价格回撤", "V3c 纯IV",
        "V3-B RP 当前", "V3-B RP w/o 价格回撤", "V3-B RP 纯HRP",
        "V3-B Con 当前", "V3-B Con w/o 价格回撤", "V3-B Con 纯IV",
    ]

    print(f"  {'策略':20s}  {'阶段':4s}  {'CAGR':>7s}  {'MDD':>8s}  {'Sharpe':>7s}  {'Calmar':>7s}")
    print(f"  {'-'*20}  {'-'*4}  {'-'*7}  {'-'*8}  {'-'*7}  {'-'*7}")

    for name in strategies:
        t = train_results[(name, "100% RP")]
        f = full_results[(name, "100% RP")]
        print(f"  {name:20s}  {'训练':4s}  {t['cagr']:6.2%}  {t['mdd']:7.2%}  {t['sharpe']:6.2f}  {t['calmar']:6.2f}")
        print(f"  {'':20s}  {'全量':4s}  {f['cagr']:6.2%}  {f['mdd']:7.2%}  {f['sharpe']:6.2f}  {f['calmar']:6.2f}")
        print(f"  {'':20s}  {'Δ':4s}  {f['cagr']-t['cagr']:+6.2%}  {f['mdd']-t['mdd']:+7.2%}  {f['sharpe']-t['sharpe']:+6.2f}  {f['calmar']-t['calmar']:+6.2f}")
        print()


def ablation_study(rets):
    """逐个添加增强，看每项在训练集上的边际贡献。"""
    results = {}

    # ── V3c ──
    v3c = {}

    nv, _ = backtest_iv(rets, iv_window=60, max_w=0.30, min_w=0.03,
                        nonferr_trend_window=0, assets=V3C_ASSETS,
                        hs300_dip_threshold=None, gold_dip_threshold=None)
    v3c["纯IV (baseline)"] = perf_metrics(nv)

    nv, _ = backtest_iv(rets, iv_window=60, max_w=0.30, min_w=0.03,
                        nonferr_trend_window=60, assets=V3C_ASSETS,
                        hs300_dip_threshold=None, gold_dip_threshold=None,
                        hs300_value_dip=True)
    v3c["+ PE估值 (col7 30%ile 1.5x SMA90)"] = perf_metrics(nv)

    nv, _ = backtest_iv(rets, iv_window=60, max_w=0.30, min_w=0.03,
                        nonferr_trend_window=60, assets=V3C_ASSETS,
                        gold_dip_threshold=None, hs300_value_dip=False)
    v3c["+ 价格回撤 (25% SMA120 1.5x)"] = perf_metrics(nv)

    nv, _ = backtest_iv(rets, iv_window=60, max_w=0.30, min_w=0.03,
                        nonferr_trend_window=60, assets=V3C_ASSETS,
                        gold_dip_threshold=None, hs300_value_dip=True)
    v3c["完整版 (PE + 价格回撤)"] = perf_metrics(nv)

    results["V3c 多元"] = v3c

    # ── V3-B RP ──
    brp = {}

    nv, _ = backtest_b(rets[V3B_RP_ASSETS], rp_window=20,
                       rp_buckets=V3B_RP_BUCKETS,
                       nonferr_control=None,
                       hs300_dip_threshold=None, gold_dip_threshold=None,
                       gold_trend_filter=False)
    brp["纯HRP (baseline)"] = perf_metrics(nv)

    nv, _ = backtest_b(rets[V3B_RP_ASSETS], rp_window=20,
                       rp_buckets=V3B_RP_BUCKETS,
                       nonferr_control="trend_filter", nonferr_trend_window=75,
                       hs300_dip_threshold=None,
                       gold_trend_filter=True, gold_trend_window=75,
                       equity_trend_assets=["us_sp500"], equity_trend_window=120,
                       hs300_value_dip=True)
    brp["+ PE估值 (col7 30%ile 1.5x SMA90)"] = perf_metrics(nv)

    nv, _ = backtest_b(rets[V3B_RP_ASSETS], rp_window=20,
                       rp_buckets=V3B_RP_BUCKETS,
                       nonferr_control="trend_filter", nonferr_trend_window=75,
                       gold_trend_filter=True, gold_trend_window=75,
                       equity_trend_assets=["us_sp500"], equity_trend_window=120,
                       hs300_value_dip=False)
    brp["+ 价格回撤 (25% SMA120 1.5x)"] = perf_metrics(nv)

    nv, _ = backtest_b(rets[V3B_RP_ASSETS], rp_window=20,
                       rp_buckets=V3B_RP_BUCKETS,
                       nonferr_control="trend_filter", nonferr_trend_window=75,
                       gold_trend_filter=True, gold_trend_window=75,
                       equity_trend_assets=["us_sp500"], equity_trend_window=120,
                       hs300_value_dip=True)
    brp["完整版 (PE + 价格回撤)"] = perf_metrics(nv)

    results["V3-B 风险平价"] = brp

    # ── V3-B Con ──
    bcon = {}

    nv, _ = backtest_b(rets[V3B_ASSETS], rp_window=20, max_w=0.25,
                       weighting_method="inverse_vol",
                       nonferr_control=None,
                       hs300_dip_threshold=None, gold_dip_threshold=None)
    bcon["纯IV (baseline)"] = perf_metrics(nv)

    nv, _ = backtest_b(rets[V3B_ASSETS], rp_window=20, max_w=0.25,
                       weighting_method="inverse_vol",
                       nonferr_control="trend_filter", nonferr_trend_window=75,
                       hs300_dip_threshold=None, gold_dip_threshold=None,
                       hs300_value_dip=True)
    bcon["+ PE估值 (col7 30%ile 1.5x SMA90)"] = perf_metrics(nv)

    nv, _ = backtest_b(rets[V3B_ASSETS], rp_window=20, max_w=0.25,
                       weighting_method="inverse_vol",
                       nonferr_control="trend_filter", nonferr_trend_window=75,
                       gold_dip_threshold=None, hs300_value_dip=False)
    bcon["+ 价格回撤 (25% SMA120 1.5x)"] = perf_metrics(nv)

    nv, _ = backtest_b(rets[V3B_ASSETS], rp_window=20, max_w=0.25,
                       weighting_method="inverse_vol",
                       nonferr_control="trend_filter", nonferr_trend_window=75,
                       gold_dip_threshold=None, hs300_value_dip=True)
    bcon["完整版 (PE + 价格回撤)"] = perf_metrics(nv)

    results["V3-B 保守增强"] = bcon

    return results


def save_ablation_csv(ablation_results):
    rows = []
    for strategy, variants in ablation_results.items():
        for label, m in variants.items():
            rows.append({
                "策略": strategy,
                "变体": label,
                "CAGR": f"{m['cagr']:.4%}",
                "Vol": f"{m['vol']:.4%}",
                "MDD": f"{m['mdd']:.4%}",
                "Sharpe": f"{m['sharpe']:.4f}",
                "Calmar": f"{m['calmar']:.4f}",
                "累计收益": f"{m['cum_return']:.4%}",
                "期末净值": f"{m['final_nv']:.4f}",
            })

    df = pd.DataFrame(rows)
    path = OUTPUT_DIR / "overfit_analysis.csv"
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"\n详细结果已保存: {path}")


if __name__ == "__main__":
    t0 = time.time()
    run_all()
    print(f"\n总耗时: {time.time() - t0:.1f}s")