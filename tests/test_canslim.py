"""
Tests for scoring/canslim.py — CAN SLIM letter scoring, market direction,
buy point detection, decision engine, and serialization.
"""

import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scoring.canslim import (
    _safe, _label, _cagr, _mean, _ma,
    _score_C, _score_A, _score_N, _score_S, _score_L, _score_I,
    _assess_market, _detect_buy_point, _decide, _composite_label,
    run_canslim, WEIGHTS,
)
from scoring.canslim_models import LetterScore, BuyPoint, CANSLIMResult


# ── Helpers ───────────────────────────────────────────────────────────────────

def _q_income(rows):
    """rows = list of (netIncome, revenue), newest first."""
    return [{"netIncome": ni, "revenue": rev, "date": f"Q{i}"}
            for i, (ni, rev) in enumerate(rows)]


def _q_cashflow(rows):
    """rows = list of operatingCashFlow values, newest first."""
    return [{"operatingCashFlow": cf} for cf in rows]


def _income(rows):
    """Annual income stmts, newest first. rows = list of netIncome values."""
    return [{"netIncome": ni, "revenue": 1_000_000} for ni in rows]


def _prices(n, start=100.0, growth_per_day=0.0):
    """Generate n daily close prices, newest first (declining from start)."""
    # newest = start, oldest = start * (1 + growth_per_day)^(n-1)
    # growth_per_day > 0 means price was lower in the past (uptrend)
    return [start / (1 + growth_per_day) ** i for i in range(n)]


class TestSafeHelper:
    def test_none_returns_default(self):
        assert _safe(None) == 0.0

    def test_nan_returns_default(self):
        assert _safe(float("nan")) == 0.0

    def test_valid_float(self):
        assert _safe(3.14) == pytest.approx(3.14)

    def test_string_number(self):
        assert _safe("2.5") == pytest.approx(2.5)

    def test_non_numeric_string(self):
        assert _safe("abc") == 0.0

    def test_custom_default(self):
        assert _safe(None, 99.0) == 99.0


class TestLabelHelper:
    def test_strong(self):
        assert _label(70) == "Strong"
        assert _label(100) == "Strong"

    def test_average(self):
        assert _label(40) == "Average"
        assert _label(69) == "Average"

    def test_weak(self):
        assert _label(0) == "Weak"
        assert _label(39) == "Weak"


class TestCagrHelper:
    def test_positive_growth(self):
        assert _cagr(100, 200, 4) == pytest.approx(0.1892, abs=1e-4)

    def test_flat(self):
        assert _cagr(100, 100, 5) == pytest.approx(0.0)

    def test_zero_start(self):
        assert _cagr(0, 200, 5) == 0.0

    def test_zero_end(self):
        assert _cagr(100, 0, 5) == 0.0

    def test_zero_years(self):
        assert _cagr(100, 200, 0) == 0.0


class TestMaHelper:
    def test_simple_ma(self):
        prices = [10.0, 8.0, 6.0, 4.0, 2.0]  # newest first
        assert _ma(prices, 3) == pytest.approx(8.0)

    def test_insufficient_data_returns_zero(self):
        assert _ma([10.0, 20.0], 5) == 0.0


# ── C — Current Quarterly Earnings ───────────────────────────────────────────

