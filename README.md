# 桥水全天候策略 · 中国版

[![Backtest](https://github.com/IdealAuror/all-weather-portfolio/actions/workflows/backtest.yml/badge.svg)](https://github.com/IdealAuror/all-weather-portfolio/actions/workflows/backtest.yml)
[![Pages](https://img.shields.io/badge/docs-online-blue)](https://idealauror.github.io/all-weather-portfolio/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)

基于真实 A 股 / 债 / 商品 ETF 数据的风险平价（Risk Parity）回测工程。

📖 **在线阅读完整方案**：https://idealauror.github.io/all-weather-portfolio/

## 🚀 一键运行

```bash
# 用 uv（推荐，自动管理依赖）
uv run --with numpy --with pandas --with openpyxl python -X utf8 main.py

# 或者用本地 Python（需先 pip install）
pip install numpy pandas openpyxl
python main.py
```

跑完会在控制台看到 9 张报表（核心指标 / 分年 / 风险贡献 / 宏观情景 / 关键事件 / 滚动统计 / 蒙特卡洛 / 持仓 / 推荐），同时把以下文件写到 `output/`：

| 文件 | 说明 |
|---|---|
| `report.xlsx` | ⭐ Excel 多 sheet 综合报告（11 sheet，带格式 / 高亮 / 负数标红）|
| `report.md` | Markdown 综合报告（GitHub / IDE 直接渲染）|
| `nv_curves.csv` | 9 条净值曲线（3 策略 × 3 档现金，画图用）|
| `summary.json` | 核心指标（CI sanity check 也读这个）|
| `weights.csv` | 三策略权重 |

## 📋 命令行选项

```bash
python main.py                跑回测（默认输出 5 类文件）
python main.py --fetch        先补拉缺失数据再回测
python main.py --fetch-only   只拉数据不回测
python main.py --force-fetch  强制重拉所有数据（覆盖）
python main.py --no-excel     跳过 Excel 综合报告
python main.py --no-markdown  跳过 Markdown 综合报告
python main.py --help         查看完整帮助
```

> 数据已经预先拉好放在 `data/`，正常情况直接 `python main.py` 即可。

## 📁 目录结构

```
全季节策略/
├── main.py                     ⭐ 主入口
├── pyproject.toml              依赖声明
├── README.md                   本文件
├── 桥水全季节.docx              📄 最终方案文档
├── 桥水全季节.html              🌐 HTML 版本
│
├── allweather/                 核心包
│   ├── __init__.py
│   ├── config.py               常量：ETF 代码 / 桶定义 / 调仓参数
│   ├── data.py                 数据加载 + 30Y 国债合成
│   ├── fetch.py                数据拉取（akshare）
│   ├── portfolios.py           V3b/V3c/V3d 三套权重
│   ├── backtest.py             回测引擎（双触发再平衡）
│   ├── stats.py                收益统计 + 蒙特卡洛
│   ├── reports.py              控制台 / 文件报告
│   └── pipeline.py             6 步流水线编排
│
├── data/                       历史 CSV
├── results/                    早期回测中间结果
└── output/                     本次跑的输出（自动生成）
    ├── nv_curves.csv           9 条净值曲线
    ├── summary.json            核心指标汇总
    └── weights.csv             三策略权重
```

## 🎯 策略速查

| 方案 | 路线 | CAGR | 回撤 | Sharpe | 适合 |
|---|---|---|---|---|---|
| **V3c 多元** | 实战派 | 6.64% | -6.90% | 1.00 | 固定权重月度调仓+趋势过滤，简单落地 |
| **V3-B (20d)** | 学院派 | 8.48% | -8.19% | 1.24 | CAGR 最高，5桶RP+趋势过滤+Gold/HS300抄底 |
| **V3-B 保守增强(20d)** | 保守派 | 7.32% | -3.63% | 1.52 | 睡得着觉，回撤最低，Sharpe最优 |

> V3-B 5桶+Gold/HS300抄底 CAGR 领跑（8.48%）；V3c 月度调仓+趋势过滤（6.64%）；保守增强+Gold/HS300抄底 Sharpe 最高（1.52）。
>
> 回测期：2008-01 ~ 2025-12（~18 年）
> 调仓规则：全策略月度调仓 + nonferr 趋势过滤 + Gold/HS300 抄底

## 🔧 自定义

修改权重或参数直接改 `allweather/config.py` 或 `allweather/portfolios.py` 后重跑。

跑单步而非全流程：

```python
from allweather.pipeline import (
    step_1_load_data, step_2_run_backtests,
    step_3_compute_metrics, step_4_bootstrap,
    step_5_print_reports, step_6_save_outputs,
)

panel, rets = step_1_load_data()
weights, nv = step_2_run_backtests(rets)
# ...
```

## 🌿 分支规范

项目采用 Git Flow 分支策略：

- `main` — 生产分支，打 Tag 发版，**禁止直接 push**
- `develop` — 集成测试，feature/hotfix 合入后验证
- `feature/xxx` — 新功能开发，从 develop 拉，**回测通过后**提 PR 回合
- `hotfix/xxx` — 紧急修复，从 main 拉，修复合入 main+develop

提交遵循 Conventional Commits（`feat:` / `fix:` / `docs:` / `refactor:`）。详见 [CLAUDE.md](CLAUDE.md)。

## 📊 文档

详细策略论证、回测过程、风险提示、落地手册见：
- `桥水全季节.docx`
- `桥水全季节.html`（浏览器直接打开）
