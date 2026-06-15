"""测试回测引擎核心逻辑：趋势过滤、现金档位调整、全策略集成。"""
import numpy as np
import pandas as pd
import pytest
from allweather.backtest import _apply_trend_dip, adjust_nav_for_cash, backtest
from allweather.strategy_b import backtest_b
from allweather.backtest import backtest_iv


def make_price_array(n_days=100, n_assets=5):
    """生成模拟价格数组，每天+0.05% 趋势向上。"""
    np.random.seed(42)
    rets = np.random.normal(0.0005, 0.01, (n_days, n_assets))
    prices = np.ones((n_days, n_assets))
    for i in range(1, n_days):
        prices[i] = prices[i-1] * (1 + rets[i])
    return prices


def test_adjust_nav_for_cash_full():
    nv = pd.Series(np.linspace(1.0, 2.0, 253), index=pd.date_range("2024-01-01", periods=253))
    nv_cash = adjust_nav_for_cash(nv, cash_ratio=0.30)
    assert nv_cash.iloc[-1] < nv.iloc[-1]
    assert nv_cash.iloc[0] == 1.0


def test_adjust_nav_for_cash_no_cash():
    nv = pd.Series(np.linspace(1.0, 2.0, 253), index=pd.date_range("2024-01-01", periods=253))
    nv_cash = adjust_nav_for_cash(nv, cash_ratio=0.0)
    assert abs(nv_cash.iloc[-1] - nv.iloc[-1]) < 1e-10


