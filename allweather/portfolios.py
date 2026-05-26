"""V3c 权重方案。"""
import pandas as pd
from .config import ASSETS

WEIGHTS = {
    "V3c 多元": {
        "hs300":   0.04, "div_idx":  0.06, "us_sp500": 0.08, "credit":   0.05,
        "bond_10y":0.40, "bond_30y": 0.15,
        "gold":    0.10, "nonferr":  0.06, "soymeal":  0.06,
    },
}

PORTFOLIO_TAGS = {
    "V3c 多元":            {"stars": "★★★", "label": "实战派 — 固定权重月度再平衡 + nonferr 趋势过滤"},
    "V3-B 风险平价(20d)":  {"stars": "★★★", "label": "学院派 — 5桶分层风险平价(10Y/30Y分拆) + nonferr 趋势过滤"},
    "V3-B 保守增强(20d)":  {"stars": "★★★", "label": "保守增强 — 逆波动率 + nonferr 趋势过滤，Sharpe 最高"},
}


def get_weights():
    """返回 {方案名: pd.Series(对齐到 ASSETS 顺序)}。"""
    out = {}
    for name, w in WEIGHTS.items():
        s = pd.Series(w).reindex(ASSETS).fillna(0)
        assert abs(s.sum() - 1) < 1e-6, f"{name} 权重和={s.sum()}"
        out[name] = s
    return out
