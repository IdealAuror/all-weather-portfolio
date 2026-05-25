"""诊断 V3-A 和 V3-B 相对 V3c 的性能拖累来源。

输出：
  1. V3-A: 趋势过滤误判分析、回撤止损时机、现金拖累
  2. V3-B: 波动率目标缩放、相关性断路器激活频率、权重换手率
"""
import pandas as pd
import numpy as np
from allweather.data import load_panel_extended
from allweather.portfolios import get_weights
from allweather.config import (
    CASH_TIERS, REBAL_THRESHOLD, RISK_FREE_RATE, ETF_META,
    TREND_LOOKBACK_MONTHS, DRAWDOWN_STOP as DD_STOP,
    DRAWDOWN_RECOVER, DRAWDOWN_TARGET_CAP,
    RISK_PARITY_WINDOW, RISK_PARITY_MAX_WEIGHT, RISK_PARITY_MIN_WEIGHT,
    CORR_BREAKER_THRESHOLD, CORR_BREAKER_RECOVER, CORR_BREAKER_CAP,
    VOL_TARGET, BUCKET_GROUPS,
)
from allweather.risk import (
    trend_filter, drawdown_stop, vol_target_scale,
    correlation_breaker, hierarchical_rp_weights,
)


def diagnose_a():
    """V3-A 诊断：量化三层风控各自的拖累。"""
    print("=" * 90)
    print("  V3-A 保守 策略诊断")
    print("=" * 90)

    panel = load_panel_extended()
    rets = panel.pct_change().dropna()
    weights = get_weights()
    w = weights["V3-A 保守"]
    cols = list(w.index)

    cash_ratio = 0.0
    target = w.values
    h = pd.Series(target, index=cols)
    v = 1.0
    nv = pd.Series(index=rets.index, dtype=float)
    n_rebal = 0
    n_trend_trig = 0
    n_dd_trig = 0
    in_drawdown_stop = False

    # 跟踪每个资产被趋势过滤逐出的时间
    trend_out_days = {a: 0 for a in cols}
    dd_stop_days = 0
    total_days = 0

    # 记录每次事件的日期和上下文
    trend_events = []
    dd_events = []

    for i, d in enumerate(rets.index):
        if i == 0:
            nv.loc[d] = 1.0
            continue

        total_days += 1
        v *= 1 + (h * rets.loc[d, cols]).sum() + cash_ratio * RISK_FREE_RATE
        nv.loc[d] = v
        h = h * (1 + rets.loc[d, cols])
        s = h.sum()
        if s > 0:
            h = h / s * (1 - cash_ratio)

        # Monthly trend filter
        if d.month != rets.index[i - 1].month:
            lookback_days = TREND_LOOKBACK_MONTHS * 21
            triggered_assets = []
            for a in cols:
                asset_ret = rets.loc[:d, a].tail(lookback_days)
                if trend_filter(asset_ret):
                    h[a] = 0.0
                    n_trend_trig += 1
                    triggered_assets.append(a)
                    trend_out_days[a] += 1
            for a in cols:
                if h[a] == 0.0:
                    asset_ret = rets.loc[:d, a].tail(lookback_days)
                    if not trend_filter(asset_ret):
                        h[a] = target[a]
            if triggered_assets:
                trend_events.append((d, triggered_assets,
                                     [(a, (1 + rets.loc[:d, a].tail(252)).prod() - 1)
                                      for a in triggered_assets]))
            s = h.sum()
            if s > 0:
                h = h / s * (1 - cash_ratio)

        # Drawdown stop
        if in_drawdown_stop:
            dd_stop_days += 1
            if not drawdown_stop(nv.loc[:d], DRAWDOWN_RECOVER):
                in_drawdown_stop = False
                dd_events.append((d, "recover"))
        else:
            if drawdown_stop(nv.loc[:d], DD_STOP):
                in_drawdown_stop = True
                h = h * DRAWDOWN_TARGET_CAP
                n_dd_trig += 1
                n_rebal += 1
                dd_events.append((d, "trigger",
                                  (nv.loc[:d].iloc[-1] / nv.loc[:d].cummax().iloc[-1] - 1)))

        if not in_drawdown_stop:
            triggered = abs(h.values - target).max() > REBAL_THRESHOLD
            if triggered:
                h = pd.Series(target, index=cols)
                n_rebal += 1

    # --- 计算结果 ---
    cum_ret = nv.iloc[-1] - 1
    cagr = (nv.iloc[-1]) ** (252 / len(nv)) - 1
    ret_series = nv.pct_change().dropna()
    vol = ret_series.std() * np.sqrt(252)
    mdd = ((nv / nv.cummax()) - 1).min()
    sharpe = (cagr - 0.022) / vol

    print(f"\n核心指标: CAGR={cagr:.2%}  Vol={vol:.2%}  MDD={mdd:.2%}  Sharpe={sharpe:.2f}")
    print(f"总交易日: {total_days}  调仓次数: {n_rebal}")

    # 趋势过滤统计
    print(f"\n--- 趋势过滤 ---")
    print(f"触发总次数: {n_trend_trig} (月度检查，每个资产独立计数)")
    for a in cols:
        pct = trend_out_days[a] / total_days * 100
        meta = ETF_META[a]
        print(f"  {meta['name']:<20} 被过滤 {trend_out_days[a]:>4}天 ({pct:.1f}%)")

    # 列出趋势过滤的关键事件
    print(f"\n趋势过滤事件详情 (最近10次):")
    for d, assets, rets_12m in trend_events[-10:]:
        names = [ETF_META[a]['name'] for a in assets]
        details = [f"{ETF_META[a]['name']}(12m:{r*100:.1f}%)" for a, r in rets_12m]
        print(f"  {d.date()} 触发: {', '.join(details)}")

    # 回撤止损统计
    print(f"\n--- 回撤止损 ---")
    print(f"触发次数: {n_dd_trig}  处于止损状态天数: {dd_stop_days} ({dd_stop_days/total_days*100:.1f}%)")
    for d, ev_type, *rest in dd_events:
        if ev_type == "trigger":
            print(f"  {d.date()} 触发止损 DD={rest[0]:.2%}")
        else:
            print(f"  {d.date()} 恢复")

    # 现金拖累：计算趋势过滤+回撤止损期间的 effective cash ratio
    print(f"\n--- 现金暴露分析 ---")
    # 重新运行但记录每日的 effective risk exposure
    exposures = []
    h2 = pd.Series(w.values, index=cols)
    in_dd2 = False
    for i, d in enumerate(rets.index):
        if i == 0:
            exposures.append((d, 1.0))
            continue
        # track exposure before update
        exposures.append((d, h2.sum()))

        h2 = h2 * (1 + rets.loc[d, cols])
        s2 = h2.sum()
        if s2 > 0:
            h2 = h2 / s2

        if d.month != rets.index[i - 1].month:
            lookback_days = TREND_LOOKBACK_MONTHS * 21
            for a in cols:
                asset_ret = rets.loc[:d, a].tail(lookback_days)
                if trend_filter(asset_ret):
                    h2[a] = 0.0
            for a in cols:
                if h2[a] == 0.0:
                    asset_ret = rets.loc[:d, a].tail(lookback_days)
                    if not trend_filter(asset_ret):
                        h2[a] = w[a]  # original weight for this asset
            s2 = h2.sum()
            if s2 > 0:
                h2 = h2 / s2

        if in_dd2:
            if not drawdown_stop(nv.loc[:d], DRAWDOWN_RECOVER):
                in_dd2 = False
                h2 = pd.Series(w.values, index=cols)
        else:
            if drawdown_stop(nv.loc[:d], DD_STOP):
                in_dd2 = True
                h2 = h2 * DRAWDOWN_TARGET_CAP

    exp_df = pd.DataFrame(exposures, columns=["date", "exposure"]).set_index("date")
    avg_exposure = exp_df["exposure"].mean()
    print(f"平均风险暴露: {avg_exposure:.1%}")
    print(f"平均现金拖累: {(1-avg_exposure)*100:.1f}% 仓位 × 平均资产回报差")

    # 分年统计
    exp_df["year"] = exp_df.index.year
    yearly_exp = exp_df.groupby("year")["exposure"].mean()
    print(f"\n分年平均暴露:")
    for yr, exp in yearly_exp.items():
        print(f"  {yr}: {exp:.1%}")

    return nv, trend_events, dd_events


