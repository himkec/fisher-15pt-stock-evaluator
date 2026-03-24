"""
Fundamental Analysis scoring engine.
10-phase framework: business understanding → statements → valuation →
profitability → growth → financial health → DCF → dividends →
earnings quality → overall scorecard.
"""

import statistics
from typing import Any

from scoring.fundamental_models import (
    FundamentalResult, SectionScore, MetricRow, DCFScenario,
)
from config.settings import SECTOR_FALLBACK_GROSS_MARGINS

# ── Constants ──────────────────────────────────────────────────────────────────

RISK_FREE_RATE = 0.045       # 10-yr Treasury approximate
EQUITY_RISK_PREMIUM = 0.055  # standard ERP
DEFAULT_TAX_RATE = 0.21      # US corporate
TERMINAL_GROWTH = 0.03       # perpetual terminal growth
DCF_YEARS = 5

# Sector fallback P/E medians
SECTOR_PE = {
    "Technology": 28.0,
    "Communication Services": 22.0,
    "Consumer Discretionary": 22.0,
    "Consumer Staples": 20.0,
    "Health Care": 20.0,
    "Financials": 13.0,
    "Industrials": 20.0,
    "Materials": 17.0,
    "Energy": 13.0,
    "Utilities": 17.0,
    "Real Estate": 30.0,
    "default": 20.0,
}

