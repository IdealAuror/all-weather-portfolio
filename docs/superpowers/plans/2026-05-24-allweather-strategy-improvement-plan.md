# 全天候策略优化 · 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 7 个核心问题 + 实现两个改进方案（A:轻量风控 / B:真风险平价），回测对比选最优

**Architecture:** 分三层 —— 基础修复层（改动 `config.py`/`stats.py`/`data.py`/`fetch.py`）、风控模块层（新增 `risk.py`）、策略实现层（新增 `strategy_a.py`/`strategy_b.py`，修改 `pipeline.py`/`reports.py`）。新代码放进已有 `allweather/` 包，遵循现有单一导出风格。

**Tech Stack:** Python 3.10+, numpy, pandas, openpyxl

---

### Task 1: 更新常量配置

**Files:**
- Modify: `allweather/config.py`

- [ ] **Step 1: 加新配置项**

在 `allweather/config.py` 末尾追加以下配置：

```python
# === 风险调整常量 ===
RISK_FREE_ANNUAL = 0.022         # 无风险利率年化（货币基金 2.2%），用于 Sharpe 修正

# === 方案 A 常量 ===
TREND_LOOKBACK_MONTHS = 12       # 趋势过滤回顾窗口（月）
DRAWDOWN_STOP = 0.08             # 回撤止损触发线
DRAWDOWN_RECOVER = 0.04          # 回撤恢复线
DRAWDOWN_TARGET_CAP = 0.50       # 回撤止损时目标仓位比例

# === 方案 B 常量 ===
RISK_PARITY_WINDOW = 60          # 逆波动率窗口（交易日）
RISK_PARITY_MAX_WEIGHT = 0.25    # 单资产权重上限
RISK_PARITY_MIN_WEIGHT = 0.02    # 单资产权重下限
CORR_BREAKER_THRESHOLD = 0.30    # 相关性断路器触发阈值
CORR_BREAKER_RECOVER = 0.20      # 相关性恢复阈值
CORR_BREAKER_CAP = 0.70          # 相关熔断时仓位上限
VOL_TARGET = 0.06                # 年化目标波动率
```

- [ ] **Step 2: 在现有 `ASSETS` 列表后加 `ASSETS_PLAN_A`**

```python
ASSETS_PLAN_A = [
    "hs300", "div_idx", "us_sp500", "credit",
    "bond_10y", "bond_30y", "short_bond",
    "gold", "nonferr", "soymeal",
]
```

- [ ] **Step 3: 在 `ETF_META` 里加 `short_bond` 条目**

```python
"short_bond": {"code": "511880", "name": "短久期债券 ETF", "bucket": "增长↓", "role": "短久期利率债"},
```

- [ ] **Step 4: 在 `BUCKETS` 里更新利率债桶，在 `BUCKET_GROUPS` 里加 `short_bond`**

```python
# BUCKETS 里的 "增长↓利率债": ["bond_10y", "bond_30y", "short_bond"],
# BUCKET_GROUPS 里的 "增长↓": ["bond_10y", "bond_30y", "short_bond"],
```

- [ ] **Step 5: Commit**

```bash
git add allweather/config.py
git commit -m "config: 加风控常量、short_bond 元信息、修正 Sharpe 所需 rf 年化率"
```

---

### Task 2: 修正 Sharpe 计算

**Files:**
- Modify: `allweather/stats.py:19`

- [ ] **Step 1: 修改 `perf_metrics` 函数**

将第 19 行：
```python
sharpe = cagr / vol if vol > 0 else float("nan")
```

替换为：
```python
from .config import RISK_FREE_ANNUAL
rf = RISK_FREE_ANNUAL
sharpe = (cagr - rf) / vol if vol > 0 else float("nan")
```

- [ ] **Step 2: 同时加 `sharpe_raw`（不减 rf 版本）保留兼容**

在返回 dict 中加一行：
```python
"sharpe_raw": cagr / vol if vol > 0 else float("nan"),
```

