"""回撤改进探索 — 四种风控机制 vs 基线对比。

A: nonferr 单独刹车  B: 商品桶降权  C: 商品波动率目标  D: nonferr 趋势过滤
"""
import numpy as np
import pandas as pd
import time
from .data import load_panel
from .stats import perf_metrics
from .config import RISK_PARITY_MIN_WEIGHT, BUCKET_GROUPS, RISK_FREE_RATE
from .risk import hierarchical_rp_weights


def _base_risk_parity_nv(rets, window=90, max_w=0.30):
    """Pure V3-B risk_parity — baseline for comparison."""
    cols = list(rets.columns)
    rp_buckets = {k: list(v) for k, v in BUCKET_GROUPS.items()}
    core_rets = rets[cols]

    initial_w = hierarchical_rp_weights(
        core_rets.iloc[:window], rp_buckets, window,
        max_w, RISK_PARITY_MIN_WEIGHT, bucket_method="risk_parity",
    )
    h = pd.Series(initial_w.values, index=cols)
    v = 1.0
    nv = pd.Series(1.0, index=rets.index, dtype=float)

    for i, d in enumerate(rets.index):
        if i == 0:
            nv.loc[d] = 1.0
            continue
        v *= 1 + (h * rets.loc[d, cols]).sum()
        nv.loc[d] = v
        h = h * (1 + rets.loc[d, cols])
        s = h.sum()
        if s > 0:
            h = h / s
        if d.month != rets.index[i - 1].month and i > window:
            win = core_rets.iloc[max(0, i - window):i]
            new_w = hierarchical_rp_weights(
                win, rp_buckets, window, max_w, RISK_PARITY_MIN_WEIGHT,
                bucket_method="risk_parity",
            )
            h = pd.Series(new_w.values, index=cols)
    return nv


# ============================================================================
#  Approach A: nonferr 单独刹车
# ============================================================================

def backtest_a_nonferr_dd_stop(rets, dd_threshold=-0.15, window=90, max_w=0.30):
    """nonferr 从峰值回撤超阈值 → 清仓 nonferr，权重转 credit。"""
    cols = list(rets.columns)
    rp_buckets = {k: list(v) for k, v in BUCKET_GROUPS.items()}
    core_rets = rets[cols]
    prices = (1 + rets[cols]).cumprod()

    initial_w = hierarchical_rp_weights(
        core_rets.iloc[:window], rp_buckets, window,
        max_w, RISK_PARITY_MIN_WEIGHT, bucket_method="risk_parity",
    )
    h = pd.Series(initial_w.values, index=cols)
    v = 1.0
    nv = pd.Series(1.0, index=rets.index, dtype=float)
    nferr_peak = prices.iloc[0]["nonferr"]
    nferr_stopped = False

    for i, d in enumerate(rets.index):
        if i == 0:
            nv.loc[d] = 1.0
            continue

        # Update nonferr running peak
        curr_nf = prices.iloc[i]["nonferr"]
        if curr_nf > nferr_peak:
            nferr_peak = curr_nf
            nferr_stopped = False  # new high, reset stop

        # Check nonferr drawdown stop
        nf_dd = (curr_nf / nferr_peak) - 1
        if nf_dd <= dd_threshold:
            nferr_stopped = True

        # Drift
        v *= 1 + (h * rets.loc[d, cols]).sum()
        nv.loc[d] = v
        h = h * (1 + rets.loc[d, cols])
        s = h.sum()
        if s > 0:
            h = h / s

        # Monthly rebalance with nonferr stop
        if d.month != rets.index[i - 1].month and i > window:
            win = core_rets.iloc[max(0, i - window):i]
            new_w = hierarchical_rp_weights(
                win, rp_buckets, window, max_w, RISK_PARITY_MIN_WEIGHT,
                bucket_method="risk_parity",
            )
            w = pd.Series(new_w.values, index=cols)
            if nferr_stopped and "nonferr" in w.index:
                freed = w["nonferr"]
                w["nonferr"] = 0.0
                if "credit" in w.index:
                    w["credit"] += freed
            h = w

    return nv


# ============================================================================
#  Approach B: 商品桶降权
# ============================================================================

