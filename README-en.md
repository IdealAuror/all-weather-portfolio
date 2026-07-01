<div align="center">

# Bridgewater All-Weather Portfolio · China Edition

[![Pages](https://img.shields.io/badge/docs-online-blue)](https://idealauror.github.io/all-weather-portfolio/)
[![License](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Backtest](https://img.shields.io/badge/backtest-2005--2026-green)]()
</div>

<div align="center">

**English** | [中文](README.md)

</div>

A risk-parity backtesting framework based on real China A-share/bond/commodity ETF data, covering **2005–2026 (~21 years of full bull-bear cycles)** with **3 deployable strategies**.

Online docs: [https://idealauror.github.io/all-weather-portfolio/](https://idealauror.github.io/all-weather-portfolio/)

> **For the full Chinese documentation** (strategy details, asset universe, metrics, tutorials) see [README.md](README.md).

## Getting Started

```bash
pip install -r requirements.txt
python main.py                         # Full backtest (auto incremental data + report)
# python main.py --force-fetch         # Force re-fetch all data
# python main.py --no-excel            # Skip Excel report
# python main.py --no-markdown         # Skip Markdown report
python -m allweather.rebalance         # Real-portfolio rebalancing
```

## Project Layout

```
├── main.py                  # Entry point: full backtest
├── allweather/              # Core modules (backtest engine, risk parity, etc.)
├── data/                    # Historical data CSV
├── docs/                    # GitHub Pages interactive report
├── joinquant/               # JoinQuant platform implementation
└── output/                  # Auto-generated reports
```
