# 回测期前推至 2015 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将全天候策略回测起始日从 2020-08-01 前推至 2015-01-01，覆盖 2015 股灾、2016 熔断、2017 债熊、2018 大熊市等关键宏观情景。

**Architecture:** 修改 3 个核心文件（config.py, fetch.py, data.py）。7 个资产直接从 2015 拉 ETF NAV，3 个资产（nonferr, soymeal, bond_30y）通过 `stitch_series()` 缝合 ETF 真实数据与早期替代数据，替代段施加安全扣减。附带修复 cgb_yields 编码、hs300/div_lowvol 分红缺失（BH-4）。

**Tech Stack:** Python, pandas, akshare, numpy

---

## File Map

| 文件 | 职责 | 改动类型 |
|------|------|---------|
| `allweather/config.py` | 回测期间 + 安全扣减常量 | 修改 |
| `allweather/fetch.py` | 数据拉取：新增 proxy fetcher + cgb_yields + 编码修复 | 修改 |
| `allweather/data.py` | 数据加载：stitch_series() + cgb_yields 位置列匹配 | 修改 |

---

### Task 1: config.py — 回测期间前推 + 新增安全扣减常量

**Files:**
- Modify: `allweather/config.py`

- [ ] **Step 1: 修改 BACKTEST_START 为 2015-01-01**

将第 11 行 `BACKTEST_START = "2020-08-01"` 改为 `BACKTEST_START = "2015-01-01"`：

```python
BACKTEST_START = "2015-01-01"
BACKTEST_END   = "2025-12-31"
```

- [ ] **Step 2: 在 BOND_30Y_AMP 下方新增 SAFETY_DEDUCT 常量表**

在 `BOND_30Y_AMP = 3.0` 之后插入：

```python
# === 合成数据安全扣减（年化）===
# 仅对合成段（ETF 上市前的替代数据）应用，ETF 真实数据段不扣减
SAFETY_DEDUCT = {
    "nonferr":  0.005,   # 申万有色指数不含管理费、跟踪误差
    "soymeal":  0.020,   # 豆粕期货展期损耗+管理费+contango+无现货锚
    "bond_30y": 0.003,   # ×3.0 久期放大的期权费率差
}
```

- [ ] **Step 3: Commit**

```bash
git add allweather/config.py
git commit -m "config: 回测期前推至 2015-01-01，新增合成数据安全扣减常量"
```

---

### Task 2: fetch.py — 新增资产拉取能力（proxy fetchers + cgb_yields 编码修复）

**Files:**
- Modify: `allweather/fetch.py`

- [ ] **Step 1: TARGETS 中 hs300 / div_lowvol 切换为 ETF NAV（BH-4 修复）**

将第 18-19 行：
```python
"hs300":      ("idx", "sh000300"),
"div_lowvol": ("idx", "sh000922"),  # 中证红利
```

改为：
```python
"hs300":      ("etf_nav", "510300"),  # ETF NAV 含分红（was: 价格指数 sh000300）
"div_lowvol": ("etf_nav", "510880"),  # ETF NAV 含分红（was: 价格指数 sh000922）
```

- [ ] **Step 2: TARGETS 新增 bond_short、nonferr_idx、soymeal_fut**

在 TARGETS 字典末尾（`"us_sp500"` 之后）新增：

```python
# 短债/货币（2015 起有数据）
"bond_short":   ("etf_nav", "511880"),
# 缝合用替代数据
"nonferr_idx":  ("idx_em", "sw2_850400"),   # 申万有色金属指数（2015-2019 替代 nonferr ETF）
"soymeal_fut":  ("fut_dce", "M"),            # 豆粕期货主力连续（2015-2019 替代 soymeal ETF）
```

- [ ] **Step 3: 新增 _fetch_fut_dce() 豆粕期货主力连续 fetcher**

在 `_fetch_etf_hist()` 函数之后新增：

