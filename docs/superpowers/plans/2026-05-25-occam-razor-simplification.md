# 奥卡姆剃刀精简：6 策略 → 3 策略 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从 6 策略精简到 3 策略（保留 V3c / V3-B 60d / V3-B 120d），删除 strategy_a.py，移除所有 short_bond 代码，同步文档。

**Architecture:** 逐文件精简——先删 strategy_a.py（无依赖），再自底向上清理 config→data→strategy_b→portfolios→pipeline，最后更新 4 个文档文件。每步可独立验证。

**Tech Stack:** Python 3.10+, pandas, numpy, openpyxl

---

## 文件变更总览

| 操作 | 文件 |
|------|------|
| 删除 | `allweather/strategy_a.py` |
| 修改 | `allweather/config.py` |
| 修改 | `allweather/data.py` |
| 修改 | `allweather/strategy_b.py` |
| 修改 | `allweather/portfolios.py` |
| 修改 | `allweather/pipeline.py` |
| 修改 | `allweather/markdown_report.py` |
| 修改 | `README.md` |
| 修改 | `docs/index.html` |
| 修改 | `PROJECT_HISTORY.md` |

---

### Task 1: 删除 strategy_a.py

**Files:**
- Delete: `allweather/strategy_a.py`

- [ ] **Step 1: 删除文件**

```bash
rm allweather/strategy_a.py
```

- [ ] **Step 2: 验证无 import 引用残留**

```bash
grep -r "strategy_a" allweather/ --include="*.py"
```

Expected: 无输出（之前只有 pipeline.py import 它，后续 Task 会清理）

- [ ] **Step 3: 验证 risk.py 中被 strategy_a 调用的函数没有新引用**

```bash
grep -r "trend_filter\|drawdown_stop" allweather/ --include="*.py"
```

Expected: 只有 `risk.py` 自身的定义，无调用方

- [ ] **Step 4: 提交**

```bash
git add allweather/strategy_a.py
git commit -m "refactor: 删除 strategy_a.py（V3-A 移除，奥卡姆剃刀精简）"
```

---

### Task 2: 精简 config.py — 移除 ASSETS_PLAN_A 和 short_bond

**Files:**
- Modify: `allweather/config.py`

- [ ] **Step 1: 删除 ASSETS_PLAN_A 常量（第 47-51 行）**

定位 `ASSETS_PLAN_A` 定义块，删除如下 5 行：

```python
ASSETS_PLAN_A = [
    "hs300", "div_idx", "us_sp500", "credit",
    "bond_10y", "bond_30y", "short_bond",
    "gold", "nonferr", "soymeal",
]
```

- [ ] **Step 2: 删除 ETF_META["short_bond"]（第 62 行）**

删除：
```python
"short_bond": {"code": "511880", "name": "短久期债券 ETF",      "bucket": "增长↓", "role": "短久期利率债"},
```

- [ ] **Step 3: 从 BUCKETS["增长↓利率债"] 移除 short_bond（第 74 行）**

将：
```python
"增长↓利率债":    ["bond_10y", "bond_30y", "short_bond"],
```
改为：
```python
"增长↓利率债":    ["bond_10y", "bond_30y"],
```

- [ ] **Step 4: 从 BUCKET_GROUPS["增长↓"] 移除 short_bond（第 81 行）**

将：
```python
"增长↓": ["bond_10y", "bond_30y", "short_bond"],
```
改为：
```python
"增长↓": ["bond_10y", "bond_30y"],
```

- [ ] **Step 5: 验证 config.py 无语法错误**

```bash
python -c "from allweather.config import *; print('ASSETS:', ASSETS); print('BUCKETS keys:', list(BUCKETS.keys()))"
```

Expected: 打印 ASSETS（9 个）和 BUCKETS（6 个桶），无 "short_bond" 出现

- [ ] **Step 6: 提交**

```bash
git add allweather/config.py
git commit -m "refactor: config.py 移除 ASSETS_PLAN_A 和 short_bond"
```

---

### Task 3: 精简 data.py — 删除 load_panel_extended()

**Files:**
- Modify: `allweather/data.py`

- [ ] **Step 1: 删除 load_panel_extended() 函数（第 232-239 行）**

删除整个函数定义：

