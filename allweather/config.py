"""配置常量 - ETF 代码、桶定义、回测期间、调仓规则参数。"""
from pathlib import Path

# === 路径 ===
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RESULTS_DIR = ROOT / "results"
OUTPUT_DIR = ROOT / "output"

# === 回测期间 ===
BACKTEST_START = "2015-01-01"
BACKTEST_END   = "2025-12-31"

# === 30 年国债合成参数 ===
# 2024-03 之前没有 30Y ETF 数据，用 10Y 国债指数 × 久期放大系数合成
BOND_30Y_AMP = 3.0

# === 合成数据安全扣减（年化）===
# 仅对合成段（ETF 上市前的替代数据）应用，ETF 真实数据段不扣减
SAFETY_DEDUCT = {
    "nonferr":  0.005,   # 申万有色指数不含管理费、跟踪误差
    "soymeal":  0.020,   # 豆粕期货展期损耗+管理费+contango+无现货锚
    "bond_30y": 0.003,   # ×3.0 久期放大的期权费率差
}

# === 调仓规则 ===
REBAL_FREQ = "2QE"           # 半年节点
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
    "hs300", "div_idx", "us_sp500", "credit",
    "bond_10y", "bond_30y",
    "gold", "nonferr", "soymeal",
]

ASSETS_PLAN_A = [
    "hs300", "div_idx", "us_sp500", "credit",
    "bond_10y", "bond_30y", "short_bond",
    "gold", "nonferr", "soymeal",
]

ETF_META = {
    "hs300":     {"code": "510300", "name": "沪深 300 ETF",        "bucket": "增长↑", "role": "A股大盘"},
    "div_idx":   {"code": "510880", "name": "红利 ETF（中证红利）",   "bucket": "增长↑", "role": "A股价值/股息"},
    "us_sp500":  {"code": "513500", "name": "标普 500 ETF（QDII）", "bucket": "增长↑", "role": "海外权益"},
    "credit":    {"code": "511220", "name": "城投债 ETF",          "bucket": "收益垫", "role": "信用债"},
    "bond_10y":  {"code": "511260", "name": "10 年国债 ETF",       "bucket": "增长↓", "role": "中久期利率债"},
    "bond_30y":  {"code": "511130", "name": "30 年国债 ETF",       "bucket": "增长↓", "role": "长久期利率债"},
    "gold":      {"code": "518880", "name": "黄金 ETF",            "bucket": "通胀↑", "role": "实物黄金"},
    "nonferr":   {"code": "159980", "name": "有色金属 ETF",        "bucket": "通胀↑", "role": "工业金属"},
    "short_bond": {"code": "511880", "name": "短久期债券 ETF",      "bucket": "增长↓", "role": "短久期利率债"},
    "soymeal":   {"code": "159985", "name": "豆粕 ETF",           "bucket": "通胀↑", "role": "农产品"},
}

CASH_ETF = {"code": "511880", "name": "货币基金 ETF"}

# === 桶定义（用于风险贡献分析）===
BUCKETS = {
    "增长↑权益(A股)":  ["hs300", "div_idx"],
    "增长↑权益(海外)": ["us_sp500"],
    "信用债":          ["credit"],
    "增长↓利率债":    ["bond_10y", "bond_30y", "short_bond"],
    "通胀↑黄金":      ["gold"],
    "通胀↑商品":      ["nonferr", "soymeal"],
}

BUCKET_GROUPS = {
    "增长↑": ["hs300", "div_idx", "us_sp500"],
    "收益垫": ["credit"],
    "增长↓": ["bond_10y", "bond_30y", "short_bond"],
    "通胀↑": ["gold", "nonferr", "soymeal"],
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
TURNOVER_PER_REBAL = 0.08
COST_PER_SIDE = 0.0015

# === 方案 B 常量（分层风险平价）===
RISK_PARITY_WINDOW = 60          # 逆波动率窗口（交易日），默认版本
RISK_PARITY_WINDOW_LONG = 120    # 长窗口版本，更接近桥水战略定位
RISK_PARITY_MAX_WEIGHT = 0.25    # 单资产权重上限
RISK_PARITY_MIN_WEIGHT = 0.02    # 单资产权重下限