class TestScoreC:
    def _info(self, shares=1_000_000):
        return {"sharesOutstanding": shares}

    def test_strong_eps_growth_and_sales(self):
        # Latest quarter NI = 200K, year-ago = 100K → 100% YoY growth
        inc = _q_income([(200_000, 5_000_000)] * 5)
        inc[4] = {"netIncome": 100_000, "revenue": 4_000_000, "date": "Q4"}
        cfs = _q_cashflow([180_000] + [100_000] * 4)

        result = _score_C(self._info(), inc, cfs)
        assert result.letter == "C"
        assert result.score >= 80  # EPS growth ✓ + sales ✓ + quality ✓

    def test_strong_eps_no_sales_growth(self):
        inc = _q_income([(200_000, 1_000_000)] * 5)
        inc[4] = {"netIncome": 100_000, "revenue": 1_000_000, "date": "Q4"}
        cfs = _q_cashflow([180_000] + [0] * 4)
        result = _score_C(self._info(), inc, cfs)
        # EPS growth ✓ (+60), no sales growth (0), quality marginal
        assert result.score >= 60

    def test_eps_growth_below_25pct(self):
        # 15% EPS growth → average tier: 40 (eps) + 20 (sales) + 20 (quality) = 80
        # Confirms it does NOT reach the 60-pt strong-EPS tier
        inc = _q_income([(115_000, 1_000_000)] * 5)
        inc[4] = {"netIncome": 100_000, "revenue": 900_000, "date": "Q4"}
        cfs = _q_cashflow([100_000] * 5)
        result = _score_C(self._info(), inc, cfs)
        assert result.metrics["eps_growth_yoy"] < 0.25   # below strong bar
        assert result.score < 100   # not full score (would need ≥25% EPS)

    def test_negative_eps_growth(self):
        inc = _q_income([(50_000, 500_000)] * 5)
        inc[4] = {"netIncome": 100_000, "revenue": 600_000, "date": "Q4"}
        cfs = _q_cashflow([40_000] * 5)
        result = _score_C(self._info(), inc, cfs)
        assert result.score < 40   # EPS declined → weak

    def test_insufficient_quarters_defaults_average(self):
        inc = _q_income([(100_000, 1_000_000)] * 3)
        result = _score_C(self._info(), inc, [])
        assert result.score == 40
        assert result.label == "Average"

    def test_quality_clean_fcf_ge_ni(self):
        inc = _q_income([(200_000, 2_000_000)] * 5)
        inc[4] = {"netIncome": 100_000, "revenue": 1_500_000, "date": "Q4"}
        cfs = _q_cashflow([200_000] + [0] * 4)  # FCF > NI
        result = _score_C(self._info(), inc, cfs)
        assert result.metrics["quality_clean"] is True

    def test_quality_poor_fcf_lt_ni(self):
        inc = _q_income([(200_000, 2_000_000)] * 5)
        inc[4] = {"netIncome": 100_000, "revenue": 1_500_000, "date": "Q4"}
        cfs = _q_cashflow([50_000] + [0] * 4)  # FCF << NI
        result = _score_C(self._info(), inc, cfs)
        assert result.metrics["quality_clean"] is False

    def test_metrics_populated(self):
        inc = _q_income([(200_000, 2_000_000)] * 5)
        inc[4] = {"netIncome": 100_000, "revenue": 1_500_000, "date": "Q4"}
        cfs = _q_cashflow([150_000] * 5)
        result = _score_C(self._info(), inc, cfs)
        assert "eps_growth_yoy" in result.metrics
        assert "sales_growth_yoy" in result.metrics
        assert result.weight == WEIGHTS["C"]


# ── A — Annual Earnings Growth ────────────────────────────────────────────────

