"""
Set Pieces Phase UI Components
================================
Dash layout cards for the Set Pieces section of Match Analysis.

Cards implemented
-----------------
1. Corner Kicks  (corner_kicks_card)
   A — Volume & Outcomes
   B — Delivery Type Breakdown
   C — Delivery Maps

2. Free Kicks    (free_kicks_card)
   A — Volume & Outcomes
   B — Delivery Type Breakdown
   C — Direct Shot Maps  (pitch origin + goalmouth zone figure + descriptors)
   D — Delivery Maps     (pitch origin → landing, by type)

Visual identity matches all existing dashboard cards.
"""

from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
from dash import dcc, html

from src.components.buildup_cards import _chain_connector, _chain_event_node
from src.styling.theme import COLORS_DARK, SEMANTIC_COLORS
from src.styling.plotly_template import apply_chart_theme
from src.styling.ui_components import ds_header

# ═══════════════════════════════════════════════════════════════════════════════
# PALETTE & CONSTANTS — bound to the shared design system (values unchanged,
# see theme.py Phase 2c additions)
# ═══════════════════════════════════════════════════════════════════════════════

PRIMARY   = COLORS_DARK["accent"]                       # "#8a1f33"
GOAL_CLR      = SEMANTIC_COLORS["sp_goal"]              # "#22c55e"
SOT_CLR       = SEMANTIC_COLORS["sp_shot_on_target"]    # "#3b82f6"
SOFF_CLR      = SEMANTIC_COLORS["sp_shot_off_target"]   # "#f97316"
CLEAR_CLR     = SEMANTIC_COLORS["sp_cleared"]           # "#6b7280"
SP_CLR        = SEMANTIC_COLORS["sp_second_phase"]      # "#8b5cf6"
PLAYEDON_CLR  = SEMANTIC_COLORS["sp_played_on"]         # cyan — played on / no shot

DELIVERY_COLORS = {
    "Inswinger":  SEMANTIC_COLORS["delivery_inswinger"],
    "Outswinger": SEMANTIC_COLORS["delivery_outswinger"],
    "Straight":   SEMANTIC_COLORS["delivery_straight"],
    "Short":      SEMANTIC_COLORS["delivery_short"],
    "Unknown":    SEMANTIC_COLORS["delivery_unknown"],
}

OUTCOME_COLORS = {
    "Goal":                 GOAL_CLR,
    "Own Goal":             GOAL_CLR,   # same green — counts as a goal for the team
    "Shot on Target":       SOT_CLR,
    "Shot off Target":      SOFF_CLR,
    "Cleared":              CLEAR_CLR,
    "Second Phase Attack":  SP_CLR,
}

# ── Pitch coordinate constants (Opta system) ──────────────────────────────────
# Figure axes:
#   x-axis (horizontal) = Opta y  (0→100, left touchline → right touchline)
#   y-axis (vertical)   = Opta x  (66.67→103, final-third line→goal+depth)
#                         GOAL is at TOP (fig_y = 100→103)

GOAL_LINE     = 100.0
PENALTY_LINE  = 83.33
SIX_YARD_LINE = 94.8
PEN_AREA_L    = 21.1    # left edge of penalty area (in Opta y)
PEN_AREA_R    = 78.9    # right edge
SIX_YARD_L    = 36.8    # left edge of 6-yard box
SIX_YARD_R    = 63.2    # right edge
GOAL_L        = 40.0    # left post  (~3 units inside SIX_YARD_L=36.8, well clear of GA1/GA3)
GOAL_R        = 60.0    # right post (~3 units inside SIX_YARD_R=63.2)
GOAL_DEPTH    = 3.0
PEN_SPOT_X    = 88.5    # Opta x of penalty spot → fig_y
PEN_SPOT_Y    = 50.0    # Opta y of penalty spot → fig_x
FT_LINE       = 66.67   # final third line (fig_y bottom)

# CA zone bottom — same height as GA zones (GOAL_LINE − SIX_YARD_LINE = 5.2 units)
CA_LINE = 2 * SIX_YARD_LINE - GOAL_LINE  # = 89.6

FIG_Y_MIN = FT_LINE - 1.0
FIG_Y_MAX = GOAL_LINE + GOAL_DEPTH + 0.5

# D-arc radius in Opta units
D_ARC_RX = 9.15 / 68.0 * 100   # horizontal (fig_x direction) ≈ 13.46
D_ARC_RY = 9.15 / 105.0 * 100  # vertical   (fig_y direction) ≈ 8.71

# Corner arc radius (~1 yard)
CORNER_ARC_RX = 1.34   # in Opta y units → fig_x
CORNER_ARC_RY = 0.87   # in Opta x units → fig_y

# ── Zone geometry per corner side ─────────────────────────────────────────────
# Each entry: (fig_x0, fig_x1, fig_y0, fig_y1, label, fill_rgba)
_ZONE_ALPHA_GA   = "rgba(139,92,246,0.13)"
_ZONE_ALPHA_CA   = "rgba(59,130,246,0.10)"
_ZONE_ALPHA_EDGE = "rgba(220,38,38,0.18)"   # red
_ZONE_ALPHA_WIDE = "rgba(100,100,100,0.07)"

