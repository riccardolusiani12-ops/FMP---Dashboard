"""
Defensive Phase — D3: Defensive Castle UI Components
=====================================================
Dash layout components for the Defensive Castle card.

Sections rendered:
  A — Overview KPIs     (total actions + sub-zone breakdown)
  B — Actions by Type   (KPI cards + stacked bar)
  C — Corridor Split    (KPI cards + stacked bar)
  D — Pitch Maps        (side-by-side)
        Left  — scatter: all events coloured by action type
        Right — zone heatmap: count per zone + colour intensity

Follows the exact same visual patterns as defensive_pressing_cards.py.
"""

from __future__ import annotations

from dash import html, dcc
import plotly.graph_objects as go

# ═══════════════════════════════════════════════════════════════════════════════
# PALETTE
# ═══════════════════════════════════════════════════════════════════════════════

PRIMARY       = "#8a1f33"
SUCCESS_COLOR = "#22c55e"
FAIL_COLOR    = "#ef4444"

# Action type colours
ACTION_COLORS: dict[str, str] = {
    "Tackle":        "#3b82f6",   # blue
    "Interception":  "#22c55e",   # green
    "Clearance":     "#f59e0b",   # amber
    "Aerial":        "#06b6d4",   # cyan
    "Ball Recovery": "#8b5cf6",   # purple
    "Challenge":     "#ec4899",   # pink
    "Foul":          "#f97316",   # orange
    "Blocked Pass":  "#84cc16",   # lime
}

ACTION_ICONS: dict[str, str] = {
    "Tackle":        "bi-shield-fill-check",
    "Interception":  "bi-hand-index-thumb-fill",
    "Clearance":     "bi-arrow-up-circle-fill",
    "Aerial":        "bi-arrows-collapse-vertical",
    "Ball Recovery": "bi-arrow-counterclockwise",
    "Challenge":     "bi-person-fill-slash",
    "Foul":          "bi-exclamation-triangle-fill",
    "Blocked Pass":  "bi-ban",
}

CORRIDOR_COLORS = {"L": "#3b82f6", "C": "#8b5cf6", "R": "#06b6d4"}
CORRIDOR_LABELS = {"L": "Left", "C": "Centre", "R": "Right"}

SUBZONE_COLORS = {
    "box":            "#ef4444",
    "deep_flank":     "#f97316",
    "def_third_edge": "#6b7280",
}
SUBZONE_LABELS = {
    "box":            "Own Box",
    "deep_flank":     "Wide Flanks",
    "def_third_edge": "Def. Third Edge",
}

# Zone grid edges (full pitch, 18 zones — 6 rows × 3 cols)
_X_EDGES = [0.0, 16.67, 33.33, 50.0, 66.67, 83.33, 100.0]
_Y_EDGES = [0.0, 33.33, 66.67, 100.0]


# ═══════════════════════════════════════════════════════════════════════════════
# SHARED HELPERS
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


def _hr() -> html.Hr:
    return html.Hr(style={"borderColor": "var(--border-light)", "margin": "1.5rem 0"})


# ═══════════════════════════════════════════════════════════════════════════════
# PITCH DRAWING HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_full_pitch(fig: go.Figure) -> None:
    """Add standard dark-theme full-pitch markings to *fig* in-place."""
    fig.add_shape(
        type="rect", x0=0, x1=100, y0=0, y1=100,
        line=dict(color="rgba(255,255,255,0.35)", width=1.5),
        fillcolor="rgba(0,0,0,0)", layer="below",
    )
    for y_val in (33.33, 66.67):
        fig.add_shape(
            type="line", x0=0, x1=100, y0=y_val, y1=y_val,
            line=dict(color="rgba(255,255,255,0.10)", width=1), layer="below",
        )
    for x_val in _X_EDGES[1:-1]:
        fig.add_shape(
            type="line", x0=x_val, x1=x_val, y0=0, y1=100,
            line=dict(color="rgba(255,255,255,0.07)", width=1), layer="below",
        )
    # Halfway line
    fig.add_shape(
        type="line", x0=50, x1=50, y0=0, y1=100,
        line=dict(color="rgba(255,255,255,0.22)", width=1, dash="dash"),
        layer="below",
    )
    # Own penalty box
    fig.add_shape(
        type="rect", x0=0, x1=16.5, y0=21, y1=79,
        line=dict(color="rgba(255,255,255,0.35)", width=1.5),
        fillcolor="rgba(0,0,0,0)",
    )
    # Attacking penalty box
    fig.add_shape(
        type="rect", x0=83.5, x1=100, y0=21, y1=79,
        line=dict(color="rgba(255,255,255,0.10)", width=1),
        fillcolor="rgba(0,0,0,0)",
    )
    # Highlight defensive third band
    fig.add_shape(
        type="rect", x0=0, x1=33.33, y0=0, y1=100,
        line=dict(color="rgba(239,68,68,0.20)", width=1),
        fillcolor="rgba(239,68,68,0.04)", layer="below",
    )
    # Direction labels
    fig.add_annotation(
        x=94, y=-6, text="ATK →", showarrow=False,
        font=dict(size=9, color="rgba(255,255,255,0.30)"),
    )
    fig.add_annotation(
        x=6, y=-6, text="← OWN GOAL", showarrow=False,
        font=dict(size=9, color="rgba(255,255,255,0.30)"),
    )
    # Corridor labels
    for label, y_centre in (("Right", 16.67), ("Centre", 50.0), ("Left", 83.33)):
        fig.add_annotation(
            x=1, y=y_centre, text=label, showarrow=False, textangle=-90,
            font=dict(size=8, color="rgba(255,255,255,0.18)"),
        )