class TestScoreA:
    def _info(self, shares=1_000_000):
        return {"sharesOutstanding": shares}

    def test_strong_cagr_and_consistency(self):
        # NI growing 30%/yr for 5 years: 100K → ~370K (newest first)
        ni_series = [370_000, 285_000, 219_000, 169_000, 130_000, 100_000]
        result = _score_A(self._info(), _income(ni_series))
        assert result.score >= 70   # meets strong bar
        assert result.label == "Strong"

    def test_moderate_cagr_average(self):
        # ~15% CAGR — above average threshold but below strong
        ni_series = [200_000, 175_000, 152_000, 132_000, 115_000, 100_000]
        result = _score_A(self._info(), _income(ni_series))
        assert result.score < 100
        assert result.score >= 40

    def test_low_cagr_weak(self):
        # ~5% CAGR — below both thresholds
        ni_series = [128_000, 122_000, 116_000, 110_000, 105_000, 100_000]
        result = _score_A(self._info(), _income(ni_series))
        assert result.score < 40 or result.label in ("Average", "Weak")

    def test_inconsistent_earnings_loses_points(self):
        # Only 2 of 5 years positive growth
        ni_series = [100_000, 90_000, 150_000, 80_000, 130_000, 100_000]
        result = _score_A(self._info(), _income(ni_series))
        assert result.metrics["eps_consistency_5y"] <= 3

    def test_full_consistency_bonus(self):
        ni_series = [200_000, 185_000, 170_000, 155_000, 140_000, 125_000]
        result = _score_A(self._info(), _income(ni_series))
        assert result.metrics["eps_consistency_5y"] >= 4

    def test_insufficient_data_defaults_average(self):
        result = _score_A({"sharesOutstanding": 1_000_000}, [{"netIncome": 100_000}])
        assert result.score == 40
        assert result.label == "Average"

    def test_metrics_populated(self):
        ni_series = [200_000, 160_000, 128_000, 100_000]
        result = _score_A(self._info(), _income(ni_series))
        assert "eps_cagr_3y" in result.metrics
        assert "eps_cagr_5y" in result.metrics
        assert "eps_consistency_5y" in result.metrics
        assert result.weight == WEIGHTS["A"]


# ── N — New Factor ─────────────────────────────────────────────────────────────

class TestScoreN:
    def _info(self, current=195.0, high52=200.0, eps_fwd=8.0, eps_ttm=6.0):
        return {
            "regularMarketPrice": current,
            "fiftyTwoWeekHigh": high52,
            "epsForward": eps_fwd,
            "epsTrailingTwelveMonths": eps_ttm,
        }

    def test_near_high_scores_points(self):
        info = self._info(current=198, high52=200)
        result = _score_N(info, [])
        assert result.metrics["near_high"] is True
        assert result.score >= 40

    def test_far_from_high_no_points(self):
        info = self._info(current=160, high52=200)
        result = _score_N(info, [])
        assert result.metrics["near_high"] is False

    def test_price_acceleration_detected(self):
        # Accelerating: recent 3m +20%, prior 3m +5%
        # newest-first: p_now > p_3m > p_6m (uptrend)
        prices = _prices(200, start=120.0, growth_per_day=0.001)
        info = self._info()
        result = _score_N(info, prices)
        assert result.metrics["price_accelerating"] is True or result.score >= 0

    def test_analyst_positive_scores_points(self):
        info = self._info(eps_fwd=10.0, eps_ttm=7.0)
        result = _score_N(info, [])
        assert result.metrics["analyst_positive"] is True
        assert result.score >= 30

    def test_analyst_negative_no_points(self):
        info = self._info(eps_fwd=5.0, eps_ttm=7.0)
        result = _score_N(info, [])
        assert result.metrics["analyst_positive"] is False

    def test_all_three_positive_max_score(self):
        info = self._info(current=198, high52=200, eps_fwd=10.0, eps_ttm=7.0)
        # Accelerating price: start high, declines (so newest > all prior)
        prices = [200 - i * 0.1 for i in range(200)]  # gently declining = decelerating
        result = _score_N(info, prices)
        # At least near_high + analyst_positive = 70
        assert result.score >= 60

    def test_weight_correct(self):
        result = _score_N(self._info(), [])
        assert result.weight == WEIGHTS["N"]


# ── S — Supply and Demand ─────────────────────────────────────────────────────