- [ ] **Step 3: 更新控制台/Excel/Markdown 报告以显示修正 Sharpe 为主，raw Sharpe 备用**

`reports.py::print_perf_table` 表头中 `Sharpe` 列保持，但值来自修正后的 `sharpe`。在 Excel 报告 `_sheet_perf` 中加一列 `Sharpe(不减rf)` 展示 `sharpe_raw`。

- [ ] **Step 4: Commit**

```bash
git add allweather/stats.py allweather/reports.py allweather/excel_export.py
git commit -m "fix: Sharpe 改为 (cagr-rf)/vol，保留 sharpe_raw 列兼容"
```

---

### Task 3: 改进 30Y 国债合成方法

**Files:**
- Modify: `allweather/data.py:17-25`
- Modify: `allweather/fetch.py` (加收益率曲线拉取)

**背景**：`cgb_yields.csv` 为空。需要尝试从 akshare 拉取中债收益率曲线数据，若拉不到则回退到当前的 ×3.0 方案但加明确文档警告。

- [ ] **Step 1: 在 `fetch.py` 中加收益率曲线拉取函数**

```python
def fetch_cgb_yields():
    """尝试拉取中债国债收益率曲线。失败返回 None。"""
    try:
        import akshare as ak
        df = ak.bond_china_yield(start_date="20150101", end_date="20251231")
        if df is None or df.empty:
            return None
        df = df.rename(columns={
            "曲线名称": "curve", "日期": "date",
            "10年": "y10", "30年": "y30",
        })
        # keep only 国债收益率 curve
        if "curve" in df.columns:
            df = df[df["curve"].str.contains("国债", na=False)]
        return df
    except Exception:
        return None
```

如果拉取成功，写入 `data/cgb_yields.csv`。

- [ ] **Step 2: 修改 `synthesize_bond_30y` 函数**

```python
def synthesize_bond_30y(s_10y: pd.Series, s_30y_etf: pd.Series) -> pd.Series:
    """合成 30Y 国债序列。
    
    优先用中债收益率曲线利差反推；数据不足时回退到久期放大系数 ×3.0。
    """
    yields_path = DATA_DIR / "cgb_yields.csv"
    if yields_path.exists():
        ydf = pd.read_csv(yields_path, parse_dates=["date"])
        ydf = ydf.set_index("date").sort_index()
        if "y10" in ydf.columns and "y30" in ydf.columns:
            # 计算 10Y-30Y 利差日变动，叠加到 10Y ETF 收益上
            spreads = ydf["y30"] - ydf["y10"]
            spread_chg = spreads.diff() / 100  # bp → 百分比
            cb10_ret = s_10y.pct_change().dropna()
            common_idx = cb10_ret.index.intersection(spread_chg.index)
            # 30Y_return ≈ 10Y_return + duration_adj × spread_change
            # 30Y 久期约 17-20 年，用 18 年近似
            dur_30y = 18.0
            synth_ret = cb10_ret.loc[common_idx] - dur_30y * spread_chg.loc[common_idx]
            synth = (1 + synth_ret).cumprod()
            # 与真实 ETF 拼接
            etf_start = s_30y_etf.index.min()
            synth_part = synth[synth.index < etf_start]
            if len(synth_part) > 0:
                real_norm = s_30y_etf / s_30y_etf.iloc[0] * synth_part.iloc[-1]
                return pd.concat([synth_part, real_norm[real_norm.index >= etf_start]]).sort_index()
    # fallback：久期放大
    cb10_ret = s_10y.pct_change().dropna()
    synth = (1 + cb10_ret * 3.0).cumprod()
    etf_start = s_30y_etf.index.min()
    synth_part = synth[synth.index < etf_start]
    real_norm = s_30y_etf / s_30y_etf.iloc[0] * synth_part.iloc[-1]
    return pd.concat([synth_part, real_norm[real_norm.index >= etf_start]]).sort_index()
```

