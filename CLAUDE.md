# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Git commit rules

- Commit message 中禁止包含任何 Co-Authored-By 署名（包括但不限于 Claude、Anthropic、noreply@anthropic.com 等任何 AI 相关署名）
- 所有提交仅保留用户本人的 git author 信息
- 创建 PR 时同样不添加任何 AI 合作者信息

## Git branch rules

单人项目，直接推 main。无分支保护，无 PR 流程。

- `git add -A && git commit -m "..." && git push` 即可
- 大改动可以开 feature 分支自己玩，但最终直接合 main
- 按心情打 Tag，不强制

## Project identity

Bridgewater All Weather portfolio localized to China A-share ETFs. Pure research/backtesting — not a library, not a web app. The goal: weight schemes that ordinary investors can copy-paste.

Output: console reports + `output/report.xlsx` + `output/report.md`. Online docs at `docs/index.html` (GitHub Pages).

## Commands

```bash
python main.py                 # Full pipeline: load → backtest → metrics → bootstrap → reports → save
python main.py --no-excel      # Skip Excel output (faster iteration)
python main.py --no-markdown   # Skip Markdown output
python main.py --fetch         # Pull missing data first, then backtest
python main.py --fetch-only    # Only pull data, don't backtest
python main.py --force-fetch   # Re-pull all CSVs (overwrites data/)
```

No test suite. CI (`.github/workflows/backtest.yml`) runs `python main.py` and checks `output/summary.json` Sharpe/MDD bounds.

## Architecture

```
main.py                     CLI entry → delegates to pipeline.run_full_pipeline()
allweather/
  config.py                 All constants: tickers, buckets, backtest period, RP/risk params
  data.py                   Load CSVs from data/ + synthesize 30Y bond pre-ETF-era
  fetch.py                  Pull data via akshare (optional dependency)
  portfolios.py             V3c fixed weights + V3-B tags in PORTFOLIO_TAGS
  backtest.py               V3c engine: monthly rebalancing + nonferr trend filter + cash tiers
  risk.py                   Risk primitives: inverse vol weights, hierarchical RP (trend filter/drawdown
                            stop/vol target/corr breaker retained as library functions but unused in pipeline)
  strategy_b.py             V3-B: hierarchical RP (4/5-bucket) / inverse vol monthly rebalance + nonferr trend filter
  stats.py                  perf_metrics, yearly_returns, event_returns, regime_returns, block_bootstrap, etc.
  reports.py                Console output (9 tables) + JSON/CSV persistence
  excel_export.py           11-sheet formatted Excel report
  markdown_report.py        GitHub-renderable Markdown report
  pipeline.py               6-step orchestration
```

### The 6-step pipeline (`pipeline.py`)

1. `step_1_load_data` — load 9-asset panel, compute daily returns
2. `step_2_run_backtests` — V3c (6 assets) + V3-B RP (4-bucket HRP, 6 assets) + V3-B 保守增强(20d) (IV, 7 assets), each × 3 cash tiers = 9 backtests
3. `step_3_compute_metrics` — perf / yearly / risk contribution / regime / event / rolling stats
4. `step_4_bootstrap` — 1000×5yr block bootstrap (21-day blocks). V3-B uses last-window proxy weights.
5. `step_5_print_reports` — console output
6. `step_6_save_outputs` — CSV/JSON/Excel/Markdown

### 3 strategies (2026-05-27)

- **V3c 多元** ★★★: 6-asset inverse vol 60d (max_w=0.30, min_w=0.03) + nonferr trend filter 60d + gold/hs300 dip-buying. "简约派" — highest Sharpe (1.40), CAGR 8.59%, MDD -5.84%.
- **V3-B 风险平价(20d)** ★★★: 4-bucket hierarchical RP (30Y only, no 10Y) + nonferr trend filter 75d + gold/hs300 dip-buying, 20d window. "学院派" — best CAGR (10.68%), best cumulative return (536.57%), MDD -10.34%, Sharpe 1.33.
- **V3-B 保守增强(20d)** ★★★: Inverse vol + nonferr trend filter 75d + gold/hs300 dip-buying, 20d window, max_w=0.25. "保守增强" — lowest MDD (-3.83%), highest Sharpe (1.64).

V3c: 6 assets. V3-B RP: 6 assets (no bond_10y). V3-B 保守增强: 7 assets. div_idx (0.90 corr with hs300) and soymeal (negative Sharpe) removed 2026-05-27.

### Dynamic rebalancing

