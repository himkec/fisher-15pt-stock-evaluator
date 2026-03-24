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


# ── CAN SLIM components ───────────────────────────────────────────────────────

CANSLIM_VERDICT_STYLE = {
    "BUY":       ("success", "✅ BUY"),
    "WATCHLIST": ("warning", "⚠️ WATCHLIST"),
    "AVOID":     ("error",   "❌ AVOID"),
}

MARKET_LABEL = {
    "market_uptrend":    ("🟢", "Market Uptrend"),
    "mixed":             ("🟡", "Mixed Market"),
    "market_correction": ("🔴", "Market Correction"),
}

LETTER_COLOR = {
    "Strong":  "#27ae60",
    "Average": "#e67e22",
    "Weak":    "#c0392b",
}

LETTER_NAMES = {
    "C": "Current Earnings",
    "A": "Annual Earnings",
    "N": "New / Price Highs",
    "S": "Supply & Demand",
    "L": "Leader vs Laggard",
    "I": "Institutional Sponsorship",
}


def canslim_banner(canslim) -> None:
    from scoring.canslim_models import CANSLIMResult
    cs: CANSLIMResult = canslim

    style, verdict_label = CANSLIM_VERDICT_STYLE.get(cs.recommendation, ("info", cs.recommendation))
    mkt_icon, mkt_label  = MARKET_LABEL.get(cs.market_direction, ("⚪", cs.market_direction))

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Composite Score", f"{cs.composite_score:.0f} / 100",
                  delta=cs.composite_label, delta_color="off")
    with c2:
        st.metric("Market Direction", mkt_label, delta=mkt_icon, delta_color="off")
    with c3:
        bp = cs.buy_point
        if bp:
            bp_label = f"${bp.pivot:.2f} {'✓' if bp.valid else '◯'}"
            st.metric("Buy Point (Pivot)", bp_label,
                      delta="Confirmed" if bp.valid else "Not yet confirmed",
                      delta_color="normal" if bp.valid else "off")
        else:
            st.metric("Buy Point", "N/A", delta_color="off")
    with c4:
        getattr(st, style)(f"**{verdict_label}**")

    if cs.red_flags:
        st.warning("**Red flags:**\n" + "\n".join(f"- {f}" for f in cs.red_flags))


def canslim_letters_table(canslim) -> None:
    from scoring.canslim_models import CANSLIMResult
    cs: CANSLIMResult = canslim

    rows_html = ""
    for letter in ["C", "A", "N", "S", "L", "I"]:
        ls = cs.letter_scores.get(letter)
        if not ls:
            continue
        color   = LETTER_COLOR.get(ls.label, "#7f8c8d")
        bar_pct = int(ls.score)
        weight_pct = int(ls.weight * 100)
        rows_html += (
            f'<tr>'
            f'<td style="text-align:center;padding:7px 8px;font-weight:700;'
            f'color:{color};font-size:1.1em">{letter}</td>'
            f'<td style="padding:7px 10px">{LETTER_NAMES.get(letter, ls.name)}</td>'
            f'<td style="text-align:center;padding:7px 8px;color:#aaa">{weight_pct}%</td>'
            f'<td style="text-align:center;padding:7px 8px;color:{color};font-weight:600">'
            f'{ls.label}</td>'
            f'<td style="padding:7px 12px;min-width:110px">'
            f'<div style="background:rgba(255,255,255,0.08);border-radius:4px;height:9px">'
            f'<div style="background:{color};width:{bar_pct}%;height:100%;border-radius:4px">'
            f'</div></div></td>'
            f'<td style="text-align:right;padding:7px 10px;color:#aaa">{ls.score:.0f}</td>'
            f'</tr>'
        )

    html = f"""
    <table class="fisher-table" style="width:100%">
      <thead><tr>
        <th style="text-align:center;width:30px">Letter</th>
        <th>Criterion</th>
        <th style="text-align:center;width:50px">Weight</th>
        <th style="text-align:center">Rating</th>
        <th>Score bar</th>
        <th style="text-align:right">/ 100</th>
      </tr></thead>
      <tbody>{rows_html}</tbody>
    </table>"""
    st.markdown(html, unsafe_allow_html=True)

    # Per-letter expanders
    for letter in ["C", "A", "N", "S", "L", "I"]:
        ls = cs.letter_scores.get(letter)
        if not ls:
            continue
        color = LETTER_COLOR.get(ls.label, "#7f8c8d")
        with st.expander(f"{letter} — {LETTER_NAMES.get(letter, ls.name)}  [{ls.label}]",
                         expanded=False):
            if ls.notes:
                for note in ls.notes:
                    st.markdown(f"- {note}")
            if ls.metrics:
                with st.expander("Raw metrics", expanded=False):
                    st.json(ls.metrics)


