"""
General Build-up (Open Play) — UI Components  v2
==================================================
Dash components for the General Build-up card inside
Offensive Phase → Build-up.

Sections:
  A. Frequency KPIs  (Z3 entries, entry %, open-play possessions)
  B. Origin          (Left / Centre / Right stacked bar)
  C. Progression     (★ MAIN — 5 categories, bar chart + KPI cards)
  D. After Z3        (Z14 control %, wide play %, box entry %)
  E. Extra Metrics   (avg passes before entry, avg seconds to reach FT)
"""

from __future__ import annotations

from dash import html, dcc
import plotly.graph_objects as go

# ── Progression palette ─────────────────────────────────────────────────────
PROG_COLORS = {
    "through_ball":     "#f43f5e",   # rose
    "long_ball":        "#f97316",   # orange
    "recovery_fast":    "#22c55e",   # green
    "individual_carry": "#eab308",   # amber
    "short_passing":    "#3b82f6",   # blue
    "other":            "#6b7280",   # grey
}

PROG_LABELS = {
    "through_ball":     "Through Ball",
    "long_ball":        "Long Ball / Direct",
    "recovery_fast":    "Recovery + Quick",
    "individual_carry": "Individual Carry",
    "short_passing":    "Short Passing",
    "other":            "Other",
}

PROG_ICONS = {
    "through_ball":     "bi-chevron-double-up",
    "long_ball":        "bi-arrow-up-right",
    "recovery_fast":    "bi-lightning-charge-fill",
    "individual_carry": "bi-person-walking",
    "short_passing":    "bi-arrow-repeat",
    "other":            "bi-three-dots",
}

# Display order for progression types
PROG_ORDER = [
    "through_ball", "long_ball", "recovery_fast",
    "individual_carry", "short_passing", "other",
]


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER — mini KPI card (reusable)
# ═══════════════════════════════════════════════════════════════════════════════

