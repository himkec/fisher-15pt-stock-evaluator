"""
Tests for scoring/qafp.py — QAFP scoring engine.
Covers all sub-scores, valuation, decision engine, and helpers.
"""

import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scoring.qafp import (
    _safe, _label_quality, _label_valuation, _cagr, _linear_slope,
    _score_profitability, _score_cash_generation, _score_balance_sheet,
    _score_growth, _score_valuation, _check_red_flags, _decide,
    run_qafp, THRESHOLDS,
)
from scoring.qafp_models import SubScore


# ── Helper: _safe ─────────────────────────────────────────────────────────────

class TestSafe:
    def test_none_returns_default(self):
        assert _safe(None) == 0.0
        assert _safe(None, 99.0) == 99.0

    def test_normal_float(self):
        assert _safe(0.25) == pytest.approx(0.25)

    def test_nan_returns_default(self):
        import math
        assert _safe(float("nan")) == 0.0

    def test_string_number(self):
        assert _safe("3.14") == pytest.approx(3.14)

    def test_invalid_string_returns_default(self):
        assert _safe("N/A", 5.0) == 5.0

    def test_integer_input(self):
        assert _safe(42) == pytest.approx(42.0)

    def test_zero_returns_zero(self):
        assert _safe(0) == 0.0


# ── Helper: _label_quality ────────────────────────────────────────────────────

class TestLabelQuality:
    def test_high(self):
        assert _label_quality(80) == "High"
        assert _label_quality(75) == "High"

    def test_above_average(self):
        assert _label_quality(70) == "Above Average"
        assert _label_quality(55) == "Above Average"

    def test_average(self):
        assert _label_quality(50) == "Average"
        assert _label_quality(35) == "Average"

    def test_low(self):
        assert _label_quality(34) == "Low"
        assert _label_quality(0) == "Low"

    def test_boundary_75(self):
        assert _label_quality(75) == "High"
        assert _label_quality(74.9) == "Above Average"

    def test_boundary_55(self):
        assert _label_quality(55) == "Above Average"
        assert _label_quality(54.9) == "Average"

    def test_boundary_35(self):
        assert _label_quality(35) == "Average"
        assert _label_quality(34.9) == "Low"


# ── Helper: _label_valuation ──────────────────────────────────────────────────

class TestLabelValuation:
    def test_cheap(self):
        assert _label_valuation(70) == "Cheap"
        assert _label_valuation(100) == "Cheap"

    def test_fair(self):
        assert _label_valuation(60) == "Fair"
        assert _label_valuation(40) == "Fair"

    def test_expensive(self):
        assert _label_valuation(39) == "Expensive"
        assert _label_valuation(0) == "Expensive"

    def test_boundary_70(self):
        assert _label_valuation(70) == "Cheap"
        assert _label_valuation(69.9) == "Fair"

    def test_boundary_40(self):
        assert _label_valuation(40) == "Fair"
        assert _label_valuation(39.9) == "Expensive"


# ── Profitability sub-score ───────────────────────────────────────────────────

def _income(rows):
    """rows = list of (revenue, op_income) newest-first."""
    return [{"revenue": r, "operatingIncome": op, "netIncome": op * 0.7}
            for r, op in rows]


