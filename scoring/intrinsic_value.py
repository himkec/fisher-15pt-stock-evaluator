"""
Intrinsic Value / Valuation Models engine.

Supported methods:
  DCF_FCF        — Free Cash Flow DCF (Bear / Base / Bull)
  DDM_GORDON     — Gordon Growth Dividend Discount Model
  DDM_MULTI      — Multi-period DDM
  RIM            — Residual Income Model
  GRAHAM_NUMBER  — Graham Number and defensive checks
"""

import math
from typing import Any

from scoring.intrinsic_value_models import (
    IntrinsicValueResult,
    DCFFCFResult, IVScenario,
    DDMGordonResult, DDMMultiPeriodResult,
    RIMResult, GrahamResult,
    FootballFieldEntry,
)

# ── Constants ──────────────────────────────────────────────────────────────────

RISK_FREE_RATE     = 0.045   # 10-yr Treasury approx
EQUITY_RISK_PREMIUM = 0.055  # standard ERP
DEFAULT_TAX_RATE   = 0.21
TERMINAL_GROWTH    = 0.025   # long-run perpetual growth
FORECAST_YEARS     = 10

DDM_REQUIRED_RETURN = 0.09
RIM_TERMINAL_RI_GROWTH = 0.01


# ── Helpers ───────────────────────────────────────────────────────────────────