def backtest_b_comm_underweight(rets, comm_weight=0.15, window=90, max_w=0.30):
    """通胀↑桶降权至 comm_weight，多出的给收益垫（credit）。"""
    cols = list(rets.columns)
    rp_buckets = {k: list(v) for k, v in BUCKET_GROUPS.items()}
    core_rets = rets[cols]

    # Modified bucket allocation
    def custom_bucket_weights(returns, bucket_groups, window, max_w, min_w):
        """Same as hierarchical_rp_weights but with custom bucket allocation."""
        if len(returns) < 20:
            n = returns.shape[1]
            return pd.Series(1.0 / n, index=returns.columns)

        recent = returns.tail(window)
        n_buckets = len(bucket_groups)
        bucket_names = list(bucket_groups.keys())

        bucket_w = {}
        bucket_vol = {}
        for bname, assets in bucket_groups.items():
            valid = [a for a in assets if a in recent.columns]
            if not valid:
                continue
            brets = recent[valid]
            vols = brets.std() * np.sqrt(252)
            inv = 1 / vols.replace(0, np.nan)
            w = inv / inv.sum()
            bucket_w[bname] = w
            port_r = (brets * w.values).sum(axis=1)
            bucket_vol[bname] = port_r.std() * np.sqrt(252)

        inv_vols = {k: 1.0 / v for k, v in bucket_vol.items() if v > 0.001}
        total = sum(inv_vols.values())
        bucket_alloc = {k: v / total for k, v in inv_vols.items()}

        # Override: commodity bucket gets comm_weight, rest redistributed
        extra = bucket_alloc.get("通胀↑", 0.25) - comm_weight
        bucket_alloc["通胀↑"] = comm_weight
        # Give extra to 收益垫
        bucket_alloc["收益垫"] = bucket_alloc.get("收益垫", 0.25) + extra

        raw = pd.Series(0.0, index=returns.columns)
        for bname, bw in bucket_alloc.items():
            for asset in bucket_w[bname].index:
                raw[asset] = bw * bucket_w[bname][asset]

        capped = raw.clip(lower=min_w, upper=max_w)
        return capped / capped.sum()

    initial_w = custom_bucket_weights(
        core_rets.iloc[:window], rp_buckets, window, max_w, RISK_PARITY_MIN_WEIGHT,
    )
    h = pd.Series(initial_w.values, index=cols)
    v = 1.0
    nv = pd.Series(1.0, index=rets.index, dtype=float)

    for i, d in enumerate(rets.index):
        if i == 0:
            nv.loc[d] = 1.0
            continue
        v *= 1 + (h * rets.loc[d, cols]).sum()
        nv.loc[d] = v
        h = h * (1 + rets.loc[d, cols])
        s = h.sum()
        if s > 0:
            h = h / s
        if d.month != rets.index[i - 1].month and i > window:
            win = core_rets.iloc[max(0, i - window):i]
            new_w = custom_bucket_weights(
                win, rp_buckets, window, max_w, RISK_PARITY_MIN_WEIGHT,
            )
            h = pd.Series(new_w.values, index=cols)
    return nv


# ============================================================================
#  Approach C: 商品波动率目标
# ============================================================================

def backtest_c_comm_vol_target(rets, vol_threshold=0.25, window=90, max_w=0.30):
    """商品桶滚动波动率超阈值 → 仓位减半，转入 credit。"""
    cols = list(rets.columns)
    rp_buckets = {k: list(v) for k, v in BUCKET_GROUPS.items()}
    core_rets = rets[cols]
    comm_assets = rp_buckets["通胀↑"]

    initial_w = hierarchical_rp_weights(
        core_rets.iloc[:window], rp_buckets, window,
        max_w, RISK_PARITY_MIN_WEIGHT, bucket_method="risk_parity",
    )
    h = pd.Series(initial_w.values, index=cols)
    v = 1.0
    nv = pd.Series(1.0, index=rets.index, dtype=float)

    for i, d in enumerate(rets.index):
        if i == 0:
            nv.loc[d] = 1.0
            continue
        v *= 1 + (h * rets.loc[d, cols]).sum()
        nv.loc[d] = v
        h = h * (1 + rets.loc[d, cols])
        s = h.sum()
        if s > 0:
            h = h / s
        if d.month != rets.index[i - 1].month and i > window:
            win = core_rets.iloc[max(0, i - window):i]

            # Compute commodity bucket trailing vol
            comm_rets = win[comm_assets]
            comm_port_ret = comm_rets.mean(axis=1)  # equal-weight proxy
            comm_vol = comm_port_ret.std() * np.sqrt(252)

            new_w = hierarchical_rp_weights(
                win, rp_buckets, window, max_w, RISK_PARITY_MIN_WEIGHT,
                bucket_method="risk_parity",
            )
            w = pd.Series(new_w.values, index=cols)

            if comm_vol > vol_threshold:
                # Halve commodity positions, add to credit
                for a in comm_assets:
                    if a in w.index:
                        freed = w[a] * 0.5
                        w[a] *= 0.5
                        if "credit" in w.index:
                            w["credit"] += freed
                # Renormalize
                w = w / w.sum()

            h = w
    return nv


