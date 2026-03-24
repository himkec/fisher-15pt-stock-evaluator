"""
Epic 7 — Sector Analysis page (single-page drill-down).

All three levels render on the same page:
  Level 0 — Sector ranking (always visible)
  Level 1 — Subsector analysis (shown below when a sector is selected)
  Level 2 — Stock universe    (shown below when a subsector is selected)
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from sector_analysis.taxonomy import (
    SECTORS, DEFAULT_LOOKBACK_YEARS, DEFAULT_TOP_SECTORS_N,
    DEFAULT_TOP_SUBSECTORS_N, LOOKBACK_OPTIONS,
)
from sector_analysis.models import AnalysisConfig, AnalysisResult, SubsectorResult
from sector_analysis.engine import (
    run_sector_analysis, run_subsector_analysis,
    get_subsector_stocks, get_top_sector_stocks,
)
from data import cache

st.set_page_config(
    page_title="Sector Analysis",
    page_icon="🏭",
    layout="wide",
)

_PSEUDO = "SECTOR_ANALYSIS"


# ── Formatting helpers ─────────────────────────────────────────────────────────

def _pct(v: float, decimals: int = 1) -> str:
    return f"{'+' if v >= 0 else ''}{v * 100:.{decimals}f}%"


def _color(v: float) -> str:
    return "#27ae60" if v >= 0 else "#c0392b"


def _badge(v: float) -> str:
    color = _color(v)
    return f'<span style="color:{color};font-weight:700">{_pct(v)}</span>'


# ── Sector ranking chart ───────────────────────────────────────────────────────

def _sector_bar_chart(result: AnalysisResult, selected_sector: str | None) -> None:
    sectors = result.all_sectors
    top_n   = result.config.top_sectors_n
    names   = [f"{SECTORS[s.name]['icon']} {s.name}" for s in sectors]
    ann_ret = [s.annualized_return * 100 for s in sectors]

    def _bar_color(i, s):
        if s.name == selected_sector:
            return "#f39c12"  # highlight selected
        return "#2980b9" if i < top_n else "#5d6d7e"

    colors = [_bar_color(i, s) for i, s in enumerate(sectors)]

    fig = go.Figure(go.Bar(
        y=names[::-1],
        x=ann_ret[::-1],
        orientation="h",
        marker_color=colors[::-1],
        text=[f"{v:+.1f}%" for v in ann_ret[::-1]],
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>Annualised: %{x:.2f}%<extra></extra>",
    ))
    bench_ann = result.benchmark_annualized * 100
    fig.add_vline(x=bench_ann, line_dash="dash", line_color="#e74c3c", line_width=1.5,
                  annotation_text=f"SPY {bench_ann:+.1f}%",
                  annotation_font_color="#e74c3c",
                  annotation_position="top right")
    fig.update_layout(
        height=480,
        margin=dict(l=10, r=60, t=20, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(title="Annualised Return (%)", gridcolor="rgba(255,255,255,0.08)"),
        yaxis=dict(tickfont=dict(size=11)),
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)


# ── Sector ranking table ───────────────────────────────────────────────────────

def _sector_table(result: AnalysisResult) -> None:
    top_n = result.config.top_sectors_n
    rows  = []
    for s in result.all_sectors:
        rows.append({
            "Rank":         s.rank,
            "Sector":       f"{SECTORS[s.name]['icon']} {s.name}",
            "ETF":          s.etf,
            "Total Return": _pct(s.total_return),
            f"{result.config.lookback_years}Y Ann.": _pct(s.annualized_return),
            "YTD":          _pct(s.ytd_return),
            "vs S&P 500":   _pct(s.vs_benchmark),
            "Volatility":   _pct(s.volatility),
            "Sharpe":       f"{s.sharpe:.2f}",
            "Max DD":       _pct(s.max_drawdown),
        })

    df = pd.DataFrame(rows)
    st.markdown(
        df.to_html(index=False, escape=False, classes="fisher-table", border=0),
        unsafe_allow_html=True,
    )
    st.caption(
        f"Blue rows = top {top_n} sectors by annualised return. "
        f"Lookback: {result.config.lookback_years} years ending {result.as_of_date}."
    )


# ── Top sector cards with drill-in buttons ────────────────────────────────────

def _sector_cards(result: AnalysisResult, selected_sector: str | None) -> None:
    top = result.top_sectors
    cols = st.columns(len(top))
    for col, s in zip(cols, top):
        with col:
            is_selected  = s.name == selected_sector
            border_color = "#f39c12" if is_selected else "#2980b9"
            bg_color     = "rgba(243,156,18,0.12)" if is_selected else "rgba(41,128,185,0.07)"
            ann_color    = _color(s.annualized_return)
            ytd_color    = _color(s.ytd_return)
            selected_label = " ✓" if is_selected else ""
            st.markdown(
                f"""<div style="border:1px solid {border_color};border-radius:8px;
                padding:14px;background:{bg_color};">
                <div style="font-size:1.6em;text-align:center">{SECTORS[s.name]['icon']}</div>
                <div style="font-weight:700;text-align:center;font-size:.85em;
                margin:4px 0">{s.name}{selected_label}</div>
                <div style="text-align:center;color:#aaa;font-size:.75em">{s.etf}</div>
                <hr style="border-color:rgba(255,255,255,.1);margin:8px 0">
                <div style="display:flex;justify-content:space-between;font-size:.8em">
                  <span style="color:#aaa">Ann. return</span>
                  <span style="color:{ann_color};font-weight:700">{_pct(s.annualized_return)}</span>
                </div>
                <div style="display:flex;justify-content:space-between;font-size:.8em;margin-top:4px">
                  <span style="color:#aaa">YTD</span>
                  <span style="color:{ytd_color};font-weight:700">{_pct(s.ytd_return)}</span>
                </div>
                <div style="display:flex;justify-content:space-between;font-size:.8em;margin-top:4px">
                  <span style="color:#aaa">Sharpe</span>
                  <span>{s.sharpe:.2f}</span>
                </div>
                <div style="display:flex;justify-content:space-between;font-size:.8em;margin-top:4px">
                  <span style="color:#aaa">Max DD</span>
                  <span style="color:#c0392b">{_pct(s.max_drawdown)}</span>
                </div>
                </div>""",
                unsafe_allow_html=True,
            )
            btn_label = "✓ Selected" if is_selected else "Drill into subsectors →"
            if st.button(btn_label, key=f"drill_{s.name}", use_container_width=True,
                         type="primary" if is_selected else "secondary"):
                if is_selected:
                    # Toggle off
                    st.session_state["sa_drill_sector"] = None
                    st.session_state["sa_subsectors"]   = None
                    st.session_state["sa_drill_sub"]    = None
                    st.session_state["sa_stocks"]       = None
                else:
                    st.session_state["sa_drill_sector"] = s.name
                    st.session_state["sa_subsectors"]   = None
                    st.session_state["sa_drill_sub"]    = None
                    st.session_state["sa_stocks"]       = None
                st.rerun()


# ── Analysis definitions (mirrors app.py ANALYSIS_GROUPS implemented entries) ──

_ANALYSES = [
    {"id": "fisher",        "name": "Fisher 15-Point",    "group": "Growth"},
    {"id": "qafp",          "name": "QAFP",               "group": "Growth"},
    {"id": "canslim",       "name": "CAN SLIM",           "group": "Momentum"},
    {"id": "fundamental",   "name": "Fundamental",        "group": "Value"},
    {"id": "dcf_fcf",       "name": "FCF DCF",            "group": "Value"},
    {"id": "ddm",           "name": "DDM",                "group": "Value"},
    {"id": "rim",           "name": "Residual Income",    "group": "Value"},
    {"id": "graham_number", "name": "Graham Number",      "group": "Value"},
]

_PRESETS = {
    "Full Due Diligence": {"fisher", "qafp", "canslim", "fundamental", "dcf_fcf", "ddm", "rim", "graham_number"},
    "Growth (Fisher + QAFP)": {"fisher", "qafp", "fundamental"},
    "Value (DCF + Graham)": {"fundamental", "dcf_fcf", "rim", "graham_number"},
    "Momentum (CAN SLIM)": {"canslim"},
    "Quick Quality (QAFP)": {"qafp"},
}


def _analysis_picker(ticker: str, company: str) -> None:
    """Inline analysis selection panel that switches to Stock Evaluator page."""
    st.markdown(
        f"<div style='background:rgba(41,128,185,0.1);border:1px solid rgba(41,128,185,0.4);"
        f"border-radius:8px;padding:12px 16px;margin:8px 0'>"
        f"<b>Analyse:</b> {ticker} &nbsp;·&nbsp; <span style='color:#aaa'>{company}</span></div>",
        unsafe_allow_html=True,
    )

    preset_key = f"sa_preset_{ticker}"
    check_key  = lambda aid: f"sa_chk_{ticker}_{aid}"

    # Preset buttons
    col_presets = st.columns(len(_PRESETS))
    for col, (label, aids) in zip(col_presets, _PRESETS.items()):
        if col.button(label, key=f"preset_{ticker}_{label}", use_container_width=True):
            for a in _ANALYSES:
                st.session_state[check_key(a["id"])] = a["id"] in aids
            st.rerun()

    # Individual checkboxes (2 rows of 4)
    st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)
    cols = st.columns(4)
    for i, a in enumerate(_ANALYSES):
        default = st.session_state.get(check_key(a["id"]), True)
        cols[i % 4].checkbox(a["name"], value=default, key=check_key(a["id"]))

    # Collect selected
    selected_ids = {a["id"] for a in _ANALYSES if st.session_state.get(check_key(a["id"]), True)}

    st.markdown("<div style='margin-top:4px'></div>", unsafe_allow_html=True)
    if st.button(
        f"Open **{ticker}** in Stock Evaluator →",
        key=f"sa_open_{ticker}",
        type="primary",
        disabled=not selected_ids,
    ):
        # Pass prefill state to app.py via session state
        st.session_state["sa_prefill_ticker"]   = ticker
        st.session_state["sa_prefill_analyses"] = list(selected_ids)
        st.switch_page("app.py")


# ── Top-10 stocks by growth ────────────────────────────────────────────────────

def _render_top_stocks(sector_name: str, result: AnalysisResult) -> None:
    config = result.config
    key    = f"sa_top_stocks_{sector_name}"

    top_stocks = st.session_state.get(key)
    if top_stocks is None:
        with st.spinner(f"Fetching top performers in {sector_name}…"):
            progress = st.progress(0)
            def _cb(pct, msg):
                progress.progress(min(pct, 100), text=msg)
            top_stocks = get_top_sector_stocks(sector_name, config, n=10, progress_cb=_cb)
            progress.empty()
            st.session_state[key] = top_stocks

    if not top_stocks:
        st.info("No stock data available.")
        return

    st.markdown(f"### Top 10 stocks by {config.lookback_years}Y total return")

    # Bar chart: total return per stock
    tickers  = [s.ticker for s in top_stocks]
    returns  = [s.total_return * 100 for s in top_stocks]
    ytds     = [s.ytd_return * 100 for s in top_stocks]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=tickers, y=returns,
        name=f"{config.lookback_years}Y Return",
        marker_color=[_color(r) for r in returns],
        text=[f"{v:+.0f}%" for v in returns],
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>Total Return: %{y:.1f}%<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        x=tickers, y=ytds,
        name="YTD",
        marker_color=["rgba(39,174,96,0.5)" if v >= 0 else "rgba(192,57,43,0.5)" for v in ytds],
        hovertemplate="<b>%{x}</b><br>YTD: %{y:.1f}%<extra></extra>",
    ))
    fig.update_layout(
        barmode="group", height=320,
        margin=dict(l=10, r=10, t=10, b=20),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(title="Return (%)", gridcolor="rgba(255,255,255,0.08)"),
        legend=dict(orientation="h", y=1.05),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Rows with per-stock Analyze button
    analyze_ticker = st.session_state.get("sa_analyze_ticker")
    for i, s in enumerate(top_stocks, 1):
        is_open = analyze_ticker == s.ticker
        with st.container(border=True):
            c_rank, c_ticker, c_name, c_sub, c_ret, c_ytd, c_mcap, c_pe, c_rev, c_btn = st.columns(
                [0.4, 0.7, 2.2, 2.0, 0.8, 0.7, 0.9, 0.6, 0.7, 1.2]
            )
            c_rank.markdown(f"**#{i}**")
            c_ticker.markdown(f"**{s.ticker}**")
            c_name.markdown(s.name)
            c_sub.markdown(f"<span style='color:#aaa;font-size:.85em'>{s.sub_industry}</span>",
                           unsafe_allow_html=True)
            c_ret.markdown(_badge(s.total_return), unsafe_allow_html=True)
            c_ytd.markdown(_badge(s.ytd_return), unsafe_allow_html=True)
            c_mcap.markdown(f"${s.market_cap_b:.1f}B" if s.market_cap_b else "—")
            c_pe.markdown(f"{s.pe_ratio:.1f}x" if s.pe_ratio > 0 else "—")
            c_rev.markdown(_badge(s.revenue_growth) if s.revenue_growth else "—",
                           unsafe_allow_html=True)
            btn_label = "✕ Close" if is_open else "Analyze →"
            if c_btn.button(btn_label, key=f"analyze_btn_{s.ticker}",
                            use_container_width=True,
                            type="primary" if is_open else "secondary"):
                st.session_state["sa_analyze_ticker"] = None if is_open else s.ticker
                st.rerun()

        # Inline analysis picker — opens below this row
        if is_open:
            _analysis_picker(s.ticker, s.name)

    st.caption(
        f"Returns over {config.lookback_years}Y lookback. "
        "Click **Analyze →** on any row to configure and launch an analysis."
    )


# ── Subsector section (Level 1) ───────────────────────────────────────────────

def _subsector_bar_chart(subsectors: list[SubsectorResult], selected_sub: str | None) -> None:
    names = [s.name for s in subsectors]
    ann   = [s.annualized_return * 100 for s in subsectors]
    ytd   = [s.ytd_return * 100 for s in subsectors]

    bar_colors_ann = ["#f39c12" if n == selected_sub else "#2980b9" for n in names]

    fig = go.Figure()
    fig.add_trace(go.Bar(name="Annualised", y=names[::-1], x=ann[::-1],
                         orientation="h",
                         marker_color=bar_colors_ann[::-1],
                         hovertemplate="<b>%{y}</b><br>Ann.: %{x:.1f}%<extra></extra>"))
    fig.add_trace(go.Bar(name="YTD", y=names[::-1], x=ytd[::-1],
                         orientation="h", marker_color="#27ae60",
                         hovertemplate="<b>%{y}</b><br>YTD: %{x:.1f}%<extra></extra>"))
    fig.update_layout(
        barmode="group", height=max(300, len(subsectors) * 40 + 80),
        margin=dict(l=10, r=40, t=20, b=20),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(title="Return (%)", gridcolor="rgba(255,255,255,0.08)"),
        legend=dict(orientation="h", y=1.02),
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_subsectors(sector_name: str, result: AnalysisResult) -> None:
    config = result.config
    icon   = SECTORS.get(sector_name, {}).get("icon", "")

    st.divider()
    st.markdown(f"## {icon} {sector_name} — Subsector Drill-Down")

    sector_obj = next((s for s in result.all_sectors if s.name == sector_name), None)
    if sector_obj:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(f"{config.lookback_years}Y Ann. Return", _pct(sector_obj.annualized_return))
        c2.metric("YTD",          _pct(sector_obj.ytd_return))
        c3.metric("Sharpe",       f"{sector_obj.sharpe:.2f}")
        c4.metric("Max Drawdown", _pct(sector_obj.max_drawdown))

    # Top 10 stocks by growth
    _render_top_stocks(sector_name, result)

    st.divider()
    st.markdown("### Subsector breakdown")

    # Load subsectors
    subsectors = st.session_state.get("sa_subsectors")
    if subsectors is None:
        with st.spinner(f"Analysing {sector_name} subsectors… (may take up to 60 s on first run)"):
            progress = st.progress(0)
            def _cb(pct, msg):
                progress.progress(min(pct, 100), text=msg)
            subsectors = run_subsector_analysis(sector_name, config, progress_cb=_cb)
            progress.empty()
            st.session_state["sa_subsectors"] = subsectors

    if not subsectors:
        st.warning("No subsector data available.")
        return

    selected_sub = st.session_state.get("sa_drill_sub")

    _subsector_bar_chart(subsectors, selected_sub)

    st.markdown(f"### Top {config.top_subsectors_n} subsectors — click to view stocks")
    for s in subsectors[:config.top_subsectors_n]:
        is_selected = s.name == selected_sub
        border = "1px solid #f39c12" if is_selected else "1px solid rgba(255,255,255,0.08)"
        with st.container(border=True):
            col1, col2, col3, col4, col5, col6 = st.columns([3, 1, 1, 1, 1, 1])
            col1.markdown(
                f"**#{s.rank} {s.name}**  "
                f"{'⚠️ small sample' if s.small_sample else ''}"
                f"{' ✓' if is_selected else ''}"
            )
            col2.metric("Ann. Return", _pct(s.annualized_return))
            col3.metric("YTD",         _pct(s.ytd_return))
            col4.metric("Volatility",  _pct(s.volatility))
            col5.metric("Sharpe",      f"{s.sharpe:.2f}")
            col6.metric("# Stocks",    s.ticker_count)
            btn_label = "✓ Selected" if is_selected else "View stocks →"
            if col1.button(btn_label, key=f"sub_{s.name}",
                           type="primary" if is_selected else "secondary"):
                if is_selected:
                    st.session_state["sa_drill_sub"] = None
                    st.session_state["sa_stocks"]    = None
                else:
                    st.session_state["sa_drill_sub"] = s.name
                    st.session_state["sa_stocks"]    = None
                st.rerun()

    if len(subsectors) > config.top_subsectors_n:
        with st.expander(f"All {len(subsectors)} subsectors"):
            rows = []
            for s in subsectors:
                rows.append({
                    "Rank":     s.rank,
                    "Subsector": s.name,
                    f"{config.lookback_years}Y Ann.": _pct(s.annualized_return),
                    "YTD":      _pct(s.ytd_return),
                    "Vol":      _pct(s.volatility),
                    "Sharpe":   f"{s.sharpe:.2f}",
                    "Stocks":   s.ticker_count,
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


# ── Stock universe section (Level 2) ──────────────────────────────────────────

def _stock_scatter(stocks, config) -> None:
    if len(stocks) < 3:
        return
    df = pd.DataFrame([{
        "ticker":    s.ticker,
        "name":      s.name,
        "total_ret": s.total_return * 100,
        "mktcap":    s.market_cap_b,
        "pe":        s.pe_ratio,
    } for s in stocks if s.market_cap_b > 0])

    if df.empty:
        return

    fig = px.scatter(
        df, x="mktcap", y="total_ret",
        text="ticker", hover_name="name",
        hover_data={"pe": ":.1f"},
        labels={"mktcap": "Market Cap ($B)", "total_ret": f"{config.lookback_years}Y Return (%)"},
        size="mktcap", size_max=40,
        color="total_ret", color_continuous_scale="RdYlGn",
    )
    fig.update_traces(textposition="top center", textfont_size=9)
    fig.update_layout(
        height=380, margin=dict(l=20, r=20, t=20, b=20),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        coloraxis_showscale=False,
        xaxis=dict(gridcolor="rgba(255,255,255,0.08)"),
        yaxis=dict(gridcolor="rgba(255,255,255,0.08)", zeroline=True,
                   zerolinecolor="rgba(255,255,255,0.2)"),
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_stocks(sub_industry: str, sector_name: str, result: AnalysisResult) -> None:
    config = result.config
    icon   = SECTORS.get(sector_name, {}).get("icon", "")

    st.divider()
    st.markdown(f"## {icon} {sector_name} › {sub_industry} — Stock Universe")

    stocks = st.session_state.get("sa_stocks")
    if stocks is None:
        with st.spinner(f"Fetching fundamentals for {sub_industry} stocks…"):
            progress = st.progress(0)
            def _cb(pct, msg):
                progress.progress(min(pct, 100), text=msg)
            stocks = get_subsector_stocks(sub_industry, config, progress_cb=_cb)
            progress.empty()
            st.session_state["sa_stocks"] = stocks

    if not stocks:
        st.warning("No stock data available for this subsector.")
        return

    st.markdown(f"**{len(stocks)} stocks** — sorted by market cap")
    _stock_scatter(stocks, config)

    rows = []
    for s in stocks:
        rows.append({
            "Ticker":                    s.ticker,
            "Company":                   s.name,
            f"{config.lookback_years}Y Return": _pct(s.total_return),
            "YTD":                       _pct(s.ytd_return),
            "Market Cap":                f"${s.market_cap_b:.1f}B" if s.market_cap_b else "—",
            "P/E":                       f"{s.pe_ratio:.1f}x" if s.pe_ratio > 0 else "N/A",
            "Rev Growth":                _pct(s.revenue_growth) if s.revenue_growth else "N/A",
        })

    st.markdown(
        pd.DataFrame(rows).to_html(index=False, escape=False, classes="fisher-table", border=0),
        unsafe_allow_html=True,
    )
    st.caption("Revenue Growth = trailing 1-year YoY per Yahoo Finance.")


# ── Sidebar / config panel ─────────────────────────────────────────────────────

def _sidebar() -> AnalysisConfig:
    st.sidebar.title("⚙️ Configuration")
    lookback_label = st.sidebar.selectbox(
        "Lookback period", list(LOOKBACK_OPTIONS.keys()), index=0,
    )
    lookback_years = LOOKBACK_OPTIONS[lookback_label]
    top_n    = st.sidebar.slider("Top sectors to highlight",  3, 11, DEFAULT_TOP_SECTORS_N)
    top_sub  = st.sidebar.slider("Top subsectors per sector", 2, 10, DEFAULT_TOP_SUBSECTORS_N)
    min_mcap = st.sidebar.number_input("Min market cap ($B)", value=1.0, step=0.5, min_value=0.0)

    st.sidebar.markdown("---")
    st.sidebar.markdown("**Data sources**")
    st.sidebar.markdown(
        "- SPDR Sector ETFs (yfinance)\n"
        "- S&P 500 constituent list (Wikipedia)\n"
        "- Yahoo Finance fundamentals"
    )
    st.sidebar.markdown("---")

    if st.sidebar.button("🗑️ Clear sector cache", use_container_width=True):
        from data import cache as _c
        _c.invalidate(_PSEUDO)
        keys_to_clear = ["sa_result", "sa_subsectors", "sa_stocks"]
        keys_to_clear += [k for k in st.session_state if k.startswith("sa_top_stocks_")]
        for k in keys_to_clear:
            st.session_state.pop(k, None)
        st.sidebar.success("Cache cleared.")

    return AnalysisConfig(
        lookback_years=lookback_years,
        top_sectors_n=top_n,
        top_subsectors_n=top_sub,
        min_market_cap_b=min_mcap,
    )


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    config = _sidebar()

    # Reset drill-down state when config changes
    prev_cfg = st.session_state.get("sa_config")
    if prev_cfg and prev_cfg != config.to_dict():
        keys_to_clear = ["sa_result", "sa_drill_sector", "sa_subsectors", "sa_drill_sub",
                         "sa_stocks", "sa_analyze_ticker"]
        keys_to_clear += [k for k in st.session_state if k.startswith("sa_top_stocks_")]
        for k in keys_to_clear:
            st.session_state.pop(k, None)
    st.session_state["sa_config"] = config.to_dict()

    # ── Level 0: sector overview ──────────────────────────────────────────────
    st.title("🏭 Sector Analysis")
    st.markdown(
        "Top-down framework: identify leading **GICS sectors** by multi-year performance, "
        "drill into **subsectors**, then explore the **stock universe** — all on this page."
    )

    result = st.session_state.get("sa_result")
    if result is None:
        run_btn = st.button("🚀 Run Sector Analysis", type="primary")
        if not run_btn:
            st.info(
                "Configure parameters in the sidebar, then click **Run Sector Analysis**.\n\n"
                "The first run fetches 3–5 years of price data for 11 sector ETFs (~10 s). "
                "Results are cached for 24 hours."
            )
            return
        with st.spinner("Downloading sector ETF price history…"):
            try:
                result = run_sector_analysis(config)
            except Exception as e:
                st.error(f"Analysis failed: {e}")
                return
        st.session_state["sa_result"] = result

    selected_sector = st.session_state.get("sa_drill_sector")

    # Header metrics
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("As of",          result.as_of_date)
    c2.metric("Lookback from",  result.lookback_start)
    c3.metric(f"S&P 500 ({result.config.lookback_years}Y Ann.)",
              _pct(result.benchmark_annualized))
    c4.metric("Sectors ranked", len(result.all_sectors))

    st.divider()
    col_left, col_right = st.columns([3, 2])
    with col_left:
        st.markdown(f"### All sectors — {config.lookback_years}Y annualised return")
        _sector_bar_chart(result, selected_sector)
    with col_right:
        st.markdown("### Rankings")
        _sector_table(result)

    st.divider()
    st.markdown(f"### Top {config.top_sectors_n} sectors — click to drill in")
    _sector_cards(result, selected_sector)

    # ── Level 1: subsector drill-down (shown below sector overview) ───────────
    if selected_sector:
        _render_subsectors(selected_sector, result)

        # ── Level 2: stock universe (shown below subsector section) ───────────
        selected_sub = st.session_state.get("sa_drill_sub")
        if selected_sub:
            _render_stocks(selected_sub, selected_sector, result)


main()
