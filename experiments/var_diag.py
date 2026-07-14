# -*- coding: utf-8 -*-
"""CVaR/ES coherent risk diagnostic — standalone script."""
import sys
import io
sys.path.insert(0, ".")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import numpy as np
from allweather.data import load_panel

ASSET_NAMES = {
    "hs300": "HS300", "us_sp500": "SP500", "credit": "Credit",
    "bond_10y": "10Y Bond", "bond_30y": "30Y Bond",
    "gold": "Gold", "nonferr": "Nonferr",
}

STRATEGY_ASSETS = {
    "V3c":      ["hs300", "us_sp500", "credit", "bond_30y", "gold", "nonferr"],
    "V3-B Con": ["hs300", "us_sp500", "credit", "bond_10y", "bond_30y", "gold", "nonferr"],
    "V3-B RP":  ["hs300", "us_sp500", "credit", "bond_30y", "gold", "nonferr"],
}

HORIZON = 21
CI = 0.95
CI_TAIL = 0.99


def es_historical(rolling_ret: np.ndarray, alpha: float) -> float:
    """ES (CVaR) via historical method — mean of returns below VaR threshold."""
    threshold = float(np.quantile(rolling_ret, 1 - alpha))
    tail = rolling_ret[rolling_ret <= threshold]
    return float(tail.mean()) if len(tail) > 0 else threshold


def es_parametric(mu: float, sigma: float, alpha: float) -> float:
    """ES under normality — closed form: mu - sigma * phi(Phi^-1(alpha)) / (1-alpha)."""
    from scipy.stats import norm
    z = abs(norm.ppf(1 - alpha))
    return mu - sigma * norm.pdf(z) / (1 - alpha)


if __name__ == "__main__":
    panel = load_panel(include_wti=False)
    rets = panel.pct_change().dropna()

    print("\n" + "=" * 105)
    print("  CVaR/ES Coherent Risk Diagnostic — Monthly Horizon (21d)")
    print("=" * 105)

    rows = []
    for col in rets.columns:
        daily = rets[col].dropna()
        if len(daily) < HORIZON * 2:
            continue

        rolling = daily.rolling(window=HORIZON).apply(lambda x: (1 + x).prod() - 1).dropna()
        mu_m = float(rolling.mean())
        sigma_m = float(rolling.std(ddof=1))
        vol_ann = sigma_m * np.sqrt(12)

        # 99% metrics — the tail that matters
        hist_var_99 = float(np.quantile(rolling, 1 - CI_TAIL))
        hist_es_99 = es_historical(rolling.values, CI_TAIL)
        param_var_99 = mu_m - abs(np.quantile(np.random.standard_normal(100000), 1 - CI_TAIL)) * sigma_m
        param_es_99 = es_parametric(mu_m, sigma_m, CI_TAIL)

        # Key: ES/Vol ratio — tail severity per unit of vol
        es_vol_ratio = abs(hist_es_99) / sigma_m if sigma_m > 0 else 0

        # 95% for reference
        hist_var_95 = float(np.quantile(rolling, 1 - CI))
        hist_es_95 = es_historical(rolling.values, CI)

        rows.append({
            "asset": col,
            "vol_ann": vol_ann,
            "hist_var_99": hist_var_99,
            "hist_es_99": hist_es_99,
            "param_var_99": param_var_99,
            "param_es_99": param_es_99,
            "es_vol_ratio": es_vol_ratio,
            "var_ratio_99": hist_var_99 / param_var_99 if param_var_99 != 0 else np.nan,
            "es_ratio_99": hist_es_99 / param_es_99 if param_es_99 != 0 else np.nan,
            "hist_var_95": hist_var_95,
            "hist_es_95": hist_es_95,
            "daily_skew": float(daily.skew()),
        })

    import pandas as pd
    df = pd.DataFrame(rows).set_index("asset")
    df = df.sort_values("es_vol_ratio", ascending=False)

    hdr = (f"{'Asset':<12} {'Vol(ann)':>8} {'VaR99%':>8} {'ES99%':>8} "
           f"{'ES/Vol':>7} {'ES/Param':>9} {'VaR95%':>8} {'ES95%':>8} {'Skew':>7}")
    print(hdr)
    print("-" * 105)

    for asset, row in df.iterrows():
        name = ASSET_NAMES.get(asset, asset)
        print(f"{name:<12} {row['vol_ann']:>8.2%} {row['hist_var_99']:>8.2%} "
              f"{row['hist_es_99']:>8.2%} {row['es_vol_ratio']:>7.2f} "
              f"{row['es_ratio_99']:>9.2f} {row['hist_var_95']:>8.2%} "
              f"{row['hist_es_95']:>8.2%} {row['daily_skew']:>7.3f}")

    print("-" * 105)
    print("  ES/Vol   = tail severity per unit of vol (higher = vol understates risk)")
    print("  ES/Param = historical ES / parametric ES (>1 = normal underestimates)")
    print("  Skew < 0 = left-skewed")

    # Cross-check: is any asset's tail risk disproportionately HIGH relative to vol?
    print(f"\n  --- Cross-sectional comparison ---")
    es_vol_median = df["es_vol_ratio"].median()
    print(f"  Median ES/Vol: {es_vol_median:.2f}")

    outliers = df[df["es_vol_ratio"] > es_vol_median * 1.15]
    if len(outliers) > 0:
        print(f"\n  !! Assets with ES/Vol > median +15% (vol UNDERSTATES tail risk):")
        for asset, row in outliers.iterrows():
            name = ASSET_NAMES.get(asset, asset)
            print(f"    {name}: ES/Vol={row['es_vol_ratio']:.2f}, ES99%={row['hist_es_99']:.2%}")

    low = df[df["es_vol_ratio"] < es_vol_median * 0.85]
    if len(low) > 0:
        print(f"\n  ... Assets with ES/Vol < median -15% (vol OVERSTATES tail risk):")
        for asset, row in low.iterrows():
            name = ASSET_NAMES.get(asset, asset)
            print(f"    {name}: ES/Vol={row['es_vol_ratio']:.2f}, ES99%={row['hist_es_99']:.2%}")

    print(f"\n  Data: {rets.index[0].strftime('%Y-%m-%d')} ~ {rets.index[-1].strftime('%Y-%m-%d')}")
    print(f"  99% tail obs per asset: ~{len(rolling) * (1 - CI_TAIL):.0f} out of {len(rolling)} months")