def _pitch_layout(
    fig: go.Figure,
    title: str,
    height: int = 430,
    show_legend: bool = True,
) -> None:
    fig.update_layout(
        title=dict(text=title, font=dict(size=13, color="#f0f0f0"), x=0.5),
        xaxis=dict(range=[-2, 102], showgrid=False, zeroline=False,
                   showticklabels=False, fixedrange=True),
        yaxis=dict(range=[-12, 106], showgrid=False, zeroline=False,
                   showticklabels=False, fixedrange=True,
                   scaleanchor="x", scaleratio=0.68),
        plot_bgcolor="rgba(15,25,35,0.7)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=120, t=40, b=20),
        height=height,
        showlegend=show_legend,
        legend=dict(
            orientation="v", yanchor="middle", y=0.5,
            xanchor="left", x=1.01,
            font=dict(size=10, color="#d0d0d0"),
            bgcolor="rgba(15,25,35,0.8)",
            bordercolor="rgba(255,255,255,0.1)",
            borderwidth=1,
        ),
        font=dict(color="var(--text-secondary)"),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# A. OVERVIEW KPIs
# ═══════════════════════════════════════════════════════════════════════════════

def _section_overview(d: dict) -> html.Div:
    total = d.get("total_actions", 0)
    box_n   = d.get("by_subzone", {}).get("box", 0)
    deep_n  = d.get("by_subzone", {}).get("deep_flank", 0)
    edge_n  = d.get("by_subzone", {}).get("def_third_edge", 0)

    return html.Div(
        [
            html.H6("Overview", className="buildup-subsection-title"),
            html.Div(
                [
                    _mini_kpi(
                        "Def. Actions in 1st Third", total,
                        "tackles · clearances · interceptions · aerials · recoveries",
                        PRIMARY, "bi-shield-fill",
                    ),
                    _mini_kpi(
                        "In Own Box", box_n,
                        f"{d.get('box_pct', 0.0)}% — inside penalty area",
                        SUBZONE_COLORS["box"], "bi-pentagon-fill",
                    ),
                    _mini_kpi(
                        "Wide Flanks", deep_n,
                        f"{d.get('deep_flank_pct', 0.0)}% — flanks near box",
                        SUBZONE_COLORS["deep_flank"], "bi-arrows-expand",
                    ),
                    _mini_kpi(
                        "Def. Third Edge", edge_n,
                        f"{d.get('def_third_edge_pct', 0.0)}% — 17–33 m line",
                        SUBZONE_COLORS["def_third_edge"], "bi-chevron-right",
                    ),
                ],
                className="team-kpi-row",
            ),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# B. ACTIONS BY TYPE
# ═══════════════════════════════════════════════════════════════════════════════

def _section_by_type(d: dict) -> html.Div:
    by_type     = d.get("by_type", {})
    by_type_pct = d.get("by_type_pct", {})
    total       = d.get("total_actions", 1) or 1

    # Stacked bar (all types that have ≥1 action)
    fig = go.Figure()
    ordered_types = sorted(by_type.items(), key=lambda x: -x[1])
    for name, count in ordered_types:
        if count == 0:
            continue
        pct   = by_type_pct.get(name, 0.0)
        color = ACTION_COLORS.get(name, "#94a3b8")
        fig.add_trace(go.Bar(
            y=["Actions"],
            x=[pct],
            orientation="h",
            name=name,
            marker_color=color,
            text=[f"{name} {pct}%"],
            textposition="inside",
            textfont=dict(size=10, color="#fff"),
            hovertemplate=f"{name}: {count} ({pct}%)<extra></extra>",
        ))
    fig.update_layout(
        barmode="stack",
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=0, b=0), height=42,
        xaxis=dict(showgrid=False, showticklabels=False, range=[0, 100], fixedrange=True),
        yaxis=dict(showgrid=False, showticklabels=False, fixedrange=True),
        showlegend=False,
    )

    # KPI mini-cards for the top types
    kpi_cards = []
    for name, count in ordered_types[:6]:
        pct   = by_type_pct.get(name, 0.0)
        color = ACTION_COLORS.get(name, "#94a3b8")
        icon  = ACTION_ICONS.get(name, "bi-activity")
        kpi_cards.append(
            _mini_kpi(name, count, f"{pct}% of defensive actions", color, icon)
        )

    return html.Div(
        [
            html.H6("Actions by Type", className="buildup-subsection-title"),
            html.Div(kpi_cards, className="team-kpi-row"),
            dcc.Graph(
                figure=fig,
                config={"displayModeBar": False},
                style={"marginTop": "0.5rem"},
            ),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# C. CORRIDOR SPLIT
# ═══════════════════════════════════════════════════════════════════════════════

def _section_corridor(d: dict) -> html.Div:
    counts = d.get("by_corridor", {"L": 0, "C": 0, "R": 0})
    pcts   = d.get("by_corridor_pct", {"L": 0.0, "C": 0.0, "R": 0.0})

    fig = go.Figure()
    for key in ("L", "C", "R"):
        if counts[key] == 0:
            continue
        fig.add_trace(go.Bar(
            y=["Corridor"],
            x=[pcts[key]],
            orientation="h",
            name=CORRIDOR_LABELS[key],
            marker_color=CORRIDOR_COLORS[key],
            text=[f"{CORRIDOR_LABELS[key]} {pcts[key]}%"],
            textposition="inside",
            textfont=dict(size=11, color="#fff"),
            hovertemplate=(
                f"{CORRIDOR_LABELS[key]}: {counts[key]} ({pcts[key]}%)<extra></extra>"
            ),
        ))
    fig.update_layout(
        barmode="stack",
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=0, b=0), height=42,
        xaxis=dict(showgrid=False, showticklabels=False, range=[0, 100], fixedrange=True),
        yaxis=dict(showgrid=False, showticklabels=False, fixedrange=True),
        showlegend=False,
    )

    kpi_cards = [
        _mini_kpi(
            CORRIDOR_LABELS[k], counts[k],
            f"{pcts[k]}% of actions",
            CORRIDOR_COLORS[k], "bi-arrows-expand-vertical",
        )
        for k in ("L", "C", "R")
    ]

    return html.Div(
        [
            html.H6("Defensive Corridor", className="buildup-subsection-title"),
            html.Div(kpi_cards, className="team-kpi-row"),
            dcc.Graph(
                figure=fig,
                config={"displayModeBar": False},
                style={"marginTop": "0.5rem"},
            ),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# D1. SCATTER PITCH MAP  — events coloured by action type
# ═══════════════════════════════════════════════════════════════════════════════

def _build_castle_scatter(detail: list[dict]) -> go.Figure:
    """Full-pitch scatter with all Defensive Castle events coloured by type."""
    fig = go.Figure()

    grouped: dict[str, list[tuple]] = {}
    for rec in detail:
        act = rec.get("action", "Unknown")
        x   = rec.get("x")
        y   = rec.get("y")
        if x is None or y is None:
            continue
        label = f"{rec.get('minute', 0)}' {rec.get('player', '?')} — {rec.get('subzone', '')}"
        grouped.setdefault(act, []).append((x, y, label))

    for act, pts in sorted(grouped.items(), key=lambda kv: -len(kv[1])):
        color = ACTION_COLORS.get(act, "#94a3b8")
        fig.add_trace(go.Scatter(
            x=[p[0] for p in pts],
            y=[p[1] for p in pts],
            mode="markers",
            name=act,
            marker=dict(
                color=color, size=9, opacity=0.85,
                line=dict(color="rgba(255,255,255,0.35)", width=0.5),
            ),
            hovertemplate=(
                f"<b>{act}</b><br>"
                "x=%{x:.1f} · y=%{y:.1f}<br>"
                "%{text}<extra></extra>"
            ),
            text=[p[2] for p in pts],
        ))

    _draw_full_pitch(fig)
    _pitch_layout(fig, "Defensive Actions — All Events", height=430, show_legend=True)
    return fig


# ═══════════════════════════════════════════════════════════════════════════════
# D2. ZONE HEATMAP — count per zone + colour shading
# ═══════════════════════════════════════════════════════════════════════════════

def _build_castle_heatmap(zone_counts: dict[int, int]) -> go.Figure:
    """
    Full-pitch zone heatmap.

    Only the 6 zones in the defensive third (zones 1-6) are shaded.
    Each zone shows the action count; zones outside the defensive third
    are drawn in neutral grey (no data expected there).
    """
    fig = go.Figure()

    _ROWS = 6
    _COLS = 3

    # Consider only defensive-third zones for the max scale
    def_counts = {z: v for z, v in zone_counts.items() if z <= 6}
    max_count  = max(def_counts.values(), default=1) or 1

    for zone_num in range(1, 19):
        row = (zone_num - 1) // _COLS   # 0-5  (x bands)
        col = (zone_num - 1) % _COLS    # 0-2  (y bands)
        x0 = _X_EDGES[row]
        x1 = _X_EDGES[row + 1]
        y0 = _Y_EDGES[col]
        y1 = _Y_EDGES[col + 1]
        count = zone_counts.get(zone_num, 0)

        if zone_num <= 6:
            # Defensive third — apply crimson-intensity gradient
            intensity = count / max_count
            r = int(27  + (180 - 27)  * intensity)
            g = int(40  + (20  - 40)  * intensity)
            b = int(56  + (40  - 56)  * intensity)
            a = 0.20 + 0.65 * intensity
            fill = f"rgba({r},{g},{b},{a:.2f})"
        else:
            # Rest of pitch — neutral very dim fill
            fill = "rgba(255,255,255,0.02)"

        fig.add_shape(
            type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
            line=dict(color="rgba(255,255,255,0.10)", width=1),
            fillcolor=fill, layer="below",
        )

        # Count label only in defensive third zones
        if zone_num <= 6 and count > 0:
            intensity_text = 0.30 + 0.65 * (count / max_count)
            fig.add_annotation(
                x=(x0 + x1) / 2,
                y=(y0 + y1) / 2,
                text=f"<b>{count}</b>",
                showarrow=False,
                font=dict(size=14, color=f"rgba(255,255,255,{intensity_text:.2f})"),
            )

    # Dummy trace for colour legend
    for label, color in [
        ("High density", "rgba(180,20,40,0.85)"),
        ("Low density",  "rgba(60,20,30,0.40)"),
    ]:
        fig.add_trace(go.Scatter(
            x=[None], y=[None], mode="markers",
            marker=dict(size=10, color=color, symbol="square"),
            name=label, showlegend=True,
        ))

    _draw_full_pitch(fig)
    _pitch_layout(
        fig,
        "Zone Action Density — Defensive Third",
        height=430,
        show_legend=True,
    )
    return fig


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN CARD
# ═══════════════════════════════════════════════════════════════════════════════

def defensive_castle_card(data: dict) -> html.Div:
    """
    Full D3 Defensive Castle card rendered inside the Defensive Phase section.

    Parameters
    ----------
    data : dict
        Output of ``analyse_defensive_castle()``.
    """
    return html.Div(
        [
            # ── Card header ─────────────────────────────────────────────────
            html.H5("Defensive Castle", className="buildup-card-title"),
            html.P(
                "All defensive actions executed in the team's own final third "
                "(tackles, interceptions, clearances, aerial duels, ball recoveries, "
                "blocked passes, challenges and fouls conceded).",
                className="kpi-subtitle",
                style={"marginBottom": "1.25rem"},
            ),

            # ── A — Overview ────────────────────────────────────────────────
            _section_overview(data),

            _hr(),

            # ── B — Actions by Type ─────────────────────────────────────────
            _section_by_type(data),

            _hr(),

            # ── C — Corridor Split ──────────────────────────────────────────
            _section_corridor(data),

            _hr(),

            # ── D — Pitch Maps (side-by-side) ───────────────────────────────
            html.Div(
                [
                    html.H6("Pitch Maps", className="buildup-subsection-title"),
                    html.Div(
                        [
                            # Left — scatter by action type
                            html.Div(
                                [
                                    html.P(
                                        "Events coloured by action type",
                                        className="kpi-subtitle",
                                        style={"marginBottom": "0.4rem",
                                               "textAlign": "center"},
                                    ),
                                    html.Div(
                                        dcc.Graph(
                                            figure=_build_castle_scatter(
                                                data.get("actions_detail", [])
                                            ),
                                            config={"displayModeBar": False},
                                        ),
                                        className="pitch-dark-container",
                                    ),
                                ],
                                style={"flex": "1", "minWidth": "0"},
                            ),
                            # Right — zone heatmap
                            html.Div(
                                [
                                    html.P(
                                        "Action density per zone — darker = more actions",
                                        className="kpi-subtitle",
                                        style={"marginBottom": "0.4rem",
                                               "textAlign": "center"},
                                    ),
                                    html.Div(
                                        dcc.Graph(
                                            figure=_build_castle_heatmap(
                                                data.get("zone_counts", {})
                                            ),
                                            config={"displayModeBar": False},
                                        ),
                                        className="pitch-dark-container",
                                    ),
                                ],
                                style={"flex": "1", "minWidth": "0"},
                            ),
                        ],
                        style={
                            "display": "flex",
                            "gap": "1.5rem",
                            "flexWrap": "wrap",
                        },
                    ),
                ],
            ),
        ],
        className="buildup-card",
        style={"padding": "1.5rem"},
    )
