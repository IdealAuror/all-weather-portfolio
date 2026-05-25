# 奥卡姆剃刀精简：6 策略 → 3 策略 设计文档

> 日期：2026-05-25 | 状态：已批准

## 背景

经过两轮迭代（回测期前推至 2015、动态策略精简），我们得到 6 个策略：

| 策略 | 推荐度 | CAGR | MDD | Sharpe |
|------|--------|------|-----|--------|
| V3c 多元 | ★★★ | 7.45% | -6.71% | 1.26 |
| V3b 平衡 | ★★ | 7.12% | -6.99% | 1.22 |
| V3d 商品偏重 | ★★ | 7.24% | -8.59% | 1.09 |
| V3-A 保守 | ★★ | 6.83% | -8.16% | 1.14 |
| V3-B 60d | ★★★ | 7.01% | -5.98% | 1.14 |
| V3-B 120d | ★★★ | 6.84% | -6.37% | 1.09 |

应用奥卡姆剃刀原则审视：

- **V3c 是最简单的策略，也是最好的**（Sharpe 最高 1.26，CAGR 最高 7.45%）
- V3b 被 V3c 全面覆盖（相似结构，更差指标）
- V3d 回撤最深（-8.59%），无独特优势
- V3-A 短债拖累收益，全维度落后 V3c
- V3-B 60d/120d 虽然是动态策略，但代表了桥水正统方法论——分层风险平价

**结论：只保留 ★★★ 策略。** V3c（实战最优）+ V3-B 60d/120d（方法论纯正），其余三个砍掉。

## 目标

1. 从 6 策略精简到 3 策略（V3c / V3-B 60d / V3-B 120d），回测从 18→9
2. 删除 strategy_a.py（V3-A 移除后无调用方）
3. 清理所有 short_bond 相关代码（仅 V3-A 使用）
4. 所有文档同步更新

## 设计

### 两条线定位

| | V3c 多元 | V3-B 风险平价 |
|---|---|---|
| **定位** | 实战派 — "照这个买就行" | 学院派 — "桥水怎么做就怎么做" |
| **方法论** | 固定权重 + 阈值再平衡 | 分层风险平价 + 月度调仓 |
| **适合** | 要最优指标，不想折腾 | 认同桥水方法论，接受略低 Sharpe |
| **★★★理由** | 11 年回测最优 | 方法论纯正，回撤最浅 |

V3-B 跑输 V3c 的原因：11 年中国市场资产间协方差结构未发生剧烈变化，固定权重已足够；月度调仓边际收益≈噪音。保留 V3-B 不是因为"更好"，而是因为它是桥水方法论的正统表达。如果未来市场结构剧变，V3-B 的动态适应能力可能体现价值。

### 代码变更

**删除文件：**
- `allweather/strategy_a.py` — V3-A 移除后无调用方

**修改文件：**

`allweather/portfolios.py`：
- 删除 WEIGHTS 中的 "V3b 平衡"、"V3d 商品偏重"、"V3-A 保守"
- 删除 PORTFOLIO_TAGS 中对应条目（只保留 3 个 ★★★）
- 删除 `from .config import ASSETS, ASSETS_PLAN_A` 中的 ASSETS_PLAN_A
- get_weights() 简化：不再需要 V3-A 特判和 ASSETS_PLAN_A 分支

`allweather/pipeline.py`：
- step_2: 删除 V3-A backtest_a 调用块（含 `from .strategy_a import backtest_a`）
- step_2: 简化权重遍历，不再需要 `if "V3-A" in port: continue`
- step_4: 删除 V3-A bootstrap 相关逻辑
- step_1: `load_panel_extended()` → `load_panel()`（data.py 同步改名）

`allweather/config.py`：
- 删除 ASSETS_PLAN_A（仅 V3-A 使用）
- 删除 ETF_META["short_bond"]
- BUCKETS / BUCKET_GROUPS 移除 short_bond
- 保留 RISK_PARITY_WINDOW / RISK_PARITY_WINDOW_LONG（V3-B 仍用）

`allweather/strategy_b.py`：
- 删除 SHORT_BOND_FIXED = 0.05
- _compute_weights() 移除 has_short_bond 参数和所有 short_bond 处理
- backtest_b() 简化：不再检查 "short_bond" in cols
- 纯 9 资产分层风险平价

`allweather/data.py`：
- load_panel_extended() 重命名为 load_panel()
- 移除 short_bond 列加载逻辑

**不变文件：**
backtest.py · stats.py · reports.py · risk.py · excel_export.py · markdown_report.py · fetch.py · main.py

### 文档变更

`README.md`：
- 策略速查表：两个子表合并为单表 3 策略，加"定位"列
- 更新数据：18→9 净值曲线，6→3 策略权重
- 增加 V3c vs V3-B 选择指南

`docs/index.html`：
- 删除 V3b / V3d / V3-A 策略详情卡片
- 对比表只保留 3 列
- 新增"V3c vs V3-B：怎么选"小节

`PROJECT_HISTORY.md`：
- 删除 4.2（V3b）、4.3（V3d）、4.5（V3-A）小节
- 4.6（V3-B）精简 short_bond 内容
- 新增 5.7 决策记录
- 项目结构更新

`allweather/markdown_report.py`：
- 推荐表 notes 精简为 3 条
- holdings/weights 表不再有 V3b/V3d/V3-A 列

## 影响范围

| 维度 | 前 | 后 |
|------|----|----|
| 策略数 | 6 | 3 |
| 回测数 | 18 | 9 |
| NV 曲线 | 18 条 | 9 条 |
| Python 文件 | 13 | 12（删 strategy_a.py） |
| 代码行数 | — | 预计净删 ~300 行 |

## 不变的设计决策

此次精简不改变：
- 9 资产 panel 定义
- 调仓规则（半年+3% 阈值双触发）
- 现金三档（100%/85%/70%）
- Bootstrap 参数
- 回测期间（2015-2025）
- V3c 权重数值
- V3-B 风险平价算法

## 验收

- [ ] `python main.py` 跑通，3 策略 × 3 现金档 = 9 回测
- [ ] 无 import error（不再引用 strategy_a / ASSETS_PLAN_A / short_bond）
- [ ] V3c 指标不变（CAGR 7.45%, Sharpe 1.26, MDD -6.71%）
- [ ] V3-B 60d/120d 指标不变
- [ ] 控制台、Excel、Markdown 三份报告全部生成
- [ ] README 速查表显示 3 策略
- [ ] docs/index.html 只展示 3 策略