# ============================================================================
#  Approach D: nonferr 趋势过滤
# ============================================================================

def backtest_d_nonferr_trend(rets, trend_window=120, rp_window=90, max_w=0.30):
    """nonferr < SMA(trend_window) → 清仓 nonferr，权重转 credit。"""
    cols = list(rets.columns)
    rp_buckets = {k: list(v) for k, v in BUCKET_GROUPS.items()}
    core_rets = rets[cols]
    prices = (1 + rets[cols]).cumprod()

    initial_w = hierarchical_rp_weights(
        core_rets.iloc[:rp_window], rp_buckets, rp_window,
        max_w, RISK_PARITY_MIN_WEIGHT, bucket_method="risk_parity",
    )
    h = pd.Series(initial_w.values, index=cols)
    v = 1.0
    nv = pd.Series(1.0, index=rets.index, dtype=float)

    for i, d in enumerate(rets.index):
        if i == 0:
            nv.loc[d] = 1.0
            continue
        v *= 1 + (h * rets.loc[d, cols]).sum()
        nv.loc[d] = v
        h = h * (1 + rets.loc[d, cols])
        s = h.sum()
        if s > 0:
            h = h / s
        if d.month != rets.index[i - 1].month and i > max(rp_window, trend_window):
            win = core_rets.iloc[max(0, i - rp_window):i]
            new_w = hierarchical_rp_weights(
                win, rp_buckets, rp_window, max_w, RISK_PARITY_MIN_WEIGHT,
                bucket_method="risk_parity",
            )
            w = pd.Series(new_w.values, index=cols)

            # Trend filter on nonferr
            nf_price = prices["nonferr"].iloc[i]
            nf_sma = prices["nonferr"].iloc[max(0, i - trend_window):i].mean()
            if nf_price < nf_sma and "nonferr" in w.index:
                freed = w["nonferr"]
                w["nonferr"] = 0.0
                if "credit" in w.index:
                    w["credit"] += freed
                w = w / w.sum()

            h = w
    return nv


# ============================================================================
#  Main exploration
# ============================================================================