```python
def _fetch_fut_dce(sym, start, end):
    """拉取 DCE 期货主力连续合约日频数据。"""
    import akshare as ak
    df = ak.futures_main_sina(symbol=sym)
    df = df.rename(columns={"日期": "date", "收盘价": "close"})
    df["date"] = pd.to_datetime(df["date"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["date", "close"])
    df = df[(df["date"] >= pd.to_datetime(start)) & (df["date"] <= pd.to_datetime(end))]
    return df[["date", "close"]].sort_values("date")
```

- [ ] **Step 4: fetch_one() 新增 "fut_dce" kind 分支**

在 `fetch_one()` 函数中，`elif kind == "etf_nav":` 之前插入：

```python
            elif kind == "fut_dce":
                df = _fetch_fut_dce(sym, start, end)
```

- [ ] **Step 5: 新增 fetch_cgb_yields() 函数（含编码修复）**

在 `_fetch_fut_dce` 函数之后、`fetch_all` 之前插入：

```python
def fetch_cgb_yields():
    """尝试拉取中债国债收益率曲线。失败返回 None。
    
    返回的 DataFrame 列名通过位置匹配：第 8 列=10 年、第 9 列=30 年，
    避免中文列名编码问题。
    """
    try:
        import akshare as ak
        df = ak.bond_china_yield()
        if df is None or df.empty:
            return None
        # 筛选国债行
        if "曲线名称" in df.columns:
            df = df[df["曲线名称"].str.contains("国债", na=False)]
        return df
    except Exception:
        return None
```

- [ ] **Step 6: fetch_all() 末尾新增 cgb_yields 拉取 + bond_short 纳入 skip 检查**

在 `fetch_all()` 函数中，`for name, (kind, sym) in TARGETS.items():` 循环之后、`print(f"\n=== 拉取摘要 ===")` 之前插入 cgb_yields 拉取逻辑：

```python
    # 尝试拉取中债国债收益率曲线
    print(f"  >> cgb_yields (bond_china_yield)", flush=True)
    yield_df = fetch_cgb_yields()
    if yield_df is not None and not yield_df.empty:
        yield_path = DATA_DIR / "cgb_yields.csv"
        yield_df.to_csv(yield_path, index=False, encoding="utf-8")
        print(f"    ok  n={len(yield_df)}")
    else:
        print(f"    WARN  中债收益率曲线拉取失败，将使用久期放大回退方案合成 30Y")
```

- [ ] **Step 7: 更新 check_data_complete() 加入 bond_short**

将 `required` 列表更新，加入 `"bond_short"`：

```python
    required = ["hs300", "div_lowvol", "cb_10y_idx", "bond_30y_etf",
                "bond_credit", "gold", "nonferr", "soymeal", "us_sp500", "bond_short"]
```

- [ ] **Step 8: Commit**

```bash
git add allweather/fetch.py
git commit -m "fetch: hs300/div_lowvol切换ETF NAV含分红，新增proxy fetchers + cgb_yields编码修复"
```

---

### Task 3: data.py — stitch_series() 缝合逻辑 + cgb_yields 位置列匹配

**Files:**
- Modify: `allweather/data.py`

- [ ] **Step 1: 更新 import，加入 SAFETY_DEDUCT**

将第 3 行：
```python
from .config import DATA_DIR, BACKTEST_START, BACKTEST_END, BOND_30Y_AMP
```

改为：
```python
from .config import DATA_DIR, BACKTEST_START, BACKTEST_END, BOND_30Y_AMP, SAFETY_DEDUCT
```

- [ ] **Step 2: 新增 stitch_series() 通用缝合函数**

在 `load_series()` 之后、`synthesize_bond_30y()` 之前插入：

