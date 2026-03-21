"""
Claude-powered qualitative scoring for Fisher Points 2, 3, 4, 7-9, 11-12, 14-15.
Each function takes pre-fetched text and quantitative context, calls Claude,
parses the JSON response, and returns a PointResult.
Results are cached to avoid re-scoring the same filing.
"""

import json
import re
import anthropic

from config.settings import (
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
    CLAUDE_MAX_TOKENS,
    CLAUDE_TEMPERATURE,
    CACHE_TTL_CLAUDE,
    SCORE_MAP,
)
from data import cache
from scoring.models import PointResult
from scoring import prompts


_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def _call_claude(system_prompt: str, user_prompt: str) -> dict:
    """Call Claude and parse JSON response. Retries once on parse failure."""
    client = _get_client()

    def _attempt(extra: str = "") -> str:
        msg = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=CLAUDE_MAX_TOKENS,
            temperature=CLAUDE_TEMPERATURE,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt + extra}],
        )
        return msg.content[0].text

    raw = _attempt()

    # Parse attempt 1: direct JSON
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Parse attempt 2: extract JSON object from response
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # Parse attempt 3: retry with explicit reminder
    raw2 = _attempt("\n\nIMPORTANT: Your previous response was not valid JSON. Reply with ONLY the JSON object.")
    try:
        return json.loads(raw2)
    except json.JSONDecodeError:
        pass

    # Fallback
    return {
        "score": "average",
        "rationale": "Claude response could not be parsed. Manual review recommended.",
        "key_signals": ["parse_error"],
    }


def _score_point(
    point_number: int,
    label: str,
    prompt_fn,
    ticker: str,
    company_name: str,
    ten_k: str,
    proxy: str,
    quant: str,
    cache_seed: str,
) -> PointResult:
    """Generic scorer: cache check → Claude call → PointResult."""
    cache_key = f"claude:pt{point_number}:{cache.make_hash(cache_seed, ticker)}"
    cached = cache.get(cache_key, ticker)
    if cached:
        return PointResult(
            point_number=point_number,
            label=label,
            score=cached["score"],
            numeric=SCORE_MAP.get(cached["score"], 1),
            rationale=cached["rationale"],
            key_signals=cached.get("key_signals", []),
            data_used={"source": "claude_cache"},
        )

    system_prompt, user_prompt = prompt_fn(ticker, company_name, ten_k, proxy, quant)
    result = _call_claude(system_prompt, user_prompt)

    score = result.get("score", "average")
    if score not in SCORE_MAP:
        score = "average"

    cache.set(cache_key, ticker, result, ttl=CACHE_TTL_CLAUDE)
    cache.log_request("claude", f"pt{point_number}", ticker)

    return PointResult(
        point_number=point_number,
        label=label,
        score=score,
        numeric=SCORE_MAP[score],
        rationale=result.get("rationale", ""),
        key_signals=result.get("key_signals", []),
        data_used={"source": "claude_live"},
    )


# ── Public scoring functions ───────────────────────────────────────────────────

def score_point_2(ticker, company_name, ten_k, xbrl_facts, cache_seed) -> PointResult:
    rnd_data = xbrl_facts.get("ResearchAndDevelopmentExpense", [])
    revenues = xbrl_facts.get("RevenueFromContractWithCustomerExcludingAssessedTax",
                              xbrl_facts.get("Revenues", []))
    quant_lines = []
    if rnd_data and revenues:
        for r, v in zip(rnd_data[:3], revenues[:3]):
            rev = v.get("val", 0)
            rnd = r.get("val", 0)
            if rev > 0:
                quant_lines.append(f"  {r.get('end','?')}: R&D ${rnd/1e6:.0f}M = {rnd/rev:.1%} of revenue")
    quant = "R&D as % of Revenue (most recent 3 years):\n" + "\n".join(quant_lines) if quant_lines else ""
    return _score_point(2, "Innovation Drive", prompts.build_prompt_2,
                        ticker, company_name, ten_k, "", quant, cache_seed)


def score_point_3(ticker, company_name, ten_k, xbrl_facts, cache_seed) -> PointResult:
    rnd_data = xbrl_facts.get("ResearchAndDevelopmentExpense", [])
    revenues = xbrl_facts.get("RevenueFromContractWithCustomerExcludingAssessedTax",
                              xbrl_facts.get("Revenues", []))
    quant_lines = []
    for r in rnd_data[:5]:
        quant_lines.append(f"  {r.get('end','?')}: R&D expense ${r.get('val',0)/1e6:.0f}M")
    rev_per_rnd = []
    for r, v in zip(rnd_data[:3], revenues[:3]):
        rnd = r.get("val", 0)
        rev = v.get("val", 0)
        if rnd > 0:
            rev_per_rnd.append(f"  {r.get('end','?')}: ${rev/rnd:.1f} revenue per R&D dollar")
    quant = ("R&D Expense (5yr):\n" + "\n".join(quant_lines) +
             "\nRevenue per R&D Dollar:\n" + "\n".join(rev_per_rnd)) if quant_lines else ""
    return _score_point(3, "R&D Effectiveness", prompts.build_prompt_3,
                        ticker, company_name, ten_k, "", quant, cache_seed)