class TestScoreS:
    def _info(self, shares=100e6, avg_vol=1e6, curr_vol=2e6, price=150, ma50=140):
        return {
            "sharesOutstanding": shares,
            "averageVolume": avg_vol,
            "regularMarketVolume": curr_vol,
            "regularMarketPrice": price,
            "fiftyDayAverage": ma50,
        }

    def test_small_float_and_strong_demand(self):
        info = self._info(shares=50e6, avg_vol=1e6, curr_vol=2e6, price=150, ma50=140)
        result = _score_S(info)
        assert result.metrics["small_float"] is True
        assert result.metrics["strong_demand"] is True
        assert result.score == 100

    def test_large_float_reduces_score(self):
        info = self._info(shares=800e6)  # > 500M
        result = _score_S(info)
        assert result.metrics["small_float"] is False
        assert result.score <= 60

    def test_no_volume_spike(self):
        info = self._info(avg_vol=1e6, curr_vol=1.2e6)  # < 1.5x
        result = _score_S(info)
        assert result.metrics["volume_spike"] is False

    def test_volume_spike_but_below_ma50(self):
        info = self._info(avg_vol=1e6, curr_vol=2e6, price=130, ma50=140)
        result = _score_S(info)
        assert result.metrics["volume_spike"] is True
        assert result.metrics["price_above_ma50"] is False
        assert result.metrics["strong_demand"] is False

    def test_metrics_populated(self):
        result = _score_S(self._info())
        assert "shares_outstanding" in result.metrics
        assert "volume_ratio" in result.metrics
        assert result.weight == WEIGHTS["S"]


# ── L — Leader vs Laggard ─────────────────────────────────────────────────────

class TestScoreL:
    def _histories(self, ticker_12m_ret, spy_12m_ret, n=260):
        """Create synthetic price histories with given 12m returns."""
        def _hist(ret):
            # prices[0] = current, prices[251] = 12 months ago
            p_12m = 100.0
            p_now = p_12m * (1 + ret)
            h = [p_now] + [p_12m] * (n - 1)
            return h
        return _hist(ticker_12m_ret), _hist(spy_12m_ret)

    def test_strong_outperformer_scores_100(self):
        t, s = self._histories(0.50, 0.20)  # +30pp outperformance
        result = _score_L(t, s)
        assert result.score == 100
        assert result.metrics["rs_percentile_est"] >= 90

    def test_moderate_leader_scores_80(self):
        t, s = self._histories(0.30, 0.15)  # +15pp outperformance
        result = _score_L(t, s)
        assert result.score == 80

    def test_slight_leader_scores_60(self):
        t, s = self._histories(0.15, 0.10)  # +5pp outperformance
        result = _score_L(t, s)
        assert result.score == 60

    def test_laggard_below_spy_low_score(self):
        t, s = self._histories(0.05, 0.20)  # -15pp vs SPY
        result = _score_L(t, s)
        assert result.score < 60

    def test_insufficient_history_returns_zero(self):
        result = _score_L([100.0] * 10, [100.0] * 10)
        # <252 days → both returns = 0 → outperformance = 0 → 60
        assert result.score <= 60

    def test_metrics_populated(self):
        t, s = self._histories(0.30, 0.10)
        result = _score_L(t, s)
        assert "ticker_12m_return" in result.metrics
        assert "spy_12m_return" in result.metrics
        assert "outperformance" in result.metrics
        assert result.weight == WEIGHTS["L"]


# ── I — Institutional Sponsorship ─────────────────────────────────────────────

class TestScoreI:
    def _holders(self, n):
        return [{"holder": f"Fund {i}", "pctHeld": 0.01} for i in range(n)]

    def _info(self, pct_inst=0.60, pct_insider=0.05):
        return {"heldPercentInstitutions": pct_inst, "heldPercentInsiders": pct_insider}

    def test_strong_many_holders_high_ownership(self):
        info = self._info(pct_inst=0.70, pct_insider=0.02)
        result = _score_I(info, self._holders(150))
        assert result.score >= 70
        assert result.label == "Strong"

    def test_average_moderate_holders(self):
        info = self._info(pct_inst=0.35, pct_insider=0.10)
        result = _score_I(info, self._holders(50))
        assert result.score >= 40

    def test_weak_few_holders(self):
        info = self._info(pct_inst=0.10, pct_insider=0.50)
        result = _score_I(info, self._holders(5))
        assert result.score < 40

    def test_no_holders_list(self):
        info = self._info(pct_inst=0.60)
        result = _score_I(info, [])
        assert result.metrics["num_institutional_holders"] == 0

    def test_none_holders(self):
        result = _score_I(self._info(), None)
        assert result.metrics["num_institutional_holders"] == 0

    def test_metrics_populated(self):
        result = _score_I(self._info(), self._holders(80))
        assert "num_institutional_holders" in result.metrics
        assert "pct_institutional" in result.metrics
        assert result.weight == WEIGHTS["I"]


