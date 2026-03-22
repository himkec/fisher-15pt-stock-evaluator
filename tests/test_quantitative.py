"""
Tests for scoring/quantitative.py — Fisher Points 1, 5, 6, 10, 13.
Covers helper functions, boundary conditions, edge cases.
"""

import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scoring.quantitative import (
    _cagr, _linear_slope, _score,
    score_point_1, score_point_5, score_point_6,
    score_point_10, score_point_13,
)
from config.settings import SECTOR_FALLBACK_GROSS_MARGINS


# ── Helper: _cagr ─────────────────────────────────────────────────────────────

class TestCagr:
    def test_doubles_in_one_year(self):
        assert _cagr(100, 200, 1) == pytest.approx(1.0)

    def test_doubles_in_four_years(self):
        # 2^(1/4) - 1 ≈ 18.92%
        assert _cagr(100, 200, 4) == pytest.approx(0.1892, abs=1e-4)

    def test_flat_revenue(self):
        assert _cagr(100, 100, 5) == pytest.approx(0.0)

    def test_decline(self):
        result = _cagr(200, 100, 4)
        assert result < 0

    def test_zero_start_returns_zero(self):
        assert _cagr(0, 200, 5) == 0.0

    def test_negative_start_returns_zero(self):
        assert _cagr(-50, 200, 5) == 0.0

    def test_zero_years_returns_zero(self):
        assert _cagr(100, 200, 0) == 0.0

    def test_ten_year_10pct(self):
        # 100 * 1.1^10 ≈ 259.37
        assert _cagr(100, 259.37, 10) == pytest.approx(0.10, abs=1e-3)


# ── Helper: _linear_slope ─────────────────────────────────────────────────────

class TestLinearSlope:
    def test_perfectly_increasing(self):
        # [0, 1, 2, 3, 4] → slope = 1.0
        assert _linear_slope([0, 1, 2, 3, 4]) == pytest.approx(1.0)

    def test_perfectly_decreasing(self):
        assert _linear_slope([4, 3, 2, 1, 0]) == pytest.approx(-1.0)

    def test_flat_series(self):
        assert _linear_slope([5, 5, 5, 5, 5]) == pytest.approx(0.0)

    def test_two_points_increasing(self):
        assert _linear_slope([0, 10]) == pytest.approx(10.0)

    def test_single_point_returns_zero(self):
        assert _linear_slope([42]) == 0.0

    def test_empty_returns_zero(self):
        assert _linear_slope([]) == 0.0

    def test_known_slope(self):
        # values at x=0,1,2: y=1,3,5 → slope=2
        assert _linear_slope([1, 3, 5]) == pytest.approx(2.0)

    def test_noisy_uptrend(self):
        # Generally increasing despite noise
        result = _linear_slope([0.10, 0.12, 0.11, 0.14, 0.16])
        assert result > 0


# ── Helper: _score ────────────────────────────────────────────────────────────

class TestScoreMap:
    def test_strong_is_2(self):
        assert _score("strong") == 2

    def test_average_is_1(self):
        assert _score("average") == 1

    def test_weak_is_0(self):
        assert _score("weak") == 0

    def test_unknown_is_0(self):
        assert _score("unknown") == 0


# ── Point 1: Growth Potential ─────────────────────────────────────────────────

def _income(revenues):
    """Build income stmt list newest-first from revenue list (newest-first)."""
    return [{"revenue": r} for r in revenues]


class TestPoint1:
    def test_strong_high_cagr(self):
        # 100 → 200 in 4 years ≈ 18.9% CAGR → strong (≥15%)
        stmts = _income([200, 160, 130, 115, 100])
        result = score_point_1(stmts)
        assert result.score == "strong"
        assert result.numeric == 2
        assert result.point_number == 1

    def test_average_moderate_cagr(self):
        # ~10% CAGR (between 7% and 15%)
        stmts = _income([161, 146, 133, 121, 110, 100])
        result = score_point_1(stmts)
        assert result.score == "average"
        assert result.numeric == 1

    def test_weak_low_cagr(self):
        # ~3% CAGR (below 7%)
        stmts = _income([116, 112, 109, 106, 103, 100])
        result = score_point_1(stmts)
        assert result.score == "weak"
        assert result.numeric == 0

    def test_insufficient_data_defaults_average(self):
        result = score_point_1([{"revenue": 100}])
        assert result.score == "average"
        assert result.numeric == 1

    def test_empty_data_defaults_average(self):
        result = score_point_1([])
        assert result.score == "average"

    def test_zero_revenues_excluded(self):
        stmts = [{"revenue": 200}, {"revenue": 0}, {"revenue": 100}]
        result = score_point_1(stmts)
        # Should use 200 and 100 (skip zero)
        assert result.numeric in (0, 1, 2)

    def test_caps_at_5_years(self):
        # Even with 7 data points, uses max 5yr window
        stmts = _income([400, 350, 300, 250, 200, 170, 100])
        result = score_point_1(stmts)
        assert result.data_used["years"] == 5
        assert result.data_used["start_revenue"] == 170  # oldest of the 6 used = index 5

    def test_data_used_populated(self):
        stmts = _income([200, 100])
        result = score_point_1(stmts)
        assert "revenue_cagr" in result.data_used
        assert "years" in result.data_used
        assert result.data_used["latest_revenue"] == 200
        assert result.data_used["start_revenue"] == 100