- [ ] **Step 3: 在 `data.py` 中新增 `load_panel_extended` 函数**

```python
def load_panel_extended() -> pd.DataFrame:
    """加载 11 资产面板（9 原始 + short_bond，用于方案 A/B）。"""
    panel = load_panel()
    raw = load_series("bond_short")
    panel["short_bond"] = raw.reindex(panel.index).ffill()
    panel = panel.dropna()
    return panel
```

- [ ] **Step 4: 修改 `load_panel` 内部，支持加载 `short_bond` 列**（供现有逻辑使用）

在 `raw` 加载 dict 中加 `"short_bond": load_series("bond_short")`，panel 中加 `"short_bond": raw["short_bond"]`。

- [ ] **Step 5: 更新 `check_data_complete` required 列表加 `bond_short`**

```python
required = [..., "bond_short"]
```

- [ ] **Step 6: Commit**

```bash
git add allweather/data.py allweather/fetch.py
git commit -m "fix: 改进 30Y 合成，加 short_bond 加载 + load_panel_extended"
```

---

### Task 4: 创建风控模块

**Files:**
- Create: `allweather/risk.py`

- [ ] **Step 1: 写趋势过滤函数**

```python
"""风控模块 —— 趋势过滤、回撤止损、波动率目标、逆波动率加权。"""
import numpy as np
import pandas as pd


def trend_filter(returns_12m: pd.Series) -> bool:
    """过去 12 个月总收益为负 → True（触发避险）。"""
    if len(returns_12m) < 20:
        return False
    cum = (1 + returns_12m).prod() - 1
    return cum < 0
```

- [ ] **Step 2: 写回撤止损函数**

```python
def drawdown_stop(nv: pd.Series, threshold: float = 0.08) -> bool:
    """当前回撤超过 threshold → True（触发降仓）。"""
    dd = (nv / nv.cummax()) - 1
    return dd.iloc[-1] < -threshold
```

- [ ] **Step 3: 写波动率缩放函数**

```python
def vol_target_scale(returns: pd.DataFrame, target_vol: float = 0.06,
                     window: int = 60) -> float:
    """返回仓位缩放系数：实际波动 vs 目标波动。上限 1.0（不加杠杆）。"""
    recent = returns.tail(window)
    if len(recent) < 20:
        return 1.0
    ann_vol = recent.std().mean() * np.sqrt(252)  # 各资产平均波动
    if ann_vol < 0.001:
        return 1.0
    scale = target_vol / ann_vol
    return min(scale, 1.0)
```

- [ ] **Step 4: 写相关性断路器**

```python
def correlation_breaker(returns: pd.DataFrame, threshold: float = 0.30,
                        window: int = 60) -> bool:
    """平均两两相关性 > threshold → True（触发降仓）。"""
    recent = returns.tail(window)
    if len(recent) < 20:
        return False
    corr = recent.corr().values
    n = corr.shape[0]
    # 上三角均值（不含对角线）
    upper = corr[np.triu_indices(n, k=1)]
    return upper.mean() > threshold
```

- [ ] **Step 5: 写逆波动率加权函数**

```python
def inverse_vol_weights(returns: pd.DataFrame, window: int = 60,
                        max_w: float = 0.25, min_w: float = 0.02) -> pd.Series:
    """用过去 window 日逆波动率算权重，再截断到 [min_w, max_w]。"""
    recent = returns.tail(window)
    vols = recent.std() * np.sqrt(252)
    inv_vol = 1 / vols.replace(0, np.nan)
    raw = inv_vol / inv_vol.sum()
    # 截断
    capped = raw.clip(lower=min_w, upper=max_w)
    return capped / capped.sum()
```

- [ ] **Step 6: Commit**

```bash
git add allweather/risk.py allweather/__init__.py
git commit -m "feat: 新风控模块 —— 趋势过滤、回撤止损、vol targeting、相关性断路器、逆波动率加权"
```

