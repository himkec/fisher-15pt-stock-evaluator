"""
Philip Fisher Stock Evaluator
Multi-framework stock analysis: Fisher 15-Point, QAFP, CAN SLIM, and more coming.

Run:  streamlit run app.py --server.headless true --server.port 8502
"""

import time
import streamlit as st
from data import cache
from data import fmp_client, edgar_client
from data.fmp_client import FMPRateLimitError, FMPError
from data.edgar_client import EDGARError
from scoring import quantitative as quant
from scoring import qualitative as qual
from scoring import aggregator
from scoring.models import PointResult, EvalSummary
from scoring.qafp import run_qafp
from scoring.qafp_models import QAFPResult
from scoring.canslim import run_canslim
from scoring.canslim_models import CANSLIMResult
from scoring.fundamental import run_fundamental
from scoring.fundamental_models import FundamentalResult
from scoring.intrinsic_value import run_intrinsic_value
from scoring.intrinsic_value_models import IntrinsicValueResult
from ui import components
from config.settings import FMP_DAILY_LIMIT, ANTHROPIC_API_KEY

st.set_page_config(
    page_title="Stock Evaluator",
    page_icon="📊",
    layout="wide",
)

# ── Analysis group / sub-analysis registry ─────────────────────────────────────

ANALYSIS_GROUPS = [
    # ── Row 1: implemented ────────────────────────────────────────────────────
    {
        "id": "qualitative_growth",
        "name": "Qualitative Growth Frameworks",
        "description": "Deep business quality, management & growth runway",
        "implemented": True,
        "analyses": [
            {"id": "fisher", "name": "Fisher 15-Point Checklist", "implemented": True},
        ],
    },
    {
        "id": "quality_qafp",
        "name": "Quality & QARP / QAFP",
        "description": "Quality companies at a reasonable or fair price",
        "implemented": True,
        "analyses": [
            {"id": "qafp", "name": "QAFP Analysis", "implemented": True},
        ],
    },
    {
        "id": "momentum",
        "name": "Momentum / Growth-Trading",
        "description": "High-growth leaders with earnings & price momentum",
        "implemented": True,
        "analyses": [
            {"id": "canslim", "name": "CAN SLIM", "implemented": True},
        ],
    },
    # ── Row 2: coming soon ────────────────────────────────────────────────────
    {
        "id": "fundamental",
        "name": "Fundamental Analysis",
        "description": "Intrinsic value & long-term earning power",
        "implemented": True,
        "analyses": [
            {"id": "fundamental", "name": "Deep Fundamental Analysis", "implemented": True},
        ],
    },
    {
        "id": "intrinsic_value",
        "name": "Intrinsic Value / Valuation Models",
        "description": "DCF, DDM, Residual Income, Graham Number — football field view",
        "implemented": True,
        "analyses": [
            {"id": "dcf_fcf",       "name": "FCF DCF Model",              "implemented": True},
            {"id": "ddm",           "name": "Dividend Discount Models",   "implemented": True},
            {"id": "rim",           "name": "Residual Income Model",      "implemented": True},
            {"id": "graham_number", "name": "Graham Number",              "implemented": True},
        ],
    },
    {
        "id": "technical",
        "name": "Technical Analysis",
        "description": "Price patterns, moving averages, breakouts",
        "implemented": False,
        "analyses": [
            {"id": "chart_patterns",    "name": "Chart Patterns",         "implemented": False},
            {"id": "moving_averages",   "name": "Moving Averages & Trend","implemented": False},
            {"id": "support_resistance","name": "Support & Resistance",   "implemented": False},
        ],
    },
    # ── Row 3: coming soon ────────────────────────────────────────────────────
    {
        "id": "sentiment",
        "name": "Sentiment & Flow Analysis",
        "description": "News, options flow & crowd psychology",
        "implemented": False,
        "analyses": [
            {"id": "news_sentiment", "name": "News Sentiment",  "implemented": False},
            {"id": "options_flow",   "name": "Options Flow",    "implemented": False},
            {"id": "put_call_ratio", "name": "Put / Call Ratio","implemented": False},
        ],
    },
    {
        "id": "quant_factor",
        "name": "Quant / Factor Models",
        "description": "Multifactor screens & systematic ranking",
        "implemented": False,
        "analyses": [
            {"id": "multifactor", "name": "Multifactor Model",  "implemented": False},
            {"id": "smart_beta",  "name": "Smart-Beta Screens", "implemented": False},
        ],
    },
    {
        "id": "income_dividend",
        "name": "Income / Dividend Analysis",
        "description": "Dividend growth, yield & payout sustainability",
        "implemented": False,
        "analyses": [
            {"id": "dividend_growth", "name": "Dividend Growth Investing",   "implemented": False},
            {"id": "payout_analysis", "name": "Payout & Coverage Analysis",  "implemented": False},
        ],
    },
]

