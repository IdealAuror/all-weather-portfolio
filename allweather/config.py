"""配置常量 - ETF 代码、桶定义、回测期间、调仓规则参数。"""
from pathlib import Path

# === 路径 ===
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"

# === 回测期间 ===
BACKTEST_START = "2005-04-08"
BACKTEST_END   = "2026-05-30"

# === 30 年国债合成参数 ===
# 2024-03 之前没有 30Y ETF 数据，用 10Y 国债指数 × 久期放大系数合成
BOND_30Y_AMP = 3.0
BOND_30Y_SPREAD_CUTOFF = "2020-02-01"  # 利差法起始日
BOND_30Y_DURATION = 18.0               # 利差法久期参数

# === 合成数据安全扣减（年化）===
# 仅对合成段（ETF 上市前的替代数据）应用，ETF 真实数据段不扣减
SAFETY_DEDUCT = {
    "nonferr":  0.005,   # 申万有色指数不含管理费、跟踪误差
    "bond_30y": 0.003,   # ×3.0 久期放大的期权费率差
}

# === 调仓规则 ===
REBAL_FREQ = "ME"            # 月度再平衡（V3c）
RISK_FREE_RATE = 0.022 / 252 # 货币基金年化 2.2%（日度）
RISK_FREE_ANNUAL = 0.022         # 无风险利率年化，用于 Sharpe 修正

# === 现金降杠杆档位 ===
CASH_TIERS = [
    ("100% RP", 0.00),
    ("85% RP",  0.15),
    ("70% RP",  0.30),
]

# === 8 资产元信息 ===
# 顺序就是各个表的标准列序
ASSETS = [
    "hs300", "us_sp500", "credit",
    "bond_10y", "bond_30y",
    "gold", "nonferr", "wti",
]

ETF_META = {
    "hs300":     {"code": "510300", "name": "沪深 300 ETF",        "bucket": "增长↑", "role": "A股大盘"},
    "us_sp500":  {"code": "513500", "name": "标普 500 ETF（QDII）", "bucket": "增长↑", "role": "海外权益"},
    "credit":    {"code": "511220", "name": "城投债 ETF",          "bucket": "收益垫", "role": "信用债"},
    "bond_10y":  {"code": "511260", "name": "10 年国债 ETF",       "bucket": "增长↓10Y", "role": "中久期利率债"},
    "bond_30y":  {"code": "511130", "name": "30 年国债 ETF",       "bucket": "增长↓30Y", "role": "长久期利率债"},
    "gold":      {"code": "518880", "name": "黄金 ETF",            "bucket": "通胀↑", "role": "实物黄金"},
    "nonferr":   {"code": "159980", "name": "有色金属 ETF",        "bucket": "通胀↑", "role": "工业金属"},
    "wti":       {"code": "501018", "name": "南方原油 LOF",         "bucket": "通胀↑", "role": "原油LOF"},
}

# === 桶定义（用于风险贡献分析）===
BUCKETS = {
    "增长↑权益(A股)":  ["hs300"],
    "增长↑权益(海外)": ["us_sp500"],
    "信用债":          ["credit"],
    "增长↓10Y":       ["bond_10y"],
    "增长↓30Y":       ["bond_30y"],
    "通胀↑黄金":      ["gold"],
    "通胀↑有色":      ["nonferr"],
    "通胀↑能源":      ["wti"],
}

BUCKET_GROUPS = {
    "增长↑":   ["hs300", "us_sp500"],
    "收益垫":  ["credit"],
    "增长↓10Y": ["bond_10y"],
    "增长↓30Y": ["bond_30y"],
    "通胀↑":   ["gold", "nonferr", "wti"],
}

# === 关键事件压力测试 ===
STRESS_EVENTS = [
    ("2008 GFC",          "2008-09-15", "2009-03-09"),
    ("2015 股灾",         "2015-06-12", "2015-08-26"),
    ("2016 熔断",         "2016-01-04", "2016-01-07"),
    ("2017 债熊",         "2017-01-03", "2017-12-29"),
    ("2018 大熊市",       "2018-01-24", "2018-10-19"),
    ("2019 春季反弹",     "2019-01-04", "2019-04-19"),
    ("2020 疫情",         "2020-02-19", "2020-03-23"),
    ("2020-Q4 内需复苏",  "2020-09-01", "2020-12-31"),
    ("2021-2 白马回撤",   "2021-02-10", "2021-03-31"),
    ("2022 股债双杀",     "2022-01-04", "2022-11-30"),
    ("2022 理财赎回",     "2022-10-30", "2022-12-31"),
    ("2024 雪球危机",     "2024-01-02", "2024-02-29"),
    ("2024-08 长债",      "2024-08-01", "2024-09-30"),
    ("2024-924 反弹",     "2024-09-23", "2024-10-08"),
    ("2025-Q1 长债",      "2025-01-02", "2025-03-31"),
    ("2025-9 关税",       "2025-09-01", "2025-10-31"),
]

CHART_EVENT_NAMES = [
    "2008 GFC", "2015 股灾", "2018 大熊市", "2020 疫情",
    "2022 股债双杀", "2024-924 反弹",
]

# === Block Bootstrap 参数 ===
BOOTSTRAP_N_SIM = 1000
BOOTSTRAP_HORIZON_DAYS = 252 * 5
BOOTSTRAP_BLOCK_DAYS = 21
BOOTSTRAP_SEED = 42

# === 交易成本估计 ===

# === V3c 精简资产 ===
V3C_ASSETS = ["hs300", "us_sp500", "credit", "bond_30y", "gold", "nonferr", "wti"]
V3C_ASSETS_NO_WTI = ["hs300", "us_sp500", "credit", "bond_30y", "gold", "nonferr"]
# wti — 南方原油 LOF(501018)，目前申购暂停