---

### Task 5: 实现方案 A（轻量风控层）

**Files:**
- Create: `allweather/strategy_a.py`
- Modify: `allweather/portfolios.py`

- [ ] **Step 1: 在 `portfolios.py` 中加方案 A 权重**

```python
"V3-A 风控": {
    "hs300":   0.04, "div_idx":  0.06, "us_sp500": 0.08, "credit":   0.05,
    "bond_10y":0.25, "bond_30y": 0.10, "short_bond": 0.20,
    "gold":    0.10, "nonferr":  0.06, "soymeal":  0.06,
},
```

- [ ] **Step 2: 写 `strategy_a.py`**

```python
"""方案 A：固定权重 + 三层风控（久期调整 + 趋势过滤 + 回撤止损）。"""
import pandas as pd
import numpy as np
from .config import (
    REBAL_FREQ, REBAL_THRESHOLD, RISK_FREE_RATE,
    TREND_LOOKBACK_MONTHS, DRAWDOWN_STOP as DD_STOP,
    DRAWDOWN_RECOVER, DRAWDOWN_TARGET_CAP,
)
from .risk import trend_filter, drawdown_stop


def backtest_a(weights: pd.Series, rets: pd.DataFrame,
               cash_ratio: float = 0.0) -> tuple:
    """方案 A 回测。

    三层防护：
    1. 久期结构调整（权重层面已做，见 portfolios.py）
    2. 月度趋势过滤：单个资产 12 月动量转负 → 转货币基金
    3. 回撤止损：组合回撤 > 8% → 总仓位 50%

    返回：nv (pd.Series), n_rebal (int), n_trend_trig (int), n_dd_trig (int)
    """
    cols = list(weights.index)
    target = weights.values * (1 - cash_ratio)
    nv = pd.Series(index=rets.index, dtype=float)
    h = pd.Series(target, index=cols)
    v = 1.0
    n_rebal = 0
    n_trend_trig = 0
    n_dd_trig = 0
    in_drawdown_stop = False

    rebal_dates = set(rets.resample(REBAL_FREQ).last().index)

    for i, d in enumerate(rets.index):
        if i == 0:
            nv.loc[d] = 1.0
            continue

        v *= 1 + (h * rets.loc[d, cols]).sum() + cash_ratio * RISK_FREE_RATE
        nv.loc[d] = v
        h = h * (1 + rets.loc[d, cols])
        s = h.sum()
        if s > 0:
            h = h / s * (1 - cash_ratio)

        # === 月度趋势过滤：每月初检查 ===
        if d.month != rets.index[i - 1].month:
            for a in cols:
                asset_ret = rets.loc[:d, a].tail(TREND_LOOKBACK_MONTHS * 21)
                if trend_filter(asset_ret):
                    h[a] = 0.0  # 该仓位转入货币基金
                    n_trend_trig += 1
            # 恢复检查：12 月动量回正的资产恢复仓位
            for a in cols:
                if h[a] == 0.0:
                    asset_ret = rets.loc[:d, a].tail(TREND_LOOKBACK_MONTHS * 21)
                    if not trend_filter(asset_ret):
                        h[a] = target[a]
            # 正常化
            s = h.sum()
            if s > 0:
                h = h / s * (1 - cash_ratio)

        # === 回撤止损 ===
        if in_drawdown_stop:
            if not drawdown_stop(nv.loc[:d], DRAWDOWN_RECOVER):
                in_drawdown_stop = False
                h = pd.Series(target, index=cols)
                n_dd_trig += 1
                n_rebal += 1
        else:
            if drawdown_stop(nv.loc[:d], DD_STOP):
                in_drawdown_stop = True
                h = h * DRAWDOWN_TARGET_CAP
                n_dd_trig += 1
                n_rebal += 1

        # === 基础调仓（半年节点 + 3% 阈值）===
        if not in_drawdown_stop:
            triggered = (h.values - target).__abs__().max() > REBAL_THRESHOLD
            if (d in rebal_dates) or triggered:
                h = pd.Series(target, index=cols)
                n_rebal += 1

    return nv, n_rebal, n_trend_trig, n_dd_trig
```