```python
def stitch_series(etf: pd.Series, proxy: pd.Series,
                  annual_deduct: float = 0.0) -> pd.Series:
    """ETF 上市前用 proxy，归一化对齐 + 安全扣减后拼接。

    1. proxy 先做交易日对齐（reindex 到 A 股日历，ffill）
    2. proxy 日收益扣减 safety margin
    3. 在 etf 起始日归一化：proxy *= etf[0] / proxy[stitch_date]
    4. 拼接 proxy[:stitch_date) + etf[stitch_date:]
    """
    if proxy.empty or etf.empty:
        raise ValueError("proxy 或 etf 数据为空，无法缝合")

    # 1. 对齐到 A 股日历（proxy 可能来自期货/指数，交易日历不同）
    ashare_cal = etf.index.sort_values()
    proxy = proxy.reindex(ashare_cal).ffill().dropna()

    # 2. 安全扣减应用于 proxy 日收益率
    daily_deduct = annual_deduct / 252.0
    proxy_ret = proxy.pct_change().dropna()
    proxy_ret = proxy_ret - daily_deduct
    proxy = (1 + proxy_ret).cumprod()
    # 补回首日
    first_val = proxy.iloc[0] / (1 + proxy_ret.iloc[0]) if len(proxy_ret) > 0 else 1.0
    proxy = pd.concat([pd.Series(first_val, index=[proxy.index[0]]), proxy])

    # 3. 在 etf 起始日归一化
    stitch_date = etf.index.min()
    if stitch_date not in proxy.index:
        raise ValueError(f"缝合日 {stitch_date} 不在 proxy 索引中")
    proxy = proxy * (etf.iloc[0] / proxy.loc[stitch_date])

    # 4. 拼接
    proxy_part = proxy[proxy.index < stitch_date]
    return pd.concat([proxy_part, etf]).sort_index()
```

- [ ] **Step 3: 新增 _load_cgb_yields_spread() 从 cgb_yields.csv 读取利差**

在 `synthesize_bond_30y()` 之前插入：

```python
def _load_cgb_yields_spread() -> pd.Series:
    """从 cgb_yields.csv 读取 10Y-30Y 利差日序列。

    使用位置索引匹配列名，避免中文编码依赖。
    列顺序参考 akshare bond_china_yield 输出：
    第 8 列（0-indexed: 7）= 10 年期，第 9 列（0-indexed: 8）= 30 年期。
    如果列数不够，回退到 substring 匹配 '10' 和 '30'。
    """
    path = DATA_DIR / "cgb_yields.csv"
    if not path.exists():
        return pd.Series(dtype=float)

    df = pd.read_csv(path)
    if df.empty or len(df.columns) < 9:
        return pd.Series(dtype=float)

    # 尝试位置匹配（列 7=10Y, 列 8=30Y）
    try:
        date_col = df.columns[0]
        y10_col = df.columns[7]
        y30_col = df.columns[8]
        spread = pd.to_numeric(df[y30_col], errors="coerce") - pd.to_numeric(df[y10_col], errors="coerce")
        dates = pd.to_datetime(df[date_col], errors="coerce")
        spread.index = dates
        spread = spread.dropna().sort_index()
        return spread / 100.0  # 百分比 → 小数
    except Exception:
        pass

    # 回退：substring 匹配
    date_col = df.columns[0]
    cols = df.columns.tolist()
    y10_col = next((c for c in cols if "10" in str(c)), None)
    y30_col = next((c for c in cols if "30" in str(c)), None)
    if y10_col is None or y30_col is None:
        return pd.Series(dtype=float)
    spread = pd.to_numeric(df[y30_col], errors="coerce") - pd.to_numeric(df[y10_col], errors="coerce")
    dates = pd.to_datetime(df[date_col], errors="coerce")
    spread.index = dates
    return spread.dropna().sort_index() / 100.0
```

- [ ] **Step 4: 重写 synthesize_bond_30y() — 三阶段合成**

将现有 `synthesize_bond_30y()` 替换为三阶段版本：

