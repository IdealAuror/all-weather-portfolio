"""V3b / V3c / V3d / V3-A 权重方案。"""
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
    "V3c 多元":            {"stars": "★★★", "label": "实战派 — 固定权重，11年回测最优"},
    "V3-B 风险平价(60d)":  {"stars": "★★★", "label": "学院派 — 分层风险平价，月度调仓（战术）"},
    "V3-B 风险平价(120d)": {"stars": "★★★", "label": "学院派 — 分层风险平价，长窗口（战略）"},
    "V3-B 保守增强(60d)":  {"stars": "★★★", "label": "保守增强 — risk_parity桶 + nonferr趋势过滤，Sharpe最优"},
}


def get_weights():
    """返回 {方案名: pd.Series(对齐到 ASSETS 顺序)}。"""
    out = {}
    for name, w in WEIGHTS.items():
        s = pd.Series(w).reindex(ASSETS).fillna(0)
        assert abs(s.sum() - 1) < 1e-6, f"{name} 权重和={s.sum()}"
        out[name] = s
    return out
