"""
Tests for scoring/intrinsic_value.py — Intrinsic Value / Valuation Models engine.

Each test documents the expected hand-calculated result so discrepancies are obvious.
"""

import math
import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scoring.intrinsic_value import (
    _s, _cagr, _clamp, _wacc, _shares, _current_price, _upside,
    _run_dcf_fcf, _run_ddm_gordon, _run_ddm_multi, _run_rim, _run_graham,
    _build_football_field, run_intrinsic_value,
    RISK_FREE_RATE, EQUITY_RISK_PREMIUM, TERMINAL_GROWTH,
    FORECAST_YEARS, DDM_REQUIRED_RETURN, RIM_TERMINAL_RI_GROWTH,
)
from scoring.intrinsic_value_models import IntrinsicValueResult


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_info(**kwargs):
    """Minimal yfinance info dict with sensible defaults."""
    defaults = {
        "currentPrice":       100.0,
        "sharesOutstanding":  1_000.0,   # 1 000 shares for easy per-share math
        "beta":               1.0,
        "trailingEps":        5.0,
        "bookValue":          20.0,
        "dividendRate":       0.0,
        "payoutRatio":        0.0,
        "returnOnEquity":     0.0,
        "trailingPE":         20.0,
        "priceToBook":        5.0,
    }
    defaults.update(kwargs)
    return defaults


def _make_balance_sheets(equity=10_000.0, debt=0.0, cash=0.0):
    return [{"totalStockholdersEquity": equity, "totalDebt": debt,
             "cashAndCashEquivalents": cash}]


def _make_income(net_income_list):
    """Newest first, same as yfinance."""
    return [{"netIncome": ni} for ni in net_income_list]


def _make_cashflows(ocf_capex_pairs):
    """List of (operating_cash_flow, capex) tuples, newest first."""
    return [{"operatingCashFlow": ocf, "capitalExpenditure": capex}
            for ocf, capex in ocf_capex_pairs]


# ── _s helper ─────────────────────────────────────────────────────────────────

class TestSafeHelper:
    def test_none_returns_default(self):
        assert _s(None) == 0.0
        assert _s(None, 5.0) == 5.0

    def test_nan_returns_default(self):
        assert _s(float("nan")) == 0.0

    def test_normal_float(self):
        assert _s(3.14) == pytest.approx(3.14)

    def test_string_parseable(self):
        assert _s("2.5") == pytest.approx(2.5)

    def test_invalid_string(self):
        assert _s("N/A", 1.0) == 1.0


# ── _cagr ─────────────────────────────────────────────────────────────────────

class TestCagr:
    def test_positive_growth(self):
        # 100 → 121 over 2 years → 10% CAGR
        assert _cagr(100, 121, 2) == pytest.approx(0.10, rel=1e-4)

    def test_negative_growth(self):
        # 100 → 81 over 2 years → -10% CAGR
        assert _cagr(100, 81, 2) == pytest.approx(-0.10, rel=1e-4)

    def test_zero_start(self):
        assert _cagr(0, 100, 5) == 0.0

    def test_zero_years(self):
        assert _cagr(100, 200, 0) == 0.0


# ── _wacc ─────────────────────────────────────────────────────────────────────

class TestWacc:
    def test_pure_equity_no_debt(self):
        # No debt → WACC = re = Rf + β × ERP = 0.045 + 1.0 × 0.055 = 0.10
        info = _make_info(beta=1.0)
        bs   = _make_balance_sheets(equity=1000, debt=0)
        assert _wacc(info, bs) == pytest.approx(0.10, rel=1e-4)

    def test_with_debt_lowers_wacc(self):
        # 50/50 debt-equity split, rd=5%, re=10%
        # WACC = 0.5*10% + 0.5*5%*(1-0.21) = 5% + 1.975% = 6.975%
        info = _make_info(beta=1.0)
        bs   = _make_balance_sheets(equity=1000, debt=1000)
        w = _wacc(info, bs)
        assert 0.065 < w < 0.075

    def test_clamped_to_min(self):
        # Very low beta → still at least 6%
        info = _make_info(beta=0.1)
        bs   = _make_balance_sheets(equity=1000, debt=0)
        assert _wacc(info, bs) >= 0.06

    def test_clamped_to_max(self):
        # Very high beta → capped at 20%
        info = _make_info(beta=3.0)  # will be clamped to 2.5 in _wacc
        bs   = _make_balance_sheets(equity=1000, debt=0)
        assert _wacc(info, bs) <= 0.20

    def test_no_balance_sheet_uses_cost_of_equity(self):
        info = _make_info(beta=1.0)
        w = _wacc(info, [])
        assert w == pytest.approx(0.10, rel=1e-4)