```python
def load_panel_extended() -> pd.DataFrame:
    """加载 10 资产面板（9 基础 + short_bond，用于方案 A/B）。"""
    panel = load_panel()
    short_bond = load_series("bond_short")
    full_idx = panel.index
    short_bond = short_bond.reindex(full_idx).ffill()
    panel["short_bond"] = short_bond
    return panel.dropna()
```

- [ ] **Step 2: 验证 load_panel() 正常工作**

```bash
python -c "from allweather.data import load_panel; p = load_panel(); print(p.columns.tolist()); print(len(p))"
```

Expected: 9 列（无 short_bond），约 2683 行（2015-2025）

- [ ] **Step 3: 验证 load_panel_extended 已无法导入**

```bash
python -c "from allweather.data import load_panel_extended" 2>&1
```

Expected: `ImportError: cannot import name 'load_panel_extended'`

- [ ] **Step 4: 提交**

```bash
git add allweather/data.py
git commit -m "refactor: data.py 删除 load_panel_extended()"
```

---

### Task 4: 精简 strategy_b.py — 移除 short_bond 处理

**Files:**
- Modify: `allweather/strategy_b.py`

- [ ] **Step 1: 删除 SHORT_BOND_FIXED 常量（第 8 行）**

删除：
```python
SHORT_BOND_FIXED = 0.05  # short_bond 固定 5%，不参与风险预算
```

- [ ] **Step 2: 简化 _compute_weights() 函数签名和实现**

将整个 `_compute_weights` 函数替换为：

```python
def _compute_weights(rets_rp, rp_buckets, window):
    """Compute full weight vector from hierarchical RP."""
    rp_w = hierarchical_rp_weights(
        rets_rp, rp_buckets, window,
        RISK_PARITY_MAX_WEIGHT, RISK_PARITY_MIN_WEIGHT,
    )
    return rp_w
```

- [ ] **Step 3: 简化 backtest_b() — 移除 has_short 相关逻辑**

将 `backtest_b` 函数中的：

```python
    cols = list(rets.columns)
    has_short = "short_bond" in cols

    rp_cols = [c for c in cols if c != "short_bond"]
    rets_rp = rets[rp_cols]
    rp_buckets = {
        k: [a for a in v if a != "short_bond"]
        for k, v in BUCKET_GROUPS.items()
    }
    rp_buckets = {k: v for k, v in rp_buckets.items() if v}
```

替换为：

```python
    cols = list(rets.columns)
    rets_rp = rets[cols]
    rp_buckets = {k: list(v) for k, v in BUCKET_GROUPS.items()}
```

并将 `_compute_weights` 的两次调用从：

```python
        initial_w = _compute_weights(
            rets_rp.iloc[:rp_window], rp_buckets, has_short, cols, rp_window)
```

改为：

```python
        initial_w = _compute_weights(
            rets_rp.iloc[:rp_window], rp_buckets, rp_window)
```

以及：

```python
            new_w = _compute_weights(window, rp_buckets, has_short, cols, rp_window)
```

改为：

```python
            new_w = _compute_weights(window, rp_buckets, rp_window)
```

- [ ] **Step 4: 验证 strategy_b.py 无语法错误**

```bash
python -c "from allweather.strategy_b import backtest_b; print('ok')"
```

Expected: `ok`

- [ ] **Step 5: 提交**

```bash
git add allweather/strategy_b.py
git commit -m "refactor: strategy_b.py 移除 short_bond 处理，纯 9 资产风险平价"
```

---

### Task 5: 精简 portfolios.py — 只保留 3 个 ★★★ 策略

**Files:**
- Modify: `allweather/portfolios.py`

- [ ] **Step 1: 删除 V3b/V3d/V3-A 的 WEIGHTS 定义**

删除 WEIGHTS dict 中的 "V3b 平衡"、"V3d 商品偏重"、"V3-A 保守" 三个条目，只保留 "V3c 多元"。

WEIGHTS 变为：

```python
WEIGHTS = {
    "V3c 多元": {
        "hs300":   0.04, "div_idx":  0.06, "us_sp500": 0.08, "credit":   0.05,
        "bond_10y":0.40, "bond_30y": 0.15,
        "gold":    0.10, "nonferr":  0.06, "soymeal":  0.06,
    },
}
```

- [ ] **Step 2: 精简 PORTFOLIO_TAGS**

