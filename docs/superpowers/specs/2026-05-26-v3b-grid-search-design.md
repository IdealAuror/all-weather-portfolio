# V3-B 网格搜索优化 — 设计说明

## 背景

V3-B 分层风险平价当前硬编码了 bucket_method="equal"（4 桶各 25%）、窗口仅测过 60d/120d、资产上限固定 25%。桶间风险平价的代码在 risk.py 已实现但未使用，窗口和参数也未系统搜索。

## 目标

1. **首要**：巩固 V3-B 的回撤优势（当前 -6.29% 已是三策略最浅）
2. **次要**：探索方法论纯度（桶间风险平价是桥水原教旨做法）

## 改动范围

| 文件 | 改动 |
|------|------|
| `allweather/strategy_b.py` | `_compute_weights` 增加 `bucket_method` 参数透传 |
| `allweather/grid_search_b.py` | **新建**：独立网格搜索脚本，不污染主流程 |

其余文件（pipeline.py, config.py, risk.py, backtest.py）不动。

## 参数网格

| 参数 | 候选值 | 说明 |
|------|--------|------|
| `rp_window` | 30, 60, 90, 120, 180, 252 | 交易日，约 1.5 月 ~ 1 年 |
| `max_w` | 0.20, 0.25, 0.30 | 单资产权重上限 |
| `bucket_method` | "equal", "risk_parity" | 桶间等权 vs 桶间逆波动率 |
| `min_w` | 固定 0.02 | 下限不变 |

共 6 × 3 × 2 = 36 种参数组合。每种跑 3 档现金（100%/85%/70%）= 108 个回测。

## grid_search_b.py 流程

1. `load_panel()` 加载数据，算日收益
2. 遍历 36 种参数组合，每种调用 `backtest_b(rets, cash_ratio=0, rp_window=w, ...)` 跑 100% RP 档
3. 对每种组合调用 `perf_metrics(nv)` 拿 CAGR/vol/MDD/Sharpe/Calmar
4. 按 MDD 升序排序输出 Top 10
5. 识别 Pareto 前沿（MDD 和 CAGR 双目标下不被支配的组合）
6. 对 Pareto 最优组合补跑 85%/70% 档，输出完整三档指标

## 评估标准

- **主排序**：MDD 升序（回撤最浅排最前）
- **辅助列**：CAGR、Sharpe、Calmar
- **Pareto 前沿**：以 MDD 为 x 轴、CAGR 为 y 轴，输出非支配解

## 成功标准

- 找到至少一组参数使 MDD < -6.0% 且 CAGR ≥ 7.0%
- 或确认当前参数（60d, 25%, equal）已接近最优

## 不在范围内

- 桶内最小方差（方案 C）— 留待 B 结果出来再评估
- 修改 bucket 定义或资产映射
- 修改 pipeline 主流程
