"""
Quality at a Fair Price (QAFP) scoring engine.
Computes Quality Score (0-100) and Valuation Score (0-100)
from yfinance data and derives a BUY / WATCHLIST / AVOID recommendation.
"""

import statistics
from typing import Any

from scoring.qafp_models import QAFPResult, SubScore

# ── Configurable thresholds ────────────────────────────────────────────────────

THRESHOLDS = {
    # Profitability
    "roe_high": 0.20,
    "roe_avg":  0.12,
    "roe_low":  0.08,
    "op_margin_high": 0.20,
    "op_margin_avg":  0.10,

    # Cash generation
    "fcf_margin_high": 0.15,
    "fcf_margin_avg":  0.05,
    "fcf_cagr_high":   0.10,
    "fcf_cagr_avg":    0.03,

    # Balance sheet
    "de_safe":   0.5,
    "de_ok":     1.0,
    "de_risky":  2.0,
    "nd_ebitda_safe":  2.0,
    "nd_ebitda_ok":    3.5,

    # Growth
    "rev_cagr_high": 0.12,
    "rev_cagr_avg":  0.05,
    "eps_cagr_high": 0.12,
    "eps_cagr_avg":  0.05,

    # Valuation
    "pe_cheap":      15.0,
    "pe_fair_hi":    25.0,
    "peg_fair":       1.5,
    "fcf_yield_high": 0.06,
    "fcf_yield_fair": 0.03,

    # Decision
    "quality_buy":       70.0,
    "quality_watchlist": 50.0,
    "valuation_buy":     60.0,
    "required_return":   0.09,
}


