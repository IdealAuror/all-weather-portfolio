"""数据加载层 - 从 data/ 读取 CSV，处理 30Y 国债合成，返回回测期价格表。"""
import pandas as pd
import numpy as np
from .config import DATA_DIR, BACKTEST_START, BACKTEST_END, BOND_30Y_AMP, SAFETY_DEDUCT


def load_series(name: str) -> pd.Series:
    """从 CSV 加载单资产收盘价时间序列（按日期升序）。

    若文件不存在（旧的 ETF 文件可能尚未替换），返回空 Series 而非抛错，
    让调用方有机会降级到 proxy-only 方案。
    """
    path = DATA_DIR / f"{name}.csv"
    if not path.exists():
        return pd.Series(dtype=float)
    df = pd.read_csv(path, parse_dates=["date"])
    return df.set_index("date")["close"].sort_index()


def _load_optional(name: str) -> pd.Series | None:
    """加载可选数据文件；不存在返回 None。"""
    path = DATA_DIR / f"{name}.csv"
    if not path.exists():
        return None
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
    """加载 10Y 国债序列：ETF (2017-08+) + 国债总指数 (2008-2017) + 企债指数 (2005-2008)。"""
    etf = load_series("bond_10y_etf")
    treasury_idx = load_series("treasury_idx")
    credit_idx = load_series("credit_idx")

    if etf.empty and treasury_idx.empty:
        raise FileNotFoundError("bond_10y_etf 和 treasury_idx 都不可用")

    if etf.empty:
        return treasury_idx

    if treasury_idx.empty:
        proxy = credit_idx
    else:
        proxy = stitch_series(treasury_idx, credit_idx, annual_deduct=0.0)

    return stitch_series(etf, proxy, annual_deduct=0.0)


def _load_gold_cny() -> pd.Series:
    """黄金 CNY：ETF (2013+) + 伦敦金×USDCNY (2006-2013) + ETF 持仓推算 (2005-2006)。"""
    etf = load_series("gold")
    london = _load_optional("london_gold")
    usdcny = _load_optional("usdcny")

    if etf.empty and london is None:
        raise FileNotFoundError("gold ETF 和 london_gold 都不可用")

    if london is None or usdcny is None:
        return etf

    combined = london.index.union(usdcny.index).union(etf.index).sort_values()
    london = london.reindex(combined).ffill()
    usdcny = usdcny.reindex(combined).ffill()
    gold_cny = london * usdcny
    gold_cny.name = "close"

    # 2005-2006: 黄金 ETF 持仓数据推算金价（伦敦金数据从 2006-05 起）
    try:
        import akshare as ak
        mg = ak.macro_cons_gold()
        mg["date"] = pd.to_datetime(mg["日期"])
        mg["proxy"] = mg["总价值"] / mg["总库存"]
        mg = mg.set_index("date").sort_index()

        cd = mg.index.intersection(gold_cny.index)
        if len(cd) > 10:
            ratio = (gold_cny.loc[cd] / mg.loc[cd, "proxy"]).mean()
            mg_pre = mg[mg.index < gold_cny.index.min()].copy()
            if len(mg_pre) > 0:
                mg_pre["gold_cny"] = mg_pre["proxy"] * ratio
                full_cal = mg_pre.index.union(usdcny.index).union(
                    pd.date_range(mg_pre.index.min(), gold_cny.index.min(), freq="B"))
                mg_daily = mg_pre["gold_cny"].reindex(full_cal).sort_index().ffill()
                mg_daily = mg_daily[mg_daily.index < gold_cny.index.min()]
                if len(mg_daily) > 0:
                    gold_cny = pd.concat([mg_daily, gold_cny]).sort_index()
    except Exception:
        pass

    if etf.empty:
        return gold_cny

    return stitch_series(etf, gold_cny, annual_deduct=0.0)


def _load_sp500_cny() -> pd.Series:
    """标普500 CNY：ETF (2015+) + .INX×USDCNY。

    us_sp500.csv 当前存的是 ETF NAV（已含 CNY），
    若存在 sp500_idx.csv 则用于 pre-ETF 拼接。
    """
    etf = load_series("us_sp500")
    # 尝试加载 S&P500 指数原始数据 + USDCNY
    sp500_usd = _load_optional("sp500_idx")
    usdcny = _load_optional("usdcny")

    if sp500_usd is None or usdcny is None:
        return etf if not etf.empty else load_series("us_sp500")

    combined = sp500_usd.index.union(usdcny.index).union(etf.index if not etf.empty else []).sort_values()
    sp500_usd = sp500_usd.reindex(combined).ffill()
    usdcny = usdcny.reindex(combined).ffill()
    sp500_cny = sp500_usd * usdcny
    sp500_cny.name = "close"

    if etf.empty:
        return sp500_cny

    return stitch_series(etf, sp500_cny, annual_deduct=0.0)


