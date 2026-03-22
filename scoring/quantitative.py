"""
Rule-based quantitative scoring for Fisher Points 1, 5, 6, 10, 13.
Pure functions — no I/O. Takes pre-fetched FMP data dicts.
"""

import statistics
from typing import Any

from config.settings import (
    REVENUE_CAGR_STRONG,
    REVENUE_CAGR_AVERAGE,
    MARGIN_PREMIUM_STRONG,
    MARGIN_PREMIUM_AVERAGE,
    MARGIN_TREND_STRONG,
    MARGIN_TREND_AVERAGE,
    SGNA_TREND_STRONG,
    SGNA_TREND_AVERAGE,
    DILUTION_STRONG,
    DILUTION_AVERAGE,
    SECTOR_FALLBACK_GROSS_MARGINS,
    SCORE_MAP,
)
from scoring.models import PointResult


def _score(val: str) -> int:
    return SCORE_MAP.get(val, 0)


def _linear_slope(values: list[float]) -> float:
    """Simple OLS slope for a list of values (oldest→newest)."""
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2
    y_mean = statistics.mean(values)
    num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    den = sum((i - x_mean) ** 2 for i in range(n))
    return num / den if den != 0 else 0.0


def _cagr(start: float, end: float, years: int) -> float:
    if start <= 0 or years <= 0:
        return 0.0
    return (end / start) ** (1 / years) - 1


# ── Point 1 — Growth Potential ────────────────────────────────────────────────

def score_point_1(income_stmts: list[dict]) -> PointResult:
    """5-year revenue CAGR vs thresholds."""
    revenues = [s.get("revenue", 0) for s in income_stmts if s.get("revenue")]
    revenues = [r for r in revenues if r and r > 0]

    if len(revenues) < 2:
        return PointResult(
            point_number=1, label="Growth Potential",
            score="average", numeric=1,
            rationale="Insufficient revenue history to calculate CAGR. Defaulting to average.",
            data_used={"revenues_found": len(revenues)},
        )

    # income_stmts are newest-first; cap window at 5 years
    years = min(len(revenues) - 1, 5)
    cagr = _cagr(revenues[years], revenues[0], years)  # revenues[years] = exactly `years` ago

    if cagr >= REVENUE_CAGR_STRONG:
        score = "strong"
        rationale = f"Revenue CAGR of {cagr:.1%} over {years}yr exceeds the 15% threshold — strong sales growth runway."
    elif cagr >= REVENUE_CAGR_AVERAGE:
        score = "average"
        rationale = f"Revenue CAGR of {cagr:.1%} over {years}yr is solid but below the 15% high-growth threshold."
    else:
        score = "weak"
        rationale = f"Revenue CAGR of {cagr:.1%} over {years}yr is below the 7% minimum — growth potential is limited."

    return PointResult(
        point_number=1, label="Growth Potential",
        score=score, numeric=_score(score),
        rationale=rationale,
        data_used={"revenue_cagr": round(cagr, 4), "years": years,
                   "start_revenue": revenues[years], "latest_revenue": revenues[0]},
    )


# ── Point 5 — Profit Margin Level ─────────────────────────────────────────────

def score_point_5(ratios: list[dict], peers_ratios: list[dict], sector: str) -> PointResult:
    """Gross margin vs sector peers or fallback median."""
    if not ratios:
        return PointResult(
            point_number=5, label="Profit Margin Level",
            score="average", numeric=1,
            rationale="No ratio data available. Defaulting to average.",
            data_used={},
        )

    gross_margin = ratios[0].get("grossProfitMargin", 0) or 0

    # Peer median
    peer_margins = [p.get("grossProfitMargin", 0) for p in peers_ratios if p.get("grossProfitMargin")]
    if peer_margins:
        sector_median = statistics.median(peer_margins)
        source = "peer_median"
    else:
        sector_median = SECTOR_FALLBACK_GROSS_MARGINS.get(sector, SECTOR_FALLBACK_GROSS_MARGINS["default"])
        source = "sector_fallback"

    premium = gross_margin - sector_median

    if premium >= MARGIN_PREMIUM_STRONG:
        score = "strong"
        rationale = f"Gross margin {gross_margin:.1%} is {premium:.1%}pp above sector median — meaningful pricing power."
    elif premium >= MARGIN_PREMIUM_AVERAGE:
        score = "average"
        rationale = f"Gross margin {gross_margin:.1%} is near sector median ({sector_median:.1%}) — adequate but not exceptional."
    else:
        score = "weak"
        rationale = f"Gross margin {gross_margin:.1%} is {abs(premium):.1%}pp below sector median ({sector_median:.1%}) — margin pressure evident."

    return PointResult(
        point_number=5, label="Profit Margin Level",
        score=score, numeric=_score(score),
        rationale=rationale,
        data_used={"gross_margin": round(gross_margin, 4), "sector_median": round(sector_median, 4),
                   "premium": round(premium, 4), "comparison_source": source},
    )


# ── Point 6 — Margin Trend ────────────────────────────────────────────────────