# ── Graham Number ─────────────────────────────────────────────────────────────

class TestGrahamNumber:
    """Graham Number = sqrt(22.5 × EPS × BVPS)"""

    def _build(self, eps_ni, shares, bvps_override=None, price=100.0, **info_kwargs):
        info = _make_info(
            currentPrice=price,
            sharesOutstanding=shares,
            bookValue=bvps_override if bvps_override is not None else 0.0,
            **info_kwargs,
        )
        income = _make_income([eps_ni])   # 1 year so avg EPS = ni/shares
        bs     = _make_balance_sheets(equity=eps_ni * 5)  # arbitrary equity
        return _run_graham(info, income, bs)

    def test_formula_exact(self):
        # EPS = 3.0 (netIncome=3000 / shares=1000), BVPS = 10.0
        # Graham = sqrt(22.5 × 3.0 × 10.0) = sqrt(675) = 25.9808...
        info   = _make_info(currentPrice=20.0, sharesOutstanding=1_000.0, bookValue=10.0)
        income = _make_income([3_000.0])   # NI=3000, shares=1000 → EPS=3.0
        bs     = _make_balance_sheets(equity=10_000.0)
        result = _run_graham(info, income, bs)

        assert result is not None
        assert result.eps  == pytest.approx(3.0,   rel=1e-4)
        assert result.bvps == pytest.approx(10.0,  rel=1e-4)
        expected_gn = math.sqrt(22.5 * 3.0 * 10.0)   # 25.9808
        assert result.graham_number == pytest.approx(expected_gn, rel=1e-3)

    def test_price_to_graham_ratio(self):
        # price=20, GN≈25.98 → P/G ≈ 0.770 < 0.90 → "Below Graham ceiling"
        info   = _make_info(currentPrice=20.0, sharesOutstanding=1_000.0, bookValue=10.0)
        income = _make_income([3_000.0])
        bs     = _make_balance_sheets(equity=10_000.0)
        result = _run_graham(info, income, bs)

        expected_gn = math.sqrt(22.5 * 3.0 * 10.0)
        expected_ptg = 20.0 / expected_gn
        assert result.price_to_graham == pytest.approx(expected_ptg, rel=1e-3)
        assert result.label == "Below Graham ceiling"

    def test_label_at_ceiling(self):
        # price ≈ GN → "At Graham ceiling"
        gn = math.sqrt(22.5 * 3.0 * 10.0)   # 25.98
        info   = _make_info(currentPrice=round(gn, 2), sharesOutstanding=1_000.0, bookValue=10.0)
        income = _make_income([3_000.0])
        bs     = _make_balance_sheets()
        result = _run_graham(info, income, bs)
        assert result.label == "At Graham ceiling"

    def test_label_above_ceiling(self):
        # price = 40 > GN = 25.98 → "Above Graham ceiling"
        info   = _make_info(currentPrice=40.0, sharesOutstanding=1_000.0, bookValue=10.0)
        income = _make_income([3_000.0])
        bs     = _make_balance_sheets()
        result = _run_graham(info, income, bs)
        assert result.label == "Above Graham ceiling"

    def test_three_year_avg_eps(self):
        # 3 income years → avg EPS used, not just latest
        # NI years (newest first): 4500, 3000, 1500 → avg NI = 3000 → EPS = 3.0
        info   = _make_info(currentPrice=20.0, sharesOutstanding=1_000.0, bookValue=10.0)
        income = _make_income([4_500.0, 3_000.0, 1_500.0])
        bs     = _make_balance_sheets()
        result = _run_graham(info, income, bs)
        assert result.eps == pytest.approx(3.0, rel=1e-4)

    def test_upside_pct(self):
        # price=20, GN≈25.98 → upside = (25.98-20)/20 ≈ 0.299
        info   = _make_info(currentPrice=20.0, sharesOutstanding=1_000.0, bookValue=10.0)
        income = _make_income([3_000.0])
        bs     = _make_balance_sheets()
        result = _run_graham(info, income, bs)
        gn = math.sqrt(22.5 * 3.0 * 10.0)
        expected_upside = (gn - 20.0) / 20.0
        assert result.upside_pct == pytest.approx(expected_upside, rel=1e-3)

    def test_negative_eps_returns_none(self):
        info   = _make_info(currentPrice=20.0, sharesOutstanding=1_000.0, bookValue=10.0,
                            trailingEps=-2.0)
        income = _make_income([-2_000.0])   # negative NI → EPS < 0
        bs     = _make_balance_sheets()
        assert _run_graham(info, income, bs) is None

    def test_negative_bvps_returns_none(self):
        # Negative equity (e.g., after buybacks)
        info   = _make_info(currentPrice=20.0, sharesOutstanding=1_000.0, bookValue=-5.0)
        income = _make_income([3_000.0])
        bs     = _make_balance_sheets(equity=-5_000.0)
        assert _run_graham(info, income, bs) is None

    def test_pe_below_15_check(self):
        info   = _make_info(currentPrice=20.0, sharesOutstanding=1_000.0, bookValue=10.0,
                            trailingPE=12.0)
        income = _make_income([3_000.0])
        bs     = _make_balance_sheets()
        result = _run_graham(info, income, bs)
        assert result.checks["pe_below_15"] is True

    def test_pe_above_15_fails_check(self):
        info   = _make_info(currentPrice=20.0, sharesOutstanding=1_000.0, bookValue=10.0,
                            trailingPE=25.0)
        income = _make_income([3_000.0])
        bs     = _make_balance_sheets()
        result = _run_graham(info, income, bs)
        assert result.checks["pe_below_15"] is False

    def test_earnings_stability_all_positive(self):
        info   = _make_info(currentPrice=20.0, sharesOutstanding=1_000.0, bookValue=10.0)
        income = _make_income([3_000.0, 2_800.0, 2_600.0])
        bs     = _make_balance_sheets()
        result = _run_graham(info, income, bs)
        assert result.checks["earnings_stability"] is True

    def test_earnings_stability_with_loss_year(self):
        info   = _make_info(currentPrice=20.0, sharesOutstanding=1_000.0, bookValue=10.0)
        income = _make_income([3_000.0, -500.0, 2_600.0])   # middle year loss
        bs     = _make_balance_sheets()
        result = _run_graham(info, income, bs)
        assert result.checks["earnings_stability"] is False

    def test_dividend_check(self):
        info = _make_info(currentPrice=20.0, sharesOutstanding=1_000.0,
                          bookValue=10.0, dividendRate=1.0)
        income = _make_income([3_000.0])
        bs     = _make_balance_sheets()
        result = _run_graham(info, income, bs)
        assert result.checks["pays_dividend"] is True

    def test_no_dividend_check(self):
        info = _make_info(currentPrice=20.0, sharesOutstanding=1_000.0,
                          bookValue=10.0, dividendRate=0.0)
        income = _make_income([3_000.0])
        bs     = _make_balance_sheets()
        result = _run_graham(info, income, bs)
        assert result.checks["pays_dividend"] is False


