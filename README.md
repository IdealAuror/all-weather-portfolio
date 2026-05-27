# 桥水全天候策略 · 中国版


[![Pages](https://img.shields.io/badge/docs-online-blue)](https://idealauror.github.io/all-weather-portfolio/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)

基于真实 A 股 / 债 / 商品 ETF 数据的全天候风险平价（Risk Parity）回测工程。回测期 2008-2025，覆盖 ~18 年完整牛熊周期。

📖 **在线阅读完整方案**：https://idealauror.github.io/all-weather-portfolio/

---

## 策略速查

| 方案 | 风格 | CAGR | 最大回撤 | Sharpe | 一句话 |
|---|---|---|---|---|---|
| **V3c 多元** | 简约派 | 8.59% | -5.84% | 1.40 | 6资产逆波动率 60d — 简单干净 |
| **V3-B 风险平价(20d)** | 学院派 | **10.68%** | -10.34% | 1.33 | 4桶等权 RP — 回报最高 |
| **V3-B 保守增强(20d)** | 保守增强 | 7.52% | **-3.83%** | **1.64** | 逆波动率 — 睡得着觉 |

> 全部策略均含 nonferr 趋势过滤 + Gold 抄底(15%/2.5x) + HS300 抄底(35%)，月度调仓。
> V3c：6 资产；B-RP：6 资产 4 桶（无 bond_10y）；B-Con：7 资产 5 桶。
> HS300 抄底 boost：V3c 3.0x / B-RP 1.5x / B-Con 3.0x。
> 去除了 div_idx（与 hs300 相关性 0.90）和 soymeal（自身 Sharpe 为负）。

### 策略评估

**V3c 多元 (简约派)**
- 资产最少(6个)，执行最简单；中等回撤，回报稳健
- 无桶级风控，单资产上限 30% 较宽松
- 适合：初入全天候、不想研究桶逻辑、追求简单透明

**V3-B 风险平价(20d) (学院派)**
- 长期回报最高 CAGR 10.68%，累计 537%；四桶真正等权(25%×4)，无 bond_10y
- 回撤最大(-10.34%)，最差年份 -3.52%；桶逻辑比另外两个策略复杂
- 适合：长期持有者(5年+)、认同正统全天候理念、能承受短期波动

**V3-B 保守增强(20d) (保守增强)**
- 回撤最低(-3.83%)，最差年份仅 -0.42%；Sharpe 最高(1.64)，熊市表现最好
- 牛市可能跑输(2019仅+0.44%，2017仅+2.89%)；长期累计回报最低(275%)
- 适合：保守型资金、退休/教育金、无法承受大幅回撤

**一句话选策略：要简单 → V3c / 要高回报 → V3-B RP / 要不亏钱 → V3-B 保守增强**

---

## 一键运行

```bash
# 用 uv（推荐，自动管理依赖）
uv run --with numpy --with pandas --with openpyxl python -X utf8 main.py

# 或者用本地 Python（需先 pip install）
pip install numpy pandas openpyxl
python main.py
```

跑完在控制台输出 9 张报表，同时写 `output/`：

| 文件 | 说明 |
|---|---|
| `report.xlsx` | Excel 多 sheet 综合报告（11 sheet，带格式/高亮/负数标红）|
| `report.md` | Markdown 综合报告（GitHub / IDE 直接渲染）|
| `nv_curves.csv` | 9 条净值曲线（3 策略 × 3 档现金）|
| `summary.json` | 核心指标（CI sanity check 读这个）|
| `weights.csv` | 三策略权重快照 |

## 命令行选项

```bash
python main.py                跑回测（默认输出全部报告）
python main.py --fetch        先补拉缺失数据再回测
python main.py --fetch-only   只拉数据不回测
python main.py --force-fetch  强制重拉所有数据（覆盖）
python main.py --no-excel     跳过 Excel 综合报告
python main.py --no-markdown  跳过 Markdown 综合报告
python main.py --help         查看完整帮助
```

> 数据已预先拉好放在 `data/`，正常直接 `python main.py`。

## 目录结构

```
全季节策略/
├── main.py                    主入口
├── pyproject.toml              依赖声明
├── README.md                   本文件
├── CLAUDE.md                   AI 协作指引 + 策略说明
│
├── allweather/                 核心包
│   ├── config.py               常量：ETF代码 / 桶定义 / 调仓参数
│   ├── data.py                 数据加载 + 30Y国债合成
│   ├── fetch.py                数据拉取（akshare）
│   ├── portfolios.py           策略标签与权重定义
│   ├── backtest.py             回测引擎（V3c 逆波动率 + 双触发再平衡）
│   ├── strategy_b.py           V3-B 分层风险平价/逆波动率回测
│   ├── risk.py                 风险原语：逆波动率权重 / 分层RP / 风险控制库函数
│   ├── stats.py                收益统计 + block bootstrap 蒙特卡洛
│   ├── reports.py              控制台输出（9 张表 + 策略评估）
│   ├── excel_export.py         Excel 11-sheet 格式化报告
│   ├── markdown_report.py      GitHub Markdown 综合报告
│   └── pipeline.py             6 步流水线编排
│
├── data/                       历史 CSV（已拉取）
├── results/                    早期回测中间结果
└── output/                     本次跑的输出（自动生成）
```

## 回测设计

### 资产与桶

| | V3c 多元 | V3-B 风险平价 | V3-B 保守增强 |
|---|---|---|---|
| 资产数 | 6 | 6 | 7 |
| 桶结构 | 无 | 4 桶 × 25% | 5 桶 × 20%（仅分组标签） |
| 资产列表 | hs300, us_sp500, credit, bond_30y, gold, nonferr | 同左 | + bond_10y |

**B-RP 4 桶：** 增长↑(hs300/us_sp500) / 收益垫(credit) / 增长↓(bond_30y) / 通胀↑(gold/nonferr) — 各 25%。
**B-Con 5 桶：** 同上 + 增长↓10Y(bond_10y) — 桶仅用于资产分组，权重由逆波动率直接计算。

### 三条策略的核心差异

| | V3c 多元 | V3-B 风险平价 | V3-B 保守增强 |
|---|---|---|---|
| 权重方法 | 逆波动率 60d | 4桶等权 + 桶内IV | 逆波动率 20d |
| 桶结构 | 无 | 4 桶 × 25% | 无 |
| 资产数 | 6 (无 bond_10y) | 6 (无 bond_10y) | 7 |
| max_w | 0.30 | 0.20 | 0.25 |
| 现金档位 | 100%/85%/70% | 100%/85%/70% | 100%/85%/70% |

### 关键参数

| 参数 | 值 | 说明 |
|---|---|---|
| 回测区间 | 2008-01 ~ 2025-12 | ~18 年 |
| 调仓频率 | 月度 | 每月初重算权重 |
| nonferr 趋势过滤 | V3c 60d / B-RP+B-Con 75d SMA | 跌破 SMA 则权重转入 credit |
| Gold 抄底 | -15% / 2.5x | 从高点回撤 15% 触发，权重翻 2.5 倍 |
| HS300 抄底 | -35% / V3c 3.0x / B-RP 1.5x / B-Con 3.0x | 仅史诗级股灾触发 |
| 无风险利率 | 2.2% 年化 | 用于 Sharpe 修正 |

## 自定义

修改权重或参数直接改 `allweather/config.py` 后重跑。

跑单步而非全流程：

```python
from allweather.pipeline import (
    step_1_load_data, step_2_run_backtests,
    step_3_compute_metrics, step_4_bootstrap,
    step_5_print_reports, step_6_save_outputs,
)

panel, rets = step_1_load_data()
weights, nv = step_2_run_backtests(rets)
# ...
```

## 分支规范

- `main` — 生产分支，打 Tag 发版，**禁止直接 push**
- `develop` — 集成测试，feature/hotfix 合入后验证
- `feature/xxx` — 新功能开发，从 develop 拉，**回测通过后**提 PR 回合
- `hotfix/xxx` — 紧急修复，从 main 拉，修复合入 main+develop

提交遵循 Conventional Commits（`feat:` / `fix:` / `docs:` / `refactor:`）。详见 [CLAUDE.md](CLAUDE.md)。

## 文档

详细策略论证、回测过程、风险提示、落地手册见：
- `桥水全季节.docx`
- 在线文档：https://idealauror.github.io/all-weather-portfolio/