class TestApplyTrendDip:
    """核心：_apply_trend_dip 是刚修复了 bug 的函数，必须覆盖。"""

    def setup_method(self):
        self.prices = make_price_array(100, 5)
        self.col_idx = {"asset1": 0, "asset2": 1, "credit": 2, "nonferr": 3, "sp500": 4}

    def test_nonferr_trend_filter_below_sma(self):
        """nonferr 价格低于 SMA → 清仓转 credit"""
        w = np.array([0.0, 0.0, 0.3, 0.2, 0.5])
        sma_params = {"nf_window": 75, "nf_sma": float(self.prices[80, 3] * 1.05),
                      "au_sma": None, "eq_smas": {}}
        dip = {"gold_trend": False, "gold_dip_threshold": None, "gold_dip_boost": 2.5,
               "gold_dip_cap": None, "gold_peak": 1.0, "gold_boosted": False,
               "gold_boosted_flag": False, "hs300_value_dip": False, "hs300_boost": None}
        result = _apply_trend_dip(w.copy(), self.prices, 80, self.col_idx, sma_params, dip, None)
        assert result[3] == 0.0, "nonferr 应被清仓"
        assert result[2] > 0.3, "credit 应接收 nonferr 权重"

    def test_nonferr_trend_filter_above_sma(self):
        """nonferr 价格高于 SMA → 不清仓"""
        w = np.array([0.0, 0.0, 0.3, 0.2, 0.5])
        sma_params = {"nf_window": 75, "nf_sma": float(self.prices[80, 3] * 0.95),
                      "au_sma": None, "eq_smas": {}}
        dip = {"gold_trend": False, "gold_dip_threshold": None, "gold_dip_boost": 2.5,
               "gold_dip_cap": None, "gold_peak": 1.0, "gold_boosted": False,
               "gold_boosted_flag": False, "hs300_value_dip": False, "hs300_boost": None}
        result = _apply_trend_dip(w.copy(), self.prices, 80, self.col_idx, sma_params, dip, None)
        assert result[3] > 0, "nonferr 应保持持仓"

    def test_equity_trend_filter_below_sma(self):
        """SP500 价格低于 SMA → 清仓转 credit (这是之前的 bug!)"""
        w = np.array([0.0, 0.0, 0.3, 0.0, 0.2])
        sma_params = {"nf_window": 75, "nf_sma": None,
                      "au_sma": None,
                      "eq_smas": {"sp500": float(self.prices[80, 4] * 1.05)}}
        dip = {"gold_trend": False, "gold_dip_threshold": None, "gold_dip_boost": 2.5,
               "gold_dip_cap": None, "gold_peak": 1.0, "gold_boosted": False,
               "gold_boosted_flag": False, "hs300_value_dip": False, "hs300_boost": None}
        result = _apply_trend_dip(w.copy(), self.prices, 80, self.col_idx, sma_params, dip, None)
        assert result[4] == 0.0, "SP500 低于 SMA 应被清仓"
        assert result[2] > 0.3, "credit 应接收 SP500 权重"

    def test_equity_trend_filter_above_sma(self):
        """SP500 价格高于 SMA → 不清仓 (之前的 bug: 无论价格如何都清仓)"""
        w = np.array([0.0, 0.0, 0.3, 0.0, 0.2])
        sma_params = {"nf_window": 0, "nf_sma": None, "au_sma": None,
                      "eq_smas": {"sp500": float(self.prices[80, 4] * 0.95)}}
        dip = {"gold_trend": False, "gold_dip_threshold": None, "gold_dip_boost": 2.5,
               "gold_dip_cap": None, "gold_peak": 1.0, "gold_boosted": False,
               "gold_boosted_flag": False, "hs300_value_dip": False, "hs300_boost": None}
        result = _apply_trend_dip(w.copy(), self.prices, 80, self.col_idx, sma_params, dip, None)
        assert result[4] > 0, "SP500 高于 SMA 应保持持仓 (这是之前 bug 的关键测试)"

    def test_eq_sma_not_in_index(self):
        """eq_smas 中的资产不在 col_idx 中 → 忽略，不报错"""
        w = np.array([0.0, 0.2, 0.3, 0.0, 0.5])
        sma_params = {"nf_window": 0, "nf_sma": None, "au_sma": None,
                      "eq_smas": {"nonexistent": 1.5}}
        dip = {"gold_trend": False, "gold_dip_threshold": None, "gold_dip_boost": 2.5,
               "gold_dip_cap": None, "gold_peak": 1.0, "gold_boosted": False,
               "gold_boosted_flag": False, "hs300_value_dip": False, "hs300_boost": None}
        result = _apply_trend_dip(w.copy(), self.prices, 80, self.col_idx, sma_params, dip, None)
        assert abs(result.sum() - w.sum()) < 1e-10, "总和不应变化"

    def test_no_credit_no_transfer(self):
        """credit 不在组合中 → eq_smas 块跳过（credit_idx<0）"""
        col_idx_no_credit = {"asset1": 0, "sp500": 1, "nonferr": 2}
        w = np.array([0.3, 0.3, 0.4])
        sma_params = {"nf_window": 0, "nf_sma": None,
                      "au_sma": None, "eq_smas": {"sp500": 1000.0}}
        dip = {"gold_trend": False, "gold_dip_threshold": None, "gold_dip_boost": 2.5,
               "gold_dip_cap": None, "gold_peak": 1.0, "gold_boosted": False,
               "gold_boosted_flag": False, "hs300_value_dip": False, "hs300_boost": None}
        result = _apply_trend_dip(w.copy(), self.prices, 80, col_idx_no_credit, sma_params, dip, None)
        assert result[1] == 0.3

    def test_post_process_max_w_clips(self):
        """post_process_max_w 应截断极端权重"""
        w = np.array([0.1, 0.6, 0.3, 0.0, 0.0])
        sma_params = {"nf_window": 0, "nf_sma": None, "au_sma": None, "eq_smas": {}}
        dip = {"gold_trend": False, "gold_dip_threshold": None, "gold_dip_boost": 2.5,
               "gold_dip_cap": None, "gold_peak": 1.0, "gold_boosted": False,
               "gold_boosted_flag": False, "hs300_value_dip": False, "hs300_boost": None}
        result = _apply_trend_dip(w.copy(), self.prices, 80, self.col_idx, sma_params, dip,
                                   post_process_max_w=0.4)
        assert result[1] < 0.55, f"权重应被显著截断, got {result[1]:.4f}"

    def test_gold_trend_filter_below_sma(self):
        """黄金趋势过滤: 价格低于 SMA → 清仓转 credit"""
        w = np.array([0.0, 0.0, 0.3, 0.0, 0.0])
        col_idx_gold = {"asset1": 0, "credit": 1, "gold": 2}
        prices = make_price_array(100, 3)
        sma_params = {"nf_window": 0, "nf_sma": None,
                      "au_sma": float(prices[80, 2] * 1.05), "eq_smas": {}}
        dip = {"gold_trend": True, "gold_dip_threshold": None, "gold_dip_boost": 2.5,
               "gold_dip_cap": None, "gold_peak": 1.0, "gold_boosted": False,
               "gold_boosted_flag": False, "hs300_value_dip": False, "hs300_boost": None}
        result = _apply_trend_dip(w.copy(), prices, 80, col_idx_gold, sma_params, dip, None)
        assert result[2] == 0.0