def _mini_kpi(label: str, value, subtitle: str, color: str, icon: str):
    return html.Div(
        [
            html.Div(
                html.I(className=f"bi {icon}",
                       style={"color": color, "fontSize": "1.3rem"}),
                className="kpi-icon",
            ),
            html.Div(
                [
                    html.Span(label, className="kpi-label"),
                    html.Span(str(value), className="kpi-value"),
                    html.Span(subtitle, className="kpi-subtitle",
                              style={"color": color}),
                ],
                className="kpi-text",
            ),
        ],
        className="kpi-card",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# A. FREQUENCY KPIs
# ═══════════════════════════════════════════════════════════════════════════════

def _section_frequency(m: dict) -> html.Div:
    return html.Div(
        [
            html.H6("Final Third Entry Frequency",
                     className="buildup-subsection-title"),
            html.Div(
                [
                    _mini_kpi(
                        "FT Entries", m["total_z3_entries"],
                        f"{m['z3_entry_pct']}% of possessions",
                        "#8b5cf6", "bi-box-arrow-in-right",
                    ),
                    _mini_kpi(
                        "Open-Play Poss.", m["total_open_possessions"],
                        "possessions analysed",
                        "var(--primary-light)", "bi-shuffle",
                    ),
                    _mini_kpi(
                        "Starting Outside FT", m["total_starting_outside_z3"],
                        "eligible possessions",
                        "#06b6d4", "bi-arrows-move",
                    ),
                ],
                className="team-kpi-row",
            ),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# B. ORIGIN (Left / Centre / Right)
# ═══════════════════════════════════════════════════════════════════════════════

def _section_origin(m: dict) -> html.Div:
    total = m["total_z3_entries"] or 1

    fig = go.Figure()
    for label, count, color in [
        ("Left",   m["origin_left"],   "#3b82f6"),
        ("Centre", m["origin_centre"], "#8b5cf6"),
        ("Right",  m["origin_right"],  "#06b6d4"),
    ]:
        pct = round(count / total * 100, 1)
        if count == 0:
            continue
        fig.add_trace(go.Bar(
            y=["Origin"],
            x=[pct],
            orientation="h",
            name=label,
            marker_color=color,
            text=[f"{label} {pct}%"],
            textposition="inside",
            textfont=dict(size=11, color="#fff"),
            hovertemplate=f"{label}: {count} ({pct}%)<extra></extra>",
        ))
    fig.update_layout(
        barmode="stack",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=0, b=0),
        height=42,
        xaxis=dict(showgrid=False, showticklabels=False,
                   range=[0, 100], fixedrange=True),
        yaxis=dict(showgrid=False, showticklabels=False, fixedrange=True),
        showlegend=False,
    )

    return html.Div(
        [
            html.H6("Where From — Entry Origin",
                     className="buildup-subsection-title"),
            html.Div(
                "Corridor of the last action before entering the Final Third",
                style={"fontSize": "0.78rem", "color": "var(--text-muted)",
                       "marginBottom": "0.6rem"},
            ),
            dcc.Graph(figure=fig, config={"displayModeBar": False}),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# C. PROGRESSION TYPE  (★ MOST IMPORTANT SECTION)
# ═══════════════════════════════════════════════════════════════════════════════

def _section_progression(m: dict) -> html.Div:
    pt    = m["progression_types"]
    total = m["total_z3_entries"] or 1

    # ── Horizontal stacked bar ──
    bar_fig = go.Figure()
    for key in PROG_ORDER:
        count = pt.get(key, 0)
        if count == 0:
            continue
        pct = round(count / total * 100, 1)
        bar_fig.add_trace(go.Bar(
            y=["Progression"],
            x=[pct],
            orientation="h",
            name=PROG_LABELS[key],
            marker_color=PROG_COLORS[key],
            text=[f"{pct}%"],
            textposition="inside",
            textfont=dict(size=11, color="#fff"),
            hovertemplate=(
                f"{PROG_LABELS[key]}: {count} ({pct}%)<extra></extra>"
            ),
        ))
    bar_fig.update_layout(
        barmode="stack",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=0, b=0),
        height=42,
        xaxis=dict(showgrid=False, showticklabels=False,
                   range=[0, 100], fixedrange=True),
        yaxis=dict(showgrid=False, showticklabels=False, fixedrange=True),
        showlegend=False,
    )

    # ── KPI card per progression type ──
    cards = []
    for key in PROG_ORDER:
        count = pt.get(key, 0)
        pct   = round(count / total * 100, 1)
        cards.append(
            html.Div(
                [
                    html.Div(
                        html.I(
                            className=f"bi {PROG_ICONS[key]}",
                            style={"color": PROG_COLORS[key],
                                   "fontSize": "1.1rem"},
                        ),
                        className="kpi-icon",
                    ),
                    html.Div(
                        [
                            html.Span(PROG_LABELS[key], className="kpi-label"),
                            html.Span(f"{count}", className="kpi-value"),
                            html.Span(f"{pct}%", className="kpi-subtitle",
                                      style={"color": PROG_COLORS[key]}),
                        ],
                        className="kpi-text",
                    ),
                ],
                className="kpi-card",
            )
        )

    return html.Div(
        [
            html.H6("How — Progression Type",
                     className="buildup-subsection-title"),
            html.Div(
                "How the team reaches the Final Third "
                "(priority: Through Ball → Long Ball → Recovery → Carry → Short Passing)",
                style={"fontSize": "0.78rem", "color": "var(--text-muted)",
                       "marginBottom": "0.6rem"},
            ),
            html.Div(cards, className="team-kpi-row"),
            dcc.Graph(figure=bar_fig, config={"displayModeBar": False},
                      style={"marginTop": "0.5rem"}),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# D. AFTER Z3  (What happens after reaching the Final Third)
# ═══════════════════════════════════════════════════════════════════════════════

def _section_after_z3(m: dict) -> html.Div:
    total = m["total_z3_entries"] or 1

    items = [
        ("Z14 Control", m["z14_count"], m["z14_pct"],
         "#8b5cf6", "bi-bullseye",
         "Entries reaching the central danger zone (Zone 14)"),
        ("Wide Play", m["wide_count"], m["wide_pct"],
         "#06b6d4", "bi-arrows-expand-vertical",
         "Entries involving the flanks after reaching FT"),
        ("Box Entries", m["box_count"], m["box_pct"],
         "#22c55e", "bi-box-arrow-in-down-right",
         "Entries reaching the penalty area (Z16-Z18)"),
    ]

    cards = []
    for label, count, pct, color, icon, desc in items:
        cards.append(
            html.Div(
                [
                    html.Div(
                        [
                            html.I(className=f"bi {icon}",
                                   style={"color": color, "fontSize": "1.1rem"}),
                            html.Span(label, style={
                                "fontWeight": "600", "fontSize": "0.85rem",
                                "color": "var(--text-primary)"}),
                        ],
                        style={"display": "flex", "alignItems": "center",
                               "gap": "8px"},
                    ),
                    html.Div(
                        [
                            html.Span(f"{count}", style={
                                "fontSize": "1.5rem", "fontWeight": "700",
                                "color": color}),
                            html.Span(f" / {total}  ({pct}%)", style={
                                "fontSize": "0.85rem",
                                "color": "var(--text-secondary)"}),
                        ],
                        style={"marginTop": "6px"},
                    ),
                    html.Div(desc, style={
                        "fontSize": "0.72rem", "color": "var(--text-muted)",
                        "marginTop": "4px"}),
                ],
                className="outcome-card",
                style={"borderLeft": f"3px solid {color}"},
            )
        )

    return html.Div(
        [
            html.H6("After Reaching the Final Third",
                     className="buildup-subsection-title"),
            html.Div(cards, className="outcome-cards-row"),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# E. EXTRA METRICS
# ═══════════════════════════════════════════════════════════════════════════════

def _section_extras(m: dict) -> html.Div:
    return html.Div(
        [
            html.H6("Extra Insights", className="buildup-subsection-title"),
            html.Div(
                [
                    _mini_kpi(
                        "Avg Passes Before Entry",
                        m["avg_passes_before_entry"],
                        "passes per possession before reaching FT",
                        "#a78bfa", "bi-diagram-3",
                    ),
                    _mini_kpi(
                        "Avg Time to FT",
                        f"{m['avg_seconds_to_entry']}s",
                        "seconds from possession start",
                        "#06b6d4", "bi-stopwatch",
                    ),
                ],
                className="team-kpi-row",
            ),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# FULL GENERAL BUILD-UP CARD
# ═══════════════════════════════════════════════════════════════════════════════

def general_buildup_card(data: dict) -> html.Div:
    """
    Assemble the complete General Build-up (Open Play) card.

    Parameters
    ----------
    data : dict
        Output of ``analyse_general_buildup()``.
        Must contain keys ``metrics`` and ``entries``.
    """
    m = data.get("metrics", {})

    if (m.get("total_z3_entries", 0) == 0
            and m.get("total_open_possessions", 0) == 0):
        return html.Div(
            [
                html.H5("General Build-up — Open Play",
                         className="buildup-card-title"),
                html.P(
                    "No open-play possessions found for this team in this match.",
                    className="text-muted",
                    style={"padding": "2rem", "textAlign": "center"},
                ),
            ],
            className="buildup-card",
        )

    sep = html.Hr(style={"borderColor": "var(--border-light)",
                         "margin": "1.5rem 0"})

    return html.Div(
        [
            html.H5("General Build-up — Open Play",
                     className="buildup-card-title"),
            # A — Frequency
            _section_frequency(m),
            sep,
            # B — Origin
            _section_origin(m),
            sep,
            # C — Progression (★ main)
            _section_progression(m),
            sep,
            # D — After Z3
            _section_after_z3(m),
            sep,
            # E — Extra metrics
            _section_extras(m),
        ],
        className="buildup-card",
    )