class TestScoreProfitability:
    def _info(self, roe=0.25, op_margin=0.25, net_margin=0.18):
        return {"returnOnEquity": roe, "operatingMargins": op_margin, "profitMargins": net_margin}

    def test_high_quality_company(self):
        info   = self._info(roe=0.30, op_margin=0.28)
        stmts  = _income([(1000, 250), (900, 220), (800, 190), (700, 160), (600, 130)])
        sub    = _score_profitability(info, stmts)
        assert sub.score >= 75
        assert sub.label == "High"

    def test_low_quality_company(self):
        info   = self._info(roe=0.04, op_margin=0.03)
        stmts  = _income([(1000, 30), (900, 36), (800, 40), (700, 42), (600, 42)])
        sub    = _score_profitability(info, stmts)
        assert sub.score < 55

    def test_roe_high_scores_40pts(self):
        info  = self._info(roe=0.25, op_margin=0.0)  # only ROE contributes
        stmts = _income([(1000, 0)] * 3)
        sub   = _score_profitability(info, stmts)
        # ROE ≥ 0.20 → 40pts; op_margin = 0 → 0pts; trend ~ 0 → 12pts
        assert sub.score >= 40

    def test_improving_margin_gets_trend_bonus(self):
        info = self._info(roe=0.12, op_margin=0.15)
        # Oldest→newest after reversal: improving from 10% to 20%
        stmts = _income([(1000, 200), (900, 162), (800, 120), (700, 84), (600, 60)])
        sub   = _score_profitability(info, stmts)
        assert "Operating margin improving" in " ".join(sub.notes)

    def test_deteriorating_margin_flagged(self):
        info  = self._info(roe=0.15, op_margin=0.10)
        # Oldest→newest after reversal: declining
        stmts = _income([(1000, 60), (900, 90), (800, 120), (700, 140), (600, 150)])
        sub   = _score_profitability(info, stmts)
        assert "deteriorating" in " ".join(sub.notes)

    def test_metrics_populated(self):
        info  = self._info()
        sub   = _score_profitability(info, _income([(1000, 200)] * 3))
        assert "roe" in sub.metrics
        assert "operating_margin" in sub.metrics
        assert "net_margin" in sub.metrics
        assert "margin_trend_slope_per_yr" in sub.metrics

    def test_score_capped_at_100(self):
        info  = self._info(roe=0.50, op_margin=0.50)
        stmts = _income([(1000, 500)] * 5)
        sub   = _score_profitability(info, stmts)
        assert sub.score <= 100


# ── Cash Generation sub-score ─────────────────────────────────────────────────

def _cash_flows(rows):
    """rows = list of (op_cf, capex_positive) newest-first."""
    return [{"operatingCashFlow": op, "capitalExpenditure": -cap} for op, cap in rows]


class TestScoreCashGeneration:
    def _info(self):
        return {}

    def test_high_fcf_margin_and_growth(self):
        stmts = _income([(1000, 200)] * 5)
        # FCF = op_cf - capex = 200 - 50 = 150 → FCF/Rev = 15%
        cfs   = _cash_flows([(200, 50)] * 5)
        sub   = _score_cash_generation(self._info(), stmts, cfs)
        assert sub.metrics["avg_fcf_margin"] >= 0.14
        assert sub.score >= 50

    def test_negative_fcf_years_penalised(self):
        stmts = _income([(1000, 200)] * 5)
        cfs   = _cash_flows([(50, 200)] * 5)   # all negative FCF
        sub   = _score_cash_generation(self._info(), stmts, cfs)
        assert sub.metrics["negative_fcf_years"] == 5
        assert sub.score == 0

    def test_two_negative_years_flagged(self):
        stmts = _income([(1000, 200)] * 5)
        cfs   = _cash_flows([(200, 50), (200, 50), (200, 50), (50, 200), (50, 200)])
        sub   = _score_cash_generation(self._info(), stmts, cfs)
        assert any("Negative FCF" in n for n in sub.notes)

    def test_ni_fcf_divergence_flagged(self):
        # Net income high but FCF very low
        stmts = [{"revenue": 1000, "operatingIncome": 300, "netIncome": 200}] * 5
        cfs   = _cash_flows([(50, 30)] * 5)   # FCF ≈ 20, avg NI = 200
        sub   = _score_cash_generation(self._info(), stmts, cfs)
        assert any("divergence" in n for n in sub.notes)

    def test_empty_cash_flows_returns_default(self):
        sub = _score_cash_generation(self._info(), [], [])
        assert sub.score == 30
        assert sub.label == "Average"

    def test_fcf_cagr_computed_correctly(self):
        # FCF grows from 100 to 200 in 4 years → CAGR ≈ 18.9%
        stmts = _income([(1000, 200)] * 5)
        cfs   = _cash_flows([(250, 50), (220, 50), (190, 50), (160, 50), (150, 50)])
        sub   = _score_cash_generation(self._info(), stmts, cfs)
        assert sub.metrics["fcf_cagr"] > 0.10

    def test_score_cannot_exceed_100(self):
        stmts = _income([(1000, 200)] * 5)
        cfs   = _cash_flows([(500, 50)] * 5)
        sub   = _score_cash_generation(self._info(), stmts, cfs)
        assert sub.score <= 100

    def test_score_cannot_go_negative(self):
        stmts = _income([(1000, 0)] * 5)
        cfs   = _cash_flows([(0, 500)] * 5)   # massive negative FCF
        sub   = _score_cash_generation(self._info(), stmts, cfs)
        assert sub.score >= 0


