"""
Reusable Streamlit UI components — dark-mode friendly.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from scoring.models import EvalSummary, PointResult


SCORE_COLORS = {
    "strong":      "#27ae60",
    "average":     "#e67e22",
    "weak":        "#c0392b",
    "unavailable": "#7f8c8d",
}

SCORE_BADGE = {
    "strong":      "🟢 Strong",
    "average":     "🟡 Average",
    "weak":        "🔴 Weak",
    "unavailable": "⚪ N/A",
}

VERDICT_STYLE = {
    "BUY / ACCUMULATE": ("success", "✅ BUY / ACCUMULATE"),
    "WATCHLIST":        ("warning", "⚠️ WATCHLIST"),
    "PASS":             ("error",   "❌ PASS"),
}


# ── Verdict banner ────────────────────────────────────────────────────────────

def verdict_banner(summary: EvalSummary) -> None:
    pct = int(summary.ratio * 100)
    style, label = VERDICT_STYLE.get(summary.verdict, ("info", summary.verdict))

    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        st.markdown(f"## {summary.ticker} &nbsp; `{summary.company_name}`")
    with col2:
        st.metric("Fisher Score", f"{summary.total} / {summary.max_score}", f"{pct}%")
    with col3:
        getattr(st, style)(f"**{label}**")

    if summary.critical_weak:
        st.error(
            f"Critical weak points: {', '.join(f'**Point {n}**' for n in summary.critical_weak)} — "
            "these block a BUY verdict regardless of total score."
        )


# ── Scorecard table (HTML — dark mode safe) ───────────────────────────────────

def scorecard_table(results: list[PointResult]) -> None:
    _ROW_BG = {
        "strong":      "rgba(39, 174, 96, 0.18)",
        "average":     "rgba(230, 126, 34, 0.18)",
        "weak":        "rgba(192, 57, 43, 0.22)",
        "unavailable": "rgba(127, 140, 141, 0.10)",
    }
    _DOT = {
        "strong":      '<span style="color:#27ae60;font-size:1.1em">●●</span>',
        "average":     '<span style="color:#e67e22;font-size:1.1em">●<span style="opacity:.35">●</span></span>',
        "weak":        '<span style="color:#c0392b;opacity:.5;font-size:1.1em">●●</span>',
        "unavailable": '<span style="color:#7f8c8d">–</span>',
    }
    _BAR_COLOR = {"strong": "#27ae60", "average": "#e67e22", "weak": "#c0392b", "unavailable": "#7f8c8d"}

    def _bar(numeric: int, score: str) -> str:
        pct = int(numeric / 2 * 100)
        color = _BAR_COLOR.get(score, "#7f8c8d")
        return (
            f'<div style="background:rgba(255,255,255,0.08);border-radius:4px;height:10px;width:100%">'
            f'<div style="background:{color};width:{pct}%;height:100%;border-radius:4px"></div></div>'
        )

    rows_html = ""
    for r in results:
        bg = _ROW_BG.get(r.score, "")
        dot = _DOT.get(r.score, "")
        bar = _bar(r.numeric, r.score)
        rows_html += (
            f'<tr style="background:{bg}">'
            f'<td style="text-align:center;padding:6px 8px;color:#aaa">{r.point_number}</td>'
            f'<td style="padding:6px 10px">{r.label}</td>'
            f'<td style="text-align:center;padding:6px 8px">{dot}</td>'
            f'<td style="padding:6px 12px;min-width:90px">{bar}</td>'
            f'</tr>'
        )

    table_html = f"""
    <style>
        .fisher-table {{ width:100%; border-collapse:collapse; font-size:0.93em; }}
        .fisher-table th {{ background:rgba(255,255,255,0.06); padding:8px 10px;
                           text-align:left; color:#bbb; font-weight:600;
                           border-bottom:1px solid rgba(255,255,255,0.1); }}
        .fisher-table td {{ border-bottom:1px solid rgba(255,255,255,0.05); }}
    </style>
    <table class="fisher-table">
      <thead><tr>
        <th style="text-align:center;width:40px">Pt</th>
        <th>Fisher Point</th>
        <th style="text-align:center;width:60px">Score</th>
        <th style="width:120px">Strength</th>
      </tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
    """
    st.markdown(table_html, unsafe_allow_html=True)


# ── Radar chart ───────────────────────────────────────────────────────────────

def radar_chart(results: list[PointResult]) -> None:
    labels = [f"P{r.point_number}" for r in results]
    values = [r.numeric for r in results]
    labels += [labels[0]]
    values += [values[0]]

    fig = go.Figure(go.Scatterpolar(
        r=values,
        theta=labels,
        fill="toself",
        fillcolor="rgba(39, 174, 96, 0.20)",
        line=dict(color="#27ae60", width=2.5),
        marker=dict(color="#27ae60", size=6),
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        polar=dict(
            bgcolor="rgba(0,0,0,0)",
            radialaxis=dict(
                visible=True,
                range=[0, 2],
                tickvals=[0, 1, 2],
                ticktext=["weak", "avg", "strong"],
                tickfont=dict(color="#aaa", size=10),
                gridcolor="rgba(255,255,255,0.1)",
                linecolor="rgba(255,255,255,0.1)",
            ),
            angularaxis=dict(
                tickfont=dict(color="#ccc", size=11),
                gridcolor="rgba(255,255,255,0.08)",
                linecolor="rgba(255,255,255,0.15)",
            ),
        ),
        showlegend=False,
        margin=dict(l=50, r=50, t=30, b=30),
        height=400,
    )
    st.plotly_chart(fig, use_container_width=True)


# ── Per-point expanders ───────────────────────────────────────────────────────

def point_expanders(results: list[PointResult]) -> None:
    st.markdown("#### Point-by-Point Detail")
    for r in results:
        badge = SCORE_BADGE.get(r.score, r.score)
        header = f"**Point {r.point_number}** — {r.label} &nbsp; {badge}"

        with st.expander(f"Point {r.point_number} — {r.label}  [{r.score.upper()}]", expanded=False):
            color = SCORE_COLORS.get(r.score, "#7f8c8d")
            st.markdown(
                f'<div style="border-left:3px solid {color};padding-left:12px;margin-bottom:8px">'
                f'{r.rationale}</div>',
                unsafe_allow_html=True,
            )
            if r.key_signals:
                st.markdown("**Key signals:**")
                for sig in r.key_signals:
                    st.markdown(f"- {sig}")
            if r.data_used:
                with st.expander("Raw data", expanded=False):
                    st.json(r.data_used)


# ── Thesis box ────────────────────────────────────────────────────────────────

def thesis_box(thesis: str) -> None:
    st.markdown("#### Investment Thesis")
    st.markdown(
        f'<div style="background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.12);'
        f'border-radius:8px;padding:16px 20px;line-height:1.7;font-size:0.97em">{thesis}</div>',
        unsafe_allow_html=True,
    )


# ── Sidebar API usage ─────────────────────────────────────────────────────────

# ── QAFP components ───────────────────────────────────────────────────────────

QAFP_VERDICT_STYLE = {
    "BUY / ACCUMULATE": ("success", "✅ BUY / ACCUMULATE"),
    "WATCHLIST":        ("warning", "⚠️ WATCHLIST"),
    "AVOID":            ("error",   "❌ AVOID"),
}

QUALITY_LABEL_COLOR = {
    "High":          "#27ae60",
    "Above Average": "#2ecc71",
    "Average":       "#e67e22",
    "Low":           "#c0392b",
}

VALUATION_LABEL_COLOR = {
    "Cheap":     "#27ae60",
    "Fair":      "#e67e22",
    "Expensive": "#c0392b",
}


def qafp_banner(qafp) -> None:
    from scoring.qafp_models import QAFPResult
    q: QAFPResult = qafp
    style, label = QAFP_VERDICT_STYLE.get(q.recommendation, ("info", q.recommendation))
    ql_color = QUALITY_LABEL_COLOR.get(q.quality_label, "#7f8c8d")
    vl_color = VALUATION_LABEL_COLOR.get(q.valuation_label, "#7f8c8d")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Quality Score", f"{q.quality_score:.0f} / 100",
                  delta=q.quality_label, delta_color="off")
    with c2:
        st.metric("Valuation Score", f"{q.valuation_score:.0f} / 100",
                  delta=q.valuation_label, delta_color="off")
    with c3:
        ret_color = "normal" if q.expected_return >= q.required_return else "inverse"
        st.metric("Expected Return", f"{q.expected_return:.1%}",
                  delta=f"req. {q.required_return:.0%}", delta_color=ret_color)
    with c4:
        getattr(st, style)(f"**{label}**")

    if q.red_flags:
        flags_md = "\n".join(f"- {f}" for f in q.red_flags)
        st.warning(f"**Red flags:**\n{flags_md}")


def qafp_quality_table(qafp) -> None:
    from scoring.qafp_models import QAFPResult
    q: QAFPResult = qafp

    sub_order = ["profitability", "cash_generation", "balance_sheet", "growth"]
    sub_labels = {
        "profitability":   "Profitability & Returns",
        "cash_generation": "Cash Generation",
        "balance_sheet":   "Balance Sheet",
        "growth":          "Growth Profile",
    }

    rows_html = ""
    for key in sub_order:
        sub = q.sub_scores.get(key)
        if not sub:
            continue
        color = QUALITY_LABEL_COLOR.get(sub.label, "#7f8c8d")
        bar_pct = int(sub.score)
        rows_html += (
            f'<tr>'
            f'<td style="padding:7px 10px">{sub_labels[key]}</td>'
            f'<td style="text-align:center;padding:7px 8px;color:{color};font-weight:600">'
            f'{sub.label}</td>'
            f'<td style="padding:7px 12px;min-width:110px">'
            f'<div style="background:rgba(255,255,255,0.08);border-radius:4px;height:9px">'
            f'<div style="background:{color};width:{bar_pct}%;height:100%;border-radius:4px"></div>'
            f'</div></td>'
            f'<td style="text-align:right;padding:7px 10px;color:#aaa">{sub.score:.0f}</td>'
            f'</tr>'
        )

    html = f"""
    <table class="fisher-table" style="width:100%">
      <thead><tr>
        <th>Sub-pillar</th>
        <th style="text-align:center">Rating</th>
        <th>Score bar</th>
        <th style="text-align:right">/ 100</th>
      </tr></thead>
      <tbody>{rows_html}</tbody>
    </table>"""
    st.markdown(html, unsafe_allow_html=True)

    # Sub-score expanders with notes
    for key in sub_order:
        sub = q.sub_scores.get(key)
        if not sub:
            continue
        color = QUALITY_LABEL_COLOR.get(sub.label, "#7f8c8d")
        with st.expander(f"{sub_labels[key]}  [{sub.label}]", expanded=False):
            if sub.notes:
                for n in sub.notes:
                    st.markdown(f"- {n}")
            if sub.metrics:
                st.json({k: (f"{v:.1%}" if isinstance(v, float) and abs(v) < 10 else v)
                         for k, v in sub.metrics.items() if not isinstance(v, list)})


def qafp_valuation_table(qafp) -> None:
    from scoring.qafp_models import QAFPResult
    q: QAFPResult = qafp
    vm = q.valuation_metrics

    def _fmt(val, pct=False, mult=False):
        if val == 0 or val is None:
            return "N/A"
        if pct:
            return f"{val:.1%}"
        if mult:
            return f"{val:.1f}x"
        if abs(val) >= 1e9:
            return f"${val/1e9:.1f}B"
        if abs(val) >= 1e6:
            return f"${val/1e6:.0f}M"
        return str(round(val, 2))

    rows = [
        ("P/E (TTM)",         _fmt(vm.get("pe_ttm"), mult=True)),
        ("P/E (Forward)",     _fmt(vm.get("pe_forward"), mult=True)),
        ("EV/EBITDA",         _fmt(vm.get("ev_ebitda"), mult=True)),
        ("Price/Sales",       _fmt(vm.get("price_to_sales"), mult=True)),
        ("Price/Book",        _fmt(vm.get("price_to_book"), mult=True)),
        ("FCF Yield",         _fmt(vm.get("fcf_yield"), pct=True)),
        ("PEG Ratio",         _fmt(vm.get("peg_ratio"), mult=True)),
        ("Market Cap",        _fmt(vm.get("market_cap"))),
        ("Enterprise Value",  _fmt(vm.get("enterprise_value"))),
        ("Expected Return",   _fmt(vm.get("expected_return"), pct=True)),
        ("Required Return",   _fmt(vm.get("required_return"), pct=True)),
    ]

    rows_html = "".join(
        f'<tr><td style="padding:6px 10px;color:#bbb">{label}</td>'
        f'<td style="padding:6px 10px;text-align:right;font-weight:600">{val}</td></tr>'
        for label, val in rows
    )
    html = f"""
    <table class="fisher-table" style="width:100%">
      <thead><tr>
        <th>Metric</th><th style="text-align:right">Value</th>
      </tr></thead>
      <tbody>{rows_html}</tbody>
    </table>"""
    st.markdown(html, unsafe_allow_html=True)


def qafp_section(qafp) -> None:
    """Full QAFP section rendered below Fisher evaluation."""
    st.divider()
    st.markdown("## Quality at a Fair Price (QAFP) Analysis")
    qafp_banner(qafp)

    col_left, col_right = st.columns([1, 1])
    with col_left:
        st.markdown("#### Quality Breakdown")
        qafp_quality_table(qafp)
    with col_right:
        st.markdown("#### Valuation Metrics")
        qafp_valuation_table(qafp)

    # Key metrics table
    st.markdown("#### Key Metrics Summary")
    km = qafp.key_metrics
    metrics_html = f"""
    <table class="fisher-table" style="width:100%">
      <thead><tr>
        <th>Metric</th><th style="text-align:right">Value</th>
        <th>Metric</th><th style="text-align:right">Value</th>
      </tr></thead>
      <tbody>
        <tr>
          <td style="padding:6px 10px;color:#bbb">Return on Equity</td>
          <td style="padding:6px 10px;text-align:right;font-weight:600">{km.get('roe', 0):.1%}</td>
          <td style="padding:6px 10px;color:#bbb">FCF Margin (avg)</td>
          <td style="padding:6px 10px;text-align:right;font-weight:600">{km.get('fcf_margin', 0):.1%}</td>
        </tr>
        <tr>
          <td style="padding:6px 10px;color:#bbb">Operating Margin</td>
          <td style="padding:6px 10px;text-align:right;font-weight:600">{km.get('operating_margin', 0):.1%}</td>
          <td style="padding:6px 10px;color:#bbb">FCF CAGR (5yr)</td>
          <td style="padding:6px 10px;text-align:right;font-weight:600">{km.get('fcf_cagr', 0):.1%}</td>
        </tr>
        <tr>
          <td style="padding:6px 10px;color:#bbb">Net Margin</td>
          <td style="padding:6px 10px;text-align:right;font-weight:600">{km.get('net_margin', 0):.1%}</td>
          <td style="padding:6px 10px;color:#bbb">Revenue CAGR (5yr)</td>
          <td style="padding:6px 10px;text-align:right;font-weight:600">{km.get('revenue_cagr', 0):.1%}</td>
        </tr>
        <tr>
          <td style="padding:6px 10px;color:#bbb">Debt / Equity</td>
          <td style="padding:6px 10px;text-align:right;font-weight:600">{km.get('debt_to_equity', 0):.2f}x</td>
          <td style="padding:6px 10px;color:#bbb">Net Debt / EBITDA</td>
          <td style="padding:6px 10px;text-align:right;font-weight:600">{km.get('net_debt_ebitda', 0):.1f}x</td>
        </tr>
      </tbody>
    </table>"""
    st.markdown(metrics_html, unsafe_allow_html=True)


def api_usage_sidebar(fmp_count: int, fmp_limit: int, ticker: str) -> None:
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Cache / API**")
    st.sidebar.caption(f"yFinance calls today: {fmp_count}")
    if ticker and st.sidebar.button("Clear cache for this ticker", key="clear_cache"):
        from data import cache
        cache.invalidate(ticker)
        st.sidebar.success(f"Cache cleared for {ticker}")
        st.rerun()
