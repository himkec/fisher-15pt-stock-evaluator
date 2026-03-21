"""
Claude prompt templates for all 10 qualitative Fisher points.
Each build_prompt_N() returns a (system_prompt, user_prompt) tuple.
"""

SYSTEM_BASE = """You are a securities analyst evaluating a company against Philip Fisher's investment framework.

CRITICAL RULES:
1. Respond with ONLY valid JSON — no text before or after the JSON object.
2. Use exactly this schema:
   {{"score": "strong"|"average"|"weak", "rationale": "<2-3 sentences citing specific evidence>", "key_signals": ["<signal 1>", "<signal 2>", "<signal 3>"]}}
3. Base your score ONLY on the evidence provided. Do not invent facts.
4. If evidence is sparse, lean toward "average" rather than "weak".
5. Cite specific phrases, numbers, or disclosures from the text when possible.

Scoring rubric for this specific point is provided in each prompt."""


def _user_block(ticker: str, company_name: str, point_num: int, fisher_question: str,
                ten_k_excerpt: str, proxy_excerpt: str, quant_context: str) -> str:
    return f"""Company: {ticker} — {company_name}
Fisher Point {point_num}: {fisher_question}

=== 10-K EXCERPT (most recent annual report) ===
{ten_k_excerpt[:60_000] if ten_k_excerpt else "(not available)"}

=== PROXY STATEMENT EXCERPT (DEF 14A) ===
{proxy_excerpt[:20_000] if proxy_excerpt else "(not available)"}

=== QUANTITATIVE CONTEXT ===
{quant_context if quant_context else "(no quantitative signals provided)"}

Based solely on the evidence above, score this company on Fisher Point {point_num}. Reply with JSON only."""


# ── Point 2 — Innovation Drive ────────────────────────────────────────────────

def build_prompt_2(ticker, company_name, ten_k, proxy, quant):
    system = SYSTEM_BASE + """

Point 2 Rubric — Ongoing Innovation Drive:
  strong  = 10-K describes a clear product pipeline with named future initiatives; R&D spending is growing as % of revenue; language explicitly commits to innovation beyond current products.
  average = Some pipeline discussion but vague; R&D stable but not growing; incremental rather than transformative innovation signals.
  weak    = No pipeline language; R&D declining as % of revenue; 10-K focuses only on defending existing products."""
    user = _user_block(ticker, company_name, 2,
                       "Does management have determination to continue developing products to increase total sales potential?",
                       ten_k, proxy, quant)
    return system, user


# ── Point 3 — R&D Effectiveness ──────────────────────────────────────────────

def build_prompt_3(ticker, company_name, ten_k, proxy, quant):
    system = SYSTEM_BASE + """

Point 3 Rubric — R&D Effectiveness:
  strong  = R&D spending is rational vs peers AND the 10-K shows tangible outputs (new products, patents, process improvements with commercial impact); R&D-to-revenue dollar is efficient.
  average = R&D investment present but outputs are vague or mixed; some new products but unclear commercial impact.
  weak    = R&D is below-industry or shrinking; no evidence of commercial outputs; R&D described as maintenance only."""
    user = _user_block(ticker, company_name, 3,
                       "How effective are the company's R&D efforts relative to its size?",
                       ten_k, proxy, quant)
    return system, user


# ── Point 4 — Sales Organization ─────────────────────────────────────────────

def build_prompt_4(ticker, company_name, ten_k, proxy, quant):
    system = SYSTEM_BASE + """

Point 4 Rubric — Sales Organization Quality:
  strong  = 10-K describes structured, professional sales force with clear training programs; multi-channel distribution; revenue/employee trend improving; low customer concentration.
  average = Sales force described but generic; some channel diversity; revenue metrics acceptable but not exceptional.
  weak    = Thin sales force description; high customer concentration risk; weak or declining revenue efficiency metrics."""
    user = _user_block(ticker, company_name, 4,
                       "Does the company have an above-average sales organization?",
                       ten_k, proxy, quant)
    return system, user


# ── Point 7 — Labor Relations ─────────────────────────────────────────────────

def build_prompt_7(ticker, company_name, ten_k, proxy, quant):
    system = SYSTEM_BASE + """

Point 7 Rubric — Labor & Personnel Relations:
  strong  = 10-K Human Capital section describes specific programs (training, benefits, engagement); no EFTS hits for labor disputes; Risk Factors do not highlight material workforce risk.
  average = Some workforce programs mentioned; minor or historical labor issues; moderate Risk Factor language.
  weak    = EFTS hits for strikes, NLRB actions, or significant layoffs; Risk Factors flag material labor risk; no meaningful Human Capital disclosure."""
    user = _user_block(ticker, company_name, 7,
                       "Does the company have outstanding labor and personnel relations?",
                       ten_k, proxy, quant)
    return system, user


# ── Point 8 — Executive Relations ────────────────────────────────────────────

def build_prompt_8(ticker, company_name, ten_k, proxy, quant):
    system = SYSTEM_BASE + """

Point 8 Rubric — Executive Relations:
  strong  = Proxy shows compensation tied to multi-year metrics; officer bios reveal internal promotions; low C-suite turnover signals in EFTS; leadership team is broad and tenured.
  average = Compensation mostly aligned but some short-term bonus heavy; mixed internal/external hiring; occasional executive changes.
  weak    = EFTS shows multiple C-suite departures in 2-3 years; compensation heavily short-term; outsider-heavy leadership with no tenure; proxy reveals governance concerns."""
    user = _user_block(ticker, company_name, 8,
                       "Does the company have outstanding executive relations?",
                       ten_k, proxy, quant)
    return system, user