VERDICT_ICON = {
    "BUY / ACCUMULATE": "✅",
    "WATCHLIST":        "⚠️",
    "PASS":             "❌",
    "—":                "🔍",
}

# ── Investor goals ─────────────────────────────────────────────────────────────
# Each goal maps to a set of analysis IDs (implemented or not).
# `analyses` = IDs that will be auto-checked; non-implemented ones are ignored
# at runtime but kept here so they auto-select when implemented later.

INVESTOR_GOALS = [
    {
        "id": "long_term_growth",
        "label": "Long-Term Growth",
        "horizon": "5–10+ years",
        "description": (
            "Identify exceptional businesses with durable competitive advantages, "
            "deep management quality, and long R&D runways — and hold them for years. "
            "Popularised by Philip Fisher."
        ),
        "typical_users": "Concentrated growth investors, Fisher-style, high-conviction managers",
        "analyses": ["fisher", "qafp", "fundamental"],
        "note": None,
    },
    {
        "id": "quality_fair_price",
        "label": "Quality at a Fair Price (QAFP)",
        "horizon": "3–7 years",
        "description": (
            "Buffett-lite approach: screen for high-quality businesses (ROIC, FCF, margins) "
            "then confirm a fair — not rock-bottom — valuation. Steady compounding over time."
        ),
        "typical_users": "Quality-factor investors, QARP / QAFP practitioners, active fund managers",
        "analyses": ["qafp", "fisher", "fundamental"],
        "note": None,
    },
    {
        "id": "growth_momentum",
        "label": "Growth & Momentum",
        "horizon": "3–18 months",
        "description": (
            "Find market leaders with accelerating earnings and strong price momentum, "
            "then buy on confirmed breakouts with tight stop-loss rules (O'Neil / CAN SLIM)."
        ),
        "typical_users": "CAN SLIM followers, O'Neil-style traders, momentum funds",
        "analyses": ["canslim"],
        "note": "Technical analysis tools will complement this style when available.",
    },
    {
        "id": "deep_value",
        "label": "Deep Value / Contrarian",
        "horizon": "2–5 years",
        "description": (
            "Seek stocks trading well below intrinsic value using DCF and Graham formulas. "
            "QAFP valuation scoring is the closest available tool today."
        ),
        "typical_users": "Graham / Schloss-style investors, contrarian and event-driven funds",
        "analyses": ["qafp", "fundamental", "dcf_fcf", "rim", "graham_number"],
        "note": None,
    },
    {
        "id": "income_dividend",
        "label": "Income & Dividend Growth",
        "horizon": "5+ years",
        "description": (
            "Build portfolios of reliable dividend payers with growing, sustainable payouts. "
            "QAFP balance-sheet and FCF quality scoring is the best available proxy today."
        ),
        "typical_users": "Income investors, retirees, dividend-growth funds",
        "analyses": ["qafp", "dividend_growth", "payout_analysis"],
        "note": "Dividend growth and payout-coverage tools are coming soon.",
    },
    {
        "id": "active_trading",
        "label": "Active / Swing Trading",
        "horizon": "Days to weeks",
        "description": (
            "Time entries and exits using price patterns, moving averages, support / resistance, "
            "and sentiment. CAN SLIM provides momentum and buy-point context in the interim."
        ),
        "typical_users": "Day and swing traders, short-term momentum players",
        "analyses": ["canslim", "chart_patterns", "moving_averages", "news_sentiment"],
        "note": "Technical analysis and sentiment tools are coming soon for this style.",
    },
    {
        "id": "quant_systematic",
        "label": "Quantitative / Systematic",
        "horizon": "Rebalance quarterly–annually",
        "description": (
            "Rank and select stocks using multifactor models (value, quality, momentum, low vol). "
            "QAFP quality scoring and CAN SLIM relative-strength are the closest available tools."
        ),
        "typical_users": "Quant funds, smart-beta investors, data-driven systematic traders",
        "analyses": ["qafp", "canslim", "multifactor", "smart_beta"],
        "note": "Multifactor models and systematic screens are coming soon.",
    },
    {
        "id": "full_due_diligence",
        "label": "Full Due Diligence",
        "horizon": "Any",
        "description": (
            "Run every available framework for a comprehensive, multi-lens view of the stock "
            "before a major investment decision."
        ),
        "typical_users": "Professional analysts, portfolio managers, serious individual investors",
        "analyses": ["fisher", "qafp", "canslim", "fundamental", "dcf_fcf", "ddm", "rim", "graham_number"],
        "note": None,
    },
]