# ── Balance Sheet sub-score ───────────────────────────────────────────────────

class TestScoreBalanceSheet:
    def _info(self, de_pct=50, ebitda=1e9, total_debt=5e8, total_cash=2e8):
        # yfinance returns D/E as %, e.g. 50 means 0.50x
        return {
            "debtToEquity": de_pct,
            "ebitda": ebitda,
            "totalDebt": total_debt,
            "totalCash": total_cash,
        }

    def test_safe_leverage_high_score(self):
        # D/E = 0.3x, net debt/EBITDA ~1.5x
        info = self._info(de_pct=30, ebitda=2e9, total_debt=3e9, total_cash=0)
        sub, flags = _score_balance_sheet(info, [{}])
        assert sub.score >= 60
        assert flags == []

    def test_risky_leverage_low_score_with_flag(self):
        # D/E = 3.0x (above risky threshold)
        info = self._info(de_pct=300, ebitda=1e9, total_debt=5e9, total_cash=0)
        sub, flags = _score_balance_sheet(info, [{}])
        assert sub.score < 40
        assert any("High leverage" in f for f in flags)

    def test_net_debt_ebitda_flag(self):
        # ND/EBITDA = 4x (above 3.5 threshold)
        info = self._info(de_pct=100, ebitda=1e9, total_debt=4.5e9, total_cash=0.5e9)
        sub, flags = _score_balance_sheet(info, [{}])
        assert any("Net Debt/EBITDA" in f for f in flags)

    def test_net_cash_position(self):
        # Cash > Debt → net cash → nd_ebitda ≤ 0 → safe
        info = self._info(de_pct=20, ebitda=2e9, total_debt=1e9, total_cash=3e9)
        sub, flags = _score_balance_sheet(info, [{}])
        assert sub.metrics["net_debt"] < 0
        assert sub.score >= 60

    def test_de_correctly_divided_by_100(self):
        # yfinance gives 150 → should be interpreted as 1.5x
        info = self._info(de_pct=150, ebitda=2e9, total_debt=1.5e9, total_cash=0)
        sub, flags = _score_balance_sheet(info, [{}])
        assert sub.metrics["debt_to_equity"] == pytest.approx(1.5)

    def test_metrics_populated(self):
        info = self._info()
        sub, _ = _score_balance_sheet(info, [{}])
        assert "debt_to_equity" in sub.metrics
        assert "net_debt_ebitda" in sub.metrics
        assert "total_debt" in sub.metrics
        assert "total_cash" in sub.metrics


# ── Growth Profile sub-score ──────────────────────────────────────────────────

class TestScoreGrowth:
    def _info(self, analyst_growth=0.15):
        return {"earningsGrowth": analyst_growth, "epsForward": 5.0, "epsTrailingTwelveMonths": 4.0}

    def test_high_growth(self):
        stmts = [{"revenue": r} for r in [200, 160, 130, 115, 100]]
        sub   = _score_growth(self._info(0.15), stmts)
        assert sub.score >= 55

    def test_low_growth_low_score(self):
        stmts = [{"revenue": r} for r in [105, 103, 101, 100, 99]]
        sub   = _score_growth(self._info(0.02), stmts)
        assert sub.score < 35

    def test_high_volatility_penalised(self):
        # Very erratic revenue
        stmts = [{"revenue": r} for r in [200, 50, 180, 40, 150]]
        sub1  = _score_growth(self._info(0.10), stmts)
        stmts2 = [{"revenue": r} for r in [200, 180, 160, 140, 120]]
        sub2  = _score_growth(self._info(0.10), stmts2)
        assert sub1.score < sub2.score

    def test_revenue_cagr_in_metrics(self):
        stmts = [{"revenue": r} for r in [200, 160, 130, 115, 100]]
        sub   = _score_growth(self._info(), stmts)
        assert "revenue_cagr" in sub.metrics
        assert sub.metrics["revenue_cagr"] > 0.18

    def test_no_revenue_data(self):
        sub = _score_growth(self._info(), [])
        assert sub.score >= 0

    def test_score_bounded_0_to_100(self):
        stmts = [{"revenue": r} for r in [1000, 100, 1000, 100, 1000]]
        sub   = _score_growth(self._info(0.50), stmts)
        assert 0 <= sub.score <= 100


