# 桥水全天候策略 · 中国版


[![Pages](https://img.shields.io/badge/docs-online-blue)](https://idealauror.github.io/all-weather-portfolio/)
[![License](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)

基于真实 A 股 / 债 / 商品 ETF 数据的全天候风险平价（Risk Parity）回测工程。回测期 2005-2026，覆盖 ~21 年完整牛熊周期。

在线文档: https://idealauror.github.io/all-weather-portfolio/

---

## 策略速查

| 方案 | 风格 | CAGR | 最大回撤 | Sharpe | 一句话 |
|---|---|---|---|---|---|
| **V3c 多元** | 简约派 | 8.47% | -7.01% | 1.47 | 6资产逆波动率 60d + nonferr 趋势 + HS300 AND 抄底 |
| **V3-B 风险平价(20d)** | 学院派 | **10.11%** | -9.48% | 1.39 | 4桶等权 RP + nonferr/gold/sp500 趋势 + Gold/HS300 抄底 — 回报最高 |
| **V3-B 保守增强(20d)** | 保守增强 | 7.17% | **-5.35%** | **1.45** | 逆波动率 + nonferr 趋势 + HS300 AND 抄底 |

> V3-B RP: nonferr(75d) + gold(75d) + sp500(120d) 三重趋势过滤 + Gold/HS300 抄底，月度调仓。
> V3c 和 B-Con: nonferr(75d) 趋势过滤 + HS300 AND 抄底。
> V3c = 6资产; B-RP = 6资产 4桶(无 bond_10y); B-Con = 7资产 5桶(含 bond_10y)。

### 策略评估

**V3c 多元 (简约派)**
- 6资产逆波动率 60d + nonferr 趋势过滤(75d) + HS300 AND 抄底
- 月度调仓，最简执行
- 适合: 初入全天候、不想研究桶逻辑、追求简单透明

**V3-B 风险平价(20d) (学院派)**
- 4桶等权 HRP + nonferr/gold/sp500 三重趋势过滤 + Gold/HS300 抄底
- 长期回报最高 CAGR 10.11%
- 适合: 长期持有者(5年+)、认同正统全天候理念、能承受短期波动

**V3-B 保守增强(20d) (保守增强)**
- 逆波动率 20d (max_w=0.25) + nonferr 趋势过滤 + HS300 AND 抄底
- 回撤最低(-5.35%)，Sharpe 最高(1.45)
- 适合: 保守资金、退休金、无法忍受大幅回撤

---

## 7 资产（活跃）+ 1 备选

| 桶 | 资产 | V3c | V3-B RP | V3-B Con |
|----|------|:---:|:-------:|:--------:|
| 增长↑ | hs300, us_sp500 | ✓ | ✓ | ✓ |
| 收益垫 | credit | ✓ | ✓ | ✓ |
| 增长↓10Y | bond_10y | — | — | ✓ |
| 增长↓30Y | bond_30y | ✓ | ✓ | ✓ |
| 通胀↑ | gold, nonferr | ✓ | ✓ | ✓ |
| 通胀↑备选 | ~~wti~~ *(QDII限购)* | — | — | — |

---

## 运行

```bash
pip install -r requirements.txt
python main.py                 # 全量回测
python main.py --fetch         # 拉数据 + 回测
python main.py --no-excel      # 跳过 Excel
python allweather.rebalance    # 实盘再平衡
```

---

## 许可

AGPL-3.0
