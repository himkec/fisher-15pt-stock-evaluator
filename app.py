"""
Philip Fisher 15-Point Stock Evaluator
Phase 1 MVP — Streamlit + Claude API + yFinance + SEC EDGAR (all free)

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
from ui import components
from config.settings import FMP_DAILY_LIMIT, ANTHROPIC_API_KEY

st.set_page_config(
    page_title="Fisher 15-Point Evaluator",
    page_icon="📊",
    layout="wide",
)

VERDICT_ICON = {
    "BUY / ACCUMULATE": "✅",
    "WATCHLIST":        "⚠️",
    "PASS":             "❌",
}

# ── Persist full evaluation to SQLite ─────────────────────────────────────────

def _save_evaluation(summary: EvalSummary, thesis: str, qafp: QAFPResult | None) -> None:
    data = summary.to_dict()
    data["thesis"] = thesis
    cache.set("eval:summary", summary.ticker, data, ttl=60 * 60 * 24 * 30)
    if qafp:
        cache.save_qafp(summary.ticker, qafp.to_dict())


def _load_evaluation(ticker: str) -> tuple[EvalSummary, str, QAFPResult | None]:
    data = cache.get("eval:summary", ticker)
    if not data:
        return None, None, None
    thesis = data.pop("thesis", "")
    qafp_data = cache.load_qafp(ticker)
    qafp = QAFPResult.from_dict(qafp_data) if qafp_data else None

    # Back-fill QAFP from cached financial data (no new API calls)
    if qafp is None:
        qafp = _try_qafp_from_cache(ticker)

    return EvalSummary.from_dict(data), thesis, qafp


def _try_qafp_from_cache(ticker: str) -> QAFPResult | None:
    """Compute QAFP using only already-cached yfinance data — zero new API calls."""
    try:
        yf_info      = cache.get("yf:info", ticker)
        income_stmts = cache.get("yf:income_stmt", ticker)
        balance_sheets = cache.get("yf:balance_sheet", ticker)
        cash_flows   = cache.get("yf:cash_flow", ticker)

        # If any required data is missing from cache, fetch it silently
        if not yf_info:
            yf_info = fmp_client.get_info(ticker)
        if not income_stmts:
            income_stmts = fmp_client.get_income_statements(ticker)
        if not balance_sheets:
            balance_sheets = fmp_client.get_balance_sheets(ticker)
        if not cash_flows:
            cash_flows = fmp_client.get_cash_flow_statements(ticker)

        if not yf_info or not income_stmts:
            return None

        qafp = run_qafp(ticker, yf_info, income_stmts, balance_sheets or [], cash_flows or [])
        cache.save_qafp(ticker, qafp.to_dict())
        return qafp
    except Exception:
        return None


# ── Render results (shared between live eval and history load) ─────────────────

def _render(summary: EvalSummary, thesis: str, qafp: QAFPResult | None = None, from_cache: bool = False) -> None:
    if from_cache:
        st.info("Loaded from history — no API calls made.")
    st.divider()
    components.verdict_banner(summary)
    if thesis:
        components.thesis_box(thesis)

    col_left, col_right = st.columns([1, 1])
    with col_left:
        st.markdown("#### Scorecard")
        components.scorecard_table(summary.results)
    with col_right:
        st.markdown("#### Radar Chart")
        components.radar_chart(summary.results)

    components.point_expanders(summary.results)

    if qafp:
        components.qafp_section(qafp)


# ── Full evaluation pipeline ──────────────────────────────────────────────────

def _run_evaluation(ticker: str) -> None:
    progress = st.progress(0, text="Starting evaluation...")
    status   = st.empty()

    results     = []
    errors      = []
    ten_k_text  = ""
    proxy_text  = ""
    xbrl_facts  = {}
    efts_counts = {}
    key_metrics = []
    cache_seed  = ticker

    # Step 1 — financial data
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
        peers_ratios   = fmp_client.get_peers_ratios(ticker)
        yf_info        = fmp_client.get_info(ticker)
    except FMPRateLimitError as e:
        st.error(str(e))
        return
    except FMPError as e:
        st.error(f"Data error: {e}")
        return

    progress.progress(20, text="Financial data loaded.")

    # Step 2 — EDGAR filings
    cik = None
    if ANTHROPIC_API_KEY:
        status.info("Fetching SEC filings from EDGAR...")
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
            st.warning(f"SEC EDGAR unavailable — qualitative points will be skipped.")
    else:
        errors.append("ANTHROPIC_API_KEY not configured — qualitative points skipped.")

    progress.progress(40, text="SEC filings loaded.")

    # Step 3 — quantitative scoring
    status.info("Scoring quantitative points (1, 5, 6, 10, 13)...")
    results.append(quant.score_point_1(income_stmts))
    results.append(quant.score_point_5(ratios, peers_ratios, sector))
    results.append(quant.score_point_6(ratios))
    results.append(quant.score_point_10(income_stmts))
    results.append(quant.score_point_13(cash_flows, balance_sheets))
    progress.progress(55, text="Quantitative scoring complete.")

    # Step 4 — qualitative scoring via Claude
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
            pct = 55 + int((i + 1) / len(qualitative_points) * 35)
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

    # Step 5 — aggregate + thesis
    status.info("Aggregating scores and generating investment thesis...")
    summary = aggregator.aggregate(ticker, company_name, results)

    thesis = ""
    if ANTHROPIC_API_KEY:
        try:
            thesis = qual.generate_thesis(ticker, company_name, results)
        except Exception:
            thesis = "Thesis generation failed — review individual point scores above."

    progress.progress(100, text="Evaluation complete.")
    status.empty()

    # Step 6 — QAFP analysis
    status.info("Running Quality at a Fair Price (QAFP) analysis...")
    qafp = None
    try:
        qafp = run_qafp(ticker, yf_info, income_stmts, balance_sheets, cash_flows)
    except Exception as e:
        errors.append(f"QAFP analysis failed: {e}")

    progress.progress(100, text="Complete.")
    status.empty()

    # Persist to SQLite and session state
    _save_evaluation(summary, thesis, qafp)
    st.session_state["active_ticker"]  = ticker
    st.session_state["active_summary"] = summary
    st.session_state["active_thesis"]  = thesis
    st.session_state["active_qafp"]    = qafp

    if errors:
        with st.expander("Warnings during evaluation", expanded=False):
            for err in errors:
                st.warning(err)

    _render(summary, thesis, qafp)


# ── Sidebar ───────────────────────────────────────────────────────────────────

st.sidebar.title("📊 Fisher Evaluator")

ticker_input = st.sidebar.text_input("Ticker symbol", value="", placeholder="e.g. AAPL").upper().strip()
analyze_btn  = st.sidebar.button("Analyze", type="primary", use_container_width=True)

st.sidebar.markdown("---")

# ── History panel ─────────────────────────────────────────────────────────────

history = cache.list_analyzed_tickers()

st.sidebar.markdown("**Previously Analyzed**")
if history:
    for entry in history:
        icon    = VERDICT_ICON.get(entry["verdict"], "")
        pct     = int(entry["ratio"] * 100)
        ts      = time.strftime("%b %d", time.localtime(entry["analyzed_at"]))
        label   = f"{icon} {entry['ticker']}  ·  {pct}%  ·  {ts}"
        caption = entry["company_name"]

        if st.sidebar.button(label, key=f"hist_{entry['ticker']}", help=caption, use_container_width=True):
            summary, thesis, qafp = _load_evaluation(entry["ticker"])
            if summary:
                st.session_state["active_ticker"]  = entry["ticker"]
                st.session_state["active_summary"] = summary
                st.session_state["active_thesis"]  = thesis or ""
                st.session_state["active_qafp"]    = qafp
                st.rerun()
else:
    st.sidebar.caption("No stocks analyzed yet. Enter a ticker above and click Analyze.")

st.sidebar.markdown("---")
st.sidebar.markdown("**Data sources**")
st.sidebar.markdown("- Yahoo Finance — quantitative (free)\n- SEC EDGAR — filings (free)\n- Claude API — qualitative scoring")

if not ANTHROPIC_API_KEY:
    st.sidebar.error("ANTHROPIC_API_KEY not set — qualitative scoring unavailable.")

fmp_today = cache.request_count_today("fmp")
components.api_usage_sidebar(fmp_today, FMP_DAILY_LIMIT, ticker_input)


# ── Main area ─────────────────────────────────────────────────────────────────

st.title("Philip Fisher 15-Point Checklist")
st.markdown(
    "Evaluate any US stock against Fisher's 15 criteria. "
    "Quantitative points (1, 5, 6, 10, 13) use Yahoo Finance; "
    "qualitative points (2, 3, 4, 7-9, 11-12, 14-15) use Claude AI on SEC filings. "
    "All results are saved — click any stock in the sidebar to reload instantly at zero cost."
)

# ── Entry point ───────────────────────────────────────────────────────────────

if analyze_btn and ticker_input:
    _run_evaluation(ticker_input)
elif "active_ticker" in st.session_state and st.session_state.get("active_summary"):
    _render(
        st.session_state["active_summary"],
        st.session_state.get("active_thesis", ""),
        st.session_state.get("active_qafp"),
        from_cache=False,
    )
else:
    st.markdown(
        """
        ### How to use
        1. Enter a US ticker in the sidebar (e.g. `AAPL`, `MSFT`, `NVDA`) and click **Analyze**
        2. Results are saved permanently — previously analyzed stocks appear in the sidebar
        3. Click any saved stock to reload instantly with **zero API calls**

        ### Requirements
        | Key | Purpose |
        |---|---|
        | `ANTHROPIC_API_KEY` | Claude AI — qualitative points 2, 3, 4, 7–9, 11–12, 14–15 |
        | SEC EDGAR + Yahoo Finance | Free — no keys needed |

        Add keys to `.env` (see `.env.example`).
        """
    )