def _load_with_index(etf_name: str, idx_name: str, annual_deduct: float = 0.0) -> pd.Series:
    """通用：ETF + 指数 proxy 拼接。两文件都不存在则抛错。"""
    etf = load_series(etf_name)
    proxy = _load_optional(idx_name)

    if etf.empty and proxy is None:
        raise FileNotFoundError(f"{etf_name} 和 {idx_name} 都不可用")

    if proxy is None:
        return etf
    if etf.empty:
        return proxy

    return stitch_series(etf, proxy, annual_deduct=annual_deduct)


def load_panel() -> pd.DataFrame:
    """加载 9 资产收盘价面板（含缝合，对齐到回测期间，前向填充）。

    2008+ 延长回测：ETF 上市前的期间用指数/期货/国际价格拼接。
    """
    # 权益：ETF + 指数 proxy
    hs300 = _load_with_index("hs300", "hs300_idx", annual_deduct=0.0)
    credit = _load_with_index("bond_credit", "credit_idx", annual_deduct=0.0)

    # 海外权益 & 黄金：需要用汇率换算
    us_sp500 = _load_sp500_cny()
    gold = _load_gold_cny()

    # 债券
    bond_10y = _load_bond_10y()
    s_30y_etf = load_series("bond_30y_etf")
    bond_30y = synthesize_bond_30y(bond_10y, s_30y_etf)

    # nonferr: 沪铜 (2008-2013) → 申万有色指数 (2013-2019) → ETF (2019+)
    nonferr_etf = load_series("nonferr")
    nonferr_idx = load_series("nonferr_idx")
    shfe_copper = load_series("shfe_copper")

    # 构建 pre-ETF 的完整 proxy 链（铜 → 指数）
    if not shfe_copper.empty and not nonferr_idx.empty:
        nonferr_proxy = stitch_series(nonferr_idx, shfe_copper, annual_deduct=0.0)
    elif not nonferr_idx.empty:
        nonferr_proxy = nonferr_idx
    else:
        nonferr_proxy = shfe_copper

    if not nonferr_etf.empty and not nonferr_proxy.empty:
        nonferr = stitch_series(nonferr_etf, nonferr_proxy,
                                annual_deduct=SAFETY_DEDUCT["nonferr"])
    elif not nonferr_etf.empty:
        nonferr = nonferr_etf
    else:
        nonferr = nonferr_proxy

    # 原油 WTI (USD×USDCNY)
    wti_cny = _load_wti_cny()

    panel = pd.DataFrame({
        "hs300":    hs300,
        "us_sp500": us_sp500,
        "credit":   credit,
        "bond_10y": bond_10y,
        "bond_30y": bond_30y,
        "gold":     gold,
        "nonferr":  nonferr,
        "wti":      wti_cny,
    })
    panel.index = pd.to_datetime(panel.index)
    panel = panel.sort_index()
    panel = panel.loc[BACKTEST_START:BACKTEST_END].ffill().dropna()

    return panel



def _load_wti_cny() -> pd.Series:
    """WTI 原油 CNY：WTI USD × USDCNY，全段扣减 QDII 管理费 1.0%/年。"""
    wti = load_series("wti")
    usdcny = _load_optional("usdcny")
    if wti.empty:
        raise FileNotFoundError("wti data not available")
    if usdcny is None or usdcny.empty:
        return wti  # 无汇率数据时回退 USD
    combined = wti.index.union(usdcny.index).sort_values()
    wti = wti.reindex(combined).ffill()
    usdcny = usdcny.reindex(combined).ffill()
    wti_cny = (wti * usdcny).dropna()
    daily_deduct = SAFETY_DEDUCT.get("wti", 0.0) / 252.0
    if daily_deduct > 0:
        ret = wti_cny.pct_change().fillna(0.0) - daily_deduct
        wti_cny = (1 + ret).cumprod() * wti_cny.iloc[0]
    return wti_cny


def load_hs300_pe(col_index: int = 2) -> pd.Series:
    """加载沪深300 PE 时间序列（日频）。不存在返回空 Series。

    col_index: PE 列索引，默认 2（等权静态市盈率），推荐 7（滚动市盈率中位数）。
    """
    path = DATA_DIR / "hs300_pe.csv"
    if not path.exists():
        return pd.Series(dtype=float)
    df = pd.read_csv(path)
    date_col = df.columns[0]
    pe_col = df.columns[col_index]
    df[date_col] = pd.to_datetime(df[date_col])
    return df.set_index(date_col)[pe_col].sort_index()


def load_hs300_pb(col_index: int = 3) -> pd.Series:
    """加载沪深300 PB 时间序列（日频）。不存在返回空 Series。

    col_index: PB 列索引，默认 3（PB 中位数），2=加权PB，1=PB。
    """
    path = DATA_DIR / "hs300_pb.csv"
    if not path.exists():
        return pd.Series(dtype=float)
    df = pd.read_csv(path)
    date_col = df.columns[0]
    pb_col = df.columns[col_index]
    df[date_col] = pd.to_datetime(df[date_col])
    return df.set_index(date_col)[pb_col].sort_index()