def run():
    t0 = time.time()
    panel = load_panel()
    rets = panel.pct_change().dropna()
    print(f"数据: {len(rets)} 交易日, {panel.shape[1]} 资产")

    # --- Baselines ---
    print("\n" + "=" * 70)
    print("  基线")
    print("=" * 70)
    base_rp = _base_risk_parity_nv(rets)
    bm_rp = perf_metrics(base_rp)
    print(f"  V3-B risk_parity 90d:  CAGR={bm_rp['cagr']*100:.2f}%  "
          f"MDD={bm_rp['mdd']*100:.2f}%  Sharpe={bm_rp['sharpe']:.2f}  Vol={bm_rp['vol']*100:.2f}%")

    # --- A: nonferr DD stop ---
    print("\n" + "=" * 70)
    print("  A: nonferr 单独刹车 (回撤触发 → 清仓 → credit)")
    print("=" * 70)
    print(f"  {'阈值':<8} {'CAGR':<8} {'MDD':<9} {'Sharpe':<7} {'Vol':<7} {'vs基线MDD':<10}")
    print("  " + "-" * 60)
    best_a = None
    for dd_t in [-0.10, -0.15, -0.20]:
        nv = backtest_a_nonferr_dd_stop(rets, dd_threshold=dd_t)
        m = perf_metrics(nv)
        delta = (m['mdd'] - bm_rp['mdd']) * 100
        print(f"  {dd_t*100:>5.0f}%   {m['cagr']*100:>6.2f}%  {m['mdd']*100:>7.2f}%  "
              f"{m['sharpe']:>5.2f}   {m['vol']*100:>5.2f}%  {delta:>+7.2f}%")
        if best_a is None or m['sharpe'] > best_a['sharpe']:
            best_a = m

    # --- B: 商品桶降权 ---
    print("\n" + "=" * 70)
    print("  B: 商品桶降权 (通胀↑桶权重下调 → 收益垫)")
    print("=" * 70)
    print(f"  {'权重':<8} {'CAGR':<8} {'MDD':<9} {'Sharpe':<7} {'Vol':<7} {'vs基线MDD':<10}")
    print("  " + "-" * 60)
    best_b = None
    for cw in [0.10, 0.15, 0.20]:
        nv = backtest_b_comm_underweight(rets, comm_weight=cw)
        m = perf_metrics(nv)
        delta = (m['mdd'] - bm_rp['mdd']) * 100
        print(f"  {cw*100:>4.0f}%    {m['cagr']*100:>6.2f}%  {m['mdd']*100:>7.2f}%  "
              f"{m['sharpe']:>5.2f}   {m['vol']*100:>5.2f}%  {delta:>+7.2f}%")
        if best_b is None or m['sharpe'] > best_b['sharpe']:
            best_b = m

    # --- C: 商品波动率目标 ---
    print("\n" + "=" * 70)
    print("  C: 商品波动率目标 (波动率超阈值 → 仓位减半)")
    print("=" * 70)
    print(f"  {'阈值':<8} {'CAGR':<8} {'MDD':<9} {'Sharpe':<7} {'Vol':<7} {'vs基线MDD':<10}")
    print("  " + "-" * 60)
    best_c = None
    for vt in [0.20, 0.25, 0.30]:
        nv = backtest_c_comm_vol_target(rets, vol_threshold=vt)
        m = perf_metrics(nv)
        delta = (m['mdd'] - bm_rp['mdd']) * 100
        print(f"  {vt*100:>4.0f}%   {m['cagr']*100:>6.2f}%  {m['mdd']*100:>7.2f}%  "
              f"{m['sharpe']:>5.2f}   {m['vol']*100:>5.2f}%  {delta:>+7.2f}%")
        if best_c is None or m['sharpe'] > best_c['sharpe']:
            best_c = m

    # --- D: nonferr 趋势过滤 ---
    print("\n" + "=" * 70)
    print("  D: nonferr 趋势过滤 (价格 < SMA → 清仓)")
    print("=" * 70)
    print(f"  {'SMA窗':<8} {'CAGR':<8} {'MDD':<9} {'Sharpe':<7} {'Vol':<7} {'vs基线MDD':<10}")
    print("  " + "-" * 60)
    best_d = None
    for tw in [60, 120, 252]:
        nv = backtest_d_nonferr_trend(rets, trend_window=tw)
        m = perf_metrics(nv)
        delta = (m['mdd'] - bm_rp['mdd']) * 100
        print(f"  {tw:<8} {m['cagr']*100:>6.2f}%  {m['mdd']*100:>7.2f}%  "
              f"{m['sharpe']:>5.2f}   {m['vol']*100:>5.2f}%  {delta:>+7.2f}%")
        if best_d is None or m['sharpe'] > best_d['sharpe']:
            best_d = m

    # --- Summary ---
    print("\n" + "=" * 70)
    print("  汇总对比")
    print("=" * 70)
    print(f"  {'方案':<25} {'CAGR':<8} {'MDD':<9} {'Sharpe':<7} {'Vol':<7}")
    print("  " + "-" * 55)
    print(f"  {'基线: RP 90d':<25} {bm_rp['cagr']*100:>6.2f}%  {bm_rp['mdd']*100:>7.2f}%  "
          f"{bm_rp['sharpe']:>5.2f}   {bm_rp['vol']*100:>5.2f}%")
    for label, bm in [("A: nonferr刹车", best_a), ("B: 商品桶降权", best_b),
                       ("C: 商品波动率目标", best_c), ("D: nonferr趋势", best_d)]:
        print(f"  {label:<25} {bm['cagr']*100:>6.2f}%  {bm['mdd']*100:>7.2f}%  "
              f"{bm['sharpe']:>5.2f}   {bm['vol']*100:>5.2f}%")

    print(f"\n总耗时: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    run()