def diagnose_b():
    """V3-B 诊断：量化风控机制各自的拖累。"""
    print("\n\n" + "=" * 90)
    print("  V3-B 分层风险平价策略诊断")
    print("=" * 90)

    panel = load_panel_extended()
    rets = panel.pct_change().dropna()
    cols = list(rets.columns)

    has_short = "short_bond" in cols
    rp_cols = [c for c in cols if c != "short_bond"]
    rets_rp = rets[rp_cols]
    rp_buckets = {k: [a for a in v if a != "short_bond"] for k, v in BUCKET_GROUPS.items()}
    rp_buckets = {k: v for k, v in rp_buckets.items() if v}

    SHORT_BOND_FIXED = 0.05
    horizon = "long"
    risk_cap = 1.00
    cash_ratio = 0.0

    def compute_weights(rets_window):
        rp_w = hierarchical_rp_weights(
            rets_window, rp_buckets,
            RISK_PARITY_WINDOW, RISK_PARITY_MAX_WEIGHT, RISK_PARITY_MIN_WEIGHT,
        )
        full = pd.Series(0.0, index=cols)
        for a in rp_w.index:
            full[a] = rp_w[a] * (1 - SHORT_BOND_FIXED) if has_short else rp_w[a]
        if has_short and "short_bond" in cols:
            full["short_bond"] = SHORT_BOND_FIXED
        return full

    nv = pd.Series(index=rets.index, dtype=float)
    n_rebal = 0
    n_corr_break = 0
    in_corr_break = False

    initial_w = compute_weights(rets_rp.iloc[:RISK_PARITY_WINDOW])
    target = initial_w.values
    h = pd.Series(target, index=cols)
    v = 1.0

    # 追踪统计
    corr_break_days = 0
    total_days = 0
    vol_scales = []
    weight_history = []
    corr_events = []

    for i, d in enumerate(rets.index):
        if i == 0:
            nv.loc[d] = 1.0
            continue

        total_days += 1

        if i > RISK_PARITY_WINDOW:
            w_now = h / h.sum()
            port_rets = (rets.iloc[i - RISK_PARITY_WINDOW:i] * w_now.values).sum(axis=1)
            scale = vol_target_scale(port_rets, VOL_TARGET, RISK_PARITY_WINDOW)
        else:
            scale = 1.0

        vol_scales.append((d, scale))
        if in_corr_break:
            corr_break_days += 1

        effective_h = h * scale * risk_cap
        v *= 1 + (effective_h * rets.loc[d, cols]).sum() + cash_ratio * RISK_FREE_RATE
        nv.loc[d] = v

        h = h * (1 + rets.loc[d, cols])
        s = h.sum()
        if s > 0:
            h = h / s * (1 - cash_ratio)

        if d.month != rets.index[i - 1].month and i > RISK_PARITY_WINDOW:
            window = rets_rp.iloc[max(0, i - RISK_PARITY_WINDOW):i]
            if in_corr_break:
                if not correlation_breaker(window, CORR_BREAKER_RECOVER, RISK_PARITY_WINDOW):
                    in_corr_break = False
                    corr_events.append((d, "recover"))
            else:
                avg_corr = window.corr().values[np.triu_indices(window.shape[1], k=1)].mean()
                if correlation_breaker(window, CORR_BREAKER_THRESHOLD, RISK_PARITY_WINDOW):
                    in_corr_break = True
                    n_corr_break += 1
                    corr_events.append((d, "trigger", avg_corr))

            new_w = compute_weights(window)
            if in_corr_break:
                new_w = new_w * CORR_BREAKER_CAP

            weight_history.append((d, new_w.copy()))
            target = new_w.values
            h = pd.Series(target, index=cols)
            n_rebal += 1

    # --- 结果 ---
    cum_ret = nv.iloc[-1] - 1
    cagr = (nv.iloc[-1]) ** (252 / len(nv)) - 1
    ret_series = nv.pct_change().dropna()
    vol = ret_series.std() * np.sqrt(252)
    mdd = ((nv / nv.cummax()) - 1).min()
    sharpe = (cagr - 0.022) / vol

    print(f"\n核心指标: CAGR={cagr:.2%}  Vol={vol:.2%}  MDD={mdd:.2%}  Sharpe={sharpe:.2f}")
    print(f"总交易日: {total_days}  月度调仓: {n_rebal}")

    # 波动率目标统计
    vol_df = pd.DataFrame(vol_scales, columns=["date", "scale"]).set_index("date")
    avg_scale = vol_df["scale"].mean()
    pct_under_1 = (vol_df["scale"] < 0.95).mean() * 100
    print(f"\n--- 波动率目标 (target={VOL_TARGET:.0%}) ---")
    print(f"平均缩放系数: {avg_scale:.3f}  (<0.95 占比: {pct_under_1:.1f}%)")
    print(f"系数分布: min={vol_df['scale'].min():.3f}  p25={vol_df['scale'].quantile(0.25):.3f}  "
          f"p50={vol_df['scale'].median():.3f}  p75={vol_df['scale'].quantile(0.75):.3f}")

    # 分年
    vol_df["year"] = vol_df.index.year
    yearly_scale = vol_df.groupby("year")["scale"].mean()
    print(f"\n分年平均缩放系数:")
    for yr, s in yearly_scale.items():
        print(f"  {yr}: {s:.3f}")

    # 相关性断路器
    print(f"\n--- 相关性断路器 (threshold={CORR_BREAKER_THRESHOLD}) ---")
    print(f"激活次数: {n_corr_break}  激活天数: {corr_break_days} ({corr_break_days/total_days*100:.1f}%)")
    for d, ev_type, *rest in corr_events[-15:]:
        if ev_type == "trigger":
            print(f"  {d.date()} 触发 avg_corr={rest[0]:.3f}")
        else:
            print(f"  {d.date()} 恢复")

    # 权重换手率
    if len(weight_history) > 1:
        turnovers = []
        prev_w = weight_history[0][1]
        for d, w in weight_history[1:]:
            turnover = abs(w - prev_w).sum() / 2
            turnovers.append((d, turnover))
            prev_w = w
        to_df = pd.DataFrame(turnovers, columns=["date", "turnover"]).set_index("date")
        avg_turnover = to_df["turnover"].mean()
        print(f"\n--- 权重换手率 ---")
        print(f"月均换手率: {avg_turnover:.1%}  max: {to_df['turnover'].max():.1%}")
        to_df["year"] = to_df.index.year
        yearly_to = to_df.groupby("year")["turnover"].mean()
        print(f"分年月均换手率:")
        for yr, t in yearly_to.items():
            print(f"  {yr}: {t:.1%}")

    # 平均风险暴露
    print(f"\n--- 有效风险暴露 ---")
    exposures = []
    h_temp = pd.Series(initial_w.values, index=cols)
    in_cb = False
    for i, d in enumerate(rets.index):
        if i == 0:
            exposures.append(1.0)
            continue
        if i > RISK_PARITY_WINDOW:
            w_t = h_temp / h_temp.sum()
            port_r = (rets.iloc[i - RISK_PARITY_WINDOW:i] * w_t.values).sum(axis=1)
            sc = vol_target_scale(port_r, VOL_TARGET, RISK_PARITY_WINDOW)
        else:
            sc = 1.0
        if in_cb:
            sc *= CORR_BREAKER_CAP
        sc *= risk_cap
        exposures.append(sc * h_temp.sum())

        h_temp = h_temp * (1 + rets.loc[d, cols])
        s = h_temp.sum()
        if s > 0:
            h_temp = h_temp / s

        if d.month != rets.index[i - 1].month and i > RISK_PARITY_WINDOW:
            window = rets_rp.iloc[max(0, i - RISK_PARITY_WINDOW):i]
            if in_cb:
                if not correlation_breaker(window, CORR_BREAKER_RECOVER, RISK_PARITY_WINDOW):
                    in_cb = False
            else:
                if correlation_breaker(window, CORR_BREAKER_THRESHOLD, RISK_PARITY_WINDOW):
                    in_cb = True
            h_temp = pd.Series(compute_weights(window).values, index=cols)

    avg_exp = np.mean(exposures)
    print(f"平均有效暴露: {avg_exp:.1%}")
    exp_series = pd.Series(exposures, index=rets.index)
    exp_series.index.name = "date"
    yearly_exp = exp_series.groupby(exp_series.index.year).mean()
    print(f"分年平均暴露:")
    for yr, e in yearly_exp.items():
        print(f"  {yr}: {e:.1%}")

    return nv


