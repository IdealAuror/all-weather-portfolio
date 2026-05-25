# 项目过程纪要

> 这份文档面向 AI 阅读：未来任何对话只要读完它，就能完整还原项目的目标、方法论、决策依据和当前状态。
> 用 `H2/H3` 描述结构，关键事实写成 key-value 或表格，避免叙述性长句。

---

## 1. 项目身份

| 字段 | 值 |
|---|---|
| 名称 | 桥水全天候策略 · 中国版 |
| 仓库 | https://github.com/IdealAuror/all-weather-portfolio |
| 在线文档 | https://idealauror.github.io/all-weather-portfolio/ |
| 工作目录 | `C:\Users\MOSS\Desktop\全季节策略\` |
| 入口 | `python main.py` |
| 语言 | Python ≥ 3.10 |
| 必需依赖 | `numpy`, `pandas`, `openpyxl` |
| 可选依赖 | `akshare`（拉数据）, `python-docx`（生成方案文档）|
| 回测期间 | 2015-01-01 ~ 2025-12-31（~11 年）|
| License | MIT |

---

## 2. 项目目标

把桥水 All Weather 风险平价框架本地化到 A 股市场，用真实 ETF 数据回测 5.5 年，得到一组**普通投资者可以照抄落地**的权重方案。

成功标准：
- 年化 ≥ 8%，最大回撤 ≤ 4%，Sharpe ≥ 2.4
- 调仓频率不能太高（控制成本和心智负担）
- 在所有可观测的宏观情景里都不能出现单一情景被毁灭性砸盘

---

## 3. 资产与桶定义

桥水 4 象限框架（增长↑/↓ × 通胀↑/↓）落到 A 股可买的 9 只 ETF：

| 桶 | 资产 (key) | 名称 | 代码 |
|---|---|---|---|
| 增长↑ 权益 A 股 | `hs300` | 沪深 300 ETF | 510300 |
| 增长↑ 权益 A 股 | `div_idx` | 红利 ETF（中证红利）| 510880 |
| 增长↑ 权益 海外 | `us_sp500` | 标普 500 ETF（QDII）| 513500 |
| 收益垫 | `credit` | 城投债 ETF | 511220 |
| 增长↓ 利率债 | `bond_10y` | 10 年国债 ETF | 511260 |
| 增长↓ 利率债 | `bond_30y` | 30 年国债 ETF | 511130 |
| 通胀↑ 黄金 | `gold` | 黄金 ETF | 518880 |
| 通胀↑ 工业商品 | `nonferr` | 有色金属 ETF | 159980 |
| 通胀↑ 农产品 | `soymeal` | 豆粕 ETF | 159985 |
| 现金等价 | — | 货币基金 ETF | 511880 |

`bond_30y` 在 2024-03 才上市。**做法（三阶段合成）**：
1. 2015-01 ~ 2020-02：×3.0 久期放大（扣减 0.3%/年安全边际）
2. 2020-02 ~ 2024-03：利差法（10Y-30Y spread × duration 18.0）
3. 2024-03 ~ now：ETF 511130 真实 NAV
代码：`allweather/data.py::synthesize_bond_30y`。

`bond_10y` 用 ETF 511260（2017-08 起）+ 信用债 ETF 511220 作为 pre-ETF 替代（原 sh000139 国债指数在 2015-2019 数据受股灾污染）。代码：`allweather/data.py::_load_bond_10y`。

早期 nonferr/soymeal ETF 上市前（2019 前）分别用中证有色指数(sh000823)和豆粕期货主力(M0)缝合，施加年化安全扣减。代码：`allweather/data.py::stitch_series`。

---

## 4. 三个最终组合

权重定义：`allweather/portfolios.py::WEIGHTS`。

### 4.1 V3c 多元（★★★ 强烈推荐，默认）

| 资产 | 权重 |
|---|---|
| hs300 | 4% |
| div_idx | 6% |
| **us_sp500** | **8%** |
| credit | 5% |
| bond_10y | 40% |
| bond_30y | 15% |
| gold | 10% |
| nonferr | 6% |
| soymeal | 6% |

特征：海外权益 8%（三套里最高），通过国别分散对冲单一市场风险。

### 4.2 V3b 平衡（★★ 备选 - 求最浅回撤者）

| 资产 | 权重 |
|---|---|
| hs300 | 5% |
| div_idx | 7% |
| us_sp500 | 5% |
| credit | 5% |
| **bond_10y** | **43%** |
| bond_30y | 15% |
| gold | 10% |
| nonferr | 5% |
| soymeal | 5% |

特征：长债 58%（10Y+30Y），波动最低 4.03%。

### 4.3 V3d 商品偏重（★★ 备选 - 怕滞胀者）

| 资产 | 权重 |
|---|---|
| hs300 | 5% |
| div_idx | 7% |
| us_sp500 | 5% |
| credit | 3% |
| bond_10y | 40% |
| bond_30y | 13% |
| **gold** | **12%** |
| **nonferr** | **7.5%** |
| **soymeal** | **7.5%** |

特征：商品 27%，CAGR 7.24%，回撤最深 -8.59%。

### 4.4 三套核心指标对比（100% RP 档，2015-01 ~ 2025-12）

| 方案 | CAGR | 波动 | 回撤 | Sharpe | Calmar |
|---|---|---|---|---|---|
| V3c 多元 | **7.45%** | 4.16% | -6.71% | **1.26** | 1.11 |
| V3b 平衡 | 7.12% | 4.03% | -6.99% | 1.22 | 1.02 |
| V3d 商品偏重 | 7.24% | 4.63% | -8.59% | 1.09 | 0.84 |

数据来源：`output/summary.json`，由 `python main.py` 自动生成。
注：Sharpe = (CAGR - 2.2% 无风险利率) / Vol（2026-05-25 修正）。11 年覆盖了 2015 股灾、2016 熔断、2018 大熊市等极端情景，指标较 5.5 年期更保守但更真实。

### 4.5 V3-A 风控（★★★ 强烈推荐）

固定权重 + 三层防护的动态策略，10 资产（含 short_bond 20% 替代部分长债久期）：

| 资产 | 权重 |
|---|---|
| hs300 | 4% |
| div_idx | 6% |
| us_sp500 | 8% |
| credit | 5% |
| bond_10y | 25% |
| bond_30y | 10% |
| short_bond | 20% |
| gold | 10% |
| nonferr | 6% |
| soymeal | 6% |

三层防护：
1. **久期重构**：short_bond 20% 替代部分长债久期，降低利率敏感度
2. **月度趋势过滤**：任一资产 12m 动量为负 → 移入现金，恢复后回补
3. **回撤止损**：组合回撤 > 8% → 仓位砍半，恢复至 4% 后回补

特征：11 年 CAGR 6.74%，MDD -6.74%，Sharpe 1.15。趋势过滤器在 11 年期间拖累收益多于保护。

### 4.6 V3-B 分层风险平价（★★★ long / ★★ mid / ★ short）

无固定权重，每月动态计算。代码：`allweather/strategy_b.py`。

机制：
1. **分层风险平价**：4 个宏观桶各 25%（等权），桶内逆波动率加权
2. **相关性断路器**：平均两两相关性 > 0.30 → 仓位 cap 70%
3. **波动率目标**：年化目标 6%，超过则降仓
4. **三档投资期限**：long（100% 风险资产）/ mid（70%）/ short（40%）

short_bond 固定 5% 不参与风险预算（超低波动率会主导任何桶）。

特征（long 档 100% RP）：CAGR 6.85%，MDD -5.91%，Sharpe 1.13。风险调整后较 V3c 略低，但回撤更受控。

---

## 5. 关键设计决策与原因

### 5.1 调仓规则：半年节点 + 3% 偏离阈值（双触发）

**最终选择**：`REBAL_FREQ="2QE"`（每半年）+ `REBAL_THRESHOLD=0.03`，任一触发即调仓。代码：`allweather/backtest.py::backtest`，配置：`config.py`。

**为什么不是其它方案**：
- 跑过 4 种日历频率（月/季/半年/年）× 3 档阈值（2%/3%/5%）+ 纯阈值，共 12 组对照
- 纯 3% 阈值 Sharpe 最高（2.56–2.67），但调仓次数多
- "季度+5% 阈值" 退化成"纯季度"——5% 阈值在季度复位之间从未触发过
- "半年+3%" 在 5.5 年里只调仓 9 次，年化交易成本 ≈ 0.021%，Calmar 最高 3.08，回撤最浅 -2.86%

**结论**：选 Calmar 最高而不是 Sharpe 最高的，因为风险平价的卖点是"睡得着觉"，回撤优先。

### 5.2 不要进一步集中

跑过两个集中度更高的变体：
- V3e（轻度集中，9 资产但权重收紧）
- V3f（中度集中，砍到 8 资产）

结果：**集中反而伤害组合**——Sharpe 从 2.60 跌到 2.37，滞胀情景从 +0.02% 翻成 -0.25%。结论锁定：9 资产分散是当前最优。

### 5.3 现金降杠杆三档

| 档位 | 现金占比 | 用途 |
|---|---|---|
| 100% RP | 0% | 最大化 CAGR，主推 |
| 85% RP | 15% | 想再降一点波动的人 |
| 70% RP | 30% | 怕得睡不着的人 |

代码：`config.py::CASH_TIERS`。三档 Sharpe 都在 2.5+，但越降杠杆 CAGR 越低。

### 5.4 蒙特卡洛验证：Block Bootstrap

参数：1000 次模拟 × 5 年期 × 21 天块。`config.py::BOOTSTRAP_*`，实现：`stats.py::block_bootstrap`。

用块自助法（block=21 天 ≈ 1 个月）保留短期序列相关性，避免日内随机抽样高估稳定性。

### 5.5 回测期前推至 2015（2026-05-25）

**决策**：将回测起始日从 2020-08-01 前推至 2015-01-01（+5 年，总覆盖 ~11 年）

**动机**：覆盖 2015 股灾、2016 熔断、2017 债熊、2018 大熊市等关键宏观情景，验证策略在更多样化环境下的表现。

**数据源方案**：
- 7 个资产直接拉 ETF NAV 从 2015 起
- hs300/div_lowvol 从价格指数切换为 ETF NAV（含分红，修复 BH-4）
- nonferr: 中证有色指数(sh000823, 2015-2019) + ETF(2019+)，扣减 0.5%/年
- soymeal: 豆粕期货主力(M0, 2015-2019) + ETF(2019+)，扣减 2.0%/年
- bond_30y: ×3.0 久期放大(2015-2020-02) → 利差法(2020-02+) → ETF(2024-03+)
- bond_10y: ETF 511260(2017-08+) + 信用债 proxy(2015-2017-08)。原因：sh000139 国债指数在 2015-2019 受股灾数据污染（±14% 日波动）

**关键发现**：
- 11 年 CAGR 7.45% vs 5.5 年 CAGR 8.77%（更保守，更真实）
- 11 年 MDD -6.71% vs 5.5 年 MDD -2.89%（覆盖了极端事件）
- 所有 11 年均为正收益（最差 2018 年 +1.59%）
- 纯阈值调仓改为半年+阈值双触发（回测 11 年仅调仓 147 次）

**相关文件**：`config.py`（BACKTEST_START, SAFETY_DEDUCT, STRESS_EVENTS）, `fetch.py`（proxy fetchers）, `data.py`（stitch_series, 3-phase synthesis）

---

## 6. 项目结构

```
全季节策略/
├── main.py                     主入口
├── pyproject.toml              依赖声明（numpy/pandas/openpyxl 必需）
├── README.md                   面向用户的说明
├── PROJECT_HISTORY.md          本文件（面向 AI 的过程纪要）
├── LICENSE                     MIT
├── 桥水全季节.docx              方案文档（10 章 / 21 表）
├── 桥水全季节.html              方案文档 HTML 版
│
├── allweather/                 核心包
│   ├── __init__.py
│   ├── config.py               常量：ETF / 桶 / 调仓参数 / Bootstrap 参数
│   ├── data.py                 数据加载 + 30Y 国债合成
│   ├── fetch.py                数据拉取（akshare 包装）
│   ├── portfolios.py           V3b/V3c/V3d 权重定义 + PORTFOLIO_TAGS
│   ├── backtest.py             双触发再平衡 + 现金降杠杆
│   ├── risk.py                 风控原语：趋势过滤/回撤止损/波动率目标/HRP
│   ├── strategy_a.py           方案 A：固定权重+三层风控
│   ├── strategy_b.py           方案 B：分层风险平价+动态配置
│   ├── stats.py                perf / yearly / 风险贡献 / regime / Bootstrap
│   ├── reports.py              控制台 + JSON/CSV 持久化
│   ├── excel_export.py         多 sheet Excel 导出（openpyxl）
│   ├── markdown_report.py      Markdown 综合报告
│   └── pipeline.py             6 步流水线编排
│
├── data/                       历史 CSV（27 个，含原始/合成/对照）
├── docs/                       GitHub Pages 站点（index.html + .nojekyll）
├── results/                    早期回测中间结果（保留备查）
└── output/                     当前回测产物（运行后自动生成）
    ├── nv_curves.csv           9 条净值曲线（宽表）
    ├── summary.json            核心指标汇总
    ├── weights.csv             三套权重
    ├── report.xlsx             Excel 多表报告 ⭐
    └── report.md               Markdown 综合报告 ⭐
