"""
Screening page — multi-strategy stock screener.

Strategies:
  1. Quality-First Fundamental Screen  — LIVE
  2. CAN SLIM Momentum Screen          — coming soon
  3. Value / Deep-Value Screen         — coming soon
  4. GARP Screen                       — coming soon
  5. Dividend Growth Screen            — coming soon
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from sector_analysis.taxonomy import SECTORS
from screening.models import QualityScreenConfig, QualityScreenResult
from screening.quality_screen import run_quality_screen
from data import cache as _cache

st.set_page_config(
    page_title="Screening",
    page_icon="🔍",
    layout="wide",
)

_PSEUDO = "SCREEN_QUALITY"

# ── Analysis presets (mirrors sector analysis page) ────────────────────────────

_ANALYSES = [
    {"id": "fisher",        "name": "Fisher 15-Point"},
    {"id": "qafp",          "name": "QAFP"},
    {"id": "canslim",       "name": "CAN SLIM"},
    {"id": "fundamental",   "name": "Fundamental"},
    {"id": "dcf_fcf",       "name": "FCF DCF"},
    {"id": "ddm",           "name": "DDM"},
    {"id": "rim",           "name": "Residual Income"},
    {"id": "graham_number", "name": "Graham Number"},
]

_PRESETS = {
    "Full Due Diligence": {"fisher", "qafp", "canslim", "fundamental", "dcf_fcf", "ddm", "rim", "graham_number"},
    "Growth (Fisher + QAFP)": {"fisher", "qafp", "fundamental"},
    "Value (DCF + Graham)": {"fundamental", "dcf_fcf", "rim", "graham_number"},
    "Quick Quality (QAFP)": {"qafp"},
}

# ── Screen registry ────────────────────────────────────────────────────────────

SCREENS = [
    {
        "id":          "quality_fundamental",
        "title":       "Quality-First Fundamental Screen",
        "icon":        "🏆",
        "tagline":     "High ROIC · Strong FCF · Durable margins · Clean balance sheet",
        "description": (
            "Filters the S&P 500 for businesses that consistently earn returns on capital "
            "well above their cost of capital, generate ample free cash flow, maintain "
            "healthy margins, and carry manageable debt.  "
            "Inspired by Fisher, Buffett, and QAFP quality criteria."
        ),
        "implemented": True,
        "criteria": [
            ("5Y avg ROIC",             "≥ 15%",            "True capital efficiency"),
            ("5Y avg Operating Margin", "≥ 10%",            "Pricing power"),
            ("5Y avg FCF Margin",       "≥ 10%",            "Cash generation quality"),
            ("FCF positive years",      "≥ 4 of last 5",    "Consistency"),
            ("Net Debt / EBITDA",       "≤ 3×",             "Balance sheet safety"),
            ("Interest Coverage",       "≥ 3.5×",           "Debt service capacity"),
            ("Share dilution (5Y)",     "≤ 15% total",      "No chronic dilution"),
            ("5Y CFO / Net Income",     "≥ 70%",            "Earnings quality"),
            ("EPS growth volatility",   "Bottom 70%",       "Earnings stability"),
        ],
        "coming_label": "Live",
    },
    {
        "id":          "canslim_momentum",
        "title":       "CAN SLIM Momentum Screen",
        "icon":        "🚀",
        "tagline":     "Accelerating EPS · RS ≥ 80 · Institutional accumulation",
        "description": (
            "O'Neil-style screen for market leaders with accelerating quarterly earnings, "
            "strong relative price strength, and rising institutional ownership."
        ),
        "implemented": False,
        "criteria": [
            ("Current quarterly EPS growth", "≥ 25% YoY",       "C — current earnings"),
            ("Annual EPS growth (3Y)",        "≥ 25% CAGR",      "A — annual earnings"),
            ("Relative Price Strength",       "RS rating ≥ 80",  "S — price leadership"),
            ("Institutional ownership trend", "Increasing QoQ",  "I — smart money buying"),
            ("Market Cap",                    "≥ $300M",         "L — avoid micro-caps"),
        ],
        "coming_label": "Coming soon",
    },
    {
        "id":          "deep_value",
        "title":       "Value / Deep-Value Screen",
        "icon":        "💎",
        "tagline":     "Low P/E · Low P/B · High FCF yield · Margin of safety",
        "description": (
            "Graham-style contrarian screen for stocks trading at a significant discount "
            "to intrinsic value across multiple metrics."
        ),
        "implemented": False,
        "criteria": [
            ("P/E Ratio",       "≤ 15× (or ≤ 0.65× sector median)", "Earnings cheapness"),
            ("P/B Ratio",       "≤ 1.5×",                            "Asset cheapness"),
            ("FCF Yield",       "≥ 6%",                              "Cash return on price"),
            ("EV/EBITDA",       "≤ 8×",                              "Enterprise cheapness"),
            ("Net Debt/EBITDA", "≤ 3×",                              "Debt safety"),
        ],
        "coming_label": "Coming soon",
    },
    {
        "id":          "garp",
        "title":       "GARP Screen",
        "icon":        "⚖️",
        "tagline":     "Growth at a Reasonable Price · PEG ≤ 1.5 · Quality filter",
        "description": (
            "Finds companies combining above-market growth with valuation discipline "
            "using the PEG ratio layered with quality and profitability gates."
        ),
        "implemented": False,
        "criteria": [
            ("EPS Growth (fwd)", "≥ 15%",   "Growth floor"),
            ("PEG Ratio",        "≤ 1.5",   "Growth-adjusted value"),
            ("ROIC",             "≥ 12%",   "Quality gate"),
            ("Gross Margin",     "≥ 30%",   "Profitability gate"),
            ("Net Debt/EBITDA",  "≤ 2.5×",  "Balance sheet gate"),
        ],
        "coming_label": "Coming soon",
    },
    {
        "id":          "dividend_growth",
        "title":       "Dividend Growth Screen",
        "icon":        "💰",
        "tagline":     "Dividend Aristocrats · Growing payouts · Sustainable coverage",
        "description": (
            "Targets companies with long dividend growth streaks, sustainable payout ratios, "
            "and strong free cash flow coverage."
        ),
        "implemented": False,
        "criteria": [
            ("Dividend growth streak", "≥ 5 consecutive years",  "Consistency"),
            ("Dividend CAGR (5Y)",     "≥ 5%",                   "Growth rate"),
            ("Payout Ratio",           "≤ 65%",                  "Sustainability"),
            ("FCF Payout Ratio",       "≤ 75%",                  "Cash coverage"),
            ("Current Yield",          "≥ 1.5%",                 "Minimum income"),
        ],
        "coming_label": "Coming soon",
    },
]

# ── Helpers ────────────────────────────────────────────────────────────────────

def _pct(v: float, d: int = 1) -> str:
    return f"{'+' if v >= 0 else ''}{v * 100:.{d}f}%"


def _color(v: float) -> str:
    return "#27ae60" if v >= 0 else "#c0392b"


def _badge(v: float) -> str:
    return f'<span style="color:{_color(v)};font-weight:700">{_pct(v)}</span>'


def _score_bar(score: float) -> str:
    """HTML progress-bar style quality score display."""
    pct  = max(0, min(100, score))
    col  = "#27ae60" if pct >= 70 else "#f39c12" if pct >= 45 else "#c0392b"
    return (
        f'<div style="display:flex;align-items:center;gap:6px">'
        f'<div style="background:rgba(255,255,255,0.08);border-radius:3px;'
        f'width:80px;height:10px;overflow:hidden">'
        f'<div style="background:{col};width:{pct:.0f}%;height:100%"></div></div>'
        f'<span style="font-weight:700;color:{col}">{pct:.0f}</span></div>'
    )


# ── Sidebar — quality screen config ───────────────────────────────────────────

def _quality_sidebar() -> QualityScreenConfig:
    st.sidebar.title("⚙️  Quality Screen Config")

    sector_options = ["All Sectors"] + sorted(SECTORS.keys())
    sector = st.sidebar.selectbox("Universe", sector_options, index=0)

    with st.sidebar.expander("Profitability thresholds", expanded=True):
        min_roic    = st.slider("Min 5Y avg ROIC",         0, 30, 15, 1, format="%d%%") / 100
        min_op_m    = st.slider("Min 5Y avg op margin",    0, 30, 10, 1, format="%d%%") / 100
        min_fcf_m   = st.slider("Min 5Y avg FCF margin",   0, 20, 10, 1, format="%d%%") / 100
        min_fcf_pos = st.slider("FCF positive years (of 5)", 1, 5, 4, 1)

    with st.sidebar.expander("Balance sheet thresholds"):
        max_lev  = st.slider("Max Net Debt / EBITDA", 0.0, 6.0, 3.0, 0.5)
        min_ic   = st.slider("Min interest coverage", 0.0, 10.0, 3.5, 0.5)
        max_dil  = st.slider("Max share dilution 5Y", 0, 30, 15, 5, format="%d%%") / 100

    with st.sidebar.expander("Earnings quality thresholds"):
        min_cni  = st.slider("Min CFO / Net Income (5Y cum.)", 40, 100, 70, 5, format="%d%%") / 100
        max_vol_pct = st.slider(
            "Keep least-volatile (drop top X% most volatile)",
            50, 95, 70, 5, format="%d%%",
            help="70% = keep the 70% least-volatile stocks, drop the most volatile 30%"
        ) / 100

    min_mcap = st.sidebar.number_input("Min market cap ($B)", 0.0, 10.0, 1.0, 0.5)

    st.sidebar.markdown("---")
    if st.sidebar.button("🗑️ Clear screen cache", use_container_width=True):
        _cache.invalidate(_PSEUDO)
        st.session_state.pop("sc_quality_result", None)
        st.sidebar.success("Cache cleared.")

    return QualityScreenConfig(
        sector_filter=sector,
        min_market_cap_b=min_mcap,
        min_roic_5y=min_roic,
        min_op_margin_5y=min_op_m,
        min_fcf_margin_5y=min_fcf_m,
        min_fcf_positive_years=min_fcf_pos,
        max_net_debt_ebitda=max_lev,
        min_interest_coverage=min_ic,
        max_share_dilution_5y=max_dil,
        min_cfo_ni_ratio=min_cni,
        max_eps_vol_pct=max_vol_pct,
    )


# ── Funnel chart ───────────────────────────────────────────────────────────────

def _funnel_chart(result: QualityScreenResult) -> None:
    stages  = ["Universe", "Pass Profitability", "Pass Balance Sheet", "Pass Earnings Quality"]
    counts  = [
        result.universe_size,
        result.after_profitability,
        result.after_balance_sheet,
        result.after_earnings_quality,
    ]
    colors  = ["#5d6d7e", "#2980b9", "#1a6fa3", "#27ae60"]

    fig = go.Figure(go.Funnel(
        y=stages, x=counts,
        textinfo="value+percent initial",
        marker=dict(color=colors),
        connector=dict(line=dict(color="rgba(255,255,255,0.15)", width=1)),
    ))
    fig.update_layout(
        height=260,
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(size=13),
    )
    st.plotly_chart(fig, use_container_width=True)


# ── Analysis picker (inline, same UX as sector analysis page) ─────────────────

def _analysis_picker(ticker: str, company: str) -> None:
    st.markdown(
        f"<div style='background:rgba(41,128,185,0.1);border:1px solid rgba(41,128,185,0.4);"
        f"border-radius:8px;padding:10px 14px;margin:6px 0'>"
        f"<b>Analyse:</b> {ticker} &nbsp;·&nbsp; <span style='color:#aaa'>{company}</span></div>",
        unsafe_allow_html=True,
    )
    check_key = lambda aid: f"sc_chk_{ticker}_{aid}"

    preset_cols = st.columns(len(_PRESETS))
    for col, (label, aids) in zip(preset_cols, _PRESETS.items()):
        if col.button(label, key=f"sc_preset_{ticker}_{label}", use_container_width=True):
            for a in _ANALYSES:
                st.session_state[check_key(a["id"])] = a["id"] in aids
            st.rerun()

    st.markdown("<div style='margin-top:6px'></div>", unsafe_allow_html=True)
    cols = st.columns(4)
    for i, a in enumerate(_ANALYSES):
        default = st.session_state.get(check_key(a["id"]), True)
        cols[i % 4].checkbox(a["name"], value=default, key=check_key(a["id"]))

    selected_ids = {a["id"] for a in _ANALYSES if st.session_state.get(check_key(a["id"]), True)}
    if st.button(
        f"Open **{ticker}** in Stock Evaluator →",
        key=f"sc_open_{ticker}",
        type="primary",
        disabled=not selected_ids,
    ):
        st.session_state["sa_prefill_ticker"]   = ticker
        st.session_state["sa_prefill_analyses"] = list(selected_ids)
        st.switch_page("app.py")


# ── Results table ──────────────────────────────────────────────────────────────

def _results_table(result: QualityScreenResult) -> None:
    survivors = result.survivors
    if not survivors:
        st.warning("No stocks passed all filters with the current thresholds.")
        return

    cfg = result.config
    analyze_ticker = st.session_state.get("sc_analyze_ticker")

    # Column headers
    h = st.columns([0.4, 0.7, 2.0, 1.4, 0.85, 0.85, 0.85, 0.7, 1.0, 0.85, 0.85, 1.3])
    for col, label in zip(h, [
        "#", "Ticker", "Company", "Sector",
        "ROIC 5Y", "Op Mgn 5Y", "FCF Mgn 5Y", "FCF+ Yrs",
        "ND/EBITDA", "Int Cov", "Quality", "Action",
    ]):
        col.markdown(f"**{label}**")

    st.divider()

    for rank, m in enumerate(survivors, 1):
        is_open = analyze_ticker == m.ticker
        with st.container():
            c = st.columns([0.4, 0.7, 2.0, 1.4, 0.85, 0.85, 0.85, 0.7, 1.0, 0.85, 0.85, 1.3])
            c[0].markdown(f"**{rank}**")
            c[1].markdown(f"**{m.ticker}**")
            c[2].markdown(m.name)
            c[3].markdown(
                f"<span style='color:#aaa;font-size:.85em'>{m.sector}</span>",
                unsafe_allow_html=True,
            )
            c[4].markdown(_badge(m.roic_5y),       unsafe_allow_html=True)
            c[5].markdown(_badge(m.op_margin_5y),  unsafe_allow_html=True)
            c[6].markdown(_badge(m.fcf_margin_5y), unsafe_allow_html=True)
            c[7].markdown(f"{m.fcf_positive_years}/5")
            nd_color = "#27ae60" if m.net_debt_ebitda <= 2 else "#f39c12" if m.net_debt_ebitda <= 3 else "#c0392b"
            c[8].markdown(
                f'<span style="color:{nd_color}">{m.net_debt_ebitda:.1f}×</span>',
                unsafe_allow_html=True,
            )
            ic_color = "#27ae60" if m.interest_coverage >= 5 else "#f39c12" if m.interest_coverage >= 3.5 else "#c0392b"
            c[9].markdown(
                f'<span style="color:{ic_color}">{m.interest_coverage:.1f}×</span>',
                unsafe_allow_html=True,
            )
            c[10].markdown(_score_bar(m.quality_score), unsafe_allow_html=True)
            btn_label = "✕ Close" if is_open else "Analyze →"
            if c[11].button(btn_label, key=f"sc_row_{m.ticker}",
                            use_container_width=True,
                            type="primary" if is_open else "secondary"):
                st.session_state["sc_analyze_ticker"] = None if is_open else m.ticker
                st.rerun()

        if is_open:
            _analysis_picker(m.ticker, m.name)

    st.caption(
        f"Ranked by composite quality score (ROIC 25% · FCF margin 20% · "
        f"Op margin 15% · Leverage 20% · Stability 10% · Cash conversion 10%)."
    )


# ── Filter breakdown (what failed where) ──────────────────────────────────────

def _filter_breakdown(result: QualityScreenResult) -> None:
    failed = [m for m in result.all_metrics if not m.passed]
    if not failed:
        return

    with st.expander(f"Filter breakdown — {len(failed)} stocks eliminated"):
        by_step = {}
        for m in failed:
            by_step.setdefault(m.fail_step, []).append(m)

        step_labels = {
            "profitability":   "Step 2 — Profitability",
            "balance_sheet":   "Step 3 — Balance sheet",
            "earnings_quality":"Step 4 — Earnings quality",
            "":                "Pre-filtered (market cap / data)",
        }
        for step, label in step_labels.items():
            bucket = by_step.get(step, [])
            if not bucket:
                continue
            st.markdown(f"**{label}** — {len(bucket)} eliminated")
            rows = [{"Ticker": m.ticker, "Name": m.name, "Reason": m.fail_reason}
                    for m in bucket[:20]]
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


# ── Quality screen live view ───────────────────────────────────────────────────

def _render_quality_screen(config: QualityScreenConfig) -> None:
    if st.button("← Back to screens"):
        st.session_state.pop("sc_selected", None)
        st.session_state.pop("sc_quality_result", None)
        st.rerun()

    st.markdown("## 🏆 Quality-First Fundamental Screen")
    st.markdown(
        "Filters the S&P 500 through four sequential quality gates, then ranks survivors "
        "by a composite quality score. On first run, data is fetched for every stock in the "
        "universe (~10–20 min); subsequent runs use the 24-hour cache."
    )

    # Universe info
    sector_label = config.sector_filter
    c1, c2, c3 = st.columns(3)
    c1.metric("Universe",    sector_label)
    c2.metric("Min Mkt Cap", f"${config.min_market_cap_b:.1f}B")
    c3.metric("Min ROIC",    f"{config.min_roic_5y:.0%}")

    st.divider()

    # Load cached result or prompt to run
    result: QualityScreenResult | None = st.session_state.get("sc_quality_result")

    # Detect config change → invalidate cached UI result
    prev_key = st.session_state.get("sc_quality_cache_key")
    if prev_key and prev_key != config.cache_key():
        result = None
        st.session_state.pop("sc_quality_result", None)

    if result is None:
        run_btn = st.button("▶ Run Quality Screen", type="primary")
        if not run_btn:
            st.info(
                "Click **Run Quality Screen** to start.  \n\n"
                "**First run** (no cache): downloads ~5 years of financials for each stock. "
                f"For the full S&P 500 this can take 20–30 minutes. "
                "For a single sector it takes 2–5 minutes.  \n\n"
                "**Subsequent runs** are instant — results are cached for 24 hours."
            )
            return

        prog = st.progress(0, text="Starting…")
        status = st.empty()

        def _cb(pct: int, msg: str) -> None:
            prog.progress(min(pct, 100), text=msg)
            status.caption(msg)

        try:
            result = run_quality_screen(config, progress_cb=_cb)
        except Exception as e:
            st.error(f"Screen failed: {e}")
            return
        prog.empty()
        status.empty()
        st.session_state["sc_quality_result"]    = result
        st.session_state["sc_quality_cache_key"] = config.cache_key()

    # ── Results ───────────────────────────────────────────────────────────────
    n_surv = result.after_earnings_quality
    st.success(
        f"Screen complete — **{n_surv} survivors** from {result.universe_size} stocks "
        f"in {result.run_seconds:.0f}s  ·  as of {result.run_date}"
    )

    col_f, col_m = st.columns([1, 2])
    with col_f:
        st.markdown("### Filter funnel")
        _funnel_chart(result)
    with col_m:
        st.markdown("### Step summary")
        step_rows = [
            {"Stage": "Universe",               "Stocks": result.universe_size,
             "Eliminated": "—"},
            {"Stage": "Pass Profitability",     "Stocks": result.after_profitability,
             "Eliminated": result.universe_size - result.after_profitability},
            {"Stage": "Pass Balance Sheet",     "Stocks": result.after_balance_sheet,
             "Eliminated": result.after_profitability - result.after_balance_sheet},
            {"Stage": "Pass Earnings Quality",  "Stocks": result.after_earnings_quality,
             "Eliminated": result.after_balance_sheet - result.after_earnings_quality},
        ]
        st.dataframe(pd.DataFrame(step_rows), hide_index=True, use_container_width=True)

        if result.errors:
            with st.expander(f"{len(result.errors)} stocks skipped (data errors)"):
                st.text("\n".join(result.errors[:30]))

    st.divider()
    st.markdown(f"### Ranked survivors ({n_surv} stocks)")
    _results_table(result)

    _filter_breakdown(result)


# ── Screen grid (home view) ────────────────────────────────────────────────────

def _badge_status(screen: dict) -> str:
    if screen["implemented"]:
        return '<span style="background:#27ae60;color:#fff;padding:2px 8px;border-radius:4px;font-size:.75em">Live</span>'
    return (
        f'<span style="background:rgba(255,255,255,0.08);color:#aaa;'
        f'padding:2px 8px;border-radius:4px;font-size:.75em">{screen["coming_label"]}</span>'
    )


def _render_home() -> None:
    st.title("🔍 Screening")
    st.markdown(
        "Systematic, rules-based screens to narrow the investment universe. "
        "Select a strategy to configure and run it."
    )
    st.divider()

    for row_start in range(0, len(SCREENS), 2):
        row = SCREENS[row_start:row_start + 2]
        cols = st.columns(2)
        for col, screen in zip(cols, row):
            with col:
                with st.container(border=True):
                    st.markdown(
                        f"<div style='display:flex;justify-content:space-between;"
                        f"align-items:center;margin-bottom:4px'>"
                        f"<span style='font-size:1.3em'>{screen['icon']}</span>"
                        f"{_badge_status(screen)}</div>",
                        unsafe_allow_html=True,
                    )
                    st.markdown(f"**{screen['title']}**")
                    st.markdown(
                        f"<span style='color:#aaa;font-size:.85em'>{screen['tagline']}</span>",
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f"<div style='font-size:.85em;margin:8px 0 10px'>{screen['description']}</div>",
                        unsafe_allow_html=True,
                    )
                    for metric, threshold, _ in screen["criteria"][:3]:
                        st.markdown(
                            f"<div style='font-size:.8em;color:#aaa;margin:2px 0'>"
                            f"· {metric}: <code>{threshold}</code></div>",
                            unsafe_allow_html=True,
                        )
                    if len(screen["criteria"]) > 3:
                        st.markdown(
                            f"<div style='font-size:.8em;color:#555;margin-top:2px'>"
                            f"+ {len(screen['criteria']) - 3} more criteria</div>",
                            unsafe_allow_html=True,
                        )
                    st.markdown("")
                    btn_label = "▶ Run Screen" if screen["implemented"] else "View Details →"
                    if st.button(btn_label, key=f"sc_open_{screen['id']}",
                                 use_container_width=True,
                                 type="primary" if screen["implemented"] else "secondary"):
                        st.session_state["sc_selected"] = screen["id"]
                        st.rerun()


# ── Placeholder detail for unimplemented screens ───────────────────────────────

def _render_placeholder(screen: dict) -> None:
    if st.button("← Back to screens"):
        st.session_state.pop("sc_selected", None)
        st.rerun()

    st.markdown(f"## {screen['icon']} {screen['title']}")
    st.markdown(
        f"<span style='color:#aaa'>{screen['tagline']}</span>", unsafe_allow_html=True
    )
    st.markdown(screen["description"])
    st.divider()

    st.markdown("### Screening criteria")
    col_h1, col_h2, col_h3 = st.columns([2, 2, 3])
    col_h1.markdown("**Metric**")
    col_h2.markdown("**Threshold**")
    col_h3.markdown("**Rationale**")
    for metric, threshold, rationale in screen["criteria"]:
        c1, c2, c3 = st.columns([2, 2, 3])
        c1.markdown(metric)
        c2.markdown(f"`{threshold}`")
        c3.markdown(f"<span style='color:#aaa'>{rationale}</span>", unsafe_allow_html=True)

    st.divider()
    st.info(
        f"**{screen['coming_label']}** — this screen is not yet implemented.\n\n"
        "When live it will filter the universe, rank survivors by a composite score, "
        "and offer one-click **Analyze →** links to the Stock Evaluator."
    )


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    selected_id = st.session_state.get("sc_selected")

    if selected_id == "quality_fundamental":
        config = _quality_sidebar()
        _render_quality_screen(config)
        return

    if selected_id:
        screen = next((s for s in SCREENS if s["id"] == selected_id), None)
        if screen:
            _render_placeholder(screen)
            return

    _render_home()


main()