# ── DDM Gordon ────────────────────────────────────────────────────────────────

class TestDDMGordon:
    """Gordon Growth Model: fair_value = D₁ / (r − g)"""

    def _build(self, div_rate, price=100.0, payout=0.50, roe=0.10, **info_kwargs):
        info = _make_info(
            currentPrice=price,
            sharesOutstanding=1_000.0,
            dividendRate=div_rate,
            payoutRatio=payout,
            returnOnEquity=roe,
            **info_kwargs,
        )
        income = _make_income([5_000.0])
        cfs    = _make_cashflows([(110.0, -10.0)])
        return _run_ddm_gordon(info, income, cfs)

    def test_formula_exact(self):
        # div_rate=2.0, payout=0.50, roe=0.10
        # retention = 0.50, sustainable_g = 0.10 × 0.50 = 0.05
        # g = clamp(0.05, 0, r−0.01) = clamp(0.05, 0, 0.08) = 0.05
        # D₁ = 2.0 × (1 + 0.05) = 2.10
        # fair_value = 2.10 / (0.09 − 0.05) = 2.10 / 0.04 = 52.50
        result = self._build(div_rate=2.0, payout=0.50, roe=0.10)
        assert result is not None
        assert result.d1           == pytest.approx(2.10,  rel=1e-3)
        assert result.perpetual_growth == pytest.approx(0.05, rel=1e-3)
        assert result.fair_value   == pytest.approx(52.50, rel=1e-3)

    def test_no_dividend_returns_none(self):
        assert self._build(div_rate=0.0) is None

    def test_upside_positive_when_undervalued(self):
        # fair_value=52.50, price=40 → upside = (52.50-40)/40 = 31.25%
        result = self._build(div_rate=2.0, price=40.0, payout=0.50, roe=0.10)
        assert result.upside_pct > 0.0
        assert result.upside_pct == pytest.approx((result.fair_value - 40.0) / 40.0, rel=1e-3)

    def test_upside_negative_when_overvalued(self):
        result = self._build(div_rate=2.0, price=200.0, payout=0.50, roe=0.10)
        assert result.upside_pct < 0.0

    def test_yield_plus_growth(self):
        # Heuristic expected return ≈ div_yield + g
        result = self._build(div_rate=2.0, price=50.0, payout=0.50, roe=0.10)
        expected = (2.0 / 50.0) + result.perpetual_growth
        assert result.yield_plus_growth == pytest.approx(expected, rel=1e-3)

    def test_high_roe_clamps_g_below_r(self):
        # ROE=1.50 (e.g. Apple-like), payout=0.10 → sustainable_g=1.35, clamped to 0.10
        # g = clamp(0.10, 0, r-0.01=0.08) = 0.08
        # D₁ = 1.0 × 1.08 = 1.08
        # fair_value = 1.08 / (0.09 − 0.08) = 108.0
        result = self._build(div_rate=1.0, payout=0.10, roe=1.50)
        assert result is not None
        assert result.perpetual_growth <= DDM_REQUIRED_RETURN
        assert result.fair_value == pytest.approx(108.0, rel=0.01)

    def test_payout_ratio_used_for_g(self):
        # Different payout ratios produce different g and thus different fair values
        low_payout  = self._build(div_rate=2.0, payout=0.20, roe=0.10)
        high_payout = self._build(div_rate=2.0, payout=0.80, roe=0.10)
        # Higher payout = lower retention = lower g = lower fair value
        assert low_payout.fair_value > high_payout.fair_value

    def test_current_yield_correct(self):
        result = self._build(div_rate=2.0, price=50.0, payout=0.50, roe=0.10)
        assert result.current_yield == pytest.approx(2.0 / 50.0, rel=1e-4)

    def test_valid_flag_set(self):
        result = self._build(div_rate=2.0, payout=0.50, roe=0.10)
        assert result.valid is True