```

---

## 7. 6 步流水线

实现：`allweather/pipeline.py`。每步可独立调用。

| 步骤 | 函数 | 作用 |
|---|---|---|
| 1 | `step_1_load_data` | 加载 9 资产 panel，算日收益 |
| 2 | `step_2_run_backtests` | 3 策略 × 3 现金档 = 9 个回测 |
| 3 | `step_3_compute_metrics` | perf / yearly / 风险贡献 / regime / event / rolling |
| 4 | `step_4_bootstrap` | 1000 次 × 5 年 Block Bootstrap |
| 5 | `step_5_print_reports` | 9 张控制台表 |
| 6 | `step_6_save_outputs` | 写 CSV / JSON / Excel / Markdown |

---

## 8. 输出格式

| 文件 | 格式 | 用途 |
|---|---|---|
| `output/nv_curves.csv` | 宽表 CSV | 9 条净值曲线，画图直接用 |
| `output/weights.csv` | 表格 CSV | 三套权重 |
| `output/summary.json` | JSON | 9 个回测的全指标，CI sanity check 也读这个 |
| `output/report.xlsx` | Excel 多 sheet | 给人看的综合报告（11 sheet）|
| `output/report.md` | Markdown | 给 GitHub / IDE 看的综合报告 |

`report.xlsx` 的 sheet 列表（顺序）：
1. 推荐总览
2. 核心指标
3. 分年化收益
4. 风险贡献
5. 宏观情景
6. 关键事件
7. 滚动 1 年统计
8. Bootstrap 5 年分布
9. 持仓清单
10. 净值曲线
11. 权重明细

格式约定：
- 百分比列用 `0.00%` 格式，小数列用 `0.0000`
- 表头加粗 + 浅蓝填充
- 负收益自动标红
- 列宽根据内容自适应

---

## 9. 部署与 CI

| 项 | 配置 |
|---|---|
| GitHub Pages | 仓库 `/docs` 目录，`docs/index.html` 是 `桥水全季节.html` 的副本 |
| Pages URL | https://idealauror.github.io/all-weather-portfolio/ |
| GitHub Actions | `.github/workflows/backtest.yml` |
| 触发 | push / PR 到 main，paths 过滤 `main.py / allweather/** / data/** / pyproject.toml` |
| Sanity check | V3c CAGR ∈ (8%, 9.5%)，Sharpe ∈ (2.4, 2.8)，MDD ∈ (-4%, -2%) |
| Artifacts | `output/` + `backtest_output.txt`，保留 30 天 |

---

## 10. 常见维护操作

| 操作 | 怎么做 |
|---|---|
| 改权重 | 改 `allweather/portfolios.py::WEIGHTS`，重跑 `python main.py` |
| 改调仓规则 | 改 `allweather/config.py::REBAL_FREQ` / `REBAL_THRESHOLD` |
| 加新资产 | `config.py::ASSETS` 加 key，`ETF_META` 加元信息，`BUCKETS` 分桶；`data/` 放 CSV；`fetch.py` 加抓取 |
| 改回测期间 | `config.py::BACKTEST_START` / `BACKTEST_END` |
| 补数据 | `python main.py --fetch`（只补缺失）或 `--force-fetch`（全量重拉） |
| 跑单步 | `from allweather.pipeline import step_1_load_data, ...` |

---

## 11. 注意事项 / 已知陷阱

- **不要把 30Y 合成系数 3.0 当成精确久期**。它是粗略近似，在极端利率变动下会失真，但当前 5.5 年的回测期内误差可控。
- **数据来自 akshare**，存在源头限速 / 缺数据。`data/` 已预先拉好，正常情况不需要重拉。
- **再平衡逻辑里没有交易成本**。配置里有 `TURNOVER_PER_REBAL=0.08` 和 `COST_PER_SIDE=0.0015`，但默认未在净值里扣减，估算用。
- **历史不代表未来**。所有指标都是 2015-01 ~ 2025-12 这段宏观环境的产物。Bootstrap 已部分缓解，但跨结构性断点的预测仍有限。

---

## 12. 历史决策时间线（摘要）

| 阶段 | 决定 |
|---|---|
| 早期 | 9 资产 panel 定型，4 象限分桶 |
| 中期 | 跑了 V1/V2/V3 多版权重，最终保留 V3b/V3c/V3d 三套 |
| 集中度验证 | V3e/V3f 失败 → 锁定 9 资产 |
| 调仓规则验证 | 12 组对照 → 锁定半年+3% 双触发 |
| 文档化 | docx → html，章节 7 重写为"落地执行手册" |
| 工程化 | 散脚本 → `allweather/` 包 + `main.py` + `pyproject.toml` |
| 上线 | GitHub 仓库 + Pages + Actions sanity check |
| 输出强化 | 加 Excel 多 sheet 报告 + Markdown 综合报告 |
| 2026-05-25 | Sharpe 修正为 `(CAGR - 2.2%)/vol`，保留 sharpe_raw；新增 V3-A（固定权重+三层风控）和 V3-B（分层风险平价+动态配置）两种动态策略 |
