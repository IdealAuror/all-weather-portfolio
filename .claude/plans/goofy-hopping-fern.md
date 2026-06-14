# 计划：移除 CI011001 全天候策略

## 背景

CI011001 全天候复刻（ERC风险平价 + 目标波动率5% + bond_10y 2.5x杠杆）CAGR 仅 5.92%，与真实指数 8.12% 差距过大。同时高换手率（2.37x/年）使实盘执行成本不低。该策略回撤控制虽好，但回报不达预期，决定移除，简化阵容至三个策略：
- V3-B 保守增强(20d)
- V3-B 风险平价(20d)
- V3c 多元

## 改动清单

按 **config → strategy_b → pipeline → rebalance → reports → update_docs → excel_export** 顺序修改。

### 1. `allweather/config.py`
- 移除 `PORTFOLIO_TAGS` 中 `"CI011001 全天候"` 条目（第156行）
- 移除全部 `CI011001_*` 常量及注释块（第159~202行）
- 清理后文件以 `PORTFOLIO_TAGS` 结束

### 2. `allweather/strategy_b.py`
- 更新模块 docstring：`" + CI011001"` → `""`（第1行）
- 移除 CI011001 常量的 import（第10~13行）
- 移除 `backtest_ci011001()` 函数（第96~142行）

### 3. `allweather/pipeline.py`
- 移除从 config 的 CI011001 import（第23~25行）
- 移除 `backtest_ci011001` 的 import（第39行）
- 移除 CI011001 回测执行块（第140~159行）
- 简化条件分支：
  - 第197行：`("V3" in p or "CI011001" in p)` → `"V3" in p`
  - 第239行：`("V3" in portfolio or "CI011001" in portfolio)` → `"V3" in portfolio`
  - 移除第247~254行的 `elif "CI011001" in portfolio:` 分支（ERC bootstrap 路径）

### 4. `allweather/rebalance.py`
- 移除 `CI_ASSETS` 定义（第33行）
- 移除 `STRATEGIES` 中 `"CI"` 条目（第66~70行）
- 移除 `display_strategy_summary()` 中 CI011001 行（第499行）

### 5. `allweather/reports.py`
- 移除 `print_summary_recommendation()` 中 CI011001 推荐卡片（第307~313行）
- 更新"一句话选策略"行（第325行）：移除"要机构级 → CI011001"

### 6. `allweather/update_docs.py`
- 从 `STRAT_NAMES` 移除 `"CI011001 全天候"`（第12行）
- 从 `STRAT_MAP` 移除 `("CI011001 全天候", "CI")` 条目（第690行）

### 7. `allweather/excel_export.py`
- 从 notes 字典移除 CI011001 条目（第102行）
- 更新注脚（第118行）

### 8. 生成文件（无需手动清理，下次回测自动覆盖）
- `docs/data.json` — 含 CI011001 数据
- `docs/index.html` — 含 CI011001 数据
- `output/report.md` — 含 CI011001 章节
- `output/summary.json` — 含 CI011001 条目
- `experiments.jsonl` — 历史实验日志，保留不动

## 验证方法

1. `py main.py` — 全量回测无误，只输出 3 个策略
2. `python -m pytest tests/` — 全部通过
3. `python -m allweather.rebalance --signals` — 只显示 3 个策略选项
4. `python -m allweather.rebalance` — 提示 `选择策略 (B-RP/B-Con/V3c，回车=退出)`
5. 确认 docs/index.html 只显示 3 个策略卡片
