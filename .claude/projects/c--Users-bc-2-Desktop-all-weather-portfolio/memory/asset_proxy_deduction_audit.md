---
name: asset_proxy_deduction_audit
description: 全资产回测proxy扣减审计 — 8资产逐一核查，3个已扣减5个确认合理无需扣
metadata:
  type: reference
---

## 回测 Proxy 扣减全面审计 (2026-07-30)

逐一核查 8 资产在 ETF 上市前的 proxy 段是否存在系统性高估。

### 已扣减（3个）
- **bond_30y**: 0.3%/年 — 久期放大法的期权费率差（`SAFETY_DEDUCT`）
- **nonferr**: 0.5%/年 — 申万有色指数不含管理费、跟踪误差（`SAFETY_DEDUCT`）
- **wti**: 0.9%/年 — 501018 LOF vs WTI 期货实证追踪差（`annual_deduct`）

### 确认无需扣减（5个）
- **hs300**: 实物ETF跟踪误差 ~0.05%，管理费 0.15% 可忽略
- **us_sp500**: `.INX` 是价格指数不含分红（~1.5-2%/年），513500 ETF 管理费 0.80% 被分红超额覆盖。实证 ETF 跑赢 proxy +0.33%/年 — proxy 自然保守
- **credit**: 管理费 0.15%，proxy 段短
- **bond_10y**: 管理费 0.15%
- **gold**: 伦敦金×USDCNY proxy，跨境套利充分，价差极小；管理费 0.20%

**Why:** 回测必须反映实盘可实现回报。proxy 段不加扣减会高估，但也不应过度保守。

**How to apply:** 若更换底层 ETF 或新增资产，需重新做 ETF vs proxy 重合期实证对比。