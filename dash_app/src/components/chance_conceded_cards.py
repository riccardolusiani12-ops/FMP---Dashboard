"""
Defensive Phase — D4: Chances Conceded UI Components
=====================================================
Dash layout components for the Chances Conceded card inside
Defensive Phase → Defensive Castle section.

Mirrors ``chance_creation_cards.py`` (Offensive Phase) but from the
defending team's perspective:

  A — Shot Conceded Overview     KPIs (volume, xG against, SoT%, goals conceded)
  B — Attack Origin Breakdown    How the opponent built each shot
  C — xG Against by Origin       Horizontal bar chart
  D — Shot Origin Zones          Full-pitch 18-zone grid (defensive frame)
  E — Shot Map (defensive half)  ✕ markers for goals conceded (not stars)
  F — Chain-to-Concede Matrix    N · xG · SoT% · GC per attack origin

Shot Quality Tiers are intentionally omitted.

Coordinate system (after flip in analytics module)
───────────────────────────────────────────────────
  x : 0 = own goal-line   → 100 = opponent goal-line
  y : 0 = right touchline → 100 = left touchline
  Own penalty area: x ∈ [0, 16.5], y ∈ [21, 79]
"""

from __future__ import annotations

from dash import html, dcc
import plotly.graph_objects as go

from src.styling.theme import COLORS_DARK, SEMANTIC_COLORS
from src.styling.plotly_template import apply_chart_theme
from src.styling.ui_components import ds_header

from src.analytics.chance_creation import ORIGIN_LABELS
from src.components.chance_creation_cards import TIER_META

# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

PRIMARY = COLORS_DARK["accent"]   # "#8a1f33"

# Re-use the same origin colours/icons as chance_creation (consistent UX) —
# canonical attack-origin taxonomy (SEMANTIC_COLORS origin_*, values unchanged)
ORIGIN_COLORS: dict[str, str] = {
    "Set Piece":       SEMANTIC_COLORS["origin_set_piece"],
    "High Regain":     SEMANTIC_COLORS["origin_high_regain"],
    "Cross":           SEMANTIC_COLORS["origin_cross"],
    "Through Ball":    SEMANTIC_COLORS["origin_through_ball"],
    "Cut Back":        SEMANTIC_COLORS["origin_cut_back"],
    "Individual Play": SEMANTIC_COLORS["origin_individual_play"],
    "Combination":     SEMANTIC_COLORS["origin_combination"],
    "TOTAL":           COLORS_DARK["accent"],
}

ORIGIN_ICONS: dict[str, str] = {
    "Set Piece":       "bi-flag-fill",
    "High Regain":     "bi-shield-fill-exclamation",
    "Cross":           "bi-arrow-up-right",
    "Through Ball":    "bi-chevron-double-up",
    "Cut Back":        "bi-arrow-return-left",
    "Individual Play": "bi-person-fill-up",
    "Combination":     "bi-shuffle",
}

# Matrix row display config — GC replaces GS (Goals Scored → Goals Conceded)
MATRIX_ROWS = ["N", "xG", "SoT%", "GC"]
ROW_META: dict[str, dict] = {
    "N":    {"color": "#94a3b8", "fmt": "d"},
    "xG":   {"color": "#ef4444", "fmt": ".2f"},   # red — dangerous
    "SoT%": {"color": "#f97316", "fmt": ".1f%"},  # orange — pressure
    "GC":   {"color": "#ef4444", "fmt": "d"},      # red — conceded
}

# 18-zone grid edges (full pitch)
_X_EDGES = [0.0, 16.67, 33.33, 50.0, 66.67, 83.33, 100.0]
_Y_EDGES = [0.0, 33.33, 66.67, 100.0]
_N_ROWS  = 6
_N_COLS  = 3

# Half-space y boundaries (for origin zones visual overlay)
_HS_Y_VALS = (15.0, 30.0, 70.0, 85.0)


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


def _classify_18zone(x: float, y: float) -> int:
    row = min(int(x / 16.67), 5)
    col = min(int(y / 33.33), 2)
    return row * 3 + col + 1


# ═══════════════════════════════════════════════════════════════════════════════
# A. SHOT CONCEDED OVERVIEW KPIs
# ═══════════════════════════════════════════════════════════════════════════════