# Pre-build lookup: goal_id → set of analysis IDs
_GOAL_ANALYSES: dict[str, set[str]] = {
    g["id"]: set(g["analyses"]) for g in INVESTOR_GOALS
}

# All implemented analysis IDs (single source of truth)
_ALL_IMPLEMENTED: set[str] = {
    a["id"]
    for g in ANALYSIS_GROUPS
    for a in g["analyses"]
    if a["implemented"]
}


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _save_evaluation(
    ticker: str,
    company_name: str,
    summary: EvalSummary | None,
    thesis: str,
    qafp: QAFPResult | None,
    canslim: CANSLIMResult | None,
    fundamental: FundamentalResult | None = None,
    intrinsic_value: IntrinsicValueResult | None = None,
) -> None:
    # Always persist a history-index entry so the ticker appears in the sidebar.
    if summary is None:
        summary = EvalSummary(
            ticker=ticker,
            company_name=company_name,
            results=[],
            total=0, max_score=0, ratio=0.0,
            verdict="—",
            critical_weak=[],
        )
    data = summary.to_dict()
    data["thesis"] = thesis
    cache.set("eval:summary", ticker, data, ttl=60 * 60 * 24 * 30)
    if qafp:
        cache.save_qafp(ticker, qafp.to_dict())
    if canslim:
        cache.save_canslim(ticker, canslim.to_dict())
    if fundamental:
        cache.save_fundamental(ticker, fundamental.to_dict())
    if intrinsic_value:
        cache.save_intrinsic_value(ticker, intrinsic_value.to_dict())


def _load_evaluation(
    ticker: str,
) -> tuple:
    data = cache.get("eval:summary", ticker)
    if not data:
        return None, None, None, None, None, None
    thesis = data.pop("thesis", "")
    summary = EvalSummary.from_dict(data)

    qafp_data = cache.load_qafp(ticker)
    qafp = QAFPResult.from_dict(qafp_data) if qafp_data else None
    if qafp is None:
        qafp = _try_qafp_from_cache(ticker)

    canslim_data = cache.load_canslim(ticker)
    canslim = CANSLIMResult.from_dict(canslim_data) if canslim_data else None
    if canslim is None:
        canslim = _try_canslim_from_cache(ticker)

    fund_data = cache.load_fundamental(ticker)
    fundamental = FundamentalResult.from_dict(fund_data) if fund_data else None

    iv_data = cache.load_intrinsic_value(ticker)
    intrinsic_value = IntrinsicValueResult.from_dict(iv_data) if iv_data else None

    return summary, thesis, qafp, canslim, fundamental, intrinsic_value


def _try_qafp_from_cache(ticker: str) -> QAFPResult | None:
    """Compute QAFP using only already-cached yfinance data — zero new API calls."""
    try:
        yf_info        = cache.get("yf:info", ticker)
        income_stmts   = cache.get("yf:income_stmt", ticker)
        balance_sheets = cache.get("yf:balance_sheet", ticker)
        cash_flows     = cache.get("yf:cash_flow", ticker)

        if not yf_info:        yf_info        = fmp_client.get_info(ticker)
        if not income_stmts:   income_stmts   = fmp_client.get_income_statements(ticker)
        if not balance_sheets: balance_sheets = fmp_client.get_balance_sheets(ticker)
        if not cash_flows:     cash_flows     = fmp_client.get_cash_flow_statements(ticker)

        if not yf_info or not income_stmts:
            return None

        result = run_qafp(ticker, yf_info, income_stmts, balance_sheets or [], cash_flows or [])
        cache.save_qafp(ticker, result.to_dict())
        return result
    except Exception:
        return None


