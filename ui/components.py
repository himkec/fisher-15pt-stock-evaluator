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

def api_usage_sidebar(fmp_count: int, fmp_limit: int, ticker: str) -> None:
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Cache / API**")
    st.sidebar.caption(f"yFinance calls today: {fmp_count}")
    if ticker and st.sidebar.button("Clear cache for this ticker", key="clear_cache"):
        from data import cache
        cache.invalidate(ticker)
        st.sidebar.success(f"Cache cleared for {ticker}")
        st.rerun()
