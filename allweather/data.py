"""数据加载层 - 从 data/ 读取 CSV，处理 30Y 国债合成，返回回测期价格表。"""
import pandas as pd
from .config import DATA_DIR, BACKTEST_START, BACKTEST_END, BOND_30Y_AMP, SAFETY_DEDUCT


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


def stitch_series(etf: pd.Series, proxy: pd.Series,
                  annual_deduct: float = 0.0) -> pd.Series:
    """ETF 上市前用 proxy，归一化对齐 + 安全扣减后拼接。

    1. 合并 proxy + etf 交易日历，proxy reindex + ffill（对齐不同市场日历）
    2. proxy 日收益扣减 safety margin
    3. 在 etf 起始日归一化：proxy *= etf[0] / proxy[stitch_date]
    4. 拼接 proxy[:stitch_date) + etf[stitch_date:]
    """
    if proxy.empty or etf.empty:
        raise ValueError("proxy 或 etf 数据为空，无法缝合")

    # 合并日历：保留 proxy 的全部历史 + ETF 的交易日历
    combined_cal = proxy.index.union(etf.index).sort_values()
    # 保存首日，在 pct_change/dropna 后会丢失
    first_date = combined_cal[0]
    proxy = proxy.reindex(combined_cal).ffill()

    # 安全扣减应用于 proxy 日收益率
    daily_deduct = annual_deduct / 252.0
    proxy_ret = proxy.pct_change().dropna()
    proxy_ret = proxy_ret - daily_deduct
    proxy = (1 + proxy_ret).cumprod()
    # 补回首日（归一化从 1.0 起）
    proxy = pd.concat([pd.Series(1.0, index=[first_date]), proxy]).sort_index()

    # 在 etf 起始日归一化
    stitch_date = etf.index.min()
    if stitch_date not in proxy.index:
        raise ValueError(f"缝合日 {stitch_date.date()} 不在 proxy 索引中")
    proxy = proxy * (etf.iloc[0] / proxy.loc[stitch_date])

    # 拼接
    proxy_part = proxy[proxy.index < stitch_date]
    return pd.concat([proxy_part, etf]).sort_index()


def _load_cgb_yields_spread() -> pd.Series:
    """从 cgb_yields.csv 读取 10Y-30Y 利差日序列。

    优先使用位置索引（列8=10Y, 列9=30Y），避免中文编码依赖。
    回退到 substring 匹配。
    """
    path = DATA_DIR / "cgb_yields.csv"
    if not path.exists():
        return pd.Series(dtype=float)

    df = pd.read_csv(path)
    if df.empty or len(df.columns) < 10:
        return pd.Series(dtype=float)

    try:
        date_col = df.columns[0]
        y10_col = df.columns[8]
        y30_col = df.columns[9]
        spread = pd.to_numeric(df[y30_col], errors="coerce") - pd.to_numeric(df[y10_col], errors="coerce")
        dates = pd.to_datetime(df[date_col], errors="coerce")
        spread.index = dates
        spread = spread.dropna().sort_index()
        return spread / 100.0
    except Exception:
        pass

    # 回退：substring 匹配
    date_col = df.columns[0]
    cols = df.columns.tolist()
    y10_col = next((c for c in cols if "10" in str(c)), None)
    y30_col = next((c for c in cols if "30" in str(c)), None)
    if y10_col is None or y30_col is None:
        return pd.Series(dtype=float)
    spread = pd.to_numeric(df[y30_col], errors="coerce") - pd.to_numeric(df[y10_col], errors="coerce")
    dates = pd.to_datetime(df[date_col], errors="coerce")
    spread.index = dates
    return spread.dropna().sort_index() / 100.0


def synthesize_bond_30y(s_10y: pd.Series, s_30y_etf: pd.Series) -> pd.Series:
    """合成 30Y 国债序列，三阶段拼接：

    1. 2015-01 ~ 2020-02：×3.0 久期放大（扣减 0.3%/年）
    2. 2020-02 ~ 2024-03：利差法（10Y-30Y spread × duration 18.0）
    3. 2024-03 ~ now：ETF 511130 真实 NAV
    """
    cb10_ret = s_10y.pct_change().dropna()
    etf_start = s_30y_etf.index.min()

    # 阶段 1: ×3.0 久期放大（全段先算）
    amp_ret = cb10_ret * BOND_30Y_AMP
    amp_nv = (1 + amp_ret).cumprod()
    amp_nv = amp_nv / amp_nv.iloc[0]

    # 阶段 2: 利差法
    spread = _load_cgb_yields_spread()
    spread_cutoff = pd.Timestamp("2020-02-01")

    if not spread.empty and spread.index.min() <= spread_cutoff:
        cb10_aligned = cb10_ret[cb10_ret.index >= spread.index.min()]
        spread_aligned = spread.reindex(cb10_aligned.index).ffill()
        spread_daily = spread_aligned.diff().fillna(0.0) / 252.0
        dur = 18.0
        spread_ret = cb10_aligned + dur * spread_daily
        spread_nv = (1 + spread_ret).cumprod()
        spread_nv = spread_nv[spread_nv.index >= spread_cutoff]
    else:
        spread_nv = pd.Series(dtype=float)

    synth = amp_nv.copy()

    # 阶段2 覆盖
    if not spread_nv.empty:
        stitch_pt = spread_nv.index.min()
        if stitch_pt in synth.index:
            spread_nv = spread_nv * (synth.loc[stitch_pt] / spread_nv.iloc[0])
            synth = pd.concat([synth[synth.index < stitch_pt], spread_nv])

    # 阶段3: ETF 真实数据覆盖
    if etf_start in synth.index:
        etf_norm = s_30y_etf / s_30y_etf.iloc[0] * synth.loc[etf_start]
        synth = pd.concat([synth[synth.index < etf_start],
                           etf_norm[etf_norm.index >= etf_start]])

    # 阶段1 段安全扣减
    if not spread_nv.empty:
        phase1_end = min(spread_cutoff, spread_nv.index.min())
    else:
        phase1_end = etf_start
    daily_deduct = SAFETY_DEDUCT["bond_30y"] / 252.0
    phase1_mask = synth.index < phase1_end
    if phase1_mask.any():
        phase1_ret = synth[phase1_mask].pct_change().dropna() - daily_deduct
        phase1_corrected = (1 + phase1_ret).cumprod()
        phase1_corrected = phase1_corrected / phase1_corrected.iloc[0]
        if len(phase1_corrected) > 0:
            anchor_idx = phase1_corrected.index[-1]
            if anchor_idx in synth.index:
                phase1_corrected = phase1_corrected * (
                    synth.loc[anchor_idx] / phase1_corrected.iloc[-1])
            post_phase1 = synth[synth.index > phase1_corrected.index[-1]]
            synth = pd.concat([phase1_corrected, post_phase1])

    return synth.sort_index()


