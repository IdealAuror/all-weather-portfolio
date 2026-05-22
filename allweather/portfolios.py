"""V3b / V3c / V3d 三套权重方案。"""
import pandas as pd
from .config import ASSETS

WEIGHTS = {
    "V3b 平衡": {
        "hs300":   0.05, "div_idx":  0.07, "us_sp500": 0.05, "credit":   0.05,
        "bond_10y":0.43, "bond_30y": 0.15,
        "gold":    0.10, "nonferr":  0.05, "soymeal":  0.05,
    },
    "V3c 多元": {
        "hs300":   0.04, "div_idx":  0.06, "us_sp500": 0.08, "credit":   0.05,
        "bond_10y":0.40, "bond_30y": 0.15,
        "gold":    0.10, "nonferr":  0.06, "soymeal":  0.06,
    },
    "V3d 商品偏重": {
        "hs300":   0.05, "div_idx":  0.07, "us_sp500": 0.05, "credit":   0.03,
        "bond_10y":0.40, "bond_30y": 0.13,
        "gold":    0.12, "nonferr":  0.075, "soymeal": 0.075,
    },
}

PORTFOLIO_TAGS = {
    "V3b 平衡":      {"stars": "★★",   "label": "备选 - 求最浅回撤者"},
    "V3c 多元":      {"stars": "★★★",  "label": "强烈推荐"},
    "V3d 商品偏重": {"stars": "★★",   "label": "备选 - 怕滞胀者"},
}


def get_weights():
    """返回 {方案名: pd.Series(对齐到 ASSETS 顺序)}。"""
    out = {}
    for name, w in WEIGHTS.items():
        s = pd.Series(w).reindex(ASSETS).fillna(0)
        assert abs(s.sum() - 1) < 1e-6, f"{name} 权重和={s.sum()}"
        out[name] = s
    return out
