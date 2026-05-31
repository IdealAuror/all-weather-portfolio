"""配置常量 - ETF 代码、桶定义、回测期间、调仓规则参数。"""
from pathlib import Path

# === 路径 ===
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"

# === 回测期间 ===
BACKTEST_START = "2005-04-08"
BACKTEST_END   = "2026-04-30"

# === 30 年国债合成参数 ===
# 2024-03 之前没有 30Y ETF 数据，用 10Y 国债指数 × 久期放大系数合成
BOND_30Y_AMP = 3.0

# === 合成数据安全扣减（年化）===
# 仅对合成段（ETF 上市前的替代数据）应用，ETF 真实数据段不扣减
SAFETY_DEDUCT = {
    "nonferr":  0.005,   # 申万有色指数不含管理费、跟踪误差
    "bond_30y": 0.003,   # ×3.0 久期放大的期权费率差
    "wti":      0.010,   # 原油 QDII 基金管理费 1.0%/年 + 跟踪误差
}

# === 调仓规则 ===
REBAL_FREQ = "ME"            # 月度再平衡（V3c）
REBAL_THRESHOLD = 0.03       # 3% 偏离阈值
RISK_FREE_RATE = 0.022 / 252 # 货币基金年化 2.2%（日度）
RISK_FREE_ANNUAL = 0.022         # 无风险利率年化，用于 Sharpe 修正

# === 现金降杠杆档位 ===
CASH_TIERS = [
    ("100% RP", 0.00),
    ("85% RP",  0.15),
    ("70% RP",  0.30),
]

# === 9 资产 ETF 元信息 ===
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
    "wti":       {"code": "501018", "name": "南方原油 LOF",        "bucket": "通胀↑", "role": "能源商品"},
}

# === 桶定义（用于风险贡献分析）===
BUCKETS = {
    "增长↑权益(A股)":  ["hs300"],
    "增长↑权益(海外)": ["us_sp500"],
    "信用债":          ["credit"],
    "增长↓10Y":       ["bond_10y"],
    "增长↓30Y":       ["bond_30y"],
    "通胀↑黄金":      ["gold"],
    "通胀↑商品":      ["nonferr", "wti"],
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
    ("2015 股灾",         "2015-06-12", "2015-08-26"),
    ("2016 熔断",         "2016-01-04", "2016-01-07"),
    ("2017 债熊",         "2017-01-03", "2017-12-29"),
    ("2018 大熊市",       "2018-01-24", "2018-10-19"),
    ("2019 春季反弹",     "2019-01-04", "2019-04-19"),
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

# === Block Bootstrap 参数 ===
BOOTSTRAP_N_SIM = 1000
BOOTSTRAP_HORIZON_DAYS = 252 * 5
BOOTSTRAP_BLOCK_DAYS = 21
BOOTSTRAP_SEED = 42

# === 交易成本估计 ===

# === V3c 精简资产 ===
V3C_ASSETS = ["hs300", "us_sp500", "credit", "bond_30y", "gold", "nonferr"]
# wti — 已集成但 QDII 限购+溢价异常，暂不可执行

# === 方案 B 常量（分层风险平价）===
RISK_PARITY_WINDOW = 20           # V3-B 波动率窗口（交易日）
RISK_PARITY_MAX_WEIGHT = 0.20    # 单资产权重上限（0.20 实现真正等桶风险平价，原 0.18 截断单资产桶）
RISK_PARITY_MIN_WEIGHT = 0.02    # 单资产权重下限

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
SP500_TREND_WINDOW = 120     # 标普500 SMA 回看窗口（交易日），跌破则清仓转入 credit
WTI_TREND_WINDOW = 75        # 原油 SMA 回看窗口，同 nonferr（趋势性强，75d 敏感度最优）


# === 策略标签 ===
PORTFOLIO_TAGS = {
    "V3c 多元":            {"stars": "★★★", "label": "简约派 — 6资产逆波动率 60d + nonferr(75d) + HS300 AND抄底"},
    "V3-B 风险平价(20d)":  {"stars": "★★★", "label": "学院派 — 4桶等权 HRP + nonferr(75d) + Gold(75d) + SP500(120d) + HS300 AND抄底"},
    "V3-B 风险平价桶(20d)": {"stars": "★★★", "label": "预算派 — 4桶逆波动率 HRP + nonferr(75d) + Gold(75d) + SP500(120d) + HS300 AND抄底"},
    "V3-B 保守增强(20d)":  {"stars": "★★★", "label": "保守增强 — 逆波动率 20d + nonferr(75d) + HS300 AND抄底，max_w=0.25"},
}