def canslim_buy_point_box(canslim) -> None:
    from scoring.canslim_models import CANSLIMResult
    cs: CANSLIMResult = canslim
    bp = cs.buy_point

    if not bp:
        st.info("No buy point detected — 52-week high data unavailable.")
        return

    status_color = "#27ae60" if bp.valid else "#e67e22"
    status_label = "CONFIRMED BREAKOUT" if bp.valid else "Not yet confirmed"

    rows = [
        ("Pivot (resistance)", f"${bp.pivot:.2f}"),
        ("Entry price (pivot +2%)", f"${bp.entry:.2f}"),
        ("Stop loss (–7% from entry)", f"${bp.stop_loss:.2f}"),
        ("Take-profit target (+25%)", f"${bp.take_profit:.2f}"),
        ("Risk/Reward",
         f"1 : {(bp.take_profit - bp.entry) / (bp.entry - bp.stop_loss):.1f}"),
    ]
    rows_html = "".join(
        f'<tr><td style="padding:6px 10px;color:#bbb">{label}</td>'
        f'<td style="padding:6px 10px;text-align:right;font-weight:600">{val}</td></tr>'
        for label, val in rows
    )

    html = f"""
    <div style="border:1px solid {status_color};border-radius:8px;padding:12px 16px;
                background:rgba(255,255,255,0.03);margin-bottom:8px">
      <div style="color:{status_color};font-weight:700;margin-bottom:8px">{status_label}</div>
      <table class="fisher-table" style="width:100%">
        <tbody>{rows_html}</tbody>
      </table>
      <div style="margin-top:8px;color:#aaa;font-size:0.9em">{bp.notes}</div>
    </div>"""
    st.markdown(html, unsafe_allow_html=True)


def canslim_market_box(canslim) -> None:
    from scoring.canslim_models import CANSLIMResult
    cs: CANSLIMResult = canslim
    mm = cs.market_metrics

    mkt_icon, mkt_label = MARKET_LABEL.get(cs.market_direction, ("⚪", cs.market_direction))
    color = {"market_uptrend": "#27ae60", "mixed": "#e67e22",
             "market_correction": "#c0392b"}.get(cs.market_direction, "#7f8c8d")

    rows = [
        ("SPY current",          f"${mm.get('spy_current', 0):.2f}"),
        ("SPY 50d MA",           f"${mm.get('spy_ma50', 0):.2f}"),
        ("SPY 200d MA",          f"${mm.get('spy_ma200', 'N/A')}"
                                 if isinstance(mm.get('spy_ma200'), str)
                                 else f"${mm.get('spy_ma200', 0):.2f}"),
        ("Distribution days (25d)", str(mm.get("distribution_days_25d", "N/A"))),
    ]
    rows_html = "".join(
        f'<tr><td style="padding:5px 10px;color:#bbb">{label}</td>'
        f'<td style="padding:5px 10px;text-align:right;font-weight:600">{val}</td></tr>'
        for label, val in rows
    )
    html = f"""
    <div style="border-left:3px solid {color};padding-left:12px;margin-bottom:8px">
      <div style="font-weight:700;color:{color};margin-bottom:6px">
        {mkt_icon} {mkt_label}
      </div>
      <table class="fisher-table" style="width:100%">
        <tbody>{rows_html}</tbody>
      </table>
    </div>"""
    st.markdown(html, unsafe_allow_html=True)