# ============================================================
# 全策略集成测试（使用合成价格数据）
# ============================================================

BUCKETS_NOWTI = {
    "增长↑":   ["hs300", "us_sp500"],
    "收益垫":  ["credit"],
    "增长↓":   ["bond_30y"],
    "通胀↑":   ["gold", "nonferr"],
}
ASSETS_NOWTI = ["hs300", "us_sp500", "credit", "bond_30y", "gold", "nonferr"]
ASSETS_CON = ["hs300", "us_sp500", "credit", "bond_10y", "bond_30y", "gold", "nonferr"]


@pytest.fixture(scope="module")
def bt_rets(synthetic_prices):
    """Returns from synthetic prices (used by all integration tests)."""
    return synthetic_prices.pct_change().dropna()


class TestFullBacktest:
    """全链路集成测试：每个主力策略在合成数据上跑完整回测。"""

    @pytest.fixture(autouse=True)
    def setup(self, bt_rets, synthetic_pb_pe, synthetic_pct):
        self.rets = bt_rets
        self.pb_data, self.pe_data = synthetic_pb_pe
        self.pb_pct, self.pe_pct = synthetic_pct

    def test_v3b_rp_basic_invariants(self):
        """V3-B RP: NAV≥0, 有调仓, 有权重记录。"""
        nv, nv_dyn, n, wh, sl = backtest_b(
            self.rets[ASSETS_NOWTI],
            cash_ratio=0.0, rp_window=20,
            bucket_method="equal",
            max_w=0.20, min_w=0.02,
            rp_buckets=BUCKETS_NOWTI,
            nonferr_trend_window=75,
            gold_trend_filter=True, gold_trend_window=75,
            gold_dip_threshold=None,
            equity_trend_assets=["us_sp500", "hs300"],
            equity_trend_windows={"us_sp500": 75, "hs300": 30},
            hs300_value_dip=True,
            track_weights=True, track_signals=True,
            track_dynamic_nav=True,
            target_vol=0.09, vol_target_window=60,
            signal_label="V3-B RP",
            hs300_pb_data=self.pb_data, hs300_pe_data=self.pe_data,
            hs300_pb_pct=self.pb_pct, hs300_pe_pct=self.pe_pct,
        )
        assert nv.iloc[0] == pytest.approx(1.0)
        assert nv.iloc[-1] > 0.0
        assert n > 0, "应有调仓操作"
        assert len(wh) > 0, "应有权重记录"
        assert sl is not None

    def test_v3b_con_basic_invariants(self):
        """V3-B Con: NAV≥0, 有调仓, 有权重记录。"""
        nv, nv_dyn, n, wh, sl = backtest_b(
            self.rets[ASSETS_CON],
            cash_ratio=0.0, rp_window=20,
            max_w=0.25, min_w=0.03,
            weighting_method="inverse_vol",
            nonferr_trend_window=75,
            gold_dip_threshold=None, gold_dip_cap=0.20,
            hs300_value_dip=True,
            track_weights=True, track_signals=True,
            track_dynamic_nav=True,
            signal_label="V3-B Con",
            hs300_pb_data=self.pb_data, hs300_pe_data=self.pe_data,
            hs300_pb_pct=self.pb_pct, hs300_pe_pct=self.pe_pct,
        )
        assert nv.iloc[0] == pytest.approx(1.0)
        assert nv.iloc[-1] > 0.0
        assert n > 0
        assert len(wh) > 0
        assert sl is not None

    def test_v3c_basic_invariants(self):
        """V3c 多元: NAV≥0, 有调仓, 有权重记录。"""
        nv, _, n, wh, sl = backtest_iv(
            self.rets,
            cash_ratio=0.0, iv_window=60,
            max_w=0.30, min_w=0.03,
            assets=ASSETS_NOWTI,
            nonferr_trend_window=75,
            gold_trend_filter=True, gold_trend_window=75,
            gold_dip_threshold=None, gold_dip_cap=0.20,
            equity_trend_assets=["us_sp500"], equity_trend_window=75,
            hs300_value_dip=True,
            track_weights=True, track_signals=True,
            signal_label="V3c",
            hs300_pb_data=self.pb_data, hs300_pe_data=self.pe_data,
            hs300_pb_pct=self.pb_pct, hs300_pe_pct=self.pe_pct,
        )
        assert nv.iloc[0] == pytest.approx(1.0)
        assert nv.iloc[-1] > 0.0
        assert n > 0
        assert len(wh) > 0
        assert sl is not None

    def test_v3b_rp_cash_tiers(self):
        """V3-B RP: 多现金档位不崩溃，30% 现金降低 NAV。"""
        for c in [0.0, 0.15, 0.30]:
            nv_pass, _, _, _, _ = backtest_b(
                self.rets[ASSETS_NOWTI], cash_ratio=c,
                rp_window=20, bucket_method="equal",
                max_w=0.20, min_w=0.02, rp_buckets=BUCKETS_NOWTI,
                nonferr_trend_window=75,
                gold_trend_filter=True, gold_trend_window=75, gold_dip_threshold=None,
                equity_trend_assets=["us_sp500", "hs300"],
                equity_trend_windows={"us_sp500": 75, "hs300": 30},
                hs300_value_dip=False, track_dynamic_nav=True,
                target_vol=0.09, vol_target_window=60,
                signal_label="tier",
                hs300_pb_data=self.pb_data, hs300_pe_data=self.pe_data,
                hs300_pb_pct=self.pb_pct, hs300_pe_pct=self.pe_pct,
            )
            assert nv_pass.iloc[-1] > 0.0
        # verify adjust_nav_for_cash matches backtest's built-in cash
        nv0, _, _, _, _ = backtest_b(self.rets[ASSETS_NOWTI], cash_ratio=0.0,
            rp_window=20, bucket_method="equal", max_w=0.20, min_w=0.02,
            rp_buckets=BUCKETS_NOWTI,
            nonferr_trend_window=75, gold_trend_filter=True, gold_trend_window=75,
            gold_dip_threshold=None, equity_trend_assets=["us_sp500", "hs300"],
            equity_trend_windows={"us_sp500": 75, "hs300": 30},
            hs300_value_dip=False, track_dynamic_nav=True,
            target_vol=0.09, vol_target_window=60, signal_label="tier",
            hs300_pb_data=self.pb_data, hs300_pe_data=self.pe_data,
            hs300_pb_pct=self.pb_pct, hs300_pe_pct=self.pe_pct)
        nv30, _, _, _, _ = backtest_b(self.rets[ASSETS_NOWTI], cash_ratio=0.30,
            rp_window=20, bucket_method="equal", max_w=0.20, min_w=0.02,
            rp_buckets=BUCKETS_NOWTI,
            nonferr_trend_window=75, gold_trend_filter=True, gold_trend_window=75,
            gold_dip_threshold=None, equity_trend_assets=["us_sp500", "hs300"],
            equity_trend_windows={"us_sp500": 75, "hs300": 30},
            hs300_value_dip=False, track_dynamic_nav=True,
            target_vol=0.09, vol_target_window=60, signal_label="tier",
            hs300_pb_data=self.pb_data, hs300_pe_data=self.pe_data,
            hs300_pb_pct=self.pb_pct, hs300_pe_pct=self.pe_pct)
        assert nv30.iloc[-1] < nv0.iloc[-1], "现金档位应降低 NAV"
        # also verify adjust_nav_for_cash post-hoc matches
        nv_cash = adjust_nav_for_cash(nv0, 0.30)
        assert abs(nv_cash.iloc[-1] - nv30.iloc[-1]) / nv30.iloc[-1] < 0.01, "adjust_nav_for_cash 应与内置现金吻合"

    def test_v3b_rp_trend_filters_trigger(self):
        """V3-B RP: nonferr/gold 趋势过滤信号应有触发。"""
        _, _, _, _, sl = backtest_b(
            self.rets[ASSETS_NOWTI],
            cash_ratio=0.0, rp_window=20,
            bucket_method="equal",
            max_w=0.20, min_w=0.02,
            rp_buckets=BUCKETS_NOWTI,
            nonferr_trend_window=75,
            gold_trend_filter=True, gold_trend_window=75,
            gold_dip_threshold=None,
            equity_trend_assets=["us_sp500", "hs300"],
            equity_trend_windows={"us_sp500": 75, "hs300": 30},
            hs300_value_dip=False,
            track_signals=True,
            track_dynamic_nav=True,
            target_vol=0.09, vol_target_window=60,
            signal_label="test",
            hs300_pb_data=self.pb_data, hs300_pe_data=self.pe_data,
            hs300_pb_pct=self.pb_pct, hs300_pe_pct=self.pe_pct,
        )
        assert "nonferr_filtered" in sl.columns, "信号日志应有 nonferr 趋势过滤列"
        assert sl["nonferr_filtered"].sum() > 0, "nonferr 趋势过滤应有触发"