删除 V3b/V3d/V3-A 条目，保留 3 个：

```python
PORTFOLIO_TAGS = {
    "V3c 多元":            {"stars": "★★★", "label": "实战派 — 固定权重，11年回测最优"},
    "V3-B 风险平价(60d)":  {"stars": "★★★", "label": "学院派 — 分层风险平价，月度调仓（战术）"},
    "V3-B 风险平价(120d)": {"stars": "★★★", "label": "学院派 — 分层风险平价，长窗口（战略）"},
}
```

- [ ] **Step 3: 删除 ASSETS_PLAN_A 导入，简化 get_weights()**

将 import 行：
```python
from .config import ASSETS, ASSETS_PLAN_A
```
改为：
```python
from .config import ASSETS
```

将 get_weights() 函数体：
```python
def get_weights():
    """返回 {方案名: pd.Series(对齐到对应资产列表顺序)}。"""
    out = {}
    for name, w in WEIGHTS.items():
        asset_list = ASSETS_PLAN_A if "V3-A" in name else ASSETS
        s = pd.Series(w).reindex(asset_list).fillna(0)
        assert abs(s.sum() - 1) < 1e-6, f"{name} 权重和={s.sum()}"
        out[name] = s
    return out
```

替换为：
```python
def get_weights():
    """返回 {方案名: pd.Series(对齐到 ASSETS 顺序)}。"""
    out = {}
    for name, w in WEIGHTS.items():
        s = pd.Series(w).reindex(ASSETS).fillna(0)
        assert abs(s.sum() - 1) < 1e-6, f"{name} 权重和={s.sum()}"
        out[name] = s
    return out
```

- [ ] **Step 4: 验证 portfolios.py 无语法错误**

```bash
python -c "from allweather.portfolios import get_weights, PORTFOLIO_TAGS; w = get_weights(); print(list(w.keys())); print(PORTFOLIO_TAGS)"
```

Expected: 只打印 `['V3c 多元']` 和 3 个 PORTFOLIO_TAGS 条目

- [ ] **Step 5: 提交**

```bash
git add allweather/portfolios.py
git commit -m "refactor: portfolios.py 精简到 1 个固定权重 + 3 个推荐标签"
```

---

### Task 6: 精简 pipeline.py — 适配 3 策略，移除 V3-A/short_bond 引用

**Files:**
- Modify: `allweather/pipeline.py`

- [ ] **Step 1: 更新 import — 删除 strategy_a 引用**

删除第 16 行：
```python
from .strategy_a import backtest_a
```

将第 7 行：
```python
from .data import load_panel_extended
```
改为：
```python
from .data import load_panel
```

- [ ] **Step 2: 简化 step_1_load_data()**

将：
```python
    panel = load_panel_extended()
    rets = panel.pct_change().dropna()
    print(f"  ok 数据期间: {panel.index.min().date()} ~ {panel.index.max().date()}")
    print(f"  ok 资产数: {panel.shape[1]}, 交易日数: {len(panel)}")
```

改为：
```python
    panel = load_panel()
    rets = panel.pct_change().dropna()
    print(f"  ok 数据期间: {panel.index.min().date()} ~ {panel.index.max().date()}")
    print(f"  ok 资产数: {panel.shape[1]}, 交易日数: {len(panel)}")
```

并将 docstring 从 `"""Step 1: 加载历史数据（含 short_bond 用于方案 A/B）。"""` 改为 `"""Step 1: 加载历史数据（9 资产）。"""`

- [ ] **Step 3: 简化 step_2_run_backtests() — 移除 V3-A 块**

删除整个 V3-A 回测块（第 55-62 行）：
```python
    # --- 方案 A: 纯固定权重（含 short_bond）---
    from .strategy_a import backtest_a
    w_a = weights.get("V3-A 保守")
    if w_a is not None:
        for tier_label, c in CASH_TIERS:
            nv, n = backtest_a(w_a, rets, cash_ratio=c)
            nv_results[("V3-A 保守", tier_label)] = nv
            n_rebal_total += n
```

并将原 V3b/V3c/V3d 循环注释从 `# --- 原 V3b / V3c / V3d 固定权重回测 ---` 改为 `# --- 固定权重回测（V3c）---`，移除 `if "V3-A" in port: continue` 判断。

