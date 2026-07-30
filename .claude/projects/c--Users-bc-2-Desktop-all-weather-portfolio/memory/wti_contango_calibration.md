---
name: wti_contango_calibration
description: WTI proxy 段 contango 拖累校准 — 501018 LOF 相对 WTI 期货年度差 -0.90%
metadata:
  type: reference
---

## WTI 回测数据校准 (2026-07-30)

**问题：** `_load_wti_cny()` 在 pre-2016 proxy 段用 WTI 期货 × USDCNY，之前 `annual_deduct=0.0` 未考虑期货移仓损耗，高估实盘可实现的 WTI 回报。

**实证校准：** 501018 LOF 与 WTI 期货 CNY 在 2016-06-15 ~ 2026-07-24 重合期（9.7 年）对比：
- 501018 CAGR: 6.28%
- WTI 期货 CNY CAGR: 7.17%
- **年度拖累: -0.90%**

**修改：** `data.py` `_load_wti_cny()` 中 `annual_deduct=0.0` → `0.009`

**组合影响：** 极小。V3-B RP CAGR 8.86%→8.81%(-0.05pp)，其余策略无明显变化。WTI 权重 5-15%，仅 proxy 段（~11 年）受影响。

**注意：** 逐年追踪误差波动大（2020 年 -24.8%，2022 年 +16.5%），-0.90% 是长期均值估计。

**Why:** 回测必须反映实盘可实现回报，WTI 期货 proxy 不扣移仓损耗会系统性高估 pre-2016 通胀桶收益。

**How to apply:** 若未来更换 WTI 底层工具（如新 ETF 上市），需重新校准 `annual_deduct`。