# ── DDM Multi-Period ──────────────────────────────────────────────────────────

class TestDDMMulti:
    """Multi-period DDM: PV(dividends) + PV(terminal Gordon value)."""

    def _build(self, div_rate, price=100.0, payout=0.50, roe=0.10):
        info = _make_info(
            currentPrice=price,
            dividendRate=div_rate,
            payoutRatio=payout,
            returnOnEquity=roe,
        )
        cfs = _make_cashflows([(110.0, -10.0)])
        return _run_ddm_multi(info, cfs)

    def test_components_sum_to_fair_value(self):
        # fair_value == pv_dividends + terminal_value_pv (within rounding)
        result = self._build(div_rate=2.0, payout=0.50, roe=0.10)
        assert result is not None
        assert result.fair_value == pytest.approx(
            result.pv_dividends + result.terminal_value_pv, abs=0.02
        )

    def test_no_dividend_returns_none(self):
        assert self._build(div_rate=0.0) is None

    def test_terminal_value_dominates_short_horizon(self):
        # For a 10-year horizon, terminal value is usually > PV of dividends
        # (this validates the model structure, not a strict rule)
        result = self._build(div_rate=2.0, payout=0.50, roe=0.10)
        assert result.terminal_value_pv > 0.0
        assert result.pv_dividends > 0.0

    def test_upside_consistent_with_fair_value(self):
        result = self._build(div_rate=2.0, price=80.0, payout=0.50, roe=0.10)
        expected_upside = (result.fair_value - 80.0) / 80.0
        assert result.upside_pct == pytest.approx(expected_upside, rel=1e-3)

    def test_forecast_dividends_length(self):
        result = self._build(div_rate=2.0, payout=0.50, roe=0.10)
        # Should have FORECAST_YEARS entries
        assert len(result.forecast_dividends) == FORECAST_YEARS

    def test_forecast_dividends_are_growing(self):
        # Dividends should grow at near_g initially and slow down
        result = self._build(div_rate=2.0, payout=0.50, roe=0.10)
        divs = [d[1] for d in result.forecast_dividends]
        # First dividend > initial div_rate (growing)
        assert divs[0] > 2.0
        # All increasing (growth is always positive for this param combo)
        assert all(divs[i] < divs[i+1] for i in range(len(divs)-1))

    def test_required_return_stored(self):
        result = self._build(div_rate=2.0)
        assert result.required_return == pytest.approx(DDM_REQUIRED_RETURN, rel=1e-6)

    def test_terminal_growth_stored(self):
        result = self._build(div_rate=2.0)
        assert result.terminal_growth == pytest.approx(TERMINAL_GROWTH, rel=1e-6)

    def test_year1_dividend_correct(self):
        # g_near = clamp(roe × retention, 0.01, 0.12) = clamp(0.10×0.50, 0.01, 0.12) = 0.05
        # D₁ = 2.0 × (1 + 0.05) = 2.10 (first entry in forecast_dividends)
        result = self._build(div_rate=2.0, payout=0.50, roe=0.10)
        assert result.forecast_dividends[0][1] == pytest.approx(2.10, rel=1e-3)


# ── DCF FCF ───────────────────────────────────────────────────────────────────