def _try_canslim_from_cache(ticker: str) -> CANSLIMResult | None:
    """Compute CAN SLIM using only already-cached yfinance data — zero new API calls."""
    try:
        yf_info      = cache.get("yf:info", ticker) or fmp_client.get_info(ticker)
        income_stmts = cache.get("yf:income_stmt", ticker) or fmp_client.get_income_statements(ticker)
        quarterly    = cache.get("yf:quarterly", ticker) or fmp_client.get_quarterly_financials(ticker)
        price_data   = cache.get("yf:price_history:2y", ticker) or fmp_client.get_price_history(ticker)
        inst_holders = cache.get("yf:inst_holders", ticker)
        if inst_holders is None:
            inst_holders = fmp_client.get_institutional_holders(ticker)
        spy_data = cache.get("yf:spy_history:2y", "SPY") or fmp_client.get_spy_history()

        if not yf_info or not income_stmts:
            return None

        result = run_canslim(
            ticker, yf_info, income_stmts,
            quarterly.get("income", []), quarterly.get("cashflow", []),
            price_data.get("prices", []), inst_holders or [],
            spy_data.get("prices", []),
        )
        cache.save_canslim(ticker, result.to_dict())
        return result
    except Exception:
        return None


# ── Render results ────────────────────────────────────────────────────────────

def _render(
    summary: EvalSummary | None,
    thesis: str,
    qafp: QAFPResult | None = None,
    canslim: CANSLIMResult | None = None,
    fundamental: FundamentalResult | None = None,
    intrinsic_value: IntrinsicValueResult | None = None,
    from_cache: bool = False,
) -> None:
    if from_cache:
        st.info("Loaded from history — no API calls made.")

    # Always show ticker header if we have any result
    _hdr = summary or qafp or canslim or fundamental or intrinsic_value
    if _hdr:
        st.divider()
        if summary:
            st.markdown(f"## {summary.ticker} &nbsp; `{summary.company_name}`")
        else:
            st.markdown(f"## {_hdr.ticker} &nbsp; `{_hdr.company_name}`")

    # Fisher 15-Point section (only when results are present)
    if summary and summary.results:
        col_left, col_right = st.columns([2, 1])
        with col_left:
            components.verdict_banner(summary)
        if thesis:
            components.thesis_box(thesis)

        c1, c2 = st.columns([1, 1])
        with c1:
            st.markdown("#### Scorecard")
            components.scorecard_table(summary.results)
        with c2:
            st.markdown("#### Radar Chart")
            components.radar_chart(summary.results)

        components.point_expanders(summary.results)

    if qafp:
        components.qafp_section(qafp)

    if canslim:
        components.canslim_section(canslim)

    if fundamental:
        components.fundamental_section(fundamental)

    if intrinsic_value:
        components.intrinsic_value_section(intrinsic_value)


# ── Full evaluation pipeline ──────────────────────────────────────────────────

