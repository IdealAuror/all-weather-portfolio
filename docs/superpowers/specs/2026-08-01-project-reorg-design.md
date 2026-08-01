# 项目整理：归档移出 + 死代码清理 + 架构梳理 — 设计文档

> 日期：2026-08-01
> 状态：已确认

## 背景与目标

项目根目录混入了大量与核心策略无关的内容：一个独立的量化研究项目（tmpcheap）、聚宽历史存档、一次性实验脚本、29MB 的 Agent 工作树残留。核心包 `allweather/`（6360 行，18 模块）依赖分层已在 CLAUDE.md 定义且结构健康，无需合并重构。

**目标**（用户确认）：
1. 遗留目录移出项目归档（`桌面/全季节策略归档/2026-08-01/`）
2. 聚宽（JoinQuant）量化测试代码**全部保留**并纳入 git 跟踪
3. 只清理死代码，不合并正常工作的模块（低风险原则）
4. 更新 CLAUDE.md / 项目.md 的过时架构描述
5. 验收：`py main.py` 指标与 README 完全一致，`pytest` 全绿

## 一、归档移出

目标位置：`C:\Users\MOSS\Desktop\全季节策略归档\2026-08-01\`

| 内容 | 大小 | git 状态 | 处理方式 |
|------|------|---------|---------|
| `tmpcheap-stable-trending-quant/` | 2.0MB | 未跟踪 | 整体移动（独立项目，带自己的 .git） |
| `experiments/` | 92KB | **已跟踪** | `git rm -r` + 移动（8 个一次性脚本） |
| `_archive/cst_quant_strategy.py` | — | 已跟踪 | `git rm` + 移动 |
| `_archive/explore_improvements.py` | — | 已跟踪 | `git rm` + 移动 |
| `.claude/worktrees/` | 29MB | 已忽略 | 直接删除（agent 临时残留） |
| `.firecrawl/` `.pytest_cache/` `.streamlit/` `__pycache__` `*.egg-info` | ~1.2M | 已忽略 | 直接删除（缓存） |

**保留**：
- `experiments.jsonl`（活跃实验日志，`experiment_log.py` 写入，勿动）
- `output/`（gitignore 的活输出目录，回测自动重新生成）
- `tests/`、`portfolio_comparison/`、`streamlit_app/`

## 二、聚宽代码合并保留

`_archive/joinquant/` 内容并入 `joinquant/`，聚宽代码统一目录，`_archive/` 全部清空删除：

```
joinquant/
├── allweather_jq.py               # 完整版（1025 行，原 _archive/joinquant/）
├── allweather_jq_no_synth.py      # 无合成版
├── allweather_jq_no_synth_wti.py  # 无合成 + WTI 版
├── README.md                      # 原 _archive/joinquant/
└── comparison.md / comparison.html
```

以上全部 `git add` 纳入跟踪（此前是未跟踪的 `??` 状态，不随 push 同步；纳入后跨机器同步，避免再次出现"另一台机器不知道这些代码"的情况）。

注意：`tmpcheap-stable-trending-quant/` 内部也有 `archive/joinquant/`，那是该独立项目自己的组成部分，随 tmpcheap 整体移出（归档非删除，可找回）。

## 三、死代码清理

- `allweather/grid_search_b.py`（139 行）— 全项目唯一调用方是其自身 `__main__`，无任何模块引用。移入归档目录（非删除），保留在项目中的任何引用均为零。

## 四、架构梳理（文档层，零代码逻辑改动）

1. **CLAUDE.md「架构参考」** 更新：
   - 补上遗漏的活跃模块：`rebalance.py`、`charts.py`、`update_docs.py`、`experiment_log.py`、`types.py`
   - 移除 `grid_search_b.py`（已归档）
   - 新增 `joinquant/` 说明（聚宽平台测试代码，非核心流水线）
   - `streamlit_app/` 标注（Web 再平衡面板）
2. **项目.md** 依赖图同步更新（缺 rebalance/charts/update_docs 同样过时）。

## 五、验收标准

1. `py main.py` 全量回测无报错，指标与 README 一致（V3-B 保守 Sharpe 1.81、V3c MDD -6.28%、V3-B RP CAGR 8.95%）
2. `pytest tests/` 全绿
3. `git status` 干净：无 `??` 大目录，只剩 joinquant 等预期文件
4. 零代码逻辑改动 — 回测可复现性不受影响

## 风险与回滚

- **风险**：极低。不触碰任何回测逻辑，仅移动/删除文件 + 文档更新。
- **回滚**：归档目录保留原始文件；git 历史保留被 `git rm` 文件的完整历史，`git checkout <commit> -- <path>` 可随时恢复。