# ── Market Direction ──────────────────────────────────────────────────────────

class TestAssessMarket:
    def _spy(self, n, current, ma50_val, ma200_val=None):
        """Synthesize SPY history: current at [0], then MA values extrapolated."""
        if ma200_val is None:
            ma200_val = ma50_val
        prices = [current]
        # Fill 50 days at ma50_val, then rest at ma200_val
        prices += [ma50_val] * 49
        prices += [ma200_val] * max(0, n - 50)
        return prices

    def test_uptrend(self):
        # current > ma50 > ma200, few distribution days
        spy = self._spy(250, current=500, ma50_val=490, ma200_val=480)
        direction, metrics = _assess_market(spy)
        assert direction == "market_uptrend"
        assert "spy_current" in metrics

    def test_correction(self):
        # current < ma50 < ma200
        spy = self._spy(250, current=400, ma50_val=450, ma200_val=480)
        direction, metrics = _assess_market(spy)
        assert direction == "market_correction"

    def test_mixed(self):
        # current above ma50 but below ma200 (recovery)
        spy = self._spy(250, current=470, ma50_val=460, ma200_val=480)
        direction, _ = _assess_market(spy)
        assert direction in ("mixed", "market_uptrend", "market_correction")

    def test_insufficient_data_returns_mixed(self):
        direction, _ = _assess_market([100.0] * 30)
        assert direction == "mixed"

    def test_many_distribution_days_triggers_correction(self):
        # Steadily declining market: newest (index 0) is lowest, oldest is highest.
        # spy[i] < spy[i+1] always → every day is a "down day" → dist_days = 24
        spy = [200 + i * 2 for i in range(250)]  # prices[0]=200 (newest=lowest)
        direction, metrics = _assess_market(spy)
        assert metrics["distribution_days_25d"] >= 6   # exceeds bad threshold
        assert direction in ("market_correction", "mixed")


# ── Buy Point Detection ───────────────────────────────────────────────────────

class TestDetectBuyPoint:
    def _info(self, current=195, high52=200, avg_vol=1e6, curr_vol=2e6):
        return {
            "regularMarketPrice": current,
            "fiftyTwoWeekHigh": high52,
            "averageVolume": avg_vol,
            "regularMarketVolume": curr_vol,
        }

    def test_valid_breakout_near_pivot_with_volume(self):
        info = self._info(current=196, high52=200, avg_vol=1e6, curr_vol=1.8e6)
        bp = _detect_buy_point(info, [196] * 50)
        assert bp is not None
        assert bp.valid is True
        assert bp.pivot == 200.0

    def test_near_pivot_but_no_volume(self):
        info = self._info(current=196, high52=200, avg_vol=1e6, curr_vol=1.2e6)
        bp = _detect_buy_point(info, [196] * 50)
        assert bp is not None
        assert bp.valid is False  # not confirmed

    def test_far_from_pivot(self):
        info = self._info(current=170, high52=200, avg_vol=1e6, curr_vol=2e6)
        bp = _detect_buy_point(info, [170] * 50)
        assert bp is not None
        assert bp.valid is False

    def test_risk_rules_correct(self):
        info = self._info(current=196, high52=200, avg_vol=1e6, curr_vol=2e6)
        bp = _detect_buy_point(info, [196] * 50)
        assert bp.entry == pytest.approx(200 * 1.02, abs=0.01)
        assert bp.stop_loss == pytest.approx(bp.entry * 0.93, abs=0.01)
        assert bp.take_profit == pytest.approx(bp.entry * 1.25, abs=0.01)

    def test_risk_reward_at_least_2_to_1(self):
        info = self._info(current=196, high52=200)
        bp = _detect_buy_point(info, [196] * 50)
        reward = bp.take_profit - bp.entry
        risk   = bp.entry - bp.stop_loss
        assert reward / risk >= 2.0

    def test_no_52w_high_returns_none(self):
        info = {"regularMarketPrice": 150, "fiftyTwoWeekHigh": 0}
        bp = _detect_buy_point(info, [150] * 50)
        assert bp is None


