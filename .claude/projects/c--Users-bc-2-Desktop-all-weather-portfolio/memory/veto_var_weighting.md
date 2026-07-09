---
name: veto-var-weighting
description: VaR-based weighting rejected — monthly horizon shows no left fat-tail, inverse-vol already conservative
metadata:
  type: project
---

# 否决：VaR 替代逆波动率加权

**日期：** 2026-07-09

**提案：** 用 VaR/CVaR 替代或补充逆波动率（σ），作为组合风险预算的基础。

**诊断方法：** 滚动 21 日（月频 horizon）计算 7 资产的 Parametric VaR 95% / Historical VaR 95% / CVaR 95%，比较 VaR Ratio（Hist/Param）。

**数据：** 2005-04-11 ~ 2026-05-29，~21 年。

**结果：**

| 资产 | VaR Ratio (95%) | 结论 |
|------|:---:|------|
| 10Y国债 | 1.00 | 恰好正态 |
| 30Y国债 | 0.99 | 恰好正态 |
| 标普500 | 0.97 | 稍微薄尾 |
| 有色 | 0.92 | 薄左尾 |
| 沪深300 | 0.90 | 最薄左尾 |
| 城投债 | 0.81 | 右偏 |
| 黄金 | 0.68 | 极端右偏 |

**结论：** 所有资产 VaR Ratio ≤ 1.0，正态假设高估了而非低估了月频左尾风险。逆波动率加权已是保守方案，替换为 VaR 会进一步稀释风险资产权重，推高债券占比，无收益改善逻辑。

**99% VaR 附注：** 1-in-100 月事件下 VaR Ratio > 1（HS300 1.19, Nonferr 1.28, SP500 1.49），但月频 99% 分位噪音太大，不适用于权重计算。

**Why:** 中国 A 股虽然日频波动剧烈，但在月度 horizon 上左尾并没有比正态分布更肥。正态假设给出的 Param VaR 已是保守上界。

**How to apply:** 继续使用逆波动率加权。若未来有人提议 VaR/CVaR 加权，直接引用此结论否决。

**99% ES 补充诊断 (2026-07-09)：** 在 1-in-100 月极端尾部，SP500 的 ES/Param=1.72（正态低估 72%），Nonferr=1.50，HS300=1.21。这验证了趋势过滤器的必要性——SP500 和非铁是尾部风险最大的资产，而趋势过滤在下跌时把它们切到 credit，提供了 σ 无法捕捉的非对称保护。结论升级为：

- **VaR/CVaR 替代 σ 做权重 → 否决**（95% VaR 层面无肥尾，99% ES 噪音太大）
- **ES 作为趋势过滤器的验证工具 → 保留**（ES/Param 越高的资产，趋势过滤越有价值）
- 诊断函数 `var_diagnostics()` 已加入 `stats.py`，后续评估新资产或新参数时可复用
