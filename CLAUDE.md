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
  backtest.py               V3c engine: monthly rebalancing + nonferr trend filter + cash tiers
  risk.py                   Risk primitives: inverse vol weights, hierarchical RP (trend filter/drawdown
                            stop/vol target/corr breaker retained as library functions but unused in pipeline)
  strategy_b.py             V3-B: 5-bucket hierarchical RP / inverse vol monthly rebalance + nonferr trend filter
  stats.py                  perf_metrics, yearly_returns, event_returns, regime_returns, block_bootstrap, etc.
  reports.py                Console output (9 tables) + JSON/CSV persistence
  excel_export.py           11-sheet formatted Excel report
  markdown_report.py        GitHub-renderable Markdown report
  pipeline.py               6-step orchestration
```

### The 6-step pipeline (`pipeline.py`)

1. `step_1_load_data` — load 9-asset panel, compute daily returns
2. `step_2_run_backtests` — V3c (fixed) + V3-B 20d (5-bucket HRP) + V3-B 保守增强(20d) (IV), each × 3 cash tiers = 9 backtests
3. `step_3_compute_metrics` — perf / yearly / risk contribution / regime / event / rolling stats
4. `step_4_bootstrap` — 1000×5yr block bootstrap (21-day blocks). V3-B uses last-window proxy weights.
5. `step_5_print_reports` — console output
6. `step_6_save_outputs` — CSV/JSON/Excel/Markdown

### 3 strategies (2026-05-26)

- **V3c 多元** ★★★: Fixed weights (defined in `portfolios.py::WEIGHTS`). Monthly rebalancing + nonferr trend filter 60d. "实战派" — simple to execute, CAGR 7.76%, MDD -4.68%.
- **V3-B 风险平价(20d)** ★★★: 5-bucket hierarchical RP (10Y/30Y split) monthly rebalance, 20d lookback + nonferr trend filter 75d + gold dip-buying (15% DD threshold, 2.0x boost) + hs300 dip-buying (35% DD threshold, 2.0x boost). "学院派" — best CAGR (9.24%), best cumulative return, MDD -4.14%, Sharpe 1.80.
- **V3-B 保守增强(20d)** ★★★: Inverse vol weighting (no bucket hierarchy) + nonferr trend filter 75d SMA + gold/hs300 dip-buying, 20d window, max_w=0.25. "保守派" — lowest MDD (-3.57%), highest Sharpe (2.05).

### Fixed-weight vs dynamic rebalancing

- **V3c**: `REBAL_FREQ="ME"` (monthly) + nonferr trend filter 60d. Code: `backtest.py::backtest`.
- **V3-B**: No fixed weights. Every month: 5 macro buckets equal-weighted (20% each), within-bucket inverse-vol weights. 10Y/30Y bonds split into separate buckets. Code: `strategy_b.py::backtest_b`.

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

### 9 assets / 5 macro buckets

| Bucket | Assets |
|--------|--------|
| 增长↑ | hs300, div_idx, us_sp500 |
| 收益垫 | credit |
| 增长↓10Y | bond_10y |
| 增长↓30Y | bond_30y |
| 通胀↑ | gold, nonferr, soymeal |

Defined in `config.py::BUCKET_GROUPS`. 10Y/30Y split is the key improvement over classic 4-bucket structure — the two bonds have vastly different duration (~8 vs ~18 years) and deserve independent risk allocation.

## Important constants (all in `config.py`)

| Constant | Value | Purpose |
|---|---|---|
| `BACKTEST_START/END` | 2015-01-01 / 2025-12-31 | ~11 year window |
| `REBAL_FREQ` | "ME" | Monthly rebalance (V3c) |
| `REBAL_THRESHOLD` | 0.03 | 3% deviation trigger |
| `RISK_FREE_ANNUAL` | 0.022 | Sharpe correction |
| `RISK_PARITY_WINDOW` | 20 | V3-B 20d lookback (trading days) |
| `RISK_PARITY_MAX_WEIGHT` | 0.25 | Single asset cap in V3-B |
| `RISK_PARITY_MIN_WEIGHT` | 0.02 | Single asset floor in V3-B |
| `BOND_30Y_AMP` | 3.0 | Fallback duration multiplier |
| `GOLD_DIP_THRESHOLD` | 0.15 | Gold dip-buy trigger (15% DD from peak) |
| `GOLD_DIP_BOOST` | 2.0 | Gold weight boost multiplier when triggered |
| `HS300_DIP_THRESHOLD` | 0.35 | hs300 dip-buy trigger (35% DD, catastrophic only) |
| `HS300_DIP_BOOST` | 2.0 | hs300 weight boost multiplier when triggered |
| `BOOTSTRAP_N_SIM` | 1000 | Monte Carlo iterations |
| `BOOTSTRAP_HORIZON_DAYS` | 1260 | 5-year horizon |
| `BOOTSTRAP_BLOCK_DAYS` | 21 | ~1 month blocks |

## Documentation

- `PROJECT_HISTORY.md` — complete project memory for AI: decisions, rationale, metrics, timeline
- `README.md` — user-facing: quickstart, strategy quick-reference, directory map
- `docs/index.html` — full strategy document (Chinese), served on GitHub Pages
