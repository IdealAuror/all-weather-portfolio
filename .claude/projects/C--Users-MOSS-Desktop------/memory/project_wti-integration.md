---
name: wti-integration
description: WTI 原油集成到三策略 — SMA75 趋势过滤后通过，MDD -0.70pp，通胀桶新增供给冲击维度
metadata:
  type: project
  node_type: memory
  originSessionId: 0fe37449-e136-4e18-a7b2-d5179d9ef8b2
---

## WTI 原油集成决策（2026-05-30）

经优化闭环验证后集成，但因实盘限制暂不活跃。

### 回测结论（技术面通过）

**裸加否决**：无趋势过滤时 CAGR -0.08pp，MDD -0.68pp 恶化。逆波动率框架给 WTI 仅 4.8% 权重，无法贡献有意义回报，但在 2008/2014 崩盘时仍足够拖累净值。

**SMA75 趋势过滤通过**：
- V3c 基准 vs 加 WTI：CAGR 8.47%→8.58%（+0.11pp），MDD -7.01%→-6.31%（-0.70pp）
- All 4 regimes improved, key crisis events improved
- 2009 原油反弹捕获 +2.27pp，2016 能源复苏 +1.78pp

**Why:** 原油在通胀↑桶中占据独特位置 — 供给冲击型通胀，与黄金（货币型）和有色金属（工业需求型）互补。经济逻辑清晰（非过拟合）。

### 实盘限制（2026-05）

**QDII 全线限购**：美伊冲突后 501018 自 2026-02-13 暂停申购，仅 C5 客户可买，场内溢价 30%+ 且多次临时停牌。161129/160723 同样限购。

**决策：暂不活跃。** 数据管道和引擎代码保留（`config.py` 中 V3C_ASSETS 和 `pipeline.py` 中调用已移除 WTI），待 QDII 额度放开后只需加回 3 处配置即可重新启用。

### 代码状态（备选就绪）

| 层 | 状态 |
|---|------|
| 数据管道 (`data.py`, `data/wti.csv`) | 保留，正常加载 |
| 引擎支持 (`backtest.py`, `strategy_b.py`) | 保留，equity_trend_windows 机制完整 |
| 配置常量 (`config.py`) | ASSETS/ETF_META/BUCKETS 保留；V3C_ASSETS/PORTFOLIO_TAGS 移除 |
| 回测调用 (`pipeline.py`) | 全部移除 |
| 文档 (README/CLAUDE/BACKTEST_RESULTS) | 标记为备选待QDII放开 |