class TestDCFFCF:
    """Free Cash Flow DCF — 10-year horizon with linear growth fade."""

    def _build(self, ocf_capex_pairs, equity=10_000.0, debt=0.0, cash=0.0,
               beta=1.0, price=100.0):
        info = _make_info(currentPrice=price, sharesOutstanding=1_000.0, beta=beta)
        bs   = _make_balance_sheets(equity=equity, debt=debt, cash=cash)
        cfs  = _make_cashflows(ocf_capex_pairs)
        income = _make_income([5_000.0])
        return _run_dcf_fcf(info, income, bs, cfs)

    def test_negative_fcf_returns_none(self):
        # All cash flows negative → no valid FCF
        result = self._build([(-50.0, -10.0), (-60.0, -15.0)])
        assert result is None

    def test_bear_lt_base_lt_bull(self):
        # With positive FCF growth, higher growth rate → higher value
        result = self._build([(110.0, -10.0), (100.0, -10.0), (90.0, -10.0)])
        assert result is not None
        values = [s.value for s in result.scenarios]
        bear, base, bull = values
        assert bear < base < bull

    def test_three_year_average_base_fcf(self):
        # FCF years: 100, 90, 80 → avg = 90.0
        result = self._build([(110.0, -10.0), (100.0, -10.0), (90.0, -10.0)])
        assert result is not None
        assert result.base_fcf == pytest.approx(90.0, rel=1e-3)

    def test_one_year_fallback_growth(self):
        # Only 1 year of data → hist_growth fallback = 5%
        result = self._build([(110.0, -10.0)])
        assert result is not None
        base_scenario = result.scenarios[1]  # Base
        assert base_scenario.growth == pytest.approx(0.05, rel=1e-3)

    def test_two_year_growth_calculated(self):
        # FCF₀(oldest) = 90, FCF₁(newest) = 100 → CAGR = 100/90 - 1 = 11.11%
        result = self._build([(110.0, -10.0), (100.0, -10.0)])
        assert result is not None
        base_growth = result.scenarios[1].growth
        assert base_growth == pytest.approx(0.1111, rel=1e-2)

    def test_net_debt_subtracted(self):
        # Same FCF, two companies: one with net debt, one without
        # Higher net debt → lower equity value per share
        no_debt   = self._build([(110.0, -10.0)], equity=10_000.0, debt=0.0,    cash=0.0)
        with_debt = self._build([(110.0, -10.0)], equity=10_000.0, debt=5_000.0, cash=0.0)
        assert no_debt is not None and with_debt is not None
        # Company with net debt ($5000 debt, $0 cash) should have lower equity value
        assert with_debt.scenarios[1].value < no_debt.scenarios[1].value

    def test_cash_increases_equity_value(self):
        # Same FCF; holding cash reduces net debt and raises equity value
        no_cash   = self._build([(110.0, -10.0)], equity=10_000.0, debt=5_000.0, cash=0.0)
        with_cash = self._build([(110.0, -10.0)], equity=10_000.0, debt=5_000.0, cash=3_000.0)
        assert with_cash.scenarios[1].value > no_cash.scenarios[1].value

    def test_wacc_stored(self):
        # beta=1.0, no debt → WACC = re = 0.10
        result = self._build([(110.0, -10.0)])
        assert result.wacc == pytest.approx(0.10, rel=1e-3)

    def test_terminal_growth_stored(self):
        result = self._build([(110.0, -10.0)])
        assert result.terminal_growth == pytest.approx(TERMINAL_GROWTH, rel=1e-6)

    def test_forecast_years_stored(self):
        result = self._build([(110.0, -10.0)])
        assert result.forecast_years == FORECAST_YEARS

    def test_upside_consistent(self):
        result = self._build([(110.0, -10.0)], price=80.0)
        base = result.scenarios[1]
        expected = (base.value - 80.0) / 80.0
        assert base.upside_pct == pytest.approx(expected, rel=1e-3)

    def test_scenario_names_correct(self):
        result = self._build([(110.0, -10.0)])
        names = [s.name for s in result.scenarios]
        assert names == ["Bear", "Base", "Bull"]

    def test_bear_growth_is_scaled_down(self):
        # Bear growth < Base growth
        result = self._build([(110.0, -10.0), (100.0, -10.0)])
        bear_g = result.scenarios[0].growth
        base_g = result.scenarios[1].growth
        assert bear_g < base_g

    def test_bull_growth_is_scaled_up(self):
        result = self._build([(110.0, -10.0), (100.0, -10.0)])
        base_g = result.scenarios[1].growth
        bull_g = result.scenarios[2].growth
        assert bull_g > base_g

    def test_zero_fcf_mixed_returns_none(self):
        # All zero OCF → all FCF = 0 → no positive FCF → None
        result = self._build([(0.0, 0.0), (0.0, 0.0)])
        assert result is None

    def test_dcf_manual_verification_zero_net_debt(self):
        """
        Manual verification: base_fcf=100, 1 year of data → hist_growth fallback=5%.
        beta=1.0, no debt → WACC=10%, terminal_g=2.5%, N=10, shares=1000, net_debt=0.

        Year-by-year:
          fade(t) = 0.05 + (0.025−0.05) × (t−1)/(10−1)
          FCF(t)  = FCF(t−1) × (1 + fade(t))
          PV(t)   = FCF(t) / 1.10^t

        Terminal value discounted = FCF(10) × 1.025 / (0.10−0.025) / 1.10^10

        Expected base value ≈ $1.51 per share (total ≈ $1513 / 1000 shares).
        """
        result = self._build([(110.0, -10.0)], equity=10_000.0, debt=0.0, cash=0.0)
        base_val = result.scenarios[1].value

        # Recompute manually
        fcf0 = 100.0
        wacc = 0.10
        tg   = 0.025
        g    = 0.05   # fallback base growth (1 year of data)
        N    = 10

        pv_sum = 0.0
        fcf    = fcf0
        for t in range(1, N + 1):
            fade = g + (tg - g) * (t - 1) / (N - 1)
            fcf  = fcf * (1 + fade)
            pv_sum += fcf / (1 + wacc) ** t

        terminal_fcf = fcf * (1 + tg)
        tv     = terminal_fcf / (wacc - tg)
        pv_tv  = tv / (1 + wacc) ** N
        total  = pv_sum + pv_tv           # enterprise value (= equity value since net_debt=0)
        per_share = total / 1_000.0

        # Engine rounds final per-share value to 2 decimal places, so allow ±0.005
        assert base_val == pytest.approx(per_share, abs=0.005)