def _s(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        f = float(val)
        return default if (f != f) else f  # NaN guard
    except (TypeError, ValueError):
        return default


def _cagr(start: float, end: float, years: int) -> float:
    if start <= 0 or years <= 0:
        return 0.0
    return (end / start) ** (1 / years) - 1


def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


def _wacc(info: dict, balance_sheets: list) -> float:
    """Estimate WACC from CAPM cost of equity + debt weight."""
    beta = _s(info.get("beta"), 1.0)
    beta = _clamp(beta, 0.5, 2.5)
    re = RISK_FREE_RATE + beta * EQUITY_RISK_PREMIUM   # cost of equity

    bs = balance_sheets[0] if balance_sheets else {}
    total_debt  = abs(_s(bs.get("totalDebt")))
    total_equity = abs(_s(bs.get("totalStockholdersEquity")))
    if total_equity <= 0:
        # Can't compute WACC properly — fall back to pure equity cost
        return _clamp(re, 0.06, 0.20)

    total_cap = total_debt + total_equity
    we = total_equity / total_cap
    wd = total_debt / total_cap

    rd = _s(info.get("averageInterestRate") or info.get("debtInterestRate"), 0.05)
    if rd <= 0 or rd > 0.30:
        rd = 0.05   # reasonable default

    wacc = we * re + wd * rd * (1 - DEFAULT_TAX_RATE)
    return _clamp(wacc, 0.06, 0.20)


def _shares(info: dict) -> float:
    shares = _s(info.get("sharesOutstanding"))
    if shares <= 0:
        shares = _s(info.get("impliedSharesOutstanding"))
    return shares if shares > 0 else 1.0


def _current_price(info: dict) -> float:
    price = _s(info.get("currentPrice") or info.get("regularMarketPrice"))
    return price if price > 0 else 1.0


def _upside(intrinsic: float, price: float) -> float:
    return (intrinsic - price) / price if price > 0 else 0.0


# ── DCF FCF ───────────────────────────────────────────────────────────────────

def _run_dcf_fcf(info: dict, income_stmts: list, balance_sheets: list,
                  cash_flows: list) -> DCFFCFResult | None:
    """10-year FCF DCF with Bear/Base/Bull scenarios."""
    if not cash_flows:
        return None

    # Base FCF: 3-year average of (CFO - capex)
    fcf_vals = []
    for cf in cash_flows[:3]:
        cfo   = _s(cf.get("operatingCashFlow") or cf.get("freeCashFlow"))
        capex = abs(_s(cf.get("capitalExpenditure")))
        fcf   = cfo - capex if cfo != 0 else _s(cf.get("freeCashFlow"))
        if fcf != 0:
            fcf_vals.append(fcf)

    if not fcf_vals or all(v <= 0 for v in fcf_vals):
        return None

    base_fcf = sum(fcf_vals) / len(fcf_vals)
    if base_fcf <= 0:
        return None

    wacc = _wacc(info, balance_sheets)
    terminal_g = TERMINAL_GROWTH
    shares = _shares(info)
    price  = _current_price(info)

    # Estimate historical FCF growth for Base scenario
    if len(fcf_vals) >= 2 and fcf_vals[-1] > 0:
        hist_growth = _cagr(fcf_vals[-1], fcf_vals[0], len(fcf_vals) - 1)
    else:
        hist_growth = 0.05   # fallback

    # Clamp to sensible ranges
    base_growth = _clamp(hist_growth, -0.05, 0.30)
    bear_growth = _clamp(base_growth * 0.6, -0.10, 0.15)
    bull_growth = _clamp(base_growth * 1.5,  0.00, 0.40)

    notes = []

    def _dcf_value(near_g: float) -> float:
        """DCF value per share: fade near-term growth to terminal over FORECAST_YEARS."""
        pv_sum = 0.0
        fcf = base_fcf
        for t in range(1, FORECAST_YEARS + 1):
            # Linear fade from near_g to terminal_g over the forecast horizon
            fade = near_g + (terminal_g - near_g) * (t - 1) / (FORECAST_YEARS - 1)
            fcf = fcf * (1 + fade)
            pv_sum += fcf / (1 + wacc) ** t
        # Terminal value at end of forecast
        terminal_fcf = fcf * (1 + terminal_g)
        tv = terminal_fcf / (wacc - terminal_g) if wacc > terminal_g else 0
        pv_tv = tv / (1 + wacc) ** FORECAST_YEARS
        total_equity_value = pv_sum + pv_tv
        # Subtract net debt to get equity value (for firm-level FCF)
        bs = balance_sheets[0] if balance_sheets else {}
        net_debt = abs(_s(bs.get("totalDebt"))) - abs(_s(bs.get("cashAndCashEquivalents")))
        equity_val = total_equity_value - net_debt
        return equity_val / shares

    scenarios = []
    for label, g in [("Bear", bear_growth), ("Base", base_growth), ("Bull", bull_growth)]:
        iv = _dcf_value(g)
        scenarios.append(IVScenario(
            name=label, value=round(iv, 2), growth=round(g, 4),
            upside_pct=round(_upside(iv, price), 4),
        ))

    return DCFFCFResult(
        base_fcf=round(base_fcf, 0),
        wacc=round(wacc, 4),
        terminal_growth=round(terminal_g, 4),
        forecast_years=FORECAST_YEARS,
        scenarios=scenarios,
        notes=notes,
    )


# ── DDM Gordon Growth ─────────────────────────────────────────────────────────

def _run_ddm_gordon(info: dict, income_stmts: list, cash_flows: list) -> DDMGordonResult | None:
    """Gordon Growth DDM — only viable for stable dividend payers."""
    div_rate = _s(info.get("dividendRate") or info.get("lastDividendValue"))
    if div_rate <= 0:
        return None   # Company doesn't pay a dividend

    price   = _current_price(info)
    r       = DDM_REQUIRED_RETURN
    div_yield = div_rate / price if price > 0 else 0.0

    # Estimate sustainable long-term dividend growth (≤ 3% or div CAGR, whichever is lower)
    eps_ttm = _s(info.get("trailingEps"))
    payout  = _s(info.get("payoutRatio"))
    if payout <= 0 and eps_ttm > 0:
        payout = div_rate / eps_ttm

    # Long-term growth: use ROE × retention ratio as sustainable growth proxy
    roe = _s(info.get("returnOnEquity"))
    retention = 1 - _clamp(payout, 0, 1)
    sustainable_g = _clamp(roe * retention, 0.0, 0.10)
    if sustainable_g <= 0:
        sustainable_g = 0.03   # fallback

    g = _clamp(sustainable_g, 0.0, r - 0.01)   # must be < r
    if r <= g:
        return None  # Model invalid

    d1 = div_rate * (1 + g)
    fair_value = d1 / (r - g)

    # FCF payout
    fcf_payout = 0.0
    if cash_flows:
        cf = cash_flows[0]
        cfo   = _s(cf.get("operatingCashFlow"))
        capex = abs(_s(cf.get("capitalExpenditure")))
        fcf   = cfo - capex if cfo > 0 else _s(cf.get("freeCashFlow"))
        shares = _shares(info)
        fcf_ps = fcf / shares if shares > 0 else 0
        fcf_payout = div_rate / fcf_ps if fcf_ps > 0 else 0.0

    notes = []
    if payout > 0.80:
        notes.append(f"High payout ratio ({payout:.0%}) — dividend sustainability risk.")
    if g < 0.02:
        notes.append("Low estimated dividend growth — Gordon model may undervalue growth potential.")

    return DDMGordonResult(
        d1=round(d1, 4),
        required_return=r,
        perpetual_growth=round(g, 4),
        fair_value=round(fair_value, 2),
        current_price=price,
        upside_pct=round(_upside(fair_value, price), 4),
        current_yield=round(div_yield, 4),
        payout_ratio_eps=round(payout, 4),
        payout_ratio_fcf=round(fcf_payout, 4),
        yield_plus_growth=round(div_yield + g, 4),
        valid=True,
        notes=notes,
    )


# ── DDM Multi-Period ──────────────────────────────────────────────────────────

def _run_ddm_multi(info: dict, cash_flows: list) -> DDMMultiPeriodResult | None:
    """10-year explicit DDM + Gordon terminal value."""
    div_rate = _s(info.get("dividendRate") or info.get("lastDividendValue"))
    if div_rate <= 0:
        return None

    price = _current_price(info)
    r     = DDM_REQUIRED_RETURN

    # Near-term growth: use ROE × retention or a modest 5%
    payout = _s(info.get("payoutRatio"))
    roe    = _s(info.get("returnOnEquity"))
    retention = 1 - _clamp(payout, 0, 1)
    g_near = _clamp(roe * retention, 0.01, 0.12)
    if g_near <= 0:
        g_near = 0.04

    g_term = TERMINAL_GROWTH   # long-run

    if r <= g_term:
        return None

    forecast_divs = []
    div = div_rate
    pv_divs = 0.0
    for t in range(1, FORECAST_YEARS + 1):
        # Fade near-term growth to terminal growth linearly
        g = g_near + (g_term - g_near) * (t - 1) / (FORECAST_YEARS - 1)
        div = div * (1 + g)
        pv  = div / (1 + r) ** t
        pv_divs += pv
        forecast_divs.append([t, round(div, 4)])

    # Terminal value via Gordon at year 10
    terminal_div = div * (1 + g_term)
    tv = terminal_div / (r - g_term)
    tv_pv = tv / (1 + r) ** FORECAST_YEARS

    fair_value = pv_divs + tv_pv

    return DDMMultiPeriodResult(
        forecast_dividends=forecast_divs,
        terminal_value_pv=round(tv_pv, 2),
        pv_dividends=round(pv_divs, 2),
        fair_value=round(fair_value, 2),
        current_price=price,
        upside_pct=round(_upside(fair_value, price), 4),
        required_return=r,
        terminal_growth=g_term,
        notes=[],
    )


# ── Residual Income Model ─────────────────────────────────────────────────────

def _run_rim(info: dict, income_stmts: list, balance_sheets: list) -> RIMResult | None:
    """BV₀ + PV(residual incomes) over 10 years + terminal RI."""
    if not balance_sheets or not income_stmts:
        return None

    bs = balance_sheets[0]
    total_equity = _s(bs.get("totalStockholdersEquity"))
    if total_equity <= 0:
        return None

    shares = _shares(info)
    price  = _current_price(info)
    bvps   = total_equity / shares if shares > 0 else _s(info.get("bookValue"))
    if bvps <= 0:
        bvps = _s(info.get("bookValue"))
    if bvps <= 0:
        return None

    # Cost of equity via CAPM
    beta = _clamp(_s(info.get("beta"), 1.0), 0.5, 2.5)
    re   = RISK_FREE_RATE + beta * EQUITY_RISK_PREMIUM
    re   = _clamp(re, 0.06, 0.20)

    # Net income growth estimate from historical trend
    nis = [_s(s.get("netIncome")) for s in income_stmts if _s(s.get("netIncome")) != 0]
    if len(nis) >= 2 and nis[-1] > 0:
        ni_growth = _clamp(_cagr(nis[-1], nis[0], len(nis) - 1), -0.05, 0.25)
    else:
        ni_growth = 0.05   # fallback

    # Annual dividend per share
    div_per_share = _s(info.get("dividendRate") or info.get("lastDividendValue"), 0.0)

    # RIM calculation
    bv  = total_equity
    pv_ri_sum = 0.0
    for t in range(1, FORECAST_YEARS + 1):
        # Fade NI growth toward terminal growth
        g = ni_growth + (RIM_TERMINAL_RI_GROWTH - ni_growth) * (t - 1) / (FORECAST_YEARS - 1)
        ni = bv * (re + g)   # implied NI from ROE = re + growth premium approximation
        # Simpler: grow last NI by faded growth rate
    # Restart with simpler explicit approach
    pv_ri_sum = 0.0
    bv = total_equity
    last_ni = _s(income_stmts[0].get("netIncome")) if income_stmts else total_equity * 0.10
    if last_ni <= 0:
        last_ni = total_equity * 0.08
    ni = last_ni

    for t in range(1, FORECAST_YEARS + 1):
        g = ni_growth + (RIM_TERMINAL_RI_GROWTH - ni_growth) * (t - 1) / (FORECAST_YEARS - 1)
        ni = ni * (1 + g)
        equity_charge = bv * re
        ri = ni - equity_charge
        pv_ri_sum += ri / (1 + re) ** t
        # Update book value: BV += NI - dividends paid
        divs_total = div_per_share * shares
        bv = bv + ni - divs_total

    # Terminal residual income at year FORECAST_YEARS + 1
    terminal_ni = ni * (1 + RIM_TERMINAL_RI_GROWTH)
    terminal_ec = bv * re
    terminal_ri = terminal_ni - terminal_ec
    if re > RIM_TERMINAL_RI_GROWTH:
        tv_ri = terminal_ri / (re - RIM_TERMINAL_RI_GROWTH)
    else:
        tv_ri = terminal_ri * 10   # cap
    pv_tv_ri = tv_ri / (1 + re) ** FORECAST_YEARS

    intrinsic_equity = total_equity + pv_ri_sum + pv_tv_ri
    fair_value = intrinsic_equity / shares

    notes = []
    if ni_growth < 0:
        notes.append("Negative NI growth — RIM likely understates value if trajectory improves.")

    return RIMResult(
        book_value_per_share=round(bvps, 2),
        cost_of_equity=round(re, 4),
        pv_residual_incomes=round(pv_ri_sum / shares, 2),
        terminal_ri_pv=round(pv_tv_ri / shares, 2),
        fair_value=round(fair_value, 2),
        current_price=price,
        upside_pct=round(_upside(fair_value, price), 4),
        forecast_years=FORECAST_YEARS,
        notes=notes,
    )


# ── Graham Number ─────────────────────────────────────────────────────────────

def _run_graham(info: dict, income_stmts: list, balance_sheets: list) -> GrahamResult | None:
    """Graham Number = sqrt(22.5 × EPS × BVPS)."""
    # EPS: prefer 3-yr average over TTM for stability
    eps_vals = [_s(s.get("netIncome")) for s in income_stmts[:3]]
    shares = _shares(info)
    eps_list = [e / shares for e in eps_vals if e > 0 and shares > 0]
    if eps_list:
        eps = sum(eps_list) / len(eps_list)
    else:
        eps = _s(info.get("trailingEps"))

    if eps <= 0:
        return None   # Graham Number requires positive EPS

    # Book value per share
    bvps = _s(info.get("bookValue"))
    if bvps <= 0 and balance_sheets:
        bs = balance_sheets[0]
        eq = _s(bs.get("totalStockholdersEquity"))
        bvps = eq / shares if shares > 0 else 0

    if bvps <= 0:
        return None

    graham_num = math.sqrt(22.5 * eps * bvps)
    price = _current_price(info)
    ptg   = price / graham_num if graham_num > 0 else 0.0

    if ptg < 0.90:
        label = "Below Graham ceiling"
    elif ptg <= 1.10:
        label = "At Graham ceiling"
    else:
        label = "Above Graham ceiling"

    # Optional defensive checks
    checks = {}
    # Earnings stability: positive EPS for last N years
    ni_history = [_s(s.get("netIncome")) for s in income_stmts]
    checks["earnings_stability"] = all(ni > 0 for ni in ni_history) if ni_history else False

    # Dividend record (any dividend paid)
    checks["pays_dividend"] = _s(info.get("dividendRate")) > 0

    # P/E check (< 15)
    pe = _s(info.get("trailingPE"))
    checks["pe_below_15"] = (0 < pe < 15) if pe else False

    # P/B check (< 1.5)
    pb = _s(info.get("priceToBook"))
    checks["pb_below_1_5"] = (0 < pb < 1.5) if pb else False

    notes = []
    if ptg > 2.0:
        notes.append(f"Price is {ptg:.1f}× Graham Number — significantly above conservative ceiling.")
    if eps < 1.0:
        notes.append("Low absolute EPS — Graham Number result is sensitive to EPS changes.")

    return GrahamResult(
        eps=round(eps, 2),
        bvps=round(bvps, 2),
        graham_number=round(graham_num, 2),
        current_price=price,
        price_to_graham=round(ptg, 3),
        label=label,
        upside_pct=round(_upside(graham_num, price), 4),
        checks=checks,
        notes=notes,
    )


# ── Football field aggregation ────────────────────────────────────────────────

def _build_football_field(result: IntrinsicValueResult) -> list:
    entries = []
    price = result.current_price

    if result.dcf_fcf and result.dcf_fcf.scenarios:
        vals = [s.value for s in result.dcf_fcf.scenarios]
        entries.append(FootballFieldEntry(
            method="DCF (FCF)", low=min(vals), mid=vals[1], high=max(vals),
        ))

    if result.ddm_gordon and result.ddm_gordon.valid:
        fv = result.ddm_gordon.fair_value
        entries.append(FootballFieldEntry(
            method="DDM (Gordon)", low=fv * 0.85, mid=fv, high=fv * 1.15,
        ))

    if result.ddm_multi:
        fv = result.ddm_multi.fair_value
        entries.append(FootballFieldEntry(
            method="DDM (Multi-Period)", low=fv * 0.85, mid=fv, high=fv * 1.15,
        ))

    if result.rim:
        fv = result.rim.fair_value
        entries.append(FootballFieldEntry(
            method="Residual Income", low=fv * 0.85, mid=fv, high=fv * 1.15,
        ))

    if result.graham:
        gn = result.graham.graham_number
        entries.append(FootballFieldEntry(
            method="Graham Number", low=gn * 0.85, mid=gn, high=gn * 1.15,
        ))

    return entries


# ── Public entry point ────────────────────────────────────────────────────────

def run_intrinsic_value(
    ticker: str,
    company_name: str,
    info: dict,
    income_stmts: list,
    balance_sheets: list,
    cash_flows: list,
    selected_methods: set[str],
) -> IntrinsicValueResult:
    """
    Run the selected intrinsic value sub-methods and combine into one result.

    selected_methods: subset of {"dcf_fcf", "ddm", "rim", "graham_number"}
    """
    price   = _current_price(info)
    skipped = []

    result = IntrinsicValueResult(
        ticker=ticker,
        company_name=company_name,
        current_price=price,
    )

    if "dcf_fcf" in selected_methods:
        try:
            result.dcf_fcf = _run_dcf_fcf(info, income_stmts, balance_sheets, cash_flows)
            if result.dcf_fcf is None:
                skipped.append("DCF FCF: insufficient / negative cash flow data")
        except Exception as e:
            skipped.append(f"DCF FCF: {e}")

    if "ddm" in selected_methods:
        try:
            result.ddm_gordon = _run_ddm_gordon(info, income_stmts, cash_flows)
            if result.ddm_gordon is None:
                skipped.append("DDM Gordon: company pays no dividend or r ≤ g")
        except Exception as e:
            skipped.append(f"DDM Gordon: {e}")

        try:
            result.ddm_multi = _run_ddm_multi(info, cash_flows)
            if result.ddm_multi is None:
                skipped.append("DDM Multi-Period: company pays no dividend")
        except Exception as e:
            skipped.append(f"DDM Multi-Period: {e}")

    if "rim" in selected_methods:
        try:
            result.rim = _run_rim(info, income_stmts, balance_sheets)
            if result.rim is None:
                skipped.append("RIM: missing equity or income data")
        except Exception as e:
            skipped.append(f"RIM: {e}")

    if "graham_number" in selected_methods:
        try:
            result.graham = _run_graham(info, income_stmts, balance_sheets)
            if result.graham is None:
                skipped.append("Graham Number: requires positive EPS and book value")
        except Exception as e:
            skipped.append(f"Graham Number: {e}")

    result.skipped = skipped
    result.football_field = _build_football_field(result)

    return result
