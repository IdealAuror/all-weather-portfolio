# 项目整理实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将项目根目录的遗留目录归档移出、聚宽代码合并纳入 git、清理死代码，并更新过时的架构文档，全程零代码逻辑改动。

**Architecture:** 纯文件操作 + 文档更新。核心 `allweather/` 包（18 模块）结构健康，不做合并重构。归档目标 `C:\Users\MOSS\Desktop\全季节策略归档\2026-08-01\`（归档非删除，可随时找回）。

**Tech Stack:** bash（git bash / Windows）、git、python（仅用于验证回测）

**Spec:** `docs/superpowers/specs/2026-08-01-project-reorg-design.md`

## Global Constraints

- 零代码逻辑改动：`allweather/*.py` 中除 `grid_search_b.py` 外的文件一律不编辑
- `experiments.jsonl`、`output/`、`tests/`、`portfolio_comparison/`、`streamlit_app/` 一律保留不动
- 归档 = 移动文件到 `C:\Users\MOSS\Desktop\全季节策略归档\2026-08-01\`，绝不删除有 git 历史或被引用的代码（缓存除外）
- 聚宽代码（joinquant/）必须保留在项目内并纳入 git
- 所有 commit 直接推 main（单人项目规则）
- 每次文件移动后必须验证，最终验收跑 `py main.py` 全量回测

---

### Task 1: 创建归档目录并移出非聚宽遗留内容

**Files:**
- Move: `tmpcheap-stable-trending-quant/` → 归档
- Move: `experiments/` → 归档
- Move: `_archive/cst_quant_strategy.py`、`_archive/explore_improvements.py` → 归档
- Delete: `.claude/worktrees/`、`.firecrawl/`、`.pytest_cache/`、`allweather_cn.egg-info/`、各 `__pycache__/`

**Interfaces:**
- Consumes: 无
- Produces: 归档目录结构、干净的 `git status`（无 `??` 大目录）

- [ ] **Step 1: 创建归档目录**

```bash
mkdir -p "/c/Users/MOSS/Desktop/全季节策略归档/2026-08-01"
```

- [ ] **Step 2: 检查 .streamlit/ 内容（条件保留）**

```bash
ls -la .streamlit/
```
若包含 `config.toml`（用户手动配置）→ 保留 `.streamlit/`；若为空或只有缓存文件 → 随缓存删除。

- [ ] **Step 3: git rm 跟踪的实验脚本 + 移动**

```bash
git rm -r experiments/
mv experiments "/c/Users/MOSS/Desktop/全季节策略归档/2026-08-01/"
```

- [ ] **Step 4: git rm 并移出 _archive 非聚宽文件**

```bash
git rm _archive/cst_quant_strategy.py _archive/explore_improvements.py
mv _archive/cst_quant_strategy.py _archive/explore_improvements.py "/c/Users/MOSS/Desktop/全季节策略归档/2026-08-01/"
```

- [ ] **Step 5: 移动 tmpcheap 独立项目**

```bash
mv tmpcheap-stable-trending-quant "/c/Users/MOSS/Desktop/全季节策略归档/2026-08-01/"
```

- [ ] **Step 6: 删除临时残留与缓存**

```bash
rm -rf .claude/worktrees .firecrawl .pytest_cache allweather_cn.egg-info
find . -name "__pycache__" -not -path "./.git/*" -type d -exec rm -rf {} +
```
（若 Step 2 判定 `.streamlit/` 为缓存则追加 `rm -rf .streamlit`）

- [ ] **Step 7: 验证**

```bash
git status -sb
ls "/c/Users/MOSS/Desktop/全季节策略归档/2026-08-01/"
```
预期：`git status` 无 `?? tmpcheap` / `?? _archive` 大目录、无 `D experiments/` 残留（已被 git rm 暂存）；归档目录含 `experiments/`、`tmpcheap-stable-trending-quant/`、两个 py。

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "chore: 归档移出遗留目录 — tmpcheap独立项目/experiments实验脚本/_archive非聚宽部分+清理缓存"
git push
```

---

### Task 2: 聚宽代码合并入 joinquant/ 并纳入 git

**Files:**
- Move: `_archive/joinquant/*` → `joinquant/`
- Delete: `_archive/`（空目录）
- Add: `joinquant/` 全部文件

**Interfaces:**
- Consumes: Task 1 已 git rm 的 `_archive/cst_quant_strategy.py`、`explore_improvements.py`（_archive 现仅剩 joinquant/）
- Produces: `joinquant/` 含 6 个文件：`allweather_jq.py`、`allweather_jq_no_synth.py`、`allweather_jq_no_synth_wti.py`、`README.md`、`comparison.md`、`comparison.html`

- [ ] **Step 1: 合并移动**

```bash
mv _archive/joinquant/* joinquant/
```

- [ ] **Step 2: 删除空 _archive**

```bash
rmdir _archive 2>/dev/null || ls _archive   # 若仍有残留文件先列出再处理
```

- [ ] **Step 3: 验证文件清单**

```bash
ls -la joinquant/ && git status -sb
```
预期：joinquant/ 恰好 6 个文件；git status 无 `?? _archive`。

- [ ] **Step 4: 纳入 git 并提交**

```bash
git add joinquant/
git commit -m "feat: 聚宽量化测试代码纳入版本控制 — 完整版/no_synth/WTI三版本+对比文档合并到 joinquant/"
git push
```

---

### Task 3: 死代码 grid_search_b.py 移入归档

**Files:**
- Move: `allweather/grid_search_b.py` → 归档

**Interfaces:**
- Consumes: Task 1 的归档目录
- Produces: `allweather/` 无 grid_search_b；归档内 `grid_search_b.py`

- [ ] **Step 1: 确认无引用（已核实，复核一遍）**

```bash
grep -rn "grid_search" --include="*.py" . | grep -v __pycache__
```
预期：仅 `allweather/grid_search_b.py` 自身（含 `__main__` 调用），无其他引用。

- [ ] **Step 2: git rm + 移动**

```bash
git rm allweather/grid_search_b.py
mv allweather/grid_search_b.py "/c/Users/MOSS/Desktop/全季节策略归档/2026-08-01/"
```

- [ ] **Step 3: 验证 + 提交**

```bash
python -c "import allweather" && echo "包导入正常"
git commit -m "chore: 移除死代码 grid_search_b — 无任何模块引用，移入归档"
git push
```

---

### Task 4: 更新 CLAUDE.md 架构参考

**Files:**
- Modify: `CLAUDE.md`（仅「架构参考」小节）

**Interfaces:**
- Consumes: Task 1-3 完成后的真实模块清单
- Produces: CLAUDE.md 架构参考与实际模块一致

- [ ] **Step 1: 替换「架构参考」代码块**

当前内容（CLAUDE.md 中 `## 架构参考` 段）：
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
替换为（补 5 个缺失活跃模块、去 grid_search_b）：
```
main.py → pipeline.run_full_pipeline()
allweather/
  config.py         所有常量
  types.py          PerfMetrics/Step3Metrics 等共享类型
  experiment_log.py 实验日志（experiments.jsonl）
  data.py           加载 + 合成 30Y 国债
  fetch.py          akshare 数据拉取
  backtest.py       统一回测引擎
  strategy_b.py     backtest_b 向后兼容包装
  risk.py           逆波动率 / 分层风险平价 / 趋势过滤
  stats.py          指标 / Bootstrap / D_excess
  reports.py        控制台输出
  charts.py         8 张 matplotlib 图表
  excel_export.py   Excel 报告
  markdown_report.py Markdown 报告
  update_docs.py    README/CLAUDE.md/docs 同步
  rebalance.py      实盘再平衡（streamlit_app 调用）
  pipeline.py       6 步编排
streamlit_app/     Web 再平衡面板（app.py 主程序 + run.py 启动器）
joinquant/         聚宽平台量化测试代码（独立于核心流水线）
portfolio_comparison/  多策略对比工具
```

- [ ] **Step 2: 同步更新「模块依赖分层」列表**

当前：第 0 层 config.py/risk.py/experiment_log.py；第 1 层 data/fetch/stats/charts/reports/excel_export/markdown_report/update_docs；第 2 层 backtest/rebalance；第 3 层 strategy_b；第 4 层 pipeline。
需更新：第 1 层加入 `types.py`（被 stats/pipeline 依赖），其余保持不变。

- [ ] **Step 3: 验证 + 提交**

```bash
grep -n "grid_search\|types.py\|joinquant" CLAUDE.md | head
git commit -m "docs: CLAUDE.md 架构参考补全 — rebalance/charts/update_docs/experiment_log/types + joinquant 标注"
git push
```

---

### Task 5: 更新项目.md 依赖图

**Files:**
- Modify: `项目.md`（仅「一、代码架构总览」的模块依赖小节）

**Interfaces:**
- Consumes: Task 4 后的真实模块清单
- Produces: 项目.md 与 CLAUDE.md 架构描述一致

- [ ] **Step 1: 更新模块依赖代码块**

当前（项目.md「### 模块依赖」）：
```
main.py
 └─ pipeline.py (编排)
    ├─ data.py         数据加载 + 30Y 国债合成
    ├─ backtest.py     统一回测引擎
    ├─ strategy_b.py   backtest_b → backtest() 包装
    ├─ risk.py         逆波动率/HRP/趋势过滤/抄底
    ├─ stats.py        指标/Bootstrap/D_excess
    ├─ reports.py      控制台输出
    ├─ charts.py       8 张 matplotlib 图表
    ├─ excel_export.py openpyxl 多 sheet 报告
    ├─ markdown_report.py Markdown 报告
    ├─ fetch.py        akshare 数据拉取
    └─ update_docs.py  GitHub Pages 同步
```
替换为（补 rebalance、types、experiment_log，去 grid_search_b 残留提及）：
```
main.py
 └─ pipeline.py (编排)
    ├─ data.py         数据加载 + 合成 30Y 国债
    ├─ backtest.py     统一回测引擎
    ├─ strategy_b.py   backtest_b → backtest() 包装
    ├─ risk.py         逆波动率/HRP/趋势过滤/抄底
    ├─ stats.py        指标/Bootstrap/D_excess
    ├─ types.py        PerfMetrics 等共享类型
    ├─ reports.py      控制台输出
    ├─ charts.py       8 张 matplotlib 图表
    ├─ excel_export.py openpyxl 多 sheet 报告
    ├─ markdown_report.py Markdown 报告
    ├─ fetch.py        akshare 数据拉取
    ├─ update_docs.py  GitHub Pages 同步
    ├─ experiment_log.py 实验日志
    └─ rebalance.py    实盘再平衡（streamlit_app 调用）
```

- [ ] **Step 2: 验证 + 提交**

```bash
grep -c "rebalance.py\|types.py" 项目.md
git commit -m "docs: 项目.md 依赖图补全 rebalance/types/experiment_log"
git push
```

---

### Task 6: 全量验证（验收）

**Files:**
- 验证：`py main.py`、`pytest tests/`、`git status`

**Interfaces:**
- Consumes: Task 1-5 全部完成
- Produces: 验收结论（通过与设计文档「五、验收标准」逐条对照）

- [ ] **Step 1: 回测全量验证**

```bash
py main.py
```
预期：无报错；指标与 README 一致（V3-B 保守 Sharpe 1.81、V3c MDD -6.28%、V3-B RP CAGR 8.95%）。若因远端 WTI 提交后重跑导致微调（如数据更新），记录新指标并确认无异常跳变。

- [ ] **Step 2: 单元测试**

```bash
python -m pytest tests/ -v
```
预期：全部 PASS（test_backtest.py、test_risk.py、conftest.py）。

- [ ] **Step 3: 最终 git 状态确认**

```bash
git status -sb
git log --oneline -8
```
预期：工作区干净（无意外 `??`）；提交序列为 Task 1-5 的 5 个 commit。

- [ ] **Step 4: 收尾提交（若 Step 1 有数据/文档更新）**

```bash
git add -A && git commit -m "chore: 整理后全量回测重跑" && git push
```

- [ ] **Step 5: 归档目录最终确认**

```bash
ls -la "/c/Users/MOSS/Desktop/全季节策略归档/2026-08-01/"
```
预期：含 `experiments/`、`tmpcheap-stable-trending-quant/`、`grid_search_b.py`、`cst_quant_strategy.py`、`explore_improvements.py`。