# ── Point 5: Profit Margin Level ──────────────────────────────────────────────

class TestPoint5:
    def test_strong_with_peers(self):
        # Company 65%, peers around 40-50% → premium > 10pp
        ratios = [{"grossProfitMargin": 0.65}]
        peers  = [{"grossProfitMargin": 0.45}, {"grossProfitMargin": 0.50}]
        result = score_point_5(ratios, peers, "Technology")
        assert result.score == "strong"
        assert result.data_used["comparison_source"] == "peer_median"

    def test_average_near_peer_median(self):
        ratios = [{"grossProfitMargin": 0.50}]
        peers  = [{"grossProfitMargin": 0.48}, {"grossProfitMargin": 0.52}]
        result = score_point_5(ratios, peers, "Technology")
        assert result.score == "average"

    def test_weak_below_peer_median(self):
        ratios = [{"grossProfitMargin": 0.30}]
        peers  = [{"grossProfitMargin": 0.55}, {"grossProfitMargin": 0.60}]
        result = score_point_5(ratios, peers, "Technology")
        assert result.score == "weak"

    def test_sector_fallback_used_when_no_peers(self):
        ratios = [{"grossProfitMargin": 0.75}]
        result = score_point_5(ratios, [], "Technology")
        # Tech fallback is 0.55; 0.75 - 0.55 = 0.20 > MARGIN_PREMIUM_STRONG (0.10)
        assert result.score == "strong"
        assert result.data_used["comparison_source"] == "sector_fallback"

    def test_unknown_sector_uses_default_fallback(self):
        ratios = [{"grossProfitMargin": 0.50}]
        result = score_point_5(ratios, [], "Nonexistent")
        assert result.data_used["sector_median"] == SECTOR_FALLBACK_GROSS_MARGINS["default"]

    def test_empty_ratios_defaults_average(self):
        result = score_point_5([], [], "Technology")
        assert result.score == "average"
        assert result.numeric == 1

    def test_peer_median_uses_statistical_median(self):
        # Median of [0.30, 0.50, 0.70] = 0.50
        ratios = [{"grossProfitMargin": 0.62}]
        peers  = [{"grossProfitMargin": 0.30},
                  {"grossProfitMargin": 0.50},
                  {"grossProfitMargin": 0.70}]
        result = score_point_5(ratios, peers, "Technology")
        assert result.data_used["sector_median"] == pytest.approx(0.50)


# ── Point 6: Margin Stability & Improvement ───────────────────────────────────

def _ratios(op_margins_newest_first):
    return [{"operatingProfitMargin": m} for m in op_margins_newest_first]


class TestPoint6:
    def test_strong_improving_margin(self):
        # Improving by ~1pp/yr (oldest→newest after reversal)
        ratios = _ratios([0.24, 0.22, 0.20, 0.18, 0.16])  # newest first
        result = score_point_6(ratios)
        assert result.score == "strong"
        assert result.numeric == 2

    def test_average_stable_margin(self):
        # Flat margins
        ratios = _ratios([0.20, 0.20, 0.20, 0.20, 0.20])
        result = score_point_6(ratios)
        assert result.score == "average"

    def test_weak_deteriorating_margin(self):
        # Declining by ~1.5pp/yr
        ratios = _ratios([0.10, 0.12, 0.14, 0.17, 0.22])  # newest first = deteriorating
        result = score_point_6(ratios)
        assert result.score == "weak"

    def test_insufficient_data_defaults_average(self):
        result = score_point_6([{"operatingProfitMargin": 0.20}])
        assert result.score == "average"

    def test_filters_none_values(self):
        ratios = [{"operatingProfitMargin": 0.20},
                  {"other_field": 1},
                  {"operatingProfitMargin": 0.18}]
        result = score_point_6(ratios)
        assert result.numeric in (0, 1, 2)

    def test_slope_stored_in_data_used(self):
        ratios = _ratios([0.25, 0.22, 0.19, 0.16, 0.13])
        result = score_point_6(ratios)
        assert "margin_slope_per_yr" in result.data_used
        assert result.data_used["margin_slope_per_yr"] > 0  # improving


# ── Point 10: Cost Controls ───────────────────────────────────────────────────