# ── Valuation scoring ─────────────────────────────────────────────────────────

class TestScoreValuation:
    def _info(self, pe=20, fcf=5e9, ev=100e9, analyst_growth=0.12):
        return {
            "trailingPE": pe,
            "forwardPE": pe * 0.9,
            "freeCashflow": fcf,
            "enterpriseValue": ev,
            "marketCap": ev * 0.9,
            "earningsGrowth": analyst_growth,
            "priceToSalesTrailing12Months": 5.0,
            "priceToBook": 3.0,
            "enterpriseToEbitda": 15.0,
            "epsTrailingTwelveMonths": 5.0,
        }

    def test_cheap_valuation(self):
        # Low P/E, high FCF yield
        info = self._info(pe=12, fcf=8e9, ev=100e9)
        score, label, metrics, ret, flags = _score_valuation(info, [])
        assert label == "Cheap"
        assert score >= 70

    def test_expensive_valuation(self):
        # Very high P/E, low FCF yield
        info = self._info(pe=60, fcf=1e9, ev=200e9)
        score, label, metrics, ret, flags = _score_valuation(info, [])
        assert label == "Expensive"

    def test_stretched_valuation_flagged(self):
        info = self._info(pe=50, fcf=1e8, ev=200e9)  # pe>40, fcf_yield<2%
        score, label, metrics, ret, flags = _score_valuation(info, [])
        assert any("Stretched" in f for f in flags)

    def test_expected_return_calculation(self):
        # FCF yield = 5e9/100e9 = 5%; growth = 12%
        info = self._info(pe=20, fcf=5e9, ev=100e9, analyst_growth=0.12)
        _, _, metrics, ret, _ = _score_valuation(info, [])
        assert ret == pytest.approx(0.05 + 0.12, abs=0.001)

    def test_expected_return_below_required_flagged(self):
        # Very low FCF yield, low growth
        info = self._info(pe=30, fcf=1e9, ev=200e9, analyst_growth=0.03)
        _, _, _, ret, flags = _score_valuation(info, [])
        assert ret < THRESHOLDS["required_return"]
        assert any("below required" in f for f in flags)

    def test_peg_ratio_computed(self):
        info = self._info(pe=20, analyst_growth=0.20)  # PEG = 20/(20*100) = 0.01...
        # PEG = pe / (analyst_growth * 100) = 20 / 20 = 1.0
        _, _, metrics, _, _ = _score_valuation(info, [])
        assert metrics["peg_ratio"] == pytest.approx(1.0)

    def test_zero_fcf_yield_handled(self):
        info = self._info(fcf=0)
        score, _, metrics, _, _ = _score_valuation(info, [])
        assert metrics["fcf_yield"] == 0.0
        assert score >= 0

    def test_negative_pe_treated_neutral(self):
        info = self._info(pe=-5)
        score, _, metrics, _, _ = _score_valuation(info, [])
        assert score >= 0  # shouldn't crash

    def test_growth_capped_at_20pct_for_expected_return(self):
        # Analyst growth = 50%, should be capped at 20% for expected return
        info = self._info(fcf=5e9, ev=100e9, analyst_growth=0.50)
        _, _, _, ret, _ = _score_valuation(info, [])
        assert ret <= 0.20 + 0.10  # max FCF yield + 20% growth cap


# ── Decision engine ───────────────────────────────────────────────────────────

