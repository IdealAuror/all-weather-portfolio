"""Test fixtures — synthetic market data for backtest engine tests."""
import numpy as np
import pandas as pd
import pytest

ASSETS_8 = ["hs300", "us_sp500", "credit", "bond_10y", "bond_30y",
            "gold", "nonferr", "wti"]


@pytest.fixture(scope="session")
def synthetic_prices():
    """生成 500 × 8 合成价格数据。

    结构：
    - 多数资产以温和漂移 + 噪声向上
    - hs300: 第 300-370 天 -35% 回撤（触发 HS300 抄底阈值 25%）
    - gold:  第 200-240 天 -22% 回撤（触发 gold dip 阈值 15%）
    - nonferr: 第 100-140 天 -18% 回撤后反弹（测试 trend filter）
    - us_sp500: 第 400-430 天 -12% 小回撤（测试 sp500 trend filter）
    """
    np.random.seed(42)
    n = 500

    params = {
        "hs300":     {"drift": 0.0004, "vol": 0.012},
        "us_sp500":  {"drift": 0.0005, "vol": 0.010},
        "credit":    {"drift": 0.0002, "vol": 0.003},
        "bond_10y":  {"drift": 0.0002, "vol": 0.004},
        "bond_30y":  {"drift": 0.0003, "vol": 0.007},
        "gold":      {"drift": 0.0003, "vol": 0.008},
        "nonferr":   {"drift": 0.0003, "vol": 0.010},
        "wti":       {"drift": 0.0002, "vol": 0.015},
    }

    data = {}
    for asset, p in params.items():
        noise = np.random.normal(p["drift"], p["vol"], n)
        price = np.ones(n)
        for i in range(1, n):
            price[i] = price[i-1] * (1 + noise[i])
        data[asset] = price

    dates = pd.date_range("2022-01-01", periods=n, freq="B")
    df = pd.DataFrame(data, index=dates)
    df.index.name = "date"

    # hs300 -35% drawdown (day 300→370)
    _inject_dd(df, "hs300", 300, 370, 0.35)
    # gold -22% drawdown (day 200→240)
    _inject_dd(df, "gold", 200, 240, 0.22)
    # nonferr -18% drawdown then recovery (day 100→140)
    _inject_dd(df, "nonferr", 100, 140, 0.18)
    # us_sp500 -12% (day 400→430)
    _inject_dd(df, "us_sp500", 400, 430, 0.12)

    return df


def _inject_dd(df, col, peak_day, trough_day, depth):
    """Override price with a linear drawdown from peak_day to trough_day."""
    peak = df.iloc[peak_day][col]
    col_idx = df.columns.get_loc(col)
    for i in range(peak_day + 1, trough_day + 1):
        t = (i - peak_day) / (trough_day - peak_day)
        df.iloc[i, col_idx] = peak * (1 - t * depth)


@pytest.fixture(scope="session")
def synthetic_rets(synthetic_prices):
    """Returns DataFrame derived from synthetic prices."""
    return synthetic_prices.pct_change().dropna()


@pytest.fixture(scope="session")
def synthetic_pb_pe(synthetic_prices):
    """Synthetic PB/PE percentile series matching price index."""
    idx = synthetic_prices.index
    n = len(idx)
    np.random.seed(7)
    pb = pd.Series(np.random.uniform(10, 60, n), index=idx, name="pb")
    pe = pd.Series(np.random.uniform(10, 80, n), index=idx, name="pe")
    return pb, pe


@pytest.fixture(scope="session")
def synthetic_pct(synthetic_prices):
    """Pre-computed PB/PE percentiles (simple rank-based)."""
    idx = synthetic_prices.index
    n = len(idx)
    np.random.seed(13)
    pb_pct = pd.Series(np.random.uniform(0, 100, n), index=idx)
    pe_pct = pd.Series(np.random.uniform(0, 100, n), index=idx)
    return pb_pct, pe_pct