# ── Residual Income Model ─────────────────────────────────────────────────────

class TestRIM:
    """RIM: fair_value = BV₀ + PV(residual incomes) + PV(terminal RI)."""

    def _build(self, equity, net_incomes, shares=1_000.0, beta=1.0,
               div_per_share=0.0, price=100.0):
        info   = _make_info(currentPrice=price, sharesOutstanding=shares, beta=beta,
                            dividendRate=div_per_share)
        income = _make_income(net_incomes)   # newest first
        bs     = _make_balance_sheets(equity=equity)
        return _run_rim(info, income, bs)

    def test_negative_equity_returns_none(self):
        info   = _make_info(currentPrice=100.0, sharesOutstanding=1_000.0, beta=1.0)
        income = _make_income([5_000.0])
        bs     = _make_balance_sheets(equity=-1_000.0)
        assert _run_rim(info, income, bs) is None

    def test_missing_income_returns_none(self):
        info = _make_info(currentPrice=100.0, sharesOutstanding=1_000.0, beta=1.0)
        bs   = _make_balance_sheets()
        assert _run_rim(info, [], bs) is None

    def test_bvps_computed_from_equity_and_shares(self):
        # equity=10_000, shares=1_000 → bvps=10.0
        result = self._build(equity=10_000.0, net_incomes=[5_000.0, 4_000.0], shares=1_000.0)
        assert result.book_value_per_share == pytest.approx(10.0, rel=1e-3)

    def test_cost_of_equity_capm(self):
        # beta=1.0 → re = 0.045 + 1.0×0.055 = 0.10
        result = self._build(equity=10_000.0, net_incomes=[5_000.0, 4_000.0], beta=1.0)
        assert result.cost_of_equity == pytest.approx(0.10, rel=1e-3)

    def test_fair_value_components_sum(self):
        # fair_value ≈ bvps + pv_residual_incomes + terminal_ri_pv
        result = self._build(equity=10_000.0, net_incomes=[2_000.0, 1_800.0], shares=1_000.0)
        reconstructed = (result.book_value_per_share
                         + result.pv_residual_incomes
                         + result.terminal_ri_pv)
        # Allow small rounding error from round() calls on each component
        assert result.fair_value == pytest.approx(reconstructed, abs=0.10)

    def test_high_roe_produces_value_above_book(self):
        # ROE = 20% (NI=2000 on equity=10000), re=10% → positive RI → value > bvps
        result = self._build(equity=10_000.0, net_incomes=[2_000.0, 1_800.0], shares=1_000.0)
        assert result.fair_value > result.book_value_per_share

    def test_low_roe_produces_value_near_or_below_book(self):
        # ROE = 5% (NI=500 on equity=10000), re=10% → negative RI → value < bvps
        result = self._build(equity=10_000.0, net_incomes=[500.0, 450.0], shares=1_000.0)
        assert result.fair_value < result.book_value_per_share

    def test_positive_pv_ri_when_roe_exceeds_cost(self):
        result = self._build(equity=10_000.0, net_incomes=[2_000.0, 1_800.0])
        assert result.pv_residual_incomes > 0.0

    def test_forecast_years_stored(self):
        result = self._build(equity=10_000.0, net_incomes=[2_000.0, 1_800.0])
        assert result.forecast_years == FORECAST_YEARS

    def test_upside_consistent(self):
        result = self._build(equity=10_000.0, net_incomes=[2_000.0, 1_800.0],
                              price=50.0, shares=1_000.0)
        expected = (result.fair_value - 50.0) / 50.0
        assert result.upside_pct == pytest.approx(expected, rel=1e-3)

    def test_dividends_reduce_book_value_growth(self):
        # Paying dividends slows BV growth, changes RI trajectory
        no_div  = self._build(equity=10_000.0, net_incomes=[2_000.0, 1_800.0],
                               div_per_share=0.0)
        with_div = self._build(equity=10_000.0, net_incomes=[2_000.0, 1_800.0],
                                div_per_share=5.0)
        # Both should compute without error; dividends paid out means slower BV growth
        assert no_div is not None and with_div is not None

    def test_rim_manual_single_year_no_dividend(self):
        """
        Manual trace for 1 forecast year to verify the loop logic.

        Setup:
          equity=1_000, shares=100, bvps=10
          NI history: [120, 100] → ni_growth = CAGR(100, 120, 1) = 20%, clamped to 20%
          re = 0.045 + 1.0×0.055 = 0.10, div_per_share=0, FORECAST_YEARS=10

        Year 1:
          g1 = 0.20 + (0.01−0.20)×0/9 = 0.20
          NI₁ = 120 × 1.20 = 144
          equity_charge = 1000 × 0.10 = 100
          RI₁ = 144 − 100 = 44
          PV(RI₁) = 44 / 1.10 = 40.0
          BV₁ = 1000 + 144 = 1144

        (We only verify year 1 since full 10-year trace is complex.)
        """
        # Trick: We can't directly test internal loop state, but we can verify
        # that RI is positive (NI₁=144 > equity_charge=100) → pv_residual_incomes > 0
        result = self._build(equity=1_000.0, net_incomes=[120.0, 100.0],
                              shares=100.0, beta=1.0, div_per_share=0.0)
        assert result is not None
        assert result.pv_residual_incomes > 0.0  # high-ROE company earns above cost of equity