def canslim_investor_fit(canslim) -> None:
    from scoring.canslim_models import CANSLIMResult
    cs: CANSLIMResult = canslim
    fit = cs.investor_fit
    if not fit:
        return
    with st.expander("Who is CAN SLIM for?", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Best suited for:**")
            for item in fit.get("for", []):
                st.markdown(f"- {item}")
        with c2:
            st.markdown("**Not suitable for:**")
            for item in fit.get("not_for", []):
                st.markdown(f"- {item}")
        if fit.get("summary"):
            st.info(fit["summary"])


def canslim_section(canslim) -> None:
    """Full CAN SLIM section rendered below QAFP."""
    st.divider()
    st.markdown("## CAN SLIM Analysis")
    canslim_banner(canslim)

    col_left, col_right = st.columns([3, 2])
    with col_left:
        st.markdown("#### Letter Scores")
        canslim_letters_table(canslim)
    with col_right:
        st.markdown("#### Market Direction (M)")
        canslim_market_box(canslim)
        st.markdown("#### Buy Point & Risk Rules")
        canslim_buy_point_box(canslim)

    canslim_investor_fit(canslim)


# ── Fundamental Analysis components ──────────────────────────────────────────

FUNDAMENTAL_VERDICT_STYLE = {
    "BUY":  ("success", "✅ BUY with Conviction"),
    "HOLD": ("warning", "🟡 HOLD / Watch for Better Entry"),
    "AVOID":("error",   "❌ AVOID"),
}

SECTION_SCORE_COLOR = {
    "Strong": "#27ae60",
    "Good":   "#2ecc71",
    "Fair":   "#e67e22",
    "Weak":   "#e74c3c",
    "Poor":   "#c0392b",
}

METRIC_SCORE_COLOR = lambda s: (
    "#27ae60" if s >= 8 else
    "#2ecc71" if s >= 6.5 else
    "#e67e22" if s >= 5 else
    "#e74c3c" if s >= 3 else
    "#c0392b"
)


def fundamental_section_banner(result) -> None:
    from scoring.fundamental_models import FundamentalResult
    r: FundamentalResult = result
    style, label = FUNDAMENTAL_VERDICT_STYLE.get(r.recommendation, ("info", r.recommendation))

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Composite Score", f"{r.composite_score:.1f} / 10",
                  delta=r.composite_label, delta_color="off")
    with c2:
        st.metric("Current Price", f"${r.current_price:.2f}" if r.current_price else "N/A")
    with c3:
        base_dcf = next((d for d in r.dcf_scenarios if d.name == "Base"), None)
        if base_dcf and base_dcf.intrinsic_value > 0:
            mos = base_dcf.margin_of_safety
            mos_color = "normal" if mos > 0 else "inverse"
            st.metric("DCF Base Intrinsic Value",
                      f"${base_dcf.intrinsic_value:.2f}",
                      delta=f"MoS {mos:+.0%}", delta_color=mos_color)
        else:
            st.metric("DCF", "N/A (neg. FCF)")
    with c4:
        getattr(st, style)(f"**{label}**")

    if r.red_flags:
        st.warning("**Red flags:**\n" + "\n".join(f"- {f}" for f in r.red_flags))
    if r.highlights:
        st.success("**Highlights:**\n" + "\n".join(f"- {h}" for h in r.highlights))