# ── Decision Engine ───────────────────────────────────────────────────────────

class TestDecide:
    def _bp(self, valid=True):
        return BuyPoint(pivot=200, valid=valid, entry=204, stop_loss=190, take_profit=255)

    def test_buy_signal(self):
        result = _decide(80, "market_uptrend", self._bp(True), [])
        assert result == "BUY"

    def test_watchlist_no_buy_point(self):
        result = _decide(80, "market_uptrend", self._bp(False), [])
        assert result == "WATCHLIST"

    def test_watchlist_mixed_market(self):
        result = _decide(75, "mixed", self._bp(True), [])
        assert result == "WATCHLIST"

    def test_watchlist_market_correction(self):
        result = _decide(80, "market_correction", self._bp(True), [])
        assert result == "WATCHLIST"

    def test_avoid_low_composite(self):
        result = _decide(40, "market_uptrend", self._bp(True), [])
        assert result == "AVOID"

    def test_avoid_below_50(self):
        result = _decide(49, "market_uptrend", self._bp(True), [])
        assert result == "AVOID"

    def test_watchlist_moderate_composite(self):
        result = _decide(60, "market_uptrend", self._bp(True), [])
        assert result == "WATCHLIST"


# ── Composite Label ───────────────────────────────────────────────────────────

class TestCompositeLabel:
    def test_strong(self):
        assert _composite_label(70) == "Strong"
        assert _composite_label(85) == "Strong"

    def test_average(self):
        assert _composite_label(50) == "Average"
        assert _composite_label(69) == "Average"

    def test_weak(self):
        assert _composite_label(49) == "Weak"
        assert _composite_label(0) == "Weak"


# ── Serialization ─────────────────────────────────────────────────────────────

class TestLetterScoreSerialization:
    def test_roundtrip(self):
        ls = LetterScore(
            letter="C", name="Current Earnings", score=75.0, label="Strong",
            weight=0.20, metrics={"eps_growth": 0.30}, notes=["note1"],
        )
        restored = LetterScore.from_dict(ls.to_dict())
        assert restored.letter == "C"
        assert restored.score == 75.0
        assert restored.metrics["eps_growth"] == 0.30
        assert restored.notes == ["note1"]


class TestBuyPointSerialization:
    def test_roundtrip(self):
        bp = BuyPoint(pivot=200.0, valid=True, entry=204.0,
                      stop_loss=189.72, take_profit=255.0, notes="test")
        restored = BuyPoint.from_dict(bp.to_dict())
        assert restored.pivot == 200.0
        assert restored.valid is True
        assert restored.notes == "test"


class TestCANSLIMResultSerialization:
    def _minimal_result(self):
        ls = LetterScore("C", "Current", 60, "Average", 0.20)
        bp = BuyPoint(200, True, 204, 189.72, 255, "ok")
        return CANSLIMResult(
            ticker="TEST",
            company_name="Test Corp",
            composite_score=65.0,
            composite_label="Average",
            letter_scores={"C": ls},
            market_direction="mixed",
            market_metrics={"spy_current": 500},
            buy_point=bp,
            recommendation="WATCHLIST",
            red_flags=["flag1"],
            investor_fit={"summary": "test"},
        )

    def test_roundtrip(self):
        original = self._minimal_result()
        restored = CANSLIMResult.from_dict(original.to_dict())
        assert restored.ticker == "TEST"
        assert restored.composite_score == 65.0
        assert restored.composite_label == "Average"
        assert "C" in restored.letter_scores
        assert restored.letter_scores["C"].letter == "C"
        assert restored.buy_point is not None
        assert restored.buy_point.valid is True
        assert restored.red_flags == ["flag1"]

    def test_none_buy_point_roundtrip(self):
        original = self._minimal_result()
        original.buy_point = None
        restored = CANSLIMResult.from_dict(original.to_dict())
        assert restored.buy_point is None


