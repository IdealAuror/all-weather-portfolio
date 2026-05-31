# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## 策略优化闭环

所有策略改动遵循此流程，不跳步：

```
问题定义 → 假设 → 设计 → 验证 → 稳健性检验 → 决策 → 实施
   ↑                                                            │
   └────────────────────────────────────────────────────────────┘
```

**1. 问题定义** — 先问"哪里不满意？"，必须是可量化的缺陷（具体时间、幅度、原因）。
  - 好："2013年 MDD -10.34%，因为 gold/nonferr/hs300 同时暴跌"
  - 差："感觉 Sharpe 不够高"

**2. 假设** — 因果陈述，不是相关性猜测。必须可证伪。
  - 好："SP500 跌破 SMA120 意味着中期趋势转熊，清仓转信用债可避免主跌段"
  - 差："加个均线试试"

**3. 设计** — 参数选择 + 逻辑边界 + 和已有机制的交互效应。
  - 参数用网格搜索，窗口取整数（20/60/120），报告敏感度
  - 明确进场/出场条件，确认与其他滤波器是否冲突

**4. 验证** — 单变量对比（基准 vs 实验），锁定其余参数。
  - 必须检查：CAGR/波动/MDD/Sharpe/Calmar、最差年份、负收益年数、事件期收益、4 宏观情景
  - 验收：目标改善 + 非目标不恶化 + 最差年份不倒退

**5. 稳健性检验** — 确认不是过拟合。
  - 参数敏感度（±50% 窗口）
  - D_excess 尾部风险诊断
  - 80/20 检验：改善幅度 vs 复杂度代价
  - 过拟合风险：是否有经济学逻辑支撑？

**6. 决策** — 二选一，不存在"再看看"。
  - 通过 → 实施（下一步）
  - 否决 → 写 memory 记录原因 + 数据，防止重复尝试

**7. 实施** — 按 checklist 执行（见下节），不跳步。

## 前置原则（Sperandeo 三层结构）

按优先级排序，不可颠倒：

**第一层：保障资本。** 任何改动前先考量风险。对应实践：
- D_excess 尾部风险诊断 — 每次验证必须跑，D << 0 直接否决
- 墨菲定律 — 每个新信号必须有 fallback（数据断了怎么办？）
- 止损纪律 — 趋势过滤的本质是"迅速认赔"，不在下跌趋势中死扛

**第二层：一致性的获利能力。** 建立可重复的方法论，而非依赖运气。对应实践：
- 奥卡姆剃刀 — 从最简方案开始。数据证伪才加复杂度
- 80/20 检验 — CAGR +0.3pp 或 MDD -1pp 以上才值得
- 休谟因果 — 任何新机制必须有经济学逻辑支撑，不能仅是回测好看
- 最小描述长度 — 参数响应面是平的 → 砍掉该参数

**第三层：追求卓越的报酬。** 仅在前两层满足后，以获利部分承担更高风险。对应实践：
- HS300 AND 抄底 — 只在极端便宜时适度加仓（1.8x，非全仓押注）
- 方案 C 的教训 — "不可摊平亏损"，补仓 = 在亏损头寸上加码

## 实施 Checklist

改任何参数/资产/逻辑，按顺序执行：

| # | 步骤 | 内容 |
|---|------|------|
| 1 | 改代码 | `config.py`(常量) → `pipeline.py`(调用) → `strategy_b.py`/`backtest.py`(引擎) |
| 2 | 全量回测 | `py main.py`，确认无报错并记录指标 |
| 3 | 更新文档 | `BACKTEST_RESULTS.md`、`CLAUDE.md`、`docs/index.html`、`README.md`（`output/` 自动生成） |
| 4 | 更新 Memory | 有新结论或推翻旧结论时才写，不是每次都改 |
| 5 | 提交 | `git add -A && git commit -m "..." && git push` |

**最容易漏**：README.md 的策略速查表和参数表、docs/index.html 里的年度/事件/Bootstrap 表。

## Git 规则

- 单人项目，直接推 main。`git add -A && git commit -m "..." && git push`
- Commit message 禁止 Co-Authored-By 署名
- 大改动可开 feature 分支，最终合 main

## 模型选择

日常分析用当前模型（Flash）。以下场景**必须**用 Agent + `model: "opus"` 启动子任务，子任务完成后将结论带回主会话：

- **复杂策略分析** — 多变量对比、参数响应面解读、敏感度网格的统计推断
- **统计诊断** — D_excess 尾部风险分析、Bootstrap 分布解读、过拟合检验
- **回测异常排查** — 归因分析、事件期解剖、多因子分离
- **新机制设计** — 优化闭环中"问题定义→假设→设计"前三个阶段

简单任务（改常量、更新文档、常规 commit）不走 Agent，直接在当前会话处理。

## 项目信息

Bridgewater All Weather × 中国 A 股 ETF 回测研究。输出：控制台 + `output/report.xlsx` + `output/report.md` + `docs/index.html` (GitHub Pages)。

### 命令