def _section_card(section) -> None:
    color = SECTION_SCORE_COLOR.get(section.label, "#7f8c8d")
    bar_pct = int(section.score / 10 * 100)
    weight_pct = int(section.weight * 100)

    # Section header
    st.markdown(
        f'<div style="border-left:3px solid {color};padding-left:10px;margin-bottom:6px">'
        f'<span style="font-weight:700;color:{color}">{section.label}</span>'
        f' <span style="color:#aaa;font-size:0.85em">({section.score:.1f}/10 · weight {weight_pct}%)</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    # Score bar
    st.markdown(
        f'<div style="background:rgba(255,255,255,0.08);border-radius:4px;height:8px;margin-bottom:10px">'
        f'<div style="background:{color};width:{bar_pct}%;height:100%;border-radius:4px"></div></div>',
        unsafe_allow_html=True,
    )

    # Metrics table
    if section.metrics:
        rows_html = ""
        for m in section.metrics:
            if m.score > 0:
                mc = METRIC_SCORE_COLOR(m.score)
                dot = f'<span style="color:{mc}">●</span>'
            else:
                dot = '<span style="color:#555">–</span>'
            rows_html += (
                f'<tr>'
                f'<td style="padding:4px 8px;color:#ccc;font-size:0.88em">{m.name}</td>'
                f'<td style="padding:4px 8px;text-align:right;font-weight:600;font-size:0.88em">{m.value}</td>'
                f'<td style="padding:4px 6px;text-align:center">{dot}</td>'
                f'</tr>'
            )
        st.markdown(
            f'<table style="width:100%;border-collapse:collapse">'
            f'<tbody>{rows_html}</tbody></table>',
            unsafe_allow_html=True,
        )

    # Notes
    if section.notes:
        with st.expander("Notes", expanded=False):
            for n in section.notes:
                st.markdown(f"- {n}")


def fundamental_scorecard_grid(result) -> None:
    """3-column grid of the 5 section score cards."""
    from scoring.fundamental_models import FundamentalResult
    r: FundamentalResult = result

    order = ["valuation", "profitability", "growth", "health", "earnings_quality"]
    sections = [r.sections[k] for k in order if k in r.sections]

    # Row 1: 3 sections
    cols1 = st.columns(3)
    for col, sec in zip(cols1, sections[:3]):
        with col:
            with st.container(border=True):
                st.markdown(f"**{sec.name}**")
                _section_card(sec)

    # Row 2: 2 sections centred
    _, col_l, col_r, _ = st.columns([0.5, 1, 1, 0.5])
    for col, sec in zip([col_l, col_r], sections[3:]):
        with col:
            with st.container(border=True):
                st.markdown(f"**{sec.name}**")
                _section_card(sec)


def fundamental_dcf_section(result) -> None:
    from scoring.fundamental_models import FundamentalResult
    r: FundamentalResult = result

    if not r.dcf_scenarios:
        st.info("DCF not available — negative or zero free cash flow.")
        return

    st.markdown(f"WACC: **{r.wacc:.1%}** &nbsp;·&nbsp; Terminal growth: **{r.terminal_growth:.1%}**")

    rows_html = ""
    for s in r.dcf_scenarios:
        mos = s.margin_of_safety
        mos_color = "#27ae60" if mos > 0.10 else "#e67e22" if mos > -0.10 else "#c0392b"
        rows_html += (
            f'<tr>'
            f'<td style="padding:7px 10px;font-weight:600">{s.name}</td>'
            f'<td style="padding:7px 10px;text-align:center;color:#aaa">{s.fcf_growth:.0%}/yr</td>'
            f'<td style="padding:7px 10px;text-align:right;font-weight:700">${s.intrinsic_value:.2f}</td>'
            f'<td style="padding:7px 10px;text-align:right;color:{mos_color};font-weight:700">'
            f'{"+" if mos >= 0 else ""}{mos:.0%}</td>'
            f'</tr>'
        )
    html = f"""
    <table class="fisher-table" style="width:100%">
      <thead><tr>
        <th>Scenario</th>
        <th style="text-align:center">FCF Growth</th>
        <th style="text-align:right">Intrinsic Value / Share</th>
        <th style="text-align:right">Margin of Safety</th>
      </tr></thead>
      <tbody>{rows_html}</tbody>
    </table>"""
    st.markdown(html, unsafe_allow_html=True)
    st.caption("Margin of Safety = (Intrinsic Value − Current Price) / Intrinsic Value. Positive = undervalued.")


def fundamental_dividend_section(result) -> None:
    from scoring.fundamental_models import FundamentalResult
    r: FundamentalResult = result
    dm = r.dividend_metrics
    if not dm:
        st.info("Company does not pay a dividend.")
        return

    rows = [
        ("Annual Dividend Rate", f"${dm.get('annual_dividend', 0):.2f}"),
        ("Dividend Yield", f"{dm.get('dividend_yield', 0):.2%}" if dm.get('dividend_yield') else "N/A"),
        ("Payout Ratio (EPS)", f"{dm.get('payout_ratio', 0):.1%}" if dm.get('payout_ratio') else "N/A"),
        ("FCF Payout Ratio", f"{dm.get('fcf_payout_ratio', 0):.1%}" if dm.get('fcf_payout_ratio') else "N/A"),
    ]
    rows_html = "".join(
        f'<tr><td style="padding:6px 10px;color:#bbb">{label}</td>'
        f'<td style="padding:6px 10px;text-align:right;font-weight:600">{val}</td></tr>'
        for label, val in rows
    )
    st.markdown(
        f'<table class="fisher-table" style="width:100%"><tbody>{rows_html}</tbody></table>',
        unsafe_allow_html=True,
    )
    payout = dm.get("payout_ratio", 0) or 0
    if payout > 0.80:
        st.warning(f"Payout ratio of {payout:.0%} is high — dividend may be at risk if earnings decline.")


def fundamental_section(result) -> None:
    """Full Fundamental Analysis section rendered in the main results area."""
    st.divider()
    st.markdown("## Deep Fundamental Analysis")
    fundamental_section_banner(result)

    st.markdown("### Section Scorecards")
    fundamental_scorecard_grid(result)

    st.markdown("### DCF Intrinsic Value Model")
    fundamental_dcf_section(result)

    if result.dividend_metrics:
        st.markdown("### Dividend Analysis")
        fundamental_dividend_section(result)


def intrinsic_value_football_field(result) -> None:
    """Plotly horizontal bar chart: each method's value range vs current price."""
    from scoring.intrinsic_value_models import IntrinsicValueResult
    r: IntrinsicValueResult = result

    if not r.football_field:
        st.info("No intrinsic value estimates available to chart.")
        return

    price   = r.current_price
    methods = [e.method for e in r.football_field]
    lows    = [e.low    for e in r.football_field]
    highs   = [e.high   for e in r.football_field]
    mids    = [e.mid    for e in r.football_field]

    fig = go.Figure()

    # Range bars (low → high)
    fig.add_trace(go.Bar(
        name="Value range",
        y=methods,
        x=[h - l for h, l in zip(highs, lows)],
        base=lows,
        orientation="h",
        marker_color="rgba(41, 128, 185, 0.45)",
        marker_line_width=0,
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Low: $%{base:.2f}<br>"
            "High: $%{customdata:.2f}<extra></extra>"
        ),
        customdata=highs,
    ))

    # Mid-point markers
    fig.add_trace(go.Scatter(
        name="Central estimate",
        y=methods,
        x=mids,
        mode="markers",
        marker=dict(symbol="diamond", size=10, color="#2980b9"),
        hovertemplate="<b>%{y}</b><br>Central: $%{x:.2f}<extra></extra>",
    ))

    # Current price vertical line
    fig.add_vline(
        x=price, line_width=2, line_dash="dash", line_color="#e74c3c",
        annotation_text=f"Current ${price:.2f}",
        annotation_position="top right",
        annotation_font_color="#e74c3c",
    )

    fig.update_layout(
        height=max(220, len(methods) * 60 + 80),
        margin=dict(l=20, r=20, t=30, b=20),
        showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(title="Per-share value ($)", gridcolor="rgba(255,255,255,0.08)"),
        yaxis=dict(tickfont=dict(size=12)),
        bargap=0.35,
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "Blue bars = Bear → Bull range for each method. "
        "Diamond = central estimate. Red dashed line = current price."
    )


