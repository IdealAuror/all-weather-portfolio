# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## 策略优化闭环

所有策略改动遵循此流程，不跳步：

```
问题定义 → 假设 → 设计 → 验证 → 稳健性检验 → 决策 → 实施
   ↑                                                            │
   └────────────────────────────────────────────────────────────┘
```

1. **问题定义** — 可量化的缺陷（具体时间、幅度、原因）
2. **假设** — 因果陈述，可证伪，有经济学逻辑
3. **设计** — 参数选择 + 逻辑边界 + 交互效应；网格搜索，整数窗口
4. **验证** — 单变量对比，检查 CAGR/波动/MDD/Sharpe/Calmar/最差年份/事件期/宏观情景
5. **稳健性检验** — 参数敏感度(±50%) + D_excess + 80/20 检验 + 过拟合风险
6. **决策** — 二选一，通过→实施，否决→写 memory 记录原因
7. **实施** — 按 checklist 执行

## 前置原则（Sperandeo 三层结构）

按优先级排序，不可颠倒：

**第一层：保障资本。** D_excess 尾部风险诊断（每次验证必须跑，D<<0 直接否决）| 墨菲定律（每个信号有 fallback）| 止损纪律（不扛下跌趋势）

**第二层：一致性的获利能力。** 奥卡姆剃刀（从最简开始）| 80/20 检验（CAGR+0.3pp 或 MDD-1pp 以上才值得）| 休谟因果（必须有经济学逻辑）| 最小描述长度（参数响应面平的→砍掉）

**第三层：追求卓越的报酬。** HS300 AND 抄底（只在极端便宜时加仓 1.8x）| 方案 C 教训（不可摊平亏损）

## 实施 Checklist

| # | 步骤 | 内容 |
|---|------|------|
| 1 | 改代码 | `config.py`(常量) → `pipeline.py`(调用) → `strategy_b.py`/`backtest.py`(引擎) |
| 2 | 全量回测 | `py main.py`，确认无报错并记录指标 |
| 3 | 更新文档 | `README.md`、`docs/index.html` 等（`output/` 自动生成） |
| 4 | 更新 Memory | 有新结论或推翻旧结论时才写 |
| 5 | 提交 | `git add -A && git commit -m "..." && git push` |

## 行为原则

| # | 原文 | 含义 |
|---|------|------|
| 1 | **Think Before Coding** | 先分析再动手，不沉默假设 |
| 2 | **Simplicity First** | 最短代码，不为未来造抽象 |
| 3 | **Surgical Changes** | 只改必须改的，不重构没坏的东西 |
| 4 | **Goal-Driven Execution** | 定义验收标准，循环直到通过 |
| 5 | **Don't route decisions through the model** | 确定性逻辑写代码，不消耗 token |
| 6 | **Hard token budgets** | 每任务设上限，到了就停 |
| 7 | **Surface conflicts, don't average** | 有分歧选一个，不取平均 |
| 8 | **Read before you write** | 先读相邻文件，理解既有模式 |
| 9 | **Tests are not optional, but they're not the goal** | 写有意义测试，假通过不如没有 |
| 10 | **Long-running operations need checkpoints** | 每步检查点，一步错不丢全部进度 |
| 11 | **Convention beats novelty** | 匹配既有模式，两个模式比一个坏模式更糟 |
| 12 | **Fail visibly, not silently** | 出问题大声说，沉默隐藏 bug |

## Git 规则

- 单人项目，直接推 main。`git add -A && git commit -m "..." && git push`
- Commit message 禁止 Co-Authored-By 署名
- 大改动可开 feature 分支，最终合 main

## 模型选择

日常分析用当前模型（Flash）。以下场景**必须**用 Agent + `model: "opus"`：

- **复杂策略分析** — 多变量对比、参数响应面解读、敏感度网格的统计推断
- **统计诊断** — D_excess 尾部风险分析、Bootstrap 分布解读、过拟合检验
- **回测异常排查** — 归因分析、事件期解剖、多因子分离
- **新机制设计** — 优化闭环中"问题定义→假设→设计"前三个阶段

简单任务（改常量、更新文档、常规 commit）不走 Agent，直接在当前会话处理。

## 命令

```bash
py main.py                         # 全量回测
py main.py --no-excel              # 跳过 Excel
py main.py --no-markdown           # 跳过 Markdown
py main.py --fetch                 # 拉数据 + 回测
py main.py --fetch-only            # 仅拉数据
py main.py --force-fetch           # 强制重拉
python -m allweather.rebalance              # 实盘再平衡
python -m allweather.rebalance --strat V4   # 只看 V4 详情
python -m allweather.rebalance --signals    # 只看当前市场信号状态
```

CI：`.github/workflows/backtest.yml` 跑 `py main.py`，检查 Sharpe/MDD 边界。

## 策略目标框架

所有改动必须满足各策略的目标约束，按通用红线 → 策略专属约束的优先级逐层检查。

| 指标 | V3-B 保守增强 | V3c 多元 | V3-B 风险平价 |
|------|:-------------:|:--------:|:-------------:|
| **定位** | 保守防御 | 中位中枢 | 进取高回报 |
| **CAGR 目标** | ≥ 7% | ≥ 8.5% | ≥ 8.5% |
| **MDD 上限** | ≤ -7% | ≤ -8.5% | ≤ -9% |
| **波动率上限** | ≤ 5% | ≤ 6% | ≤ 7% |
| **核心约束** | Sharpe ≥ 1.2 | 回撤优先 | CAGR 优先 |
| | | | |
| **通用红线** | | | |
| 换手率（年化） | ≤ 2x | ≤ 2x | ≤ 2x |
| 最差单年 | ≥ -8% | ≥ -8% | ≥ -10% |
| 正收益年比例 | ≥ 70% | ≥ 70% | ≥ 70% |
| Bootstrap 5年亏损概率 | < 5% | < 5% | < 8% |
| D_excess | ≥ -0.5 | ≥ -0.5 | ≥ -0.5 |

> Sharpe 为修正版 `(CAGR - 2.2%) / vol`（代码中 `sharpe` 字段）。MDD 为全样本最大回撤。CAGR 为几何年化收益率。

## 策略速查

| 策略 | 一句话 |
|------|--------|
| V3-B 保守增强(20d) | 逆波动率20d + nonferr75d趋势 + HS300 AND抄底 — Sharpe 1.28 |
| V3c 多元 | 8资产逆波动率60d + nonferr75d + SP500趋势75d + HS300 AND抄底 — MDD -7.26% |
| V3-B 风险平价(20d) | 4桶HRP + 三重趋势 + 抄底 + target_vol=9% — CAGR 9.33% |

增长↑(hs300,sp500) | 收益垫(credit) | 增长↓10Y(bond_10y) | 增长↓30Y(bond_30y) | 通胀↑(gold,nonferr,wti,copper)

## 外部参考

- [策略参考.md](策略参考.md) — 策略详情、资产桶表、关键常量、设计决策
- [架构参考.md](架构参考.md) — 模块结构、流水线、依赖关系
- [项目.md](项目.md) — 完整分析文档（性能优化、回测异常排查）
- Memory — `.claude/projects/C--Users-MOSS-Desktop------/memory/`
