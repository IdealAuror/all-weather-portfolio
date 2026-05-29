"""数据拉取 - 调用 akshare 拉取 ETF / 指数日频，写入 data/。

仅在数据不齐全时调用；正常回测从已有 CSV 读取。
"""
import time
import pandas as pd
from .config import DATA_DIR

RETRY_TIMES = 3
RETRY_DELAY = 5  # 秒

DEFAULT_START = "20050101"
DEFAULT_END   = "20260430"

# 资产清单：name -> (kind, symbol)
TARGETS = {
    # A 股权益 ETF NAV（含分红，不用价格指数）
    "hs300":      ("etf_nav", "510300"),
    # 债券指数
    # ETF 净值（避开折溢价）
    "bond_30y_etf": ("etf_nav", "511130"),
    "bond_10y_etf": ("etf_nav", "511260"),
    "bond_credit":  ("etf_nav", "511220"),
    "gold":         ("etf_nav", "518880"),
    "nonferr":      ("etf_nav", "159980"),
    "soymeal":      ("etf_nav", "159985"),
    # QDII
    "us_sp500":     ("etf_nav", "513500"),
    # 短债/货币
    # 缝合用替代数据
    "nonferr_idx":  ("idx", "sh000823"),   # 中证有色金属指数
    "soymeal_fut":  ("fut_dce", "M0"),     # 豆粕期货主力连续（DCE）
    # 2008+ 延长回测数据源
    "hs300_idx":    ("idx", "sh000300"),   # CSI 300 指数 (2008+)
    "credit_idx":   ("idx", "sh000013"),   # 上证企债指数 (2008+)
    "treasury_idx": ("treasury", None),    # 国债总指数 (2008+)
    "london_gold":  ("foreign_fut", "XAU"),  # 伦敦金 USD/oz (2006+)
    "shfe_copper":  ("sina_fut", "CU0"),   # 沪铜连续 (2005+)
    "usdcny":       ("fx_boc", "USDCNY"),  # 美元人民币汇率 (2008+)
    "sp500_idx":    ("sp500", None),       # S&P500 指数 USD (2008+)
}


def _fetch_idx(sym):
    import akshare as ak
    df = ak.stock_zh_index_daily(symbol=sym)
    df["date"] = pd.to_datetime(df["date"])
    return df[["date", "close"]].sort_values("date")

def _fetch_idx_tx(sym):
    """腾讯证券指数接口，作为备用。"""
    import akshare as ak
    df = ak.stock_zh_index_daily_tx(symbol=sym)
    df["date"] = pd.to_datetime(df["date"])
    return df[["date", "close"]].sort_values("date")


def _fetch_idx_em(sym):
    import akshare as ak
    df = ak.stock_zh_index_daily_em(symbol=sym)
    df["date"] = pd.to_datetime(df["date"])
    return df[["date", "close"]].sort_values("date")


def _fetch_etf_nav(code, start, end):
    import akshare as ak
    df = ak.fund_etf_fund_info_em(fund=code, start_date=start, end_date=end)
    # 列顺序固定：净值日期, 单位净值, 累计净值, 日增长率, 申购状态, 赎回状态
    # 用位置重命名，避免编码乱码导致 rename 失败
    df.columns = ["date", "unit_nav", "close", "daily_chg", "buy", "sell"]
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["date", "close"])
    return df[["date", "close"]].sort_values("date")


def _fetch_etf_hist(code, start, end):
    import akshare as ak
    df = ak.fund_etf_hist_em(symbol=code, period="daily",
                             start_date=start, end_date=end, adjust="hfq")
    df = df.rename(columns={"日期": "date", "收盘": "close"})
    df["date"] = pd.to_datetime(df["date"])
    return df[["date", "close"]].sort_values("date")