def _iv_upside_badge(upside: float) -> str:
    color = "#27ae60" if upside > 0.10 else "#e67e22" if upside > -0.10 else "#c0392b"
    sign  = "+" if upside >= 0 else ""
    return f'<span style="color:{color};font-weight:700">{sign}{upside:.0%}</span>'


def intrinsic_value_dcf_section(result) -> None:
    from scoring.intrinsic_value_models import IntrinsicValueResult
    r: IntrinsicValueResult = result

    if not r.dcf_fcf:
        st.info("DCF FCF not available — negative or insufficient free cash flow.")
        return

    dcf = r.dcf_fcf
    st.markdown(
        f"Base FCF: **${dcf.base_fcf:,.0f}** &nbsp;·&nbsp; "
        f"WACC: **{dcf.wacc:.1%}** &nbsp;·&nbsp; "
        f"Terminal growth: **{dcf.terminal_growth:.1%}** &nbsp;·&nbsp; "
        f"Horizon: **{dcf.forecast_years} years**"
    )

    rows_html = ""
    for s in dcf.scenarios:
        rows_html += (
            f'<tr>'
            f'<td style="padding:7px 10px;font-weight:600">{s.name}</td>'
            f'<td style="padding:7px 10px;text-align:center;color:#aaa">{s.growth:.0%}/yr near-term</td>'
            f'<td style="padding:7px 10px;text-align:right;font-weight:700">${s.value:.2f}</td>'
            f'<td style="padding:7px 10px;text-align:right">{_iv_upside_badge(s.upside_pct)}</td>'
            f'</tr>'
        )
    st.markdown(
        f'<table class="fisher-table" style="width:100%">'
        f'<thead><tr><th>Scenario</th><th style="text-align:center">FCF Growth</th>'
        f'<th style="text-align:right">Intrinsic Value</th>'
        f'<th style="text-align:right">Upside / Downside</th></tr></thead>'
        f'<tbody>{rows_html}</tbody></table>',
        unsafe_allow_html=True,
    )
    if dcf.notes:
        for n in dcf.notes:
            st.caption(n)