- [ ] **Step 3: Commit**

```bash
git add allweather/strategy_a.py allweather/portfolios.py
git commit -m "feat: 方案 A 轻量风控（久期调整 + 趋势过滤 + 回撤止损）"
```

---

### Task 6: 实现方案 B（真风险平价 + 动态配置）

**Files:**
- Create: `allweather/strategy_b.py`

- [ ] **Step 1: 写 `strategy_b.py`**

```python
"""方案 B：真风险平价 + 动态配置 + 三级防护。"""
import pandas as pd
import numpy as np
from .config import (
    RISK_FREE_RATE, RISK_PARITY_WINDOW, RISK_PARITY_MAX_WEIGHT,
    RISK_PARITY_MIN_WEIGHT, CORR_BREAKER_THRESHOLD, CORR_BREAKER_RECOVER,
    CORR_BREAKER_CAP, VOL_TARGET,
)
from .risk import (
    inverse_vol_weights, correlation_breaker, vol_target_scale,
)


def backtest_b(
    rets: pd.DataFrame,
    cash_ratio: float = 0.0,
    horizon: str = "long",  # "short" / "mid" / "long"
) -> tuple:
    """方案 B 回测。

    机制：
    1. 每月用逆波动率重算权重（真风险平价）
    2. 相关性断路器：平均相关 > 0.3 → 仓位 70%
    3. Vol targeting：年化目标 6%
    4. 投资期限分档控制风险资产上限

    返回：nv (pd.Series), n_rebal (int), n_corr_break (int)
    """
    horizon_caps = {"short": 0.40, "mid": 0.70, "long": 1.00}
    risk_cap = horizon_caps.get(horizon, 1.00)

    cols = list(rets.columns)
    nv = pd.Series(index=rets.index, dtype=float)
    n_rebal = 0
    n_corr_break = 0
    in_corr_break = False

    # 初始权重
    initial_w = inverse_vol_weights(
        rets.iloc[:RISK_PARITY_WINDOW],
        RISK_PARITY_WINDOW, RISK_PARITY_MAX_WEIGHT, RISK_PARITY_MIN_WEIGHT
    )
    target = initial_w.values * (1 - cash_ratio)
    h = pd.Series(target, index=cols)
    v = 1.0
    current_weights = initial_w.copy()

    for i, d in enumerate(rets.index):
        if i == 0:
            nv.loc[d] = 1.0
            continue

        # 仓位缩放：vol targeting
        if i > RISK_PARITY_WINDOW:
            scale = vol_target_scale(
                rets.iloc[i - RISK_PARITY_WINDOW:i],
                VOL_TARGET, RISK_PARITY_WINDOW
            )
        else:
            scale = 1.0

        effective_h = h * scale * risk_cap
        v *= 1 + (effective_h * rets.loc[d, cols]).sum() + cash_ratio * RISK_FREE_RATE
        nv.loc[d] = v

        h = h * (1 + rets.loc[d, cols])
        s = h.sum()
        if s > 0:
            h = h / s * (1 - cash_ratio)

        # === 月度调仓 ===
        if d.month != rets.index[i - 1].month and i > RISK_PARITY_WINDOW:
            # 相关性断路器
            window = rets.iloc[max(0, i - RISK_PARITY_WINDOW):i]
            if in_corr_break:
                if not correlation_breaker(window, CORR_BREAKER_RECOVER,
                                          RISK_PARITY_WINDOW):
                    in_corr_break = False
            else:
                if correlation_breaker(window, CORR_BREAKER_THRESHOLD,
                                      RISK_PARITY_WINDOW):
                    in_corr_break = True
                    n_corr_break += 1

            new_w = inverse_vol_weights(
                window, RISK_PARITY_WINDOW,
                RISK_PARITY_MAX_WEIGHT, RISK_PARITY_MIN_WEIGHT
            )

            if in_corr_break:
                new_w = new_w * CORR_BREAKER_CAP

            current_weights = new_w
            target = current_weights.values * (1 - cash_ratio)
            h = pd.Series(target, index=cols)
            n_rebal += 1

    return nv, n_rebal, n_corr_break
```

