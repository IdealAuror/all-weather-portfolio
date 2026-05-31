<div align="center">

# 桥水全天候策略 · 中国版

[![Pages](https://img.shields.io/badge/docs-online-blue)](https://idealauror.github.io/all-weather-portfolio/)
[![License](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Backtest](https://img.shields.io/badge/backtest-2005--2026-green)]()
</div>

基于真实 A 股 / 债 / 商品 ETF 数据的全天候风险平价（Risk Parity）回测工程，覆盖 **2005–2026 年（~21 年完整牛熊周期）**，提供 3 套可落地策略，每套支持 4 档现金管理（100% / 85% / 70% / 动态），共 12 个回测。


## 策略速查

| 方案 | 风格 | CAGR | 最大回撤 | Sharpe | 一句话 |
|------|:----:|:----:|:--------:|:-----:|--------|
| **V3c 多元** | 简约派 | 7.90% | -7.01% | 1.43 | 6 资产逆波动率 60d + nonferr 趋势 + HS300 AND 抄底 |
| **V3-B 风险平价(20d)** | 学院派 | **10.03%** | -9.48% | 1.39 | 4 桶等权 RP + nonferr/gold/sp500 趋势 + Gold/HS300 抄底 |
| **V3-B 保守增强(20d)** | 保守增强 | 6.76% | **-5.35%** | 1.36 | 逆波动率 20d + nonferr 趋势 + HS300 AND 抄底 |

> V3-B RP 使用 nonferr(75d) + gold(75d) + sp500(120d) 三重趋势过滤。V3c 和 V3-B Con 使用 nonferr(75d) 趋势过滤 + HS300 AND 抄底。V3-B RP 不含 bond_10y（CAGR +1.43pp, Sharpe -0.02）。

**V3c 多元 (简约派)** — 6 资产逆波动率加权（60d 回看，max_w=0.30）+ nonferr 趋势过滤（75d SMA）+ Gold 抄底 + HS300 AND 抄底（PB 入场 / PE 出场）。月度调仓，最简执行。适合初入全天候、不想研究桶逻辑、追求简单透明。

**V3-B 风险平价(20d) (学院派)** — 4 桶（增长↑ / 收益垫 / 增长↓ / 通胀↑）等权分层风险平价（HRP, 20d）+ nonferr(75d) + gold(75d) + sp500(120d) 三重趋势过滤 + Gold 抄底 + HS300 AND 抄底。CAGR 最高（年化 1.68x 换手率）。适合长期持有者(5 年+)、认同正统全天候理念、能承受短期波动。

**V3-B 保守增强(20d) (保守增强)** — 逆波动率加权（20d 回看，max_w=0.25）+ nonferr 趋势过滤 + HS300 AND 抄底。含 bond_10y（7 资产）。回撤最低(-5.35%)，熊市表现最好，年化成本拖累仅 0.21%。适合保守资金、退休金、无法忍受大幅回撤。

**多档现金管理** — 每策略支持四档: 100% RP（满仓）、85% RP（15% 货币基金）、70% RP（30% 货币基金）、动态（根据 HS300 回撤自动调节）。现金档 Sharpe 基本不衰减，适合不同风险偏好的投资者。


## 资产宇宙

基于桥水原版全天候的**四象限宏观暴露**框架，在 A 股可投范围内选择 ETF：

| 桶 | 资产 | ETF 代码 | V3c | V3-B RP | V3-B Con |
|----|------|:--------:|:---:|:-------:|:--------:|
| **增长↑** | 沪深 300 | 510300 | ✓ | ✓ | ✓ |
| | 标普 500 | 513500 | ✓ | ✓ | ✓ |
| **收益垫** | 城投债 | 511220 | ✓ | ✓ | ✓ |
| **增长↓ 10Y** | 10 年国债 | 511260 | — | — | ✓ |
| **增长↓ 30Y** | 30 年国债 | 511130 | ✓ | ✓ | ✓ |
| **通胀↑** | 黄金 | 518880 | ✓ | ✓ | ✓ |
| | 有色金属 | 159980 | ✓ | ✓ | ✓ |
| **通胀↑ 备选** | ~~原油(QDII)~~ | ~~501018~~ | — | — | — |

> 原油（南方原油 LOF 501018）数据管道已接入，因 QDII 限购+溢价异常，暂不可执行。

> 30 年国债 ETF（511130）2024 年 3 月才上市。回测覆盖 2005–2024 年数据缺口采用三阶段合成法：**2005–2020** 用 10Y 国债指数 × 久期放大系数(×3.0)近似；**2020–2024** 用利差法（10Y + 期限利差）；**2024+** 使用真实 ETF 数据。合成段年化扣减 0.3% 作为期权费率差。

---

## 项目目录

```
├── main.py                  # 入口：全量回测
├── pyproject.toml
├── allweather/              # 核心模块
│   ├── config.py            常量（参数阈值、回测区间）
│   ├── data.py              数据加载 + 30Y 国债三阶段合成
│   ├── fetch.py             通过 akshare 拉取实时数据
│   ├── backtest.py          V3c 引擎（逆波动率加权）
│   ├── strategy_b.py        V3-B 引擎（分层风险平价 + 保守增强）
│   ├── risk.py              逆波动率 / 风险平价 / 趋势过滤算法
│   ├── stats.py             绩效指标 / Bootstrap / D_excess 尾部诊断
│   ├── reports.py           控制台输出
│   ├── charts.py            15 张分析图表生成
│   ├── rebalance.py         实盘再平衡（信号仪表盘）
│   └── pipeline.py          6 步流水线编排
├── data/                    # 历史数据 CSV
├── docs/                    # GitHub Pages 文档
│   ├── index.html           交互式报告
│   ├── data.json            结构化指标
│   ├── strategy-paper.md    策略设计论文
│   └── charts/              分析图表 PNG
└── output/                  # 自动生成（回测报告/Excel/权重日志）
```

---

## 快速开始

```bash
pip install -r requirements.txt
python main.py                        # 全量回测（6 步流水线）
python main.py --fetch                # 拉数据 + 回测
python main.py --no-excel             # 跳过 Excel 报告
python main.py --no-markdown          # 跳过 Markdown 报告

python -m allweather.rebalance        # 实盘再平衡（三策略对比 + 信号仪表盘）
python -m allweather.rebalance --strat V3c   # 只看 V3c 详情
python -m allweather.rebalance --signals     # 只看当前市场信号状态
```

**输出文件说明**:

| 文件 | 说明 |
|------|------|
| `output/report.xlsx` | 11-sheet Excel 综合报告 |
| `output/nv_curves.csv` | 全部回测净值曲线宽表 |
| `output/weight_history_*.csv` | 三策略权重历史 |
| `output/signal_log.csv` | 风控信号触发日志 |
| `docs/charts/*.png` | 分析图表 |
| `docs/data.json` | 结构化指标（前端展示用） |


## 回测局限

- **30 年国债数据合成**：2024 年 3 月前无真实 ETF 数据，采用三阶段合成法（久期乘数 → 利差法 → 真实数据），合成段年化扣减 0.3%
- **QDII 限购**：标普 500（513500）和原油（501018）受 QDII 额度限制，极端行情可能出现溢价或暂停申购
- **费用假设**：回测以价格收益率为准，未扣除管理费、托管费（ETF 层面约 0.5%/年），通过无风险利率修正 Sharpe
- **不可执行风险**：回测假设每月调仓日以收盘价成交，实盘存在滑点和流动性差异

---

## 许可

[AGPL-3.0](LICENSE)
