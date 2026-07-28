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
## 前置原则
### 第 0 层：哲学基座
方法论的底层。所有 Sperandeo 原则之所以成立，是因为它们符合以下更根本的认知规律：
**实事求是。** 每个参数回答"为什么在中国数据上成立"。桥水原版是起点不是终点。30Y 三阶段合成、HS300 AND 抄底、nonferr 75d — 全是实事求是的结果。
**矛盾论。** 80/20 是主要矛盾的量化。桶结构是主要方面，内部加权是次要方面。牛市收益是主要矛盾，熊市回撤是主要矛盾。不同质的矛盾用不同方法解决。
**实践论。** 7 步闭环 = 认识→实践→再认识。memory 是实践记录，否决≠删除。具体分析见 `docs/framework/马克思主义.md`。
### Sperandeo 三层结构
按优先级排序，不可颠倒：
**第一层：保障资本。** D_excess 尾部风险诊断（每次验证必须跑，D<<0 直接否决）| 墨菲定律（每个信号有 fallback）| 止损纪律（不扛下跌趋势）
**第二层：一致性的获利能力。** 奥卡姆剃刀（从最简开始）| 80/20 检验（CAGR+0.3pp 或 MDD-1pp 以上才值得）| 休谟因果（必须有经济学逻辑）| 最小描述长度（参数响应面平的→砍掉）
**第三层：追求卓越的报酬。** HS300 AND 抄底（只在极端便宜时加仓 1.8x）| 方案 C 教训（不可摊平亏损）
## 实施 Checklist
| # | 步骤 | 内容 |
|---|------|------|
| 1 | 改代码 | `config.py`(常量) → `pipeline.py`(调用) → `strategy_b.py`/`backtest.py`(引擎) |
| 2 | 全量回测 | `py main.py`，确认无报错并记录指标 |
| 3 | 更新文档 | `py main.py` 自动同步 `README.md`（编辑文字改 `README.template.md`）、`docs/index.html`、`docs/charts/` |
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
### 分工原则
| 改动类型 | 执行 | 审查 | 说明 |
|---------|:----:|:----:|------|
| **简单任务** | Flash 直接 | 不审查 | 改常量、更新文档、常规 commit |
| **常规改动** | Flash Agent | Flash Agent | 策略参数调整、回测逻辑小改 — 一个改一个审，交叉检查 |
| **重要改动** | Flash Agent | Opus Agent | 新机制实现、参数网格搜索、多变量对比 — Opus 给高层指导，Flash 执行，Opus 审结果 |
| **核心决策** | Opus Agent 直接 | — | 问题定义→假设→设计阶段、统计诊断、D_excess、过拟合检验 |
### 常规改动审查流程
1. Agent A（Flash）：执行改动
2. Agent B（Flash）：独立审查，检查逻辑正确性、边界条件、是否符合 CLAUDE.md 规则
3. 审查发现问题则回到步骤 1，通过则继续
### 重要改动审查流程
1. Opus Agent：分析问题、给出设计方案、参数范围建议
2. Flash Agent：按 Opus 方案实现代码
3. Opus Agent：审查实现、检查指标、验证稳健性
4. 通过后进入实施 Checklist
## 命令
```bash
py main.py                         # 全量回测（自动增量更新数据 + 报告）
# flags: --force-fetch  --no-excel  --no-markdown
python -m allweather.rebalance     # 实盘再平衡
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
| V3-B 保守增强(20d) | 逆波动率20d + nonferr75d趋势 + HS300 AND抄底 — Sharpe 1.50 |
| V3c 多元 | 6资产逆波动率60d + nonferr/gold/sp500趋势75d + HS300 AND抄底 — MDD -7.06% |
| V3-B 风险平价(20d) | 4桶HRP + 四重趋势 + 抄底 + target_vol=9% — CAGR 8.87% |
增长↑(hs300,sp500) | 收益垫(credit) | 增长↓10Y(bond_10y) | 增长↓30Y(bond_30y) | 通胀↑(gold,nonferr)
## 策略参考

| 策略 | 引擎 | 核心逻辑 | 资产 | 特点 |
|------|------|----------|------|------|
| V3-B 保守增强(20d) | `strategy_b.py::backtest_b` | 逆波动率 20d (max 0.25) + nonferr 75d + HS300 AND抄底 | 7 (含 bond_10y) | Sharpe 最高 |
| V3-B 风险平价(20d) | `strategy_b.py::backtest_b` | 4 桶等权 HRP + nonferr 75d + gold 75d + sp500 75d + hs300 30d + HS300 AND抄底 | 6 (无 bond_10y) | CAGR 最高 |
| V3c 多元 | `backtest.py::backtest_iv` | 逆波动率 60d + nonferr 75d + gold 75d + sp500 75d + HS300 AND抄底 | 6 (无 bond_10y) | 最均衡 |

× 3-4 现金档：100% RP / 85% RP / 70% RP / 动态（仅 V3-B 系列）。

### 资产与桶

| 桶 | 资产 | V3-B Con | V3-B RP | V3c |
|----|------|:--------:|:-------:|:---:|
| 增长↑ | hs300, us_sp500 | ✓ | ✓ | ✓ |
| 收益垫 | credit | ✓ | ✓ | ✓ |
| 增长↓10Y | bond_10y | ✓ | — | — |
| 增长↓30Y | bond_30y | ✓ | ✓ | ✓ |
| 通胀↑ | gold, nonferr | ✓ | ✓ | ✓ |

V3-B RP 和 V3c 去掉了 bond_10y（CAGR +1.43pp，Sharpe 仅 -0.02）。

### 关键常量

| 常量 | 值 | 说明 |
|------|-----|------|
| `BACKTEST_START/END` | 2005-04-08 / 2026-05-30 | ~21 年 |
| `RISK_FREE_ANNUAL` | 0.022 | 无风险利率 |
| `GOLD_DIP_THRESHOLD` | 0.15 | 黄金抄底触发 |
| `GOLD_DIP_BOOST` | 2.5 | 黄金抄底倍数 |
| `HS300_DIP_THRESHOLD` | 0.25 | HS300 抄底触发 |
| `HS300_DIP_BOOST` | 1.8 | HS300 抄底倍数 |
| `HS300_PB_ENTRY` / `HS300_PE_EXIT` | 30 / 70 | AND 入场PB / 出场PE 分位 |
| `RISK_PARITY_TARGET_VOL` | 0.09 | 风险平价目标波动率 |
| `BOOTSTRAP_N_SIM` | 1000 | 蒙特卡洛次数 |

> 代码中的权威定义在 `config.py`。

## 架构参考

```
main.py → pipeline.run_full_pipeline()
allweather/
  config.py         所有常量
  data.py           加载 + 合成 30Y 国债
  fetch.py          akshare 数据拉取
  backtest.py       统一回测引擎
  strategy_b.py     backtest_b 向后兼容包装
  risk.py           逆波动率 / 分层风险平价 / 趋势过滤
  stats.py          指标 / Bootstrap / D_excess
  reports.py        控制台输出
  excel_export.py   Excel 报告
  markdown_report.py Markdown 报告
  pipeline.py       6 步编排
```

**模块依赖分层：**
- **第 0 层**: config.py, risk.py, experiment_log.py
- **第 1 层**: data.py, fetch.py, stats.py, charts.py, reports.py, excel_export.py, markdown_report.py, update_docs.py
- **第 2 层**: backtest.py, rebalance.py
- **第 3 层**: strategy_b.py
- **第 4 层(编排)**: pipeline.py
- **入口**: main.py（延迟导入）

## 外部参考
- [项目.md](项目.md) — 完整分析文档（架构深层解析、设计决策）
- Memory — `.claude/projects/C--Users-MOSS-Desktop------/memory/`