def _run_evaluation(ticker: str, selected: set[str]) -> None:
    run_fisher      = "fisher"      in selected
    run_qafp        = "qafp"        in selected
    run_canslim     = "canslim"     in selected
    do_fundamental  = "fundamental" in selected
    iv_methods      = {"dcf_fcf", "ddm", "rim", "graham_number"} & selected
    do_intrinsic    = bool(iv_methods)

    if not any([run_fisher, run_qafp, run_canslim, do_fundamental, do_intrinsic]):
        st.warning("Select at least one analysis to run.")
        return

    progress = st.progress(0, text="Starting evaluation...")
    status   = st.empty()
    errors: list[str] = []

    # ── Step 1: core financial data (all analyses need this) ──────────────────
    status.info("Fetching financial statements from Yahoo Finance...")
    try:
        profile        = fmp_client.get_profile(ticker)
        company_name   = profile.get("companyName", ticker)
        sector         = profile.get("sector", "default")
        income_stmts   = fmp_client.get_income_statements(ticker)
        balance_sheets = fmp_client.get_balance_sheets(ticker)
        cash_flows     = fmp_client.get_cash_flow_statements(ticker)
        ratios         = fmp_client.get_ratios(ticker)
        key_metrics    = fmp_client.get_key_metrics(ticker)
        yf_info        = fmp_client.get_info(ticker)
    except FMPRateLimitError as e:
        st.error(str(e))
        return
    except FMPError as e:
        st.error(f"Data error: {e}")
        return

    progress.progress(15, text="Financial data loaded.")

    # ── Step 2: EDGAR filings (Fisher only) ───────────────────────────────────
    cik         = None
    ten_k_text  = ""
    proxy_text  = ""
    xbrl_facts  = {}
    efts_counts = {}
    cache_seed  = ticker
    peers_ratios = []

    if run_fisher:
        status.info("Fetching SEC filings from EDGAR...")
        try:
            peers_ratios = fmp_client.get_peers_ratios(ticker)
        except Exception:
            pass

        if ANTHROPIC_API_KEY:
            try:
                cik         = edgar_client.resolve_cik(ticker)
                submissions = edgar_client.get_submissions(cik)
                ten_k_text  = edgar_client.get_latest_10k_text(ticker, cik, submissions)
                proxy_text  = edgar_client.get_latest_proxy_text(ticker, cik, submissions)
                xbrl_facts  = edgar_client.get_xbrl_facts(cik)
                efts_counts = edgar_client.get_efts_hit_counts(company_name)
                acc, _      = edgar_client._find_latest_accession(submissions, "10-K")
                if acc:
                    cache_seed = f"{ticker}:{acc}"
            except EDGARError as e:
                errors.append(f"EDGAR: {e}")
                st.warning("SEC EDGAR unavailable — qualitative points will be skipped.")
        else:
            errors.append("ANTHROPIC_API_KEY not configured — qualitative points skipped.")

    progress.progress(35, text="SEC filings loaded." if run_fisher else "Data loaded.")

    # ── Step 3: Fisher quantitative scoring ───────────────────────────────────
    summary = None
    thesis  = ""

    if run_fisher:
        status.info("Scoring quantitative points (1, 5, 6, 10, 13)...")
        results: list[PointResult] = []
        results.append(quant.score_point_1(income_stmts))
        results.append(quant.score_point_5(ratios, peers_ratios, sector))
        results.append(quant.score_point_6(ratios))
        results.append(quant.score_point_10(income_stmts))
        results.append(quant.score_point_13(cash_flows, balance_sheets))
        progress.progress(50, text="Quantitative scoring complete.")

        # ── Step 4: Fisher qualitative scoring ────────────────────────────────
        qualitative_points = [
            (2,  "Innovation Drive",         lambda: qual.score_point_2(ticker, company_name, ten_k_text, xbrl_facts, cache_seed)),
            (3,  "R&D Effectiveness",        lambda: qual.score_point_3(ticker, company_name, ten_k_text, xbrl_facts, cache_seed)),
            (4,  "Sales Organization",       lambda: qual.score_point_4(ticker, company_name, ten_k_text, key_metrics, cache_seed)),
            (7,  "Labor Relations",          lambda: qual.score_point_7(ticker, company_name, ten_k_text, efts_counts, cache_seed)),
            (8,  "Executive Relations",      lambda: qual.score_point_8(ticker, company_name, ten_k_text, proxy_text, efts_counts, cache_seed)),
            (9,  "Management Depth",         lambda: qual.score_point_9(ticker, company_name, ten_k_text, proxy_text, cache_seed)),
            (11, "Industry Characteristics", lambda: qual.score_point_11(ticker, company_name, ten_k_text, cache_seed)),
            (12, "Long-Term Outlook",        lambda: qual.score_point_12(ticker, company_name, ten_k_text, key_metrics, cache_seed)),
            (14, "Management Candor",        lambda: qual.score_point_14(ticker, company_name, ten_k_text, efts_counts, cache_seed)),
            (15, "Management Integrity",     lambda: qual.score_point_15(ticker, company_name, ten_k_text, proxy_text, efts_counts, cache_seed)),
        ]

        if ANTHROPIC_API_KEY and cik:
            for i, (pt_num, pt_label, scorer) in enumerate(qualitative_points):
                pct = 50 + int((i + 1) / len(qualitative_points) * 30)
                status.info(f"Claude scoring Point {pt_num}: {pt_label}...")
                try:
                    results.append(scorer())
                except Exception as e:
                    errors.append(f"Point {pt_num}: {e}")
                    results.append(PointResult(
                        point_number=pt_num, label=pt_label,
                        score="average", numeric=1,
                        rationale=f"Scoring failed: {e}. Defaulting to average.",
                    ))
                progress.progress(pct, text=f"Qualitative: {i + 1}/{len(qualitative_points)} points scored.")
        else:
            for pt_num, pt_label, _ in qualitative_points:
                results.append(PointResult(
                    point_number=pt_num, label=pt_label,
                    score="average", numeric=1,
                    rationale="Qualitative scoring skipped — API key or EDGAR data unavailable.",
                ))

        results.sort(key=lambda r: r.point_number)

        # ── Step 5: Aggregate + thesis ─────────────────────────────────────────
        status.info("Aggregating scores and generating investment thesis...")
        summary = aggregator.aggregate(ticker, company_name, results)

        if ANTHROPIC_API_KEY:
            try:
                thesis = qual.generate_thesis(ticker, company_name, results)
            except Exception:
                thesis = "Thesis generation failed — review individual point scores above."

    progress.progress(82, text="Fisher complete." if run_fisher else "Scoring...")

    # ── Step 6: QAFP ──────────────────────────────────────────────────────────
    qafp = None
    if run_qafp:
        status.info("Running Quality at a Fair Price (QAFP) analysis...")
        try:
            qafp = run_qafp(ticker, yf_info, income_stmts, balance_sheets, cash_flows)
        except Exception as e:
            errors.append(f"QAFP analysis failed: {e}")

    # ── Step 7: CAN SLIM ──────────────────────────────────────────────────────
    canslim = None
    if run_canslim:
        status.info("Running CAN SLIM analysis...")
        try:
            quarterly_data = fmp_client.get_quarterly_financials(ticker)
            price_data     = fmp_client.get_price_history(ticker)
            inst_holders   = fmp_client.get_institutional_holders(ticker)
            spy_data       = fmp_client.get_spy_history()
            canslim = run_canslim(
                ticker, yf_info, income_stmts,
                quarterly_data.get("income", []),
                quarterly_data.get("cashflow", []),
                price_data.get("prices", []),
                inst_holders,
                spy_data.get("prices", []),
            )
        except Exception as e:
            errors.append(f"CAN SLIM analysis failed: {e}")

    # ── Step 8: Fundamental Analysis ──────────────────────────────────────────
    fundamental = None
    if do_fundamental:
        status.info("Running Deep Fundamental Analysis...")
        try:
            extended = fmp_client.get_balance_sheet_extended(ticker)
            fundamental = run_fundamental(
                ticker, company_name, sector,
                yf_info, income_stmts, balance_sheets, cash_flows, extended,
            )
        except Exception as e:
            errors.append(f"Fundamental analysis failed: {e}")

    # ── Step 9: Intrinsic Value Models ────────────────────────────────────────
    intrinsic_value = None
    if do_intrinsic:
        status.info("Running Intrinsic Value models...")
        try:
            intrinsic_value = run_intrinsic_value(
                ticker, company_name, yf_info,
                income_stmts, balance_sheets, cash_flows,
                iv_methods,
            )
        except Exception as e:
            errors.append(f"Intrinsic Value analysis failed: {e}")

    progress.progress(100, text="Complete.")
    status.empty()

    _save_evaluation(ticker, company_name, summary, thesis, qafp, canslim, fundamental, intrinsic_value)
    st.session_state.update({
        "active_ticker":         ticker,
        "active_summary":        summary,
        "active_thesis":         thesis,
        "active_qafp":           qafp,
        "active_canslim":        canslim,
        "active_fundamental":    fundamental,
        "active_intrinsic_value": intrinsic_value,
    })

    if errors:
        with st.expander("Warnings during evaluation", expanded=False):
            for err in errors:
                st.warning(err)

    _render(summary, thesis, qafp, canslim, fundamental, intrinsic_value)


