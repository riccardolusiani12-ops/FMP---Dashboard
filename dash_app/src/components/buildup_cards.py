"""
Build-up Analysis UI Components  (v4 — Goal Kicks)
====================================================
Dash components for the Goal-Kick Build-up card inside
Offensive Phase → Build-up.

Only goal kicks (Opta "Goal Kick" == "Si") are counted.
Follows the existing dashboard visual identity.

v4 adds:
  - Granular outcome cards (P1/P2/P3, N1/N2/N3)
  - Event chain visualisation per goal kick distribution
"""

from __future__ import annotations

from dash import html, dcc
import plotly.graph_objects as go

from src.styling.plotly_template import apply_chart_theme
from src.styling.ui_components import ds_header

from src.components.pitch_zones import pitch_zone_figure, OUTCOME_COLORS


# ═══════════════════════════════════════════════════════════════════════════════
# A. BUILD-UP TYPE SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════

def buildup_type_summary(data: dict) -> html.Div:
    """
    Render the short vs long build-up summary using KPI-style cards
    and a horizontal stacked bar.
    """
    total = data.get("total", 0)
    short_count = data.get("short_count", 0)
    long_count = data.get("long_count", 0)
    short_pct = data.get("short_pct", 0)
    long_pct = data.get("long_pct", 0)

    # Stacked bar figure
    bar_fig = go.Figure()
    bar_fig.add_trace(go.Bar(
        y=["Build-up"],
        x=[short_pct],
        orientation="h",
        name="Short",
        marker_color="#3b82f6",
        text=[f"{short_pct}%"],
        textposition="inside",
        textfont=dict(size=12, color="#fff"),
        hovertemplate="Short: %{x:.1f}%<extra></extra>",
    ))
    bar_fig.add_trace(go.Bar(
        y=["Build-up"],
        x=[long_pct],
        orientation="h",
        name="Long",
        marker_color="#f97316",
        text=[f"{long_pct}%"],
        textposition="inside",
        textfont=dict(size=12, color="#fff"),
        hovertemplate="Long: %{x:.1f}%<extra></extra>",
    ))
    apply_chart_theme(bar_fig, "dark")
    bar_fig.update_layout(
        barmode="stack",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=0, b=0),
        height=42,
        xaxis=dict(showgrid=False, showticklabels=False, range=[0, 100], fixedrange=True),
        yaxis=dict(showgrid=False, showticklabels=False, fixedrange=True),
        showlegend=False,
    )

    return html.Div(
        [
            html.H6("Build-up Type", className="buildup-subsection-title"),
            html.Div(
                [
                    # Short KPI
                    html.Div(
                        [
                            html.Div(
                                html.I(className="bi bi-arrow-down-short",
                                       style={"color": "#3b82f6", "fontSize": "1.3rem"}),
                                className="kpi-icon",
                            ),
                            html.Div(
                                [
                                    html.Span("Short", className="kpi-label"),
                                    html.Span(f"{short_count}", className="kpi-value"),
                                    html.Span(f"{short_pct}%",
                                              className="kpi-subtitle",
                                              style={"color": "#3b82f6"}),
                                ],
                                className="kpi-text",
                            ),
                        ],
                        className="kpi-card",
                    ),
                    # Long KPI
                    html.Div(
                        [
                            html.Div(
                                html.I(className="bi bi-arrow-up-right",
                                       style={"color": "#f97316", "fontSize": "1.3rem"}),
                                className="kpi-icon",
                            ),
                            html.Div(
                                [
                                    html.Span("Long", className="kpi-label"),
                                    html.Span(f"{long_count}", className="kpi-value"),
                                    html.Span(f"{long_pct}%",
                                              className="kpi-subtitle",
                                              style={"color": "#f97316"}),
                                ],
                                className="kpi-text",
                            ),
                        ],
                        className="kpi-card",
                    ),
                    # Total KPI
                    html.Div(
                        [
                            html.Div(
                                html.I(className="bi bi-bullseye",
                                       style={"color": "var(--primary-light)", "fontSize": "1.3rem"}),
                                className="kpi-icon",
                            ),
                            html.Div(
                                [
                                    html.Span("Total", className="kpi-label"),
                                    html.Span(f"{total}", className="kpi-value"),
                                    html.Span("distributions",
                                              className="kpi-subtitle"),
                                ],
                                className="kpi-text",
                            ),
                        ],
                        className="kpi-card",
                    ),
                ],
                className="team-kpi-row",
            ),
            # Stacked bar
            dcc.Graph(
                figure=bar_fig,
                config={"displayModeBar": False},
                style={"marginTop": "0.5rem"},
            ),
        ],
        className="buildup-type-summary",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# B. TARGET ZONE DISTRIBUTION
# ═══════════════════════════════════════════════════════════════════════════════

def target_zone_distribution(data: dict) -> html.Div:
    """Render the 18-zone pitch visualisation."""
    zone_counts = data.get("zone_counts", {})
    zone_outcomes = data.get("zone_outcomes", {})

    fig = pitch_zone_figure(
        zone_counts=zone_counts,
        zone_outcomes=zone_outcomes,
        title="Goal Kick — First Receiver Zones",
    )

    return html.Div(
        [
            html.H6("First Receiver Zone Distribution", className="buildup-subsection-title"),
            html.Div(
                dcc.Graph(
                    figure=fig,
                    config={"displayModeBar": False},
                ),
                className="pitch-dark-container",
            ),
        ],
        className="buildup-zone-distribution",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# C. OUTCOME LAYER  — Granular (P1/P2/P3, N1/N2/N3)
# ═══════════════════════════════════════════════════════════════════════════════

# Tier definitions (code, label, colour, icon, short description)
_GRANULAR_TIERS = [
    # ── Positive tiers (ascending quality) ──
    ("P1", "Established Possession",    "#22c55e", "bi-check-circle-fill",
     "Kept the ball ≥15 s without leaving own half"),
    ("P2", "Reached Final Third",       "#16a34a", "bi-arrow-up-right-circle-fill",
     "Kept the ball ≥15 s and reached the final third"),
    ("P3", "Created a Shot",            "#15803d", "bi-bullseye",
     "Retained possession and produced a shot attempt"),
    # ── Negative tiers (ascending severity) ──
    ("N1", "Possession Lost",           "#f97316", "bi-x-circle-fill",
     "Opponent recovered without entering the box or shooting"),
    ("N2", "Box Entry Conceded",        "#ef4444", "bi-exclamation-triangle-fill",
     "Opponent entered the penalty area after recovery"),
    ("N3", "Shot Conceded",             "#dc2626", "bi-shield-exclamation",
     "Opponent produced a shot attempt after recovery"),
]


def granular_outcome_summary(data: dict) -> html.Div:
    """Render the 6-tier outcome classification as a sunburst chart."""
    gc = data.get("granular_counts", {})
    total = data.get("total", 0) or 1

    # Compute positive / negative totals
    pos_total = sum(gc.get(c, 0) for c in ("P1", "P2", "P3"))
    neg_total = sum(gc.get(c, 0) for c in ("N1", "N2", "N3"))

    C_BG  = "rgba(15,25,35,0.95)"
    C_POS = "#22c55e"
    C_NEG = "#ef4444"

    TIER_COLORS = {
        "P1": "#22c55e", "P2": "#16a34a", "P3": "#15803d",
        "N1": "#f97316", "N2": "#ef4444", "N3": "#dc2626",
    }

    # Build sunburst data
    labels  = [f"Total: {total}"]
    parents = [""]
    values  = [total]
    colors  = [C_BG]

    pos_lbl = f"Positive: {pos_total} ({round(pos_total / total * 100)}%)"
    neg_lbl = f"Negative: {neg_total} ({round(neg_total / total * 100)}%)"

    labels.append(pos_lbl)
    parents.append(f"Total: {total}")
    values.append(pos_total)
    colors.append(C_POS)

    labels.append(neg_lbl)
    parents.append(f"Total: {total}")
    values.append(neg_total)
    colors.append(C_NEG)

    for code, label, color, _icon, _desc in _GRANULAR_TIERS:
        c = gc.get(code, 0)
        labels.append(f"{code}: {c}")
        parents.append(pos_lbl if code.startswith("P") else neg_lbl)
        values.append(c)
        colors.append(TIER_COLORS[code])

    fig = go.Figure(go.Sunburst(
        labels=labels,
        parents=parents,
        values=values,
        branchvalues="total",
        marker=dict(colors=colors, line=dict(color=C_BG, width=2)),
        textfont=dict(size=11, color="white"),
        insidetextorientation="radial",
    ))
    apply_chart_theme(fig, "dark")
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        height=380,
        margin=dict(l=10, r=10, t=10, b=10),
    )

    # Build glossary legend
    pos_items = []
    neg_items = []
    for code, label, color, icon, desc in _GRANULAR_TIERS:
        count = gc.get(code, 0)
        pct = round(count / total * 100, 1) if total else 0
        item = html.Div(
            [
                html.Div(
                    [
                        html.Span(code, style={
                            "fontSize": "0.68rem", "fontWeight": "700",
                            "color": color, "padding": "1px 6px",
                            "borderRadius": "3px", "background": f"{color}18",
                            "marginRight": "6px",
                        }),
                        html.Span(f"{count}", style={
                            "fontSize": "0.95rem", "fontWeight": "700",
                            "color": color, "marginRight": "4px",
                        }),
                        html.Span(f"({pct}%)", style={
                            "fontSize": "0.72rem", "color": "var(--text-muted)",
                        }),
                    ],
                    style={"display": "flex", "alignItems": "center"},
                ),
                html.Div(label, style={
                    "fontSize": "0.78rem", "fontWeight": "600",
                    "color": "var(--text-primary)", "marginTop": "2px",
                }),
                html.Div(desc, style={
                    "fontSize": "0.65rem", "color": "var(--text-muted)",
                    "lineHeight": "1.3", "marginTop": "1px",
                }),
            ],
            style={"paddingBottom": "0.5rem"},
        )
        if code.startswith("P"):
            pos_items.append(item)
        else:
            neg_items.append(item)

    glossary = html.Div(
        [
            # Positive header
            html.Div(
                [
                    html.I(className="bi bi-check-circle-fill",
                           style={"color": "#22c55e", "fontSize": "0.8rem"}),
                    html.Span("Positive", style={
                        "fontSize": "0.72rem", "fontWeight": "600",
                        "textTransform": "uppercase", "letterSpacing": "0.6px",
                        "color": "#22c55e",
                    }),
                ],
                style={"display": "flex", "alignItems": "center", "gap": "5px",
                       "marginBottom": "0.4rem"},
            ),
            *pos_items,
            # Negative header
            html.Div(
                [
                    html.I(className="bi bi-x-circle-fill",
                           style={"color": "#ef4444", "fontSize": "0.8rem"}),
                    html.Span("Negative", style={
                        "fontSize": "0.72rem", "fontWeight": "600",
                        "textTransform": "uppercase", "letterSpacing": "0.6px",
                        "color": "#ef4444",
                    }),
                ],
                style={"display": "flex", "alignItems": "center", "gap": "5px",
                       "marginTop": "0.6rem", "marginBottom": "0.4rem"},
            ),
            *neg_items,
        ],
        style={"flex": "1", "minWidth": "180px", "display": "flex",
               "flexDirection": "column", "justifyContent": "center"},
    )

    return html.Div(
        [
            html.H6("Outcome Classification", className="buildup-subsection-title"),
            html.Div(
                [
                    # Sunburst chart — left
                    html.Div(
                        dcc.Graph(figure=fig, config={"displayModeBar": False}),
                        style={"flex": "1.2", "minWidth": "260px"},
                    ),
                    # Glossary — right
                    glossary,
                ],
                style={"display": "flex", "gap": "1rem", "alignItems": "center",
                       "flexWrap": "wrap"},
            ),
        ],
        className="buildup-outcome-summary",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# D. EVENT CHAIN VISUALISATION
# ═══════════════════════════════════════════════════════════════════════════════

# Map event types to connector style
_PASS_EVENTS = frozenset({"pass", "blocked pass", "offside pass"})
_SHOT_EVENTS = frozenset({"miss", "saved shot", "goal", "save"})

# Granular tier → colour and label
_TIER_META: dict[str, tuple[str, str]] = {
    "P1": ("#22c55e", "Established Possession"),
    "P2": ("#16a34a", "Reached Final Third"),
    "P3": ("#15803d", "Created a Shot"),
    "N1": ("#f97316", "Possession Lost"),
    "N2": ("#ef4444", "Box Entry Conceded"),
    "N3": ("#dc2626", "Shot Conceded"),
}


def _chain_event_node(evt: dict, idx: int, total: int) -> html.Div:
    """Render a single event node in the chain."""
    is_team = evt.get("is_team", True)
    et = str(evt.get("event_type", "")).strip().lower()
    player = evt.get("player", "?")

    # Node colours
    bg = "rgba(34,197,94,0.12)" if is_team else "rgba(239,68,68,0.12)"
    border_col = "#22c55e" if is_team else "#ef4444"
    text_col = "#d1fae5" if is_team else "#fecaca"

    # Event icon
    if et in _PASS_EVENTS:
        icon_cls = "bi bi-arrow-right"
    elif et in _SHOT_EVENTS or et == "goal":
        icon_cls = "bi bi-bullseye"
    elif et in ("aerial",):
        icon_cls = "bi bi-arrow-up"
    elif et in ("tackle", "interception", "ball recovery"):
        icon_cls = "bi bi-shield-fill"
    elif et in ("foul",):
        icon_cls = "bi bi-exclamation-circle"
    else:
        icon_cls = "bi bi-circle-fill"

    # Short event label
    short_et = {
        "pass": "Pass", "ball touch": "Touch", "take on": "Take On",
        "aerial": "Aerial", "tackle": "Tackle", "interception": "Int.",
        "ball recovery": "Recovery", "clearance": "Clear",
        "miss": "Shot", "saved shot": "Shot", "goal": "Goal",
        "blocked pass": "Blk Pass", "foul": "Foul", "out": "Out",
        "dispossessed": "Disp.", "offside pass": "Offside",
        "error": "Error", "save": "Save",
    }.get(et, et.title())

    return html.Div(
        [
            # Player name
            html.Div(player, style={
                "fontSize": "0.68rem", "fontWeight": "600",
                "color": text_col, "whiteSpace": "nowrap",
                "overflow": "hidden", "textOverflow": "ellipsis",
                "maxWidth": "80px", "textAlign": "center",
            }),
            # Icon circle
            html.Div(
                html.I(className=icon_cls, style={
                    "fontSize": "0.65rem", "color": border_col,
                }),
                style={
                    "width": "26px", "height": "26px",
                    "borderRadius": "50%", "background": bg,
                    "border": f"2px solid {border_col}",
                    "display": "flex", "alignItems": "center",
                    "justifyContent": "center", "margin": "3px auto",
                },
            ),
            # Event type label
            html.Div(short_et, style={
                "fontSize": "0.58rem", "color": "var(--text-muted)",
                "textAlign": "center", "whiteSpace": "nowrap",
            }),
        ],
        style={"display": "flex", "flexDirection": "column",
               "alignItems": "center", "minWidth": "50px"},
    )


def _chain_connector(evt: dict) -> html.Div:
    """Render a connector arrow/dashed line between two chain nodes."""
    et = str(evt.get("event_type", "")).strip().lower()
    is_pass = et in _PASS_EVENTS

    # Solid arrow for passes, dashed for carries/touches
    style = {
        "display": "flex", "alignItems": "center",
        "margin": "0 -2px", "paddingTop": "8px",
    }

    if is_pass:
        # Solid arrow line
        return html.Div(
            [
                html.Div(style={
                    "width": "18px", "height": "2px",
                    "background": "rgba(255,255,255,0.3)",
                }),
                html.I(className="bi bi-caret-right-fill", style={
                    "fontSize": "0.5rem", "color": "rgba(255,255,255,0.3)",
                    "marginLeft": "-3px",
                }),
            ],
            style=style,
        )
    else:
        # Dashed line for carries / touches
        return html.Div(
            [
                html.Div(style={
                    "width": "18px", "height": "0px",
                    "borderTop": "2px dashed rgba(255,255,255,0.2)",
                }),
                html.I(className="bi bi-caret-right-fill", style={
                    "fontSize": "0.5rem", "color": "rgba(255,255,255,0.2)",
                    "marginLeft": "-3px",
                }),
            ],
            style=style,
        )


def _single_chain_card(event_rec: dict, idx: int) -> html.Div:
    """
    Render a single goal kick's chain of events as a horizontal
    scrollable strip.
    """
    chain = event_rec.get("chain", [])
    granular = event_rec.get("granular_outcome", "N1")
    outcome = event_rec.get("outcome", "negative")
    minute = int(event_rec.get("minute", 0))
    second = int(event_rec.get("second", 0))
    gk_player = event_rec.get("gk_player", "GK")
    pass_type = event_rec.get("pass_type", "short")

    tier_color, tier_label = _TIER_META.get(granular, ("#888", "Unknown"))

    # Build chain nodes
    chain_elements = []
    for i, evt in enumerate(chain):
        if i > 0:
            chain_elements.append(_chain_connector(evt))
        chain_elements.append(_chain_event_node(evt, i, len(chain)))

    # Header: GK #n · Mm:ss · Short/Long · Outcome badge
    header = html.Div(
        [
            html.Span(f"#{idx + 1}", style={
                "fontWeight": "700", "fontSize": "0.8rem",
                "color": "var(--text-primary)", "marginRight": "8px",
            }),
            html.I(className="bi bi-clock", style={
                "fontSize": "0.7rem", "color": "var(--text-muted)",
            }),
            html.Span(f" {minute}:{second:02d}", style={
                "fontSize": "0.75rem", "color": "var(--text-secondary)",
                "marginRight": "10px",
            }),
            html.Span(gk_player, style={
                "fontSize": "0.75rem", "color": "var(--text-primary)",
                "fontWeight": "500", "marginRight": "10px",
            }),
            # Short/Long badge
            html.Span(
                pass_type.capitalize(),
                style={
                    "fontSize": "0.62rem", "fontWeight": "600",
                    "textTransform": "uppercase", "letterSpacing": "0.5px",
                    "padding": "2px 8px", "borderRadius": "4px",
                    "background": "#3b82f618" if pass_type == "short" else "#f9731618",
                    "color": "#3b82f6" if pass_type == "short" else "#f97316",
                    "marginRight": "8px",
                },
            ),
            # Granular outcome badge
            html.Span(
                f"{granular} — {tier_label}",
                style={
                    "fontSize": "0.62rem", "fontWeight": "600",
                    "padding": "2px 8px", "borderRadius": "4px",
                    "background": f"{tier_color}18",
                    "color": tier_color,
                },
            ),
        ],
        style={"display": "flex", "alignItems": "center", "gap": "4px",
               "marginBottom": "8px", "flexWrap": "wrap"},
    )

    return html.Div(
        [
            header,
            # Scrollable chain strip
            html.Div(
                chain_elements,
                className="chain-strip",
            ),
        ],
        className="chain-card",
        style={"borderLeft": f"3px solid {tier_color}"},
    )


def event_chain_section(data: dict) -> html.Div:
    """Render all goal kick event chains inside a collapsible section."""
    events = data.get("events", [])
    if not events:
        return html.Div()

    chain_cards = [
        _single_chain_card(evt, i)
        for i, evt in enumerate(events)
    ]

    return html.Details(
        [
            html.Summary(
                [
                    html.I(className="bi bi-link-45deg",
                           style={"marginRight": "6px", "fontSize": "1rem"}),
                    html.Span("Distribution Chains",
                              style={"fontWeight": "600", "fontSize": "0.85rem"}),
                    html.Span(f" ({len(events)})",
                              style={"color": "var(--text-muted)", "fontSize": "0.8rem"}),
                ],
                className="buildup-subsection-title",
                style={"cursor": "pointer", "listStyle": "none",
                       "display": "flex", "alignItems": "center",
                       "userSelect": "none"},
            ),
            html.Div(
                chain_cards,
                style={"display": "flex", "flexDirection": "column",
                       "gap": "0.75rem", "marginTop": "0.75rem"},
            ),
        ],
        className="buildup-chains-section",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# FULL BUILD-UP CARD
# ═══════════════════════════════════════════════════════════════════════════════

def goalkeeper_buildup_card(data: dict) -> html.Div:
    """
    Assemble the full Build-up from Goal Kicks card.
    Combines three sub-sections (A–C).
    """
    _header = ds_header(
        "Build-up — Goal Kicks", "bi-diagram-3",
        "Build-up from Goal Kicks",
        "Short vs long distribution, first-receiver zones, outcomes and "
        "event chains",
    )

    if data.get("total", 0) == 0:
        return html.Div(
            [
                _header,
                html.P(
                    "No goal kicks found for this team in this match.",
                    className="text-muted",
                    style={"padding": "2rem", "textAlign": "center"},
                ),
            ],
            className="buildup-card ma-card",
        )

    return html.Div(
        [
            _header,
            buildup_type_summary(data),
            html.Hr(style={"borderColor": "var(--border-light)", "margin": "1.5rem 0"}),
            target_zone_distribution(data),
            html.Hr(style={"borderColor": "var(--border-light)", "margin": "1.5rem 0"}),
            granular_outcome_summary(data),
            html.Hr(style={"borderColor": "var(--border-light)", "margin": "1.5rem 0"}),
            event_chain_section(data),
        ],
        className="buildup-card ma-card",
    )
