<div align="center">

# Bridgewater All-Weather Portfolio · China Edition

[![Pages](https://img.shields.io/badge/docs-online-blue)](https://idealauror.github.io/all-weather-portfolio/)
[![License](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Backtest](https://img.shields.io/badge/backtest-2005--2026-green)]()
</div>

<div align="center">

**English** | [中文](README-zh.md)

</div>

A risk-parity backtesting framework based on real China A-share/bond/commodity ETF data, covering **2005–2026 (~21 years of full bull-bear cycles)** with **3 deployable strategies**, each supporting 3-4 cash tiers (100% / 85% / 70% / Dynamic), totaling 11 backtests.

Online docs: [https://idealauror.github.io/all-weather-portfolio/](https://idealauror.github.io/all-weather-portfolio/)


## Strategy Quick Reference

| Strategy | Style | CAGR | Vol | Max DD | Sharpe | One-liner |
|----------|:-----:|:----:|:---:|:------:|:-----:|-----------|
| **V3-B Conservative(20d)** | Conservative Enhanced | **8.26%** | 3.62% | **-5.31%** | **1.81** | Inverse vol 20d + nonferr(75d) + HS300 AND dip |
| **V3-B Risk Parity(20d)** | Academic | 8.95% | 4.90% | -5.68% | 1.48 | 4-bucket equal HRP + nonferr/gold/sp500/hs300 trends + dip + target vol |
| **V3c Multi-Asset** | All-Weather | **9.29%** | 4.60% | -6.28% | 1.65 | 6-asset inverse vol 60d + nonferr/gold/sp500 trend(75d) + HS300 AND dip |

> V3-B RP 4 trend filters: nonferr(75d) + gold(75d) + sp500(75d) + hs300(30d); V3c 3 trend filters: nonferr(75d) + gold(75d) + sp500(75d). Both exclude bond_10y. All three strategies include crude oil (WTI 75d trend filter, default).

| | Positioning | CAGR | MDD | Core Constraint | Trend Filters | Negative Years |
|--|:-----------:|:---:|:---:|:--------------:|:-------------:|:--------------:|
| **V3-B Conservative** | Conservative defense | 7% | -7% | Sharpe 1.2 | 1 | See Chinese docs |
| **V3-B Risk Parity** | Aggressive return | 8.5% | -9% | CAGR priority | 4 | See Chinese docs |
| **V3c Multi-Asset** | Balanced core | 8.5% | -8.5% | Drawdown priority | 3 | See Chinese docs |

### How to Choose

| Your Situation | Pick |
|---------------|:----:|
| Retirement funds, can't lose principal, may need money anytime | **V3-B Conservative** |
| Long-term savings (5yr+), believe in all-weather, can stomach short-term volatility | **V3-B Risk Parity** |
| Seek high returns, embrace multi-asset diversification, understand trend filters | **V3c Multi-Asset** |


## Asset Universe

Based on Bridgewater's **four-quadrant macro exposure** framework, selecting from investable China ETFs:

| Bucket | Asset | Ticker | V3-B Con | V3-B RP | V3c |
|--------|-------|:------:|:--------:|:-------:|:---:|
| **Growth↑** | CSI 300 | 510300 | ✓ | ✓ | ✓ |
| | S&P 500 | 513500 | ✓ | ✓ | ✓ |
| **Income** | Municipal bond | 511220 | ✓ | ✓ | ✓ |
| **Growth↓ 10Y** | 10Y Treasury | 511260 | ✓ | — | — |
| **Growth↓ 30Y** | 30Y Treasury | 511130 | ✓ | ✓ | ✓ |
| **Inflation↑** | Gold | 518850 | ✓ | ✓ | ✓ |
| | Non-ferrous metals | 159980 | ✓ | ✓ | ✓ |
| | Crude oil (LOF) | 501018 | ✓ | ✓ | ✓ |

> V3c and V3-B RP exclude bond_10y (same growth↓ bucket as bond_30y, shorter duration, redundant contribution).
>
> 30Y Treasury ETF (511130) listed Mar 2024. Pre-listing data synthesized in 3 phases: **2005–2020** 10Y index × duration multiplier (×3.0), **2020–2024** spread method (10Y + term spread), **2024+** real data. Synthetic periods deduct 0.3% annualized.
>
> **Crude oil (Southern Crude Oil LOF 501018)**: default in all three strategies with a 75d trend filter — improves MDD by 1-2pp at a CAGR cost of 0.2-0.3pp, diversifying within the inflation bucket alongside gold and non-ferrous metals. Tradeable on-exchange as a LOF.

> **For exact live metrics** (CAGR, Vol, MDD, Sharpe) see the [Chinese README-zh.md](README-zh.md) — automatically updated after each backtest run.


## Getting Started

```bash
pip install -r requirements.txt
python main.py                         # Full backtest (auto incremental data + report)
# python main.py --force-fetch         # Force re-fetch all data
# python main.py --no-excel            # Skip Excel report
# python main.py --no-markdown         # Skip Markdown report
# 双击 streamlit_app/run.bat  打开 Web 再平衡面板
python -m allweather.rebalance         # CLI rebalancing (legacy)
```

**Output files**:

| File | Description |
|------|-------------|
| `output/report.xlsx` | 11-sheet Excel report |
| `output/nv_curves.csv` | All NAV curves in wide format |
| `output/weight_history_*.csv` | Weight history |
| `output/signal_log.csv` | Risk control signal log |
| `docs/charts/*.png` | 8 analysis charts |
| `docs/data.json` | Structured metrics (for frontend) |


## Backtest Limitations

- **30Y Treasury synthesis**: No real ETF data before Mar 2024 — 3-phase synthesis (duration multiplier → spread method → real data), synthetic period deducts 0.3% annualized
- **QDII quota**: S&P 500 (513500) subject to QDII limits — may trade at premium or suspend subscriptions under extreme conditions
- **Fee assumption**: Backtest uses price returns, excludes management/custodian fees (~0.5%/yr at ETF level); Sharpe ratio adjusted via risk-free rate
- **Execution risk**: Backtest assumes month-end close-price execution; real trading faces slippage and liquidity differences


## Project Layout

```
├── main.py                  # Entry point: full backtest
├── pyproject.toml
├── allweather/              # Core modules
│   ├── config.py            Constants
│   ├── types.py             Shared type definitions
│   ├── data.py              Data loading + 30Y bond synthesis
│   ├── fetch.py             Data fetching via akshare
│   ├── backtest.py          Unified backtest engine
│   ├── strategy_b.py        V3-B engine (HRP + conservative)
│   ├── risk.py              Inverse vol / risk parity / trend filters
│   ├── stats.py             Performance metrics / Bootstrap / D_excess
│   ├── reports.py           Console output
│   ├── charts.py            8 chart generation
│   ├── excel_export.py      Excel report
│   ├── markdown_report.py   Markdown report
│   ├── update_docs.py       README/CLAUDE.md/docs sync
│   ├── experiment_log.py    Experiment log
│   ├── rebalance.py         Real-portfolio rebalancing tool
│   └── pipeline.py          6-step pipeline orchestrator
├── streamlit_app/           # Web rebalancing panel
├── joinquant/               # JoinQuant platform implementations
├── portfolio_comparison/    # Multi-strategy comparison tool
├── data/                    # Historical data CSV
├── docs/                    # GitHub Pages
│   ├── index.html           Interactive report
│   ├── data.json            Structured metrics
│   ├── strategy-paper.md    Strategy design paper
│   └── charts/              Chart PNGs
└── output/                  # Auto-generated reports
```

## JoinQuant Edition

Three strategies ported to the [JoinQuant (聚宽)](https://www.joinquant.com/) platform — single-file paste-to-run, no local setup required.

| Strategy | Local CAGR | JQ CAGR | Diff | JQ MDD | JQ Sharpe |
|----------|:---------:|:---------:|:----:|:--------:|:----------:|
| **V3c Multi-Asset** | 9.21% | 9.50% | +0.29pp | −7.73% | 1.01 |
| **V3-B Conservative** | 8.69% | 7.99% | −0.70pp | −5.22% | 1.04 |
| **V3-B Risk Parity** | 10.03% | 10.23% | +0.20pp | −7.51% | 0.93 |

> JQ simplifications: HS300 dip-buying uses price-only (no PB/PE percentile), trend checks monthly not daily, backtest starts 2020. See `joinquant/comparison.md` for full comparison.

See `joinquant/` directory or [joinquant/README.md](joinquant/README.md).
