"""数据拉取 - 调用 akshare 拉取 ETF / 指数日频，写入 data/。

仅在数据不齐全时调用；正常回测从已有 CSV 读取。
"""
import os
import sys
import pandas as pd
from .config import DATA_DIR

START = "20150101"
END = "20251231"

# 资产清单：name -> (kind, symbol)
TARGETS = {
    # A 股权益指数
    "hs300":      ("idx", "sh000300"),
    "div_lowvol": ("idx", "sh000922"),  # 中证红利
    # 债券指数
    "cb_10y_idx": ("idx_em", "sh000139"),  # 上证 10 年国债
    # ETF 净值（避开折溢价）
    "bond_30y_etf": ("etf_nav", "511130"),
    "bond_credit":  ("etf_nav", "511220"),
    "gold":         ("etf_nav", "518880"),
    "nonferr":      ("etf_nav", "159980"),
    "soymeal":      ("etf_nav", "159985"),
    # QDII
    "us_sp500":     ("etf_nav", "513500"),
}


def _fetch_idx(sym):
    import akshare as ak
    df = ak.stock_zh_index_daily(symbol=sym)
    df["date"] = pd.to_datetime(df["date"])
    return df[["date", "close"]].sort_values("date")


def _fetch_idx_em(sym):
    import akshare as ak
    df = ak.stock_zh_index_daily_em(symbol=sym)
    df["date"] = pd.to_datetime(df["date"])
    return df[["date", "close"]].sort_values("date")


def _fetch_etf_nav(code):
    import akshare as ak
    df = ak.fund_etf_fund_info_em(fund=code, start_date=START, end_date=END)
    df = df.rename(columns={"净值日期": "date", "累计净值": "close"})
    df["date"] = pd.to_datetime(df["date"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["close"])
    return df[["date", "close"]].sort_values("date")


def _fetch_etf_hist(code):
    import akshare as ak
    df = ak.fund_etf_hist_em(symbol=code, period="daily",
                             start_date=START, end_date=END, adjust="hfq")
    df = df.rename(columns={"日期": "date", "收盘": "close"})
    df["date"] = pd.to_datetime(df["date"])
    return df[["date", "close"]].sort_values("date")


def fetch_one(name, kind, sym):
    if kind == "idx":
        df = _fetch_idx(sym)
    elif kind == "idx_em":
        df = _fetch_idx_em(sym)
    elif kind == "etf_nav":
        df = _fetch_etf_nav(sym)
        if df.empty:
            df = _fetch_etf_hist(sym)
    else:
        raise ValueError(f"unknown kind: {kind}")
    df = df[(df["date"] >= pd.to_datetime(START)) & (df["date"] <= pd.to_datetime(END))]
    return df


def fetch_all(force: bool = False):
    """拉取所有目标资产。force=True 时覆盖已有文件。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"📥 数据目录: {DATA_DIR}")

    ok, errors, skipped = {}, {}, []
    for name, (kind, sym) in TARGETS.items():
        path = DATA_DIR / f"{name}.csv"
        if path.exists() and not force:
            skipped.append(name)
            continue
        print(f"  ▸ {name} ({kind}:{sym})", flush=True)
        try:
            df = fetch_one(name, kind, sym)
            df.to_csv(path, index=False)
            ok[name] = (df["date"].min(), df["date"].max(), len(df))
            print(f"    ok  {df['date'].min().date()} → {df['date'].max().date()}  n={len(df)}")
        except Exception as e:
            errors[name] = str(e)[:200]
            print(f"    ERR  {e}")

    print(f"\n=== 拉取摘要 ===")
    print(f"  成功: {len(ok)}    跳过(已有): {len(skipped)}    失败: {len(errors)}")
    if errors:
        print("  失败明细:")
        for k, v in errors.items():
            print(f"    {k}: {v}")
    return ok, errors, skipped


def check_data_complete() -> bool:
    """检查回测必需的 9 个 CSV 是否齐全。"""
    required = ["hs300", "div_lowvol", "cb_10y_idx", "bond_30y_etf",
                "bond_credit", "gold", "nonferr", "soymeal", "us_sp500"]
    missing = [n for n in required if not (DATA_DIR / f"{n}.csv").exists()]
    return len(missing) == 0, missing


if __name__ == "__main__":
    fetch_all()