将原循环：
```python
    # --- 原 V3b / V3c / V3d 固定权重回测 ---
    for port, w in weights.items():
        if "V3-A" in port:
            continue          # V3-A 在下文用 backtest_a 处理
        for tier_label, c in CASH_TIERS:
            nv, n = backtest(w, rets, cash_ratio=c)
            nv_results[(port, tier_label)] = nv
            n_rebal_total += n
```

改为：
```python
    # --- 固定权重回测（V3c）---
    for port, w in weights.items():
        for tier_label, c in CASH_TIERS:
            nv, n = backtest(w, rets, cash_ratio=c)
            nv_results[(port, tier_label)] = nv
            n_rebal_total += n
```

- [ ] **Step 4: 简化 step_4_bootstrap() — 移除 V3-A 和 short_bond 逻辑**

删除 step_4 中的 `short_bond` 过滤逻辑。将：

```python
    rp_buckets_boot = {
        k: [a for a in v if a != "short_bond"]
        for k, v in BOOT_BG.items()
    }
    rp_buckets_boot = {k: v for k, v in rp_buckets_boot.items() if v}
```

改为：
```python
    rp_buckets_boot = {k: list(v) for k, v in BOOT_BG.items()}
```

同时删除 `boot_rets` 中的 short_bond 过滤：
```python
            boot_rets = rets[[c for c in rets.columns if c != "short_bond"]]
```
改为：
```python
            boot_rets = rets
```

- [ ] **Step 5: 验证 pipeline.py 无语法错误**

```bash
python -c "from allweather.pipeline import step_1_load_data; print('ok')"
```

Expected: `ok`

- [ ] **Step 6: 提交**

```bash
git add allweather/pipeline.py
git commit -m "refactor: pipeline.py 适配 3 策略，移除 V3-A/short_bond"
```

---

### Task 7: 更新 markdown_report.py — 精简推荐和持仓表

**Files:**
- Modify: `allweather/markdown_report.py`

- [ ] **Step 1: 更新 _section_recommendation() 中的 notes（第 57-64 行）**

将 notes 字典替换为：

```python
    notes = {
        "V3c 多元": "实战派 — 固定权重+阈值再平衡，11年回测最优（Sharpe 1.26）",
        "V3-B 风险平价(60d)": "学院派（战术）— 分层风险平价，月度调仓，回撤最浅",
        "V3-B 风险平价(120d)": "学院派（战略）— 长窗口风险平价，接近桥水战略定位",
    }
```

- [ ] **Step 2: 更新 _section_recommendation() 末尾说明（第 72 行）**

将：
```python
        "> 默认主推 **V3c 多元**；其它两套是「特殊偏好」备选。",
```
改为：
```python
        "> **V3c** 和 **V3-B** 是两条不同路线的 ★★★ 推荐：前者是实战答案（指标最优），后者是方法论正统（桥水真经）。选哪个取决于你更信回测还是更信哲学。",
```

- [ ] **Step 3: 验证 markdown_report.py 无语法错误**

```bash
python -c "from allweather.markdown_report import save_markdown_report; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: 提交**

```bash
git add allweather/markdown_report.py
git commit -m "docs: markdown_report.py 推荐表精简为 3 策略，两线定位"
```

---

### Task 8: 运行完整回测验证

- [ ] **Step 1: 运行完整回测**

```bash
source .venv/Scripts/activate && python main.py
```

Expected:
- 9 个回测（3 策略 × 3 现金档）
- 无 import error，无 KeyError
- V3c 100% RP 指标：CAGR ≈ 7.45%, Sharpe ≈ 1.26, MDD ≈ -6.71%
- V3-B 60d 100% RP 指标：CAGR ≈ 7.01%, MDD ≈ -5.98%
- V3-B 120d 100% RP 指标：CAGR ≈ 6.84%, MDD ≈ -6.37%
- Excel + Markdown 报告生成成功

- [ ] **Step 2: 检查 summary.json 策略数**

```bash
python -c "import json; d = json.load(open('output/summary.json')); print(len(d), '回测'); print([k[0] for k in d.keys()])"
```

Expected: 9 回测，3 个不同策略名（各出现 3 次对应 3 档现金）

- [ ] **Step 3: 检查 nv_curves.csv 列数**

```bash
python -c "import pandas as pd; df = pd.read_csv('output/nv_curves.csv'); print(df.columns.tolist())"
```

Expected: 10 列（date + 9 条曲线 = 3 策略 × 3 档）

- [ ] **Step 4: 提交回测产物（可选）**

```bash
git add output/ && git commit -m "backtest: 奥卡姆剃刀精简后回测结果（3策略×3档=9回测）"
```

> 注意：output/ 如果在 .gitignore 中则跳过此步

---

### Task 9: 更新 README.md

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 替换策略速查表（第 76-97 行）**

将两个子表（固定权重 + 动态风险平价）合并为一个表：

```markdown
## 🎯 策略速查