def intrinsic_value_ddm_section(result) -> None:
    from scoring.intrinsic_value_models import IntrinsicValueResult
    r: IntrinsicValueResult = result

    if not r.ddm_gordon and not r.ddm_multi:
        st.info("DDM not available — company does not pay a dividend.")
        return

    if r.ddm_gordon:
        g = r.ddm_gordon
        st.markdown(
            f"**Gordon Growth** — D₁: **${g.d1:.3f}** &nbsp;·&nbsp; "
            f"Required return: **{g.required_return:.0%}** &nbsp;·&nbsp; "
            f"Perpetual growth: **{g.perpetual_growth:.1%}**"
        )
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Fair Value", f"${g.fair_value:.2f}")
        col2.metric("Upside", f"{'+' if g.upside_pct >= 0 else ''}{g.upside_pct:.0%}")
        col3.metric("Div. Yield", f"{g.current_yield:.2%}")
        col4.metric("Yield + Growth", f"{g.yield_plus_growth:.2%}")
        if g.notes:
            for n in g.notes:
                st.caption(n)

    if r.ddm_multi:
        st.markdown("---")
        m = r.ddm_multi
        st.markdown(
            f"**Multi-Period DDM** — Required return: **{m.required_return:.0%}** &nbsp;·&nbsp; "
            f"Terminal growth: **{m.terminal_growth:.1%}**"
        )
        col1, col2, col3 = st.columns(3)
        col1.metric("Fair Value", f"${m.fair_value:.2f}")
        col2.metric("PV (Dividends)", f"${m.pv_dividends:.2f}")
        col3.metric("PV (Terminal)", f"${m.terminal_value_pv:.2f}")


def intrinsic_value_rim_section(result) -> None:
    from scoring.intrinsic_value_models import IntrinsicValueResult
    r: IntrinsicValueResult = result

    if not r.rim:
        st.info("Residual Income Model not available.")
        return

    rim = r.rim
    st.markdown(
        f"Book value / share: **${rim.book_value_per_share:.2f}** &nbsp;·&nbsp; "
        f"Cost of equity: **{rim.cost_of_equity:.1%}** &nbsp;·&nbsp; "
        f"Horizon: **{rim.forecast_years} years**"
    )
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Fair Value", f"${rim.fair_value:.2f}")
    col2.metric("Upside", f"{'+' if rim.upside_pct >= 0 else ''}{rim.upside_pct:.0%}")
    col3.metric("PV Residual Incomes", f"${rim.pv_residual_incomes:.2f}")
    col4.metric("PV Terminal RI", f"${rim.terminal_ri_pv:.2f}")
    if rim.notes:
        for n in rim.notes:
            st.caption(n)


