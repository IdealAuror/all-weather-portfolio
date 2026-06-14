"""测试逆波动率加权、分层风险平价、HS300 AND抄底。"""
import numpy as np
import pandas as pd
import pytest
from allweather.risk import (
    inverse_vol_weights,
    erc_weights,
    hierarchical_rp_weights,
    hs300_dip_check,
    _clip_normalize,
)


def test_clip_normalize():
    w = pd.Series({"a": 0.5, "b": 0.5})
    clipped = _clip_normalize(w, min_w=0.2, max_w=0.6)
    assert abs(clipped.sum() - 1.0) < 1e-10
    assert clipped.max() <= 0.6 * 1.001
    assert clipped.min() >= 0.2 * 0.999


def test_clip_normalize_large():
    w = pd.Series({"a": 0.9, "b": 0.1})
    clipped = _clip_normalize(w, min_w=0.2, max_w=0.6)
    assert abs(clipped.sum() - 1.0) < 1e-10
    assert clipped.max() <= 0.65, "极端权重应被有效截断"
    assert clipped.min() >= 0.2 * 0.999, "最小值应不低于 min_w"


def test_inverse_vol_weights_short_history():
    rets = pd.DataFrame({"a": [0.01] * 10, "b": [0.02] * 10})
    w = inverse_vol_weights(rets, window=5, max_w=0.25, min_w=0.02)
    assert len(w) == 2
    assert abs(w.sum() - 1.0) < 1e-10


def test_inverse_vol_weights_allocation():
    np.random.seed(42)
    n = 100
    low_vol = np.random.normal(0.001, 0.005, n)
    high_vol = np.random.normal(0.001, 0.03, n)
    rets = pd.DataFrame({"bond": low_vol, "equity": high_vol})
    w = inverse_vol_weights(rets, window=60, max_w=0.8, min_w=0.05)
    # Low-vol asset (bond) should get higher weight
    assert w["bond"] > w["equity"], "逆波动率应给低波动资产更高权重"


def test_hierarchical_rp_weights_returns_series():
    np.random.seed(42)
    n = 100
    data = {f"a{i}": np.random.normal(0.001, 0.02, n) for i in range(4)}
    rets = pd.DataFrame(data)
    buckets = {"bucket1": ["a0", "a1"], "bucket2": ["a2", "a3"]}
    w = hierarchical_rp_weights(rets, buckets, window=60, max_w=0.8, min_w=0.05)
    assert abs(w.sum() - 1.0) < 1e-10
    assert all(a in w.index for a in ["a0", "a1", "a2", "a3"])


def test_hierarchical_rp_equal_buckets():
    np.random.seed(42)
    n = 100
    rets = pd.DataFrame({
        "eq1": np.random.normal(0.001, 0.02, n),
        "eq2": np.random.normal(0.001, 0.02, n),
        "bd1": np.random.normal(0.0005, 0.005, n),
        "bd2": np.random.normal(0.0005, 0.005, n),
    })
    buckets = {"equity": ["eq1", "eq2"], "bond": ["bd1", "bd2"]}
    w = hierarchical_rp_weights(rets, buckets, window=60, max_w=0.8, min_w=0.02,
                                 bucket_method="equal")
    eq_w = w["eq1"] + w["eq2"]
    bd_w = w["bd1"] + w["bd2"]
    assert abs(eq_w + bd_w - 1.0) < 1e-10
    # Equal buckets → equity and bond should be close to 50% each
    assert abs(eq_w - bd_w) < 0.15, f"等权桶应使 equity({eq_w:.3f}) ≈ bond({bd_w:.3f})"


def test_hs300_dip_check_entry():
    """PB分位低 + 回撤深 + 价格在SMA上方 → 入场抄底"""
    idx = pd.date_range("2020-01-01", "2024-01-15", periods=1000)
    pb_data = pd.Series(np.random.rand(1000), index=idx)
    pe_data = pd.Series(np.random.rand(1000), index=idx)
    pb_pct = pd.Series({pd.Timestamp("2024-01-15"): 15.0})
    pe_pct = pd.Series({pd.Timestamp("2024-01-15"): 40.0})
    boosted, boost = hs300_dip_check(
        pb_data=pb_data, pe_data=pe_data,
        hs300_peak=150, hs300_boosted=False,  # peak=150, price=95 → dd=-36.7%
        threshold=0.25, exit_recovery=0.10,
        pb_entry=30, pe_exit=70, boost_mult=1.8,
        pb_pct_series=pb_pct, pe_pct_series=pe_pct,
        hs300_sma_val=90, hs300_price_val=95, date=pd.Timestamp("2024-01-15"),
    )
    assert boosted is True
    assert boost == 1.8