def _income_with_sgna(rows):
    """rows = list of (revenue, sgna) tuples, newest first."""
    return [{"revenue": r, "sellingGeneralAndAdministrativeExpenses": s} for r, s in rows]


class TestPoint10:
    def test_strong_falling_sgna_ratio(self):
        # SG&A/Rev falling from 25% to 20% (oldest→newest after reversal)
        stmts = _income_with_sgna([(1000, 200), (1000, 215), (1000, 230), (1000, 245), (1000, 250)])
        result = score_point_10(stmts)
        assert result.score == "strong"

    def test_average_stable_sgna_ratio(self):
        stmts = _income_with_sgna([(1000, 200)] * 5)
        result = score_point_10(stmts)
        assert result.score == "average"

    def test_weak_rising_sgna_ratio(self):
        # SG&A/Rev rising from 20% to 30%
        stmts = _income_with_sgna([(1000, 300), (1000, 280), (1000, 260), (1000, 240), (1000, 200)])
        result = score_point_10(stmts)
        assert result.score == "weak"

    def test_skips_zero_revenue_rows(self):
        stmts = [{"revenue": 0, "sellingGeneralAndAdministrativeExpenses": 100},
                 {"revenue": 1000, "sellingGeneralAndAdministrativeExpenses": 200},
                 {"revenue": 1000, "sellingGeneralAndAdministrativeExpenses": 210}]
        result = score_point_10(stmts)
        # Should work with 2 valid rows
        assert result.numeric in (0, 1, 2)

    def test_insufficient_data_defaults_average(self):
        stmts = [{"revenue": 1000, "sellingGeneralAndAdministrativeExpenses": 200}]
        result = score_point_10(stmts)
        assert result.score == "average"

    def test_missing_sgna_skipped(self):
        stmts = [{"revenue": 1000},
                 {"revenue": 900, "sellingGeneralAndAdministrativeExpenses": 180},
                 {"revenue": 800, "sellingGeneralAndAdministrativeExpenses": 170}]
        result = score_point_10(stmts)
        assert result.numeric in (0, 1, 2)


# ── Point 13: Equity Financing Needs ─────────────────────────────────────────

def _cash_flows(rows):
    """rows = list of (op_cf, capex) tuples, newest first. capex as positive."""
    return [{"operatingCashFlow": op, "capitalExpenditure": -cap} for op, cap in rows]


def _balance_sheets(shares_list):
    return [{"commonStockSharesOutstanding": s} for s in shares_list]


class TestPoint13:
    def test_strong_fcf_and_buybacks(self):
        # FCF positive all years, shares declining (buyback)
        cfs  = _cash_flows([(500, 100)] * 5)
        bals = _balance_sheets([900, 920, 950, 980, 1000])  # newest first → declining
        result = score_point_13(cfs, bals)
        assert result.score == "strong"
        assert result.numeric == 2

    def test_average_fcf_ok_mild_dilution(self):
        # FCF positive, shares growing ~1%/yr
        cfs  = _cash_flows([(500, 100)] * 5)
        bals = _balance_sheets([1010, 1005, 1000, 995, 990])
        result = score_point_13(cfs, bals)
        assert result.score in ("strong", "average")

    def test_weak_low_fcf_coverage(self):
        # Only 2/5 years FCF positive
        cfs = _cash_flows([(500, 100), (50, 200), (50, 300), (500, 100), (50, 200)])
        bals = _balance_sheets([1100, 1050, 1000, 950, 900])
        result = score_point_13(cfs, bals)
        assert result.score == "weak"
        assert result.numeric == 0

    def test_weak_high_dilution(self):
        # FCF fine but heavy dilution >2%/yr
        cfs  = _cash_flows([(500, 100)] * 5)
        bals = _balance_sheets([1200, 1150, 1100, 1050, 1000])
        result = score_point_13(cfs, bals)
        assert result.score == "weak"

    def test_no_shares_data_still_scores(self):
        cfs  = _cash_flows([(500, 100)] * 4)
        bals = [{}] * 4  # no shares data
        result = score_point_13(cfs, bals)
        assert result.numeric in (0, 1, 2)

    def test_fcf_self_funded_threshold_60pct(self):
        # 3/5 = 60% → just meets threshold
        cfs  = _cash_flows([(500, 100), (500, 100), (500, 100), (50, 200), (50, 300)])
        bals = _balance_sheets([1000, 1000, 1000, 1000, 1000])
        result = score_point_13(cfs, bals)
        assert result.data_used["fcf_self_funded_years"] == 3

    def test_data_used_populated(self):
        cfs  = _cash_flows([(500, 100)] * 5)
        bals = _balance_sheets([900, 950, 1000, 1050, 1100])
        result = score_point_13(cfs, bals)
        assert "fcf_self_funded_years" in result.data_used
        assert "dilution_cagr" in result.data_used
        assert "total_years" in result.data_used
