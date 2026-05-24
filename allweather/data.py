"""数据加载层 - 从 data/ 读取 CSV，处理 30Y 国债合成，返回回测期价格表。"""
import pandas as pd
from .config import DATA_DIR, BACKTEST_START, BACKTEST_END, BOND_30Y_AMP


def load_series(name: str) -> pd.Series:
    """从 CSV 加载单资产收盘价时间序列（按日期升序）。"""
    path = DATA_DIR / f"{name}.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"找不到数据文件 {path}。请先运行 fetch.py 拉取数据，"
            f"或确认 data/ 目录下有 {name}.csv。"
        )
    df = pd.read_csv(path, parse_dates=["date"])
    return df.set_index("date")["close"].sort_index()


def synthesize_bond_30y(s_10y: pd.Series, s_30y_etf: pd.Series) -> pd.Series:
    """合成 30Y 国债序列：2024-03 ETF 之前用 10Y × 久期放大系数。"""
    cb10_ret = s_10y.pct_change().dropna()
    synth = (1 + cb10_ret * BOND_30Y_AMP).cumprod()
    etf_start = s_30y_etf.index.min()
    synth_part = synth[synth.index < etf_start]
    real_norm = s_30y_etf / s_30y_etf.iloc[0] * synth_part.iloc[-1]
    return pd.concat([synth_part, real_norm[real_norm.index >= etf_start]]).sort_index()


def load_panel() -> pd.DataFrame:
    """加载 9 资产收盘价面板（已对齐到回测期间，前向填充）。"""
    raw = {k: load_series(k) for k in [
        "hs300", "div_lowvol", "cb_10y_idx", "bond_30y_etf",
        "bond_credit", "gold", "nonferr", "soymeal", "us_sp500",
    ]}
    bond_30y = synthesize_bond_30y(raw["cb_10y_idx"], raw["bond_30y_etf"])

    panel = pd.DataFrame({
        "hs300":    raw["hs300"],
        "div_idx":  raw["div_lowvol"],
        "us_sp500": raw["us_sp500"],
        "credit":   raw["bond_credit"],
        "bond_10y": raw["cb_10y_idx"],
        "bond_30y": bond_30y,
        "gold":     raw["gold"],
        "nonferr":  raw["nonferr"],
        "soymeal":  raw["soymeal"],
    })
    panel.index = pd.to_datetime(panel.index)
    panel = panel.sort_index()
    panel = panel.loc[BACKTEST_START:BACKTEST_END].ffill().dropna()

    return panel


def get_returns() -> pd.DataFrame:
    """便捷函数：返回日收益率面板。"""
    return load_panel().pct_change().dropna()
