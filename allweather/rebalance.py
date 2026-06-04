"""实操再平衡工具 — 根据最新行情计算目标权重 + 全信号仪表盘 + 三策略对比。

用法：
    python -m allweather.rebalance                 # 交互式，三策略对比
    python -m allweather.rebalance --strat V3c     # 看单个策略详情
    python -m allweather.rebalance --strat B-RP --tier 85
    python -m allweather.rebalance --signals       # 只看当前信号状态
    python -m allweather.rebalance --strat V3c --amount 500000   # 建仓清单
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path
from .config import (
    ROOT, ASSETS, ETF_META,
    RISK_PARITY_WINDOW, RISK_PARITY_MAX_WEIGHT, RISK_PARITY_MIN_WEIGHT,
    GOLD_DIP_THRESHOLD, GOLD_DIP_BOOST,
    HS300_DIP_THRESHOLD, HS300_DIP_BOOST,
    HS300_PB_ENTRY, HS300_PE_EXIT, HS300_DIP_EXIT_RECOVERY,
    SP500_TREND_WINDOW,
)
from .risk import inverse_vol_weights, hierarchical_rp_weights

# === 策略定义 ===
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
        "name": "V3c 多元", "assets": V3C_ASSETS,
        "method": "inverse_vol", "window": 60,
        "max_w": 0.30, "min_w": 0.03,
    },
    "B-RP": {
        "name": "V3-B 风险平价(20d)", "assets": V3B_RP_ASSETS,
        "method": "hierarchical_rp", "window": 20,
        "max_w": 0.20, "min_w": 0.02,
        "buckets": V3B_RP_BUCKETS,
    },
    "B-Con": {
        "name": "V3-B 保守增强(20d)", "assets": V3B_CON_ASSETS,
        "method": "inverse_vol", "window": 20,
        "max_w": 0.25, "min_w": 0.02,
    },
}

LINE = "=" * 72


# ============================================================
# 信号状态检测
# ============================================================

def _sma_filter(prices, asset, window):
    """资产跌破 SMA → 返回 True（应清仓）。"""
    if asset not in prices.columns or len(prices) < window:
        return False
    s = prices[asset]
    return s.iloc[-1] < s.iloc[-window:].mean()


def _drawdown(prices, asset, lookback=252):
    """当前从 N 日高点的回撤。"""
    if asset not in prices.columns or len(prices) < lookback:
        return 0.0
    s = prices[asset].iloc[-lookback:]
    peak = s.max()
    return s.iloc[-1] / peak - 1


def compute_signal_states(prices):
    """返回当前所有风控信号状态。"""
    rets = prices.pct_change().dropna()
    latest = prices.index[-1]
    d = latest

    signals = {}

    # --- SMA trend filters ---
    signals["nonferr_below_sma75"] = _sma_filter(prices, "nonferr", 75)
    signals["gold_below_sma75"] = _sma_filter(prices, "gold", 75)
    signals["sp500_below_sma120"] = _sma_filter(prices, "us_sp500", SP500_TREND_WINDOW)

    # --- Gold dip ---
    gold_dd = _drawdown(prices, "gold", 252)
    signals["gold_dd_pct"] = gold_dd
    signals["gold_dip_active"] = gold_dd <= -GOLD_DIP_THRESHOLD

    # --- HS300 dip ---
    hs300_dd = _drawdown(prices, "hs300", 756)
    signals["hs300_dd_pct"] = hs300_dd

    # HS300 SMA check (> SMA120 for entry)
    hs300_sma120 = prices["hs300"].iloc[-120:].mean() if len(prices) >= 120 else 0
    signals["hs300_above_sma120"] = prices["hs300"].iloc[-1] > hs300_sma120 if len(prices) >= 120 else False

    # HS300 PB/PE percentile
    try:
        pb_data = load_hs300_pb()
        pe_data = load_hs300_pe()
        if pb_data is not None and len(pb_data[pb_data.index <= d]) >= 252:
            pb_to = pb_data[pb_data.index <= d]
            pb_val = pb_to.iloc[-1]
            pb_pct = (pb_to < pb_val).sum() / len(pb_to) * 100
            signals["pb_pctile"] = float(pb_pct)
            signals["pb_entry_ok"] = pb_pct < HS300_PB_ENTRY
        else:
            signals["pb_pctile"] = None
            signals["pb_entry_ok"] = False

        if pe_data is not None and len(pe_data[pe_data.index <= d]) >= 252:
            pe_to = pe_data[pe_data.index <= d]
            pe_val = pe_to.iloc[-1]
            pe_pct = (pe_to < pe_val).sum() / len(pe_to) * 100
            signals["pe_pctile"] = float(pe_pct)
            signals["pe_exit_ok"] = pe_pct < HS300_PE_EXIT
        else:
            signals["pe_pctile"] = None
            signals["pe_exit_ok"] = False
    except (FileNotFoundError, OSError):
        signals["pb_pctile"] = None
        signals["pe_pctile"] = None
        signals["pb_entry_ok"] = False
        signals["pe_exit_ok"] = False

    # HS300 AND condition
    dd_ok = signals["hs300_dd_pct"] <= -HS300_DIP_THRESHOLD
    pb_ok = signals.get("pb_entry_ok", False)
    sma_ok = signals.get("hs300_above_sma120", False)
    signals["hs300_dip_ready"] = dd_ok and pb_ok and sma_ok
    signals["hs300_dip_exit"] = signals.get("pe_exit_ok", True) is False

    return signals


# ============================================================
# 权重计算
# ============================================================

def compute_target_weights(strat_key, prices, cash_ratio=0.0):
    cfg = STRATEGIES[strat_key]
    rets_all = prices.pct_change().dropna()
    rets = rets_all[cfg["assets"]].dropna()

    if cfg["method"] == "inverse_vol":
        w = inverse_vol_weights(rets, cfg["window"], cfg["max_w"], cfg["min_w"])
    else:
        w = hierarchical_rp_weights(rets, cfg["buckets"], cfg["window"],
                                     cfg["max_w"], cfg["min_w"])
    return w * (1 - cash_ratio)


def apply_signal_overrides(strat_key, w, signals):
    """按策略应用各风控措施到目标权重。"""
    w = w.copy()

    # nonferr trend filter (all strategies)
    if signals.get("nonferr_below_sma75", False) and "nonferr" in w.index and "credit" in w.index:
        if w["nonferr"] > 0:
            w["credit"] += w["nonferr"]
            w["nonferr"] = 0.0

    # gold trend filter (only V3-B RP)
    if strat_key == "B-RP":
        if signals.get("gold_below_sma75", False) and "gold" in w.index and "credit" in w.index:
            if w["gold"] > 0:
                w["credit"] += w["gold"]
                w["gold"] = 0.0

    # SP500 trend filter (all strategies now include it)
    if signals.get("sp500_below_sma120", False) and "us_sp500" in w.index and "credit" in w.index:
        if w["us_sp500"] > 0:
            w["credit"] += w["us_sp500"]
            w["us_sp500"] = 0.0

    # Gold dip (V3c and B-Con use cap 0.20)
    if signals.get("gold_dip_active", False) and "gold" in w.index and "credit" in w.index:
        if w["gold"] > 0:
            boost = w["gold"] * GOLD_DIP_BOOST
            if w["credit"] >= boost:
                w["gold"] += boost
                w["credit"] -= boost
                if strat_key in ("V3c", "B-Con"):
                    cap = 0.20
                    if w["gold"] > cap:
                        w["credit"] += w["gold"] - cap
                        w["gold"] = cap

    # HS300 AND dip
    if signals.get("hs300_dip_ready", False) and "hs300" in w.index and "credit" in w.index:
        if w["hs300"] > 0:
            boost = w["hs300"] * (HS300_DIP_BOOST - 1)
            if w["credit"] >= boost:
                w["hs300"] += boost
                w["credit"] -= boost

    return w / w.sum()  # renormalize to 1.0


# ============================================================
# 显示格式
# ============================================================

def _pct(v):
    return f"{v*100:>6.1f}%"


def _fmt_bool(v, yes="触发", no="正常"):
    return yes if v else no


def display_signal_dashboard(signals):
    """风控信号仪表盘。"""
    print(f"\n{LINE}")
    print("  当前市场信号状态")
    print(LINE)

    au_dd = signals.get("gold_dd_pct", 0)
    hs_dd = signals.get("hs300_dd_pct", 0)

    print(f"  nonferr vs SMA75:  {_fmt_bool(signals['nonferr_below_sma75'])}")
    print(f"  gold vs SMA75:     {_fmt_bool(signals['gold_below_sma75'])}")
    print(f"  SP500 vs SMA120:   {_fmt_bool(signals['sp500_below_sma120'])}")
    print(f"  Gold 回撤:         {au_dd*100:>5.1f}%  ({_fmt_bool(signals['gold_dip_active'], '可抄底', '未触发')})")
    print(f"  HS300 回撤:        {hs_dd*100:>5.1f}%  ({_fmt_bool(signals['hs300_dd_pct'] <= -HS300_DIP_THRESHOLD, '深度回撤', '正常')})")

    pb = signals.get("pb_pctile")
    pe = signals.get("pe_pctile")
    print(f"  PB 分位:           {f'{pb:.0f}%ile' if pb is not None else 'n/a'}  "
          f"({_fmt_bool(signals.get('pb_entry_ok', False), '便宜 [OK]', '偏贵')})")
    print(f"  PE 分位:           {f'{pe:.0f}%ile' if pe is not None else 'n/a'}  "
          f"({_fmt_bool(pe is not None and pe < 70, '正常', '偏贵需出场')})")
    print(f"  HS300 AND 抄底:    {'[已就绪]' if signals['hs300_dip_ready'] else '[等待条件]'}")


def display_weight_table(strat_key, w, signals):
    """单个策略详细权重表。"""
    cfg = STRATEGIES[strat_key]

    print(f"\n{LINE}")
    print(f"  {cfg['name']}")
    print(f"  方法: {cfg['method']}, 窗口: {cfg['window']}d, "
          f"max_w={cfg['max_w']}, min_w={cfg['min_w']}")
    print(LINE)
    print(f"  {'资产':<22} {'代码':<8} {'权重':>8}  |  {'风控状态':<20}")
    print("  " + "-" * 72)

    for a in cfg["assets"]:
        meta = ETF_META.get(a, {"code": "", "name": a})
        pct = w.get(a, 0)
        status = []
        if a == "nonferr" and signals.get("nonferr_below_sma75", False) and pct == 0:
            status.append("趋势过滤→credit")
        if a == "gold" and signals.get("gold_below_sma75", False) and pct == 0:
            status.append("趋势过滤→credit")
        if a == "gold" and signals.get("gold_dip_active", False) and pct > 0:
            status.append(f"抄底×{GOLD_DIP_BOOST:.0f}")
        if a == "us_sp500" and signals.get("sp500_below_sma120", False) and pct == 0:
            status.append("趋势过滤→credit")
        if a == "hs300" and signals.get("hs300_dip_ready", False) and pct > 0:
            status.append(f"AND抄底×{HS300_DIP_BOOST:.1f}")
        if a == "credit":
            nf = signals.get("nonferr_below_sma75", False)
            sp = signals.get("sp500_below_sma120", False)
            au = signals.get("gold_below_sma75", False)
            incoming = []
            if nf: incoming.append("nonferr")
            if sp: incoming.append("SP500")
            if au: incoming.append("gold")
            if incoming:
                status.append(f"接收{'/'.join(incoming)}")
        s = ", ".join(status) if status else "—"
        print(f"  {meta['name']:<22} {meta['code']:<8} {_pct(pct):>8}  |  {s:<20}")

    print(f"  {'':<22} {'合计':<8} {_pct(w.sum()):>8}")


def display_all_strategies(prices, signals, tier="100"):
    """三策略目标权重同屏对比。"""
    cash_ratio = 1 - int(tier) / 100
    results = {}
    for k in ["V3c", "B-RP", "B-Con"]:
        w0 = compute_target_weights(k, prices, cash_ratio)
        w1 = apply_signal_overrides(k, w0, signals)
        results[k] = w1

    print(f"\n{LINE}")
    print(f"  三策略目标权重对比（{tier}% RP）  数据: {prices.index[-1].date()}")
    print(LINE)

    # Header
    print(f"  {'资产':<22} {'代码':<8}", end="")
    for k in ["V3c", "B-RP", "B-Con"]:
        print(f"{STRATEGIES[k]['name']:>20}", end="")
    print()

    print("  " + "-" * 80)

    for a in ASSETS:
        meta = ETF_META.get(a, {"code": "", "name": a})
        print(f"  {meta['name']:<22} {meta['code']:<8}", end="")
        for k in ["V3c", "B-RP", "B-Con"]:
            pct = results[k].get(a, 0)
            print(f"{_pct(pct):>20}", end="")
        print()

    print(f"  {'':<22} {'合计':<8}", end="")
    for k in ["V3c", "B-RP", "B-Con"]:
        print(f"{_pct(results[k].sum()):>20}", end="")
    print()


def display_trade_list(strat_key, target_w, holdings_dict, total_value):
    """生成买卖清单。"""
    cfg = STRATEGIES[strat_key]
    print(f"\n{LINE}")
    print(f"  调仓清单 --- {cfg['name']}   组合总市值: RMB {total_value:,.0f}")
    print(LINE)
    print(f"  {'资产':<22} {'代码':<8} {'当前':>10} {'目标':>10} {'差额':>10}  {'操作':<12}")
    print("  " + "-" * 72)

    any_trade = False
    for a in cfg["assets"]:
        meta = ETF_META.get(a, {"code": "", "name": a})
        target = target_w.get(a, 0) * total_value
        current = holdings_dict.get(a, 0)
        diff = target - current

        if abs(diff) < total_value * 0.005:
            action = "不动"
        elif diff > 0:
            action = f"买入 RMB {diff:>8,.0f}"
            any_trade = True
        else:
            action = f"卖出 RMB {-diff:>8,.0f}"
            any_trade = True

        print(f"  {meta['name']:<22} {meta['code']:<8} "
              f"RMB {current:>8,.0f} RMB {target:>8,.0f} "
              f"{'+' if diff>=0 else '-'}RMB {abs(diff):>8,.0f}  {action:<12}")

    if not any_trade:
        print(f"\n  [OK] 所有资产偏离 < 0.5%，无需调仓")


def display_build_plan(strat_key, w, prices, total_amount):
    """建仓买入清单。从零开始，计算各 ETF 买入金额和股数。"""
    cfg = STRATEGIES[strat_key]
    latest = prices.iloc[-1]
    lot_size = 100

    print(f"\n{LINE}")
    print(f"  建仓清单 --- {cfg['name']}    总投资: RMB {total_amount:,.0f}")
    print(LINE)
    print(f"  {'资产':<22} {'代码':<8} {'权重':>6} {'目标金额':>12} {'现价':>8} {'买入股数':>8} {'预估金额':>12}")
    print("  " + "-" * 80)

    total_used = 0
    for a in cfg["assets"]:
        meta = ETF_META.get(a, {"code": "", "name": a})
        pct = w.get(a, 0)
        if pct <= 0:
            continue
        amount = pct * total_amount
        price = float(latest.get(a, np.nan))
        if np.isnan(price) or price <= 0:
            continue
        shares = int(amount / price / lot_size) * lot_size
        actual = shares * price
        total_used += actual
        print(f"  {meta['name']:<22} {meta['code']:<8} {_pct(pct):>6} "
              f"RMB {amount:>8,.0f} {price:>8.3f} {shares:>8d} RMB {actual:>8,.0f}")

    remainder = total_amount - total_used
    if remainder > 0:
        print(f"  {'剩余现金/货基':<22} {'':<8} {'':>6} {'':>12} {'':>8} {'':>8} RMB {remainder:>8,.0f}")
    print(f"  {'':<22} {'合计':<8} {'100.0%':>6} RMB {total_amount:>8,.0f}")
    print(f"  提示: 建仓后剩余现金放入货币基金或华宝添益(511990)")
    if any(a == "us_sp500" for a in cfg["assets"]) and w.get("us_sp500", 0) > 0:
        print(f"  提示: 标普500 QDII 经常限购，买不到用场外联接 050025 替代")


def parse_holdings_input():
    """交互式输入当前持仓。"""
    print("\n输入当前持仓金额（元），直接回车跳过该项：")
    holdings = {}
    for key, (code, name) in ETF_META.items():
        try:
            inp = input(f"  {name} ({code}): ").strip()
            if inp:
                holdings[key] = float(inp.replace(",", "").replace("万", "0000"))
        except (ValueError, KeyboardInterrupt):
            print("  已跳过")
    return holdings


# ============================================================
# 数据加载
# ============================================================

def load_hs300_pb():
    from .data import load_hs300_pb as _load
    return _load()

def load_hs300_pe():
    from .data import load_hs300_pe as _load
    return _load()

def load_prices():
    from .data import load_panel
    return load_panel()


# ============================================================
# 主入口
# ============================================================

def main():
    args = sys.argv[1:]
    strat_key = None
    tier = None
    show_signals_only = False
    build_amount = None

    i = 0
    while i < len(args):
        if args[i] == "--strat" and i + 1 < len(args):
            strat_key = args[i + 1]; i += 2
        elif args[i] == "--tier" and i + 1 < len(args):
            tier = args[i + 1]; i += 2
        elif args[i] in ("--signals", "-s"):
            show_signals_only = True; i += 1
        elif args[i] == "--amount" and i + 1 < len(args):
            build_amount = float(args[i + 1]); i += 2
        elif args[i] in ("-h", "--help"):
            print(__doc__)
            return
        else:
            i += 1

    if strat_key is not None and strat_key not in STRATEGIES:
        print(f"可选策略: {' / '.join(STRATEGIES.keys())}")
        return

    if tier is None:
        tier = "100"
    if tier not in ("100", "85", "70"):
        tier = "100"

    print(f"加载行情数据...")
    prices = load_prices()
    last_date = prices.index[-1].strftime("%Y-%m-%d")
    print(f"最新数据: {last_date}  |  共 {len(prices)} 个交易日\n")

    signals = compute_signal_states(prices)

    # --signals: 只看信号
    if show_signals_only:
        display_signal_dashboard(signals)
        print()
        return

    # 指定单一策略
    if strat_key:
        cfg = STRATEGIES[strat_key]
        missing = [a for a in cfg["assets"] if a not in prices.columns]
        if missing:
            print(f"缺少数据: {missing}")
            return

        cash_ratio = 1 - int(tier) / 100
        w0 = compute_target_weights(strat_key, prices, cash_ratio)
        w = apply_signal_overrides(strat_key, w0, signals)

        display_signal_dashboard(signals)
        display_weight_table(strat_key, w, signals)

        if build_amount:
            display_build_plan(strat_key, w, prices, build_amount)
        else:
            amt = input("\n建仓金额？(输入数字生成买入清单，直接回车跳过): ").strip()
            if amt:
                try:
                    display_build_plan(strat_key, w, prices, float(amt))
                except ValueError:
                    pass
            else:
                has_holdings = input("\n有当前持仓数据吗？生成调仓清单 (y/n): ").strip().lower()
                if has_holdings == "y":
                    holdings = parse_holdings_input()
                    if holdings:
                        total = sum(holdings.values())
                        if total > 0 and all(v >= 0 for v in holdings.values()):
                            display_trade_list(strat_key, w, holdings, total)

    else:
        # 默认：三策略对比 + 信号仪表盘
        display_signal_dashboard(signals)
        display_all_strategies(prices, signals, tier)

        if build_amount:
            for k in ["V3c", "B-RP", "B-Con"]:
                cash_ratio = 1 - int(tier) / 100
                w0 = compute_target_weights(k, prices, cash_ratio)
                w = apply_signal_overrides(k, w0, signals)
                display_build_plan(k, w, prices, build_amount)
        else:
            # 选一个看详情
            print(f"\n策略: {' / '.join(STRATEGIES.keys())}")
            pick = input("看哪个策略详情? (直接回车跳过): ").strip()
            if pick in STRATEGIES:
                cash_ratio = 1 - int(tier) / 100
                w0 = compute_target_weights(pick, prices, cash_ratio)
                w = apply_signal_overrides(pick, w0, signals)
                display_weight_table(pick, w, signals)

                amt = input("\n建仓金额？(输入数字生成买入清单，直接回车跳过): ").strip()
                if amt:
                    try:
                        display_build_plan(pick, w, prices, float(amt))
                    except ValueError:
                        pass
                else:
                    has_holdings = input("\n有当前持仓数据吗？生成调仓清单 (y/n): ").strip().lower()
                    if has_holdings == "y":
                        holdings = parse_holdings_input()
                        if holdings:
                            total = sum(holdings.values())
                            if total > 0 and all(v >= 0 for v in holdings.values()):
                                display_trade_list(pick, w, holdings, total)

    # 调仓提示
    print(f"\n{LINE}")
    print("  调仓规则:")
    print("  1. 每月最后一个交易日执行一次")
    print("  2. 先卖后买 — 卖出资金 T+0 可用后再买入")
    print(f"  3. nonferr/gold/SP500 跌破 SMA → 清仓转 credit")
    print("  4. 偏离 < 0.5% 不用动，省手续费")
    print("  5. 标普 500 QDII 经常限购，买不到用场外联接 050025 替代")
    print(f"{LINE}\n")


if __name__ == "__main__":
    main()
