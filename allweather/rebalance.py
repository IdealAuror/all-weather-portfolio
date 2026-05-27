"""实操再平衡工具 — 根据最新行情计算目标权重，生成调仓指令。

用法：
    py -m allweather.rebalance                 # 交互式
    py -m allweather.rebalance --strat V3c     # 指定策略
    py -m allweather.rebalance --strat B-RP --tier 85

输出：
    1. 各策略目标权重表
    2. 对比当前持仓（如提供）
    3. 买卖清单（份额 + 金额）
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import date

DATA_DIR = Path(__file__).parent.parent / "data"

TICKER_INFO = {
    "hs300":     ("510300", "沪深 300 ETF"),
    "us_sp500":  ("513500", "标普 500 ETF（QDII）"),
    "credit":    ("511220", "城投债 ETF"),
    "bond_10y":  ("511260", "10 年国债 ETF"),
    "bond_30y":  ("511130", "30 年国债 ETF"),
    "gold":      ("518880", "黄金 ETF"),
    "nonferr":   ("159980", "有色金属 ETF"),
}

V3C_ASSETS = ["hs300", "us_sp500", "credit", "bond_30y", "gold", "nonferr"]
V3B_RP_ASSETS = ["hs300", "us_sp500", "credit", "bond_30y", "gold", "nonferr"]
V3B_CON_ASSETS = ["hs300", "us_sp500", "credit", "bond_10y", "bond_30y", "gold", "nonferr"]

V3B_RP_BUCKETS = {
    "增长↑": ["hs300", "us_sp500"],
    "收益垫": ["credit"],
    "增长↓": ["bond_30y"],
    "通胀↑": ["gold", "nonferr"],
}
V3B_CON_BUCKETS = {
    "增长↑": ["hs300", "us_sp500"],
    "收益垫": ["credit"],
    "增长↓10Y": ["bond_10y"],
    "增长↓30Y": ["bond_30y"],
    "通胀↑": ["gold", "nonferr"],
}

STRATEGIES = {
    "V3c": {
        "name": "V3c 多元",
        "assets": V3C_ASSETS,
        "method": "inverse_vol",
        "window": 60,
        "max_w": 0.30,
        "min_w": 0.03,
        "nonferr_trend": 60,
        "buckets": None,
    },
    "B-RP": {
        "name": "V3-B 风险平价(20d)",
        "assets": V3B_RP_ASSETS,
        "method": "hierarchical_rp",
        "window": 20,
        "max_w": 0.20,
        "min_w": 0.02,
        "nonferr_trend": 75,
        "buckets": V3B_RP_BUCKETS,
    },
    "B-Con": {
        "name": "V3-B 保守增强(20d)",
        "assets": V3B_CON_ASSETS,
        "method": "inverse_vol",
        "window": 20,
        "max_w": 0.25,
        "min_w": 0.02,
        "nonferr_trend": 75,
        "buckets": None,
    },
}


def load_prices():
    """用 data.load_panel() 加载全资产面板（含缝合合成）。"""
    from .data import load_panel
    return load_panel()


def inverse_vol_weights(returns, window, max_w, min_w):
    recent = returns.tail(window)
    vols = recent.std() * np.sqrt(252)
    inv_vol = 1 / vols.replace(0, np.nan)
    raw = inv_vol / inv_vol.sum()
    capped = raw.clip(lower=min_w, upper=max_w)
    return capped / capped.sum()


def hierarchical_rp_weights(returns, buckets, window, max_w, min_w):
    recent = returns.tail(window)
    n_buckets = len(buckets)
    bucket_w = {}
    for bname, assets in buckets.items():
        valid = [a for a in assets if a in recent.columns]
        if not valid:
            continue
        brets = recent[valid]
        vols = brets.std() * np.sqrt(252)
        inv = 1 / vols.replace(0, np.nan)
        bucket_w[bname] = inv / inv.sum()

    bucket_alloc = {k: 1.0 / n_buckets for k in bucket_w}
    weights = pd.Series(0.0, index=returns.columns)
    for bname, alloc in bucket_alloc.items():
        if bname in bucket_w:
            weights[bucket_w[bname].index] = bucket_w[bname] * alloc

    capped = weights.clip(lower=min_w, upper=max_w)
    weights = capped / capped.sum()
    return weights


def check_nonferr_trend(prices, window):
    """检查有色金属是否跌破 SMA → True=触发过滤, 应清仓 nonferr。"""
    if "nonferr" not in prices.columns or len(prices) < window:
        return False
    nf = prices["nonferr"]
    sma = nf.iloc[-window:].mean()
    return nf.iloc[-1] < sma


def compute_target_weights(strat_key, prices, cash_ratio=0.0):
    cfg = STRATEGIES[strat_key]
    rets_all = prices.pct_change().dropna()
    rets = rets_all[cfg["assets"]]

    if cfg["method"] == "inverse_vol":
        w = inverse_vol_weights(rets, cfg["window"], cfg["max_w"], cfg["min_w"])
    else:
        w = hierarchical_rp_weights(rets, cfg["buckets"], cfg["window"],
                                     cfg["max_w"], cfg["min_w"])

    nf_triggered = check_nonferr_trend(prices, cfg["nonferr_trend"])
    if nf_triggered and "nonferr" in w.index and "credit" in w.index:
        w["credit"] += w["nonferr"]
        w["nonferr"] = 0.0

    w = w * (1 - cash_ratio)
    return w, nf_triggered


def format_weight_table(strat_key, w, nf_triggered):
    cfg = STRATEGIES[strat_key]
    lines = []
    lines.append(f"\n{'='*70}")
    lines.append(f"  {cfg['name']} — 目标权重")
    lines.append(f"  方法: {cfg['method']}, 窗口: {cfg['window']}d, "
                 f"max_w={cfg['max_w']}, min_w={cfg['min_w']}")
    if cfg['nonferr_trend']:
        flag = " ⚠ 已触发!" if nf_triggered else " 正常"
        lines.append(f"  nonferr 趋势过滤({cfg['nonferr_trend']}d SMA):{flag}")
    lines.append(f"{'='*70}")
    lines.append(f"{'资产':<25} {'代码':<8} {'目标权重':>8}")
    lines.append("-" * 45)
    for a in cfg["assets"]:
        code, name = TICKER_INFO[a]
        pct = w.get(a, 0) * 100
        lines.append(f"{name:<25} {code:<8} {pct:>7.1f}%")
    if nf_triggered and w.get("nonferr", 0) == 0:
        lines.append(f"  → nonferr 跌破 SMA，权重已转入 credit")
    lines.append(f"{' '*25} {'合计':<8} {w.sum()*100:>7.1f}%")
    return "\n".join(lines)


def format_trade_list(strat_key, target_w, holdings_dict, total_value):
    cfg = STRATEGIES[strat_key]
    lines = []
    lines.append(f"\n{'='*70}")
    lines.append(f"  调仓清单 — {cfg['name']}")
    lines.append(f"  组合总市值: ¥{total_value:,.0f}")
    lines.append(f"{'='*70}")
    lines.append(f"{'资产':<12} {'代码':<8} {'当前':>10} {'目标':>10} {'差额':>10} {'操作':>12}")
    lines.append("-" * 70)

    any_trade = False
    for a in cfg["assets"]:
        code, name = TICKER_INFO[a]
        target = target_w.get(a, 0) * total_value
        current = holdings_dict.get(a, 0)
        diff = target - current

        if abs(diff) < total_value * 0.005:
            action = "不动"
        elif diff > 0:
            action = f"买入 ¥{diff:,.0f}"
            any_trade = True
        else:
            action = f"卖出 ¥{-diff:,.0f}"
            any_trade = True

        lines.append(f"{name:<12} {code:<8} ¥{current:>9,.0f} ¥{target:>9,.0f} "
                     f"{'+' if diff>=0 else ''}¥{diff:>8,.0f} {action:>12}")

    if not any_trade:
        lines.append("\n  ✓ 所有资产偏离 < 0.5%，无需调仓")
    return "\n".join(lines)


def parse_holdings_input():
    """交互式输入当前持仓。"""
    print("\n输入当前持仓金额（元），直接回车跳过该项：")
    holdings = {}
    for key, (code, name) in TICKER_INFO.items():
        try:
            inp = input(f"  {name} ({code}): ").strip()
            if inp:
                holdings[key] = float(inp.replace(",", "").replace("万", "0000"))
        except (ValueError, KeyboardInterrupt):
            print("  已跳过")
    return holdings


def validate_holdings(holdings, assets):
    for k, v in holdings.items():
        if v < 0:
            raise ValueError(f"{TICKER_INFO[k][1]} 金额不能为负: {v}")
    total = sum(holdings.values())
    if total <= 0:
        raise ValueError("持仓总市值必须 > 0")
    return total


def main():
    args = sys.argv[1:]
    strat_key = None
    tier = None

    i = 0
    while i < len(args):
        if args[i] == "--strat" and i + 1 < len(args):
            strat_key = args[i + 1]; i += 2
        elif args[i] == "--tier" and i + 1 < len(args):
            tier = args[i + 1]; i += 2
        elif args[i] in ("-h", "--help"):
            print(__doc__)
            return
        else:
            i += 1

    if strat_key not in STRATEGIES:
        print("可选策略: V3c / B-RP / B-Con")
        strat_key = input("选择策略: ").strip()
        if strat_key not in STRATEGIES:
            print(f"无效策略: {strat_key}")
            return

    if tier not in ("100", "85", "70"):
        tier = input("现金档位 (100/85/70, 默认 100): ").strip() or "100"
    cash_ratio = 1 - int(tier) / 100

    print(f"\n加载行情数据...")
    prices = load_prices()

    cfg = STRATEGIES[strat_key]
    missing = [a for a in cfg["assets"] if a not in prices.columns]
    if missing:
        print(f"缺少数据: {missing}")
        return

    last_date = prices.index[-1].strftime("%Y-%m-%d")
    print(f"最新数据日期: {last_date}")

    w, nf_triggered = compute_target_weights(strat_key, prices, cash_ratio)
    print(format_weight_table(strat_key, w, nf_triggered))

    has_holdings = input("\n有当前持仓数据吗？输入金额生成调仓清单 (y/n): ").strip().lower()
    if has_holdings == "y":
        holdings = parse_holdings_input()
        if holdings:
            try:
                total = validate_holdings(holdings, cfg["assets"])
                print(format_trade_list(strat_key, w, holdings, total))
            except ValueError as e:
                print(f"输入错误: {e}")
                return

    print(f"\n{'='*70}")
    print("  调仓规则:")
    print(f"  1. 每月最后一个交易日执行一次")
    if cfg["nonferr_trend"]:
        print(f"  2. 检查 nonferr vs {cfg['nonferr_trend']}d SMA — 跌破则清仓转 credit")
    print(f"  3. 先卖后买 — 卖出资金 T+0 可用后再买入")
    print(f"  4. 偏离 < 0.5% 不用动，省手续费")
    print(f"  5. 标普 500 QDII 经常限购，买不到用场外联接 050025 替代")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