def _zones_for_side(is_left: bool) -> list:
    """
    Return zone rectangles. Zones are always within penalty area width.
    is_left=True → football left corner → flag at fig_x≈100 (Opta y≈100) → near post on RIGHT of figure.
    is_left=False → football right corner → flag at fig_x≈0 (Opta y≈0) → near post on LEFT of figure.
    """
    if is_left:
        # Flag at fig_x≈0 (LEFT) → near post column on the LEFT of figure
        near_l, near_r = PEN_AREA_L, SIX_YARD_L   # 21.1 → 36.8
        far_l,  far_r  = SIX_YARD_R, PEN_AREA_R   # 63.2 → 78.9
        front_l, front_r = 0.0, PEN_AREA_L         # near-post wide strip (low fig_x)
        back_l,  back_r  = PEN_AREA_R, 100.0       # far-post wide strip
    else:
        # Flag at fig_x≈100 (RIGHT) → near post column on the RIGHT of figure
        near_l, near_r = SIX_YARD_R, PEN_AREA_R   # 63.2 → 78.9
        far_l,  far_r  = PEN_AREA_L, SIX_YARD_L   # 21.1 → 36.8
        front_l, front_r = PEN_AREA_R, 100.0       # near-post wide strip (high fig_x)
        back_l,  back_r  = 0.0, PEN_AREA_L         # far-post wide strip

    cx_l, cx_r = SIX_YARD_L, SIX_YARD_R            # centre strip (36.8→63.2)

    return [
        # 6-yard box row  (SIX_YARD_LINE → GOAL_LINE, height = 5.2)
        (near_l,  near_r,  SIX_YARD_LINE, GOAL_LINE, "GA1", _ZONE_ALPHA_GA),
        (cx_l,    cx_r,    SIX_YARD_LINE, GOAL_LINE, "GA2", _ZONE_ALPHA_GA),
        (far_l,   far_r,   SIX_YARD_LINE, GOAL_LINE, "GA3", _ZONE_ALPHA_GA),
        # Penalty area row — same height as GA (CA_LINE → SIX_YARD_LINE, height = 5.2)
        (near_l,  near_r,  CA_LINE, SIX_YARD_LINE, "CA1", _ZONE_ALPHA_CA),
        (cx_l,    cx_r,    CA_LINE, SIX_YARD_LINE, "CA2", _ZONE_ALPHA_CA),
        (far_l,   far_r,   CA_LINE, SIX_YARD_LINE, "CA3", _ZONE_ALPHA_CA),
        # Edge strip — pen-area width, from D-arc tangent to bottom of CA zones
        (PEN_AREA_L, PEN_AREA_R, PEN_SPOT_X - D_ARC_RY, CA_LINE, "Edge", _ZONE_ALPHA_EDGE),
        # Wide corridors — full height (FT_LINE → GOAL_LINE)
        (front_l, front_r, FT_LINE, GOAL_LINE, "Front\nZone", _ZONE_ALPHA_WIDE),
        (back_l,  back_r,  FT_LINE, GOAL_LINE, "Back\nZone",  _ZONE_ALPHA_WIDE),
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# SHARED HELPER — mini KPI card (matches all existing cards)
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
# A. VOLUME & OUTCOMES
# ═══════════════════════════════════════════════════════════════════════════════

def _section_volume_outcomes(data: dict) -> html.Div:
    total    = data.get("total", 0)
    outcomes = data.get("outcomes", {})
    goal     = outcomes.get("goal", 0)
    sot      = outcomes.get("shot_on_target", 0)
    soff     = outcomes.get("shot_off_target", 0)
    cleared  = outcomes.get("cleared", 0)
    sp       = outcomes.get("second_phase", 0)

    return html.Div(
        [
            html.H6("Volume & Outcomes", className="buildup-subsection-title"),
            html.Div(
                [
                    _mini_kpi("Total Corners", total,
                               "corner kicks taken", PRIMARY, "bi-flag-fill"),
                    _mini_kpi("Goals", goal,
                               f"{goal/total*100:.0f}% of corners" if total else "—",
                               GOAL_CLR, "bi-trophy-fill"),
                    _mini_kpi("Shots on Target", sot,
                               f"{sot/total*100:.0f}%" if total else "—",
                               SOT_CLR, "bi-bullseye"),
                    _mini_kpi("Shots off Target", soff,
                               f"{soff/total*100:.0f}%" if total else "—",
                               SOFF_CLR, "bi-x-circle"),
                    _mini_kpi("Cleared", cleared,
                               f"{cleared/total*100:.0f}%" if total else "—",
                               CLEAR_CLR, "bi-shield"),
                    _mini_kpi("2nd Phase", sp,
                               f"{sp/total*100:.0f}%" if total else "—",
                               SP_CLR, "bi-arrow-repeat"),
                ],
                className="team-kpi-row",
            ),
        ]
    )


# ═══════════════════════════════════════════════════════════════════════════════
# B. DELIVERY TYPE BREAKDOWN
# ═══════════════════════════════════════════════════════════════════════════════

def _section_delivery_type(data: dict) -> html.Div:
    delivery_counts   = data.get("delivery_counts", {})
    delivery_outcomes = data.get("delivery_outcomes", {})
    total             = data.get("total", 0)

    delivery_order = ["Inswinger", "Outswinger", "Straight", "Short", "Unknown"]
    counts = [delivery_counts.get(d, 0) for d in delivery_order]
    colors = [DELIVERY_COLORS[d] for d in delivery_order]

    # ── Horizontal bar chart ─────────────────────────────────────────────────
    bar_fig = go.Figure()
    bar_fig.add_trace(go.Bar(
        y=delivery_order,
        x=counts,
        orientation="h",
        marker=dict(color=colors, opacity=0.85),
        text=[str(c) if c else "" for c in counts],
        textposition="outside",
        textfont=dict(size=11, color="#e2e8f0"),
        hovertemplate="%{y}: %{x}<extra></extra>",
    ))
    apply_chart_theme(bar_fig, "dark")
    bar_fig.update_layout(
        margin=dict(l=10, r=30, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=180,
        xaxis=dict(
            showgrid=True, gridcolor="rgba(255,255,255,0.06)",
            zeroline=False, color="#94a3b8", tickfont=dict(size=10),
        ),
        yaxis=dict(
            color="#e2e8f0", tickfont=dict(size=11),
        ),
        showlegend=False,
    )

    # ── Outcome table per delivery type ─────────────────────────────────────
    outcome_cols = ["Goal", "Own Goal", "Shot on Target", "Shot off Target",
                    "Cleared", "Second Phase Attack"]

    header_cells = [html.Th("Type", style={"padding": "0.4rem 0.6rem",
                                           "color": "var(--text-secondary)",
                                           "fontSize": "0.75rem"})]
    for oc in outcome_cols:
        header_cells.append(
            html.Th(oc, style={
                "padding": "0.4rem 0.5rem",
                "color": OUTCOME_COLORS.get(oc, "#94a3b8"),
                "fontSize": "0.75rem",
                "textAlign": "center",
            })
        )

    body_rows = []
    for d in delivery_order:
        cnt = delivery_counts.get(d, 0)
        if cnt == 0:
            continue
        do = delivery_outcomes.get(d, {})
        cells = [
            html.Td(
                html.Span([
                    html.Span("●", style={"color": DELIVERY_COLORS[d], "marginRight": "5px"}),
                    d,
                ]),
                style={"padding": "0.35rem 0.6rem", "fontSize": "0.85rem",
                       "color": "#e2e8f0", "fontWeight": "600"},
            )
        ]
        for oc in outcome_cols:
            v = do.get(oc, 0)
            pct = f"({v/cnt*100:.0f}%)" if cnt and v else ""
            cells.append(
                html.Td(
                    f"{v} {pct}".strip(),
                    style={
                        "padding": "0.35rem 0.5rem",
                        "textAlign": "center",
                        "fontSize": "0.82rem",
                        "color": OUTCOME_COLORS.get(oc, "#94a3b8") if v else "var(--text-muted)",
                        "fontWeight": "600" if v else "400",
                    },
                )
            )
        body_rows.append(html.Tr(cells))

    if not body_rows:
        body_rows = [html.Tr(html.Td("No data", colSpan=5,
                                     style={"padding": "0.5rem", "color": "var(--text-muted)"}))]

    table = html.Table(
        [html.Thead(html.Tr(header_cells)), html.Tbody(body_rows)],
        style={"width": "100%", "borderCollapse": "separate", "borderSpacing": "2px"},
    )

    return html.Div(
        [
            html.H6("Delivery Type", className="buildup-subsection-title"),
            html.Div(
                [
                    html.Div(
                        dcc.Graph(figure=bar_fig, config={"displayModeBar": False,
                                                          "responsive": True}),
                        style={"flex": "1", "minWidth": "220px"},
                    ),
                    html.Div(
                        table,
                        style={"flex": "2", "minWidth": "0",
                               "overflowX": "auto"},
                    ),
                ],
                style={"display": "flex", "gap": "1.5rem",
                       "alignItems": "flex-start", "flexWrap": "wrap"},
            ),
        ]
    )


# ═══════════════════════════════════════════════════════════════════════════════
# C. DELIVERY MAPS — two vertical final-third pitch maps
# ═══════════════════════════════════════════════════════════════════════════════

# NOTE (Phase 2c): these corner/FK/goalmouth pitch drawings are PORTRAIT-
# oriented (figure x = Opta y, goal at top) with set-piece zone furniture
# (GA/CA zones, corner arcs, goalmouth) that is part of the analysis itself.
# pitch_utils.draw_pitch() is landscape-only, so adoption is intentionally
# DEFERRED; figures are themed in place via apply_chart_theme() and the
# shared SEMANTIC_COLORS palettes.
def _pitch_shapes(is_left: bool) -> list:
    """
    Return Plotly shape dicts for the vertical final-third pitch.
    fig_x = Opta y (width 0→100), fig_y = Opta x (depth 66.67→103, goal on top).
    """
    lc = "rgba(255,255,255,0.50)"   # main line colour
    lw = 1.5

    def rect(x0, x1, y0, y1, color=None, width=None, fill="rgba(0,0,0,0)", dash="solid"):
        return dict(type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
                    line=dict(color=color or lc, width=width or lw, dash=dash),
                    fillcolor=fill, layer="below")

    def hline(y, x0=0, x1=100, color=None, width=None, dash="solid"):
        return dict(type="line", x0=x0, x1=x1, y0=y, y1=y,
                    line=dict(color=color or lc, width=width or lw, dash=dash))

    shapes = []

    # ── Touchlines (full height) ──────────────────────────────────────────────
    for xv in (0.0, 100.0):
        shapes.append(dict(type="line", x0=xv, x1=xv, y0=FIG_Y_MIN, y1=GOAL_LINE,
                           line=dict(color=lc, width=lw), layer="below"))

    # ── Final third line (bottom of figure) ───────────────────────────────────
    shapes.append(hline(FT_LINE, color="rgba(255,255,255,0.30)", width=1, dash="dot"))

    # ── Goal line (bold) ──────────────────────────────────────────────────────
    shapes.append(hline(GOAL_LINE, color="rgba(255,255,255,0.80)", width=2.5))

    # ── Goal box ─────────────────────────────────────────────────────────────
    shapes.append(rect(GOAL_L, GOAL_R, GOAL_LINE, GOAL_LINE + GOAL_DEPTH,
                       color="rgba(255,255,255,0.75)", width=2,
                       fill="rgba(255,255,255,0.04)"))

    # ── Penalty area ─────────────────────────────────────────────────────────
    shapes.append(rect(PEN_AREA_L, PEN_AREA_R, PENALTY_LINE, GOAL_LINE))

    # ── 6-yard box ───────────────────────────────────────────────────────────
    shapes.append(rect(SIX_YARD_L, SIX_YARD_R, SIX_YARD_LINE, GOAL_LINE))

    # ── Penalty spot ─ rendered as scatter marker (true circle) in _build_corner_pitch_map

    # ── D-arc (penalty arc, portion below penalty line) ───────────────────────
    t_arc = np.linspace(-2.51, -0.63, 50)
    ax = PEN_SPOT_Y + D_ARC_RX * np.cos(t_arc)
    ay = PEN_SPOT_X + D_ARC_RY * np.sin(t_arc)
    mask = (ay < PENALTY_LINE) & (ax >= 0) & (ax <= 100)
    ax, ay = ax[mask], ay[mask]
    if len(ax) >= 2:
        path = "M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in zip(ax, ay))
        shapes.append(dict(type="path", path=path,
                           line=dict(color="rgba(255,255,255,0.45)", width=1.2),
                           fillcolor="rgba(0,0,0,0)", layer="below"))

    # ── Corner arcs ───────────────────────────────────────────────────────────
    # Left corner (flag at fig_x=0, fig_y=100)
    t_cl = np.linspace(-np.pi / 2, 0, 25)
    shapes.append(dict(type="path",
                       path="M " + " L ".join(
                           f"{CORNER_ARC_RX * np.cos(t):.3f},{100 + CORNER_ARC_RY * np.sin(t):.3f}"
                           for t in t_cl),
                       line=dict(color="rgba(255,255,255,0.50)", width=1.2),
                       fillcolor="rgba(0,0,0,0)", layer="below"))
    # Right corner (flag at fig_x=100, fig_y=100)
    t_cr = np.linspace(-np.pi, -np.pi / 2, 25)
    shapes.append(dict(type="path",
                       path="M " + " L ".join(
                           f"{100 + CORNER_ARC_RX * np.cos(t):.3f},{100 + CORNER_ARC_RY * np.sin(t):.3f}"
                           for t in t_cr),
                       line=dict(color="rgba(255,255,255,0.50)", width=1.2),
                       fillcolor="rgba(0,0,0,0)", layer="below"))

    # ── Zone rectangles ───────────────────────────────────────────────────────
    for x0, x1, y0, y1, _lbl, fill in _zones_for_side(is_left):
        shapes.append(dict(type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
                           line=dict(color="rgba(255,255,255,0.18)", width=0.8),
                           fillcolor=fill, layer="below"))

    return shapes


def _zone_annotations(is_left: bool) -> list:
    """Zone label annotations placed at zone centres."""
    anns = []
    for x0, x1, y0, y1, label, _ in _zones_for_side(is_left):
        cx = (x0 + x1) / 2
        cy = (y0 + y1) / 2
        anns.append(dict(
            x=cx, y=cy,
            text=label.replace("\n", "<br>"),
            showarrow=False,
            font=dict(size=8, color="rgba(255,255,255,0.40)"),
            xanchor="center", yanchor="middle",
        ))
    return anns


def _hover_text(c: dict) -> str:
    taker   = c.get("taker") or "—"
    outcome = c.get("outcome", "")
    # Display label — own goals get an explicit marker
    display_outcome = "Goal (OG) ⚽" if outcome == "Own Goal" else outcome
    lines = [
        f"<b>{c['minute']}' — {display_outcome}</b>",
        f"Taker: {taker}",
    ]
    # When cleared or an own goal the defending team made first contact —
    # hide the receiver so the hover only shows Taker / Type / Zone.
    if outcome not in ("Cleared", "Own Goal"):
        receiver = c.get("receiver") or "—"
        lines.append(f"1st touch: {receiver}")
    lines.append(f"Type: {c['delivery']}")
    lines.append(f"Zone: {c['zone']}")
    return "<br>".join(lines)


def _build_corner_pitch_map(corners: list, is_left: bool, title: str) -> go.Figure:
    """
    Vertical final-third pitch map for corners from one side.

    fig_x = Opta y  (pitch width)
    fig_y = Opta x  (pitch depth, goal at top)
    """
    fig = go.Figure()

    # ── Pitch shapes ─────────────────────────────────────────────────────
    for shape in _pitch_shapes(is_left):
        fig.add_shape(**shape)

    # ── Penalty spot (scatter marker = true visual circle) ─────────────────────
    fig.add_trace(go.Scatter(
        x=[100 - PEN_SPOT_Y], y=[PEN_SPOT_X],
        mode="markers",
        marker=dict(size=7, color="rgba(255,255,255,0.60)", symbol="circle",
                    line=dict(color="rgba(255,255,255,0.60)", width=0)),
        showlegend=False, hoverinfo="skip",
    ))

    # ── Corner flag: fig_x = 100 − Opta_y
    #   is_left=True  (Opta y≈99.5) → fig_x ≈0   = LEFT  of figure ✓
    #   is_left=False (Opta y≈0.5)  → fig_x ≈100  = RIGHT of figure ✓
    flag_fig_x = 0.0 if is_left else 100.0

    if not corners:
        apply_chart_theme(fig, "dark")
        fig.update_layout(**_pitch_layout(title, is_left, []))
        return fig

    # ── Delivery lines: corner flag → landing dot (per corner) ───────────────
    for c in corners:
        if c.get("end_x") is None or c.get("end_y") is None:
            continue
        color = OUTCOME_COLORS.get(c.get("outcome", "Cleared"), CLEAR_CLR)
        fig.add_trace(go.Scatter(
            x=[flag_fig_x, 100 - c["end_y"]],
            y=[GOAL_LINE,  c["end_x"]],            mode="lines",
            line=dict(color=color, width=1.0, dash="dot"),
            opacity=0.50,
            showlegend=False,
            hoverinfo="skip",
        ))

    # ── Delivery dots (grouped by outcome for legend) ─────────────────────────
    OUTCOME_ORDER = ["Goal", "Own Goal", "Shot on Target", "Shot off Target",
                     "Cleared", "Second Phase Attack"]
    legend_shown = set()

    for outcome in OUTCOME_ORDER:
        group = [c for c in corners
                 if c.get("outcome") == outcome
                 and c.get("end_x") is not None]
        if not group:
            continue

        color   = OUTCOME_COLORS[outcome]
        is_goal = outcome in ("Goal", "Own Goal")  # both rendered as a star
        show_lg = outcome not in legend_shown
        legend_shown.add(outcome)

        fig.add_trace(go.Scatter(
            x=[100 - c["end_y"] for c in group],
            y=[c["end_x"] for c in group],
            mode="markers",
            name=outcome,
            marker=dict(
                size=13 if is_goal else 11,
                color=color,
                symbol="star" if is_goal else "circle",
                line=dict(color="rgba(255,255,255,0.70)", width=1.5),
                opacity=0.95,
            ),
            text=[_hover_text(c) for c in group],
            hovertemplate="%{text}<extra></extra>",
            showlegend=show_lg,
        ))

    apply_chart_theme(fig, "dark")

    fig.update_layout(**_pitch_layout(title, is_left, _zone_annotations(is_left)))
    return fig


def _pitch_layout(title: str, is_left: bool, annotations: list) -> dict:
    # Goal text centred above goal line
    extra_anns = [
        dict(x=50, y=GOAL_LINE + GOAL_DEPTH / 2 + 0.3,
             text="GOAL", showarrow=False,
             font=dict(size=9, color="rgba(255,255,255,0.75)"),
             xanchor="center"),
        dict(x=50, y=FT_LINE - 0.8,
             text="Final Third Line", showarrow=False,
             font=dict(size=7, color="rgba(255,255,255,0.28)"),
             xanchor="center"),
    ]

    return dict(
        title=dict(text=title,
                   font=dict(size=11, color="#e2e8f0"),
                   x=0.5, xanchor="center"),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=15, r=15, t=30, b=50),
        height=520,
        xaxis=dict(range=[-5, 105], showgrid=False, zeroline=False,
                   showticklabels=False, fixedrange=True),
        yaxis=dict(range=[FIG_Y_MIN - 1, FIG_Y_MAX + 0.5],
                   showgrid=False, zeroline=False,
                   showticklabels=False, fixedrange=True),
        showlegend=True,
        legend=dict(
            orientation="h", yanchor="top", y=-0.03,
            xanchor="center", x=0.5,
            font=dict(size=10, color="#e2e8f0"),
            bgcolor="rgba(0,0,0,0)",
            itemsizing="constant",
        ),
        annotations=annotations + extra_anns,
    )


def _section_delivery_maps(data: dict) -> html.Div:
    corners = data.get("corners", [])
    if not corners:
        return html.Div()

    left_corners  = [c for c in corners if c.get("is_left", True)]
    right_corners = [c for c in corners if not c.get("is_left", True)]

    nl = len(left_corners)
    nr = len(right_corners)

    fig_left  = _build_corner_pitch_map(left_corners,  True,
                                         f"Left-Side Corners ({nl})")
    fig_right = _build_corner_pitch_map(right_corners, False,
                                         f"Right-Side Corners ({nr})")

    def _pitch_col(fig, corners_list):
        subtitle = (
            f"{len(corners_list)} corner{'s' if len(corners_list) != 1 else ''}"
            if corners_list else "No corners from this side"
        )
        return html.Div(
            [
                html.P(subtitle, className="kpi-subtitle",
                       style={"textAlign": "center", "marginBottom": "0.4rem"}),
                html.Div(
                    dcc.Graph(figure=fig,
                              config={"displayModeBar": False, "responsive": True}),
                    className="pitch-dark-container",
                ),
            ],
            style={"flex": "1", "minWidth": "280px"},
        )

    return html.Div(
        [
            html.H6("Delivery Maps", className="buildup-subsection-title"),
            html.P(
                "Dotted line = corner flag → landing point  ·  dot colour = outcome  ·  "
                "★ = goal  ·  hover for taker & first-touch player",
                className="kpi-subtitle",
                style={"marginBottom": "0.8rem"},
            ),
            html.Div(
                [_pitch_col(fig_left, left_corners),
                 _pitch_col(fig_right, right_corners)],
                style={"display": "flex", "gap": "1.5rem", "flexWrap": "wrap"},
            ),
        ]
    )


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN CARD BUILDER
# ═══════════════════════════════════════════════════════════════════════════════

def corner_kicks_card(data: dict) -> html.Div:
    """
    Render the full Corner Kicks analysis card.

    Parameters
    ----------
    data : dict
        Output of ``analyse_corner_kicks()``.
    """
    total = data.get("total", 0)

    if total == 0:
        empty_state = html.Div(
            [
                html.I(className="bi bi-flag me-2",
                       style={"color": "var(--text-muted)", "fontSize": "2rem"}),
                html.P("No corner kicks recorded for this match.",
                       className="text-muted",
                       style={"marginTop": "0.5rem"}),
            ],
            style={"textAlign": "center", "padding": "3rem 1rem"},
        )
        return html.Div(
            [
                ds_header(
                    "Set Pieces — Corners", "bi-flag-fill",
                    "Corner Kicks",
                    "Volume, delivery types and zone-by-zone delivery maps",
                ),
                empty_state,
            ],
            className="buildup-card ma-card",
            style={"padding": "1.5rem"},
        )

    HR = html.Hr(style={"borderColor": "var(--border-light)", "margin": "1.5rem 0"})

    return html.Div(
        [
            ds_header(
                "Set Pieces — Corners", "bi-flag-fill",
                "Corner Kicks",
                "Volume, delivery types and zone-by-zone delivery maps",
            ),

            # A — Volume & Outcomes
            html.Div(_section_volume_outcomes(data), style={"marginBottom": "1.5rem"}),

            HR,

            # B — Delivery Type
            html.Div(_section_delivery_type(data), style={"marginBottom": "1.5rem"}),

            HR,

            # C — Zone Heatmap
            html.Div(_section_delivery_maps(data)),
        ],
        className="buildup-card ma-card",
        style={"padding": "1.5rem"},
    )


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║                        FREE KICKS CARD                                   ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

# ─── Palette — bound to the shared design system (values unchanged) ───────────
FK_TYPE_COLORS: dict = {
    "Direct Shot":      SEMANTIC_COLORS["fk_direct_shot"],
    "Crossed into Box": SEMANTIC_COLORS["fk_crossed"],
    "Chipped / Lofted": SEMANTIC_COLORS["fk_chipped"],
    "Long Ball":        SEMANTIC_COLORS["fk_long_ball"],
    "Short":            SEMANTIC_COLORS["fk_short"],
    "Launch":           SEMANTIC_COLORS["fk_launch"],
    "Unknown":          SEMANTIC_COLORS["delivery_unknown"],
}

FK_OUTCOME_COLORS: dict = {
    "Goal":              SEMANTIC_COLORS["sp_goal"],
    "Shot on Target":    SEMANTIC_COLORS["sp_shot_on_target"],
    "Shot off Target":   SEMANTIC_COLORS["sp_shot_off_target"],
    "Hit Post":          SEMANTIC_COLORS["sp_hit_post"],
    "Blocked":           SEMANTIC_COLORS["sp_blocked"],
    "Second Phase":      SEMANTIC_COLORS["sp_second_phase"],
    "Foul Won":          SEMANTIC_COLORS["sp_foul_won"],
    "Assist":            SEMANTIC_COLORS["sp_foul_won"],
    "Cleared / No Shot": SEMANTIC_COLORS["sp_cleared"],
}

_FK_TYPE_ORDER = [
    "Direct Shot", "Crossed into Box", "Chipped / Lofted",
    "Long Ball", "Short", "Launch", "Unknown",
]

# FK maps show the full offensive half (x 50 → 100+goal), not just final third
FK_HALF_LINE     = 50.0   # halfway line (Opta x)
FK_FIG_Y_MIN     = FK_HALF_LINE - 1.0
FK_HALF_LINE_ANN = FK_HALF_LINE - 0.8  # annotation y position

_FK_OUTCOME_ORDER = [
    "Goal", "Shot on Target", "Shot off Target", "Hit Post",
    "Blocked", "Second Phase", "Foul Won", "Assist", "Cleared / No Shot",
]

# ─── Goalmouth geometry ───────────────────────────────────────────────────────
# Goal is 7.32 m wide × 2.44 m high.  Figure axes (GK perspective):
#   figure x: 0 = GK left post  →  100 = GK right post
#   figure y: 0 = ground        →  ~100 = crossbar area
#
# Opta Q102 (gm_y): full-pitch Y coordinate (right touchline=0 → left touchline=100).
#   Goal posts sit at Y≈44.62 (GK-right) and Y≈55.38 (GK-left).
#   figure_x = (GM_POST_LEFT_Y − Q102) / GM_GOAL_WIDTH_Y * GM_W
#   i.e. LOWER Q102 → rightward in figure; HIGHER Q102 → leftward.
#
# Opta Q103 (gm_z): height scale where Low/High zone boundary ≈ 20
#   (empirically verified from 6 k+ events; not a 0-100 over crossbar scale).
#   figure_y = Q103 * GM_Z_SCALE   where GM_Z_SCALE = GM_ROW1 / GM_Z_MID = 2.5
#   → Q103=0 → figure_y=0 (ground);  Q103=20 → figure_y=50 (Low/High split);
#     Q103=40 → figure_y=100 (approximately at/above crossbar).
GM_W = 100.0   # figure x extent
GM_H = 100.0   # figure y extent
# Zone dividers
GM_COL1 = 33.33
GM_COL2 = 66.67
GM_ROW1 = 50.0
# Goalmouth coordinate transformation constants (empirically derived)
GM_POST_LEFT_Y  = 55.38   # Opta pitch Y of GK’s-left post
GM_POST_RIGHT_Y = 44.62   # Opta pitch Y of GK’s-right post
GM_GOAL_WIDTH_Y = GM_POST_LEFT_Y - GM_POST_RIGHT_Y   # ≈10.76 units
GM_Z_MID        = 20.0    # Q103_Z value at the Low/High zone boundary
GM_Z_SCALE      = GM_ROW1 / GM_Z_MID   # 2.5  — Q103 × 2.5 = figure y

# Zone display labels with estimated centres
_GM_ZONES = [
    # (x0, x1, y0, y1, label)
    (0,       GM_COL1,  0,      GM_ROW1, "Low\nLeft"),
    (GM_COL1, GM_COL2,  0,      GM_ROW1, "Low\nCentre"),
    (GM_COL2, GM_W,     0,      GM_ROW1, "Low\nRight"),
    (0,       GM_COL1,  GM_ROW1, GM_H,   "High\nLeft"),
    (GM_COL1, GM_COL2,  GM_ROW1, GM_H,   "High\nCentre"),
    (GM_COL2, GM_W,     GM_ROW1, GM_H,   "High\nRight"),
]

# ─── Goalmouth coordinate helper ─────────────────────────────────────────────

def _gm_to_fig(gm_y: float, gm_z: float):
    """
    Convert Opta goalmouth coordinates to figure (x, y).

    Parameters
    ----------
    gm_y : float
        Q102 — full-pitch Y coordinate where ball crossed goal line.
        Goal posts at approximately Y=44.62 (GK-right) and Y=55.38 (GK-left).
        Lower Q102 → right side of figure; higher Q102 → left side.
    gm_z : float
        Q103 — height scale where Low/High zone boundary ≈ 20.
        Multiply by GM_Z_SCALE (2.5) to get figure y (0=ground, 50=zone split).

    Returns
    -------
    (fig_x, fig_y) in figure units. Values outside [0, 100] indicate
    the ball missed the frame (wide or over the bar).
    """
    fig_x = (GM_POST_LEFT_Y - gm_y) / GM_GOAL_WIDTH_Y * GM_W
    fig_y = gm_z * GM_Z_SCALE
    return fig_x, fig_y


# ─── Helper: build goalmouth figure ───────────────────────────────────────────

def _build_goalmouth_figure(direct_shots: list) -> go.Figure:
    """
    Render a goal-face rectangle divided into 6 zones (Low/High × L/C/R).
    Each shot is plotted at (Q102, Q103) or zone centre if coordinates absent.
    Colour = outcome.
    """
    fig = go.Figure()

    # ── Goal frame ──────────────────────────────────────────────────────────
    lc = "rgba(255,255,255,0.70)"
    fig.add_shape(type="rect", x0=0, x1=GM_W, y0=0, y1=GM_H,
                  line=dict(color=lc, width=2.5),
                  fillcolor="rgba(30,30,30,0.30)", layer="below")

    # ── Zone dividers ────────────────────────────────────────────────────────
    for xv in (GM_COL1, GM_COL2):
        fig.add_shape(type="line", x0=xv, x1=xv, y0=0, y1=GM_H,
                      line=dict(color="rgba(255,255,255,0.25)", width=1, dash="dot"),
                      layer="below")
    fig.add_shape(type="line", x0=0, x1=GM_W, y0=GM_ROW1, y1=GM_ROW1,
                  line=dict(color="rgba(255,255,255,0.25)", width=1, dash="dot"),
                  layer="below")

    # ── Zone count annotations (background) ──────────────────────────────────
    gm_zone_key_map = {
        "Low Left":    (0,       GM_COL1,  0,       GM_ROW1),
        "Low Centre":  (GM_COL1, GM_COL2,  0,       GM_ROW1),
        "Low Right":   (GM_COL2, GM_W,     0,       GM_ROW1),
        "High Left":   (0,       GM_COL1,  GM_ROW1, GM_H),
        "High Centre": (GM_COL1, GM_COL2,  GM_ROW1, GM_H),
        "High Right":  (GM_COL2, GM_W,     GM_ROW1, GM_H),
    }
    zone_counts_local: dict = {}
    for fk in direct_shots:
        gz = fk.get("goalmouth_zone")
        if gz and gz in gm_zone_key_map:
            zone_counts_local[gz] = zone_counts_local.get(gz, 0) + 1

    for zone_name, (x0, x1, y0, y1) in gm_zone_key_map.items():
        cx = (x0 + x1) / 2
        cy = (y0 + y1) / 2
        cnt = zone_counts_local.get(zone_name, 0)
        fig.add_annotation(
            x=cx, y=cy,
            text=zone_name.replace(" ", "<br>"),
            showarrow=False,
            font=dict(size=8, color="rgba(255,255,255,0.28)"),
            xanchor="center", yanchor="middle",
        )
        if cnt:
            fig.add_annotation(
                x=cx, y=cy + 10,
                text=f"<b>{cnt}</b>",
                showarrow=False,
                font=dict(size=14, color="rgba(255,255,255,0.18)"),
                xanchor="center", yanchor="middle",
            )

    if not direct_shots:
        _apply_gm_layout(fig)
        return fig

    # ── Shot dots grouped by outcome ─────────────────────────────────────────
    legend_shown: set = set()
    for outcome in _FK_OUTCOME_ORDER:
        group = [s for s in direct_shots
                 if s.get("outcome") == outcome
                 and not s.get("is_blocked", False)
                 and s.get("goalmouth_y") is not None
                 and outcome != "Shot off Target"]
        if not group:
            continue
        color   = FK_OUTCOME_COLORS.get(outcome, "#6b7280")
        is_goal = (outcome == "Goal")
        show_lg = outcome not in legend_shown
        legend_shown.add(outcome)

        hover_texts = []
        for s in group:
            bp   = s.get("body_part") or "—"
            desc = ", ".join(s.get("descriptors") or []) or "—"
            hover_texts.append(
                f"<b>{s['minute']}' — {outcome}</b><br>"
                f"Taker: {s.get('taker') or '—'}<br>"
                f"Body part: {bp}<br>"
                f"Descriptors: {desc}"
            )

        fig.add_trace(go.Scatter(
            x=[_gm_to_fig(s["goalmouth_y"], s["goalmouth_z"])[0] for s in group],
            y=[_gm_to_fig(s["goalmouth_y"], s["goalmouth_z"])[1] for s in group],
            mode="markers",
            name=outcome,
            marker=dict(
                size=16 if is_goal else 13,
                color=color,
                symbol="star" if is_goal else "circle",
                line=dict(color="rgba(255,255,255,0.80)", width=1.5),
                opacity=0.95,
            ),
            text=hover_texts,
            hovertemplate="%{text}<extra></extra>",
            showlegend=show_lg,
        ))

    # ── X markers for off-target shots (outside goal frame) ───────────────────
    # Q73 "Left"  = attacker's left  = GK's RIGHT → x > 100
    # Q75 "Right" = attacker's right = GK's LEFT  → x < 0
    # Q74 "High"  = over the bar                  → y > 100
    # If Q102/Q103 are present they may already be outside 0-100; use them directly.
    # Otherwise fall back to miss-direction qualifiers stored in analytics.
    miss_shots = [
        s for s in direct_shots
        if s.get("outcome") == "Shot off Target"
        and not s.get("is_blocked", False)
    ]
    if miss_shots:
        miss_x, miss_y, miss_hover = [], [], []
        for s in miss_shots:
            gy = s.get("goalmouth_y")
            gz = s.get("goalmouth_z")
            if gy is not None and gz is not None:
                # Q102/Q103 present — transform to figure coordinates
                px, py = _gm_to_fig(gy, gz)
            else:
                # No goalmouth coords → derive position from Q73/Q74/Q75 flags
                ml = s.get("miss_left",  False)   # Q73: missed left (attacker’s left = GK’s right = figure RIGHT)
                mh = s.get("miss_high",  False)   # Q74: over the bar
                mr = s.get("miss_right", False)   # Q75: missed right (attacker’s right = GK’s left = figure LEFT)
                # Default X (horizontal): centre of goal
                px = 50.0
                if ml and not mr:
                    px = 112.0   # wide to figure right (GK’s right)
                elif mr and not ml:
                    px = -12.0  # wide to figure left (GK’s left)
                # Default Y (vertical): mid-height
                py = 50.0
                if mh:
                    py = 112.0   # over the bar
                elif not mh and not ml and not mr:
                    # No qualifier info at all — place above bar as safest default
                    py = 112.0
            miss_x.append(px)
            miss_y.append(py)
            bp   = s.get("body_part") or "—"
            desc = ", ".join(s.get("descriptors") or []) or "—"
            miss_hover.append(
                f"<b>{s['minute']}' — Shot off Target</b><br>"
                f"Taker: {s.get('taker') or '—'}<br>"
                f"Body part: {bp}<br>"
                f"Descriptors: {desc}"
            )
        color = FK_OUTCOME_COLORS.get("Shot off Target", "#f97316")
        fig.add_trace(go.Scatter(
            x=miss_x, y=miss_y,
            mode="markers",
            name="Shot off Target",
            marker=dict(
                size=14,
                color=color,
                symbol="x",
                line=dict(color=color, width=2.5),
                opacity=0.90,
            ),
            text=miss_hover,
            hovertemplate="%{text}<extra></extra>",
            showlegend=("Shot off Target" not in legend_shown),
        ))

    _apply_gm_layout(fig)
    return fig


def _apply_gm_layout(fig: go.Figure) -> None:
    apply_chart_theme(fig, "dark")
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=28, b=50),
        height=260,
        xaxis=dict(range=[-18, 118], showgrid=False, zeroline=False,
                   showticklabels=False, fixedrange=True),
        yaxis=dict(range=[-15, 118], showgrid=False, zeroline=False,
                   showticklabels=False, fixedrange=True),
        showlegend=True,
        legend=dict(
            orientation="h", yanchor="top", y=-0.05,
            xanchor="center", x=0.5,
            font=dict(size=10, color="#e2e8f0"),
            bgcolor="rgba(0,0,0,0)",
            itemsizing="constant",
        ),
        annotations=[
            dict(x=50, y=105, text="GOAL (GK perspective)",
                 showarrow=False,
                 font=dict(size=9, color="rgba(255,255,255,0.55)"),
                 xanchor="center"),
        ],
    )