| 方案 | 路线 | CAGR | 回撤 | Sharpe | 适合 |
|---|---|---|---|---|---|
| **V3c 多元** | 实战派 | 7.45% | -6.71% | 1.26 | 要最优指标，简单落地 |
| **V3-B (60d)** | 学院派 | 7.01% | -5.98% | 1.14 | 认同桥水方法论，战术灵活 |
| **V3-B (120d)** | 学院派 | 6.84% | -6.37% | 1.09 | 认同桥水方法论，战略稳定 |

> V3c 和 V3-B 是两条不同路线的 ★★★ 推荐。V3c 是回测答案（固定权重，半年+3%阈值再平衡），V3-B 是方法论正统（分层风险平价，月度调仓）。选哪个取决于你更信回测还是更信哲学。
>
> 回测期：2015-01 ~ 2025-12（~11 年）
```

- [ ] **Step 2: 更新输出文件数量**

将第 28 行表格中的：
```markdown
| `nv_curves.csv` | 18 条净值曲线（宽表，画图用）|
```
改为：
```markdown
| `nv_curves.csv` | 9 条净值曲线（宽表，画图用）|
```

将第 73 行目录树中：
```
│   ├── nv_curves.csv           9 条净值曲线
```
改为：
```
│   ├── nv_curves.csv           9 条净值曲线（3 策略 × 3 档现金）
```

（如果已经是 9 则不改）

- [ ] **Step 3: 提交**

```bash
git add README.md
git commit -m "docs: README 策略速查精简到 3 策略，增加两线定位说明"
```

---

### Task 10: 更新 docs/index.html

**Files:**
- Modify: `docs/index.html`

关键行号（基于当前文件）：
- L240-241: 介绍段落（"三套固定权重方案" + V3-A/V3-B 引用）
- L242-409: V3d 商品偏重型完整卡片
- L410-578: V3c 多元型完整卡片（保留）
- L579-745: V3b 平衡型完整卡片
- L746-753: 对比表表头（V3c | V3d | V3b）
- L754-769+: 对比表数据行
- L920-937: 推荐表（V3c / V3d / V3b 三行）
- L58: CSS `.plan-c` 定义，L50区域附近 `.plan-d` `.plan-b` 定义

- [ ] **Step 1: 删除 V3d 策略卡片（L242-409）**

删除从 `<h2 class="plan-title plan-d">方案 2: V3d 商品偏重型` 到 V3c 标题前的全部内容（含持仓表、蒙特卡洛表、事件收益表、优势列表）。

```bash
# 确认边界
sed -n '242p' docs/index.html  # 应显示: <h2 class="plan-title plan-d">方案 2: V3d...
sed -n '409p' docs/index.html  # 应显示: <p class="para">• 2025 关税冲击期...
```

删除 L242-409（共 168 行）。

- [ ] **Step 2: 删除 V3b 策略卡片（L579-745）**

删除从 `<h2 class="plan-title plan-b">方案 3: V3b 平衡型` 到对比表标题前的全部内容。

```bash
# 确认边界（删除 V3d 后行号会偏移，重新确认）
grep -n "方案 3: V3b 平衡型\|四、方案对比一表看清" docs/index.html
```

删除 V3b section 的全部行（从 `plan-title plan-b` 到 `id="ch3"` 前）。

- [ ] **Step 3: 更新介绍段落（L240-241）**

将：
```html
<p class="para">以下三套固定权重方案基于同一框架：9 资产 × 4 桶（增长↑权益、收益垫信用债、增长↓利率债、通胀↑商品+黄金）。差异在于桶内权重侧重。</p>
<p class="para">另外提供 V3-A（含 20% 短债保守配置）和 V3-B（分层风险平价月度调仓，60d/120d 双窗口）作为动态配置备选。详见 <a href="https://github.com/IdealAuror/all-weather-portfolio/blob/main/README.md">README 速查表</a>。</p>
```

改为：
```html
<p class="para">V3c 是固定权重方案（9 资产 × 4 桶），基于 11 年回测优化。另外提供 <strong>V3-B 分层风险平价</strong>（60d/120d 双窗口，月度调仓）——路线不同但同为 ★★★ 推荐。</p>
<p class="para"><strong>V3c vs V3-B 怎么选？</strong> V3c 是实战答案（Sharpe 1.26 最高，简单省心）；V3-B 是方法论正统（分层风险平价，桥水真经）。选哪个取决于你更信回测还是更信哲学。详见 <a href="https://github.com/IdealAuror/all-weather-portfolio/blob/main/README.md">README 速查表</a>。</p>
```

- [ ] **Step 4: 更新对比表表头（L750-753）**

将：
```html
<th>V3c 多元 ★★★</th>
<th>V3d 商品 ★★</th>
<th>V3b 平衡 ★★</th>
```

改为：
```html
<th>V3c 多元 ★★★</th>
<th>V3-B 风险平价(60d) ★★★</th>
<th>V3-B 风险平价(120d) ★★★</th>
```

- [ ] **Step 5: 更新对比表所有数据行**

从对比表的每个 `<tr>` 中删除 V3d 和 V3b 的 `<td>`，替换为 V3-B 60d 和 120d 的数据。

关键指标对照（100% RP 档）：
| 指标 | V3c | V3-B 60d | V3-B 120d |
|------|-----|----------|-----------|
| CAGR | 7.45% | 7.01% | 6.84% |
| 回撤 | -6.71% | -5.98% | -6.37% |
| Sharpe | 1.26 | 1.14 | 1.09 |
| 波动 | 4.16% | — | — |
| Calmar | 1.11 | — | — |

需要在对比表的每一行中替换。逐行修改：
- 哲学行：改为 "固定权重最优" | "风险平价战术" | "风险平价战略"
- 资产数行：全部 9
- CAGR行、回撤行、Sharpe行、波动行、Calmar行等

- [ ] **Step 6: 更新推荐表（L920-937）**

将三行推荐改为：
```html
<tr>
<td class="td-first">没特别判断 / 让组合自己平衡</td>
<td class="td-num">V3c 多元 ★★★</td>
<td class="td-num">Sharpe 1.26 最高、CAGR 7.45% 最高、最简单省心（默认推荐）</td>
</tr>
<tr>
<td class="td-first">认同桥水方法论 / 要动态适应</td>
<td class="td-num">V3-B 风险平价(60d) ★★★</td>
<td class="td-num">分层风险平价，月度调仓，回撤最浅 -5.98%</td>
</tr>
<tr>
<td class="td-first">认同桥水方法论 / 要战略稳定</td>
<td class="td-num">V3-B 风险平价(120d) ★★★</td>
<td class="td-num">长窗口风险平价，权重更稳定，接近桥水战略定位</td>
</tr>
```

- [ ] **Step 7: 清理未使用的 CSS 类**

确认 `.plan-d` 和 `.plan-b` CSS 类不再被使用后，可保留（不影响渲染）或删除对应 CSS 规则。

- [ ] **Step 8: 同步更新对比表中 V3-B 相关的蒙特卡洛和事件数据行**

对比表中若有蒙特卡洛 5%分位、事件收益等行，需更新为 V3-B 的实际数据。从 `output/summary.json` 获取最新值。

- [ ] **Step 9: 在浏览器中验证 HTML**

用浏览器打开 `docs/index.html`，确认：
- 策略卡片只有 V3c
- 对比表只有 V3c | V3-B 60d | V3-B 120d 三列
- 推荐表三行对应三个策略
- 新增的"怎么选"说明渲染正确
- 无 broken layout、无残留 V3d/V3b/V3-A 文本

- [ ] **Step 10: 提交**

```bash
git add docs/index.html
git commit -m "docs: index.html 精简到 3 策略（V3c + V3-B 60d/120d），新增选择指南"
```

---

### Task 11: 更新 PROJECT_HISTORY.md

**Files:**
- Modify: `PROJECT_HISTORY.md`

- [ ] **Step 1: 删除 4.2 V3b 小节（第 85-99 行）**

删除整个 "### 4.2 V3b 平衡" section（含权重表和特征说明）。

- [ ] **Step 2: 删除 4.3 V3d 小节（第 101-116 行）**

删除整个 "### 4.3 V3d 商品偏重" section。

- [ ] **Step 3: 精简 4.4 核心指标对比表（第 118-126 行）**

从 3 行数据改为 3 行（V3c + V3-B 60d + V3-B 120d），标题改为 "### 4.2 三策略核心指标对比"。

- [ ] **Step 4: 删除 4.5 V3-A 小节（第 128-148 行）**

删除整个 "### 4.5 V3-A 保守" section。

- [ ] **Step 5: 精简 4.6 V3-B 小节（第 149-163 行）**

将小节编号从 4.6 改为 4.4，删除 short_bond 相关描述（"short_bond 固定 5% 不参与风险预算"），精简为：

```markdown
### 4.4 V3-B 分层风险平价（★★★ 60d / ★★★ 120d）