class TestParameterBoundaries:
    """参数边界测试：极端参数不崩溃。"""

    @pytest.fixture(autouse=True)
    def setup(self, bt_rets, synthetic_pb_pe, synthetic_pct):
        self.rets = bt_rets
        self.pb_data, self.pe_data = synthetic_pb_pe
        self.pb_pct, self.pe_pct = synthetic_pct

    def test_extreme_max_w(self):
        """max_w=1.0 不崩溃。"""
        nv, _, n, wh, sl = backtest_iv(
            self.rets,
            cash_ratio=0.0, iv_window=60,
            max_w=1.0, min_w=0.0,
            assets=ASSETS_NOWTI,
            nonferr_trend_window=75,
            gold_dip_threshold=None, gold_dip_cap=0.20,
            hs300_value_dip=False,
            track_weights=True,
            signal_label="extreme",
        )
        assert nv.iloc[-1] > 0.0

    def test_minimal_iv_window(self):
        """iv_window=5（最小值）不崩溃。"""
        nv, _, n, wh, sl = backtest_iv(
            self.rets,
            cash_ratio=0.0, iv_window=5,
            max_w=0.30, min_w=0.03,
            assets=ASSETS_NOWTI,
            nonferr_trend_window=0,
            gold_dip_threshold=None, gold_dip_cap=0.20,
            hs300_value_dip=False,
            track_weights=True,
            signal_label="min_win",
        )
        assert nv.iloc[-1] > 0.0

    def test_zero_nonferr_trend(self):
        """nonferr_trend_window=0（禁用趋势过滤）不崩溃。"""
        nv, _, n, wh, sl = backtest_iv(
            self.rets,
            cash_ratio=0.0, iv_window=60,
            max_w=0.30, min_w=0.03,
            assets=ASSETS_NOWTI,
            nonferr_trend_window=0,
            gold_dip_threshold=None, gold_dip_cap=0.20,
            hs300_value_dip=False,
            track_weights=True,
            signal_label="no_nf_trend",
        )
        assert nv.iloc[-1] > 0.0

    def test_extreme_min_w(self):
        """min_w=0.20（高底仓）不崩溃。"""
        nv, _, n, wh, sl = backtest_iv(
            self.rets,
            cash_ratio=0.0, iv_window=60,
            max_w=0.35, min_w=0.20,
            assets=ASSETS_NOWTI,
            nonferr_trend_window=75,
            gold_dip_threshold=None, gold_dip_cap=0.20,
            hs300_value_dip=False,
            track_weights=True,
            signal_label="high_min",
        )
        assert nv.iloc[-1] > 0.0

    def test_very_low_target_vol(self):
        """target_vol=0.01 接近 0 但不崩溃。"""
        nv, _, n, wh, sl = backtest_b(
            self.rets[ASSETS_NOWTI],
            cash_ratio=0.0, rp_window=20,
            bucket_method="equal",
            max_w=0.30, min_w=0.03,
            rp_buckets=BUCKETS_NOWTI,
            nonferr_trend_window=0,
            gold_trend_filter=False,
            gold_dip_threshold=None,
            hs300_value_dip=False,
            track_weights=True, track_signals=False,
            track_dynamic_nav=True,
            target_vol=0.01, vol_target_window=60,
            signal_label="low_vol",
        )
        assert nv.iloc[-1] > 0.0

    def test_all_filters_disabled(self):
        """全部趋势/抄底关闭，纯逆波动率。"""
        nv, _, n, wh, sl = backtest_iv(
            self.rets,
            cash_ratio=0.0, iv_window=60,
            max_w=0.30, min_w=0.03,
            assets=ASSETS_NOWTI,
            nonferr_trend_window=0,
            gold_trend_filter=False,
            gold_dip_threshold=None,
            hs300_value_dip=False,
            hs300_dip_threshold=None,
            track_weights=True,
            signal_label="plain_iv",
        )
        assert nv.iloc[-1] > 0.0
        assert n > 0