# ─── Helper: pitch map for direct FK shots ────────────────────────────────────

def _fk_pitch_shapes() -> list:
    """
    Pitch shapes for the FK offensive-half map (halfway line → goal).
    fig_x = Opta y (0→100 width), fig_y = Opta x (50→100 depth, goal at top).
    """
    import numpy as np
    lc = "rgba(255,255,255,0.50)"
    lw = 1.5

    def rect(x0, x1, y0, y1, color=None, width=None, fill="rgba(0,0,0,0)", dash="solid"):
        return dict(type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
                    line=dict(color=color or lc, width=width or lw, dash=dash),
                    fillcolor=fill, layer="below")

    def hline(y, x0=0, x1=100, color=None, width=None, dash="solid"):
        return dict(type="line", x0=x0, x1=x1, y0=y, y1=y,
                    line=dict(color=color or lc, width=width or lw, dash=dash))

    shapes = []

    # ── Touchlines: full height from halfway line to goal line ──────────────
    for xv in (0.0, 100.0):
        shapes.append(dict(type="line", x0=xv, x1=xv,
                           y0=FK_HALF_LINE, y1=GOAL_LINE,
                           line=dict(color=lc, width=lw), layer="below"))

    # ── Halfway line (solid) ──────────────────────────────────────────
    shapes.append(hline(FK_HALF_LINE))

    # ── Final-third line (faint dashed reference) ──────────────────────
    shapes.append(hline(FT_LINE, color="rgba(255,255,255,0.20)", width=1, dash="dot"))

    # ── Goal line (bold) ─────────────────────────────────────────────
    shapes.append(hline(GOAL_LINE, color="rgba(255,255,255,0.80)", width=2.5))

    # ── Goal box ───────────────────────────────────────────────────
    shapes.append(rect(GOAL_L, GOAL_R, GOAL_LINE, GOAL_LINE + GOAL_DEPTH,
                       color="rgba(255,255,255,0.75)", width=2,
                       fill="rgba(255,255,255,0.04)"))

    # ── Penalty area ──────────────────────────────────────────────
    shapes.append(rect(PEN_AREA_L, PEN_AREA_R, PENALTY_LINE, GOAL_LINE))

    # ── 6-yard box ───────────────────────────────────────────────
    shapes.append(rect(SIX_YARD_L, SIX_YARD_R, SIX_YARD_LINE, GOAL_LINE))

    # ── D-arc ─────────────────────────────────────────────────────
    t_arc = np.linspace(-2.51, -0.63, 50)
    ax = PEN_SPOT_Y + D_ARC_RX * np.cos(t_arc)
    ay = PEN_SPOT_X + D_ARC_RY * np.sin(t_arc)
    mask = (ay < PENALTY_LINE) & (ax >= 0) & (ax <= 100)
    ax, ay = ax[mask], ay[mask]
    if len(ax) >= 2:
        path = "M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in zip(ax, ay))
        shapes.append(dict(type="path", path=path,
                           line=dict(color="rgba(255,255,255,0.45)", width=1.2),
                           fillcolor="rgba(0,0,0,0)", layer="below"))

    # ── Centre circle (attacking half semicircle) ──────────────────────
    cx_r = 9.15 / 68.0 * 100
    cx_y = 9.15 / 105.0 * 100
    t_semi = np.linspace(0, np.pi, 60)
    semi_x = PEN_SPOT_Y + cx_r * np.cos(t_semi)   # Opta-y coords
    semi_y = FK_HALF_LINE + cx_y * np.sin(t_semi)  # Opta-x coords
    path_semi = "M " + " L ".join(
        f"{100 - x:.2f},{y:.2f}" for x, y in zip(semi_x, semi_y)
    )
    shapes.append(dict(type="path", path=path_semi,
                       line=dict(color="rgba(255,255,255,0.45)", width=1.2),
                       fillcolor="rgba(0,0,0,0)", layer="below"))

    return shapes


