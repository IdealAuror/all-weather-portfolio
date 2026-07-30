---
name: wti_trend_filter_adopted
description: WTI 75d 趋势过滤正式纳入 — 三策略全面改善，CAGR↑0.14-0.23pp，MDD↑0.61-0.78pp
metadata:
  type: project
---

## WTI 75d 趋势过滤正式纳入 (2026-07-30)

**背景：** WTI 是所有资产中唯一没有趋势过滤的，nonferr/gold/sp500/hs300 都有。

**实证结果：**

| 策略 | 变化 |
|------|------|
| V3-B Con | CAGR 8.09→8.26% MDD -5.92→-5.31% Sharpe 1.62→1.81 |
| V3-B RP | CAGR 8.81→8.95% MDD -6.46→-5.68% Sharpe 1.37→1.48 |
| V3c | CAGR 9.06→9.29% MDD -7.06→-6.28% Sharpe 1.47→1.65 |

三策略无 trade-off，收益↑波动↓回撤↓。

**经济学逻辑：** 油价价格趋势与期限结构高度重叠——升水（contango）伴随价格疲软，贴水（backwardation）伴随价格强势。趋势过滤在跌势中减仓，规避了 contango 环境下的移仓磨损。

**实施：** `backtest.py` 增加 `wti_trend_window` 参数，`pipeline.py` `_common` 中设为 75，与 nonferr 一致。

**Why:** 趋势过滤框架对商品资产一致有效，WTI 不应例外。

**How to apply:** 所有策略的 `_common` 中 `wti_trend_window=75`。若未来切换 WTI 底层工具，无需调整参数。