def _section_shot_overview(data: dict) -> html.Div:
    sm  = data.get("shot_metrics", {})
    gc  = data.get("goals_conceded", 0)
    xga = data.get("xg_against", 0.0)
    bc  = data.get("big_chances_conceded", 0)

    return html.Div(
        [
            html.H6("Shots Conceded — Overview", className="buildup-subsection-title"),
            html.Div(
                [
                    _mini_kpi(
                        "Total Shots Faced", sm.get("shots_total", 0),
                        "shots taken by opponent",
                        "#ef4444", "bi-crosshair",
                    ),
                    _mini_kpi(
                        "In-Box", sm.get("shots_in_box", 0),
                        f"{sm.get('pct_in_box', 0)}% of shots faced",
                        "#8b5cf6", "bi-box-arrow-in-down-right",
                    ),
                    _mini_kpi(
                        "Out-Box", sm.get("shots_out_box", 0),
                        f"{sm.get('pct_out_box', 0)}% of shots faced",
                        "#6b7280", "bi-box-arrow-up-right",
                    ),
                    _mini_kpi(
                        "SoT Faced %", f"{sm.get('sot_pct_total', 0)}%",
                        "opponent shots on target",
                        "#f97316", "bi-bullseye",
                    ),
                    _mini_kpi(
                        "xG Against", f"{xga:.2f}",
                        f"xG/Shot: {sm.get('xg_per_shot', 0):.2f}",
                        "#ef4444", "bi-graph-down-arrow",
                    ),
                    _mini_kpi(
                        "Goals Conceded", gc,
                        f"Big chances: {bc}",
                        "#8a1f33", "bi-x-circle-fill",
                    ),
                ],
                className="team-kpi-row",
            ),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# B. ATTACK ORIGIN BREAKDOWN
# ═══════════════════════════════════════════════════════════════════════════════

def _section_origin_breakdown(shots_detail: list) -> html.Div:
    total = max(len(shots_detail), 1)
    counts: dict[str, int] = {o: 0 for o in ORIGIN_LABELS}
    for s in shots_detail:
        origin = s.get("origin", "Combination")
        if origin in counts:
            counts[origin] += 1

    # Stacked horizontal bar
    bar_fig = go.Figure()
    for origin in ORIGIN_LABELS:
        count = counts[origin]
        if count == 0:
            continue
        pct = round(count / total * 100, 1)
        bar_fig.add_trace(go.Bar(
            y=["Origin"],
            x=[pct],
            orientation="h",
            name=origin,
            marker_color=ORIGIN_COLORS[origin],
            text=[f"{origin} {pct}%"],
            textposition="inside",
            textfont=dict(size=10, color="#fff"),
            hovertemplate=f"{origin}: {count} ({pct}%)<extra></extra>",
        ))
    apply_chart_theme(bar_fig, "dark")
    bar_fig.update_layout(
        barmode="stack",
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=0, b=0), height=42,
        xaxis=dict(showgrid=False, showticklabels=False,
                   range=[0, 100], fixedrange=True),
        yaxis=dict(showgrid=False, showticklabels=False, fixedrange=True),
        showlegend=False,
    )

    cards = []
    for origin in ORIGIN_LABELS:
        count = counts[origin]
        if count == 0:
            continue
        pct    = round(count / total * 100, 1)
        gc     = sum(1 for s in shots_detail
                     if s.get("origin") == origin and s.get("is_goal"))
        xg_sum = sum(s.get("xG", 0.0) for s in shots_detail
                     if s.get("origin") == origin)
        cards.append(
            html.Div(
                [
                    html.Div(
                        html.I(className=f"bi {ORIGIN_ICONS[origin]}",
                               style={"color": ORIGIN_COLORS[origin],
                                      "fontSize": "1.1rem"}),
                        className="kpi-icon",
                    ),
                    html.Div(
                        [
                            html.Span(origin, className="kpi-label"),
                            html.Span(str(count), className="kpi-value"),
                            html.Span(
                                f"{pct}% · {gc}GC · xGA {xg_sum:.2f}",
                                className="kpi-subtitle",
                                style={"color": ORIGIN_COLORS[origin]},
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
            html.H6("Attack Origin Breakdown",
                    className="buildup-subsection-title"),
            html.Div(
                "How the opponent built each shot conceded — "
                "Set Piece → High Regain → Cross → Through Ball → Cut Back → Combination",
                style={"fontSize": "0.78rem", "color": "var(--text-muted)",
                       "marginBottom": "0.6rem"},
            ),
            html.Div(cards, className="team-kpi-row"),
            dcc.Graph(figure=bar_fig, config={"displayModeBar": False},
                      style={"marginTop": "0.5rem"}),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# C. xGA BY ORIGIN  (horizontal bar)
# ═══════════════════════════════════════════════════════════════════════════════

def _section_xg_by_origin(matrix: dict) -> html.Div:
    origins = [o for o in ORIGIN_LABELS
               if matrix.get(o, {}).get("xG", 0) > 0]
    if not origins:
        return html.Div()

    xg_vals = [matrix[o]["xG"] for o in origins]
    colors  = [ORIGIN_COLORS[o] for o in origins]

    fig = go.Figure(go.Bar(
        y=origins,
        x=xg_vals,
        orientation="h",
        marker_color=colors,
        text=[f"{v:.2f}" for v in xg_vals],
        textposition="outside",
        textfont=dict(size=11, color="#e2e8f0"),
        hovertemplate="%{y}: xGA = %{x:.2f}<extra></extra>",
    ))
    apply_chart_theme(fig, "dark")
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=80, r=50, t=10, b=10),
        height=max(120, len(origins) * 35),
        xaxis=dict(showgrid=False, showticklabels=False, fixedrange=True),
        yaxis=dict(showgrid=False, fixedrange=True, autorange="reversed",
                   tickfont=dict(size=11, color="#94a3b8")),
        showlegend=False,
    )

    return html.Div(
        [
            html.H6("xG Against by Attack Origin",
                    className="buildup-subsection-title"),
            dcc.Graph(figure=fig, config={"displayModeBar": False}),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# D. SHOT ORIGIN ZONES  (full-pitch 18-zone grid — defensive frame)
# ═══════════════════════════════════════════════════════════════════════════════

def _section_origin_grid(shots_detail: list) -> html.Div:
    """Full-pitch 18-zone grid showing where conceded shots came from."""
    if not shots_detail:
        return html.Div()

    # With flipped coords, shots should cluster in zones 1-6 (our defensive third)
    zone_pos: dict[int, int] = {z: 0 for z in range(1, 19)}
    zone_neg: dict[int, int] = {z: 0 for z in range(1, 19)}

    for s in shots_detail:
        z = _classify_18zone(s["x"], s["y"])
        if s.get("is_goal") or s.get("on_target"):
            zone_pos[z] += 1
        else:
            zone_neg[z] += 1

    fig = go.Figure()

    max_count = max(
        (zone_pos[z] + zone_neg[z] for z in range(1, 19)), default=1
    ) or 1

    for zone_num in range(1, 19):
        row = (zone_num - 1) // _N_COLS
        col = (zone_num - 1) % _N_COLS
        x0  = _X_EDGES[row]
        x1  = _X_EDGES[row + 1]
        y0  = _Y_EDGES[col]
        y1  = _Y_EDGES[col + 1]
        cx  = (x0 + x1) / 2
        cy  = (y0 + y1) / 2

        pos   = zone_pos[zone_num]
        neg   = zone_neg[zone_num]
        total = pos + neg
        intensity = total / max_count if max_count else 0

        # Defensive zones (1-6 = own third after flip) glow red; rest dim
        if zone_num <= 6:
            fill_a = 0.10 + 0.60 * intensity if total else 0.04
            fill   = f"rgba(239,68,68,{fill_a:.2f})"
        else:
            fill   = "rgba(255,255,255,0.02)"

        fig.add_shape(
            type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
            line=dict(color="rgba(255,255,255,0.10)", width=0.5),
            fillcolor=fill, layer="below",
        )

        if total > 0:
            fig.add_annotation(
                x=cx, y=cy + 4,
                text=f"<b>{total}</b>",
                showarrow=False,
                font=dict(size=16, color="#f0f0f0"),
            )
            fig.add_annotation(
                x=cx, y=cy - 4,
                text=f"Z{zone_num}",
                showarrow=False,
                font=dict(size=9, color="rgba(255,255,255,0.55)"),
            )
            dot_parts: list[str] = []
            if pos > 0:
                dot_parts.append(
                    f"<span style='color:#ef4444'>✕{pos}</span>"
                )
            if neg > 0:
                dot_parts.append(
                    f"<span style='color:#6b7280'>●{neg}</span>"
                )
            if dot_parts:
                fig.add_annotation(
                    x=cx, y=cy - 12,
                    text=" ".join(dot_parts),
                    showarrow=False,
                    font=dict(size=10),
                )
        else:
            fig.add_annotation(
                x=cx, y=cy,
                text=f"Z{zone_num}",
                showarrow=False,
                font=dict(size=9, color="rgba(255,255,255,0.18)"),
            )

    # Zone grid lines
    for y_val in (33.33, 66.67):
        fig.add_shape(type="line", x0=0, x1=100, y0=y_val, y1=y_val,
                      line=dict(color="rgba(255,255,255,0.12)", width=1),
                      layer="below")
    for x_val in _X_EDGES[1:-1]:
        fig.add_shape(type="line", x0=x_val, x1=x_val, y0=0, y1=100,
                      line=dict(color="rgba(255,255,255,0.12)", width=1),
                      layer="below")

    # Pitch outline
    fig.add_shape(type="rect", x0=0, x1=100, y0=0, y1=100,
                  line=dict(color="rgba(255,255,255,0.35)", width=1.5),
                  fillcolor="rgba(0,0,0,0)")
    fig.add_shape(type="line", x0=50, x1=50, y0=0, y1=100,
                  line=dict(color="rgba(255,255,255,0.25)", width=1, dash="dash"),
                  layer="below")
    # Own penalty box highlight
    fig.add_shape(type="rect", x0=0, x1=16.5, y0=21, y1=79,
                  line=dict(color="rgba(239,68,68,0.40)", width=2),
                  fillcolor="rgba(239,68,68,0.06)")
    fig.add_shape(type="rect", x0=83.5, x1=100, y0=21, y1=79,
                  line=dict(color="rgba(255,255,255,0.18)", width=1),
                  fillcolor="rgba(0,0,0,0)")
    # Defensive third line
    fig.add_shape(type="line", x0=33.33, x1=33.33, y0=0, y1=100,
                  line=dict(color="rgba(239,68,68,0.5)", width=2, dash="dash"))

    fig.add_annotation(x=8, y=-6, text="← OWN GOAL", showarrow=False,
                       font=dict(size=9, color="rgba(255,255,255,0.35)"))
    fig.add_annotation(x=92, y=-6, text="ATK →", showarrow=False,
                       font=dict(size=9, color="rgba(255,255,255,0.35)"))

    apply_chart_theme(fig, "dark")

    fig.update_layout(
        plot_bgcolor="rgba(15,25,35,0.7)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=10, b=20), height=400,
        xaxis=dict(range=[-2, 102], showgrid=False, showticklabels=False,
                   fixedrange=True, zeroline=False),
        yaxis=dict(range=[-10, 105], showgrid=False, showticklabels=False,
                   fixedrange=True, zeroline=False,
                   scaleanchor="x", scaleratio=0.68),
        showlegend=False,
    )

    return html.Div(
        [
            html.H6("Shot Origin Zones — Defensive Frame",
                    className="buildup-subsection-title"),
            html.Div(
                [
                    html.Span("✕ ", style={"color": "#ef4444", "fontSize": "0.85rem"}),
                    html.Span("on target / goal conceded", style={
                        "fontSize": "0.75rem", "color": "var(--text-muted)",
                        "marginRight": "1rem"}),
                    html.Span("● ", style={"color": "#6b7280", "fontSize": "0.85rem"}),
                    html.Span("miss / blocked", style={
                        "fontSize": "0.75rem", "color": "var(--text-muted)"}),
                ],
                style={"marginBottom": "0.5rem"},
            ),
            html.Div(
                dcc.Graph(figure=fig, config={"displayModeBar": False}),
                className="pitch-dark-container",
            ),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# E. SHOT MAP — defensive left half  (✕ = goal conceded, circle = shot saved/missed)
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_defensive_half(fig: go.Figure) -> None:
    """Draw the left half of the pitch (defensive half, x ∈ [0, 50])."""
    line_color = "rgba(255,255,255,0.25)"
    lw = 1.5

    shapes = [
        # Pitch outline (left half)
        dict(type="rect", x0=0, y0=0, x1=50, y1=100,
             line=dict(color=line_color, width=lw)),
        # Own penalty box
        dict(type="rect", x0=0, y0=21.1, x1=16.5, y1=78.9,
             line=dict(color="rgba(239,68,68,0.55)", width=2)),
        # Six-yard box
        dict(type="rect", x0=0, y0=36.8, x1=5.5, y1=63.2,
             line=dict(color=line_color, width=lw)),
        # Penalty spot
        dict(type="circle", x0=11.5 - 0.6, y0=50 - 0.6,
             x1=11.5 + 0.6, y1=50 + 0.6,
             fillcolor=line_color, line=dict(color=line_color, width=0)),
        # D-arc (partial)
        dict(type="circle",
             x0=11.5 - 9.15, y0=50 - 9.15,
             x1=11.5 + 9.15, y1=50 + 9.15,
             line=dict(color=line_color, width=lw)),
        # Goal (left side)
        dict(type="rect", x0=-2, y0=44.2, x1=0, y1=55.8,
             line=dict(color=line_color, width=lw)),
        # Halfway line
        dict(type="line", x0=50, y0=0, x1=50, y1=100,
             line=dict(color="rgba(255,255,255,0.22)", width=1, dash="dash")),
        # Defensive third boundary
        dict(type="line", x0=33.33, y0=0, x1=33.33, y1=100,
             line=dict(color="rgba(255,255,255,0.12)", width=1, dash="dot")),
    ]
    for s in shapes:
        fig.add_shape(**s)


# ═══════════════════════════════════════════════════════════════════════════════
# E. SHOT QUALITY TIERS (CONCEDED)
# ═══════════════════════════════════════════════════════════════════════════════

def _section_shot_quality(tiers: dict, shots_detail: list) -> html.Div:
    """Shot quality tier distribution for chances conceded — donut chart + KPI cards."""
    total = max(len(shots_detail), 1)

    tier_keys = ["level_3_converted", "level_2_threat", "level_0_low"]
    labels, values, colors = [], [], []
    for tk in tier_keys:
        meta = TIER_META[tk]
        t = tiers.get(tk, {})
        labels.append(meta["label"])
        values.append(t.get("count", 0))
        colors.append(meta["color"])

    donut_fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        hole=0.55,
        marker=dict(colors=colors, line=dict(color="rgba(0,0,0,0.3)", width=1)),
        textinfo="label+percent",
        textfont=dict(size=11, color="#e2e8f0"),
        hovertemplate="%{label}: %{value} shots (%{percent})<extra></extra>",
        sort=False,
    )])
    apply_chart_theme(donut_fig, "dark")
    donut_fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=10, b=10), height=220,
        showlegend=False,
        annotations=[dict(
            text=f"<b>{total}</b><br><span style='font-size:10px'>shots</span>",
            x=0.5, y=0.5, font_size=18, font_color="#e2e8f0",
            showarrow=False,
        )],
    )

    cards = []
    for tk in tier_keys:
        meta = TIER_META[tk]
        t = tiers.get(tk, {})
        cards.append(
            _mini_kpi(
                meta["label"], t.get("count", 0),
                f"{t.get('pct', 0)}% · {meta['desc']}",
                meta["color"], meta["icon"],
            )
        )

    return html.Div(
        [
            html.H6("Shot Quality Tiers Conceded", className="buildup-subsection-title"),
            html.Div(
                [
                    html.Div(
                        dcc.Graph(figure=donut_fig, config={"displayModeBar": False}),
                        style={"flex": "0 0 240px", "minWidth": "200px"},
                    ),
                    html.Div(
                        cards,
                        className="team-kpi-row",
                        style={"flex": "1", "minWidth": "0"},
                    ),
                ],
                style={"display": "flex", "gap": "1.5rem",
                       "alignItems": "center", "flexWrap": "wrap"},
            ),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# F. SHOT MAP (defensive half)
# ═══════════════════════════════════════════════════════════════════════════════

def _section_shot_map(shots_detail: list) -> html.Div:
    """Scatter plot of shots conceded on the defensive half of the pitch.

    Goals conceded are shown with a bold red ✕ (x-mark);
    other shots (saved, missed, blocked) with a circle.
    Color encodes the attack origin.
    """
    if not shots_detail:
        return html.Div()

    fig = go.Figure()

    for origin in ORIGIN_LABELS:
        origin_shots = [s for s in shots_detail if s.get("origin") == origin]
        if not origin_shots:
            continue

        color  = ORIGIN_COLORS[origin]
        goals  = [s for s in origin_shots if s.get("is_goal")]
        others = [s for s in origin_shots if not s.get("is_goal")]

        def _tip(s: dict) -> str:
            return (
                f"{s.get('player', '?')}<br>"
                f"{s.get('minute', 0)}' — xG {s.get('xG', 0.0):.2f}"
                + (" ✕ GOAL CONCEDED" if s.get("is_goal") else "")
            )

        # Non-goals (circles)
        if others:
            fig.add_trace(go.Scatter(
                x=[s["x"] for s in others],
                y=[s["y"] for s in others],
                mode="markers",
                marker=dict(
                    size=10, color=color, opacity=0.70,
                    line=dict(color="rgba(255,255,255,0.35)", width=1),
                ),
                name=origin,
                text=[_tip(s) for s in others],
                hoverinfo="text",
            ))

        # Goals conceded — bold red ✕
        if goals:
            fig.add_trace(go.Scatter(
                x=[s["x"] for s in goals],
                y=[s["y"] for s in goals],
                mode="markers",
                marker=dict(
                    size=16,
                    color="#ef4444",
                    symbol="x",
                    line=dict(color="#fff", width=2),
                ),
                name=f"{origin} (GC)",
                text=[_tip(s) for s in goals],
                hoverinfo="text",
            ))

    _draw_defensive_half(fig)

    apply_chart_theme(fig, "dark")

    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=5, r=5, t=5, b=5),
        height=320,
        xaxis=dict(range=[-3, 53], showgrid=False, showticklabels=False,
                   fixedrange=True, zeroline=False),
        yaxis=dict(range=[-2, 102], showgrid=False, showticklabels=False,
                   fixedrange=True, zeroline=False, scaleanchor="x"),
        showlegend=True,
        legend=dict(
            orientation="h", yanchor="bottom", y=-0.18,
            xanchor="center", x=0.5,
            font=dict(size=10, color="#94a3b8"),
            bgcolor="rgba(0,0,0,0)",
        ),
    )

    return html.Div(
        [
            html.H6("Shot Map — Defensive Half", className="buildup-subsection-title"),
            html.Div(
                "✕ = goal conceded · circle = shot saved/missed · colour = attack origin",
                style={"fontSize": "0.75rem", "color": "var(--text-muted)",
                       "marginBottom": "0.5rem"},
            ),
            html.Div(
                dcc.Graph(figure=fig, config={"displayModeBar": False}),
                className="pitch-dark-container",
            ),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# F. CHAIN-TO-CONCEDE MATRIX
# ═══════════════════════════════════════════════════════════════════════════════

def _section_chain_to_concede_matrix(matrix: dict) -> html.Div:
    """Render the Chain-to-Concede Matrix: 6 origins × 4 rows (N, xG, SoT%, GC)."""
    columns = ORIGIN_LABELS + ["TOTAL"]

    # Header
    header_cells = [html.Th("", style={"width": "60px"})]
    for col in columns:
        color = ORIGIN_COLORS.get(col, PRIMARY)
        header_cells.append(html.Th(
            col,
            style={
                "color": color, "fontWeight": "600", "fontSize": "0.78rem",
                "textAlign": "center", "padding": "0.6rem 0.5rem",
                "textTransform": "uppercase", "letterSpacing": "0.5px",
            },
        ))

    # Body rows
    body_rows = []
    for row_key in MATRIX_ROWS:
        meta = ROW_META[row_key]
        row_cells = [
            html.Td(
                row_key,
                style={"fontWeight": "600", "color": meta["color"],
                       "fontSize": "0.82rem", "padding": "0.5rem 0.6rem"},
            )
        ]

        values = [matrix.get(col, {}).get(row_key, 0) for col in columns]
        max_val = max(values) if values else 0

        for i, col in enumerate(columns):
            val      = values[i]
            is_total = col == "TOTAL"
            is_max   = (val == max_val and max_val > 0 and not is_total)

            if meta["fmt"] == "d":
                display = str(int(val))
            elif meta["fmt"] == ".1f%":
                display = f"{val:.1f}%"
            else:
                display = f"{val:.2f}"

            cell_style = {
                "textAlign": "center", "padding": "0.5rem 0.4rem",
                "fontSize": "0.95rem",
                "fontWeight": "700" if is_total else "600",
                "borderRadius": "6px",
            }
            if is_total:
                cell_style["color"] = PRIMARY
                cell_style["background"] = "rgba(138, 31, 51, 0.08)"
            elif is_max:
                cell_style["color"] = ORIGIN_COLORS.get(col, "#fff")
                cell_style["background"] = "rgba(138, 31, 51, 0.06)"
            else:
                cell_style["color"] = "var(--text-secondary)"

            row_cells.append(html.Td(display, style=cell_style))

        body_rows.append(html.Tr(row_cells))

    table = html.Table(
        [
            html.Thead(html.Tr(header_cells)),
            html.Tbody(body_rows),
        ],
        style={
            "width": "100%", "borderCollapse": "separate", "borderSpacing": "4px",
        },
    )

    return html.Div(
        [
            html.H6("Chain-to-Concede Matrix",
                    className="buildup-subsection-title"),
            html.Div(
                "Rows: N (shots faced) · xG (xG against) · "
                "SoT% (shots on target %) · GC (goals conceded) "
                "— columns = opponent attack origin",
                style={"fontSize": "0.75rem", "color": "var(--text-muted)",
                       "marginBottom": "0.8rem"},
            ),
            html.Div(
                table,
                className="pitch-dark-container chain-goal-matrix-table",
                style={"borderRadius": "var(--radius-sm)",
                       "padding": "0.8rem", "overflowX": "auto"},
            ),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# FULL CARD ASSEMBLER
# ═══════════════════════════════════════════════════════════════════════════════

def chance_conceded_card(data: dict) -> html.Div:
    """
    Assemble the complete Chances Conceded card.

    Parameters
    ----------
    data : dict
        Output of ``analyse_chance_conceded()``.
    """
    shots   = data.get("shots_detail", [])
    matrix  = data.get("chain_to_concede_matrix", {})
    sm      = data.get("shot_metrics", {})
    opp     = data.get("opponent", "Opponent")

    _header = ds_header(
        "Defensive Phase — Chance Conceded", "bi-shield-x",
        "Chances Conceded",
        f"Shots conceded vs {opp} — where they came from, "
        "how they were created, and how dangerous they were",
    )

    if sm.get("shots_total", 0) == 0 and not shots:
        return html.Div(
            [
                _header,
                html.P(
                    "No opponent shots found for this match.",
                    className="text-muted",
                    style={"padding": "2rem", "textAlign": "center"},
                ),
            ],
            className="buildup-card ma-card",
        )

    sep = html.Hr(
        style={"borderColor": "var(--border-light)", "margin": "1.5rem 0"}
    )

    sections = [
        _header,

        # A — Overview KPIs
        _section_shot_overview(data),
        sep,

        # B — Attack origin breakdown
        _section_origin_breakdown(shots),
        sep,

        # C — xGA by origin
        _section_xg_by_origin(matrix),
        sep,

        # D — Origin zones (defensive frame)
        _section_origin_grid(shots),
        sep,

        # E — Shot quality tiers
        _section_shot_quality(data.get("shot_quality_tiers", {}), shots),
        sep,

        # F — Shot map (defensive half)
        _section_shot_map(shots),
        sep,

        # G — Chain-to-Concede matrix
        _section_chain_to_concede_matrix(matrix),
    ]

    return html.Div(sections, className="buildup-card ma-card")
