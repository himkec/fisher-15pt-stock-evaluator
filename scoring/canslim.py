"""
CAN SLIM scoring engine.
Implements William O'Neil's CAN SLIM framework using yfinance data.

Letters C, A, N, S, L, I are scored 0–100 and combined into a weighted
composite score.  M (market direction) is a gatekeeper — it is evaluated
separately and can override a BUY recommendation to WATCHLIST/AVOID.
"""

import statistics
from typing import Any

from scoring.canslim_models import CANSLIMResult, LetterScore, BuyPoint


# ── Weights (must sum to 1.0) ─────────────────────────────────────────────────
WEIGHTS = {
    "C": 0.20,  # Current quarterly earnings
    "A": 0.20,  # Annual earnings growth
    "N": 0.15,  # New: product/management/highs
    "S": 0.15,  # Supply and demand
    "L": 0.15,  # Leader vs laggard
    "I": 0.15,  # Institutional sponsorship
}

# ── Thresholds ────────────────────────────────────────────────────────────────
T = {
    # C — Current earnings
    "c_eps_strong":   0.25,   # ≥25% YoY EPS growth = strong
    "c_eps_average":  0.10,   # 10-25% = average
    "c_quality_ratio": 0.70,  # FCF / NI ≥ 70% = clean earnings

    # A — Annual earnings
    "a_cagr_strong":  0.25,   # ≥25% EPS CAGR = strong
    "a_cagr_average": 0.10,   # 10-25% = average
    "a_consistency":  4,      # 4+ of last 5 years positive EPS growth

    # N — New
    "n_high_tolerance": 0.05,  # within 5% of 52w high = near high
    "n_base_tolerance": 0.10,  # within 10% = buyable zone

    # S — Supply / demand
    "s_float_small": 500_000_000,  # < 500M shares = small float
    "s_volume_spike": 1.50,        # ≥ 1.5× avg volume = demand spike

    # L — Leader
    "l_outperform_strong":  0.20,  # +20pp above SPY 12m = ~90th pct
    "l_outperform_average": 0.10,  # +10pp = ~80th pct
    "l_outperform_leader":  0.00,  # above SPY = ~70th pct

    # I — Institutional
    "i_insts_strong": 100,   # ≥100 institutional holders = strong
    "i_insts_average": 30,   # 30-100 = average
    "i_pct_strong": 0.50,    # ≥50% institutional ownership
    "i_pct_average": 0.30,   # 30-50%

    # M — Market
    "m_distribution_warn": 4,  # 4+ distribution days in 25 sessions = caution
    "m_distribution_bad":  6,  # 6+ = correction signal
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        f = float(val)
        return default if f != f else f   # NaN check
    except (TypeError, ValueError):
        return default


def _label(score: float) -> str:
    if score >= 70:  return "Strong"
    if score >= 40:  return "Average"
    return "Weak"


def _cagr(start: float, end: float, years: int) -> float:
    if start <= 0 or end <= 0 or years <= 0:
        return 0.0
    return (end / start) ** (1 / years) - 1


def _mean(lst: list[float]) -> float:
    return statistics.mean(lst) if lst else 0.0


def _ma(prices: list[float], n: int) -> float:
    """Moving average of first n prices (newest-first list)."""
    window = prices[:n]
    return _mean(window) if len(window) == n else 0.0


# ── C — Current Quarterly Earnings ───────────────────────────────────────────

def _score_C(
    info: dict,
    quarterly_income: list[dict],
    quarterly_cashflow: list[dict],
) -> LetterScore:
    """Current quarterly EPS and sales growth YoY."""
    shares = _safe(info.get("sharesOutstanding"), 1) or 1

    # Need at least 5 quarters for YoY comparison (q0 vs q4)
    if len(quarterly_income) < 5:
        return LetterScore(
            letter="C", name="Current Quarterly Earnings", score=40, label="Average",
            weight=WEIGHTS["C"],
            notes=["Insufficient quarterly data — defaulting to average."],
            metrics={"quarters_available": len(quarterly_income)},
        )

    q_latest = quarterly_income[0]
    q_year_ago = quarterly_income[4]

    ni_latest   = _safe(q_latest.get("netIncome"))
    ni_year_ago = _safe(q_year_ago.get("netIncome"))
    rev_latest  = _safe(q_latest.get("revenue"), 1)
    rev_year_ago = _safe(q_year_ago.get("revenue"), 1)

    # EPS approximation (shares constant — good enough for growth direction)
    eps_latest   = ni_latest / shares
    eps_year_ago = ni_year_ago / shares

    if eps_year_ago > 0:
        eps_growth = (eps_latest - eps_year_ago) / eps_year_ago
    elif eps_year_ago < 0 and eps_latest > 0:
        eps_growth = 1.0   # turned profitable
    else:
        eps_growth = 0.0

    sales_growth = (rev_latest - rev_year_ago) / rev_year_ago if rev_year_ago > 0 else 0.0

    # EPS quality: operating cash flow ≥ 70% of net income
    cf_latest = quarterly_cashflow[0] if quarterly_cashflow else {}
    op_cf = _safe(cf_latest.get("operatingCashFlow"))
    quality_clean = (op_cf >= ni_latest * T["c_quality_ratio"]) if ni_latest > 0 else False

    # Score
    if eps_growth >= T["c_eps_strong"]:
        eps_pts = 60
    elif eps_growth >= T["c_eps_average"]:
        eps_pts = 40
    elif eps_growth > 0:
        eps_pts = 20
    else:
        eps_pts = 0

    sales_pts   = 20 if sales_growth > 0 else 0
    quality_pts = 20 if quality_clean else 0

    score = min(100, eps_pts + sales_pts + quality_pts)
    notes = [
        f"Q EPS growth YoY: {eps_growth:+.1%}",
        f"Q Sales growth YoY: {sales_growth:+.1%}",
        f"Earnings quality: {'clean (FCF ≥ 70% of NI)' if quality_clean else 'check accruals'}",
    ]

    return LetterScore(
        letter="C", name="Current Quarterly Earnings",
        score=score, label=_label(score), weight=WEIGHTS["C"],
        metrics={
            "eps_growth_yoy": round(eps_growth, 4),
            "sales_growth_yoy": round(sales_growth, 4),
            "quality_clean": quality_clean,
            "latest_quarter": q_latest.get("date", ""),
        },
        notes=notes,
    )


# ── A — Annual Earnings Growth ────────────────────────────────────────────────

def _score_A(info: dict, income_stmts: list[dict]) -> LetterScore:
    """Annual EPS CAGR (3yr and 5yr) and consistency."""
    shares = _safe(info.get("sharesOutstanding"), 1) or 1

    if len(income_stmts) < 2:
        return LetterScore(
            letter="A", name="Annual Earnings Growth", score=40, label="Average",
            weight=WEIGHTS["A"],
            notes=["Insufficient annual data — defaulting to average."],
            metrics={},
        )

    eps_series = []   # newest first
    for stmt in income_stmts:
        ni = _safe(stmt.get("netIncome"))
        eps_series.append(ni / shares)

    # CAGR calculations — need positive start value
    def _eps_cagr(n_years: int) -> float:
        if len(eps_series) <= n_years:
            n_years = len(eps_series) - 1
        if n_years < 1:
            return 0.0
        start, end = eps_series[n_years], eps_series[0]
        return _cagr(start, end, n_years)

    eps_3y = _eps_cagr(3)
    eps_5y = _eps_cagr(5)

    # Consistency: years with positive YoY EPS growth (out of last 5)
    consistency = sum(
        1 for i in range(min(5, len(eps_series) - 1))
        if eps_series[i] > eps_series[i + 1]
    )

    # Score
    if eps_3y >= T["a_cagr_strong"] and eps_5y >= T["a_cagr_strong"]:
        cagr_pts = 70
    elif eps_3y >= T["a_cagr_average"] or eps_5y >= T["a_cagr_average"]:
        cagr_pts = 45
    elif eps_3y > 0 and eps_5y > 0:
        cagr_pts = 25
    else:
        cagr_pts = 0

    consistency_pts = 30 if consistency >= T["a_consistency"] else (15 if consistency >= 3 else 0)

    score = min(100, cagr_pts + consistency_pts)
    notes = [
        f"EPS CAGR 3yr: {eps_3y:+.1%}",
        f"EPS CAGR 5yr: {eps_5y:+.1%}",
        f"Years of positive EPS growth (last 5): {consistency}/5",
    ]

    return LetterScore(
        letter="A", name="Annual Earnings Growth",
        score=score, label=_label(score), weight=WEIGHTS["A"],
        metrics={
            "eps_cagr_3y": round(eps_3y, 4),
            "eps_cagr_5y": round(eps_5y, 4),
            "eps_consistency_5y": consistency,
            "eps_series_newest_first": [round(e, 4) for e in eps_series[:6]],
        },
        notes=notes,
    )


# ── N — New: Product / Management / Highs ────────────────────────────────────

def _score_N(info: dict, price_history: list[float]) -> LetterScore:
    """Price near 52-week high and momentum acceleration."""
    current_price = _safe(info.get("regularMarketPrice") or info.get("currentPrice"))
    high_52w      = _safe(info.get("fiftyTwoWeekHigh"))
    eps_fwd       = _safe(info.get("epsForward"))
    eps_ttm       = _safe(info.get("epsTrailingTwelveMonths"))

    near_high = (current_price >= high_52w * (1 - T["n_high_tolerance"])
                 if high_52w > 0 and current_price > 0 else False)

    # Price acceleration: 3-month return vs prior 3-month return
    # price_history is newest-first daily closes
    price_accelerating = False
    ret_3m = ret_prior_3m = 0.0
    if len(price_history) >= 127:
        p_now = price_history[0]
        p_3m  = price_history[63]
        p_6m  = price_history[126]
        if p_3m > 0 and p_6m > 0:
            ret_3m       = (p_now - p_3m) / p_3m
            ret_prior_3m = (p_3m - p_6m) / p_6m
            price_accelerating = ret_3m > ret_prior_3m

    # Analyst revision proxy: forward EPS > trailing EPS (positive revision signal)
    analyst_positive = (eps_fwd > eps_ttm > 0)

    score = 0
    if near_high:         score += 40
    if price_accelerating: score += 30
    if analyst_positive:  score += 30

    notes = [
        f"Price ${current_price:.2f} vs 52w high ${high_52w:.2f} "
        f"({'near high ✓' if near_high else 'below high'})",
        f"Momentum: recent 3m {ret_3m:+.1%} vs prior 3m {ret_prior_3m:+.1%} "
        f"({'accelerating ✓' if price_accelerating else 'decelerating'})",
    ]
    if eps_fwd and eps_ttm:
        notes.append(f"Analyst EPS est ${eps_fwd:.2f} vs TTM ${eps_ttm:.2f} "
                     f"({'positive revision ✓' if analyst_positive else 'flat/negative'})")

    return LetterScore(
        letter="N", name="New Product / Management / Highs",
        score=min(100, score), label=_label(score), weight=WEIGHTS["N"],
        metrics={
            "current_price": round(current_price, 2),
            "high_52w": round(high_52w, 2),
            "near_high": near_high,
            "ret_3m": round(ret_3m, 4),
            "ret_prior_3m": round(ret_prior_3m, 4),
            "price_accelerating": price_accelerating,
            "analyst_positive": analyst_positive,
        },
        notes=notes,
    )


# ── S — Supply and Demand ─────────────────────────────────────────────────────

def _score_S(info: dict) -> LetterScore:
    """Float size + volume demand spike + price above 50-day MA."""
    shares       = _safe(info.get("sharesOutstanding"))
    avg_volume   = _safe(info.get("averageVolume") or info.get("averageVolume10days"), 1)
    curr_volume  = _safe(info.get("regularMarketVolume"))
    curr_price   = _safe(info.get("regularMarketPrice") or info.get("currentPrice"))
    ma50         = _safe(info.get("fiftyDayAverage"))

    small_float    = 0 < shares < T["s_float_small"]
    volume_spike   = (curr_volume >= avg_volume * T["s_volume_spike"]) if avg_volume > 0 else False
    breaking_out   = (curr_price > ma50) if ma50 > 0 and curr_price > 0 else False
    strong_demand  = volume_spike and breaking_out

    score = 0
    if small_float:   score += 40
    if strong_demand: score += 60
    elif volume_spike or breaking_out: score += 30

    vol_ratio = curr_volume / avg_volume if avg_volume > 0 else 0.0

    notes = [
        f"Shares outstanding: {shares/1e6:.0f}M "
        f"({'small float ✓' if small_float else 'large float'})",
        f"Volume: {vol_ratio:.1f}× avg "
        f"({'spike ✓' if volume_spike else 'normal'})",
        f"Price ${curr_price:.2f} vs 50d MA ${ma50:.2f} "
        f"({'above MA ✓' if breaking_out else 'below MA'})",
    ]

    return LetterScore(
        letter="S", name="Supply and Demand",
        score=min(100, score), label=_label(score), weight=WEIGHTS["S"],
        metrics={
            "shares_outstanding": shares,
            "small_float": small_float,
            "volume_ratio": round(vol_ratio, 2),
            "volume_spike": volume_spike,
            "price_above_ma50": breaking_out,
            "strong_demand": strong_demand,
        },
        notes=notes,
    )


# ── L — Leader vs Laggard ─────────────────────────────────────────────────────

def _score_L(price_history: list[float], spy_history: list[float]) -> LetterScore:
    """Relative strength vs S&P 500 over 12 months."""
    # price_history and spy_history are newest-first daily closes

    def _12m_return(hist: list[float]) -> float:
        if len(hist) < 252:
            return 0.0
        p_now = hist[0]
        p_12m = hist[251]
        return (p_now - p_12m) / p_12m if p_12m > 0 else 0.0

    ticker_12m = _12m_return(price_history)
    spy_12m    = _12m_return(spy_history)

    # Relative outperformance vs SPY
    outperformance = ticker_12m - spy_12m

    # Map to approximate RS percentile
    if outperformance >= T["l_outperform_strong"]:
        rs_pct = 92
        score  = 100
    elif outperformance >= T["l_outperform_average"]:
        rs_pct = 83
        score  = 80
    elif outperformance >= T["l_outperform_leader"]:
        rs_pct = 72
        score  = 60
    else:
        # Below market — linearly scale from 0 to 55 based on how far below
        rs_pct = max(5, int(65 + outperformance * 150))
        score  = max(0, int(60 + outperformance * 200))

    notes = [
        f"12m return: {ticker_12m:+.1%} vs SPY {spy_12m:+.1%}",
        f"Relative outperformance: {outperformance:+.1%}",
        f"Estimated RS percentile: ~{rs_pct}th",
    ]
    if rs_pct < 70:
        notes.append("Below 70th percentile — laggard, not a leader per CAN SLIM rules")

    return LetterScore(
        letter="L", name="Leader vs Laggard",
        score=max(0, min(100, score)), label=_label(score), weight=WEIGHTS["L"],
        metrics={
            "ticker_12m_return": round(ticker_12m, 4),
            "spy_12m_return":    round(spy_12m, 4),
            "outperformance":    round(outperformance, 4),
            "rs_percentile_est": rs_pct,
        },
        notes=notes,
    )


# ── I — Institutional Sponsorship ─────────────────────────────────────────────

def _score_I(info: dict, institutional_holders: list[dict]) -> LetterScore:
    """Institutional holder count and ownership quality."""
    num_insts        = len(institutional_holders) if institutional_holders else 0
    pct_institutional = _safe(info.get("heldPercentInstitutions"))
    pct_insider      = _safe(info.get("heldPercentInsiders"))
    pct_float        = max(0.0, 1.0 - pct_insider)

    # Count score (0-40)
    if num_insts >= T["i_insts_strong"]:
        count_pts = 40
    elif num_insts >= T["i_insts_average"]:
        count_pts = 25
    elif num_insts > 0:
        count_pts = 10
    else:
        count_pts = 0

    # Quality score — use pct_institutional as proxy (0-30)
    if pct_institutional >= T["i_pct_strong"]:
        quality_pts = 30
    elif pct_institutional >= T["i_pct_average"]:
        quality_pts = 20
    elif pct_institutional > 0:
        quality_pts = 10
    else:
        quality_pts = 0

    # Trend proxy — widely held float suggests broad institutional interest (0-30)
    if pct_float >= 0.95:
        trend_pts = 30
    elif pct_float >= 0.80:
        trend_pts = 20
    elif pct_float >= 0.60:
        trend_pts = 10
    else:
        trend_pts = 0

    score = min(100, count_pts + quality_pts + trend_pts)

    notes = [
        f"Institutional holders: {num_insts}",
        f"Institutional ownership: {pct_institutional:.1%}",
        f"Insider ownership: {pct_insider:.1%} ({pct_float:.1%} float)",
    ]

    return LetterScore(
        letter="I", name="Institutional Sponsorship",
        score=score, label=_label(score), weight=WEIGHTS["I"],
        metrics={
            "num_institutional_holders": num_insts,
            "pct_institutional":  round(pct_institutional, 4),
            "pct_insider":        round(pct_insider, 4),
            "pct_float":          round(pct_float, 4),
        },
        notes=notes,
    )


# ── M — Market Direction (gatekeeper, not in composite) ──────────────────────

def _assess_market(spy_history: list[float]) -> tuple[str, dict]:
    """Assess broad market trend using SPY price history (newest first)."""
    if len(spy_history) < 50:
        return "mixed", {"note": "Insufficient SPY history"}

    current = spy_history[0]
    ma50  = _ma(spy_history, 50)
    ma200 = _ma(spy_history, 200) if len(spy_history) >= 200 else 0.0

    # Distribution days: price fell day-over-day in recent 25 sessions
    # (Without volume we count consecutive down days as proxy)
    dist_days = sum(
        1 for i in range(min(24, len(spy_history) - 1))
        if spy_history[i] < spy_history[i + 1]   # day fell vs prior day
    )

    # Trend classification
    if ma200 > 0:
        if current > ma50 > ma200 and dist_days <= T["m_distribution_warn"]:
            direction = "market_uptrend"
        elif current < ma50 < ma200 or dist_days >= T["m_distribution_bad"]:
            direction = "market_correction"
        else:
            direction = "mixed"
    else:
        # Only 50d available
        if current > ma50 and dist_days <= T["m_distribution_warn"]:
            direction = "market_uptrend"
        elif dist_days >= T["m_distribution_bad"]:
            direction = "market_correction"
        else:
            direction = "mixed"

    metrics = {
        "spy_current": round(current, 2),
        "spy_ma50":    round(ma50, 2),
        "spy_ma200":   round(ma200, 2) if ma200 else "N/A",
        "distribution_days_25d": dist_days,
    }
    return direction, metrics


# ── Buy Point Detection ───────────────────────────────────────────────────────

def _detect_buy_point(info: dict, price_history: list[float]) -> BuyPoint | None:
    """Detect cup/flat base pivot and check for breakout confirmation."""
    pivot = _safe(info.get("fiftyTwoWeekHigh"))
    if pivot <= 0:
        return None

    current_price = _safe(info.get("regularMarketPrice") or info.get("currentPrice"))
    avg_volume    = _safe(info.get("averageVolume") or info.get("averageVolume10days"), 1)
    curr_volume   = _safe(info.get("regularMarketVolume"))

    near_pivot      = (current_price >= pivot * (1 - T["n_base_tolerance"])
                       if current_price > 0 else False)
    volume_confirmed = (curr_volume >= avg_volume * T["s_volume_spike"]
                        if avg_volume > 0 else False)

    # Base check: 7-week price consolidation (35 trading days)
    has_base = False
    if len(price_history) >= 35:
        base_prices = price_history[:35]
        base_high   = max(base_prices)
        base_low    = min(base_prices)
        base_depth  = (base_high - base_low) / base_high if base_high > 0 else 1
        has_base    = base_depth <= 0.15   # < 15% depth = tight base

    valid = near_pivot and volume_confirmed

    entry       = round(pivot * 1.02, 2)
    stop_loss   = round(entry * 0.93, 2)
    take_profit = round(entry * 1.25, 2)

    vol_ratio = curr_volume / avg_volume if avg_volume > 0 else 0.0
    pct_from_pivot = (current_price / pivot - 1) if pivot > 0 else 0

    if valid:
        notes = (f"Breakout above pivot ${pivot:.2f} on {vol_ratio:.1f}× avg volume. "
                 f"{'Base formed ✓' if has_base else 'No clear base — higher risk'}")
    elif near_pivot:
        notes = (f"Near pivot ${pivot:.2f} ({pct_from_pivot:+.1%}) but volume "
                 f"only {vol_ratio:.1f}× avg — wait for volume confirmation.")
    else:
        notes = (f"Price ${current_price:.2f} is {pct_from_pivot:+.1%} from pivot "
                 f"${pivot:.2f} — not in buyable range yet.")

    return BuyPoint(
        pivot=round(pivot, 2),
        valid=valid,
        entry=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
        notes=notes,
    )


# ── Composite score label ─────────────────────────────────────────────────────

def _composite_label(score: float) -> str:
    if score >= 70:  return "Strong"
    if score >= 50:  return "Average"
    return "Weak"


# ── Decision engine ───────────────────────────────────────────────────────────

def _decide(
    composite: float,
    market_direction: str,
    buy_point: BuyPoint | None,
    red_flags: list[str],
) -> str:
    if composite < 50:
        return "AVOID"
    if market_direction == "market_correction":
        return "WATCHLIST"   # even great stocks fail in bear market
    if composite >= 70 and market_direction == "market_uptrend" and buy_point and buy_point.valid:
        return "BUY"
    if composite >= 70:
        return "WATCHLIST"   # strong fundamentals but not in confirmed uptrend + buy point
    return "WATCHLIST"


# ── Investor fit ──────────────────────────────────────────────────────────────

_INVESTOR_FIT = {
    "for": [
        "Active traders and aggressive growth investors",
        "Users comfortable with short- to medium-term holding periods (weeks to months)",
        "People willing to follow strict buy/sell rules and monitor markets frequently",
    ],
    "not_for": [
        "Classic long-term buy-and-hold investors seeking low turnover",
        "Very risk-averse investors who dislike frequent stop-losses",
        "Anyone unable to track market direction and price/volume regularly",
    ],
    "summary": (
        "Aggressive, rules-based growth system best for high risk tolerance "
        "and short- to medium-term horizons, not 'buy forever' investors."
    ),
}


# ── Main entry point ──────────────────────────────────────────────────────────

def run_canslim(
    ticker: str,
    info: dict,
    income_stmts: list[dict],
    quarterly_income: list[dict],
    quarterly_cashflow: list[dict],
    price_history: list[float],         # newest-first daily closes
    institutional_holders: list[dict],  # from yfinance
    spy_history: list[float],           # newest-first daily closes for SPY
) -> CANSLIMResult:
    """Compute full CAN SLIM analysis and return a CANSLIMResult."""

    company_name = info.get("longName") or info.get("shortName", ticker)

    # Score each letter
    c = _score_C(info, quarterly_income, quarterly_cashflow)
    a = _score_A(info, income_stmts)
    n = _score_N(info, price_history)
    s = _score_S(info)
    l = _score_L(price_history, spy_history)
    i = _score_I(info, institutional_holders)

    letter_scores = {"C": c, "A": a, "N": n, "S": s, "L": l, "I": i}

    # Composite (M excluded)
    composite = sum(ls.score * ls.weight for ls in letter_scores.values())
    composite = round(composite, 1)

    # Market direction gatekeeper
    market_direction, market_metrics = _assess_market(spy_history)

    # Buy point
    buy_point = _detect_buy_point(info, price_history)

    # Red flags
    red_flags = []
    if a.score < 40:
        red_flags.append("Weak annual earnings growth — does not meet CAN SLIM criteria")
    if c.score < 40:
        red_flags.append("Weak current quarterly earnings — acceleration missing")
    if l.score < 40:
        red_flags.append("Stock is a laggard, not a leader — RS percentile below 70th")
    if market_direction == "market_correction":
        red_flags.append("Market in correction — high risk of failed breakouts")

    recommendation = _decide(composite, market_direction, buy_point, red_flags)

    return CANSLIMResult(
        ticker=ticker,
        company_name=company_name,
        composite_score=composite,
        composite_label=_composite_label(composite),
        letter_scores=letter_scores,
        market_direction=market_direction,
        market_metrics=market_metrics,
        buy_point=buy_point,
        recommendation=recommendation,
        red_flags=red_flags,
        investor_fit=_INVESTOR_FIT,
    )