```bash
py main.py                         # 全量回测
py main.py --no-excel              # 跳过 Excel
py main.py --no-markdown           # 跳过 Markdown
py main.py --fetch                 # 拉数据 + 回测
py main.py --fetch-only            # 仅拉数据
py main.py --force-fetch           # 强制重拉
python -m allweather.rebalance              # 实盘再平衡（三策略对比 + 信号仪表盘）
python -m allweather.rebalance --strat V3c  # 只看 V3c 详情
python -m allweather.rebalance --signals    # 只看当前市场信号状态
```

CI：`.github/workflows/backtest.yml` 跑 `py main.py`，检查 Sharpe/MDD 边界。

### 架构

```
main.py → pipeline.run_full_pipeline()
allweather/
  config.py         所有常量
  data.py           加载 + 合成 30Y 国债
  fetch.py          通过 akshare 拉数据
  backtest.py       V3c 引擎
  strategy_b.py     V3-B 引擎
  risk.py           逆波动率 / 分层风险平价 / 趋势过滤（部分仅库函数）
  stats.py          指标 / Bootstrap / D_excess
  reports.py        控制台输出
  excel_export.py   Excel 报告
  markdown_report.py Markdown 报告
  pipeline.py       6 步编排
```

### 6 步流水线

1. 加载 8 资产面板 → 2. 跑 3 策略 × 3 现金档 = 9 回测（+3 动态现金 = 12）→ 3. 算衍生指标 + D_excess 显著性 → 4. Block Bootstrap (1000×5yr, 21d block) → 5. 打印控制台 → 6. 保存 CSV/JSON/Excel/Markdown/图表

### 三策略

| 策略 | 引擎 | 核心逻辑 | 资产数 | 特点 |
|------|------|----------|--------|------|
| V3c 多元 | `backtest.py::backtest_iv` | 逆波动率 60d (max 0.30) + nonferr 75d + HS300 AND抄底 | 6 | 最简，每月调仓 |
| V3-B 风险平价(20d) | `strategy_b.py::backtest_b` | 4 桶等权 HRP + nonferr 75d + gold 75d + sp500 120d + Gold dip + HS300 AND抄底 | 6 (无 bond_10y) | CAGR 最高，三重风控 |
| V3-B 保守增强(20d) | `strategy_b.py::backtest_b` | 逆波动率 20d (max 0.25) + nonferr 75d + HS300 AND抄底 | 7 (含 bond_10y) | 回撤最低，Sharpe 最高 |

× 3 现金档：100% RP / 85% RP / 70% RP。div_idx 和 soymeal 已于 2026-05-27 移除。
wti（原油 501018）已集成数据管道和引擎，因 QDII 限购暂不可执行。

### 资产与桶

| 桶 | 资产 | V3c | V3-B RP | V3-B Con |
|----|------|:---:|:-------:|:--------:|
| 增长↑ | hs300, us_sp500 | ✓ | ✓ | ✓ |
| 收益垫 | credit | ✓ | ✓ | ✓ |
| 增长↓10Y | bond_10y | — | — | ✓ |
| 增长↓30Y | bond_30y | ✓ | ✓ | ✓ |
| 通胀↑ | gold, nonferr | ✓ | ✓ | ✓ |
| 通胀↑备选 | ~~wti~~ *(QDII限购)* | — | — | — |

V3-B RP 去掉了 bond_10y：CAGR +1.43pp，Sharpe 仅 -0.02。

### 关键设计决策

- **30Y 国债合成** (`data.py::synthesize_bond_30y`)：三阶段 — 久期乘数法(05-20) → 利差法(20-24) → 真实 ETF(24+)
- **Sharpe 修正**：`(CAGR - 2.2% risk-free) / vol`，原始版保留为 `sharpe_raw`
- **V3-B Bootstrap 代理**：动态权重用最近窗口固定权重作近似

### 关键常量

| 常量 | 值 | 说明 |
|------|-----|------|
| `BACKTEST_START/END` | 2005-04-08 / 2026-04-30 | ~21 年 |
| `RISK_FREE_ANNUAL` | 0.022 | 无风险利率 |
| `RISK_PARITY_WINDOW` | 20 | V3-B 回看窗口（交易日） |
| `RISK_PARITY_MAX_WEIGHT` | 0.20 | 单资产上限 |
| `RISK_PARITY_MIN_WEIGHT` | 0.02 | 单资产下限 |
| `GOLD_DIP_THRESHOLD` | 0.15 | 黄金抄底触发 |
| `GOLD_DIP_BOOST` | 2.5 | 黄金抄底倍数 |
| `HS300_DIP_THRESHOLD` | 0.25 | HS300 抄底触发 |
| `HS300_DIP_BOOST` | 1.8 | HS300 抄底倍数 |
| `HS300_PB_ENTRY` / `HS300_PE_EXIT` | 30 / 70 | AND 逻辑 入场PB / 出场PE 分位阈值 |
| `SP500_TREND_WINDOW` | 120 | SP500 SMA 回看 |
| `WTI_TREND_WINDOW` | 75 | 原油 SMA 回看（同 nonferr） |
| `BOOTSTRAP_N_SIM` | 1000 | 蒙特卡洛次数 |
| `BOOTSTRAP_HORIZON_DAYS` | 1260 | 5 年 |
| `BOOTSTRAP_BLOCK_DAYS` | 21 | ~1 个月块 |