def _build_fk_shot_pitch_map(direct_shots: list) -> go.Figure:
    """
    Offensive-half pitch showing the origin of each direct FK shot.
    fig_x = Opta y  (width 0→100)
    fig_y = Opta x  (depth, goal at top)
    """
    fig = go.Figure()

    # ── Pitch shapes (offensive half) ─────────────────────────────────────
    for shape in _fk_pitch_shapes():
        fig.add_shape(**shape)

    # Penalty spot
    fig.add_trace(go.Scatter(
        x=[100 - PEN_SPOT_Y], y=[PEN_SPOT_X],
        mode="markers",
        marker=dict(size=7, color="rgba(255,255,255,0.55)", symbol="circle"),
        showlegend=False, hoverinfo="skip",
    ))

    if not direct_shots:
        apply_chart_theme(fig, "dark")
        fig.update_layout(**_fk_pitch_layout("Direct FK Shots — Origin & Trajectory", []))
        return fig

    # ── Trajectory lines: origin → end point (blocked coords or omitted) ──────
    for s in direct_shots:
        ex = s.get("end_x")
        ey = s.get("end_y")
        if ex is None or ey is None:
            continue
        color = FK_OUTCOME_COLORS.get(s.get("outcome", ""), CLEAR_CLR)
        fig.add_trace(go.Scatter(
            x=[100 - s["start_y"], 100 - ey],
            y=[s["start_x"],       ex],
            mode="lines",
            line=dict(color=color, width=1.2, dash="dot"),
            opacity=0.55,
            showlegend=False, hoverinfo="skip",
        ))

    legend_shown: set = set()
    for outcome in _FK_OUTCOME_ORDER:
        group = [s for s in direct_shots if s.get("outcome") == outcome]
        if not group:
            continue
        color   = FK_OUTCOME_COLORS.get(outcome, "#6b7280")
        is_goal = (outcome == "Goal")
        show_lg = outcome not in legend_shown
        legend_shown.add(outcome)

        hover_texts = []
        for s in group:
            bp   = s.get("body_part") or "—"
            desc = ", ".join(s.get("descriptors") or []) or "—"
            hover_texts.append(
                f"<b>{s['minute']}' — {outcome}</b><br>"
                f"Taker: {s.get('taker') or '—'}<br>"
                f"Body part: {bp}<br>"
                f"Descriptors: {desc}"
            )

        fig.add_trace(go.Scatter(
            x=[100 - s["start_y"] for s in group],
            y=[s["start_x"]       for s in group],
            mode="markers",
            name=outcome,
            marker=dict(
                size=15 if is_goal else 12,
                color=color,
                symbol="star" if is_goal else "circle",
                line=dict(color="rgba(255,255,255,0.75)", width=1.5),
                opacity=0.95,
            ),
            text=hover_texts,
            hovertemplate="%{text}<extra></extra>",
            showlegend=show_lg,
        ))

    apply_chart_theme(fig, "dark")

    fig.update_layout(**_fk_pitch_layout("Direct FK Shots — Origin & Trajectory", []))
    return fig


