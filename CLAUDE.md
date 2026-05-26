# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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
  backtest.py               V3c engine: semi-annual + 3% threshold dual-trigger rebalancing + cash tiers
  risk.py                   Risk primitives: inverse vol weights, hierarchical RP (trend filter/drawdown
                            stop/vol target/corr breaker retained as library functions but unused in pipeline)
  strategy_b.py             V3-B: hierarchical RP monthly rebalance, 60d window + nonferr trend filter variant
  stats.py                  perf_metrics, yearly_returns, event_returns, regime_returns, block_bootstrap, etc.
  reports.py                Console output (9 tables) + JSON/CSV persistence
  excel_export.py           11-sheet formatted Excel report
  markdown_report.py        GitHub-renderable Markdown report
  pipeline.py               6-step orchestration
```

### The 6-step pipeline (`pipeline.py`)

1. `step_1_load_data` — load 9-asset panel, compute daily returns
2. `step_2_run_backtests` — V3c (fixed) + V3-B 60d + V3-B 保守增强(60d), each × 3 cash tiers = 9 backtests
3. `step_3_compute_metrics` — perf / yearly / risk contribution / regime / event / rolling stats
4. `step_4_bootstrap` — 1000×5yr block bootstrap (21-day blocks). V3-B uses last-window proxy weights.
5. `step_5_print_reports` — console output
6. `step_6_save_outputs` — CSV/JSON/Excel/Markdown

### 3 strategies (2026-05-26)

- **V3c 多元** ★★★: Fixed weights (defined in `portfolios.py::WEIGHTS`). Semi-annual + 3% threshold dual-trigger rebalancing. "实战派" — best 11-year backtest, simple to execute.
- **V3-B 风险平价(60d)** ★★★: Hierarchical RP monthly rebalance, 60-day lookback. "学院派（战术）" — responsive.
- **V3-B 保守增强(60d)** ★★★: risk_parity bucket + nonferr trend filter 90d SMA. "保守派" — lowest MDD (-3.52%), highest Sharpe (1.80).

### Fixed-weight vs dynamic rebalancing

- **V3c**: `REBAL_FREQ="2QE"` (semi-annual) + `REBAL_THRESHOLD=0.03`, either trigger fires rebalance. Code: `backtest.py::backtest`.
- **V3-B**: No fixed weights. Every month: 4 macro buckets equal-weighted (25% each), within-bucket inverse-vol weights. Code: `strategy_b.py::backtest_b`.

### Cash tiers

Every strategy × 3 cash levels: 100% RP (0% cash), 85% RP (15% cash), 70% RP (30% cash). Defined in `config.py::CASH_TIERS`.

## Key design decisions

### 30Y bond synthesis (`data.py::synthesize_bond_30y`)

ETF 511130 launched 2024-03. Three-stage synthesis:
1. 2015-01 ~ 2020-02: 10Y returns × 3.0 duration multiplier (deduct 0.3%/yr)
2. 2020-02 ~ 2024-03: yield curve spread method (10Y-30Y spread × duration 18.0)
3. 2024-03 ~ now: real ETF NAV

### Sharpe ratio is corrected

`sharpe = (CAGR - 2.2% risk-free) / vol`. Raw preserved as `sharpe_raw` in `summary.json`.

### V3-B bootstrap uses proxy weights

Since V3-B has dynamic weights, bootstrap uses the last window's hierarchical RP weights as a fixed proxy (known limitation: all V3-B variants share bootstrap results).

### 9 assets / 4 macro buckets

| Bucket | Assets |
|--------|--------|
| 增长↑ | hs300, div_idx, us_sp500 |
| 收益垫 | credit |
| 增长↓ | bond_10y, bond_30y |
| 通胀↑ | gold, nonferr, soymeal |

Defined in `config.py::BUCKET_GROUPS`.

## Important constants (all in `config.py`)

| Constant | Value | Purpose |
|---|---|---|
| `BACKTEST_START/END` | 2015-01-01 / 2025-12-31 | ~11 year window |
| `REBAL_FREQ` | "2QE" | Semi-annual rebalance |
| `REBAL_THRESHOLD` | 0.03 | 3% deviation trigger |
| `RISK_FREE_ANNUAL` | 0.022 | Sharpe correction |
| `RISK_PARITY_WINDOW` | 60 | V3-B 60d lookback (trading days) |
| `RISK_PARITY_MAX_WEIGHT` | 0.25 | Single asset cap in V3-B |
| `RISK_PARITY_MIN_WEIGHT` | 0.02 | Single asset floor in V3-B |
| `BOND_30Y_AMP` | 3.0 | Fallback duration multiplier |
| `BOOTSTRAP_N_SIM` | 1000 | Monte Carlo iterations |
| `BOOTSTRAP_HORIZON_DAYS` | 1260 | 5-year horizon |
| `BOOTSTRAP_BLOCK_DAYS` | 21 | ~1 month blocks |

## Documentation

- `PROJECT_HISTORY.md` — complete project memory for AI: decisions, rationale, metrics, timeline
- `README.md` — user-facing: quickstart, strategy quick-reference, directory map
- `docs/index.html` — full strategy document (Chinese), served on GitHub Pages
