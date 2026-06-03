"""
Final Third Entry Analysis — UI Components
==========================================
Dash components for the Final Third Entry card inside
Offensive Phase → Build-up.

Follows the exact same patterns as general_buildup_cards.py.
"""

from __future__ import annotations

from dash import html, dcc
import plotly.graph_objects as go

from src.components.final_third_pitch import (
    METHOD_COLORS,
    METHOD_LABELS,
    CORRIDOR_COLORS,
    CORRIDOR_LABELS,
    OUTCOME_COLORS,
    ft_entry_scatter_method,
    ft_zone_outcome_heatmap,
)

# Display order for methods (matches _classify_ft_method() priority)
METHOD_ORDER = [
    "transition_recovery", "through_ball", "switch_of_play", "set_piece",
    "long_ball", "cross_delivery", "individual_carry", "short_pass",
]

METHOD_ICONS = {
    "transition_recovery": "bi-lightning-charge-fill",
    "through_ball":        "bi-chevron-double-up",
    "switch_of_play":      "bi-arrow-left-right",
    "set_piece":           "bi-flag-fill",
    "long_ball":           "bi-arrow-up-right",
    "cross_delivery":      "bi-send-fill",
    "individual_carry":    "bi-person-walking",
    "short_pass":          "bi-dot",
}

METHOD_DESCRIPTIONS = {
    "transition_recovery": "Ball won in own half, FT reached within 15 s",
    "through_ball":        "Penetrative pass splitting the defence",
    "switch_of_play":      "Lateral pass changing the point of attack",
    "set_piece":           "Set-piece played directly into the final third",
    "long_ball":           "Direct pass over 32 m or aerial ball into the FT",
    "cross_delivery":      "Cross from wide area into or across the final third",
    "individual_carry":    "Dribble or run with the ball into FT",
    "short_pass":          "Patient build-up with ≥ 5 passes",
}


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER — mini KPI card
# ═══════════════════════════════════════════════════════════════════════════════

def _mini_kpi(label: str, value, subtitle: str, color: str, icon: str) -> html.Div:
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
# TEMPO CARD — with 15-minute windows dropdown
# ═══════════════════════════════════════════════════════════════════════════════