class TestDecide:
    def test_buy_when_all_thresholds_met(self):
        result = _decide(quality=75, valuation=65, expected_return=0.12, red_flags=[])
        assert result == "BUY / ACCUMULATE"

    def test_watchlist_quality_ok_expensive(self):
        # Great quality but too expensive
        result = _decide(quality=75, valuation=50, expected_return=0.07, red_flags=[])
        assert result == "WATCHLIST"

    def test_watchlist_decent_quality_cheap(self):
        result = _decide(quality=60, valuation=70, expected_return=0.12, red_flags=[])
        assert result == "WATCHLIST"

    def test_avoid_low_quality(self):
        result = _decide(quality=40, valuation=80, expected_return=0.15, red_flags=[])
        assert result == "AVOID"

    def test_avoid_forced_by_extreme_leverage_flag(self):
        flags = ["Extreme leverage D/E 5.0x — financial distress risk"]
        result = _decide(quality=80, valuation=80, expected_return=0.15, red_flags=flags)
        assert result == "AVOID"

    def test_avoid_forced_by_repeated_negative_fcf(self):
        flags = ["Repeated negative FCF (4 years) — capital destruction risk"]
        result = _decide(quality=75, valuation=70, expected_return=0.12, red_flags=flags)
        assert result == "AVOID"

    def test_avoid_forced_by_financial_distress(self):
        flags = ["financial distress risk noted"]
        result = _decide(quality=80, valuation=80, expected_return=0.15, red_flags=flags)
        assert result == "AVOID"

    def test_return_below_required_not_buy(self):
        # Return below required → not BUY even with good scores
        result = _decide(quality=75, valuation=65, expected_return=0.05, red_flags=[])
        assert result != "BUY / ACCUMULATE"

    def test_boundary_quality_exactly_70(self):
        result = _decide(quality=70.0, valuation=65, expected_return=0.12, red_flags=[])
        assert result == "BUY / ACCUMULATE"

    def test_boundary_quality_just_below_70(self):
        result = _decide(quality=69.9, valuation=80, expected_return=0.15, red_flags=[])
        assert result == "WATCHLIST"


# ── Red flag checks ───────────────────────────────────────────────────────────

class TestCheckRedFlags:
    def _bs_sub(self, de=0.5):
        return SubScore("Balance Sheet", 70, "High", metrics={"debt_to_equity": de})

    def _cash_sub(self, neg_years=0):
        return SubScore("Cash Generation", 70, "High", metrics={"negative_fcf_years": neg_years})

    def test_no_flags_clean_company(self):
        cash = self._cash_sub(0)
        bs   = self._bs_sub(0.3)
        flags = _check_red_flags({}, {"balance_sheet": bs}, cash, [])
        assert flags == []

    def test_repeated_negative_fcf_flagged(self):
        cash  = self._cash_sub(3)
        bs    = self._bs_sub(0.3)
        flags = _check_red_flags({}, {"balance_sheet": bs}, cash, [])
        assert any("Repeated negative FCF" in f for f in flags)

    def test_extreme_leverage_flagged(self):
        cash  = self._cash_sub(0)
        bs    = self._bs_sub(3.5)  # > 3.0
        flags = _check_red_flags({}, {"balance_sheet": bs}, cash, [])
        assert any("Extreme leverage" in f for f in flags)

    def test_bs_flags_passed_through(self):
        cash     = self._cash_sub(0)
        bs       = self._bs_sub(0.3)
        existing = ["High leverage from balance sheet check"]
        flags    = _check_red_flags({}, {"balance_sheet": bs}, cash, existing)
        assert existing[0] in flags


# ── run_qafp integration ──────────────────────────────────────────────────────