# ── Point 9 — Management Depth ────────────────────────────────────────────────

def build_prompt_9(ticker, company_name, ten_k, proxy, quant):
    system = SYSTEM_BASE + """

Point 9 Rubric — Depth of Management:
  strong  = 10-K/proxy lists a broad, experienced leadership team across functions; no single-founder dependency language; succession planning explicitly addressed; delegation is evident from org descriptions.
  average = Adequate management team but some key-person risk signals; succession not explicitly discussed but team appears functional.
  weak    = Thin officer list; founder or single-person dependency language in Risk Factors; no succession planning evidence; highly centralized decision-making implied."""
    user = _user_block(ticker, company_name, 9,
                       "Does the company have depth to its management?",
                       ten_k, proxy, quant)
    return system, user


# ── Point 11 — Industry Characteristics ──────────────────────────────────────

def build_prompt_11(ticker, company_name, ten_k, proxy, quant):
    system = SYSTEM_BASE + """

Point 11 Rubric — Industry Characteristics & Competitive Edge:
  strong  = 10-K Business section describes durable, structural advantages specific to the company's industry (network effects, proprietary data, regulatory moats, high switching costs); advantages are described as hard to replicate.
  average = Some competitive differentiation exists but is not clearly durable; moderate switching costs or partial network effects.
  weak    = Company competes in a commodity-like environment with no described structural edge; competition section emphasizes price competition; no moat language."""
    user = _user_block(ticker, company_name, 11,
                       "Are there industry-specific aspects that give the company an important competitive edge?",
                       ten_k, proxy, quant)
    return system, user


# ── Point 12 — Long-Term Outlook ─────────────────────────────────────────────

def build_prompt_12(ticker, company_name, ten_k, proxy, quant):
    system = SYSTEM_BASE + """

Point 12 Rubric — Long-Term vs Short-Term Outlook:
  strong  = MD&A uses multi-year language for investment plans; CapEx growing as % of revenue; management discusses stakeholder relationships (customers, suppliers, employees) as long-term investments; earnings guidance avoids quarter-by-quarter obsession.
  average = Mixed signals — some long-term investment language alongside quarterly focus; CapEx stable.
  weak    = MD&A language dominated by quarterly comparisons and short-term EPS; CapEx declining; stakeholder language is absent or formulaic."""
    user = _user_block(ticker, company_name, 12,
                       "Does the company have a long-range outlook in regard to profits?",
                       ten_k, proxy, quant)
    return system, user


# ── Point 14 — Management Candor ─────────────────────────────────────────────

def build_prompt_14(ticker, company_name, ten_k, proxy, quant):
    system = SYSTEM_BASE + """

Point 14 Rubric — Management Candor with Investors:
  strong  = MD&A acknowledges specific challenges by name with quantified impacts; past mistakes are discussed with lessons learned; no restatement history; Risk Factors are specific and company-specific (not just boilerplate).
  average = Some challenge disclosure but vague; Risk Factors partially generic; no restatements but communication is somewhat spin-heavy.
  weak    = MD&A is purely promotional; Risk Factors are entirely boilerplate; any restatement history; management has pattern of blaming externals for underperformance."""
    user = _user_block(ticker, company_name, 14,
                       "Does management talk freely to investors about its affairs when times are good AND bad?",
                       ten_k, proxy, quant)
    return system, user


# ── Point 15 — Management Integrity ──────────────────────────────────────────

def build_prompt_15(ticker, company_name, ten_k, proxy, quant):
    system = SYSTEM_BASE + """

Point 15 Rubric — Management Integrity:
  strong  = Proxy shows no material related-party transactions (or any disclosed at clearly arm's-length terms); 10-K legal proceedings section is clean; no EFTS hits for SEC/DOJ investigations; insider compensation is fair and aligned with shareholder returns.
  average = Minor related-party disclosures with reasonable explanation; small legal matters; no major investigations; compensation mostly aligned.
  weak    = Material related-party transactions that benefit insiders; ongoing SEC/DOJ actions; excessive executive perks disclosed; compensation dramatically disconnected from performance; any pattern of undisclosed conflicts."""
    user = _user_block(ticker, company_name, 15,
                       "Does the company have management of unquestionable integrity?",
                       ten_k, proxy, quant)
    return system, user


# ── Synthesis prompt (final verdict summary) ──────────────────────────────────

def build_synthesis_prompt(ticker: str, company_name: str, scorecard_summary: str) -> tuple[str, str]:
    system = """You are a senior investment analyst writing a concise investment thesis.
Reply with ONLY valid JSON using this schema:
{"thesis": "<3-5 sentence investment thesis summarizing the strongest points, the weakest points, and the overall verdict>"}"""

    user = f"""Company: {ticker} — {company_name}

Fisher 15-Point Scorecard Summary:
{scorecard_summary}

Write a 3-5 sentence investment thesis. Reference the strongest and weakest Fisher points by number. Be direct. Reply with JSON only."""
    return system, user
