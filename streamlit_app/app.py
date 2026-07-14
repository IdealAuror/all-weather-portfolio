"""再平衡调仓工具 — Streamlit Web 界面.

用法: streamlit run streamlit_app/app.py
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
import pandas as pd
from datetime import date
import numpy as np

from allweather.rebalance import (
    compute_signal_states,
    compute_target_weights,
    apply_signal_overrides,
    STRATEGIES,
    ETF_META,
)
from allweather.config import (
    DATA_DIR,
    GOLD_DIP_THRESHOLD,
    HS300_DIP_THRESHOLD,
    HS300_PB_ENTRY,
    HS300_PE_EXIT,
)

st.set_page_config(page_title="全天候再平衡", page_icon="🌤️", layout="wide")

st.markdown("""<style>
[role="tab"] { color: #a0a8c0 !important; }
[role="tab"][aria-selected="true"] { color: #ff4b4b !important; font-weight: 600; }
@media (prefers-color-scheme: light) {
  [role="tab"] { color: #555 !important; }
}
[data-testid="stDeployButton"] { display: none; }
[data-testid="stDecoration"] { display: none; }
#MainMenu { visibility: hidden; }
header[data-testid="stHeader"] { display: none; }
</style>""", unsafe_allow_html=True)

# ============================================================
# 信号 → 操作 映射表
# ============================================================
SIGNAL_ACTIONS = [
    {
        "key": "nonferr_below_sma75",
        "desc": "有色金属ETF (159980) 跌破 SMA75",
        "condition": lambda s: s.get("nonferr_below_sma75", False),
        "sell": "有色金属ETF (159980)",
        "buy": "城投债ETF (511220)",
        "strategies": ["B-Con", "B-RP", "V3c"],
        "type": "趋势过滤",
    },
    {
        "key": "gold_below_sma75",
        "desc": "黄金ETF (518880) 跌破 SMA75",
        "condition": lambda s: s.get("gold_below_sma75", False),
        "sell": "黄金ETF (518880)",
        "buy": "城投债ETF (511220)",
        "strategies": ["B-RP"],
        "type": "趋势过滤",
    },
    {
        "key": "sp500_below_sma120",
        "desc": "标普500ETF (513500) 跌破 SMA75",
        "condition": lambda s: s.get("sp500_below_sma120", False),
        "sell": "标普500ETF (513500)",
        "buy": "城投债ETF (511220)",
        "strategies": ["B-Con", "B-RP", "V3c"],
        "type": "趋势过滤",
    },
    {
        "key": "gold_dip_active",
        "desc": f"黄金 1Y 回撤 > {GOLD_DIP_THRESHOLD:.0%}，触发抄底",
        "condition": lambda s: s.get("gold_dip_active", False),
        "sell": "城投债ETF (511220)（筹资）",
        "buy": "黄金ETF (518880) ×2.5",
        "strategies": ["B-Con", "B-RP", "V3c"],
        "type": "抄底加仓",
    },
    {
        "key": "hs300_dip_ready",
        "desc": f"HS300 回撤>{HS300_DIP_THRESHOLD:.0%} + PB<{HS300_PB_ENTRY}%ile + 价格>SMA120",
        "condition": lambda s: s.get("hs300_dip_ready", False),
        "sell": "城投债ETF (511220)（筹资）",
        "buy": "沪深300ETF (510300) ×1.8",
        "strategies": ["B-Con", "B-RP", "V3c"],
        "type": "抄底加仓",
    },
    {
        "key": "hs300_dip_exit",
        "desc": f"PE > {HS300_PE_EXIT}%ile，抄底出场",
        "condition": lambda s: s.get("hs300_dip_exit", False),
        "sell": "沪深300ETF (510300) 恢复原权重",
        "buy": "城投债ETF (511220)",
        "strategies": ["B-Con", "B-RP", "V3c"],
        "type": "抄底出场",
    },
]

# ============================================================
# 数据新鲜度
# ============================================================
ASSETS_TO_CHECK = ["hs300", "us_sp500", "bond_credit", "bond_10y_etf", "bond_30y_etf", "gold", "nonferr"]


def _trading_days_ago(last_date, today):
    """估算交易日间隔（日历天 - 周末天数）。"""
    cal_days = (today - last_date).days
    weeks = cal_days // 7
    extra = min(cal_days % 7, 2)
    return max(1, cal_days - weeks * 2 - extra)

def _check_data_staleness():
    """返回 (最旧交易日数, 最旧资产名) 若无数据则返回 (None, None)。"""
    results = []
    now = pd.Timestamp.now().date()
    for name in ASSETS_TO_CHECK:
        fp = DATA_DIR / f"{name}.csv"
        if not fp.exists():
            return None, None
        try:
            df = pd.read_csv(fp, parse_dates=["date"])
            last_date = df["date"].max().date()
            results.append((name, _trading_days_ago(last_date, now)))
        except Exception:
            return None, None
    if not results:
        return None, None
    oldest = max(results, key=lambda x: x[1])
    return oldest[1], oldest[0]


# ============================================================
# Sidebar
# ============================================================
st.sidebar.title("🌤️ 全天候再平衡")

_strat_display = {"B-Con": "V3-B 保守增强", "B-RP": "V3-B 风险平价", "V3c": "V3c 多元"}
strat_key = st.sidebar.radio(
    "策略",
    ["B-Con", "B-RP", "V3c"],
    format_func=lambda k: _strat_display[k],
)
tier = st.sidebar.radio(
    "现金档位",
    ["100", "85", "70"],
    format_func=lambda t: f"{t}% RP",
)

# 自动拉取：数据超过 1 天就增量更新
staleness_days, staleness_asset = _check_data_staleness()
if "auto_fetch_done" not in st.session_state:
    st.session_state.auto_fetch_done = False

if staleness_days is not None and staleness_days > 1 and not st.session_state.auto_fetch_done:
    from allweather.fetch import fetch_all
    today_str = date.today().strftime("%Y%m%d")
    fetch_all(force=False, end=today_str)
    st.session_state.auto_fetch_done = True
    st.cache_data.clear()
    st.rerun()

if staleness_days is not None:
    if staleness_days > 7:
        st.sidebar.warning(f"数据 {staleness_days} 天未更新")
    else:
        st.sidebar.success(f"数据新鲜（滞后 {staleness_days} 个交易日）")
else:
    st.sidebar.error("数据缺失")

if st.sidebar.button("🔄 拉取最新数据"):
    with st.sidebar:
        with st.spinner("正在拉取..."):
            from allweather.fetch import fetch_all
            today_str = date.today().strftime("%Y%m%d")
            fetch_all(force=False, end=today_str)
    st.session_state.auto_fetch_done = True
    st.cache_data.clear()
    st.rerun()

# ============================================================
# 数据加载（直接读 CSV，不截断到 BACKTEST_END）
# ============================================================
_LIVE_ASSETS = {
    "hs300": "hs300",
    "us_sp500": "us_sp500",
    "credit": "bond_credit",
    "bond_10y": "bond_10y_etf",
    "bond_30y": "bond_30y_etf",
    "gold": "gold",
    "nonferr": "nonferr",
    "wti": "wti",
}


def _load_live_prices():
    dfs = {}
    for col, filename in _LIVE_ASSETS.items():
        fp = DATA_DIR / f"{filename}.csv"
        if fp.exists():
            df = pd.read_csv(fp, parse_dates=["date"], index_col="date")
            dfs[col] = df["close"]
    panel = pd.DataFrame(dfs).sort_index().ffill().dropna()
    return panel


@st.cache_data(ttl=300, show_spinner=False)
def _load_prices_and_signals():
    prices = _load_live_prices()
    signals = compute_signal_states(prices)
    return prices, signals


prices, signals = _load_prices_and_signals()

last_date = prices.index[-1].strftime("%Y-%m-%d")
st.sidebar.caption(f"数据截止: {last_date}")

missing = [a for a in STRATEGIES[strat_key]["assets"] if a not in prices.columns]
if missing:
    st.error(f"缺少数据: {missing}")
    st.stop()

cash_ratio = 1 - int(tier) / 100

# ============================================================
# 计算权重
# ============================================================
w0 = compute_target_weights(strat_key, prices, cash_ratio)
w = apply_signal_overrides(strat_key, w0, signals, prices)
cfg = STRATEGIES[strat_key]

# ============================================================
# Main Tabs
# ============================================================
tab1, tab2, tab3, tab4 = st.tabs(
    ["📊 信号仪表盘", "📋 目标权重", "🏗️ 建仓清单", "🔄 调仓清单"]
)

# ============================================================
# Tab 1: 信号仪表盘
# ============================================================
with tab1:
    triggered = []
    calm = []

    for sa in SIGNAL_ACTIONS:
        active = sa["condition"](signals)
        applies = strat_key in sa["strategies"]
        if active and applies:
            triggered.append(sa)
        else:
            calm.append(sa)

    if triggered:
        st.subheader("⚠️ 已触发信号")
        for sa in triggered:
            with st.container(border=True):
                cols = st.columns([2, 1, 1])
                with cols[0]:
                    st.markdown(f"### {sa['desc']}")
                    st.caption(sa["type"])
                with cols[1]:
                    st.markdown(f"**卖出**\n\n{sa['sell']}")
                with cols[2]:
                    st.markdown(f"**买入**\n\n{sa['buy']}")
    else:
        st.success("当前无触发信号，所有资产正常配置")

    with st.expander(f"未触发信号（{len(calm)} 项）"):
        for sa in calm:
            applies = strat_key in sa["strategies"]
            tag = "✅ 适用" if applies else "⚪ 不适用本策略"
            st.text(f"{tag}  {sa['desc']}")

    st.divider()
    st.subheader("估值分位")
    pb_col, pe_col = st.columns(2)
    with pb_col:
        pb_pct = signals.get("pb_pctile")
        if pb_pct is not None:
            st.metric("PB 分位", f"{pb_pct:.0f}%ile",
                      delta="便宜" if signals.get("pb_entry_ok") else "偏贵",
                      delta_color="inverse" if not signals.get("pb_entry_ok") else "normal")
            st.progress(min(pb_pct / 100, 1.0))
    with pe_col:
        pe_pct = signals.get("pe_pctile")
        if pe_pct is not None:
            st.metric("PE 分位", f"{pe_pct:.0f}%ile",
                      delta="偏贵" if signals.get("pe_exit_ok") is False else "正常",
                      delta_color="inverse" if signals.get("pe_exit_ok") is False else "normal")
            st.progress(min(pe_pct / 100, 1.0))

    st.divider()
    dd_col1, dd_col2 = st.columns(2)
    with dd_col1:
        gold_dd = signals.get("gold_dd_pct", 0)
        st.metric("黄金 1Y 回撤", f"{gold_dd*100:.1f}%",
                  delta=f"距抄底线 {(-GOLD_DIP_THRESHOLD*100):.0f}% 还差 {(gold_dd*100 + GOLD_DIP_THRESHOLD*100):.1f}%" if gold_dd > -GOLD_DIP_THRESHOLD else "已触发")
    with dd_col2:
        hs_dd = signals.get("hs300_dd_pct", 0)
        st.metric("沪深300 3Y 回撤", f"{hs_dd*100:.1f}%",
                  delta=f"距抄底线 {(-HS300_DIP_THRESHOLD*100):.0f}% 还差 {(hs_dd*100 + HS300_DIP_THRESHOLD*100):.1f}%" if hs_dd > -HS300_DIP_THRESHOLD else "深度回撤")

    # 四季象限
    st.divider()
    st.subheader("宏观季节")

    growth_up = signals.get("hs300_above_sma120", False)
    gold_sma75 = prices["gold"].rolling(75).mean().iloc[-1]
    inflation_up = prices["gold"].iloc[-1] > gold_sma75

    QUADRANTS = [
        {"label": "复苏", "sub": "增长↑ 通胀↓", "growth": True,  "inflation": False,
         "icon": "🌸", "color": "#2e7d32", "assets": "沪深300 · 标普500"},
        {"label": "过热", "sub": "增长↑ 通胀↑",  "growth": True,  "inflation": True,
         "icon": "🔥", "color": "#c62828", "assets": "黄金 · 有色金属"},
        {"label": "滞胀", "sub": "增长↓ 通胀↑", "growth": False, "inflation": True,
         "icon": "💨", "color": "#e65100", "assets": "黄金（避险）"},
        {"label": "衰退", "sub": "增长↓ 通胀↓",  "growth": False, "inflation": False,
         "icon": "❄️", "color": "#1565c0", "assets": "10Y国债 · 30Y国债"},
    ]

    current_label = ""
    for q in QUADRANTS:
        if q["growth"] == growth_up and q["inflation"] == inflation_up:
            current_label = q["label"]
            break

    st.caption(f"当前：**{current_label}**（增长{'↑' if growth_up else '↓'}  通胀{'↑' if inflation_up else '↓'}）")

    cells = []
    for q in QUADRANTS:
        active = q["growth"] == growth_up and q["inflation"] == inflation_up
        border = "3px solid #ffd54f" if active else "1px solid #555"
        bg = "rgba(255,215,0,0.08)" if active else "transparent"
        cells.append(
            f"<div style='border:{border};border-radius:10px;padding:12px 16px;background:{bg};height:100px'>"
            f"<span style='font-size:24px'>{q['icon']}</span> "
            f"<strong style='font-size:16px'>{q['label']}</strong> "
            f"<span style='color:#888;font-size:12px'>{q['sub']}</span><br>"
            f"<span style='font-size:13px;color:#aaa'>{q['assets']}</span>"
            f"</div>"
        )

    html = "<div style='display:grid;grid-template-columns:1fr 1fr;gap:12px'>" + "".join(cells) + "</div>"
    st.markdown(html, unsafe_allow_html=True)

# ============================================================
# Tab 2: 目标权重
# ============================================================
with tab2:
    st.subheader(f"{cfg['name']}  —  {tier}% RP")

    rows = []
    for a in cfg["assets"]:
        meta = ETF_META.get(a, {"code": "", "name": a})
        pct = w.get(a, 0)
        status_parts = []

        if a == "nonferr" and signals.get("nonferr_below_sma75") and pct == 0:
            status_parts.append("趋势过滤→已清仓")
        if a == "gold" and strat_key == "B-RP" and signals.get("gold_below_sma75") and pct == 0:
            status_parts.append("趋势过滤→已清仓")
        if a == "us_sp500" and signals.get("sp500_below_sma120") and pct == 0:
            status_parts.append("趋势过滤→已清仓")
        if a == "gold" and signals.get("gold_dip_active") and pct > 0:
            status_parts.append("抄底×2.5")
        if a == "hs300" and signals.get("hs300_dip_ready") and pct > 0:
            status_parts.append("AND抄底×1.8")
        if a == "credit":
            incoming = []
            if signals.get("nonferr_below_sma75"):
                incoming.append("有色")
            if signals.get("sp500_below_sma120"):
                incoming.append("标普")
            if strat_key == "B-RP" and signals.get("gold_below_sma75"):
                incoming.append("黄金")
            if incoming:
                status_parts.append(f"接收{'/'.join(incoming)}")

        rows.append({
            "资产": meta["name"],
            "代码": meta["code"],
            "权重": f"{pct*100:.1f}%",
            "状态": " / ".join(status_parts) if status_parts else "—",
        })

    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    if any(signals.get(k, False) for k in ["nonferr_below_sma75", "gold_below_sma75", "sp500_below_sma120"]):
        st.info("趋势过滤触发 → 对应资产已清仓，权重转入城投债ETF (511220)")

# ============================================================
# Tab 3: 建仓清单
# ============================================================
with tab3:
    st.subheader("从零建仓")

    amount = st.number_input(
        "投资总额（元）",
        min_value=1000,
        value=500000,
        step=10000,
        format="%d",
        key="build_amount_input",
    )

    if amount > 0:
        latest = prices.iloc[-1]
        lot_size = 100

        rows = []
        total_used = 0
        for a in cfg["assets"]:
            meta = ETF_META.get(a, {"code": "", "name": a})
            pct = w.get(a, 0)
            if pct <= 0:
                continue
            target_amount = pct * amount
            price = float(latest.get(a, np.nan))
            if np.isnan(price) or price <= 0:
                continue
            shares = int(target_amount / price / lot_size) * lot_size
            actual = shares * price
            total_used += actual
            rows.append({
                "资产": meta["name"],
                "代码": meta["code"],
                "权重": f"{pct*100:.1f}%",
                "目标金额": f"¥{target_amount:,.0f}",
                "现价": f"{price:.3f}",
                "买入股数": shares,
                "实际金额": f"¥{actual:,.0f}",
            })

        if rows:
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

            remainder = amount - total_used
            cols = st.columns(3)
            with cols[0]:
                st.metric("总投资", f"¥{amount:,.0f}")
            with cols[1]:
                st.metric("已分配", f"¥{total_used:,.0f}")
            with cols[2]:
                st.metric("剩余现金", f"¥{remainder:,.0f}",
                          delta="放入货基/华宝添益(511990)")

            if any(a == "us_sp500" for a in cfg["assets"]) and w.get("us_sp500", 0) > 0:
                st.info("标普500 QDII 经常限购，买不到用场外联接 050025 替代")
        else:
            st.warning("无有效资产可建仓")

# ============================================================
# Tab 4: 调仓清单
# ============================================================
with tab4:
    st.subheader("调仓对比")

    st.caption("输入当前持仓股数，自动计算买卖清单")

    latest = prices.iloc[-1]
    lot_size = 100

    holdings_shares = {}
    cols = st.columns(3)
    for i, a in enumerate(cfg["assets"]):
        meta = ETF_META.get(a, {"code": "", "name": a})
        with cols[i % 3]:
            holdings_shares[a] = st.number_input(
                f"{meta['name']} ({meta['code']})",
                min_value=0,
                value=0,
                step=100,
                format="%d",
                key=f"holdings_{strat_key}_{a}",
            )

    total_value = sum(
        holdings_shares.get(a, 0) * float(latest.get(a, 0)) for a in cfg["assets"]
    )
    if total_value > 0:
        st.divider()
        st.caption(f"持仓总市值: ¥{total_value:,.0f}")

        trade_rows = []
        any_trade = False
        for a in cfg["assets"]:
            meta = ETF_META.get(a, {"code": "", "name": a})
            price = float(latest.get(a, 0))
            shares = holdings_shares.get(a, 0)
            current_amt = shares * price
            target_amt = w.get(a, 0) * total_value
            diff_amt = target_amt - current_amt
            pct_diff = abs(diff_amt) / total_value if total_value > 0 else 0
            diff_shares = int(diff_amt / price / lot_size) * lot_size if price > 0 else 0

            if pct_diff < 0.005 or diff_shares == 0:
                action = "不变"
            elif diff_amt > 0:
                action = f"买入 {diff_shares} 股"
                any_trade = True
            else:
                action = f"卖出 {-diff_shares} 股"
                any_trade = True

            trade_rows.append({
                "资产": meta["name"],
                "代码": meta["code"],
                "持仓股数": shares,
                "市值 (¥)": f"{current_amt:,.0f}",
                "目标 (¥)": f"{target_amt:,.0f}",
                "差额 (¥)": f"{diff_amt:+,.0f}" if abs(diff_amt) >= 1 else "—",
                "操作": action,
            })

        st.dataframe(pd.DataFrame(trade_rows), width="stretch", hide_index=True)

        if not any_trade:
            st.success("所有资产偏离 < 0.5%，无需调仓")

        with st.expander("调仓规则说明"):
            st.markdown("""
            1. 每月最后一个交易日执行一次
            2. 先卖后买 — 卖出资金 T+0 可用后再买入
            3. nonferr / gold / SP500 跌破 SMA → 清仓转城投债
            4. 偏离 < 0.5% 不用动，省手续费
            5. 股数按 100 股取整，实际成交金额以市价为准
            6. 标普500 QDII 限购时用场外联接 050025 替代
            """)
    else:
        st.caption("输入持仓股数后自动生成调仓清单")

# ============================================================
# 底部：三策略对比
# ============================================================
st.divider()
with st.expander("📈 三策略权重对比"):
    all_weights = {}
    for k in ["B-Con", "B-RP", "V3c"]:
        w0_cmp = compute_target_weights(k, prices, cash_ratio)
        w_cmp = apply_signal_overrides(k, w0_cmp, signals, prices)
        all_weights[k] = w_cmp

    cmp_rows = []
    for a in ["hs300", "us_sp500", "credit", "bond_10y", "bond_30y", "gold", "nonferr", "wti"]:
        meta = ETF_META.get(a, {"code": "", "name": a})
        row = {"资产": meta["name"], "代码": meta["code"]}
        for k in ["B-Con", "B-RP", "V3c"]:
            row[_strat_display[k]] = f"{all_weights[k].get(a, 0)*100:.1f}%"
        cmp_rows.append(row)

    st.dataframe(pd.DataFrame(cmp_rows), width="stretch", hide_index=True)