def _safe(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        f = float(val)
        return default if (f != f) else f   # NaN check
    except (TypeError, ValueError):
        return default


def _label_quality(score: float) -> str:
    if score >= 75:  return "High"
    if score >= 55:  return "Above Average"
    if score >= 35:  return "Average"
    return "Low"


def _label_valuation(score: float) -> str:
    if score >= 70:  return "Cheap"
    if score >= 40:  return "Fair"
    return "Expensive"


def _cagr(start: float, end: float, years: int) -> float:
    if start <= 0 or years <= 0:
        return 0.0
    return (end / start) ** (1 / years) - 1


def _linear_slope(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2
    y_mean = statistics.mean(values)
    num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    den = sum((i - x_mean) ** 2 for i in range(n))
    return num / den if den else 0.0


# ── Sub-score: Profitability ──────────────────────────────────────────────────

def _score_profitability(info: dict, income_stmts: list[dict]) -> SubScore:
    roe      = _safe(info.get("returnOnEquity"))
    op_margin = _safe(info.get("operatingMargins"))
    net_margin = _safe(info.get("profitMargins"))

    # 5yr operating margin trend
    op_margins_hist = [
        s.get("operatingIncome", 0) / s.get("revenue", 1)
        for s in reversed(income_stmts)
        if s.get("revenue") and s.get("operatingIncome") is not None
    ]
    margin_slope = _linear_slope(op_margins_hist) if len(op_margins_hist) >= 3 else 0.0

    # ROE score (0-40)
    t = THRESHOLDS
    if roe >= t["roe_high"]:      roe_pts = 40
    elif roe >= t["roe_avg"]:     roe_pts = 28
    elif roe >= t["roe_low"]:     roe_pts = 16
    else:                         roe_pts = 5

    # Operating margin score (0-40)
    if op_margin >= t["op_margin_high"]:  om_pts = 40
    elif op_margin >= t["op_margin_avg"]: om_pts = 24
    elif op_margin > 0:                   om_pts = 12
    else:                                 om_pts = 0

    # Trend bonus (0-20)
    trend_pts = 20 if margin_slope > 0.005 else (12 if margin_slope > -0.005 else 0)

    raw = roe_pts + om_pts + trend_pts
    score = min(100, raw)

    notes = []
    if roe >= t["roe_high"]:  notes.append(f"ROE {roe:.1%} — high quality returns")
    elif roe < t["roe_low"]:  notes.append(f"ROE {roe:.1%} — below quality threshold")
    if margin_slope > 0.005:  notes.append("Operating margin improving over 5yr")
    elif margin_slope < -0.005: notes.append("Operating margin deteriorating over 5yr")

    return SubScore(
        name="Profitability & Returns",
        score=score,
        label=_label_quality(score),
        metrics={
            "roe": round(roe, 4),
            "operating_margin": round(op_margin, 4),
            "net_margin": round(net_margin, 4),
            "margin_trend_slope_per_yr": round(margin_slope, 4),
        },
        notes=notes,
    )


# ── Sub-score: Cash Generation ────────────────────────────────────────────────

def _score_cash_generation(info: dict, income_stmts: list[dict], cash_flows: list[dict]) -> SubScore:
    red_flags = []

    # Build FCF series oldest→newest
    fcf_series = []
    for cf, inc in zip(reversed(cash_flows), reversed(income_stmts)):
        op_cf = _safe(cf.get("operatingCashFlow"))
        capex = abs(_safe(cf.get("capitalExpenditure")))
        rev   = _safe(inc.get("revenue"), 1)
        fcf   = op_cf - capex
        fcf_series.append((fcf, rev))

    if not fcf_series:
        return SubScore("Cash Generation", 30, "Average", notes=["Insufficient FCF data"])

    fcf_vals   = [f for f, _ in fcf_series]
    fcf_margins = [f / r if r else 0 for f, r in fcf_series]
    avg_fcf_margin = statistics.mean(fcf_margins) if fcf_margins else 0

    negative_years = sum(1 for f in fcf_vals if f < 0)
    if negative_years >= 2:
        red_flags.append(f"Negative FCF in {negative_years} of last {len(fcf_vals)} years")

    # FCF CAGR
    fcf_cagr = 0.0
    if len(fcf_vals) >= 2 and fcf_vals[0] > 0 and fcf_vals[-1] > 0:
        fcf_cagr = _cagr(fcf_vals[0], fcf_vals[-1], len(fcf_vals) - 1)

    # NI vs FCF divergence check
    net_incomes = [_safe(s.get("netIncome")) for s in income_stmts[:3]]
    if net_incomes and fcf_vals:
        avg_ni = statistics.mean(net_incomes)
        avg_fcf_recent = statistics.mean(fcf_vals[-3:]) if len(fcf_vals) >= 3 else fcf_vals[-1]
        if avg_ni > 0 and avg_fcf_recent < avg_ni * 0.5:
            red_flags.append("Large divergence between net income and FCF — check accruals")

    t = THRESHOLDS
    margin_pts = (50 if avg_fcf_margin >= t["fcf_margin_high"]
                  else 30 if avg_fcf_margin >= t["fcf_margin_avg"]
                  else 10 if avg_fcf_margin > 0 else 0)
    cagr_pts   = (30 if fcf_cagr >= t["fcf_cagr_high"]
                  else 20 if fcf_cagr >= t["fcf_cagr_avg"]
                  else 10 if fcf_cagr > 0 else 0)
    penalty    = negative_years * 10

    score = max(0, min(100, margin_pts + cagr_pts - penalty))

    notes = [f"FCF CAGR {fcf_cagr:.1%} over {len(fcf_vals)-1}yr",
             f"Avg FCF margin {avg_fcf_margin:.1%}"] + red_flags

    return SubScore(
        name="Cash Generation",
        score=score,
        label=_label_quality(score),
        metrics={
            "avg_fcf_margin": round(avg_fcf_margin, 4),
            "fcf_cagr": round(fcf_cagr, 4),
            "negative_fcf_years": negative_years,
            "fcf_series": [round(f, 0) for f in fcf_vals],
        },
        notes=notes,
    )


# ── Sub-score: Balance Sheet ──────────────────────────────────────────────────

def _score_balance_sheet(info: dict, balance_sheets: list[dict]) -> tuple[SubScore, list[str]]:
    red_flags = []
    de     = _safe(info.get("debtToEquity")) / 100  # yfinance returns as %, e.g. 150 = 1.5x
    ebitda = _safe(info.get("ebitda"), 1)
    total_debt = _safe(info.get("totalDebt"))
    total_cash = _safe(info.get("totalCash"))
    net_debt   = total_debt - total_cash

    nd_ebitda = net_debt / ebitda if ebitda > 0 else 0

    # Interest coverage proxy: operating income / interest expense
    int_coverage = 0.0
    if balance_sheets and len(balance_sheets) > 0:
        # yfinance doesn't give interest expense directly in balance sheet
        # Use ebitda / total_debt as proxy
        int_coverage = ebitda / total_debt if total_debt > 0 else 10.0

    t = THRESHOLDS
    de_pts = (40 if de <= t["de_safe"]
              else 25 if de <= t["de_ok"]
              else 10 if de <= t["de_risky"]
              else 0)
    nd_pts = (40 if nd_ebitda <= t["nd_ebitda_safe"]
              else 25 if nd_ebitda <= t["nd_ebitda_ok"]
              else 10 if nd_ebitda <= 5
              else 0)
    cov_pts = min(20, int(int_coverage * 2)) if int_coverage < 10 else 20

    if de > t["de_risky"]:
        red_flags.append(f"High leverage: Debt/Equity {de:.1f}x — above safe threshold")
    if nd_ebitda > t["nd_ebitda_ok"]:
        red_flags.append(f"Net Debt/EBITDA {nd_ebitda:.1f}x — elevated")

    score = min(100, de_pts + nd_pts + cov_pts)
    notes = [f"D/E {de:.2f}x", f"Net Debt/EBITDA {nd_ebitda:.1f}x"]

    return SubScore(
        name="Balance Sheet",
        score=score,
        label=_label_quality(score),
        metrics={
            "debt_to_equity": round(de, 3),
            "net_debt_ebitda": round(nd_ebitda, 2),
            "total_debt": total_debt,
            "total_cash": total_cash,
            "net_debt": net_debt,
        },
        notes=notes,
    ), red_flags


# ── Sub-score: Growth Profile ─────────────────────────────────────────────────

def _score_growth(info: dict, income_stmts: list[dict]) -> SubScore:
    revenues = [_safe(s.get("revenue")) for s in income_stmts if s.get("revenue")]
    revenues = [r for r in revenues if r > 0]

    rev_cagr = 0.0
    if len(revenues) >= 2:
        years = len(revenues) - 1
        rev_cagr = _cagr(revenues[-1], revenues[0], years)

    # EPS CAGR from yfinance info
    eps_fwd  = _safe(info.get("epsForward"))
    eps_ttm  = _safe(info.get("epsTrailingTwelveMonths"))
    analyst_growth = _safe(info.get("earningsGrowth"))

    # Revenue growth volatility
    if len(revenues) >= 3:
        yoy = [(revenues[i] - revenues[i+1]) / revenues[i+1]
               for i in range(len(revenues)-1) if revenues[i+1] > 0]
        growth_vol = statistics.stdev(yoy) if len(yoy) >= 2 else 0
    else:
        growth_vol = 0

    t = THRESHOLDS
    rev_pts = (40 if rev_cagr >= t["rev_cagr_high"]
               else 25 if rev_cagr >= t["rev_cagr_avg"]
               else 10 if rev_cagr > 0 else 0)

    analyst_pts = (30 if analyst_growth >= t["eps_cagr_high"]
                   else 20 if analyst_growth >= t["eps_cagr_avg"]
                   else 10 if analyst_growth > 0 else 0)

    # Penalise high volatility
    vol_penalty = min(20, int(growth_vol * 100))

    score = min(100, max(0, rev_pts + analyst_pts - vol_penalty))

    notes = [f"Revenue CAGR {rev_cagr:.1%} over {len(revenues)-1}yr"]
    if analyst_growth:
        notes.append(f"Analyst earnings growth est: {analyst_growth:.1%}")
    if growth_vol > 0.15:
        notes.append(f"High growth volatility (σ={growth_vol:.1%}) — cyclical risk")

    return SubScore(
        name="Growth Profile",
        score=score,
        label=_label_quality(score),
        metrics={
            "revenue_cagr": round(rev_cagr, 4),
            "analyst_earnings_growth": round(analyst_growth, 4),
            "growth_volatility": round(growth_vol, 4),
            "revenue_series": [round(r, 0) for r in revenues[:5]],
        },
        notes=notes,
    )


# ── Valuation scoring ─────────────────────────────────────────────────────────

def _score_valuation(info: dict, income_stmts: list[dict]) -> tuple[float, str, dict, float, list[str]]:
    """Returns (valuation_score, label, metrics_dict, expected_return, red_flags)."""
    red_flags = []

    pe_ttm    = _safe(info.get("trailingPE"))
    pe_fwd    = _safe(info.get("forwardPE"))
    ps        = _safe(info.get("priceToSalesTrailing12Months"))
    pb        = _safe(info.get("priceToBook"))
    ev_ebitda = _safe(info.get("enterpriseToEbitda"))
    mkt_cap   = _safe(info.get("marketCap"), 1)
    ev        = _safe(info.get("enterpriseValue"), mkt_cap)
    fcf_ttm   = _safe(info.get("freeCashflow"))
    eps_ttm   = _safe(info.get("epsTrailingTwelveMonths"))
    analyst_growth = _safe(info.get("earningsGrowth"))

    # FCF yield
    fcf_yield = fcf_ttm / ev if ev > 0 and fcf_ttm > 0 else 0

    # PEG
    peg = (pe_ttm / (analyst_growth * 100)) if pe_ttm > 0 and analyst_growth > 0.01 else 0

    t = THRESHOLDS
    # FCF yield score (0-50)
    fcf_pts = (50 if fcf_yield >= t["fcf_yield_high"]
               else 35 if fcf_yield >= t["fcf_yield_fair"]
               else 20 if fcf_yield > 0 else 10)

    # P/E score (0-30)
    if pe_ttm <= 0:
        pe_pts = 15  # negative P/E — neutral
    elif pe_ttm <= t["pe_cheap"]:
        pe_pts = 30
    elif pe_ttm <= t["pe_fair_hi"]:
        pe_pts = 18
    else:
        pe_pts = 5

    # PEG score (0-20)
    if peg <= 0:
        peg_pts = 10
    elif peg <= 1.0:
        peg_pts = 20
    elif peg <= t["peg_fair"]:
        peg_pts = 12
    else:
        peg_pts = 3

    val_score = min(100, fcf_pts + pe_pts + peg_pts)

    if pe_ttm > 40 and fcf_yield < 0.02:
        red_flags.append(f"Stretched valuation: P/E {pe_ttm:.1f}x with FCF yield only {fcf_yield:.1%}")

    # Expected return: FCF yield + sustainable growth
    sustainable_growth = min(analyst_growth, 0.20) if analyst_growth > 0 else 0.05
    expected_return = fcf_yield + sustainable_growth

    if expected_return < t["required_return"]:
        red_flags.append(
            f"Expected return {expected_return:.1%} below required {t['required_return']:.0%}"
        )

    val_label = _label_valuation(val_score)

    metrics = {
        "pe_ttm":        round(pe_ttm, 1),
        "pe_forward":    round(pe_fwd, 1),
        "ev_ebitda":     round(ev_ebitda, 1),
        "price_to_sales": round(ps, 2),
        "price_to_book": round(pb, 2),
        "fcf_yield":     round(fcf_yield, 4),
        "peg_ratio":     round(peg, 2),
        "market_cap":    mkt_cap,
        "enterprise_value": ev,
        "expected_return": round(expected_return, 4),
        "required_return": t["required_return"],
    }
    return val_score, val_label, metrics, expected_return, red_flags


# ── Red-flag override checks ──────────────────────────────────────────────────

def _check_red_flags(info: dict, sub_scores: dict, cash_sub: SubScore, bs_flags: list[str]) -> list[str]:
    flags = list(bs_flags)

    # Repeated negative FCF
    neg_years = cash_sub.metrics.get("negative_fcf_years", 0)
    if neg_years >= 3:
        flags.append(f"Repeated negative FCF ({neg_years} years) — capital destruction risk")

    # Heavy dilution
    de = sub_scores.get("balance_sheet", SubScore("", 0, "")).metrics.get("debt_to_equity", 0)
    if de > 3.0:
        flags.append(f"Extreme leverage D/E {de:.1f}x — financial distress risk")

    return flags


# ── Decision engine ───────────────────────────────────────────────────────────

def _decide(quality: float, valuation: float, expected_return: float, red_flags: list[str]) -> str:
    t = THRESHOLDS
    force_avoid = any(
        kw in f.lower()
        for f in red_flags
        for kw in ["extreme leverage", "repeated negative fcf", "financial distress"]
    )
    if force_avoid:
        return "AVOID"

    if quality >= t["quality_buy"] and valuation >= t["valuation_buy"] and expected_return >= t["required_return"]:
        return "BUY / ACCUMULATE"
    if quality >= t["quality_buy"] and valuation < t["valuation_buy"]:
        return "WATCHLIST"    # great business, too expensive
    if t["quality_watchlist"] <= quality < t["quality_buy"] and valuation >= t["valuation_buy"]:
        return "WATCHLIST"    # decent business at good price
    if quality < t["quality_watchlist"]:
        return "AVOID"
    return "WATCHLIST"


# ── Main entry point ──────────────────────────────────────────────────────────

def run_qafp(
    ticker: str,
    info: dict,
    income_stmts: list[dict],
    balance_sheets: list[dict],
    cash_flows: list[dict],
    required_return: float = 0.09,
) -> QAFPResult:
    """Compute full QAFP analysis and return a QAFPResult."""

    THRESHOLDS["required_return"] = required_return

    company_name  = info.get("longName") or info.get("shortName", ticker)
    sector        = info.get("sector", "Unknown")
    security_type = "etf" if info.get("quoteType", "").upper() == "ETF" else "stock"

    # Sub-scores
    prof_sub = _score_profitability(info, income_stmts)
    cash_sub = _score_cash_generation(info, income_stmts, cash_flows)
    bs_sub, bs_flags = _score_balance_sheet(info, balance_sheets)
    growth_sub = _score_growth(info, income_stmts)

    sub_scores = {
        "profitability": prof_sub,
        "cash_generation": cash_sub,
        "balance_sheet": bs_sub,
        "growth": growth_sub,
    }

    # Quality score: weighted average of sub-scores
    weights = {"profitability": 0.30, "cash_generation": 0.30, "balance_sheet": 0.20, "growth": 0.20}
    quality_score = sum(sub_scores[k].score * w for k, w in weights.items())
    quality_label = _label_quality(quality_score)

    # Valuation
    val_score, val_label, val_metrics, expected_return, val_flags = _score_valuation(info, income_stmts)

    # Key metrics summary
    key_metrics = {
        "roe":             prof_sub.metrics.get("roe", 0),
        "operating_margin": prof_sub.metrics.get("operating_margin", 0),
        "net_margin":      prof_sub.metrics.get("net_margin", 0),
        "fcf_margin":      cash_sub.metrics.get("avg_fcf_margin", 0),
        "fcf_cagr":        cash_sub.metrics.get("fcf_cagr", 0),
        "revenue_cagr":    growth_sub.metrics.get("revenue_cagr", 0),
        "debt_to_equity":  bs_sub.metrics.get("debt_to_equity", 0),
        "net_debt_ebitda": bs_sub.metrics.get("net_debt_ebitda", 0),
    }

    # Aggregate red flags
    all_flags = _check_red_flags(info, sub_scores, cash_sub, bs_flags) + val_flags

    recommendation = _decide(quality_score, val_score, expected_return, all_flags)

    return QAFPResult(
        ticker=ticker,
        company_name=company_name,
        security_type=security_type,
        sector=sector,
        quality_score=round(quality_score, 1),
        quality_label=quality_label,
        valuation_score=round(val_score, 1),
        valuation_label=val_label,
        sub_scores=sub_scores,
        key_metrics=key_metrics,
        valuation_metrics=val_metrics,
        expected_return=round(expected_return, 4),
        required_return=required_return,
        recommendation=recommendation,
        red_flags=all_flags,
    )