无固定权重，月度动态计算。代码：`allweather/strategy_b.py`。

机制：
1. **分层风险平价**：4 个宏观桶各 25%（等权），桶内逆波动率加权
2. **双窗口版本**：60d（响应快，战术）和 120d（权重稳定，战略定位）
3. 纯 9 资产，无 short_bond

| 版本 | CAGR | MDD | Sharpe |
|------|------|-----|--------|
| V3-B 60d | 7.01% | -5.98% | 1.14 |
| V3-B 120d | 6.84% | -6.37% | 1.09 |
```

- [ ] **Step 6: 新增 5.7 决策记录**

在第 5.6 节之后新增：

```markdown
### 5.7 奥卡姆剃刀精简：6 策略 → 3 策略（2026-05-25）

**背景**：经过策略精简（5.6）后仍有 6 个策略在推荐表中。V3c 在 11 年回测中全面最优，应用奥卡姆剃刀原则审视冗余。

**决策**：只保留 ★★★ 策略。V3c（实战派，回测最优）+ V3-B 60d/120d（学院派，桥水方法论正统）。

**移除**：
- V3b 平衡：被 V3c 全面覆盖（相似结构，更差指标）
- V3d 商品偏重：回撤最深（-8.59%），无独立存在理由
- V3-A 保守：short_bond 拖累收益，全维度落后 V3c