- **V3c**: Inverse vol weighting, monthly rebalance (60d lookback), 6 assets filtered via V3C_ASSETS. Code: `backtest.py::backtest_iv`.
- **V3-B RP**: No fixed weights. Monthly: 4 macro buckets equal-weighted (25% each), within-bucket inverse-vol weights (HRP). 6 assets (no bond_10y). Code: `strategy_b.py::backtest_b` with `rp_buckets=V3B_RP_BUCKETS`.
- **V3-B 保守增强**: No fixed weights. Monthly: flat inverse vol (no buckets). 7 assets. Code: `strategy_b.py::backtest_b` with `weighting_method="inverse_vol"`.

### Cash tiers

Every strategy × 3 cash levels: 100% RP (0% cash), 85% RP (15% cash), 70% RP (30% cash). Defined in `config.py::CASH_TIERS`.

## Key design decisions

### 30Y bond synthesis (`data.py::synthesize_bond_30y`)

ETF 511130 launched 2024-03. Three-stage synthesis:
1. 2008-01 ~ 2020-02: 10Y returns × 3.0 duration multiplier (deduct 0.3%/yr)
2. 2020-02 ~ 2024-03: yield curve spread method (10Y-30Y spread × duration 18.0)
3. 2024-03 ~ now: real ETF NAV

### Sharpe ratio is corrected

`sharpe = (CAGR - 2.2% risk-free) / vol`. Raw preserved as `sharpe_raw` in `summary.json`.

### V3-B bootstrap uses proxy weights

Since V3-B has dynamic weights, bootstrap uses the last window's hierarchical RP weights as a fixed proxy (known limitation: all V3-B variants share bootstrap results).

### Asset universe & macro buckets

**V3-B 保守增强 (7 assets / 5 buckets)** — `config.py::BUCKET_GROUPS`:

| Bucket | Assets |
|--------|--------|
| 增长↑ | hs300, us_sp500 |
| 收益垫 | credit |
| 增长↓10Y | bond_10y |
| 增长↓30Y | bond_30y |
| 通胀↑ | gold, nonferr |

**V3-B 风险平价 (6 assets / 4 buckets)** — `pipeline.py::V3B_RP_BUCKETS`:

| Bucket | Assets |
|--------|--------|
| 增长↑ | hs300, us_sp500 |
| 收益垫 | credit |
| 增长↓ | bond_30y |
| 通胀↑ | gold, nonferr |

B-RP drops bond_10y: asset test showed CAGR +1.43% with negligible Sharpe loss (-0.02). The 10Y bond (~8yr duration) is redundant with 30Y (~18yr) when buckets get equal weight — keeping both dilutes the growth/equity allocation.

## Important constants (all in `config.py`)

| Constant | Value | Purpose |
|---|---|---|
| `BACKTEST_START/END` | 2008-01-01 / 2025-12-31 | ~18 year window |
| `REBAL_FREQ` | "ME" | Monthly rebalance (V3c) |
| `REBAL_THRESHOLD` | 0.03 | 3% deviation trigger |
| `RISK_FREE_ANNUAL` | 0.022 | Sharpe correction |
| `RISK_PARITY_WINDOW` | 20 | V3-B 20d lookback (trading days) |
| `RISK_PARITY_MAX_WEIGHT` | 0.20 | Single asset cap in V3-B (0.20 enables true equal-bucket parity, 0.18 artificially capped single-asset buckets) |
| `RISK_PARITY_MIN_WEIGHT` | 0.02 | Single asset floor in V3-B |
| `BOND_30Y_AMP` | 3.0 | Fallback duration multiplier |
| `GOLD_DIP_THRESHOLD` | 0.15 | Gold dip-buy trigger (15% DD from peak) |
| `GOLD_DIP_BOOST` | 2.5 | Gold weight boost multiplier when triggered (2.5x, grid-search optimal) |
| `HS300_DIP_THRESHOLD` | 0.35 | hs300 dip-buy trigger (35% DD, catastrophic only) |
| `HS300_DIP_BOOST` | 2.5 | hs300 weight boost multiplier when triggered (2.5x, grid-search optimal) |
| `BOOTSTRAP_N_SIM` | 1000 | Monte Carlo iterations |
| `BOOTSTRAP_HORIZON_DAYS` | 1260 | 5-year horizon |
| `BOOTSTRAP_BLOCK_DAYS` | 21 | ~1 month blocks |

## Documentation

- `PROJECT_HISTORY.md` — complete project memory for AI: decisions, rationale, metrics, timeline
- `README.md` — user-facing: quickstart, strategy quick-reference, directory map
- `docs/index.html` — full strategy document (Chinese), served on GitHub Pages