def _fk_pitch_layout(title: str, annotations: list) -> dict:
    extra = [
        dict(x=50, y=GOAL_LINE + GOAL_DEPTH / 2 + 0.3,
             text="GOAL", showarrow=False,
             font=dict(size=9, color="rgba(255,255,255,0.75)"),
             xanchor="center"),
        dict(x=50, y=FK_HALF_LINE_ANN,
             text="Halfway Line", showarrow=False,
             font=dict(size=7, color="rgba(255,255,255,0.28)"),
             xanchor="center"),
    ]
    return dict(
        title=dict(text=title, font=dict(size=11, color="#e2e8f0"),
                   x=0.5, xanchor="center"),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=15, r=15, t=30, b=50),
        height=620,
        xaxis=dict(range=[-5, 105], showgrid=False, zeroline=False,
                   showticklabels=False, fixedrange=True),
        yaxis=dict(range=[FK_FIG_Y_MIN - 1, FIG_Y_MAX + 0.5],
                   showgrid=False, zeroline=False,
                   showticklabels=False, fixedrange=True),
        showlegend=True,
        legend=dict(
            orientation="h", yanchor="top", y=-0.03,
            xanchor="center", x=0.5,
            font=dict(size=10, color="#e2e8f0"),
            bgcolor="rgba(0,0,0,0)", itemsizing="constant",
        ),
        annotations=annotations + extra,
    )


