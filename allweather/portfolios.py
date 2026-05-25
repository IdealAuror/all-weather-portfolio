"""V3b / V3c / V3d / V3-A 权重方案。"""
import pandas as pd
from .config import ASSETS, ASSETS_PLAN_A

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
    "V3-A 保守": {
        "hs300":      0.04, "div_idx":  0.06, "us_sp500": 0.08, "credit":   0.05,
        "bond_10y":   0.25, "bond_30y": 0.10, "short_bond": 0.20,
        "gold":       0.10, "nonferr":  0.06, "soymeal":  0.06,
    },
}

PORTFOLIO_TAGS = {
    "V3b 平衡":        {"stars": "★★",   "label": "备选 - 长债58%防守"},
    "V3c 多元":        {"stars": "★★★",  "label": "强烈推荐 — 海外8%分散，Sharpe最高"},
    "V3d 商品偏重":   {"stars": "★★",   "label": "备选 - 商品27%抗滞胀"},
    "V3-A 保守":       {"stars": "★★",   "label": "备选 - 含20%短债，稳健保守"},
    "V3-B 风险平价(60d)":  {"stars": "★★★",  "label": "强烈推荐 — 分层风险平价，月度再平衡"},
    "V3-B 风险平价(120d)": {"stars": "★★★",  "label": "强烈推荐 — 长窗口风险平价，战略定位"},
}


def get_weights():
    """返回 {方案名: pd.Series(对齐到对应资产列表顺序)}。"""
    out = {}
    for name, w in WEIGHTS.items():
        asset_list = ASSETS_PLAN_A if "V3-A" in name else ASSETS
        s = pd.Series(w).reindex(asset_list).fillna(0)
        assert abs(s.sum() - 1) < 1e-6, f"{name} 权重和={s.sum()}"
        out[name] = s
    return out
