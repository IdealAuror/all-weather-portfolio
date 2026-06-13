<div align="center">

# 桥水全天候策略 · 中国版

[![Pages](https://img.shields.io/badge/docs-online-blue)](https://idealauror.github.io/all-weather-portfolio/)
[![License](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Backtest](https://img.shields.io/badge/backtest-2005--2026-green)]()
</div>

基于真实 A 股 / 债 / 商品 ETF 数据的全天候风险平价（Risk Parity）回测工程，覆盖 **2005–2026 年（~21 年完整牛熊周期）**，提供 **4 套可落地策略**（含 V4 国债期货杠杆全天候），每套支持 4 档现金管理（100% / 85% / 70% / 动态），共 15 个回测。

在线文档：[https://idealauror.github.io/all-weather-portfolio/](https://idealauror.github.io/all-weather-portfolio/)


## 策略速查

| 方案 | 风格 | CAGR | 最大回撤 | Sharpe | 一句话 |
|------|:----:|:----:|:--------:|:-----:|--------|
| **V3c 多元** | 简约派 | 8.96% | -9.17% | 1.21 | 8 资产逆波动率 60d + nonferr 趋势 + HS300 AND 抄底 |
| **V3-B 风险平价(20d)** | 学院派 | 9.48% | -10.04% | 1.21 | 4 桶等权 HRP + nonferr/gold/sp500 趋势 + Gold/HS300 抄底 |
| **V3-B 保守增强(20d)** | 保守增强 | 7.68% | **-6.08%** | 1.32 | 逆波动率 20d + nonferr 趋势 + HS300 AND 抄底 |
| **V4 全天候杠杆** | 杠杆全天候 | **11.44%** | -13.87% | **1.66** | T.CFFEX 国债期货 5x 杠杆 + 逆波动率 60d |

> V3-B RP 使用 nonferr(75d) + gold(75d) + sp500(120d) 三重趋势过滤。V3c 和 V3-B Con 使用 nonferr(75d) 趋势过滤 + HS300 AND 抄底。V3-B RP 不含 bond_10y（CAGR +1.43pp, Sharpe -0.02）。V3c 和 V3-B Con 已关闭 gold dip-buying（一致性改善）。V4 使用 bond_10y 国债期货 5x 杠杆实现真正风险平价。

**V3c 多元 (简约派)** — 8 资产（含 SC原油、沪铜）逆波动率加权（60d 回看，max_w=0.30）+ nonferr 趋势过滤（75d SMA）+ HS300 AND 抄底（PB 入场 / PE 出场）。月度调仓，最简执行。适合初入全天候、不想研究桶逻辑、追求简单透明。

**V3-B 风险平价(20d) (学院派)** — 4 桶（增长↑ / 收益垫 / 增长↓ / 通胀↑）等权分层风险平价（HRP, 20d）+ nonferr(75d) + gold(75d) + sp500(120d) 三重趋势过滤 + Gold 抄底 + HS300 AND 抄底。CAGR 9.48%（年化 1.67x 换手率）。适合长期持有者(5 年+)、认同正统全天候理念、能承受短期波动。

**V3-B 保守增强(20d) (保守增强)** — 逆波动率加权（20d 回看，max_w=0.25）+ nonferr 趋势过滤 + HS300 AND 抄底。含 bond_10y（9 资产）。Sharpe 1.32，熊市表现最好，年化成本拖累 0.17%。适合保守资金、退休金、无法忍受大幅回撤。

**V4 全天候杠杆 (杠杆全天候)** — 9 资产逆波动率 60d + **bond_10y T.CFFEX 国债期货 5x 杠杆**（notional 敞口 = capital × 5，保证金仅 2%）。杠杆释放的资本配置给权益类资产，使各宏观桶风险贡献更平衡。CAGR 11.44% 最高，Sharpe 1.66 最高，风险集中度(max/min) 3.97x 最优。适合进阶全天候投资者、理解杠杆风险、追求更高长期回报。

**多档现金管理** — 每策略支持四档: 100% RP（满仓）、85% RP（15% 货币基金）、70% RP（30% 货币基金）、动态（根据 HS300 回撤自动调节）。现金档 Sharpe 基本不衰减，适合不同风险偏好的投资者。


## 资产宇宙

基于桥水原版全天候的**四象限宏观暴露**框架，在 A 股可投范围内选择 ETF：

| 桶 | 资产 | ETF/期货代码 | V3c | V3-B RP | V3-B Con | V4 |
|----|------|:-----------:|:---:|:-------:|:--------:|:--:|
| **增长↑** | 沪深 300 | 510300 | ✓ | ✓ | ✓ | ✓ |
| | 标普 500 | 513500 | ✓ | ✓ | ✓ | ✓ |
| **收益垫** | 城投债 | 511220 | ✓ | ✓ | ✓ | ✓ |
| **增长↓ 10Y** | 10 年国债 | 511260 | — | — | ✓ | ✓(5x) |
| **增长↓ 30Y** | 30 年国债 | 511130 | ✓ | ✓ | ✓ | ✓ |
| **通胀↑** | 黄金 | 518880 | ✓ | ✓ | ✓ | ✓ |
| | 有色金属 | 159980 | ✓ | ✓ | ✓ | ✓ |
| | SC 原油 | SC.INE | ✓ | ✓ | ✓ | ✓ |
| | 沪铜 | CU.SHF | ✓ | ✓ | ✓ | ✓ |

> SC 原油期货（SC.INE，2018+）用 WTI CL × USDCNY 拼接历史数据，人民币计价无 QDII 限制。沪铜期货（CU.SHF）独立暴露，年化展期成本扣减 0.3%。
>
> V4 中 bond_10y 使用 T.CFFEX 国债期货 5x 名义杠杆：capital 分配 ~30% × 5 = 150% notional 债券敞口，保证金仅消耗 ~2% 资本，释放现金配置权益。

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
│   ├── backtest.py          统一回测引擎（含 V4 杠杆模型）
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

python -m allweather.rebalance        # 实盘再平衡（四策略对比 + 信号仪表盘）
python -m allweather.rebalance --strat V3c   # 只看 V3c 详情
python -m allweather.rebalance --strat V4    # V4 全天候杠杆（含杠杆敞口）
python -m allweather.rebalance --signals     # 只看当前市场信号状态
```

**输出文件说明**:

| 文件 | 说明 |
|------|------|
| `output/report.xlsx` | 11-sheet Excel 综合报告 |
| `output/nv_curves.csv` | 全部回测净值曲线宽表 |
| `output/weight_history_*.csv` | 四策略权重历史 |
| `output/signal_log.csv` | 风控信号触发日志 |
| `docs/charts/*.png` | 分析图表 |
| `docs/data.json` | 结构化指标（前端展示用） |


## 回测局限

- **30 年国债数据合成**：2024 年 3 月前无真实 ETF 数据，采用三阶段合成法（久期乘数 → 利差法 → 真实数据），合成段年化扣减 0.3%
- **QDII 限购**：标普 500（513500）受 QDII 额度限制，极端行情可能出现溢价或暂停申购。原油已用 SC 期货替代，无 QDII 问题
- **V4 杠杆模型**：使用合成杠杆（T.CFFEX 风格）而非真实期货数据。未模拟展期成本、基差风险和保证金追缴。融资利差固定为 20bp，实盘可能更高
- **费用假设**：回测以价格收益率为准，未扣除管理费、托管费（ETF 层面约 0.5%/年），通过无风险利率修正 Sharpe
- **不可执行风险**：回测假设每月调仓日以收盘价成交，实盘存在滑点和流动性差异