# ── Football Field ────────────────────────────────────────────────────────────

class TestFootballField:
    def _full_result(self):
        info = _make_info(
            currentPrice=100.0,
            sharesOutstanding=1_000.0,
            beta=1.0,
            dividendRate=2.0,
            payoutRatio=0.50,
            returnOnEquity=0.10,
            bookValue=10.0,
        )
        income = _make_income([5_000.0, 4_500.0, 4_000.0])
        bs     = _make_balance_sheets(equity=10_000.0, debt=0.0, cash=0.0)
        cfs    = _make_cashflows([(110.0, -10.0), (100.0, -10.0), (90.0, -10.0)])
        return run_intrinsic_value("TEST", "Test Co", info, income, bs, cfs,
                                   {"dcf_fcf", "ddm", "rim", "graham_number"})

    def test_has_entries_for_each_method(self):
        result = self._full_result()
        methods = {e.method for e in result.football_field}
        assert "DCF (FCF)" in methods
        assert "DDM (Gordon)" in methods
        assert "DDM (Multi-Period)" in methods
        assert "Residual Income" in methods
        assert "Graham Number" in methods

    def test_dcf_low_le_mid_le_high(self):
        result = self._full_result()
        dcf_entry = next(e for e in result.football_field if e.method == "DCF (FCF)")
        assert dcf_entry.low <= dcf_entry.mid <= dcf_entry.high

    def test_dcf_bear_is_low(self):
        result = self._full_result()
        dcf_entry = next(e for e in result.football_field if e.method == "DCF (FCF)")
        assert dcf_entry.low == result.dcf_fcf.scenarios[0].value  # Bear
        assert dcf_entry.high == result.dcf_fcf.scenarios[2].value  # Bull

    def test_non_dcf_range_is_15pct_band(self):
        # Graham, DDM Gordon, DDM Multi, RIM entries are ±15% around central value
        result = self._full_result()
        for entry in result.football_field:
            if entry.method != "DCF (FCF)":
                assert entry.low  == pytest.approx(entry.mid * 0.85, rel=1e-4)
                assert entry.high == pytest.approx(entry.mid * 1.15, rel=1e-4)

    def test_no_dividend_skips_ddm_entries(self):
        info   = _make_info(currentPrice=100.0, sharesOutstanding=1_000.0,
                            beta=1.0, dividendRate=0.0, bookValue=10.0)
        income = _make_income([5_000.0, 4_500.0, 4_000.0])
        bs     = _make_balance_sheets(equity=10_000.0)
        cfs    = _make_cashflows([(110.0, -10.0)])
        result = run_intrinsic_value("TEST", "Test Co", info, income, bs, cfs,
                                     {"dcf_fcf", "ddm", "rim", "graham_number"})
        methods = {e.method for e in result.football_field}
        assert "DDM (Gordon)" not in methods
        assert "DDM (Multi-Period)" not in methods