**两条线定位**：V3c 是"照这个买就行"，V3-B 是"桥水怎么做就怎么做"。两者不互相竞争，服务于不同价值观的用户。

**影响**：回测 18→9，策略 6→3，删除 strategy_a.py，移除所有 short_bond 代码。

**相关文件**：`strategy_a.py`（删除）、`config.py`、`data.py`、`strategy_b.py`、`portfolios.py`、`pipeline.py`、`markdown_report.py`、`README.md`、`index.html`
```

- [ ] **Step 7: 更新项目结构（第 6 节）**

将第 267 行 `strategy_a.py` 条目从结构中删除：
```
│   ├── strategy_a.py           方案 A：固定权重（含 short_bond）+ 阈值再平衡
```
改为不包含 strategy_a.py 的结构。

更新 pipeline 描述（第 296 行）：
```
| 2 | `step_2_run_backtests` | 3 策略 × 3 现金档 = 9 个回测 |
```

- [ ] **Step 8: 提交**

```bash
git add PROJECT_HISTORY.md
git commit -m "docs: PROJECT_HISTORY 记录奥卡姆剃刀精简决策，移除冗余策略章节"
```

---

### Task 12: 最终验证和推送

- [ ] **Step 1: 确认所有 import 路径干净**

```bash
grep -r "strategy_a\|load_panel_extended\|ASSETS_PLAN_A\|short_bond" allweather/ --include="*.py" | grep -v "risk.py" | grep -v "__pycache__"
```

Expected: 无输出（risk.py 中的 short_bond 引用已确认只是在 BUCKET_GROUPS 重建时的过滤，需确认 pipeline.py 中不再重建含 short_bond 的 buckets）

- [ ] **Step 2: 最终完整回测**

```bash
source .venv/Scripts/activate && python main.py
```

Expected: 全部通过，9 回测，三份报告生成

- [ ] **Step 3: 推送到 GitHub**

```bash
git push
```