# ── Home page — analysis selection ────────────────────────────────────────────

def _apply_goal_defaults(goal_id: str) -> None:
    """Set sel_* session-state keys to match the chosen goal (implemented IDs only)."""
    active = _GOAL_ANALYSES.get(goal_id, _ALL_IMPLEMENTED)
    for aid in _ALL_IMPLEMENTED:
        st.session_state[f"sel_{aid}"] = (aid in active)


def _render_home() -> None:
    # ── Handle prefill from Sector Analysis page ──────────────────────────────
    prefill_ticker   = st.session_state.pop("sa_prefill_ticker",   None)
    prefill_analyses = st.session_state.pop("sa_prefill_analyses", None)
    if prefill_ticker:
        st.session_state["home_ticker"] = prefill_ticker
        st.session_state["_applied_goal_id"] = "__sector_prefill__"
        if prefill_analyses:
            for aid in _ALL_IMPLEMENTED:
                st.session_state[f"sel_{aid}"] = aid in prefill_analyses

    st.title("📊 Stock Evaluator")
    st.markdown(
        "Enter a ticker, choose your analysis frameworks, and click **Run**. "
        "Results are cached — reload any prior analysis from the sidebar at zero API cost."
    )

    # ── Ticker input + run button ─────────────────────────────────────────────
    col_ticker, col_btn = st.columns([4, 1])
    with col_ticker:
        ticker_input = st.text_input(
            "Ticker symbol",
            value=st.session_state.get("home_ticker", ""),
            placeholder="e.g. AAPL, MSFT, NVDA",
            label_visibility="collapsed",
            key="home_ticker",
        ).upper().strip()
    with col_btn:
        analyze_btn = st.button(
            "Run Analysis", type="primary", use_container_width=True
        )

    # Auto-trigger when arriving via Sector Analysis prefill
    if prefill_ticker and prefill_analyses and ticker_input:
        selected = set(prefill_analyses) & _ALL_IMPLEMENTED
        if selected:
            st.info(
                f"Launched from Sector Analysis: **{prefill_ticker}** · "
                f"{', '.join(sorted(selected))}"
            )
            _run_evaluation(ticker_input, selected)
            return

    st.markdown("---")

    # ── Investor goal selector ────────────────────────────────────────────────
    st.markdown("#### Investor style  *(optional)*")

    goal_options = [None] + INVESTOR_GOALS        # None → "Custom"
    goal_fmt = lambda g: "— Custom selection —" if g is None else f"{g['label']}  ·  {g['horizon']}"

    selected_goal = st.selectbox(
        "investor_style_label",
        options=goal_options,
        format_func=goal_fmt,
        label_visibility="collapsed",
        key="investor_goal",
    )

    # Apply goal defaults when the selection changes (but not on manual checkbox edits)
    current_goal_id = selected_goal["id"] if selected_goal else "custom"
    if st.session_state.get("_applied_goal_id") != current_goal_id:
        st.session_state["_applied_goal_id"] = current_goal_id
        if selected_goal:
            _apply_goal_defaults(selected_goal["id"])
        else:
            # Custom → check all implemented by default
            for aid in _ALL_IMPLEMENTED:
                st.session_state.setdefault(f"sel_{aid}", True)

    # Goal description card
    if selected_goal:
        running = sorted(
            a["name"]
            for g in ANALYSIS_GROUPS
            for a in g["analyses"]
            if a["implemented"] and a["id"] in _GOAL_ANALYSES[selected_goal["id"]]
        )
        runs_md = "  ·  ".join(f"**{n}**" for n in running) if running else "_none available yet_"
        note_md = f"\n\n_{selected_goal['note']}_" if selected_goal.get("note") else ""
        st.info(
            f"{selected_goal['description']}\n\n"
            f"Typical users: *{selected_goal['typical_users']}*\n\n"
            f"Running: {runs_md}{note_md}"
        )

    st.markdown("---")

    # ── Analysis group cards ──────────────────────────────────────────────────
    st.markdown("#### Analysis frameworks")

    groups_by_row = [
        ANALYSIS_GROUPS[0:3],   # row 1 — implemented: Fisher, QAFP, CAN SLIM
        ANALYSIS_GROUPS[3:5],   # row 2 — implemented: Fundamental, Intrinsic Value
        ANALYSIS_GROUPS[5:8],   # row 3 — coming soon: Technical, Sentiment, Quant
        ANALYSIS_GROUPS[8:],    # row 4 — coming soon: Income/Dividend
    ]

    for row_idx, row_groups in enumerate(groups_by_row):
        if row_idx == 2:
            st.markdown(
                '<p style="color:#888;font-size:0.85em;margin:12px 0 4px">— Coming soon —</p>',
                unsafe_allow_html=True,
            )
        cols = st.columns(3)
        for col, group in zip(cols, row_groups):
            with col:
                with st.container(border=True):
                    if group["implemented"]:
                        st.markdown(f"**{group['name']}**")
                    else:
                        st.markdown(
                            f'<span style="color:#888"><b>{group["name"]}</b></span>',
                            unsafe_allow_html=True,
                        )
                    st.caption(group["description"])

                    for analysis in group["analyses"]:
                        if analysis["implemented"]:
                            # Default True only when no goal has been applied yet
                            default_val = st.session_state.get(f"sel_{analysis['id']}", True)
                            st.checkbox(
                                analysis["name"],
                                value=default_val,
                                key=f"sel_{analysis['id']}",
                            )
                        else:
                            st.checkbox(
                                analysis["name"],
                                value=False,
                                disabled=True,
                                key=f"sel_{analysis['id']}",
                                help="Coming soon",
                            )

    st.markdown("---")

    # ── Trigger evaluation ────────────────────────────────────────────────────
    if analyze_btn:
        if not ticker_input:
            st.warning("Enter a ticker symbol to continue.")
        else:
            selected = {
                a["id"]
                for g in ANALYSIS_GROUPS
                for a in g["analyses"]
                if a["implemented"] and st.session_state.get(f"sel_{a['id']}", False)
            }
            _run_evaluation(ticker_input, selected)

    # ── Show cached results if navigated back ─────────────────────────────────
    elif "active_ticker" in st.session_state and st.session_state.get("active_summary") is not None:
        _render(
            st.session_state["active_summary"],
            st.session_state.get("active_thesis", ""),
            st.session_state.get("active_qafp"),
            st.session_state.get("active_canslim"),
            st.session_state.get("active_fundamental"),
            st.session_state.get("active_intrinsic_value"),
        )


