"""
Aggregates all 15 PointResults into an EvalSummary with a verdict.
"""

from config.settings import SCORE_MAP, CRITICAL_POINTS, INVEST_THRESHOLD, WATCHLIST_THRESHOLD
from scoring.models import PointResult, EvalSummary


def aggregate(ticker: str, company_name: str, results: list[PointResult]) -> EvalSummary:
    total = sum(r.numeric for r in results)
    max_score = 2 * len(results)
    ratio = total / max_score if max_score > 0 else 0.0

    critical_weak = [
        r.point_number for r in results
        if r.point_number in CRITICAL_POINTS and r.score == "weak"
    ]

    if ratio >= INVEST_THRESHOLD and not critical_weak:
        verdict = "BUY / ACCUMULATE"
    elif ratio >= WATCHLIST_THRESHOLD:
        verdict = "WATCHLIST"
    else:
        verdict = "PASS"

    return EvalSummary(
        ticker=ticker,
        company_name=company_name,
        results=results,
        total=total,
        max_score=max_score,
        ratio=ratio,
        verdict=verdict,
        critical_weak=critical_weak,
    )