class TestSignalLogging:
    """信号日志完整性。"""

    @pytest.fixture(autouse=True)
    def setup(self, bt_rets, synthetic_pb_pe, synthetic_pct):
        self.rets = bt_rets
        self.pb_data, self.pe_data = synthetic_pb_pe
        self.pb_pct, self.pe_pct = synthetic_pct

    def test_signal_log_columns(self):
        """V3-B RP 信号日志包含预期列。"""
        _, _, _, _, sl = backtest_b(
            self.rets[ASSETS_NOWTI],
            cash_ratio=0.0, rp_window=20,
            bucket_method="equal",
            max_w=0.20, min_w=0.02,
            rp_buckets=BUCKETS_NOWTI,
            nonferr_trend_window=75,
            gold_trend_filter=True, gold_trend_window=75,
            gold_dip_threshold=None,
            equity_trend_assets=["us_sp500", "hs300"],
            equity_trend_windows={"us_sp500": 75, "hs300": 30},
            hs300_value_dip=False,
            track_signals=True,
            track_dynamic_nav=True,
            target_vol=0.09, vol_target_window=60,
            signal_label="sig_test",
        )
        expected = {"nonferr_filtered", "gold_filtered", "us_sp500_filtered", "hs300_filtered"}
        assert expected.issubset(sl.columns), f"缺少列: {expected - set(sl.columns)}"

    def test_dynamic_nav_increases_with_rebalance(self):
        """V3-B RP 动态 NAV 在调仓日应有变动。"""
        nv, nv_dyn, n, wh, sl = backtest_b(
            self.rets[ASSETS_NOWTI],
            cash_ratio=0.0, rp_window=20,
            bucket_method="equal",
            max_w=0.20, min_w=0.02,
            rp_buckets=BUCKETS_NOWTI,
            nonferr_trend_window=75,
            gold_trend_filter=True, gold_trend_window=75,
            gold_dip_threshold=None,
            equity_trend_assets=["us_sp500", "hs300"],
            equity_trend_windows={"us_sp500": 75, "hs300": 30},
            hs300_value_dip=False,
            track_dynamic_nav=True,
            target_vol=0.09, vol_target_window=60,
            signal_label="dyn_nav",
        )
        assert nv_dyn is not None
        assert nv_dyn.iloc[0] == pytest.approx(1.0)
        # 动态 NAV ≠ 基础 NAV（有 target_vol 调整）
        assert not nv_dyn.equals(nv)