- [ ] **Step 2: Commit**

```bash
git add allweather/strategy_b.py
git commit -m "feat: 方案 B 真风险平价（逆波动率 + 相关断路器 + vol targeting + 期限分档）"
```

---

### Task 7: 更新流水线和报告系统

**Files:**
- Modify: `allweather/pipeline.py`
- Modify: `allweather/reports.py`
- Modify: `allweather/portfolios.py`
- Modify: `allweather/excel_export.py`
- Modify: `allweather/markdown_report.py`

- [ ] **Step 1: 更新 `PORTFOLIO_TAGS` 加新方案标签**

```python
PORTFOLIO_TAGS = {
    "V3b 平衡":   {"stars": "★★",  "label": "备选 - 求最浅回撤者"},
    "V3c 多元":   {"stars": "★★★", "label": "强烈推荐（原基准）"},
    "V3d 商品偏重": {"stars": "★★",  "label": "备选 - 怕滞胀者"},
    "V3-A 风控":   {"stars": "★★★", "label": "轻量风控（2022 防御）"},
    "V3-B 动态":   {"stars": "★★★", "label": "真风险平价（动态配置）"},
}
```

- [ ] **Step 2: 更新 `get_weights()` 返回也包含 Plan A 权重（Plan B 无固定权重）**

```python
def get_weights():
    out = {}
    for name, w in WEIGHTS.items():
        s = pd.Series(w).reindex(ASSETS).fillna(0)
        assert abs(s.sum() - 1) < 1e-6, f"{name} 权重和={s.sum()}"
        out[name] = s
    # Plan A 使用扩展资产集
    a_w = WEIGHTS.get("V3-A 风控", {})
    if a_w:
        from .config import ASSETS_PLAN_A
        s = pd.Series(a_w).reindex(ASSETS_PLAN_A).fillna(0)
        assert abs(s.sum() - 1) < 1e-6, f"V3-A 风控 权重和={s.sum()}"
        out["V3-A 风控"] = s
    return out
```

- [ ] **Step 3: 更新 `pipeline.py::step_2_run_backtests`**

在现有 3×3=9 个回测循环后，加 Plan A（3 现金档）和 Plan B（3 现金档 × 3 期限）的回测：

```python
# 方案 A：使用 strategy_a（需要含 short_bond 的扩展面板）
from .strategy_a import backtest_a
from .data import load_panel_extended
panel_ext = load_panel_extended()
rets_ext = panel_ext.pct_change().dropna()
for tier_label, c in CASH_TIERS:
    nv, n, n_t, n_d = backtest_a(weights["V3-A 风控"], rets_ext, cash_ratio=c)
    nv_results[("V3-A 风控", tier_label)] = nv

# 方案 B：使用 strategy_b，全 11 资产面板
from .strategy_b import backtest_b
for tier_label, c in CASH_TIERS:
    for horizon in ["short", "mid", "long"]:
        nv, n, n_c = backtest_b(rets_ext, cash_ratio=c, horizon=horizon)
        nv_results[(f"V3-B {horizon}", tier_label)] = nv
```

- [ ] **Step 4: 更新 `pipeline.py::step_3`/`step_4` 以处理新方案的 metrics**

- [ ] **Step 5: 更新 `reports.py` 的表头列宽，适配更长方案名**

- [ ] **Step 6: 更新 Excel/Markdown 报告相应章节**

- [ ] **Step 7: Commit**