```python
def synthesize_bond_30y(s_10y: pd.Series, s_30y_etf: pd.Series) -> pd.Series:
    """合成 30Y 国债序列，三阶段拼接：

    1. 2015-01 ~ 2020-02：×3.0 久期放大（扣减 0.3%/年）
    2. 2020-02 ~ 2024-03：利差法（10Y-30Y spread × duration 18.0）
    3. 2024-03 ~ now：ETF 511130 真实 NAV
    """
    cb10_ret = s_10y.pct_change().dropna()
    etf_start = s_30y_etf.index.min()

    # 阶段 1: ×3.0 久期放大（全段先算）
    amp_ret = cb10_ret * BOND_30Y_AMP
    amp_nv = (1 + amp_ret).cumprod()
    amp_nv = amp_nv / amp_nv.iloc[0]  # 归一化从 1 起

    # 阶段 2: 利差法（从 cgb_yields 读取利差）
    spread = _load_cgb_yields_spread()
    spread_cutoff = pd.Timestamp("2020-02-01")

    if not spread.empty and spread.index.min() <= spread_cutoff:
        # 有利差数据，2020-02 起用利差法
        cb10_ret_aligned = cb10_ret[cb10_ret.index >= spread.index.min()]
        spread_aligned = spread.reindex(cb10_ret_aligned.index).ffill()
        # 利差法：30Y ret ≈ 10Y ret + duration × Δspread
        spread_daily = spread_aligned.diff().fillna(0.0) / 252.0
        dur = 18.0
        spread_ret = cb10_ret_aligned + dur * spread_daily
        spread_nv = (1 + spread_ret).cumprod()
        # 从 2020-02 开始使用
        spread_nv = spread_nv[spread_nv.index >= spread_cutoff]
    else:
        spread_nv = pd.Series(dtype=float)

    # 构建合成序列：阶段1 全段 → 阶段2 覆盖 → 阶段3 ETF 覆盖
    synth = amp_nv.copy()

    # 阶段2 覆盖
    if not spread_nv.empty:
        # 在覆盖点归一化
        stitch_pt = spread_nv.index.min()
        if stitch_pt in synth.index:
            spread_nv = spread_nv * (synth.loc[stitch_pt] / spread_nv.iloc[0])
            synth = pd.concat([synth[synth.index < stitch_pt], spread_nv])

    # 阶段3: ETF 真实数据覆盖
    if etf_start in synth.index:
        etf_norm = s_30y_etf / s_30y_etf.iloc[0] * synth.loc[etf_start]
        synth = pd.concat([synth[synth.index < etf_start], etf_norm[etf_norm.index >= etf_start]])

    # 对阶段1 段应用安全扣减
    if not spread_nv.empty:
        phase1_end = min(spread_cutoff, spread_nv.index.min())
    else:
        phase1_end = etf_start
    daily_deduct = SAFETY_DEDUCT["bond_30y"] / 252.0
    phase1_mask = synth.index < phase1_end
    if phase1_mask.any():
        phase1_ret = synth[phase1_mask].pct_change().dropna() - daily_deduct
        phase1_corrected = (1 + phase1_ret).cumprod()
        phase1_corrected = phase1_corrected / phase1_corrected.iloc[0]  # 重新归一化
        if len(phase1_corrected) > 0:
            anchor_idx = phase1_corrected.index[-1]
            if anchor_idx in synth.index:
                phase1_corrected = phase1_corrected * (synth.loc[anchor_idx] / phase1_corrected.iloc[-1])
            post_phase1 = synth[synth.index > phase1_corrected.index[-1]]
            synth = pd.concat([phase1_corrected, post_phase1])

    return synth.sort_index()
```

- [ ] **Step 5: 重写 load_panel() — 加载 10 资产含缝合逻辑**

将现有 `load_panel()` 替换为以下版本：