SECTION_WEIGHTS = {
    "valuation":       0.25,
    "profitability":   0.25,
    "growth":          0.25,
    "health":          0.15,
    "earnings_quality":0.10,
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        f = float(val)
        return default if (f != f) else f
    except (TypeError, ValueError):
        return default


def _cagr(start: float, end: float, years: int) -> float:
    if start <= 0 or years <= 0:
        return 0.0
    return (end / start) ** (1 / years) - 1


def _linear_slope(values: list) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2
    y_mean = statistics.mean(values)
    num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    den = sum((i - x_mean) ** 2 for i in range(n))
    return num / den if den else 0.0


def _score_10(val: float, thresholds: list) -> float:
    """
    thresholds: [(threshold, score), ...] checked in order.
    Returns score of first threshold where val >= threshold.
    """
    for threshold, score in thresholds:
        if val >= threshold:
            return score
    return thresholds[-1][1] if thresholds else 0.0


def _section_label(score: float) -> str:
    if score >= 8.0: return "Strong"
    if score >= 6.5: return "Good"
    if score >= 5.0: return "Fair"
    if score >= 3.5: return "Weak"
    return "Poor"


def _fmt_pct(v: float) -> str:
    return f"{v:.1%}"

def _fmt_x(v: float) -> str:
    return f"{v:.1f}x" if v else "N/A"

def _fmt_val(v: float) -> str:
    if not v:
        return "N/A"
    if abs(v) >= 1e9:
        return f"${v/1e9:.1f}B"
    if abs(v) >= 1e6:
        return f"${v/1e6:.0f}M"
    return f"{v:.2f}"


# ── Phase 3: Valuation ────────────────────────────────────────────────────────

def _score_valuation(info: dict, sector: str) -> SectionScore:
    pe      = _safe(info.get("trailingPE"))
    pe_fwd  = _safe(info.get("forwardPE"))
    peg     = _safe(info.get("pegRatio") or info.get("trailingPegRatio"))
    pb      = _safe(info.get("priceToBook"))
    ps      = _safe(info.get("priceToSalesTrailingTwelveMonths"))
    ev_ebitda = _safe(info.get("enterpriseToEbitda"))
    mktcap  = _safe(info.get("marketCap"))
    fcf     = _safe(info.get("freeCashflow"))
    pfcf    = (mktcap / fcf) if (fcf > 0 and mktcap > 0) else 0.0

    sector_pe = SECTOR_PE.get(sector, SECTOR_PE["default"])
    notes = []
    metrics = []

    # P/E score (25%)
    if pe > 0:
        ratio = pe / sector_pe
        pe_score = _score_10(ratio, [(0, 10), (0, 8), (0, 7), (0, 5), (0, 3)])
        # re-implement properly:
        if pe < sector_pe * 0.70:   pe_score = 10.0
        elif pe < sector_pe * 0.85: pe_score = 8.0
        elif pe < sector_pe * 1.00: pe_score = 7.0
        elif pe < sector_pe * 1.20: pe_score = 5.5
        elif pe < sector_pe * 1.50: pe_score = 3.5
        else:                        pe_score = 1.5
        metrics.append(MetricRow("P/E (Trailing)", _fmt_x(pe), pe_score,
                                 f"Sector median ~{sector_pe:.0f}x"))
    else:
        pe_score = 3.0
        metrics.append(MetricRow("P/E (Trailing)", "N/A (neg. earnings)", pe_score,
                                 "No trailing P/E — use EV/EBITDA"))

    if pe_fwd > 0:
        metrics.append(MetricRow("P/E (Forward)", _fmt_x(pe_fwd), 0.0,
                                 "Display only — not scored separately"))

    # PEG score (20%)
    if peg > 0:
        if peg < 1.0:   peg_score = 10.0
        elif peg < 1.5: peg_score = 7.5
        elif peg < 2.0: peg_score = 5.5
        elif peg < 3.0: peg_score = 3.0
        else:            peg_score = 1.0
        metrics.append(MetricRow("PEG Ratio", f"{peg:.2f}", peg_score,
                                 "< 1.0 = potentially undervalued (Lynch rule)"))
    else:
        peg_score = 5.0
        metrics.append(MetricRow("PEG Ratio", "N/A", peg_score, "Not available"))

    # P/B score (15%)
    if pb > 0:
        if pb < 1.5:   pb_score = 10.0
        elif pb < 3.0: pb_score = 7.5
        elif pb < 5.0: pb_score = 5.5
        elif pb < 8.0: pb_score = 3.0
        else:           pb_score = 1.0
        metrics.append(MetricRow("Price / Book", f"{pb:.1f}x", pb_score,
                                 "Less meaningful for intangible-heavy tech"))
    else:
        pb_score = 5.0
        metrics.append(MetricRow("Price / Book", "N/A", pb_score, "Not available"))

    # EV/EBITDA score (20%)
    if ev_ebitda > 0:
        if ev_ebitda < 10:   ev_score = 10.0
        elif ev_ebitda < 15: ev_score = 8.0
        elif ev_ebitda < 20: ev_score = 6.0
        elif ev_ebitda < 30: ev_score = 3.5
        else:                 ev_score = 1.0
        metrics.append(MetricRow("EV / EBITDA", _fmt_x(ev_ebitda), ev_score,
                                 "S&P 500 median ~14x; tech ~20–25x"))
    else:
        ev_score = 4.0
        metrics.append(MetricRow("EV / EBITDA", "N/A", ev_score, "Not available"))

    # P/FCF score (20%)
    if pfcf > 0:
        if pfcf < 15:   pfcf_score = 10.0
        elif pfcf < 22: pfcf_score = 8.0
        elif pfcf < 30: pfcf_score = 6.0
        elif pfcf < 50: pfcf_score = 3.0
        else:            pfcf_score = 1.0
        metrics.append(MetricRow("Price / FCF", _fmt_x(pfcf), pfcf_score,
                                 "P/FCF < P/E → strong earnings quality"))
    elif fcf <= 0:
        pfcf_score = 1.0
        metrics.append(MetricRow("Price / FCF", "Negative FCF", pfcf_score,
                                 "Negative FCF is a concern"))
    else:
        pfcf_score = 4.0
        metrics.append(MetricRow("Price / FCF", "N/A", pfcf_score, "Not available"))

    if ps > 0:
        metrics.append(MetricRow("Price / Sales", f"{ps:.1f}x", 0.0,
                                 "Useful for unprofitable companies — display only"))

    section_score = (
        pe_score   * 0.25 +
        peg_score  * 0.20 +
        pb_score   * 0.15 +
        ev_score   * 0.20 +
        pfcf_score * 0.20
    )

    if pe > 0 and pe > sector_pe * 1.5:
        notes.append(f"P/E of {pe:.0f}x is >50% above the sector median of {sector_pe:.0f}x.")
    if peg > 3.0:
        notes.append(f"PEG ratio of {peg:.1f} is elevated — growth may not justify the price.")

    return SectionScore(
        key="valuation", name="Valuation", score=round(section_score, 2),
        label=_section_label(section_score), weight=SECTION_WEIGHTS["valuation"],
        metrics=metrics, notes=notes,
    )


# ── Phase 4: Profitability ────────────────────────────────────────────────────

def _score_profitability(info: dict, income_stmts: list, balance_sheets: list, sector: str) -> SectionScore:
    gross_margin  = _safe(info.get("grossMargins"))
    op_margin     = _safe(info.get("operatingMargins"))
    net_margin    = _safe(info.get("profitMargins"))
    roe           = _safe(info.get("returnOnEquity"))
    roa           = _safe(info.get("returnOnAssets"))

    # ROIC = NOPAT / Invested Capital
    roic = 0.0
    if income_stmts and balance_sheets:
        ebit     = _safe(income_stmts[0].get("ebit"))
        nopat    = ebit * (1 - DEFAULT_TAX_RATE)
        equity   = _safe(balance_sheets[0].get("totalStockholdersEquity"))
        debt     = _safe(balance_sheets[0].get("totalDebt"))
        cash     = _safe(balance_sheets[0].get("cashAndCashEquivalents"))
        inv_cap  = equity + debt - cash
        if inv_cap > 0:
            roic = nopat / inv_cap

    sector_gross = SECTOR_FALLBACK_GROSS_MARGINS.get(sector, SECTOR_FALLBACK_GROSS_MARGINS["default"])
    metrics = []
    notes = []

    # Gross Margin (20%) — sector-relative
    gm_premium = gross_margin - sector_gross
    if gm_premium >= 0.15:   gm_score = 10.0
    elif gm_premium >= 0.07: gm_score = 8.0
    elif gm_premium >= 0.0:  gm_score = 6.5
    elif gm_premium >= -0.08:gm_score = 4.5
    else:                     gm_score = 2.0
    metrics.append(MetricRow("Gross Margin", _fmt_pct(gross_margin), gm_score,
                              f"Sector median ~{sector_gross:.0%}"))

    # Operating Margin (25%)
    if op_margin >= 0.25:   om_score = 10.0
    elif op_margin >= 0.15: om_score = 8.0
    elif op_margin >= 0.08: om_score = 6.0
    elif op_margin >= 0.03: om_score = 4.0
    elif op_margin >= 0.0:  om_score = 2.0
    else:                    om_score = 0.0
    metrics.append(MetricRow("Operating Margin", _fmt_pct(op_margin), om_score,
                              "> 20% = strong operating leverage"))

    # Net Margin (20%)
    if net_margin >= 0.20:   nm_score = 10.0
    elif net_margin >= 0.12: nm_score = 8.0
    elif net_margin >= 0.06: nm_score = 6.0
    elif net_margin >= 0.02: nm_score = 4.0
    elif net_margin >= 0.0:  nm_score = 2.0
    else:                     nm_score = 0.0
    metrics.append(MetricRow("Net Margin", _fmt_pct(net_margin), nm_score,
                              "Software/SaaS 20–35%; Retail 2–5%"))

    # ROE (20%)
    if roe >= 0.25:    roe_score = 10.0
    elif roe >= 0.20:  roe_score = 8.5
    elif roe >= 0.15:  roe_score = 7.0
    elif roe >= 0.08:  roe_score = 4.5
    elif roe >= 0.0:   roe_score = 2.0
    else:               roe_score = 0.0
    metrics.append(MetricRow("Return on Equity (ROE)", _fmt_pct(roe), roe_score,
                              "Buffett threshold: consistently > 15%"))

    # ROIC (15%)
    if roic >= 0.20:    roic_score = 10.0
    elif roic >= 0.15:  roic_score = 8.0
    elif roic >= 0.10:  roic_score = 6.0
    elif roic >= 0.05:  roic_score = 4.0
    elif roic >= 0.0:   roic_score = 2.0
    else:                roic_score = 0.0
    metrics.append(MetricRow("Return on Invested Capital (ROIC)", _fmt_pct(roic), roic_score,
                              "ROIC > WACC = value creation"))

    if roa:
        metrics.append(MetricRow("Return on Assets (ROA)", _fmt_pct(roa), 0.0, "Display only"))

    section_score = (
        gm_score   * 0.20 +
        om_score   * 0.25 +
        nm_score   * 0.20 +
        roe_score  * 0.20 +
        roic_score * 0.15
    )

    if op_margin < 0:
        notes.append("Negative operating margin — company is not yet profitable at the operating level.")
    if roe > 0.50 and (balance_sheets and _safe(balance_sheets[0].get("totalDebt")) > 0):
        notes.append("Very high ROE may be inflated by leverage — check D/E ratio.")
    if roic > 0.15 and roic > roe * 0.8:
        notes.append(f"ROIC of {roic:.1%} significantly above cost of capital — strong value creation.")

    return SectionScore(
        key="profitability", name="Profitability & Returns", score=round(section_score, 2),
        label=_section_label(section_score), weight=SECTION_WEIGHTS["profitability"],
        metrics=metrics, notes=notes,
    )


# ── Phase 5: Growth ───────────────────────────────────────────────────────────

def _score_growth(info: dict, income_stmts: list, cash_flows: list) -> SectionScore:
    metrics = []
    notes = []

    # Revenue CAGR (40%)
    revenues = [s.get("revenue", 0) for s in income_stmts if s.get("revenue", 0) > 0]
    rev_cagr = 0.0
    if len(revenues) >= 2:
        years = min(len(revenues) - 1, 5)
        rev_cagr = _cagr(revenues[years] if years < len(revenues) else revenues[-1], revenues[0], years)

    if rev_cagr >= 0.20:    rc_score = 10.0
    elif rev_cagr >= 0.15:  rc_score = 8.5
    elif rev_cagr >= 0.10:  rc_score = 7.0
    elif rev_cagr >= 0.07:  rc_score = 5.5
    elif rev_cagr >= 0.03:  rc_score = 3.5
    elif rev_cagr >= 0.0:   rc_score = 1.5
    else:                    rc_score = 0.0
    metrics.append(MetricRow("Revenue CAGR (5yr)", _fmt_pct(rev_cagr), rc_score,
                              "> 15%/yr = strong compounding"))

    # EPS CAGR (35%) — derive from net income / shares
    net_incomes = [s.get("netIncome", 0) for s in income_stmts if s.get("netIncome")]
    eps_cagr = 0.0
    if len(net_incomes) >= 2:
        # Use net income as proxy for EPS CAGR (same shares denominator)
        ni_start = net_incomes[min(4, len(net_incomes)-1)]
        ni_end   = net_incomes[0]
        if ni_start > 0 and ni_end > 0:
            years = min(len(net_incomes) - 1, 5)
            eps_cagr = _cagr(ni_start, ni_end, years)

    if eps_cagr >= 0.20:    ec_score = 10.0
    elif eps_cagr >= 0.15:  ec_score = 8.5
    elif eps_cagr >= 0.10:  ec_score = 7.0
    elif eps_cagr >= 0.05:  ec_score = 5.0
    elif eps_cagr >= 0.0:   ec_score = 2.5
    else:                    ec_score = 0.0
    metrics.append(MetricRow("EPS / Net Income CAGR (5yr)", _fmt_pct(eps_cagr), ec_score,
                              "> 20%/yr = exceptional; watch revenue vs EPS gap"))

    # FCF Growth CAGR (25%)
    fcfs = []
    for cf in cash_flows:
        fcf = cf.get("freeCashFlow", 0) or 0
        if fcf == 0:
            ocf   = _safe(cf.get("operatingCashFlow"))
            capex = abs(_safe(cf.get("capitalExpenditure")))
            fcf   = ocf - capex
        if fcf > 0:
            fcfs.append(fcf)

    fcf_cagr = 0.0
    if len(fcfs) >= 2:
        years = min(len(fcfs) - 1, 5)
        fcf_cagr = _cagr(fcfs[min(years, len(fcfs)-1)], fcfs[0], years)

    if fcf_cagr >= 0.20:    fc_score = 10.0
    elif fcf_cagr >= 0.15:  fc_score = 8.0
    elif fcf_cagr >= 0.10:  fc_score = 6.5
    elif fcf_cagr >= 0.05:  fc_score = 4.5
    elif fcf_cagr >= 0.0:   fc_score = 2.0
    else:                    fc_score = 0.0
    metrics.append(MetricRow("FCF CAGR (5yr)", _fmt_pct(fcf_cagr), fc_score,
                              "FCF is manipulation-resistant — the gold standard growth metric"))

    section_score = rc_score * 0.40 + ec_score * 0.35 + fc_score * 0.25

    if rev_cagr > 0.10 and eps_cagr < rev_cagr * 0.5:
        notes.append("Revenue growing faster than earnings — watch for margin compression or dilution.")
    if rev_cagr < 0:
        notes.append("Negative revenue growth — verify this is not a structural decline.")
    if fcf_cagr > 0.20:
        notes.append(f"FCF compounding at {fcf_cagr:.0%}/yr — among the most powerful compounding machines.")

    return SectionScore(
        key="growth", name="Growth", score=round(section_score, 2),
        label=_section_label(section_score), weight=SECTION_WEIGHTS["growth"],
        metrics=metrics, notes=notes,
    )


# ── Phase 6: Financial Health ──────────────────────────────────────────────────

def _score_health(info: dict, income_stmts: list, balance_sheets: list, extended: dict) -> SectionScore:
    current_ratio  = _safe(info.get("currentRatio"))
    quick_ratio    = _safe(info.get("quickRatio"))
    de_ratio       = _safe(info.get("debtToEquity"))   # yfinance reports as percentage sometimes
    # Normalise: yfinance can return 58.5 meaning 0.585
    if de_ratio > 10:
        de_ratio /= 100.0

    metrics = []
    notes = []

    # Current Ratio (20%)
    if current_ratio >= 2.5:   cr_score = 10.0
    elif current_ratio >= 1.5: cr_score = 8.0
    elif current_ratio >= 1.0: cr_score = 5.5
    elif current_ratio >= 0.7: cr_score = 3.0
    elif current_ratio > 0:    cr_score = 1.0
    else:                       cr_score = 4.0  # unavailable → neutral
    metrics.append(MetricRow("Current Ratio", f"{current_ratio:.2f}x" if current_ratio else "N/A",
                              cr_score, "> 1.5 = healthy; < 1.0 = red flag"))

    # Quick Ratio (15%)
    if quick_ratio >= 1.5:   qr_score = 10.0
    elif quick_ratio >= 1.0: qr_score = 8.0
    elif quick_ratio >= 0.7: qr_score = 5.5
    elif quick_ratio > 0:    qr_score = 2.5
    else:                     qr_score = 4.0
    metrics.append(MetricRow("Quick Ratio", f"{quick_ratio:.2f}x" if quick_ratio else "N/A",
                              qr_score, "Excludes inventory — more conservative"))

    # D/E Ratio (25%)
    if de_ratio <= 0.30:   de_score = 10.0
    elif de_ratio <= 0.60: de_score = 8.0
    elif de_ratio <= 1.00: de_score = 6.0
    elif de_ratio <= 2.00: de_score = 3.5
    elif de_ratio > 2.00:  de_score = 1.0
    else:                   de_score = 5.0   # zero debt
    metrics.append(MetricRow("Debt / Equity", f"{de_ratio:.2f}x" if de_ratio else "0x (net cash)",
                              de_score, "Context is critical — utilities naturally higher"))

    # Interest Coverage (30%)
    int_coverage = 0.0
    ebit = _safe(income_stmts[0].get("ebit")) if income_stmts else 0.0
    int_exp = _safe(extended.get("interestExpense")) if extended else 0.0
    if int_exp > 0 and ebit > 0:
        int_coverage = ebit / int_exp
    elif int_exp == 0:
        int_coverage = 99.0   # no interest expense = excellent

    if int_coverage >= 99:   ic_score = 10.0
    elif int_coverage >= 10: ic_score = 9.0
    elif int_coverage >= 5:  ic_score = 7.5
    elif int_coverage >= 3:  ic_score = 5.5
    elif int_coverage >= 1.5:ic_score = 3.0
    elif int_coverage > 0:   ic_score = 1.0
    else:                     ic_score = 0.0
    ic_display = "No debt" if int_coverage >= 99 else f"{int_coverage:.1f}x"
    metrics.append(MetricRow("Interest Coverage", ic_display, ic_score,
                              "> 5x safe; < 1.5x dangerous"))

    # Altman Z-Score (10%)
    altman_z = 0.0
    z_label = "N/A"
    cur_assets = _safe(extended.get("currentAssets")) if extended else 0.0
    cur_liabs  = _safe(extended.get("currentLiabilities")) if extended else 0.0
    ret_earn   = _safe(extended.get("retainedEarnings")) if extended else 0.0
    if balance_sheets and income_stmts:
        total_assets   = _safe(balance_sheets[0].get("totalAssets"))
        total_liabs    = _safe(balance_sheets[0].get("totalLiabilities"))
        revenue        = _safe(income_stmts[0].get("revenue"))
        mktcap         = _safe(info.get("marketCap"))

        if total_assets > 0:
            x1 = (cur_assets - cur_liabs) / total_assets
            x2 = ret_earn / total_assets
            x3 = ebit / total_assets
            x4 = mktcap / total_liabs if total_liabs > 0 else 0.0
            x5 = revenue / total_assets
            altman_z = 1.2*x1 + 1.4*x2 + 3.3*x3 + 0.6*x4 + 1.0*x5
            if altman_z > 2.99:   z_label = "Safe Zone"
            elif altman_z > 1.81: z_label = "Grey Zone"
            else:                  z_label = "Distress Zone"

    if altman_z >= 3.0:    az_score = 10.0
    elif altman_z >= 2.5:  az_score = 8.0
    elif altman_z >= 1.81: az_score = 5.0
    elif altman_z >= 1.0:  az_score = 2.0
    elif altman_z > 0:     az_score = 0.0
    else:                   az_score = 5.0   # unavailable → neutral
    z_display = f"{altman_z:.2f} ({z_label})" if altman_z else "N/A"
    metrics.append(MetricRow("Altman Z-Score", z_display, az_score,
                              "> 2.99 safe; < 1.81 distress"))

    section_score = (
        cr_score * 0.20 +
        qr_score * 0.15 +
        de_score * 0.25 +
        ic_score * 0.30 +
        az_score * 0.10
    )

    if de_ratio > 2.0:
        notes.append(f"High D/E of {de_ratio:.1f}x — elevated financial risk; check interest coverage.")
    if int_coverage < 2 and int_coverage > 0:
        notes.append(f"Interest coverage of {int_coverage:.1f}x is dangerously low — risk of distress in a downturn.")
    if altman_z > 0 and altman_z < 1.81:
        notes.append(f"Altman Z-Score of {altman_z:.2f} is in the distress zone — bankruptcy risk elevated.")

    return SectionScore(
        key="health", name="Financial Health", score=round(section_score, 2),
        label=_section_label(section_score), weight=SECTION_WEIGHTS["health"],
        metrics=metrics, notes=notes,
    )


# ── Phase 9: Earnings Quality ──────────────────────────────────────────────────

def _score_earnings_quality(income_stmts: list, cash_flows: list, balance_sheets: list) -> SectionScore:
    metrics = []
    notes = []

    # OCF / Net Income (50%) — over last 3 years average
    ocf_ni_ratios = []
    for i, stmt in enumerate(income_stmts[:4]):
        ni = _safe(stmt.get("netIncome"))
        ocf = _safe(cash_flows[i].get("operatingCashFlow")) if i < len(cash_flows) else 0.0
        if ni > 0 and ocf != 0:
            ocf_ni_ratios.append(ocf / ni)

    avg_ocf_ni = statistics.mean(ocf_ni_ratios) if ocf_ni_ratios else 0.0
    if avg_ocf_ni >= 1.2:    ocf_score = 10.0
    elif avg_ocf_ni >= 1.0:  ocf_score = 8.5
    elif avg_ocf_ni >= 0.80: ocf_score = 6.5
    elif avg_ocf_ni >= 0.60: ocf_score = 4.0
    elif avg_ocf_ni >= 0.40: ocf_score = 2.0
    else:                     ocf_score = 0.0
    metrics.append(MetricRow("OCF / Net Income (avg 4yr)", f"{avg_ocf_ni:.2f}x" if avg_ocf_ni else "N/A",
                              ocf_score, "> 1.0 = earnings backed by real cash"))

    # Accruals Ratio (30%) = (NI - OCF) / avg Total Assets
    accruals_score = 5.0  # default neutral
    accruals_ratio = 0.0
    if income_stmts and cash_flows and balance_sheets:
        ni_latest  = _safe(income_stmts[0].get("netIncome"))
        ocf_latest = _safe(cash_flows[0].get("operatingCashFlow"))
        ta_now     = _safe(balance_sheets[0].get("totalAssets"))
        ta_prev    = _safe(balance_sheets[1].get("totalAssets")) if len(balance_sheets) > 1 else ta_now
        avg_ta     = (ta_now + ta_prev) / 2 if ta_now > 0 else 0.0
        if avg_ta > 0:
            accruals_ratio = (ni_latest - ocf_latest) / avg_ta
            if accruals_ratio <= 0:       accruals_score = 10.0
            elif accruals_ratio <= 0.02:  accruals_score = 8.0
            elif accruals_ratio <= 0.05:  accruals_score = 5.5
            elif accruals_ratio <= 0.10:  accruals_score = 3.0
            else:                          accruals_score = 1.0
    metrics.append(MetricRow("Accruals Ratio", f"{accruals_ratio:.3f}" if accruals_ratio else "N/A",
                              accruals_score, "Near 0 = earnings backed by cash; high positive = concern"))

    # OCF Margin consistency (20%) — avg OCF / Revenue
    ocf_margins = []
    for i, cf in enumerate(cash_flows[:4]):
        ocf = _safe(cf.get("operatingCashFlow"))
        rev = _safe(income_stmts[i].get("revenue")) if i < len(income_stmts) else 0.0
        if rev > 0 and ocf > 0:
            ocf_margins.append(ocf / rev)
    avg_ocf_margin = statistics.mean(ocf_margins) if ocf_margins else 0.0
    if avg_ocf_margin >= 0.20:   cm_score = 10.0
    elif avg_ocf_margin >= 0.15: cm_score = 8.0
    elif avg_ocf_margin >= 0.10: cm_score = 6.0
    elif avg_ocf_margin >= 0.05: cm_score = 4.0
    elif avg_ocf_margin > 0:     cm_score = 2.0
    else:                         cm_score = 0.0
    metrics.append(MetricRow("OCF Margin (avg 4yr)", f"{avg_ocf_margin:.1%}" if avg_ocf_margin else "N/A",
                              cm_score, "Consistent OCF margin = predictable cash generation"))

    section_score = ocf_score * 0.50 + accruals_score * 0.30 + cm_score * 0.20

    if avg_ocf_ni < 0.7 and avg_ocf_ni > 0:
        notes.append(f"OCF covers only {avg_ocf_ni:.0%} of net income — earnings quality concern.")
    if accruals_ratio > 0.08:
        notes.append("High accruals ratio suggests earnings may not be fully backed by cash.")

    return SectionScore(
        key="earnings_quality", name="Earnings Quality", score=round(section_score, 2),
        label=_section_label(section_score), weight=SECTION_WEIGHTS["earnings_quality"],
        metrics=metrics, notes=notes,
    )


# ── Phase 7: DCF Model ────────────────────────────────────────────────────────

def _run_dcf(
    info: dict,
    cash_flows: list,
    income_stmts: list,
) -> tuple:
    """Returns (scenarios, wacc, terminal_growth, base_fcf_growth)."""

    # Latest FCF
    base_fcf = 0.0
    for cf in cash_flows[:2]:
        fcf = _safe(cf.get("freeCashFlow"))
        if fcf == 0:
            ocf   = _safe(cf.get("operatingCashFlow"))
            capex = abs(_safe(cf.get("capitalExpenditure")))
            fcf   = ocf - capex
        if fcf > 0:
            base_fcf = fcf
            break
    if base_fcf <= 0:
        return [], 0.09, TERMINAL_GROWTH, 0.0

    # Historical FCF CAGR → base growth rate
    fcfs = []
    for cf in cash_flows:
        f = _safe(cf.get("freeCashFlow"))
        if f == 0:
            f = _safe(cf.get("operatingCashFlow")) - abs(_safe(cf.get("capitalExpenditure")))
        if f > 0:
            fcfs.append(f)

    if len(fcfs) >= 2:
        yrs = min(len(fcfs) - 1, 5)
        historical_cagr = _cagr(fcfs[min(yrs, len(fcfs)-1)], fcfs[0], yrs)
    else:
        # Fall back to revenue CAGR
        revenues = [s.get("revenue", 0) for s in income_stmts if s.get("revenue", 0) > 0]
        if len(revenues) >= 2:
            yrs = min(len(revenues)-1, 5)
            historical_cagr = _cagr(revenues[min(yrs, len(revenues)-1)], revenues[0], yrs)
        else:
            historical_cagr = 0.08

    # Cap base growth: max 30%, min 0%
    base_growth = max(0.0, min(0.30, historical_cagr))

    # WACC
    beta = _safe(info.get("beta"), 1.0)
    beta = max(0.5, min(2.5, beta))
    cost_equity = RISK_FREE_RATE + beta * EQUITY_RISK_PREMIUM

    total_debt = _safe(info.get("totalDebt"))
    total_cash = _safe(info.get("totalCash"))
    mktcap     = _safe(info.get("marketCap"))
    net_debt   = total_debt - total_cash
    total_cap  = mktcap + max(0, net_debt)

    equity_weight = mktcap / total_cap if total_cap > 0 else 1.0
    debt_weight   = 1 - equity_weight
    cost_debt     = 0.055    # default 5.5%

    wacc = equity_weight * cost_equity + debt_weight * cost_debt * (1 - DEFAULT_TAX_RATE)
    wacc = max(0.06, min(0.20, wacc))   # clamp to reasonable range

    shares = _safe(info.get("sharesOutstanding"))
    price  = _safe(info.get("currentPrice") or info.get("regularMarketPrice"))

    def _dcf_value(growth: float) -> float:
        pv_fcfs = 0.0
        fcf = base_fcf
        for t in range(1, DCF_YEARS + 1):
            fcf *= (1 + growth)
            pv_fcfs += fcf / (1 + wacc) ** t
        terminal_fcf = fcf * (1 + TERMINAL_GROWTH)
        terminal_val = terminal_fcf / (wacc - TERMINAL_GROWTH)
        pv_terminal  = terminal_val / (1 + wacc) ** DCF_YEARS
        total_equity = pv_fcfs + pv_terminal - max(0, net_debt)
        return total_equity / shares if shares > 0 else 0.0

    scenarios = []
    for name, g in [("Bear", base_growth * 0.7), ("Base", base_growth), ("Bull", base_growth * 1.3)]:
        iv = _dcf_value(g)
        mos = (iv - price) / iv if iv > 0 else -1.0
        scenarios.append(DCFScenario(name=name, fcf_growth=g, intrinsic_value=iv, margin_of_safety=mos))

    return scenarios, wacc, TERMINAL_GROWTH, base_growth


# ── Phase 8: Dividend ─────────────────────────────────────────────────────────

def _score_dividend(info: dict, cash_flows: list) -> dict | None:
    div_yield = _safe(info.get("dividendYield"))
    div_rate  = _safe(info.get("dividendRate"))
    payout    = _safe(info.get("payoutRatio"))

    if div_yield <= 0 and div_rate <= 0:
        return None   # no dividends

    # FCF payout ratio
    fcf = _safe(info.get("freeCashflow"))
    dividends_paid = 0.0
    if cash_flows:
        dividends_paid = abs(_safe(cash_flows[0].get("dividendsPaid",
                             cash_flows[0].get("dividends_paid", 0))))
    fcf_payout = dividends_paid / fcf if fcf > 0 and dividends_paid > 0 else None

    return {
        "dividend_yield":   div_yield,
        "annual_dividend":  div_rate,
        "payout_ratio":     payout,
        "fcf_payout_ratio": fcf_payout,
        "notes": [],
    }


# ── Phase 10: Composite Scorecard ─────────────────────────────────────────────

def _composite_verdict(score: float) -> tuple:
    if score >= 7.5:
        return "BUY with Conviction", "BUY"
    elif score >= 5.5:
        return "HOLD / Watch for Better Entry", "HOLD"
    else:
        return "AVOID", "AVOID"


# ── Public entry point ────────────────────────────────────────────────────────

def run_fundamental(
    ticker: str,
    company_name: str,
    sector: str,
    info: dict,
    income_stmts: list,
    balance_sheets: list,
    cash_flows: list,
    extended: dict,
) -> FundamentalResult:
    """
    Run the full fundamental analysis.
    `extended` = dict from fmp_client.get_balance_sheet_extended().
    """
    current_price = _safe(info.get("currentPrice") or info.get("regularMarketPrice"))

    val_section  = _score_valuation(info, sector)
    prof_section = _score_profitability(info, income_stmts, balance_sheets, sector)
    grow_section = _score_growth(info, income_stmts, cash_flows)
    hlth_section = _score_health(info, income_stmts, balance_sheets, extended)
    eq_section   = _score_earnings_quality(income_stmts, cash_flows, balance_sheets)

    sections = {
        "valuation":        val_section,
        "profitability":    prof_section,
        "growth":           grow_section,
        "health":           hlth_section,
        "earnings_quality": eq_section,
    }

    composite = sum(s.score * s.weight for s in sections.values())
    composite_label, recommendation = _composite_verdict(composite)

    dcf_scenarios, wacc, terminal_g, _ = _run_dcf(info, cash_flows, income_stmts)
    dividend_metrics = _score_dividend(info, cash_flows)

    # Red flags and highlights
    red_flags = []
    highlights = []

    for s in sections.values():
        red_flags.extend(n for n in s.notes if any(
            word in n.lower() for word in ["concern", "risk", "danger", "negative", "low", "high d/e", "distress"]))
        highlights.extend(n for n in s.notes if any(
            word in n.lower() for word in ["strong", "exceptional", "gold", "compounding", "value creation"]))

    base_dcf = next((d for d in dcf_scenarios if d.name == "Base"), None)
    if base_dcf and base_dcf.margin_of_safety > 0.20:
        highlights.append(f"DCF base case implies {base_dcf.margin_of_safety:.0%} margin of safety at current price.")
    elif base_dcf and base_dcf.margin_of_safety < -0.20:
        red_flags.append(f"DCF base case implies stock is {abs(base_dcf.margin_of_safety):.0%} overvalued vs intrinsic value.")

    return FundamentalResult(
        ticker=ticker,
        company_name=company_name,
        sector=sector,
        current_price=current_price,
        sections=sections,
        composite_score=round(composite, 2),
        composite_label=composite_label,
        recommendation=recommendation,
        dcf_scenarios=dcf_scenarios,
        wacc=wacc,
        terminal_growth=terminal_g,
        dividend_metrics=dividend_metrics or {},
        red_flags=red_flags,
        highlights=highlights,
    )