# ─── Helper: layout for the FK delivery map (full offensive half) ─────────────

def _fk_delivery_pitch_layout() -> dict:
    """
    Layout for the offensive-half delivery map.
    The pitch shown spans x=[-5,105] (110 units) and y=[48,104] (56 units).
    scaleanchor+scaleratio=1 locks 1:1 Opta units so the half-pitch looks
    proportional; height=420 keeps the card compact.
    """
    extra = [
        dict(x=50, y=GOAL_LINE + GOAL_DEPTH / 2 + 0.3,
             text="GOAL", showarrow=False,
             font=dict(size=9, color="rgba(255,255,255,0.75)"),
             xanchor="center"),
        dict(x=50, y=FK_HALF_LINE_ANN,
             text="Halfway Line", showarrow=False,
             font=dict(size=7, color="rgba(255,255,255,0.28)"),
             xanchor="center"),
    ]
    return dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=15, r=15, t=10, b=50),
        height=420,
        xaxis=dict(range=[-5, 105], showgrid=False, zeroline=False,
                   showticklabels=False, fixedrange=True,
                   scaleanchor="y", scaleratio=1),
        yaxis=dict(range=[FK_FIG_Y_MIN - 1, FIG_Y_MAX + 0.5],
                   showgrid=False, zeroline=False,
                   showticklabels=False, fixedrange=True),
        showlegend=True,
        legend=dict(
            orientation="h", yanchor="top", y=-0.03,
            xanchor="center", x=0.5,
            font=dict(size=10, color="#e2e8f0"),
            bgcolor="rgba(0,0,0,0)", itemsizing="constant",
        ),
        annotations=extra,
    )


# ─── Helper: pitch map for FK deliveries (box-only) ─────────────────────────────

def _build_fk_delivery_pitch_map(deliveries: list) -> go.Figure:
    """
    Final-third pitch (same as corner kicks) showing FK pass origin → landing.
    Only deliveries whose end point falls inside the penalty box are plotted.
    Lines are coloured by FK delivery type.
    """
    # ── Filter: keep only deliveries that land inside the penalty box ────────
    box_deliveries = [
        d for d in deliveries
        if d.get("end_x") is not None
        and d.get("end_y") is not None
        and d["end_x"] >= PENALTY_LINE
        and PEN_AREA_L <= d["end_y"] <= PEN_AREA_R
    ]

    fig = go.Figure()

    # ── Use the same final-third pitch as the Corner Kicks section ───────────
    for shape in _pitch_shapes(is_left=False):
        fig.add_shape(**shape)

    # ── Extend touchlines from final-third line down to halfway line ─────────
    lc = "rgba(255,255,255,0.50)"
    for xv in (0.0, 100.0):
        fig.add_shape(type="line", x0=xv, x1=xv,
                      y0=FK_HALF_LINE, y1=FIG_Y_MIN,
                      line=dict(color=lc, width=1.5), layer="below")
    # ── Halfway line ─────────────────────────────────────────────────────────
    fig.add_shape(type="line", x0=0, x1=100,
                  y0=FK_HALF_LINE, y1=FK_HALF_LINE,
                  line=dict(color=lc, width=1.5), layer="below")
    # ── Centre circle — attacking semicircle just above halfway line ─────────
    cx_r = 9.15 / 68.0 * 100
    cx_y = 9.15 / 105.0 * 100
    t_semi = np.linspace(0, np.pi, 60)
    semi_x = PEN_SPOT_Y + cx_r * np.cos(t_semi)
    semi_y = FK_HALF_LINE + cx_y * np.sin(t_semi)
    path_semi = "M " + " L ".join(
        f"{100 - x:.2f},{y:.2f}" for x, y in zip(semi_x, semi_y)
    )
    fig.add_shape(type="path", path=path_semi,
                  line=dict(color="rgba(255,255,255,0.45)", width=1.2),
                  fillcolor="rgba(0,0,0,0)", layer="below")

    fig.add_trace(go.Scatter(
        x=[100 - PEN_SPOT_Y], y=[PEN_SPOT_X],
        mode="markers",
        marker=dict(size=7, color="rgba(255,255,255,0.55)", symbol="circle",
                    line=dict(color="rgba(255,255,255,0.55)", width=0)),
        showlegend=False, hoverinfo="skip",
    ))

    if not box_deliveries:
        _layout = _pitch_layout("FK Deliveries into the Box", False, [])
        _layout["yaxis"]["range"] = [FK_FIG_Y_MIN - 1, FIG_Y_MAX + 0.5]
        _layout["xaxis"]["scaleanchor"] = "y"
        _layout["xaxis"]["scaleratio"] = 1
        _layout["height"] = 680
        _layout["annotations"] = _layout.get("annotations", []) + [
            dict(x=50, y=FK_HALF_LINE - 0.8, text="Halfway Line", showarrow=False,
                 font=dict(size=7, color="rgba(255,255,255,0.28)"), xanchor="center"),
        ]
        apply_chart_theme(fig, "dark")
        fig.update_layout(**_layout)
        return fig

    deliveries = box_deliveries  # work with filtered set from here on

    legend_type_shown: set = set()
    legend_oc_shown:   set = set()

    for fk_type in _FK_TYPE_ORDER:
        if fk_type == "Direct Shot":
            continue
        group = [d for d in deliveries if d.get("fk_type") == fk_type]
        if not group:
            continue
        type_color = FK_TYPE_COLORS.get(fk_type, "#6b7280")

        for d in group:
            ex = d.get("end_x")
            ey = d.get("end_y")
            if ex is None or ey is None:
                continue
            fig.add_trace(go.Scatter(
                x=[100 - d["start_y"], 100 - ey],
                y=[d["start_x"],       ex],
                mode="lines",
                line=dict(color=type_color, width=1.2, dash="dot"),
                opacity=0.45,
                showlegend=False, hoverinfo="skip",
            ))

        # ── Origin dots (triangles) coloured by type ──────────────────────
        show_lg = fk_type not in legend_type_shown
        legend_type_shown.add(fk_type)

        hover_texts = []
        for d in group:
            receiver = d.get("receiver") or "—"
            quals = d.get("qualifiers", [])
            quals_str = " · ".join(quals) if quals else "—"
            hover_texts.append(
                f"<b>{d['minute']}' — {d['fk_type']}</b><br>"
                f"Outcome: {d['outcome']}<br>"
                f"Taker: {d.get('taker') or '—'}<br>"
                f"Receiver: {receiver}<br>"
                f"Qualifiers: {quals_str}"
            )
        fig.add_trace(go.Scatter(
            x=[100 - d["start_y"] for d in group],
            y=[d["start_x"]       for d in group],
            mode="markers",
            name=fk_type,
            marker=dict(size=10, color=type_color, symbol="triangle-up",
                        line=dict(color="rgba(255,255,255,0.70)", width=1.2),
                        opacity=0.90),
            text=hover_texts,
            hovertemplate="%{text}<extra></extra>",
            showlegend=show_lg,
        ))

    # ── Landing dots coloured by outcome ──────────────────────────────────
    for outcome in _FK_OUTCOME_ORDER:
        group = [d for d in deliveries
                 if d.get("outcome") == outcome and d.get("end_x") is not None]
        if not group:
            continue
        color   = FK_OUTCOME_COLORS.get(outcome, "#6b7280")
        is_goal = (outcome == "Goal")
        show_lg = outcome not in legend_oc_shown
        legend_oc_shown.add(outcome)

        fig.add_trace(go.Scatter(
            x=[100 - d["end_y"] for d in group],
            y=[d["end_x"]       for d in group],
            mode="markers",
            name=outcome,
            marker=dict(
                size=13 if is_goal else 10,
                color=color,
                symbol="star" if is_goal else "circle",
                line=dict(color="rgba(255,255,255,0.70)", width=1.2),
                opacity=0.95,
            ),
            showlegend=show_lg,
            hoverinfo="skip",
        ))

    _layout = _pitch_layout("FK Deliveries into the Box", False, [])
    _layout["yaxis"]["range"] = [FK_FIG_Y_MIN - 1, FIG_Y_MAX + 0.5]
    _layout["xaxis"]["scaleanchor"] = "y"
    _layout["xaxis"]["scaleratio"] = 1
    _layout["height"] = 680
    _layout["annotations"] = _layout.get("annotations", []) + [
        dict(x=50, y=FK_HALF_LINE - 0.8, text="Halfway Line", showarrow=False,
             font=dict(size=7, color="rgba(255,255,255,0.28)"), xanchor="center"),
    ]
    apply_chart_theme(fig, "dark")
    fig.update_layout(**_layout)
    return fig


# ─── Section A1: FK Deliveries KPI Row ───────────────────────────────────────

def _fk_section_volume_deliveries(data: dict) -> html.Div:
    deliveries = data.get("deliveries", [])
    n = len(deliveries)

    goals = sum(1 for d in deliveries if d.get("outcome") == "Goal")
    sot   = sum(1 for d in deliveries if d.get("outcome") == "Shot on Target")
    soff  = sum(1 for d in deliveries if d.get("outcome") == "Shot off Target")
    post  = sum(1 for d in deliveries if d.get("outcome") == "Hit Post")
    sp    = sum(1 for d in deliveries if d.get("outcome") in ("Second Phase", "Foul Won", "Assist"))
    clear = sum(1 for d in deliveries if d.get("outcome") in ("Cleared / No Shot", "Cleared"))

    def pct(v: int) -> str:
        return f"{v/n*100:.0f}% of deliveries" if n else "—"

    return html.Div([
        html.H6("FK Deliveries — Volume & Outcomes",
                className="buildup-subsection-title"),
        html.Div([
            _mini_kpi("Total Deliveries", n,
                      "crosses & passes", PRIMARY, "bi-send"),
            _mini_kpi("Goals", goals, pct(goals),
                      GOAL_CLR, "bi-trophy-fill"),
            _mini_kpi("Shots on Target", sot, pct(sot),
                      SOT_CLR, "bi-bullseye"),
            _mini_kpi("Shots off Target", soff, pct(soff),
                      SOFF_CLR, "bi-x-circle"),
            _mini_kpi("Hit Post", post, pct(post),
                      "#eab308", "bi-record-circle"),
            _mini_kpi("2nd Phase / Foul", sp, pct(sp),
                      SP_CLR, "bi-arrow-repeat"),
            _mini_kpi("Cleared / No Shot", clear, pct(clear),
                      CLEAR_CLR, "bi-shield"),
        ], className="team-kpi-row"),
    ])