```python
def load_panel() -> pd.DataFrame:
    """加载 10 资产收盘价面板（已对齐到回测期间，前向填充）。

    7 个资产直接从 2015 拉 ETF NAV，
    3 个资产通过 stitch_series() 缝合早期替代数据。
    """
    # 直接加载的 7 个资产（ETF NAV 从 2015 起）
    direct = {k: load_series(k) for k in [
        "hs300", "div_lowvol", "cb_10y_idx",
        "bond_credit", "gold", "us_sp500", "bond_short",
    ]}

    # bond_30y: 三阶段合成
    s_30y_etf = load_series("bond_30y_etf")
    bond_30y = synthesize_bond_30y(direct["cb_10y_idx"], s_30y_etf)

    # nonferr: 申万有色指数(2015-2019) + ETF(2019+)
    nonferr_etf = load_series("nonferr")
    nonferr_proxy_path = DATA_DIR / "nonferr_idx.csv"
    if nonferr_proxy_path.exists():
        nonferr_proxy = pd.read_csv(nonferr_proxy_path, parse_dates=["date"]).set_index("date")["close"].sort_index()
        nonferr = stitch_series(nonferr_etf, nonferr_proxy,
                                annual_deduct=SAFETY_DEDUCT["nonferr"])
    else:
        nonferr = nonferr_etf

    # soymeal: 豆粕期货主力(2015-2019) + ETF(2019+)
    soymeal_etf = load_series("soymeal")
    soymeal_proxy_path = DATA_DIR / "soymeal_fut.csv"
    if soymeal_proxy_path.exists():
        soymeal_proxy = pd.read_csv(soymeal_proxy_path, parse_dates=["date"]).set_index("date")["close"].sort_index()
        soymeal = stitch_series(soymeal_etf, soymeal_proxy,
                                annual_deduct=SAFETY_DEDUCT["soymeal"])
    else:
        soymeal = soymeal_etf

    panel = pd.DataFrame({
        "hs300":    direct["hs300"],
        "div_idx":  direct["div_lowvol"],
        "us_sp500": direct["us_sp500"],
        "credit":   direct["bond_credit"],
        "bond_10y": direct["cb_10y_idx"],
        "bond_30y": bond_30y,
        "gold":     direct["gold"],
        "nonferr":  nonferr,
        "soymeal":  soymeal,
    })
    panel.index = pd.to_datetime(panel.index)
    panel = panel.sort_index()
    panel = panel.loc[BACKTEST_START:BACKTEST_END].ffill().dropna()

    return panel
```

- [ ] **Step 6: Commit**

```bash
git add allweather/data.py
git commit -m "data: 新增stitch_series缝合逻辑 + cgb_yields位置列匹配 + 10资产面板"
```

---

### Task 4: 首次数据拉取 + 验证

**Files:**
- Modify: (none — run commands only)

- [ ] **Step 1: 强制拉取所有数据（含 2015 起的新资产）**

```bash
cd "C:\Users\MOSS\Desktop\全季节策略" && uv run python main.py --force-fetch --start 20150101
```

Expected: 11 个 CSV（9 ETF + bond_short + nonferr_idx + soymeal_fut + cgb_yields）成功拉取，nonferr/soymeal ETF 可能只有 2019 起的数据（正常），proxy fetcher 覆盖 2015 起。

- [ ] **Step 2: 检查各 CSV 数据起始日期**

```bash
cd "C:\Users\MOSS\Desktop\全季节策略" && uv run python -c "
import pandas as pd
from pathlib import Path
for f in sorted(Path('data').glob('*.csv')):
    df = pd.read_csv(f, parse_dates=['date'])
    if 'date' in df.columns and len(df) > 0:
        print(f'{f.stem:20s}  {df.date.min().date()} ~ {df.date.max().date()}  n={len(df):5d}')
    else:
        print(f'{f.stem:20s}  EMPTY')
"
```

验证清单：
- hs300, div_lowvol, bond_short, gold, us_sp500, bond_credit, cb_10y_idx: 起始日 ≤ 2015-01-05
- nonferr_idx: 起始日 ≤ 2015-01-05
- soymeal_fut: 起始日 ≤ 2015-01-05
- cgb_yields: 非空，有数据列

- [ ] **Step 3: 验证 cgb_yields 可正确读取利差**

```bash
cd "C:\Users\MOSS\Desktop\全季节策略" && uv run python -c "
import pandas as pd
df = pd.read_csv('data/cgb_yields.csv')
print(f'行数: {len(df)}, 列数: {len(df.columns)}')
print(f'列名: {list(df.columns[:12])}')
if len(df.columns) >= 9:
    y10 = pd.to_numeric(df.iloc[:,7], errors='coerce')
    y30 = pd.to_numeric(df.iloc[:,8], errors='coerce')
    spread = (y30 - y10).dropna()
    print(f'利差范围: {spread.min():.4f} ~ {spread.max():.4f}')
    print(f'利差均值: {spread.mean():.4f}')
"
```

Expected: 有数据行，第 8/9 列可解析为数值，利差在合理范围（0~2%）。