# ── Sidebar — history ─────────────────────────────────────────────────────────

def _render_sidebar() -> None:
    st.sidebar.title("History")

    history = cache.list_analyzed_tickers()
    if history:
        for entry in history:
            icon  = VERDICT_ICON.get(entry["verdict"], "🔍")
            pct   = int(entry["ratio"] * 100)
            ts    = time.strftime("%b %d", time.localtime(entry["analyzed_at"]))
            score = f"  ·  {pct}%" if pct > 0 else ""
            label = f"{icon} {entry['ticker']}{score}  ·  {ts}"

            if st.sidebar.button(
                label,
                key=f"hist_{entry['ticker']}",
                help=entry["company_name"],
                use_container_width=True,
            ):
                summary, thesis, qafp, canslim, fundamental, intrinsic_value = _load_evaluation(entry["ticker"])
                if summary:
                    st.session_state.update({
                        "active_ticker":          entry["ticker"],
                        "active_summary":         summary,
                        "active_thesis":          thesis or "",
                        "active_qafp":            qafp,
                        "active_canslim":         canslim,
                        "active_fundamental":     fundamental,
                        "active_intrinsic_value": intrinsic_value,
                    })
                    st.rerun()
    else:
        st.sidebar.caption("No stocks analyzed yet.")

    st.sidebar.markdown("---")
    st.sidebar.markdown("**Data sources**")
    st.sidebar.markdown(
        "- Yahoo Finance — quantitative (free)\n"
        "- SEC EDGAR — filings (free)\n"
        "- Claude API — qualitative scoring"
    )

    if not ANTHROPIC_API_KEY:
        st.sidebar.error("ANTHROPIC_API_KEY not set — qualitative scoring unavailable.")

    fmp_today = cache.request_count_today("fmp")
    ticker_for_cache = st.session_state.get("home_ticker", "")
    components.api_usage_sidebar(fmp_today, FMP_DAILY_LIMIT, ticker_for_cache)


# ── Entry point ───────────────────────────────────────────────────────────────

_render_sidebar()
_render_home()