def score_point_4(ticker, company_name, ten_k, key_metrics, cache_seed) -> PointResult:
    quant_lines = []
    for m in key_metrics[:3]:
        rpe = m.get("revenuePerEmployee", 0)
        if rpe:
            quant_lines.append(f"  {m.get('date','?')}: Revenue/Employee ${rpe/1e3:.0f}K")
    quant = "Revenue per Employee:\n" + "\n".join(quant_lines) if quant_lines else ""
    return _score_point(4, "Sales Organization Quality", prompts.build_prompt_4,
                        ticker, company_name, ten_k, "", quant, cache_seed)


def score_point_7(ticker, company_name, ten_k, efts_counts, cache_seed) -> PointResult:
    quant = (
        f"EFTS filing search results (last 3 years):\n"
        f"  Labor dispute / strike / NLRB hits (10-K): {efts_counts.get('labor_dispute', 0)}\n"
        f"  Executive departure 8-K hits: {efts_counts.get('exec_departure', 0)}"
    )
    return _score_point(7, "Labor & Personnel Relations", prompts.build_prompt_7,
                        ticker, company_name, ten_k, "", quant, cache_seed)


def score_point_8(ticker, company_name, ten_k, proxy, efts_counts, cache_seed) -> PointResult:
    quant = (
        f"EFTS filing search results (last 3 years):\n"
        f"  Executive departure 8-K hits: {efts_counts.get('exec_departure', 0)}"
    )
    return _score_point(8, "Executive Relations", prompts.build_prompt_8,
                        ticker, company_name, ten_k, proxy, quant, cache_seed)


def score_point_9(ticker, company_name, ten_k, proxy, cache_seed) -> PointResult:
    return _score_point(9, "Management Depth", prompts.build_prompt_9,
                        ticker, company_name, ten_k, proxy, "", cache_seed)


def score_point_11(ticker, company_name, ten_k, cache_seed) -> PointResult:
    return _score_point(11, "Industry Characteristics", prompts.build_prompt_11,
                        ticker, company_name, ten_k, "", "", cache_seed)


def score_point_12(ticker, company_name, ten_k, key_metrics, cache_seed) -> PointResult:
    quant_lines = []
    for m in key_metrics[:3]:
        capex = m.get("capexPerShare", 0)
        if capex:
            quant_lines.append(f"  {m.get('date','?')}: CapEx/Share ${capex:.2f}")
    quant = "CapEx Per Share:\n" + "\n".join(quant_lines) if quant_lines else ""
    return _score_point(12, "Long-Term Outlook", prompts.build_prompt_12,
                        ticker, company_name, ten_k, "", quant, cache_seed)


def score_point_14(ticker, company_name, ten_k, efts_counts, cache_seed) -> PointResult:
    quant = (
        f"EFTS filing search results (last 3 years):\n"
        f"  Restatement filings: {efts_counts.get('restatement', 0)}"
    )
    return _score_point(14, "Management Candor", prompts.build_prompt_14,
                        ticker, company_name, ten_k, "", quant, cache_seed)


def score_point_15(ticker, company_name, ten_k, proxy, efts_counts, cache_seed) -> PointResult:
    quant = (
        f"EFTS filing search results (last 3 years):\n"
        f"  SEC/DOJ investigation 8-K hits: {efts_counts.get('sec_investigation', 0)}\n"
        f"  Related-party transaction (DEF 14A) hits: {efts_counts.get('related_party', 0)}\n"
        f"  Restatement filings: {efts_counts.get('restatement', 0)}"
    )
    return _score_point(15, "Management Integrity", prompts.build_prompt_15,
                        ticker, company_name, ten_k, proxy, quant, cache_seed)


def generate_thesis(ticker: str, company_name: str, results) -> str:
    """Generate a 3-5 sentence investment thesis from the scored results."""
    lines = [f"Point {r.point_number} ({r.label}): {r.score.upper()} — {r.rationale}" for r in results]
    summary = "\n".join(lines)

    system, user = prompts.build_synthesis_prompt(ticker, company_name, summary)
    result = _call_claude(system, user)
    return result.get("thesis", "Thesis generation failed — review individual point scores above.")