def intrinsic_value_graham_section(result) -> None:
    from scoring.intrinsic_value_models import IntrinsicValueResult
    r: IntrinsicValueResult = result

    if not r.graham:
        st.info("Graham Number not available — requires positive EPS and book value.")
        return

    g = r.graham
    label_color = (
        "#27ae60" if "Below" in g.label else
        "#e67e22" if "At" in g.label else
        "#c0392b"
    )
    st.markdown(
        f"Graham Number: **${g.graham_number:.2f}** &nbsp;·&nbsp; "
        f"EPS (avg): **${g.eps:.2f}** &nbsp;·&nbsp; "
        f"BVPS: **${g.bvps:.2f}**"
    )

    col1, col2, col3 = st.columns(3)
    col1.metric("Graham Number", f"${g.graham_number:.2f}")
    col2.metric("Price / Graham", f"{g.price_to_graham:.2f}x")
    col3.metric("Upside to Graham", f"{'+' if g.upside_pct >= 0 else ''}{g.upside_pct:.0%}")

    st.markdown(
        f'<div style="padding:8px 14px;border-radius:6px;'
        f'background:rgba(255,255,255,0.05);margin:8px 0;'
        f'border-left:4px solid {label_color};font-weight:600;color:{label_color}">'
        f'{g.label}</div>',
        unsafe_allow_html=True,
    )

    # Defensive checks
    checks = g.checks
    if checks:
        items = [
            ("Positive earnings history",   checks.get("earnings_stability", False)),
            ("Pays a dividend",             checks.get("pays_dividend", False)),
            ("P/E below 15",                checks.get("pe_below_15", False)),
            ("P/B below 1.5",               checks.get("pb_below_1_5", False)),
        ]
        rows_html = "".join(
            f'<tr><td style="padding:5px 10px;color:#bbb">{label}</td>'
            f'<td style="padding:5px 10px;text-align:right">'
            f'{"✅" if passed else "❌"}</td></tr>'
            for label, passed in items
        )
        st.markdown(
            f'<table class="fisher-table" style="width:100%">'
            f'<tbody>{rows_html}</tbody></table>',
            unsafe_allow_html=True,
        )
    if g.notes:
        for n in g.notes:
            st.caption(n)


def intrinsic_value_section(result) -> None:
    """Full Intrinsic Value / Valuation Models section."""
    from scoring.intrinsic_value_models import IntrinsicValueResult
    r: IntrinsicValueResult = result

    st.divider()
    st.markdown("## Intrinsic Value / Valuation Models")
    st.markdown(
        f"*Current price: **${r.current_price:.2f}***  — "
        f"methods run: {len(r.football_field)}"
    )

    if r.football_field:
        st.markdown("### Football Field")
        intrinsic_value_football_field(r)

    if r.skipped:
        with st.expander("Skipped / unavailable methods", expanded=False):
            for s in r.skipped:
                st.caption(f"⚠️ {s}")

    # Per-method details
    if r.dcf_fcf:
        with st.expander("📊 DCF — Free Cash Flow Model", expanded=True):
            intrinsic_value_dcf_section(r)

    if r.ddm_gordon or r.ddm_multi:
        with st.expander("💰 Dividend Discount Models (DDM)", expanded=False):
            intrinsic_value_ddm_section(r)

    if r.rim:
        with st.expander("📚 Residual Income Model (RIM)", expanded=False):
            intrinsic_value_rim_section(r)

    if r.graham:
        with st.expander("🔢 Graham Number", expanded=False):
            intrinsic_value_graham_section(r)


def api_usage_sidebar(fmp_count: int, fmp_limit: int, ticker: str) -> None:
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Cache / API**")
    st.sidebar.caption(f"yFinance calls today: {fmp_count}")
    if ticker and st.sidebar.button("Clear cache for this ticker", key="clear_cache"):
        from data import cache
        cache.invalidate(ticker)
        st.sidebar.success(f"Cache cleared for {ticker}")
        st.rerun()