```bash
git add allweather/pipeline.py allweather/reports.py allweather/portfolios.py \
        allweather/excel_export.py allweather/markdown_report.py
git commit -m "feat: 流水线 + 报告系统适配方案 A/B"
```

---

### Task 8: 数据准备 — 拉取短债和收益率曲线

**Files:**
- Modify: `allweather/fetch.py`

- [ ] **Step 1: 在 `TARGETS` 字典中加短债拉取**

```python
"bond_short": ("etf_nav", "511880"),  # 货币基金 ETF 作为短债替代
```

- [ ] **Step 2: 运行 `python main.py --fetch` 补拉缺失数据**

- [ ] **Step 3: Commit**

```bash
git add allweather/fetch.py data/
git commit -m "data: 加短债 ETF 拉取目标"
```

---

### Task 9: 跑回测并验证结果

**Files:** 无新建，生成 `output/` 产物

- [ ] **Step 1: 尝试扩展回测起点**

```bash
# 检查各 ETF 最早可用日
python -c "
import pandas as pd
from pathlib import Path
for f in sorted(Path('data').glob('*.csv')):
    df = pd.read_csv(f, parse_dates=['date'])
    print(f'{f.stem:<25} {df.date.min().date()} ~ {df.date.max().date()}  n={len(df):>5}')
"
```

根据各资产最早可用日确定是否可扩展起点。若多数资产在 2020-01 之前有数据，将 `BACKTEST_START` 改为最早可行日。否则保持 2020-08。

- [ ] **Step 2: 加情景压力测试（在 `config.py::STRESS_EVENTS` 中加模拟历史债熊）**

```python
# 模拟情景：用 2013 年钱荒和 2017 年债熊的利率冲击幅度
("模拟-2013钱荒(利率急升)", "2020-08-01", "2021-01-31"),
("模拟-2017债熊",            "2020-08-01", "2021-06-30"),
```

注：这些是模拟情景——在回测期内用历史冲击的幅度做压力测试。实现为在 `stats.py` 中新增 `synthetic_stress_test` 函数，用历史利率冲击数据重放。

- [ ] **Step 3: 运行完整回测**

```bash
python main.py
```

- [ ] **Step 4: 检查控制台输出** —— 确认所有方案出现在报表中，Sharpe 已修正

- [ ] **Step 5: 重点验证 2022 年表现**

```bash
python -c "
from allweather.pipeline import step_1_load_data, step_2_run_backtests
panel, rets = step_1_load_data()
weights, nv = step_2_run_backtests(rets)
for k, nv_s in nv.items():
    y22 = nv_s['2022-12-31'] / nv_s['2022-01-03'] - 1
    print(f'{k[0]:<20} {k[1]:<10}  2022: {y22*100:+.2f}%')
"
```

- [ ] **Step 6: 若 2022 年亏损仍超过 -3%，调整参数**

重点看方案 A 的趋势过滤效果和方案 B 的相关性断路器是否触发。关键参数：
- Plan A: `TREND_LOOKBACK_MONTHS` 从 12 调到 6，更快减仓
- Plan B: `CORR_BREAKER_THRESHOLD` 从 0.30 调到 0.25，更早熔断

- [ ] **Step 7: Commit 回测产物**

```bash
git add output/
git commit -m "backtest: 方案 A/B vs 基准对比结果（2020-08~2025-12）"
```

---

### Task 10: 更新全部文档

**Files:**
- Modify: `PROJECT_HISTORY.md`
- Modify: `README.md`

- [ ] **Step 1: 用最新回测数据更新 `PROJECT_HISTORY.md` 第 4 节（三套组合）和第 11 节（已知陷阱），加入新方案的说明**

- [ ] **Step 2: 更新 `README.md` 速查表，加入方案 A/B 指标**

- [ ] **Step 3: Commit**

```bash
git add PROJECT_HISTORY.md README.md
git commit -m "docs: 同步最新回测指标 + 方案 A/B 说明"
```