# ─── Section A2: Direct FK Shots KPI Row ──────────────────────────────────────

def _fk_section_volume_shots(data: dict) -> html.Div:
    shots = data.get("direct_shots", [])
    n = len(shots)

    goals   = sum(1 for s in shots if s.get("outcome") == "Goal")
    sot     = sum(1 for s in shots if s.get("outcome") == "Shot on Target")
    soff    = sum(1 for s in shots if s.get("outcome") == "Shot off Target")
    post    = sum(1 for s in shots if s.get("outcome") == "Hit Post")
    blocked = sum(1 for s in shots if s.get("is_blocked", False))
    on_frm  = goals + sot + post  # shots that hit the frame / went in

    def pct(v: int) -> str:
        return f"{v/n*100:.0f}% of shots" if n else "—"

    return html.Div([
        html.H6("Direct FK Shots — Volume & Outcomes",
                className="buildup-subsection-title"),
        html.Div([
            _mini_kpi("Total FK Shots", n,
                      "direct attempts", PRIMARY, "bi-slash-circle"),
            _mini_kpi("Goals", goals, pct(goals),
                      GOAL_CLR, "bi-trophy-fill"),
            _mini_kpi("Shots on Target", sot, pct(sot),
                      SOT_CLR, "bi-bullseye"),
            _mini_kpi("Shots off Target", soff, pct(soff),
                      SOFF_CLR, "bi-x-circle"),
            _mini_kpi("Hit Post", post, pct(post),
                      "#eab308", "bi-record-circle"),
            _mini_kpi("Blocked", blocked, pct(blocked),
                      "#ef4444", "bi-shield-x"),
            _mini_kpi("On Frame", on_frm, pct(on_frm),
                      "#06b6d4", "bi-crosshair"),
        ], className="team-kpi-row"),
    ])


# ─── Section B: Delivery Type Breakdown ───────────────────────────────────────

def _fk_section_delivery_type(data: dict) -> html.Div:
    fk_type_counts   = data.get("fk_type_counts", {})
    fk_type_outcomes = data.get("fk_type_outcomes", {})
    total            = data.get("total", 0)

    types  = [t for t in _FK_TYPE_ORDER if fk_type_counts.get(t, 0) > 0]
    counts = [fk_type_counts.get(t, 0) for t in types]
    colors = [FK_TYPE_COLORS.get(t, "#6b7280") for t in types]

    bar_fig = go.Figure()
    bar_fig.add_trace(go.Bar(
        y=types, x=counts, orientation="h",
        marker=dict(color=colors, opacity=0.85),
        text=[str(c) for c in counts], textposition="outside",
        textfont=dict(size=11, color="#e2e8f0"),
        hovertemplate="%{y}: %{x}<extra></extra>",
    ))
    apply_chart_theme(bar_fig, "dark")
    bar_fig.update_layout(
        margin=dict(l=10, r=30, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        height=max(140, len(types) * 36),
        xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.06)",
                   zeroline=False, color="#94a3b8", tickfont=dict(size=10)),
        yaxis=dict(color="#e2e8f0", tickfont=dict(size=11)),
        showlegend=False,
    )

    # ── Outcome table ────────────────────────────────────────────────────────
    oc_cols = ["Goal", "Shot on Target", "Shot off Target", "Hit Post",
               "Second Phase", "Assist", "Cleared / No Shot"]
    oc_cols_present = [c for c in oc_cols
                       if any(fk_type_outcomes.get(t, {}).get(c, 0) for t in types)]
    if not oc_cols_present:
        oc_cols_present = oc_cols[:4]

    header_cells = [html.Th("Type", style={"padding": "0.4rem 0.6rem",
                                           "color": "var(--text-secondary)",
                                           "fontSize": "0.75rem"})]
    for oc in oc_cols_present:
        header_cells.append(html.Th(
            oc, style={"padding": "0.4rem 0.5rem",
                       "color": FK_OUTCOME_COLORS.get(oc, "#94a3b8"),
                       "fontSize": "0.72rem", "textAlign": "center"}
        ))

    body_rows = []
    for t in types:
        cnt = fk_type_counts.get(t, 0)
        do  = fk_type_outcomes.get(t, {})
        cells = [html.Td(
            html.Span([
                html.Span("●", style={"color": FK_TYPE_COLORS.get(t, "#6b7280"),
                                      "marginRight": "5px"}),
                t,
            ]),
            style={"padding": "0.35rem 0.6rem", "fontSize": "0.85rem",
                   "color": "#e2e8f0", "fontWeight": "600"},
        )]
        for oc in oc_cols_present:
            v   = do.get(oc, 0)
            pct = f"({v/cnt*100:.0f}%)" if cnt and v else ""
            cells.append(html.Td(
                f"{v} {pct}".strip(),
                style={"padding": "0.35rem 0.5rem", "textAlign": "center",
                       "fontSize": "0.82rem",
                       "color": FK_OUTCOME_COLORS.get(oc, "#94a3b8") if v else "var(--text-muted)",
                       "fontWeight": "600" if v else "400"},
            ))
        body_rows.append(html.Tr(cells))

    if not body_rows:
        body_rows = [html.Tr(html.Td("No data", colSpan=len(oc_cols_present) + 1,
                                     style={"padding": "0.5rem",
                                            "color": "var(--text-muted)"}))]

    table = html.Table(
        [html.Thead(html.Tr(header_cells)), html.Tbody(body_rows)],
        style={"width": "100%", "borderCollapse": "separate", "borderSpacing": "2px"},
    )

    return html.Div([
        html.H6("Delivery Type", className="buildup-subsection-title"),
        html.Div([
            html.Div(
                dcc.Graph(figure=bar_fig, config={"displayModeBar": False,
                                                  "responsive": True}),
                style={"flex": "1", "minWidth": "220px"},
            ),
            html.Div(table, style={"flex": "2", "minWidth": "0", "overflowX": "auto"}),
        ], style={"display": "flex", "gap": "1.5rem",
                  "alignItems": "flex-start", "flexWrap": "wrap"}),
    ])


# ─── Section C: Direct Shot Maps ──────────────────────────────────────────────

def _fk_badge_row(counts: dict, colors: dict, order: list) -> html.Div:
    """Mini badge row for body part or descriptor counts."""
    badges = []
    for key in order:
        cnt = counts.get(key, 0)
        if not cnt:
            continue
        color = colors.get(key, "#6b7280")
        badges.append(html.Span(
            [html.B(str(cnt), style={"marginRight": "3px"}), key],
            style={
                "display": "inline-block",
                "padding": "0.2rem 0.55rem",
                "borderRadius": "999px",
                "fontSize": "0.78rem",
                "color": "#e2e8f0",
                "background": f"rgba({_hex_to_rgb(color)},0.18)",
                "border": f"1px solid rgba({_hex_to_rgb(color)},0.45)",
                "marginRight": "6px",
                "marginBottom": "5px",
            },
        ))
    return html.Div(badges, style={"flexWrap": "wrap", "display": "flex"})


def _hex_to_rgb(hex_color: str) -> str:
    """'#aabbcc' → '170,187,204'"""
    h = hex_color.lstrip("#")
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"{r},{g},{b}"
    except Exception:
        return "150,150,150"


_BP_COLORS = {
    "Right Foot": "#3b82f6",
    "Left Foot":  "#f97316",
    "Header":     "#8b5cf6",
}
_BP_ORDER = ["Right Foot", "Left Foot", "Header"]

_DESC_COLORS = {
    "Strong":       "#22c55e",
    "Weak":         "#ef4444",
    "Rising":       "#3b82f6",
    "Dipping":      "#f97316",
    "Swerve Left":  "#8b5cf6",
    "Swerve Right": "#06b6d4",
    "Big Chance":   "#eab308",
    "Deflected":    "#6b7280",
}
_DESC_ORDER = ["Strong", "Weak", "Rising", "Dipping",
               "Swerve Left", "Swerve Right", "Big Chance", "Deflected"]


def _fk_section_direct_shots(data: dict) -> html.Div:
    direct_shots      = data.get("direct_shots", [])
    body_part_counts  = data.get("body_part_counts", {})
    descriptor_counts = data.get("descriptor_counts", {})
    n                 = len(direct_shots)

    if n == 0:
        return html.Div([
            html.H6("Direct FK Shots", className="buildup-subsection-title"),
            html.P("No direct free kick shots recorded.",
                   className="text-muted",
                   style={"padding": "0.5rem 0"}),
        ])

    fig_pitch     = _build_fk_shot_pitch_map(direct_shots)
    fig_goalmouth = _build_goalmouth_figure(direct_shots)

    return html.Div([
        html.H6("Direct FK Shots", className="buildup-subsection-title"),
        html.Div([
            # Left: pitch map
            html.Div([
                html.P("Shot origin · colour = outcome · ★ = goal",
                       className="kpi-subtitle",
                       style={"textAlign": "center", "marginBottom": "0.3rem"}),
                html.Div(
                    dcc.Graph(figure=fig_pitch,
                              config={"displayModeBar": False, "responsive": True}),
                    className="pitch-dark-container",
                ),
            ], style={"flex": "1", "minWidth": "260px"}),
            # Right: goalmouth
            html.Div([
                html.P("Goalmouth zone (GK perspective) · dot = where shot ended up",
                       className="kpi-subtitle",
                       style={"textAlign": "center", "marginBottom": "0.3rem"}),
                html.Div(
                    dcc.Graph(figure=fig_goalmouth,
                              config={"displayModeBar": False, "responsive": True}),
                    className="pitch-dark-container",
                ),
            ], style={"flex": "1", "minWidth": "260px"}),
        ], style={"display": "flex", "gap": "1.5rem", "flexWrap": "wrap",
                  "marginTop": "0.5rem"}),
    ])