def _fetch_fut_dce(sym, start, end):
    """拉取 DCE 期货主力连续合约日频数据。"""
    import akshare as ak
    df = ak.futures_main_sina(symbol=sym)
    df = df.rename(columns={"日期": "date", "收盘价": "close"})
    df["date"] = pd.to_datetime(df["date"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["date", "close"])
    df = df[(df["date"] >= pd.to_datetime(start)) & (df["date"] <= pd.to_datetime(end))]
    return df[["date", "close"]].sort_values("date")


def fetch_one(name, kind, sym, start=DEFAULT_START, end=DEFAULT_END):
    last_err = None
    for attempt in range(1, RETRY_TIMES + 1):
        try:
            if kind == "idx":
                df = _fetch_idx(sym)
                # 新浪接口数据可能截止较早，不覆盖请求范围时降级到腾讯
                if df.empty or df["date"].max() < pd.to_datetime(end) - pd.Timedelta(days=30):
                    df = _fetch_idx_tx(sym)
            elif kind == "idx_em":
                try:
                    df = _fetch_idx_em(sym)
                    if df.empty or df["date"].max() < pd.to_datetime(end) - pd.Timedelta(days=30):
                        raise ValueError("数据不足，降级到腾讯")
                except Exception:
                    df = _fetch_idx_tx(sym)
            elif kind == "fut_dce":
                df = _fetch_fut_dce(sym, start, end)
            elif kind == "etf_nav":
                df = _fetch_etf_nav(sym, start, end)
                if df.empty:
                    df = _fetch_etf_hist(sym, start, end)
            elif kind == "treasury":
                df = _fetch_treasury_idx(start, end)
            elif kind == "foreign_fut":
                df = _fetch_foreign_fut(sym, start, end)
            elif kind == "sina_fut":
                df = _fetch_sina_fut(sym, start, end)
            elif kind == "fx_boc":
                df = _fetch_fx_boc(start, end)
            elif kind == "sp500":
                df = _fetch_sp500_idx(start, end)
            else:
                raise ValueError(f"unknown kind: {kind}")
            df = df[(df["date"] >= pd.to_datetime(start)) & (df["date"] <= pd.to_datetime(end))]
            return df
        except ValueError:
            raise
        except Exception as e:
            last_err = e
            if attempt < RETRY_TIMES:
                print(f"    重试 {attempt}/{RETRY_TIMES - 1}，等待 {RETRY_DELAY}s... ({e})", flush=True)
                time.sleep(RETRY_DELAY)
    raise last_err


def _fetch_treasury_idx(start, end):
    """国债总指数 (bond_treasury_index_cbond)，2008+。"""
    import akshare as ak
    df = ak.bond_treasury_index_cbond()
    df["date"] = pd.to_datetime(df["date"])
    df = df.rename(columns={"value": "close"})
    df = df[(df["date"] >= pd.to_datetime(start)) & (df["date"] <= pd.to_datetime(end))]
    return df[["date", "close"]].sort_values("date")


def _fetch_foreign_fut(sym, start, end):
    """国际期货历史数据 (futures_foreign_hist)，例如 XAU 伦敦金。"""
    import akshare as ak
    df = ak.futures_foreign_hist(symbol=sym)
    df["date"] = pd.to_datetime(df["date"])
    df = df.rename(columns={"close": "close"})
    df = df[(df["date"] >= pd.to_datetime(start)) & (df["date"] <= pd.to_datetime(end))]
    return df[["date", "close"]].sort_values("date")


def _fetch_sina_fut(sym, start, end):
    """新浪期货主力连续 (futures_main_sina)，如 CU0 沪铜。"""
    import akshare as ak
    df = ak.futures_main_sina(symbol=sym)
    df = df.rename(columns={"日期": "date", "收盘价": "close"})
    df["date"] = pd.to_datetime(df["date"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["date", "close"])
    df = df[(df["date"] >= pd.to_datetime(start)) & (df["date"] <= pd.to_datetime(end))]
    return df[["date", "close"]].sort_values("date")


def _fetch_fx_boc(start, end):
    """美元人民币汇率 (currency_boc_sina)，取央行中间价。"""
    import akshare as ak
    df = ak.currency_boc_sina(symbol="美元", start_date=start, end_date=end)
    df = df.rename(columns={"日期": "date", "央行中间价": "close"})
    df["date"] = pd.to_datetime(df["date"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce") / 100.0  # 分→元
    df = df.dropna(subset=["date", "close"])
    return df[["date", "close"]].sort_values("date")


def _fetch_sp500_idx(start, end):
    """S&P500 指数 USD (index_us_stock_sina .INX)。"""
    import akshare as ak
    df = ak.index_us_stock_sina(symbol=".INX")
    df["date"] = pd.to_datetime(df["date"])
    df = df[(df["date"] >= pd.to_datetime(start)) & (df["date"] <= pd.to_datetime(end))]
    return df[["date", "close"]].sort_values("date")


def fetch_cgb_yields():
    """拉取中债国债收益率曲线。失败返回 None。

    返回的 DataFrame 通过位置匹配列名，避免中文编码问题。
    """
    try:
        import akshare as ak
        df = ak.bond_china_yield()
        if df is None or df.empty:
            return None
        if "曲线名称" in df.columns:
            df = df[df["曲线名称"].str.contains("国债", na=False)]
        return df
    except Exception:
        return None


def fetch_all(force: bool = False, start: str = DEFAULT_START, end: str = DEFAULT_END):
    """拉取所有目标资产。

    Args:
        force: True 时覆盖已有文件
        start: 起始日期，格式 YYYYMMDD，默认 20150101
        end:   结束日期，格式 YYYYMMDD，默认 20251231
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[fetch] 数据目录: {DATA_DIR}")
    print(f"[fetch] 拉取区间: {start} ~ {end}")

    ok, errors, skipped = {}, {}, []
    for name, (kind, sym) in TARGETS.items():
        path = DATA_DIR / f"{name}.csv"
        if path.exists() and not force:
            skipped.append(name)
            continue
        print(f"  >> {name} ({kind}:{sym})", flush=True)
        try:
            df = fetch_one(name, kind, sym, start=start, end=end)
            df.to_csv(path, index=False)
            ok[name] = (df["date"].min(), df["date"].max(), len(df))
            print(f"    ok  {df['date'].min().date()} → {df['date'].max().date()}  n={len(df)}")
        except Exception as e:
            errors[name] = str(e)[:200]
            print(f"    ERR  {e}")

    # 尝试拉取中债国债收益率曲线
    print(f"  >> cgb_yields (bond_china_yield)", flush=True)
    yield_df = fetch_cgb_yields()
    if yield_df is not None and not yield_df.empty:
        yield_path = DATA_DIR / "cgb_yields.csv"
        yield_df.to_csv(yield_path, index=False, encoding="utf-8")
        print(f"    ok  n={len(yield_df)}")
    else:
        print(f"    WARN  中债收益率曲线拉取失败，将使用久期放大回退方案合成 30Y")

    print(f"\n=== 拉取摘要 ===")
    print(f"  成功: {len(ok)}    跳过(已有): {len(skipped)}    失败: {len(errors)}")
    if errors:
        print("  失败明细:")
        for k, v in errors.items():
            print(f"    {k}: {v}")
    return ok, errors, skipped


def check_data_complete() -> bool:
    """检查回测必需的 CSV 是否齐全。"""
    required = ["hs300", "bond_30y_etf",
                "bond_credit", "gold", "nonferr", "soymeal", "us_sp500"]
    missing = [n for n in required if not (DATA_DIR / f"{n}.csv").exists()]
    return len(missing) == 0, missing


if __name__ == "__main__":
    fetch_all()