def test_hs300_dip_check_no_entry_high_pb():
    """PB分位高 → 不入场"""
    idx = pd.date_range("2020-01-01", "2024-01-15", periods=1000)
    pb_data = pd.Series(np.random.rand(1000), index=idx)
    pe_data = pd.Series(np.random.rand(1000), index=idx)
    pb_pct = pd.Series({pd.Timestamp("2024-01-15"): 50.0})
    pe_pct = pd.Series({pd.Timestamp("2024-01-15"): 40.0})
    boosted, boost = hs300_dip_check(
        pb_data=pb_data, pe_data=pe_data,
        hs300_peak=120, hs300_boosted=False,
        threshold=0.25, exit_recovery=0.10,
        pb_entry=30, pe_exit=70, boost_mult=1.8,
        pb_pct_series=pb_pct, pe_pct_series=pe_pct,
        hs300_sma_val=90, hs300_price_val=95, date=pd.Timestamp("2024-01-15"),
    )
    assert boosted is False
    assert boost is None


def test_hs300_dip_check_exit():
    """已入场 + 回撤恢复 + PE分位高 → 出场"""
    idx = pd.date_range("2020-01-01", "2024-06-01", periods=1100)
    pb_data = pd.Series(np.random.rand(1100), index=idx)
    pe_data = pd.Series(np.random.rand(1100), index=idx)
    pb_pct = pd.Series({pd.Timestamp("2024-06-01"): 20.0})
    pe_pct = pd.Series({pd.Timestamp("2024-06-01"): 80.0})
    boosted, boost = hs300_dip_check(
        pb_data=pb_data, pe_data=pe_data,
        hs300_peak=100, hs300_boosted=True,  # already boosted
        threshold=0.25, exit_recovery=0.10,
        pb_entry=30, pe_exit=70, boost_mult=1.8,
        pb_pct_series=pb_pct, pe_pct_series=pe_pct,
        hs300_sma_val=95, hs300_price_val=92, date=pd.Timestamp("2024-06-01"),
    )
    assert boosted is False
    assert boost is None


def test_dynamic_cash_ratio():
    from allweather.risk import dynamic_cash_ratio
    hs300 = pd.Series([1000, 1100, 800, 900, 950],
                      index=pd.date_range("2024-01-01", periods=5))
    # Deep drawdown (800/1100 - 1 = -27% < -20%) → 0% cash
    assert dynamic_cash_ratio(hs300, 2) == 0.0
    # Small drawdown (950/1100 - 1 = -14%) → 15% cash
    assert dynamic_cash_ratio(hs300, 4) == 0.15


def test_erc_weights_sums_to_one():
    """ERC 权重应归一化。"""
    np.random.seed(123)
    n = 200
    data = {f"a{i}": np.random.normal(0.001, 0.02, n) for i in range(5)}
    rets = pd.DataFrame(data)
    w = erc_weights(rets, window=120, max_w=0.50, min_w=0.01)
    assert abs(w.sum() - 1.0) < 1e-10
    assert w.max() <= 0.50
    assert w.min() >= 0.01


def test_erc_weights_low_vol_gets_more():
    """低波动资产在 ERC 中获得更高权重（因其风险贡献需要更大仓位来匹配）。"""
    np.random.seed(123)
    n = 200
    low_vol = np.random.normal(0.0005, 0.003, n)   # 年化 ≈ 5%
    high_vol = np.random.normal(0.0008, 0.012, n)  # 年化 ≈ 19%
    rets = pd.DataFrame({"bond": low_vol, "equity": high_vol})
    w = erc_weights(rets, window=120, max_w=0.90, min_w=0.01)
    # 低波动资产在 ERC 中应获得更大权重以匹配风险贡献
    assert w["bond"] > w["equity"], f"ERC 应给低波动 bond 更高权重，现 bond={w['bond']:.3f} equity={w['equity']:.3f}"


def test_erc_weights_short_history():
    """数据不足时应等权。"""
    rets = pd.DataFrame({"a": [0.01] * 5, "b": [0.02] * 5, "c": [0.005] * 5})
    w = erc_weights(rets, window=60)
    assert len(w) == 3
    assert abs(w.sum() - 1.0) < 1e-10
    # 历史太短，应近似等权
    assert abs(w["a"] - 1/3) < 0.1