# ─── Section D: Delivery Maps ─────────────────────────────────────────────────

# Outcome → (border colour, label) for chain cards
_FK_CHAIN_OUTCOME_META: dict = {
    "Goal":              ("#22c55e", "Goal"),
    "Shot on Target":    ("#3b82f6", "Shot on Target"),
    "Shot off Target":   ("#f97316", "Shot off Target"),
    "Hit Post":          ("#eab308", "Hit Post"),
    "Blocked":           ("#ef4444", "Blocked"),
    "Foul Won":          ("#06b6d4", "Foul Won"),
    "Second Phase":      ("#8b5cf6", "Second Phase"),
    "Cleared / No Shot": ("#6b7280", "Cleared / No Shot"),
}


def _fk_single_chain_card(delivery: dict, idx: int) -> html.Div:
    """Render one FK delivery as a scrollable event-chain strip."""
    chain    = delivery.get("chain", [])
    outcome  = delivery.get("outcome", "Cleared / No Shot")
    minute   = delivery.get("minute", 0)
    fk_type  = delivery.get("fk_type", "—")
    taker    = delivery.get("taker") or "—"
    quals    = delivery.get("qualifiers", [])

    oc_color, oc_label = _FK_CHAIN_OUTCOME_META.get(
        outcome, ("#6b7280", outcome)
    )

    quals_badge = html.Span(
        " · ".join(quals),
        style={
            "fontSize": "0.60rem", "color": "var(--text-muted)",
            "marginLeft": "8px",
        },
    ) if quals else None

    header = html.Div(
        [
            html.Span(f"#{idx + 1}", style={
                "fontWeight": "700", "fontSize": "0.78rem",
                "color": "var(--text-primary)", "marginRight": "8px",
            }),
            html.Span(f"{minute}'", style={
                "fontSize": "0.75rem", "color": "var(--text-secondary)",
                "marginRight": "8px",
            }),
            html.Span(taker, style={
                "fontSize": "0.75rem", "color": "var(--text-primary)",
                "fontWeight": "500", "marginRight": "8px",
            }),
            # FK type badge
            html.Span(fk_type, style={
                "fontSize": "0.60rem", "fontWeight": "600",
                "textTransform": "uppercase", "letterSpacing": "0.5px",
                "padding": "2px 7px", "borderRadius": "4px",
                "background": f"{FK_OUTCOME_COLORS.get(outcome, '#6b7280')}18",
                "color": FK_TYPE_COLORS.get(fk_type, "#6b7280"),
                "marginRight": "6px",
            }),
            # Outcome badge
            html.Span(oc_label, style={
                "fontSize": "0.60rem", "fontWeight": "600",
                "padding": "2px 8px", "borderRadius": "4px",
                "background": f"{oc_color}18",
                "color": oc_color,
            }),
            *([ quals_badge ] if quals_badge else []),
        ],
        style={"display": "flex", "alignItems": "center", "flexWrap": "wrap",
               "gap": "2px", "marginBottom": "6px"},
    )

    chain_elements: list = []
    for i, evt in enumerate(chain):
        if i > 0:
            chain_elements.append(_chain_connector(evt))
        chain_elements.append(_chain_event_node(evt, i, len(chain)))

    if not chain_elements:
        chain_elements = [html.Span("—", style={"color": "var(--text-muted)",
                                                  "fontSize": "0.75rem"})]

    return html.Div(
        [
            header,
            html.Div(chain_elements, className="chain-strip"),
        ],
        className="chain-card",
        style={"borderLeft": f"3px solid {oc_color}"},
    )


def _fk_delivery_chains(deliveries: list) -> html.Div:
    """Collapsible section showing the 10-second event chain for every delivery."""
    if not deliveries:
        return html.Div()

    cards = [_fk_single_chain_card(d, i) for i, d in enumerate(deliveries)]

    return html.Details(
        [
            html.Summary(
                [
                    html.I(className="bi bi-link-45deg",
                           style={"marginRight": "6px", "fontSize": "1rem"}),
                    html.Span("Delivery Chains",
                              style={"fontWeight": "600", "fontSize": "0.85rem"}),
                    html.Span(f" ({len(deliveries)})",
                              style={"color": "var(--text-muted)",
                                     "fontSize": "0.8rem"}),
                ],
                className="buildup-subsection-title",
                style={"cursor": "pointer", "listStyle": "none",
                       "display": "flex", "alignItems": "center",
                       "userSelect": "none"},
            ),
            html.Div(
                cards,
                style={"display": "flex", "flexDirection": "column",
                       "gap": "0.75rem", "marginTop": "0.75rem"},
            ),
        ],
        className="buildup-chains-section",
    )


def _fk_zone_table(zone_counts: dict) -> html.Div:
    """Compact table of delivery landing zones sorted by count."""
    if not zone_counts:
        return html.Div()

    rows = sorted(zone_counts.items(), key=lambda kv: kv[1], reverse=True)
    total = sum(v for _, v in rows)

    tr_rows = []
    for zone, cnt in rows:
        pct = f"{cnt/total*100:.0f}%" if total else "—"
        tr_rows.append(html.Tr([
            html.Td(zone,
                    style={"padding": "0.3rem 0.6rem", "fontSize": "0.82rem",
                           "color": "#e2e8f0"}),
            html.Td(str(cnt),
                    style={"padding": "0.3rem 0.5rem", "textAlign": "center",
                           "fontSize": "0.85rem", "color": "#e2e8f0",
                           "fontWeight": "600"}),
            html.Td(pct,
                    style={"padding": "0.3rem 0.5rem", "textAlign": "center",
                           "fontSize": "0.80rem", "color": "var(--text-secondary)"}),
        ]))

    return html.Table(
        [
            html.Thead(html.Tr([
                html.Th("Landing Zone",
                        style={"padding": "0.4rem 0.6rem",
                               "color": "var(--text-secondary)", "fontSize": "0.75rem"}),
                html.Th("Count",
                        style={"padding": "0.4rem 0.5rem",
                               "color": "var(--text-secondary)", "fontSize": "0.75rem",
                               "textAlign": "center"}),
                html.Th("%",
                        style={"padding": "0.4rem 0.5rem",
                               "color": "var(--text-secondary)", "fontSize": "0.75rem",
                               "textAlign": "center"}),
            ])),
            html.Tbody(tr_rows),
        ],
        style={"width": "100%", "borderCollapse": "separate", "borderSpacing": "2px"},
    )


def _fk_section_deliveries(data: dict) -> html.Div:
    deliveries  = data.get("deliveries", [])
    zone_counts = data.get("zone_counts", {})
    n           = len(deliveries)

    if n == 0:
        return html.Div([
            html.H6("FK Deliveries", className="buildup-subsection-title"),
            html.P("No free kick pass deliveries recorded.",
                   className="text-muted",
                   style={"padding": "0.5rem 0"}),
        ])

    fig_delivery = _build_fk_delivery_pitch_map(deliveries)

    return html.Div([
        html.H6("FK Deliveries", className="buildup-subsection-title"),
        # Pitch map
        html.Div([
            html.P(
                "Only deliveries landing inside the penalty box shown  ·  ▲ = FK origin  ·  ● = landing point  ·  line colour = delivery type  ·  dot colour = outcome",
                className="kpi-subtitle",
                style={"textAlign": "center", "marginBottom": "0.3rem"},
            ),
            html.Div(
                dcc.Graph(figure=fig_delivery,
                          config={"displayModeBar": False, "responsive": True}),
                className="pitch-dark-container",
            ),
        ], style={"marginBottom": "1rem"}),
        # Event chains (collapsible)
        _fk_delivery_chains(deliveries),
    ])


# ─── Main card builder ─────────────────────────────────────────────────────────

def free_kicks_card(data: dict) -> html.Div:
    """
    Render the full Free Kicks analysis card.

    Parameters
    ----------
    data : dict
        Output of ``analyse_free_kicks()``.
    """
    total = data.get("total", 0)

    _header = ds_header(
        "Set Pieces — Free Kicks", "bi-slash-circle",
        "Free Kicks",
        "Deliveries into the box, direct shots and goalmouth placement",
    )

    if total == 0:
        return html.Div(
            [
                _header,
                html.Div(
                    [
                        html.I(className="bi bi-slash-circle me-2",
                               style={"color": "var(--text-muted)", "fontSize": "2rem"}),
                        html.P("No free kicks recorded for this match.",
                               className="text-muted",
                               style={"marginTop": "0.5rem"}),
                    ],
                    style={"textAlign": "center", "padding": "3rem 1rem"},
                ),
            ],
            className="buildup-card ma-card",
            style={"padding": "1.5rem"},
        )

    HR = html.Hr(style={"borderColor": "var(--border-light)", "margin": "1.5rem 0"})

    return html.Div(
        [
            _header,

            # A1 — FK Deliveries KPI row
            html.Div(_fk_section_volume_deliveries(data),
                     style={"marginBottom": "1.5rem"}),

            HR,

            # B — Delivery Type breakdown
            html.Div(_fk_section_delivery_type(data),
                     style={"marginBottom": "1.5rem"}),

            HR,

            # D — Delivery pitch map + chains
            html.Div(_fk_section_deliveries(data),
                     style={"marginBottom": "1.5rem"}),

            HR,

            # A2 — Direct FK Shots KPI row
            html.Div(_fk_section_volume_shots(data),
                     style={"marginBottom": "1.5rem"}),

            HR,

            # C — Direct Shot pitch + goalmouth maps
            html.Div(_fk_section_direct_shots(data)),
        ],
        className="buildup-card ma-card",
        style={"padding": "1.5rem"},
    )