def _tempo_card(m: dict) -> html.Div:
    """
    Render the Tempo KPI card with passes per minute.
    Includes a Details/Summary dropdown showing 15-minute window breakdown.
    """
    ppm = m.get("passes_per_minute", 0.0)
    windows = m.get("tempo_windows", [])

    window_items = []
    for w in windows:
        start_min = w.get("start_min", 0)
        end_min = w.get("end_min", 0)
        passes = w.get("passes", 0)
        w_ppm = w.get("ppm", 0.0)

        window_items.append(
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(
                                f"{start_min}'-{end_min}'",
                                style={
                                    "fontSize": "0.75rem",
                                    "fontWeight": "600",
                                    "color": "var(--text-primary)",
                                    "minWidth": "50px",
                                },
                            ),
                            html.Span(
                                f"{passes} passes",
                                style={
                                    "fontSize": "0.75rem",
                                    "color": "var(--text-secondary)",
                                    "flex": "1",
                                },
                            ),
                            html.Span(
                                f"{w_ppm} ppm",
                                style={
                                    "fontSize": "0.75rem",
                                    "fontWeight": "600",
                                    "color": "#f59e0b",
                                },
                            ),
                        ],
                        style={
                            "display": "flex",
                            "alignItems": "center",
                            "justifyContent": "space-between",
                            "gap": "8px",
                        },
                    ),
                ],
                style={
                    "padding": "6px 0",
                    "borderBottom": "1px solid var(--border-light)",
                },
            )
        )

    return html.Div(
        [
            html.Details(
                [
                    html.Summary(
                        html.Div(
                            [
                                html.Div(
                                    html.I(className="bi bi-lightning-fill",
                                           style={"color": "#f59e0b", "fontSize": "1.3rem"}),
                                    className="kpi-icon",
                                ),
                                html.Div(
                                    [
                                        html.Span("Tempo", className="kpi-label"),
                                        html.Span(f"{ppm}", className="kpi-value"),
                                        html.Span("passes per minute (qual. poss.)",
                                                  className="kpi-subtitle",
                                                  style={"color": "#f59e0b"}),
                                    ],
                                    className="kpi-text",
                                ),
                            ],
                            style={
                                "display": "flex",
                                "alignItems": "center",
                                "cursor": "pointer",
                                "width": "100%",
                            },
                        ),
                        style={
                            "cursor": "pointer",
                            "listStyle": "none",
                        },
                    ),
                    html.Div(
                        window_items,
                        style={
                            "marginTop": "8px",
                            "paddingTop": "8px",
                            "borderTop": "1px solid var(--border-light)",
                        },
                    ) if window_items else html.Div(),
                ],
                className="kpi-card",
                style={
                    "cursor": "pointer",
                },
            ),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# A. POSSESSION OVERVIEW
# ═══════════════════════════════════════════════════════════════════════════════

def _section_possession(m: dict) -> html.Div:
    """Top-level overview: possession share + final-third entry rate + tempo."""
    return html.Div(
        [
            html.H6("Possession & Final Third Entry", className="buildup-subsection-title"),
            html.Div(
                [
                    _mini_kpi(
                        "Possession %", f"{m['possession_pct']}%",
                        "of match possession",
                        "#8b5cf6", "bi-pie-chart-fill",
                    ),
                    _mini_kpi(
                        "Qualifying Poss.", m["qualifying_poss"],
                        "possessions ≥10 seconds",
                        "var(--primary-light)", "bi-stopwatch",
                    ),
                    _mini_kpi(
                        "Total FT Entries", m.get("all_ft_entries", 0),
                        "entries into the final third",
                        "#0ea5e9", "bi-box-arrow-in-right",
                    ),
                    _mini_kpi(
                        "Qual. FT Entries", m["total_ft_entries"],
                        f"{m['ft_entry_pct']}% of qual. possessions",
                        "#06b6d4", "bi-box-arrow-in-right",
                    ),
                    _mini_kpi(
                        "Opp. Box Touches", m.get("box_touches", 0),
                        "total touches in penalty area",
                        "#ef4444", "bi-box-arrow-in-down-right",
                    ),
                    _tempo_card(m),
                ],
                className="team-kpi-row",
            ),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# C. CORRIDOR BREAKDOWN
# ═══════════════════════════════════════════════════════════════════════════════

def _section_corridor(m: dict) -> html.Div:
    counts = m["corridor_counts"]
    pcts   = m["corridor_pcts"]
    total  = m["total_ft_entries"] or 1

    # Stacked bar
    fig = go.Figure()
    for key in ("L", "C", "R"):
        pct = pcts[key]
        if counts[key] == 0:
            continue
        fig.add_trace(go.Bar(
            y=["Corridor"],
            x=[pct],
            orientation="h",
            name=CORRIDOR_LABELS[key],
            marker_color=CORRIDOR_COLORS[key],
            text=[f"{CORRIDOR_LABELS[key]} {pct}%"],
            textposition="inside",
            textfont=dict(size=11, color="#fff"),
            hovertemplate=f"{CORRIDOR_LABELS[key]}: {counts[key]} ({pct}%)<extra></extra>",
        ))
    fig.update_layout(
        barmode="stack",
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=0, b=0), height=42,
        xaxis=dict(showgrid=False, showticklabels=False,
                   range=[0, 100], fixedrange=True),
        yaxis=dict(showgrid=False, showticklabels=False, fixedrange=True),
        showlegend=False,
    )

    cards = []
    for key in ("L", "C", "R"):
        cards.append(
            html.Div(
                [
                    html.Div(
                        html.I(className="bi bi-arrows-expand-vertical",
                               style={"color": CORRIDOR_COLORS[key],
                                      "fontSize": "1.1rem"}),
                        className="kpi-icon",
                    ),
                    html.Div(
                        [
                            html.Span(CORRIDOR_LABELS[key], className="kpi-label"),
                            html.Span(str(counts[key]), className="kpi-value"),
                            html.Span(f"{pcts[key]}%", className="kpi-subtitle",
                                      style={"color": CORRIDOR_COLORS[key]}),
                        ],
                        className="kpi-text",
                    ),
                ],
                className="kpi-card",
            )
        )

    return html.Div(
        [
            html.H6("Entry by Corridor", className="buildup-subsection-title"),
            html.Div(cards, className="team-kpi-row"),
            dcc.Graph(figure=fig, config={"displayModeBar": False},
                      style={"marginTop": "0.5rem"}),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# D. ENTRY METHOD
# ═══════════════════════════════════════════════════════════════════════════════

def _section_methods(m: dict) -> html.Div:
    counts = m["method_counts"]
    pcts   = m["method_pcts"]
    total  = m["total_ft_entries"] or 1

    # Stacked bar
    bar_fig = go.Figure()
    for key in METHOD_ORDER:
        count = counts.get(key, 0)
        if count == 0:
            continue
        pct = pcts.get(key, 0.0)
        bar_fig.add_trace(go.Bar(
            y=["Method"],
            x=[pct],
            orientation="h",
            name=METHOD_LABELS[key],
            marker_color=METHOD_COLORS[key],
            text=[f"{pct}%"],
            textposition="inside",
            textfont=dict(size=10, color="#fff"),
            hovertemplate=f"{METHOD_LABELS[key]}: {count} ({pct}%)<extra></extra>",
        ))
    bar_fig.update_layout(
        barmode="stack",
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=0, b=0), height=42,
        xaxis=dict(showgrid=False, showticklabels=False,
                   range=[0, 100], fixedrange=True),
        yaxis=dict(showgrid=False, showticklabels=False, fixedrange=True),
        showlegend=False,
    )

    # KPI cards — only show methods with at least one entry
    cards = []
    for key in METHOD_ORDER:
        count = counts.get(key, 0)
        if count == 0:
            continue
        cards.append(
            html.Div(
                [
                    html.Div(
                        html.I(className=f"bi {METHOD_ICONS[key]}",
                               style={"color": METHOD_COLORS[key],
                                      "fontSize": "1.1rem"}),
                        className="kpi-icon",
                    ),
                    html.Div(
                        [
                            html.Span(METHOD_LABELS[key], className="kpi-label"),
                            html.Span(str(count), className="kpi-value"),
                            html.Span(
                                METHOD_DESCRIPTIONS.get(key, ""),
                                className="kpi-subtitle",
                                style={"color": "var(--text-muted)",
                                       "fontSize": "0.68rem"},
                            ),
                        ],
                        className="kpi-text",
                    ),
                ],
                className="kpi-card",
            )
        )

    return html.Div(
        [
            html.H6("How — Entry Method", className="buildup-subsection-title"),
            html.Div(
                "Priority: Transition → Through Ball → Switch of Play → "
                "Set-Piece → Long Ball → Cross Delivery → Carry → Short Pass",
                style={"fontSize": "0.78rem", "color": "var(--text-muted)",
                       "marginBottom": "0.6rem"},
            ),
            html.Div(cards, className="team-kpi-row"),
            dcc.Graph(figure=bar_fig, config={"displayModeBar": False},
                      style={"marginTop": "0.5rem"}),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# E. POST-ENTRY ZONE REACH
# ═══════════════════════════════════════════════════════════════════════════════

def _section_post_zones(m: dict) -> html.Div:
    zr    = m.get("zone_reach", {})
    total = m["total_ft_entries"] or 1

    # (label, zone_dict, color, icon, description, show_pct)
    items = [
        ("Zone 14",   zr.get("z14", {}),    "#8b5cf6",
         "bi-bullseye",
         "Entries reaching the central danger zone (Z14)", True),
        ("Flanks",    zr.get("flanks", {}), "#06b6d4",
         "bi-arrows-expand-vertical",
         "Entries using wide channels inside the final third (Z13/15/16/18)", True),
    ]

    cards = []
    for label, zone_d, color, icon, desc, show_pct in items:
        count = zone_d.get("count", 0)
        pct   = zone_d.get("pct", 0.0)
        count_span = [
            html.Span(f"{count}", style={
                "fontSize": "1.5rem", "fontWeight": "700",
                "color": color}),
        ]
        if show_pct:
            count_span.append(
                html.Span(f" / {total}  ({pct}%)", style={
                    "fontSize": "0.85rem",
                    "color": "var(--text-secondary)"}),
            )
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
                    html.Div(count_span, style={"marginTop": "6px"}),
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
            html.H6("Post-Entry Zone Reach", className="buildup-subsection-title"),
            html.Div(cards, className="outcome-cards-row"),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# F. OUTCOME OVERVIEW (Positive / Negative only — neutral excluded)
# ═══════════════════════════════════════════════════════════════════════════════

def _section_outcomes(m: dict) -> html.Div:
    outcomes = m.get("outcomes", {})
    total    = m["total_ft_entries"] or 1

    items = [
        ("positive", "Positive", OUTCOME_COLORS["positive"],
         "bi-check-circle-fill",
         "Retained ≥5 s OR shot / corner / foul / penalty / goal"),
        ("negative", "Negative", OUTCOME_COLORS["negative"],
         "bi-x-circle-fill",
         "Lost within ≤3 s OR foul conceded OR opponent restart"),
    ]

    cards = []
    for key, label, color, icon, desc in items:
        count = outcomes.get(key, {}).get("count", 0)
        pct   = outcomes.get(key, {}).get("pct", 0.0)
        cards.append(
            html.Div(
                [
                    html.Div(
                        [
                            html.I(className=f"bi {icon}",
                                   style={"color": color, "fontSize": "1.2rem"}),
                            html.Span(f"{count}", style={
                                "fontSize": "1.4rem", "fontWeight": "700",
                                "color": color}),
                        ],
                        style={"display": "flex", "alignItems": "center",
                               "gap": "8px"},
                    ),
                    html.Div(label, style={
                        "fontSize": "0.85rem", "fontWeight": "600",
                        "color": "var(--text-primary)", "marginTop": "4px"}),
                    html.Div(f"{pct}%", style={
                        "fontSize": "0.8rem", "color": color,
                        "fontWeight": "500"}),
                    html.Div(desc, style={
                        "fontSize": "0.7rem", "color": "var(--text-muted)",
                        "marginTop": "4px"}),
                ],
                className="outcome-card",
                style={"borderLeft": f"3px solid {color}"},
            )
        )

    return html.Div(
        [
            html.H6("Entry Outcomes (Positive / Negative)",
                    className="buildup-subsection-title"),
            html.Div(cards, className="outcome-cards-row"),
        ],
        className="buildup-outcome-summary",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# G. OUTCOME BY CORRIDOR
# ═══════════════════════════════════════════════════════════════════════════════

def _section_outcome_by_corridor(m: dict) -> html.Div:
    obc     = m.get("outcome_by_corridor", {})
    corridors = ["L", "C", "R"]

    pos_vals = [obc.get(c, {}).get("positive", 0) for c in corridors]
    neg_vals = [obc.get(c, {}).get("negative", 0) for c in corridors]
    labels   = [CORRIDOR_LABELS[c] for c in corridors]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=labels, x=pos_vals, orientation="h",
        name="Positive",
        marker_color=OUTCOME_COLORS["positive"],
        text=[str(v) if v > 0 else "" for v in pos_vals],
        textposition="inside",
        textfont=dict(size=10, color="#fff"),
        hovertemplate="Positive: %{x}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        y=labels, x=neg_vals, orientation="h",
        name="Negative",
        marker_color=OUTCOME_COLORS["negative"],
        text=[str(v) if v > 0 else "" for v in neg_vals],
        textposition="inside",
        textfont=dict(size=10, color="#fff"),
        hovertemplate="Negative: %{x}<extra></extra>",
    ))
    fig.update_layout(
        barmode="stack",
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=50, r=10, t=0, b=0), height=110,
        xaxis=dict(showgrid=False, showticklabels=False, fixedrange=True),
        yaxis=dict(showgrid=False, fixedrange=True,
                   tickfont=dict(color="#d0d0d0", size=10)),
        showlegend=False,
    )

    return html.Div(
        [
            html.H6("Outcomes by Corridor", className="buildup-subsection-title"),
            dcc.Graph(figure=fig, config={"displayModeBar": False}),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# H. OUTCOME BY METHOD
# ═══════════════════════════════════════════════════════════════════════════════

def _section_outcome_by_method(m: dict) -> html.Div:
    obm = m.get("outcome_by_method", {})

    # Only show methods that have at least one entry
    visible = [k for k in METHOD_ORDER
               if (obm.get(k, {}).get("positive", 0)
                   + obm.get(k, {}).get("negative", 0)) > 0]

    if not visible:
        return html.Div()

    pos_vals = [obm.get(k, {}).get("positive", 0) for k in visible]
    neg_vals = [obm.get(k, {}).get("negative", 0) for k in visible]
    labels   = [METHOD_LABELS[k] for k in visible]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=labels, x=pos_vals, orientation="h",
        name="Positive",
        marker_color=OUTCOME_COLORS["positive"],
        text=[str(v) if v > 0 else "" for v in pos_vals],
        textposition="inside",
        textfont=dict(size=10, color="#fff"),
        hovertemplate="Positive: %{x}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        y=labels, x=neg_vals, orientation="h",
        name="Negative",
        marker_color=OUTCOME_COLORS["negative"],
        text=[str(v) if v > 0 else "" for v in neg_vals],
        textposition="inside",
        textfont=dict(size=10, color="#fff"),
        hovertemplate="Negative: %{x}<extra></extra>",
    ))

    bar_height = max(110, len(visible) * 30)
    fig.update_layout(
        barmode="stack",
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=130, r=10, t=0, b=0), height=bar_height,
        xaxis=dict(showgrid=False, showticklabels=False, fixedrange=True),
        yaxis=dict(showgrid=False, fixedrange=True,
                   tickfont=dict(color="#d0d0d0", size=9)),
        showlegend=False,
    )

    return html.Div(
        [
            html.H6("Outcomes by Method", className="buildup-subsection-title"),
            dcc.Graph(figure=fig, config={"displayModeBar": False}),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# I. PITCH VISUALISATIONS
# ═══════════════════════════════════════════════════════════════════════════════

def _section_pitch_visuals(entries: list[dict], metrics: dict) -> html.Div:
    if not entries:
        return html.Div()

    return html.Div(
        [
            html.H6("Pitch Visualisations", className="buildup-subsection-title"),

            # Method scatter (hover) + Zone/Outcome heatmap (no hover)
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                "Entry Points — Method View",
                                style={"fontSize": "0.8rem",
                                       "color": "var(--text-secondary)",
                                       "marginBottom": "4px"},
                            ),
                            dcc.Graph(
                                figure=ft_entry_scatter_method(entries),
                                config={"displayModeBar": False},
                            ),
                        ],
                        style={"flex": "1", "minWidth": "0"},
                    ),
                    html.Div(
                        [
                            html.Div(
                                "FT Entry Zones & Outcomes  "
                                "(Z14 purple · flanks cyan)",
                                style={"fontSize": "0.8rem",
                                       "color": "var(--text-secondary)",
                                       "marginBottom": "4px"},
                            ),
                            dcc.Graph(
                                figure=ft_zone_outcome_heatmap(entries),
                                config={"displayModeBar": False},
                            ),
                        ],
                        style={"flex": "1", "minWidth": "0"},
                    ),
                ],
                style={"display": "flex", "gap": "1rem", "flexWrap": "wrap"},
                className="pitch-dark-container",
            ),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# FULL CARD ASSEMBLER
# ═══════════════════════════════════════════════════════════════════════════════

def final_third_card(data: dict) -> html.Div:
    """
    Assemble the complete Build-up to Final Third card.

    Parameters
    ----------
    data : dict
        Output of ``analyse_final_third()``.
        Must contain keys ``metrics`` and ``entries``.
    """
    m       = data.get("metrics", {})
    entries = data.get("entries", [])

    if m.get("total_ft_entries", 0) == 0 and m.get("qualifying_poss", 0) == 0:
        return html.Div(
            [
                html.H5("Build-up to Final Third",
                        className="buildup-card-title"),
                html.P(
                    "No qualifying possession data found for this team in this match.",
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
            html.H5("Build-up to Final Third", className="buildup-card-title"),
            # A — Possession & entry overview (incl. tempo KPIs)
            _section_possession(m),
            sep,
            # B — Corridor breakdown
            _section_corridor(m),
            sep,
            # C — Post-entry zones
            _section_post_zones(m),
            sep,
            # D — Entry method
            _section_methods(m),
            sep,
            # E — Pitch visualisations
            _section_pitch_visuals(entries, m),
            sep,
            # F — Outcomes
            _section_outcomes(m),
            sep,
            # G — Outcomes by corridor
            _section_outcome_by_corridor(m),
            sep,
            # H — Outcomes by method
            _section_outcome_by_method(m),
        ],
        className="buildup-card",
    )
