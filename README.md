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
| **V3-B Conservative(20d)** | Conservative Enhanced | **≥ 7%** | ≤ 5% | **≤ -7%** | **≥ 1.2** | Inverse vol 20d + nonferr(75d) + HS300 AND dip |
| **V3-B Risk Parity(20d)** | Academic | ≥ 8.5% | ≤ 7% | ≤ -9% | — | 4-bucket equal HRP + nonferr/gold/sp500/hs300 trends + dip + target vol |
| **V3c Multi-Asset** | All-Weather | **≥ 8.5%** | ≤ 6% | ≤ -8.5% | — | 6-asset inverse vol 60d + nonferr/gold/sp500 trend(75d) + HS300 AND dip |

> V3-B RP 4 trend filters: nonferr(75d) + gold(75d) + sp500(75d) + hs300(30d); V3c 3 trend filters: nonferr(75d) + gold(75d) + sp500(75d). Both exclude bond_10y. Table shows **no-WTI** version (6 assets), see WTI comparison below.

| | Positioning | CAGR | MDD | Core Constraint | Trend Filters | Negative Years |
|--|:-----------:|:---:|:---:|:--------------:|:-------------:|:--------------:|
| **V3-B Conservative** | Conservative defense | ≥ 7% | ≤ -7% | Sharpe ≥ 1.2 | 1 | See Chinese docs |
| **V3-B Risk Parity** | Aggressive return | ≥ 8.5% | ≤ -9% | CAGR priority | 4 | See Chinese docs |
| **V3c Multi-Asset** | Balanced core | ≥ 8.5% | ≤ -8.5% | Drawdown priority | 3 | See Chinese docs |

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
| **Inflation↑** | Gold | 518880 | ✓ | ✓ | ✓ |
| | Non-ferrous metals | 159980 | ✓ | ✓ | ✓ |

> V3c and V3-B RP exclude bond_10y (same growth↓ bucket as bond_30y, shorter duration, redundant contribution).
>
> 30Y Treasury ETF (511130) listed Mar 2024. Pre-listing data synthesized in 3 phases: **2005–2020** 10Y index × duration multiplier (×3.0), **2020–2024** spread method (10Y + term spread), **2024+** real data. Synthetic periods deduct 0.3% annualized.
>
> **Crude oil (Southern Crude Oil LOF 501018)**: subscriptions currently suspended, not in main strategy set. See WTI comparison below.

## Appendix: WTI Comparison

Adding crude oil (Southern Crude Oil LOF 501018) to the 7-asset pool, key metrics comparison:

| Strategy | Version | CAGR | Vol | Max DD | Sharpe | Calmar |
|----------|:------:|:----:|:---:|:------:|:-----:|:------:|
| **V3-B Conservative** | No WTI | **≥ 7%** | ≤ 5% | ≤ -7% | **≥ 1.2** | — |
| | +WTI | slightly lower | slightly higher | **improved** | — | — |
| **V3-B Risk Parity** | No WTI | ≥ 8.5% | ≤ 7% | ≤ -9% | — | — |
| | +WTI | slightly lower | — | **improved** | — | — |
| **V3c Multi-Asset** | No WTI | ≥ 8.5% | ≤ 6% | ≤ -8.5% | — | — |
| | +WTI | slightly lower | — | **improved** | — | — |

> Adding WTI reduces CAGR by ~0.2-0.3pp but improves MDD by 1-2pp. WTI diversifies within the inflation bucket alongside gold and non-ferrous metals. Subscription for 501018 currently suspended; WTI version can be enabled once resumed.

> **For exact live metrics** (CAGR, Vol, MDD, Sharpe) see the [Chinese README-zh.md](README-zh.md) — automatically updated after each backtest run.


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
| `output/nv_curves.csv` | All NAV curves in wide format |
| `output/weight_history_*.csv` | Weight history |
| `output/signal_log.csv` | Risk control signal log |
| `docs/charts/*.png` | 15 analysis charts |
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
│   ├── data.py              Data loading + 30Y bond synthesis
│   ├── fetch.py             Data fetching via akshare
│   ├── backtest.py          Unified backtest engine
│   ├── strategy_b.py        V3-B engine (HRP + conservative)
│   ├── risk.py              Inverse vol / risk parity / trend filters
│   ├── stats.py             Performance metrics / Bootstrap / D_excess
│   ├── reports.py           Console output
│   ├── charts.py            15 chart generation
│   ├── rebalance.py         Real-portfolio rebalancing tool
│   └── pipeline.py          6-step pipeline orchestrator
├── data/                    # Historical data CSV
├── docs/                    # GitHub Pages
│   ├── index.html           Interactive report
│   ├── data.json            Structured metrics
│   ├── strategy-paper.md    Strategy design paper
│   └── charts/              Chart PNGs
├── joinquant/               # JoinQuant platform implementation
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
