"""V3c 权重方案。"""
import pandas as pd
from .config import ASSETS

WEIGHTS = {}

PORTFOLIO_TAGS = {
    "V3c 多元":            {"stars": "★★★", "label": "简约派 — 6资产逆波动率 60d + nonferr 趋势过滤 + Gold/HS300抄底，去冗余提效"},
    "V3-B 风险平价(20d)":  {"stars": "★★★", "label": "学院派 — 5桶分层风险平价(10Y/30Y分拆) + nonferr 趋势过滤 + Gold/HS300抄底"},
    "V3-B 保守增强(20d)":  {"stars": "★★★", "label": "保守增强 — 逆波动率 20d 窗口 + nonferr 趋势过滤 + Gold/HS300抄底，Sharpe 最高"},
}


def get_weights():
    """返回 {方案名: pd.Series(对齐到 ASSETS 顺序)}。"""
    out = {}
    for name, w in WEIGHTS.items():
        s = pd.Series(w).reindex(ASSETS).fillna(0)
        assert abs(s.sum() - 1) < 1e-6, f"{name} 权重和={s.sum()}"
        out[name] = s
    return out