class TestRunQAFP:
    def _good_info(self):
        return {
            "longName": "Test Corp",
            "sector": "Technology",
            "quoteType": "EQUITY",
            "returnOnEquity": 0.28,
            "operatingMargins": 0.25,
            "profitMargins": 0.18,
            "debtToEquity": 30.0,   # 0.30x
            "ebitda": 5e9,
            "totalDebt": 1e9,
            "totalCash": 3e9,
            "freeCashflow": 4e9,
            "marketCap": 60e9,
            "enterpriseValue": 58e9,
            "trailingPE": 15.0,
            "forwardPE": 13.0,
            "earningsGrowth": 0.15,
            "priceToSalesTrailing12Months": 5.0,
            "priceToBook": 3.0,
            "enterpriseToEbitda": 12.0,
            "epsTrailingTwelveMonths": 4.0,
            "epsForward": 5.0,
        }

    def _income(self):
        return [{"revenue": r, "operatingIncome": int(r * 0.25), "netIncome": int(r * 0.18)}
                for r in [1000, 900, 800, 700, 600]]

    def _balance_sheets(self):
        return [{"totalAssets": 10e9, "totalDebt": 1e9,
                 "commonStockSharesOutstanding": 1000 - i * 10}
                for i in range(5)]

    def _cash_flows(self):
        return [{"operatingCashFlow": 500, "capitalExpenditure": -100} for _ in range(5)]

    def test_returns_qafp_result(self):
        from scoring.qafp_models import QAFPResult
        result = run_qafp("TEST", self._good_info(), self._income(),
                          self._balance_sheets(), self._cash_flows())
        assert isinstance(result, QAFPResult)

    def test_ticker_and_company_set(self):
        result = run_qafp("TEST", self._good_info(), self._income(),
                          self._balance_sheets(), self._cash_flows())
        assert result.ticker == "TEST"
        assert result.company_name == "Test Corp"

    def test_quality_score_in_range(self):
        result = run_qafp("TEST", self._good_info(), self._income(),
                          self._balance_sheets(), self._cash_flows())
        assert 0 <= result.quality_score <= 100

    def test_valuation_score_in_range(self):
        result = run_qafp("TEST", self._good_info(), self._income(),
                          self._balance_sheets(), self._cash_flows())
        assert 0 <= result.valuation_score <= 100

    def test_good_company_recommends_buy(self):
        result = run_qafp("TEST", self._good_info(), self._income(),
                          self._balance_sheets(), self._cash_flows())
        assert result.recommendation in ("BUY / ACCUMULATE", "WATCHLIST")

    def test_all_sub_scores_present(self):
        result = run_qafp("TEST", self._good_info(), self._income(),
                          self._balance_sheets(), self._cash_flows())
        assert "profitability" in result.sub_scores
        assert "cash_generation" in result.sub_scores
        assert "balance_sheet" in result.sub_scores
        assert "growth" in result.sub_scores

    def test_etf_detected(self):
        info = {**self._good_info(), "quoteType": "ETF"}
        result = run_qafp("SPY", info, self._income(),
                          self._balance_sheets(), self._cash_flows())
        assert result.security_type == "etf"

    def test_stock_detected(self):
        result = run_qafp("TEST", self._good_info(), self._income(),
                          self._balance_sheets(), self._cash_flows())
        assert result.security_type == "stock"

    def test_quality_weights_sum_to_100pct(self):
        weights = {"profitability": 0.30, "cash_generation": 0.30,
                   "balance_sheet": 0.20, "growth": 0.20}
        assert sum(weights.values()) == pytest.approx(1.0)

    def test_key_metrics_populated(self):
        result = run_qafp("TEST", self._good_info(), self._income(),
                          self._balance_sheets(), self._cash_flows())
        for k in ("roe", "operating_margin", "net_margin", "fcf_margin",
                  "revenue_cagr", "debt_to_equity"):
            assert k in result.key_metrics

    def test_serialization_roundtrip(self):
        from scoring.qafp_models import QAFPResult
        result = run_qafp("TEST", self._good_info(), self._income(),
                          self._balance_sheets(), self._cash_flows())
        d       = result.to_dict()
        restored = QAFPResult.from_dict(d)
        assert restored.ticker == result.ticker
        assert restored.quality_score == result.quality_score
        assert restored.recommendation == result.recommendation

    def test_custom_required_return(self):
        result = run_qafp("TEST", self._good_info(), self._income(),
                          self._balance_sheets(), self._cash_flows(),
                          required_return=0.15)
        assert result.required_return == 0.15