# === 无原油桶定义（主展示用）===
V3B_RP_BUCKETS_NO_WTI = {
    "增长↑":   ["hs300", "us_sp500"],
    "收益垫":  ["credit"],
    "增长↓":   ["bond_30y"],
    "通胀↑":   ["gold", "nonferr"],
}
V3B_CON_ASSETS_NO_WTI = ["hs300", "us_sp500", "credit", "bond_10y", "bond_30y", "gold", "nonferr"]

# === 方案 B 常量（分层风险平价）===
RISK_PARITY_WINDOW = 20           # V3-B 波动率窗口（交易日）
RISK_PARITY_MAX_WEIGHT = 0.20    # 单资产权重上限（0.20 实现真正等桶风险平价，原 0.18 截断单资产桶）
RISK_PARITY_MIN_WEIGHT = 0.02    # 单资产权重下限
RISK_PARITY_TARGET_VOL = 0.09    # V3-B RP 目标波动率上限（超标等比降敞口）
RISK_PARITY_COV_WINDOW = 60      # V3-B RP 协方差估计窗口（target_vol 用）

# === Gold 抄底参数 ===
GOLD_DIP_THRESHOLD = 0.15        # 黄金从高点回撤超过此阈值触发抄底
GOLD_DIP_BOOST = 2.5             # 触发后黄金权重翻倍倍数（2.5x，网格搜索最优）
# === HS300 抄底参数 ===
HS300_DIP_THRESHOLD = 0.25       # 价格回撤阈值（25%，中度熊市即触发）
HS300_DIP_BOOST = 1.8            # 价格回撤 boost（1.8x，grid-search 最优）
HS300_DIP_SMA = 120              # 价格回撤需价格 > SMA120 确认（交易日）
HS300_DIP_EXIT_RECOVERY = 0.15   # 恢复到 peak-15% 退出（grid-search 最优）

# HS300 抄底 — AND 逻辑：PB确认入场 + PE确认出场
HS300_PB_ENTRY = 30              # PB%ile 入场阈值（PB便宜才抄底）
HS300_PE_EXIT = 70               # PE%ile 退出阈值（PE不再便宜才退出）

# === 标普500 趋势过滤 ===
SP500_TREND_WINDOW = 75      # 标普500 SMA 回看窗口（交易日），跌破则清仓转入 credit
# 120d→75d: 2020 COVID MDD -9.66%→-6.91%（+2.75pp），牺牲 CAGR -0.16pp
# 75d 提前 1 个月触发（3 月 vs 4 月），正好在 COVID 抛售最急期提供保护
# 见 project_sp500-trend-rp-75d.md

# === 沪深300 趋势过滤 ===
HS300_TREND_WINDOW = 30      # 沪深300 SMA 回看窗口（交易日），跌破则清仓转入 credit
# 选择 30d 基于 HS300 走势分析：2015 股灾 -10% 触发（15d 延迟）、月频调仓下假信号可接受。
# 详细分析见 _analyze_hs300_sma.py

# === Nonferr 趋势过滤 — N日确认参数 ===
NF_TREND_CONFIRM_DAYS = 0     # 0=原始二值行为，>0 要求连续 N 日低于 SMA75 才触发清仓
# 已测试 N=3/5/10，全部否决——nonferr SMA75 低频过滤器（~18次/21年），
# 加确认条件只推迟保护，少量假信号节省不补偿延迟损失。
# 见 project_nonferr-trend-confirm.md
# 从国泰海通 TAA 启发：用连续 N 日确认来减少 whipsaw。
# nonferr 21年仅触发 ~18 次，hypothesis：部分触发后短期反弹(假信号)被 N日确认过滤。
# 候选值：3/5/7/10。先验选择 N=5（~1周）平衡延迟 vs 确认
# 选择 30d 基于 HS300 走势分析：2015 股灾 -10% 触发（15d 延迟）、月频调仓下假信号可接受。
# 详细分析见 _analyze_hs300_sma.py


# === 杠杆 / 保证金参数 ===
# 名义杠杆：1 单位资本可获得的资产名义敞口倍数
LEVERAGE_FACTORS = {
    "bond_10y": 3.0,     # T.CFFEX 10Y 国债期货名义敞口杠杆（从 5x 降到 3x，MDD -13.87%→-9.91%）
    "bond_30y": 1.0,     # 30Y 已在数据层有 3x 久期放大，引擎层不加杠杆
}
# 融资利差：杠杆部分的年化融资成本（T.CFFEX 隐含回购利率 - rf）
LEVERAGE_FINANCING_SPREAD = 0.002  # 年化 20bp

# V4 已移除 — 保留 V4_ASSETS 定义以防外部引用
V4_ASSETS = ["hs300", "us_sp500", "credit", "bond_10y", "bond_30y", "gold", "nonferr", "wti"]

# === 策略标签 ===
PORTFOLIO_TAGS = {
    "V3-B 保守增强(20d)":  {"stars": "★★★", "label": "保守增强 — 逆波动率 20d + nonferr(75d) + HS300 AND抄底，max_w=0.25"},
    "V3-B 风险平价(20d)":  {"stars": "★★★", "label": "学院派 — 4桶等权 HRP + nonferr(75d) + Gold(75d) + SP500(75d) + HS300(30d) + HS300 AND抄底"},
    "V3c 多元":            {"stars": "★★★", "label": "V3c 多元 — 6资产逆波动率60d + nonferr(75d) + gold(75d) + SP500(75d) + HS300 AND抄底"},
}