def score_point_6(ratios: list[dict]) -> PointResult:
    """5-year operating margin trend (linear slope in pp/yr)."""
    op_margins = [r.get("operatingProfitMargin", 0) for r in reversed(ratios) if r.get("operatingProfitMargin") is not None]
    op_margins = [m for m in op_margins if m is not None]

    if len(op_margins) < 2:
        return PointResult(
            point_number=6, label="Margin Stability & Improvement",
            score="average", numeric=1,
            rationale="Insufficient margin history for trend analysis.",
            data_used={},
        )

    slope = _linear_slope(op_margins)  # pp change per year

    if slope >= MARGIN_TREND_STRONG:
        score = "strong"
        rationale = f"Operating margin improving at {slope:+.2f}pp/yr over {len(op_margins)} years — disciplined efficiency gains."
    elif slope >= MARGIN_TREND_AVERAGE:
        score = "average"
        rationale = f"Operating margin broadly stable ({slope:+.2f}pp/yr trend) — holding ground but not expanding."
    else:
        score = "weak"
        rationale = f"Operating margin deteriorating at {slope:+.2f}pp/yr over {len(op_margins)} years — cost or pricing pressure."

    return PointResult(
        point_number=6, label="Margin Stability & Improvement",
        score=score, numeric=_score(score),
        rationale=rationale,
        data_used={"margin_slope_per_yr": round(slope, 4), "margins_oldest_to_newest": [round(m, 4) for m in op_margins]},
    )


# ── Point 10 — Cost Controls ──────────────────────────────────────────────────

def score_point_10(income_stmts: list[dict]) -> PointResult:
    """SG&A as % of revenue trend (falling = good cost discipline)."""
    ratios_over_time = []
    for stmt in reversed(income_stmts):
        rev = stmt.get("revenue", 0) or 0
        sgna = stmt.get("sellingGeneralAndAdministrativeExpenses", 0) or 0
        if rev > 0 and sgna > 0:
            ratios_over_time.append(sgna / rev)

    if len(ratios_over_time) < 2:
        return PointResult(
            point_number=10, label="Cost Analysis & Controls",
            score="average", numeric=1,
            rationale="Insufficient SG&A data for trend analysis.",
            data_used={},
        )

    slope = _linear_slope(ratios_over_time)

    if slope <= SGNA_TREND_STRONG:
        score = "strong"
        rationale = f"SG&A/Revenue falling at {slope:+.2%}/yr — clear cost discipline and operating leverage."
    elif slope <= SGNA_TREND_AVERAGE:
        score = "average"
        rationale = f"SG&A/Revenue broadly stable ({slope:+.2%}/yr) — cost structure under control but not improving."
    else:
        score = "weak"
        rationale = f"SG&A/Revenue rising at {slope:+.2%}/yr — cost creep without commensurate revenue growth."

    return PointResult(
        point_number=10, label="Cost Analysis & Controls",
        score=score, numeric=_score(score),
        rationale=rationale,
        data_used={"sgna_rev_slope_per_yr": round(slope, 4),
                   "sgna_rev_oldest_to_newest": [round(r, 4) for r in ratios_over_time]},
    )


# ── Point 13 — Equity Financing Needs ────────────────────────────────────────

def score_point_13(cash_flows: list[dict], balance_sheets: list[dict]) -> PointResult:
    """
    Two signals combined:
    1. FCF self-funding: is operating CF > CapEx consistently?
    2. Share dilution CAGR over available history.
    """
    # FCF self-funding
    fcf_positive_count = 0
    for cf in cash_flows:
        op_cf = cf.get("operatingCashFlow", 0) or 0
        capex = abs(cf.get("capitalExpenditure", 0) or 0)
        if op_cf > capex:
            fcf_positive_count += 1

    fcf_self_funded = fcf_positive_count >= max(1, len(cash_flows) * 0.6)

    # Share dilution CAGR
    shares = [b.get("commonStock", 0) or b.get("totalStockholdersEquity", 0)
              for b in balance_sheets if b.get("commonStock") or b.get("totalStockholdersEquity")]
    # Try shares outstanding from cash flow (more reliable)
    shares_outstanding = [b.get("commonStockSharesOutstanding", 0) for b in balance_sheets
                          if b.get("commonStockSharesOutstanding")]

    dilution_cagr = 0.0
    if len(shares_outstanding) >= 2:
        years = len(shares_outstanding) - 1
        dilution_cagr = _cagr(shares_outstanding[-1], shares_outstanding[0], years)

    # Scoring
    if fcf_self_funded and dilution_cagr <= DILUTION_STRONG:
        score = "strong"
        rationale = (f"FCF self-funded in {fcf_positive_count}/{len(cash_flows)} years; "
                     f"share count declining at {dilution_cagr:.1%}/yr (buybacks). Minimal dilution risk.")
    elif fcf_self_funded and dilution_cagr <= DILUTION_AVERAGE:
        score = "average"
        rationale = (f"FCF self-funded in {fcf_positive_count}/{len(cash_flows)} years; "
                     f"modest dilution of {dilution_cagr:.1%}/yr. Growth benefits largely preserved for shareholders.")
    else:
        score = "weak"
        rationale = (f"FCF self-funded in only {fcf_positive_count}/{len(cash_flows)} years or "
                     f"dilution of {dilution_cagr:.1%}/yr risks cancelling shareholder growth benefit.")

    return PointResult(
        point_number=13, label="Equity Financing Needs",
        score=score, numeric=_score(score),
        rationale=rationale,
        data_used={"fcf_self_funded_years": fcf_positive_count, "total_years": len(cash_flows),
                   "dilution_cagr": round(dilution_cagr, 4)},
    )