- [ ] **Step 4: 运行完整回测**

```bash
cd "C:\Users\MOSS\Desktop\全季节策略" && uv run python main.py --no-excel --no-markdown
```

验证：
- 回测从 2015-01-01 起
- 无 NaN 报错
- 9 张报表正常输出
- Sharpe/MDD/CAGR 在合理范围

- [ ] **Step 5: 验证缝合点无跳空**

```bash
cd "C:\Users\MOSS\Desktop\全季节策略" && uv run python -c "
from allweather.data import load_panel
panel = load_panel()
# 检查 nonferr/soymeal 2019 附近（ETF 上市缝合点）
for col in ['nonferr', 'soymeal', 'bond_30y']:
    s = panel[col].dropna()
    ret = s.pct_change().dropna()
    # 找最大单日涨跌（跳空检测）
    extreme = ret.abs().nlargest(5)
    print(f'{col}: 最大日波动={extreme.max():.4f}, 日期={ret.abs().idxmax()}')
"
```

Expected: 缝合点附近无超过 5% 的单日跳空（正常市场波动可接受）。

- [ ] **Step 6: 验证 2015-2019 各年收益合理**

```bash
cd "C:\Users\MOSS\Desktop\全季节策略" && uv run python -c "
from allweather.pipeline import step_1_load_data, step_2_run_backtests
panel, rets = step_1_load_data()
weights, nv_results = step_2_run_backtests(rets)
for year in range(2015, 2020):
    nv = nv_results[('V3c 多元', '100% RP')]
    yr_ret = nv.loc[str(year)].iloc[-1] / nv.loc[str(year)].iloc[0] - 1
    print(f'V3c {year}: {yr_ret:+.2%}')
"
```

Expected: 2015 股灾年负收益、2017 正收益、2018 大熊市负收益，均在合理范围（无异常值如 ±80%）。

- [ ] **Step 7: Commit (if data files changed)**

如果 data/ 下有新增 CSV 需要纳入版本管理：

```bash
git add data/
git commit -m "data: 新增 2015 起回测数据文件（nonferr_idx, soymeal_fut, cgb_yields 等）"
```

---

### Task 5: 文档更新 — PROJECT_HISTORY.md + README.md

**Files:**
- Modify: `PROJECT_HISTORY.md`
- Modify: `README.md`

- [ ] **Step 1: 更新 PROJECT_HISTORY.md 回测期记录**

找到回测期间相关记录，更新为 2015-01-01 ~ 2025-12-31（~11 年）。新增一条决策记录：

```markdown
### 2026-05-25: 回测期前推至 2015

**决策**：将回测起始日前推至 2015-01-01（+5 年，总覆盖 ~11 年）

**原因**：覆盖 2015 股灾、2016 熔断、2017 债熊、2018 大熊市等关键宏观情景

**方案**：
- 7 个资产直接拉 ETF NAV 从 2015 起
- nonferr/soymeal/bond_30y 使用替代数据 + stitch_series() 缝合
- 合成段施加安全扣减（nonferr -0.5%/yr, soymeal -2.0%/yr, bond_30y -0.3%/yr）
- 附带修复 hs300/div_lowvol 从价格指数切换为 ETF NAV（含分红，BH-4）
```

- [ ] **Step 2: 更新 README.md 速查表**

更新速查表中的回测期间为 2015-01-01 ~ 2025-12-31。回测指标更新为实测值（从 output/summary.json 取得）。

- [ ] **Step 3: Commit**

```bash
git add PROJECT_HISTORY.md README.md
git commit -m "docs: 更新回测期至 2015-01-01，记录前推决策"
```

---

## 验证标准（来自 Spec）

- [ ] `python main.py --force-fetch --start 20150101` 成功拉取所有数据
- [ ] 10 资产数据从 2015-01-01 起连续无断点
- [ ] 缝合点无跳空（nonferr/soymeal 2019 附近净值连续）
- [ ] V3c 2015-2019 各年收益在合理范围
- [ ] 回测 9 张报表完整输出
- [ ] 2015 股灾、2016 熔断、2018 熊市在事件分析中可识别
