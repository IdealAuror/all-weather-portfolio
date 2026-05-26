"""方案 C：风险平价核心 + 动态现金补仓（70/30 分仓）。

核心 70% 跑 V3-B risk_parity 月度再平衡；
现金 30% 在资产回撤超过阈值时补仓，盈利达标后卖回现金。
"""
import numpy as np
import pandas as pd
from .config import (
    RISK_FREE_RATE, RISK_PARITY_MIN_WEIGHT, BUCKET_GROUPS,
)
from .risk import hierarchical_rp_weights


def backtest_c(
    rets: pd.DataFrame,
    core_ratio: float = 0.70,
    trigger_threshold: float = -0.15,
    deploy_pct: float = 0.05,
    exit_threshold: float = 0.15,
    cooldown_days: int = 60,
    core_window: int = 90,
    core_max_w: float = 0.30,
) -> dict:
    """动态现金补仓回测。

    Args:
        rets: 日收益率 DataFrame（9 资产）
        core_ratio: 核心仓位占比（默认 70%）
        trigger_threshold: 资产从峰值回撤触发补仓的阈值（如 -0.15 = -15%）
        deploy_pct: 单次补仓占总资产比例
        exit_threshold: 补仓盈利退出阈值（如 0.15 = +15%）
        cooldown_days: 同资产两次补仓最少间隔（交易日）
        core_window: 核心 RP 计算窗口
        core_max_w: 核心单资产权重上限

    Returns:
        dict with keys: nv (总净值), core_nv (核心净值), n_deploy (补仓次数),
            n_exit (退出次数)
    """
    cols = list(rets.columns)
    rp_buckets = {k: list(v) for k, v in BUCKET_GROUPS.items()}
    rf_daily = RISK_FREE_RATE

    # --- Prices for drawdown tracking ---
    prices = (1 + rets[cols]).cumprod()

    # --- Core portfolio state ---
    core_nv = pd.Series(1.0, index=rets.index, dtype=float)
    core_rets = rets[cols]

    initial_w = hierarchical_rp_weights(
        core_rets.iloc[:core_window], rp_buckets, core_window,
        core_max_w, RISK_PARITY_MIN_WEIGHT,
        bucket_method="risk_parity",
    )
    core_h = pd.Series(initial_w.values * core_ratio, index=cols)
    core_v = core_ratio

    # --- Reserve state ---
    cash = 1.0 - core_ratio

    # --- Deployment tracking ---
    asset_peaks = prices.iloc[0].copy()
    last_deploy = {c: -cooldown_days for c in cols}
    active_deps = []  # list of {asset, entry_day, entry_price, shares}
    n_deploy = 0
    n_exit = 0

    # --- Final output ---
    total_nv = pd.Series(1.0, index=rets.index, dtype=float)

    for i, d in enumerate(rets.index):
        if i == 0:
            core_nv.loc[d] = core_v
            total_nv.loc[d] = 1.0
            continue

        day_prices = prices.iloc[i]

        # --- Update asset peaks ---
        asset_peaks = pd.Series(
            np.maximum(asset_peaks.values, day_prices.values),
            index=asset_peaks.index,
        )

        # --- Core drift ---
        core_v *= 1 + (core_h * rets.loc[d, cols]).sum()
        core_nv.loc[d] = core_v
        core_h = core_h * (1 + rets.loc[d, cols])
        s = core_h.sum()
        if s > 0:
            core_h = core_h / s * core_ratio

        # --- Monthly core rebalance ---
        if d.month != rets.index[i - 1].month and i > core_window:
            window = core_rets.iloc[max(0, i - core_window):i]
            new_w = hierarchical_rp_weights(
                window, rp_buckets, core_window,
                core_max_w, RISK_PARITY_MIN_WEIGHT,
                bucket_method="risk_parity",
            )
            core_h = pd.Series(new_w.values * core_ratio, index=cols)

        # --- Accrue interest on cash ---
        cash *= 1 + rf_daily

        # --- Check deployment triggers ---
        for asset in cols:
            peak = asset_peaks[asset]
            curr = day_prices[asset]
            if peak <= 0:
                continue
            dd = (curr / peak) - 1
            if dd <= trigger_threshold and cash >= deploy_pct:
                if i - last_deploy[asset] >= cooldown_days:
                    cash -= deploy_pct
                    active_deps.append({
                        "asset": asset,
                        "entry_day": i,
                        "entry_price": curr,
                        "shares": deploy_pct / curr,
                    })
                    last_deploy[asset] = i
                    n_deploy += 1

        # --- Check exit conditions ---
        remaining = []
        for dep in active_deps:
            curr = day_prices[dep["asset"]]
            if (curr / dep["entry_price"] - 1) >= exit_threshold:
                cash += dep["shares"] * curr
                n_exit += 1
            else:
                remaining.append(dep)
        active_deps = remaining

        # --- Total NV = core + cash + active deployments ---
        dep_value = sum(d["shares"] * day_prices[d["asset"]] for d in active_deps)
        total_nv.loc[d] = core_v + cash + dep_value

    return {
        "nv": total_nv,
        "core_nv": core_nv,
        "n_deploy": n_deploy,
        "n_exit": n_exit,
    }