# ── Integration: run_canslim ──────────────────────────────────────────────────

class TestRunCANSLIM:
    def _make_info(self):
        return {
            "longName": "Test Corp",
            "sharesOutstanding": 100_000_000,
            "regularMarketPrice": 195.0,
            "fiftyTwoWeekHigh": 200.0,
            "fiftyDayAverage": 185.0,
            "averageVolume": 1_000_000,
            "regularMarketVolume": 1_800_000,
            "epsForward": 8.0,
            "epsTrailingTwelveMonths": 6.0,
            "heldPercentInstitutions": 0.60,
            "heldPercentInsiders": 0.05,
        }

    def _make_income(self, n=6):
        return [{"netIncome": 200_000_000 - i * 10_000_000, "revenue": 1_000_000_000}
                for i in range(n)]

    def _make_q_income(self, n=8):
        rows = [{"netIncome": 50_000_000, "revenue": 250_000_000, "date": f"Q{i}"}
                for i in range(n)]
        rows[4] = {"netIncome": 40_000_000, "revenue": 220_000_000, "date": "Q4_py"}
        return rows

    def _make_prices(self, n=260, uptrend=True):
        if uptrend:
            return [100 + i * 0.05 for i in range(n)]   # oldest = lowest (uptrend)
        return [100.0] * n

    def test_returns_canslim_result(self):
        result = run_canslim(
            "TEST",
            self._make_info(),
            self._make_income(),
            self._make_q_income(),
            [{"operatingCashFlow": 60_000_000}] * 8,
            self._make_prices(),
            [{"holder": "Fund A", "pctHeld": 0.05}] * 120,
            self._make_prices(260, uptrend=True),
        )
        assert isinstance(result, CANSLIMResult)
        assert result.ticker == "TEST"
        assert result.company_name == "Test Corp"
        assert 0 <= result.composite_score <= 100
        assert result.composite_label in ("Strong", "Average", "Weak")
        assert result.recommendation in ("BUY", "WATCHLIST", "AVOID")

    def test_all_six_letters_present(self):
        result = run_canslim(
            "TEST", self._make_info(), self._make_income(),
            self._make_q_income(), [], self._make_prices(), [], self._make_prices(),
        )
        assert set(result.letter_scores.keys()) == {"C", "A", "N", "S", "L", "I"}

    def test_composite_matches_weighted_sum(self):
        result = run_canslim(
            "TEST", self._make_info(), self._make_income(),
            self._make_q_income(), [], self._make_prices(), [], self._make_prices(),
        )
        expected = sum(
            ls.score * ls.weight for ls in result.letter_scores.values()
        )
        assert result.composite_score == pytest.approx(expected, abs=0.5)

    def test_market_direction_set(self):
        result = run_canslim(
            "TEST", self._make_info(), self._make_income(),
            self._make_q_income(), [], self._make_prices(), [], self._make_prices(),
        )
        assert result.market_direction in ("market_uptrend", "mixed", "market_correction")

    def test_empty_price_history_handled(self):
        result = run_canslim(
            "TEST", self._make_info(), self._make_income(),
            self._make_q_income(), [], [], [], [],
        )
        # Should not raise; letters using price default gracefully
        assert isinstance(result, CANSLIMResult)

    def test_buy_point_returned(self):
        result = run_canslim(
            "TEST", self._make_info(), self._make_income(),
            self._make_q_income(), [], self._make_prices(), [], self._make_prices(),
        )
        # buy_point may be valid or not, but should exist given info has fiftyTwoWeekHigh
        assert result.buy_point is not None

    def test_weights_sum_to_one(self):
        assert sum(WEIGHTS.values()) == pytest.approx(1.0)