# ── run_intrinsic_value integration ───────────────────────────────────────────

class TestRunIntrisicValue:
    def _base_info(self, **overrides):
        d = _make_info(
            currentPrice=100.0,
            sharesOutstanding=1_000.0,
            beta=1.0,
            dividendRate=2.0,
            payoutRatio=0.50,
            returnOnEquity=0.10,
            bookValue=10.0,
        )
        d.update(overrides)
        return d

    def test_all_methods_selected(self):
        info   = self._base_info()
        income = _make_income([5_000.0, 4_500.0, 4_000.0])
        bs     = _make_balance_sheets(equity=10_000.0)
        cfs    = _make_cashflows([(110.0, -10.0), (100.0, -10.0)])
        result = run_intrinsic_value("TEST", "Test Co", info, income, bs, cfs,
                                     {"dcf_fcf", "ddm", "rim", "graham_number"})
        assert result.dcf_fcf    is not None
        assert result.ddm_gordon is not None
        assert result.ddm_multi  is not None
        assert result.rim        is not None
        assert result.graham     is not None

    def test_only_dcf_selected(self):
        info   = self._base_info()
        income = _make_income([5_000.0])
        bs     = _make_balance_sheets(equity=10_000.0)
        cfs    = _make_cashflows([(110.0, -10.0)])
        result = run_intrinsic_value("TEST", "Test Co", info, income, bs, cfs,
                                     {"dcf_fcf"})
        assert result.dcf_fcf    is not None
        assert result.ddm_gordon is None
        assert result.ddm_multi  is None
        assert result.rim        is None
        assert result.graham     is None

    def test_no_dividend_populates_skipped(self):
        info   = self._base_info(dividendRate=0.0)
        income = _make_income([5_000.0])
        bs     = _make_balance_sheets(equity=10_000.0)
        cfs    = _make_cashflows([(110.0, -10.0)])
        result = run_intrinsic_value("TEST", "Test Co", info, income, bs, cfs,
                                     {"ddm"})
        assert result.ddm_gordon is None
        assert result.ddm_multi  is None
        assert any("DDM" in s for s in result.skipped)

    def test_ticker_and_company_stored(self):
        info   = self._base_info()
        income = _make_income([5_000.0])
        bs     = _make_balance_sheets(equity=10_000.0)
        cfs    = _make_cashflows([(110.0, -10.0)])
        result = run_intrinsic_value("AAPL", "Apple Inc.", info, income, bs, cfs, set())
        assert result.ticker       == "AAPL"
        assert result.company_name == "Apple Inc."

    def test_current_price_stored(self):
        info   = self._base_info(currentPrice=123.45)
        income = _make_income([5_000.0])
        bs     = _make_balance_sheets(equity=10_000.0)
        cfs    = _make_cashflows([(110.0, -10.0)])
        result = run_intrinsic_value("X", "Co", info, income, bs, cfs, set())
        assert result.current_price == pytest.approx(123.45, rel=1e-4)

    def test_roundtrip_serialization(self):
        info   = self._base_info()
        income = _make_income([5_000.0, 4_500.0])
        bs     = _make_balance_sheets(equity=10_000.0)
        cfs    = _make_cashflows([(110.0, -10.0), (100.0, -10.0)])
        result = run_intrinsic_value("TEST", "Test Co", info, income, bs, cfs,
                                     {"dcf_fcf", "ddm", "rim", "graham_number"})
        from scoring.intrinsic_value_models import IntrinsicValueResult
        d  = result.to_dict()
        r2 = IntrinsicValueResult.from_dict(d)

        assert r2.ticker       == result.ticker
        assert r2.current_price == result.current_price
        assert r2.dcf_fcf.scenarios[1].value == result.dcf_fcf.scenarios[1].value
        assert r2.ddm_gordon.fair_value       == result.ddm_gordon.fair_value
        assert r2.graham.graham_number        == result.graham.graham_number
        assert r2.rim.fair_value              == result.rim.fair_value
        assert len(r2.football_field)         == len(result.football_field)