def _load_bond_10y() -> pd.Series:
    """加载 10Y 国债序列：bond_10y_etf (2017-08+) + bond_credit proxy(2015-2017-08)。

    cb_10y_idx (sh000139) 在 2015-2019 数据受股灾污染，改用信用债 ETF
    作为 pre-ETF 替代（2015-2017，约 2.5 年），信用债与国债久期相近。
    """
    etf = load_series("bond_10y_etf")  # 511260, 2017-08-04 起
    proxy = load_series("bond_credit")  # 511220, 2015+，作为国债替代

    return stitch_series(etf, proxy, annual_deduct=0.0)


def load_panel() -> pd.DataFrame:
    """加载 9 资产收盘价面板（含缝合，对齐到回测期间，前向填充）。

    7 个资产直接从 2015 拉 ETF NAV，
    3 个资产通过 stitch_series() 缝合早期替代数据。
    """
    # 直接加载的资产（ETF NAV 从 2015 起）
    direct = {k: load_series(k) for k in [
        "hs300", "div_lowvol",
        "bond_credit", "gold", "us_sp500",
    ]}

    # bond_10y: bond_10y_etf(2017-08+) + cb_10y_idx清洗版(2015-2017)
    bond_10y = _load_bond_10y()

    # bond_30y: 三阶段合成（依赖 bond_10y）
    s_30y_etf = load_series("bond_30y_etf")
    bond_30y = synthesize_bond_30y(bond_10y, s_30y_etf)

    # nonferr: 申万有色指数(2015-2019) + ETF(2019+)
    nonferr_etf = load_series("nonferr")
    proxy_path = DATA_DIR / "nonferr_idx.csv"
    if proxy_path.exists():
        nonferr_proxy = pd.read_csv(proxy_path, parse_dates=["date"])\
                          .set_index("date")["close"].sort_index()
        nonferr = stitch_series(nonferr_etf, nonferr_proxy,
                                annual_deduct=SAFETY_DEDUCT["nonferr"])
    else:
        nonferr = nonferr_etf

    # soymeal: 豆粕期货主力(2015-2019) + ETF(2019+)
    soymeal_etf = load_series("soymeal")
    proxy_path = DATA_DIR / "soymeal_fut.csv"
    if proxy_path.exists():
        soymeal_proxy = pd.read_csv(proxy_path, parse_dates=["date"])\
                          .set_index("date")["close"].sort_index()
        soymeal = stitch_series(soymeal_etf, soymeal_proxy,
                                annual_deduct=SAFETY_DEDUCT["soymeal"])
    else:
        soymeal = soymeal_etf

    panel = pd.DataFrame({
        "hs300":    direct["hs300"],
        "div_idx":  direct["div_lowvol"],
        "us_sp500": direct["us_sp500"],
        "credit":   direct["bond_credit"],
        "bond_10y": bond_10y,
        "bond_30y": bond_30y,
        "gold":     direct["gold"],
        "nonferr":  nonferr,
        "soymeal":  soymeal,
    })
    panel.index = pd.to_datetime(panel.index)
    panel = panel.sort_index()
    panel = panel.loc[BACKTEST_START:BACKTEST_END].ffill().dropna()

    return panel


def load_panel_extended() -> pd.DataFrame:
    """加载 10 资产面板（9 基础 + short_bond，用于方案 A/B）。"""
    panel = load_panel()
    short_bond = load_series("bond_short")
    full_idx = panel.index
    short_bond = short_bond.reindex(full_idx).ffill()
    panel["short_bond"] = short_bond
    return panel.dropna()


def get_returns() -> pd.DataFrame:
    """便捷函数：返回日收益率面板。"""
    return load_panel().pct_change().dropna()