if __name__ == "__main__":
    nv_a, _, _ = diagnose_a()
    nv_b = diagnose_b()

    # 对比 V3c 基准
    print("\n\n" + "=" * 90)
    print("  对比总结")
    print("=" * 90)

    from allweather.backtest import backtest
    panel = load_panel_extended()
    rets = panel.pct_change().dropna()
    weights = get_weights()
    w_c = weights["V3c 多元"]
    w_c_clean = w_c[w_c.index.isin(rets.columns)]
    nv_c, _ = backtest(w_c_clean, rets, cash_ratio=0.0)

    def stats(nv):
        r = nv.pct_change().dropna()
        cagr = (nv.iloc[-1]) ** (252 / len(nv)) - 1
        vol_ = r.std() * np.sqrt(252)
        mdd = ((nv / nv.cummax()) - 1).min()
        return cagr, vol_, mdd

    for name, nv in [("V3c 基准", nv_c), ("V3-A", nv_a), ("V3-B long", nv_b)]:
        c, v, m = stats(nv)
        print(f"  {name:<15} CAGR={c:.2%}  Vol={v:.2%}  MDD={m:.2%}")

    # V3-A 相对 V3c 的逐月差异
    common_idx = nv_c.index.intersection(nv_a.index)
    monthly_c = nv_c.loc[common_idx].resample("ME").last().pct_change().dropna()
    monthly_a = nv_a.loc[common_idx].resample("ME").last().pct_change().dropna()
    diff = monthly_a - monthly_c
    print(f"\nV3-A vs V3c 月度差异:")
    print(f"  月均差异: {diff.mean()*100:.2f}bp")
    print(f"  正超额月占比: {(diff > 0).mean()*100:.1f}%")
    print(f"  最差超额月: {diff.min()*100:.2f}bp  ({diff.idxmin().date()})")
    print(f"  最佳超额月: {diff.max()*100:.2f}bp  ({diff.idxmax().date()})")
