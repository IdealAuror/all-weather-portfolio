<div align="center">

# 桥水全天候策略 · 中国版

[![Pages](https://img.shields.io/badge/docs-online-blue)](https://idealauror.github.io/all-weather-portfolio/)
[![License](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Backtest](https://img.shields.io/badge/backtest-2005--2026-green)]()
</div>

基于 A 股 / 债 / 商品 ETF 真实数据的全天候风险平价回测工程，覆盖 **2005–2026 年（~21 年完整牛熊）**，提供 **3 套可落地策略**，每套支持 3-4 档现金管理（100% / 85% / 70% / 动态），共 11 个回测。

在线文档：[https://idealauror.github.io/all-weather-portfolio/](https://idealauror.github.io/all-weather-portfolio/)


## 策略速查

| 方案 | 风格 | CAGR | 波动率 | 最大回撤 | Sharpe | 一句话 |
|------|:----:|:----:|:------:|:--------:|:-----:|--------|
| **V3-B 保守增强(20d)** | 保守增强 | **{BCON_CAGR}** | {BCON_VOL} | **{BCON_MDD}** | **{BCON_SHARPE}** | 逆波动率 20d + nonferr(75d) + HS300 AND 抄底 |
| **V3-B 风险平价(20d)** | 学院派 | {BRP_CAGR} | {BRP_VOL} | {BRP_MDD} | {BRP_SHARPE} | 4 桶等权 HRP + nonferr/gold/sp500/hs300 趋势 + 抄底 + 波动率控制 |
| **V3c 多元** | 多元全天候 | **{V3C_CAGR}** | {V3C_VOL} | {V3C_MDD} | {V3C_SHARPE} | 6 资产逆波动率 60d + {V3C_TREND_DESC} + HS300 AND 抄底 |

> V3-B RP 四重趋势过滤：nonferr(75d) + gold(75d) + sp500(75d) + hs300(30d)；V3c 三重趋势过滤：nonferr(75d) + gold(75d) + sp500(75d)。不含 bond_10y（CAGR +1.43pp, Sharpe -0.02）。V3c 多元 6 资产逆波动率 60d，同样不含 bond_10y。本表为**不含原油**版本（6 资产），含原油对比见下方。

| | 定位 | CAGR | MDD | 核心约束 | 趋势过滤 | 负收益年 |
|--|:--:|:---:|:---:|:--------:|:--------:|:--------:|
| **V3-B 保守增强** | 保守防御 | ≥ 7% | ≤ -7% | Sharpe ≥ 1.2 | 1 个 | {BCON_NEG_YEARS} |
| **V3-B 风险平价** | 进取高回报 | ≥ 8.5% | ≤ -9% | CAGR 优先 | 4 个 | {BRP_NEG_YEARS} |
| **V3c 多元** | 中位中枢 | ≥ 8.5% | ≤ -8.5% | 回撤优先 | 3 个 | {V3C_NEG_YEARS} |

> 以上约束以无原油版本为基准。含原油版本 MDD 更优、CAGR 略低，详见"含原油对比"。

### 一句话选策略

| 你的情况 | 选 |
|---------|:---:|
| 退休金、不能亏、随时可能用钱 | **V3-B 保守增强** |
| 长期储蓄（5年+）、认同全天候理念、能承受短期波动 | **V3-B 风险平价** |
| 追求高回报、接受多元资产分散、理解趋势过滤逻辑 | **V3c 多元** |


## 资产宇宙

基于桥水原版**四象限宏观暴露**框架，在 A 股可投范围内选择 ETF：

| 桶 | 资产 | 代码 | V3-B Con | V3-B RP | V3c 多元 |
|----|------|:----:|:--------:|:-------:|:--------:|
| **增长↑** | 沪深 300 | 510300 | ✓ | ✓ | ✓ |
| | 标普 500 | 513500 | ✓ | ✓ | ✓ |
| **收益垫** | 城投债 | 511220 | ✓ | ✓ | ✓ |
| **增长↓ 10Y** | 10 年国债 | 511260 | ✓ | — | — |
| **增长↓ 30Y** | 30 年国债 | 511130 | ✓ | ✓ | ✓ |
| **通胀↑** | 黄金 | 518880 | ✓ | ✓ | ✓ |
| | 有色金属 | 159980 | ✓ | ✓ | ✓ |

> V3c 和 V3-B RP 不含 bond_10y（与 bond_30y 同在增长↓桶，久期更短，对组合贡献冗余）。
> 
> 30 年国债 ETF（511130）2024 年 3 月上市。回测覆盖 2005–2024 年数据缺口：**2005–2020** 10Y 国债指数 × 久期放大(×3.0)，**2020–2024** 利差法（10Y + 期限利差），**2024+** 真实数据。合成段年化扣减 0.3%。
>
> **原油（南方原油 LOF 501018）**：目前申购暂停，不在主版本策略中。含原油对比见下方。

## 附：含原油对比

在 7 资产基础上加入原油（南方原油 LOF 501018），三策略核心指标对比如下：

| 策略 | 版本 | CAGR | 波动率 | 最大回撤 | Sharpe | Calmar |
|------|:---:|:----:|:------:|:--------:|:-----:|:------:|
| **V3-B 保守增强** | 无原油 | **{BCON_CAGR}** | {BCON_VOL} | {BCON_MDD} | **{BCON_SHARPE}** | {BCON_CALMAR} |
| | +原油 | {BCON_WTI_CAGR} | {BCON_WTI_VOL} | **{BCON_WTI_MDD}** | {BCON_WTI_SHARPE} | **{BCON_WTI_CALMAR}** |
| **V3-B 风险平价** | 无原油 | **{BRP_CAGR}** | {BRP_VOL} | {BRP_MDD} | **{BRP_SHARPE}** | {BRP_CALMAR} |
| | +原油 | {BRP_WTI_CAGR} | {BRP_WTI_VOL} | **{BRP_WTI_MDD}** | {BRP_WTI_SHARPE} | **{BRP_WTI_CALMAR}** |
| **V3c 多元** | 无原油 | **{V3C_CAGR}** | {V3C_VOL} | {V3C_MDD} | **{V3C_SHARPE}** | {V3C_CALMAR} |
| | +原油 | {V3C_WTI_CAGR} | {V3C_WTI_VOL} | **{V3C_WTI_MDD}** | {V3C_WTI_SHARPE} | **{V3C_WTI_CALMAR}** |

> 加入原油后 CAGR 下降 0.2-0.3pp（WTI 本身 CAGR 约 2%），但 MDD 改善 1-2pp。原油在通胀桶内与 gold/nonferr 形成分散，降低尾部风险。当前 501018 申购暂停，恢复后可启用含原油版本。


## 快速开始

```bash
pip install -r requirements.txt
python main.py                        # 全量回测（6 步流水线）
python main.py --fetch                # 拉数据 + 回测
python main.py --no-excel             # 跳过 Excel 报告
python main.py --no-markdown          # 跳过 Markdown 报告

python -m allweather.rebalance        # 实盘再平衡（四策略对比 + 信号仪表盘）
python -m allweather.rebalance --strat V3c   # 只看 V3c 详情
python -m allweather.rebalance --signals     # 只看当前市场信号状态
```

**输出文件**:

| 文件 | 说明 |
|------|------|
| `output/report.xlsx` | 11-sheet Excel 综合报告 |
| `output/nv_curves.csv` | 全部回测净值曲线宽表 |
| `output/weight_history_*.csv` | 权重历史 |
| `output/signal_log.csv` | 风控信号触发日志 |
| `docs/charts/*.png` | 15 张分析图表 |
| `docs/data.json` | 结构化指标（前端展示用） |



## 回测局限

- **30 年国债数据合成**：2024 年 3 月前无真实 ETF 数据，三阶段合成（久期乘数 → 利差法 → 真实数据），合成段年化扣减 0.3%
- **QDII 限购**：标普 500（513500）受 QDII 额度限制，极端行情可能溢价或暂停申购
- **费用假设**：回测以价格收益率为准，未扣管理费/托管费（ETF 层面 ~0.5%/年），通过无风险利率修正 Sharpe
- **不可执行风险**：回测假设每月调仓日收盘价成交，实盘存在滑点和流动性差异


## 项目目录

```
├── main.py                  # 入口：全量回测
├── pyproject.toml
├── allweather/              # 核心模块
│   ├── config.py            常量（参数阈值、回测区间）
│   ├── data.py              数据加载 + 30Y 国债三阶段合成
│   ├── fetch.py             通过 akshare 拉取实时数据
│   ├── backtest.py          统一回测引擎（V3-B RP/V3-B Con/V3c）
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
