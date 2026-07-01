<div align="center">

# Bridgewater All-Weather Portfolio · China Edition

[![Pages](https://img.shields.io/badge/docs-online-blue)](https://idealauror.github.io/all-weather-portfolio/)
[![License](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Backtest](https://img.shields.io/badge/backtest-2005--2026-green)]()
</div>

**English** | [中文](README-zh.md)

A risk-parity backtesting framework based on real China A-share/bond/commodity ETF data, covering **2005–2026 (~21 years of full bull-bear cycles)** with **3 deployable strategies**, each supporting 3-4 cash tiers (100% / 85% / 70% / Dynamic), totaling 11 backtests.

Online docs: [https://idealauror.github.io/all-weather-portfolio/](https://idealauror.github.io/all-weather-portfolio/)

> **For the full Chinese documentation** (strategy details, asset universe, metrics, tutorials) see [README-zh.md](README-zh.md).  
> **JoinQuant (聚宽) version** — paste-and-run single-file implementation: [joinquant/](joinquant/)


## Strategy Quick Reference

| Strategy | Style | CAGR | Max DD | Sharpe |
|----------|:-----:|:----:|:------:|:-----:|
| **V3-B Conservative(20d)** | Conservative Enhanced | ≥ 7% | ≤ -7% | ≥ 1.2 |
| **V3-B Risk Parity(20d)** | Aggressive | ≥ 8.5% | ≤ -9% | — |
| **V3c Multi-Asset** | Balanced | ≥ 8.5% | ≤ -8.5% | — |

> Sharpe ratio uses the modified formula `(CAGR - 2.2%) / vol`. MDD is maximum drawdown over full sample. CAGR is geometric annualized return.


## Getting Started

```bash
pip install -r requirements.txt
python main.py                         # Full backtest (auto incremental data + report)
# python main.py --force-fetch         # Force re-fetch all data
# python main.py --no-excel            # Skip Excel report
# python main.py --no-markdown         # Skip Markdown report
python -m allweather.rebalance         # Real-portfolio rebalancing
```

**Output files**:

| File | Description |
|------|-------------|
| `output/report.xlsx` | 11-sheet Excel report |
| `output/nv_curves.csv` | All nav curves in wide format |
| `output/weight_history_*.csv` | Weight history |
| `output/signal_log.csv` | Risk control signal log |
| `docs/charts/*.png` | 15 analysis charts |
| `docs/data.json` | Structured metrics (for frontend) |


## Project Layout

```
├── main.py                  # Entry point: full backtest
├── pyproject.toml
├── allweather/              # Core modules
│   ├── config.py            Constants
│   ├── data.py              Data loading + 30Y bond synthesis
│   ├── fetch.py             Data fetching via akshare
│   ├── backtest.py          Unified backtest engine
│   ├── strategy_b.py        V3-B engine (HRP + conservative)
│   ├── risk.py              Inverse vol / risk parity / trend filters
│   ├── stats.py             Performance metrics / Bootstrap / D_excess
│   ├── reports.py           Console output
│   ├── charts.py            15 chart generation
│   ├── rebalance.py         Real-portfolio rebalancing
│   └── pipeline.py          6-step pipeline orchestrator
├── data/                    # Historical data CSV
├── docs/                    # GitHub Pages
├── joinquant/               # JoinQuant (聚宽) implementation
└── output/                  # Auto-generated reports
```
