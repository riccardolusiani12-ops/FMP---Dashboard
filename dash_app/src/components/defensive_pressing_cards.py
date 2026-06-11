"""
Defensive Phase D1 — Pressing & Defensive Actions: UI Components
=================================================================
Dash layout components for the D1 pressing card inside the Defensive Phase.

Sections rendered:
  A — PPDA Overview          (4 KPI cards + total defensive actions)
  B — Pressing Height        (stacked bar + median pressing-line KPI)
  C — Pressing Direction     (stacked bar + L/C/R KPI cards)
  D — Pressing Success by Zone  (grouped success/fail bars per zone group)
  E — Defensive Action Heatmap  (18-zone pitch heatmap)
  F — All Actions Pitch Map  (full-pitch scatter by action type + median line)
  G — Outcome Pitch Map      (full-pitch scatter: successful vs unsuccessful)

Follows the exact same visual patterns as final_third_cards.py and
chance_creation_cards.py.
"""

from __future__ import annotations

from dash import html, dcc
import plotly.graph_objects as go

from src.styling.theme import COLORS_DARK, SEMANTIC_COLORS
from src.styling.plotly_template import apply_chart_theme
from src.styling.pitch_utils import draw_pitch
from src.styling.ui_components import ds_header

# ═══════════════════════════════════════════════════════════════════════════════
# PALETTE — bound to the shared design system (values unchanged, see theme.py)
# ═══════════════════════════════════════════════════════════════════════════════

PRIMARY    = COLORS_DARK["accent"]                 # "#8a1f33"
HIGH_COLOR = SEMANTIC_COLORS["press_high"]         # red — aggressive / high press
MID_COLOR  = SEMANTIC_COLORS["press_mid"]          # orange
LOW_COLOR  = SEMANTIC_COLORS["press_low"]          # grey — low block
SUCCESS_COLOR = SEMANTIC_COLORS["outcome_positive"]
FAIL_COLOR    = SEMANTIC_COLORS["outcome_negative"]

CORRIDOR_COLORS = {
    "L": SEMANTIC_COLORS["corridor_left"],     # blue
    "C": SEMANTIC_COLORS["corridor_centre"],   # purple
    "R": SEMANTIC_COLORS["corridor_right"],    # cyan
}
CORRIDOR_LABELS = {"L": "Left", "C": "Centre", "R": "Right"}

ZONE_GROUP_COLORS = {
    "high": HIGH_COLOR,
    "mid":  MID_COLOR,
    "low":  LOW_COLOR,
}
ZONE_GROUP_LABELS = {
    "high": "High Press",
    "mid":  "Mid Press",
    "low":  "Low Block",
}


# ═══════════════════════════════════════════════════════════════════════════════
# SHARED HELPER — mini KPI card (same pattern across all phases)
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


def _fmt_ppda(val: float | None) -> str:
    if val is None:
        return "N/A"
    return f"{val:.2f}"


# ═══════════════════════════════════════════════════════════════════════════════
# A. OVERVIEW — 3 headline KPIs
# ═══════════════════════════════════════════════════════════════════════════════

def _ppda_color(val: float | None) -> str:
    """Lower PPDA = more aggressive press = greener; higher = worse = redder."""
    if val is None:
        return "#6b7280"
    if val <= 6:
        return "#22c55e"
    if val <= 10:
        return "#f97316"
    return "#ef4444"


# Harmonised to the offside-line purple used on the pitch maps (was #a855f7)
OFFSIDE_COLOR = SEMANTIC_COLORS["offside_line"]   # "#8b5cf6"


def _section_overview(d: dict) -> html.Div:
    """Five headline KPI cards: Total Def. Actions, PPDA, Press Success, Offsides Provoked, Offside Line."""
    ppda_ft  = _fmt_ppda(d.get("ppda_high"))
    total    = d.get("total_def_actions", 0)
    success  = d.get("press_success_rate", 0.0)
    succ_num = d.get("press_success_successful", 0)
    succ_tot = d.get("press_success_total", 0)

    offside_n    = d.get("offsides_provoked", 0) or 0
    offside_line = d.get("offside_line_median")
    offside_line_str = f"{offside_line:.1f}" if offside_line is not None else "N/A"

    return html.Div(
        [
            html.H6("Overview", className="buildup-subsection-title"),
            html.Div(
                [
                    _mini_kpi(
                        "Total Defensive Actions", total,
                        "tackles · interceptions · clearances · aerials · recoveries",
                        PRIMARY, "bi-activity",
                    ),
                    _mini_kpi(
                        "PPDA (Final Third)", ppda_ft,
                        "opp. passes per def. action in their own third",
                        _ppda_color(d.get("ppda_high")), "bi-shield-fill-exclamation",
                    ),
                    _mini_kpi(
                        "Press Success", f"{success}%",
                        f"{succ_num} / {succ_tot} — possession ≥ 10 s after action",
                        SUCCESS_COLOR, "bi-check-circle-fill",
                    ),
                    _mini_kpi(
                        "Offsides Provoked", offside_n,
                        "total offside traps triggered",
                        OFFSIDE_COLOR, "bi-flag-fill",
                    ),
                    _mini_kpi(
                        "Offside Line (median)", offside_line_str,
                        "median x-position of defensive line",
                        OFFSIDE_COLOR, "bi-rulers",
                    ),
                ],
                className="team-kpi-row",
            ),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# B. DEFENSIVE ACTIONS BY THIRD
# ═══════════════════════════════════════════════════════════════════════════════

def _section_defensive_actions(d: dict) -> html.Div:
    """
    Three KPI cards (Own Third / Middle Third / Final Third) with the number
    of defensive actions in each zone, plus a stacked bar for proportion.
    """
    high_pct = d.get("high_press_pct", 0.0)
    mid_pct  = d.get("mid_press_pct",  0.0)
    low_pct  = d.get("low_block_pct",  0.0)
    high_n   = d.get("high_press_count", 0)
    mid_n    = d.get("mid_press_count",  0)
    low_n    = d.get("low_block_count",  0)

    fig = go.Figure()
    for label, pct, n, color in [
        ("Final Third", high_pct, high_n, HIGH_COLOR),
        ("Middle Third", mid_pct, mid_n,  MID_COLOR),
        ("Own Third",   low_pct, low_n,  LOW_COLOR),
    ]:
        if n == 0:
            continue
        fig.add_trace(go.Bar(
            y=["Actions"],
            x=[pct],
            orientation="h",
            name=label,
            marker_color=color,
            text=[f"{label} {pct}%"],
            textposition="inside",
            textfont=dict(size=11, color="#fff"),
            hovertemplate=f"{label}: {n} ({pct}%)<extra></extra>",
        ))

    apply_chart_theme(fig, "dark")
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
            "Own Third", low_n,
            f"{low_pct}% of actions — defensive block",
            LOW_COLOR, "bi-shield",
        ),
        _mini_kpi(
            "Middle Third", mid_n,
            f"{mid_pct}% of actions — mid-field press",
            MID_COLOR, "bi-shield-half",
        ),
        _mini_kpi(
            "Final Third", high_n,
            f"{high_pct}% of actions — high press",
            HIGH_COLOR, "bi-shield-fill-exclamation",
        ),
    ]

    return html.Div(
        [
            html.H6("Defensive Actions", className="buildup-subsection-title"),
            html.Div(kpi_cards, className="team-kpi-row"),
            dcc.Graph(
                figure=fig,
                config={"displayModeBar": False},
                style={"marginTop": "0.5rem"},
            ),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# C. PRESSING DIRECTION
# ═══════════════════════════════════════════════════════════════════════════════

def _section_pressing_direction(d: dict) -> html.Div:
    """Stacked horizontal bar (Left / Centre / Right) + L/C/R KPI cards."""
    counts = {
        "L": d.get("pressing_left_count",   0),
        "C": d.get("pressing_centre_count", 0),
        "R": d.get("pressing_right_count",  0),
    }
    pcts = {
        "L": d.get("pressing_left_pct",   0.0),
        "C": d.get("pressing_centre_pct", 0.0),
        "R": d.get("pressing_right_pct",  0.0),
    }

    fig = go.Figure()
    for key in ("L", "C", "R"):
        if counts[key] == 0:
            continue
        fig.add_trace(go.Bar(
            y=["Direction"],
            x=[pcts[key]],
            orientation="h",
            name=CORRIDOR_LABELS[key],
            marker_color=CORRIDOR_COLORS[key],
            text=[f"{CORRIDOR_LABELS[key]} {pcts[key]}%"],
            textposition="inside",
            textfont=dict(size=11, color="#fff"),
            hovertemplate=f"{CORRIDOR_LABELS[key]}: {counts[key]} ({pcts[key]}%)<extra></extra>",
        ))
    apply_chart_theme(fig, "dark")
    fig.update_layout(
        barmode="stack",
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=0, b=0), height=42,
        xaxis=dict(showgrid=False, showticklabels=False, range=[0, 100], fixedrange=True),
        yaxis=dict(showgrid=False, showticklabels=False, fixedrange=True),
        showlegend=False,
    )

    kpi_cards = []
    for key in ("L", "C", "R"):
        kpi_cards.append(
            _mini_kpi(
                CORRIDOR_LABELS[key], counts[key],
                f"{pcts[key]}% of defensive actions",
                CORRIDOR_COLORS[key], "bi-arrows-expand-vertical",
            )
        )

    return html.Div(
        [
            html.H6("Pressing Direction", className="buildup-subsection-title"),
            html.Div(kpi_cards, className="team-kpi-row"),
            dcc.Graph(
                figure=fig,
                config={"displayModeBar": False},
                style={"marginTop": "0.5rem"},
            ),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# D. PRESSING SUCCESS BY ZONE
# ═══════════════════════════════════════════════════════════════════════════════

def _section_pressing_success(d: dict) -> html.Div:
    """Grouped bars: successful vs unsuccessful presses per zone group."""
    by_zone = d.get("press_success_by_zone", {})

    zone_labels  = [ZONE_GROUP_LABELS[zg] for zg in ("high", "mid", "low")]
    success_vals = [by_zone.get(zg, {}).get("success", 0)                   for zg in ("high", "mid", "low")]
    fail_vals    = [
        by_zone.get(zg, {}).get("total", 0) - by_zone.get(zg, {}).get("success", 0)
        for zg in ("high", "mid", "low")
    ]
    rates        = [by_zone.get(zg, {}).get("rate", 0.0) for zg in ("high", "mid", "low")]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Successful",
        x=zone_labels,
        y=success_vals,
        marker_color=SUCCESS_COLOR,
        hovertemplate="%{x}: %{y} successful<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        name="Unsuccessful",
        x=zone_labels,
        y=fail_vals,
        marker_color=FAIL_COLOR,
        hovertemplate="%{x}: %{y} unsuccessful<extra></extra>",
    ))
    apply_chart_theme(fig, "dark")
    fig.update_layout(
        barmode="group",
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=30, r=10, t=10, b=30), height=200,
        xaxis=dict(
            showgrid=False, fixedrange=True,
            tickfont=dict(color="var(--text-secondary)", size=11),
        ),
        yaxis=dict(
            showgrid=True, gridcolor="rgba(255,255,255,0.06)",
            tickfont=dict(color="var(--text-secondary)", size=10),
            fixedrange=True,
        ),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
            font=dict(color="var(--text-secondary)", size=11),
        ),
        font=dict(color="var(--text-secondary)"),
    )

    # KPI cards: success rate per zone + overall
    kpi_cards = [
        _mini_kpi(
            "Overall", f"{d.get('press_success_rate', 0.0)}%",
            f"{d.get('press_success_successful', 0)} / {d.get('press_success_total', 0)} presses",
            SUCCESS_COLOR, "bi-check-circle-fill",
        )
    ]
    for zg, label, color in [
        ("high", "High Press", HIGH_COLOR),
        ("mid",  "Mid Press",  MID_COLOR),
        ("low",  "Low Block",  LOW_COLOR),
    ]:
        info = by_zone.get(zg, {})
        kpi_cards.append(
            _mini_kpi(
                label, f"{info.get('rate', 0.0)}%",
                f"{info.get('success', 0)} / {info.get('total', 0)}",
                color, "bi-bar-chart-fill",
            )
        )

    return html.Div(
        [
            html.H6("Pressing Success by Zone", className="buildup-subsection-title"),
            html.Div(kpi_cards, className="team-kpi-row"),
            dcc.Graph(
                figure=fig,
                config={"displayModeBar": False},
                style={"marginTop": "0.75rem"},
            ),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# E. COMBINED HEATMAP + OUTCOMES OVERLAY
# ═══════════════════════════════════════════════════════════════════════════════

def _build_combined_heatmap_outcomes(
    zone_counts: dict[int, int],
    detail: list[dict],
) -> go.Figure:
    """
    18-zone density heatmap as filled zone rectangles (background layer)
    with success / failure outcome dots plotted on top.

    Green filled circles  = possession regained within 10 s.
    Red   open  circles  = opponent retained the ball.
    """
    fig = go.Figure()

    _ROWS = 6
    _COLS = 3
    max_count = max(zone_counts.values(), default=1) or 1

    # ─ Zone density fill ──────────────────────────────────────────────────────────
    for zone_num in range(1, 19):
        row = (zone_num - 1) // _COLS
        col = (zone_num - 1) % _COLS
        x0 = _X_EDGES[row]
        x1 = _X_EDGES[row + 1]
        y0 = _Y_EDGES[col]
        y1 = _Y_EDGES[col + 1]
        count = zone_counts.get(zone_num, 0)
        intensity = count / max_count
        # Dark navy → crimson gradient — the dashboard's unified sequential
        # ramp (encoded as SEMANTIC_COLORS["heatmap_colorscale"]; same
        # interpolation as pitch_zones.py)
        r = int(27  + (138 - 27)  * intensity)
        g = int(40  + (31  - 40)  * intensity)
        b = int(56  + (51  - 56)  * intensity)
        a = 0.25 + 0.60 * intensity
        fill = f"rgba({r},{g},{b},{a:.2f})"
        fig.add_shape(
            type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
            line=dict(color="rgba(255,255,255,0.10)", width=1),
            fillcolor=fill, layer="below",
        )
        # Zone count label (faint, behind dots)
        if count > 0:
            cx = (x0 + x1) / 2
            cy = (y0 + y1) / 2
            fig.add_annotation(
                x=cx, y=cy,
                text=f"{count}",
                showarrow=False,
                font=dict(size=11, color=f"rgba(255,255,255,{0.25 + 0.55 * intensity:.2f})"),
            )

    # ─ Outcome scatter dots ───────────────────────────────────────────────────═
    success_pts: list[tuple] = []
    fail_pts:    list[tuple] = []
    for rec in detail:
        x = rec.get("x")
        y = rec.get("y")
        if x is None or y is None:
            continue
        player = rec.get("player", "?")
        minute = rec.get("minute", 0)
        act    = rec.get("action", "")
        label  = f"{minute}' {player} — {act}"
        if rec.get("success"):
            success_pts.append((x, y, label))
        else:
            fail_pts.append((x, y, label))

    for pts, name, color, symbol in [
        (success_pts, "Successful (≤10 s)", SUCCESS_COLOR, "circle"),
        (fail_pts,    "Unsuccessful",       FAIL_COLOR,    "circle-open"),
    ]:
        if not pts:
            continue
        fig.add_trace(go.Scatter(
            x=[p[0] for p in pts],
            y=[p[1] for p in pts],
            mode="markers",
            name=name,
            marker=dict(
                color=color, size=8, opacity=0.85,
                symbol=symbol,
                line=dict(color=color, width=1.5),
            ),
            hovertemplate=(
                f"<b>{name}</b><br>"
                "x=%{x:.1f} · y=%{y:.1f}<br>"
                "%{text}<extra></extra>"
            ),
            text=[p[2] for p in pts],
        ))

    apply_chart_theme(fig, "dark")
    draw_pitch(fig, theme="dark", title="Action Density + Press Outcomes",
               height=430, show_legend=True, draw_zones=True)
    return fig


# ═══════════════════════════════════════════════════════════════════════════════
# PITCH DRAWING HELPERS  (mirrors final_third_pitch.py conventions)
# ═══════════════════════════════════════════════════════════════════════════════

_X_EDGES = [0, 16.67, 33.33, 50.0, 66.67, 83.33, 100.0]
_Y_EDGES = [0, 33.33, 66.67, 100.0]

# Bound to the shared defensive-action taxonomy (SEMANTIC_COLORS action_*)
ACTION_COLORS = {
    "Tackle":        SEMANTIC_COLORS["action_tackle"],        # blue
    "Interception":  SEMANTIC_COLORS["action_interception"],  # green
    "Foul":          SEMANTIC_COLORS["action_foul"],          # orange
    "Ball Recovery": SEMANTIC_COLORS["action_recovery"],      # purple
    "Clearance":     SEMANTIC_COLORS["action_clearance"],     # amber
    "Aerial":        SEMANTIC_COLORS["action_aerial"],        # cyan
    "Challenge":     SEMANTIC_COLORS["action_challenge"],     # pink
    "Blocked Pass":  SEMANTIC_COLORS["action_blocked_pass"],  # lime
}


# NOTE (Phase 2a): the former private _draw_full_pitch() / _pitch_layout()
# helpers were replaced by the shared, theme-aware
# src.styling.pitch_utils.draw_pitch() (draw_zones=True reproduces the zone
# grid + corridor labels these helpers drew).


# ═══════════════════════════════════════════════════════════════════════════════
# F. ALL ACTIONS PITCH MAP — by action type + median pressing line
# ═══════════════════════════════════════════════════════════════════════════════

def _build_actions_scatter(
    detail: list[dict],
    median_x: float | None,
    offside_line_x: float | None = None,
) -> go.Figure:
    """
    Full-pitch scatter of all defensive actions coloured by action type.
    Overlays the median pressing line (white dotted) and, when available,
    the offside line (purple dotted) as vertical annotations.
    """
    fig = go.Figure()

    grouped: dict[str, list[tuple]] = {k: [] for k in ACTION_COLORS}
    for rec in detail:
        act = rec.get("action", "Unknown")
        x   = rec.get("x")
        y   = rec.get("y")
        if x is None or y is None:
            continue
        player  = rec.get("player", "?")
        minute  = rec.get("minute", 0)
        zg      = rec.get("zone_group", "")
        grouped.setdefault(act, []).append((x, y, f"{minute}' {player} [{zg}]"))

    for act, color in ACTION_COLORS.items():
        pts = grouped.get(act, [])
        if not pts:
            continue
        fig.add_trace(go.Scatter(
            x=[p[0] for p in pts],
            y=[p[1] for p in pts],
            mode="markers",
            name=act,
            marker=dict(
                color=color, size=8, opacity=0.80,
                line=dict(color="rgba(255,255,255,0.35)", width=0.5),
            ),
            hovertemplate=(
                f"<b>{act}</b><br>"
                "x=%{x:.1f} · y=%{y:.1f}<br>"
                "%{text}<extra></extra>"
            ),
            text=[p[2] for p in pts],
        ))

    if median_x is not None:
        fig.add_shape(
            type="line",
            x0=median_x, x1=median_x, y0=0, y1=100,
            line=dict(color="rgba(255,255,255,0.70)", width=2, dash="dot"),
        )
        fig.add_annotation(
            x=median_x, y=103,
            text=f"<b>Pressing line x={median_x}</b>",
            showarrow=False,
            font=dict(size=10, color="rgba(255,255,255,0.80)"),
            xanchor="center",
        )

    if offside_line_x is not None:
        fig.add_shape(
            type="line",
            x0=offside_line_x, x1=offside_line_x, y0=0, y1=100,
            line=dict(color="rgba(139,92,246,0.85)", width=2, dash="dot"),
        )
        fig.add_annotation(
            x=offside_line_x, y=-8,
            text=f"<b>Offside line x={offside_line_x}</b>",
            showarrow=False,
            font=dict(size=10, color="rgba(139,92,246,0.90)"),
            xanchor="center",
        )

    apply_chart_theme(fig, "dark")
    draw_pitch(fig, theme="dark", title="Defensive Actions by Type",
               height=430, show_legend=True, draw_zones=True)
    return fig


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN CARD — defensive_pressing_card()
# ═══════════════════════════════════════════════════════════════════════════════

def defensive_pressing_card(data: dict) -> html.Div:
    """
    Full D1 card rendered inside the Defensive Phase section.

    Parameters
    ----------
    data : dict
        Output of ``analyse_defensive_pressing()``.
    """
    return html.Div(
        [
            # Card header (house style)
            ds_header(
                "Defensive Phase — Pressing", "bi-speedometer2",
                "Pressure",
                "PPDA, pressing height and direction, press success and "
                "defensive action maps",
            ),

            # A — Overview
            html.Div(
                _section_overview(data),
                style={"marginBottom": "1.5rem"},
            ),

            html.Hr(style={"borderColor": "var(--border-light)", "margin": "1.5rem 0"}),

            # B — Defensive Actions by Third
            html.Div(
                _section_defensive_actions(data),
                style={"marginBottom": "1.5rem"},
            ),

            html.Hr(style={"borderColor": "var(--border-light)", "margin": "1.5rem 0"}),

            # C — Pressing Direction
            html.Div(
                _section_pressing_direction(data),
                style={"marginBottom": "1.5rem"},
            ),

            html.Hr(style={"borderColor": "var(--border-light)", "margin": "1.5rem 0"}),

            # D — Pressing Success by Zone
            html.Div(
                _section_pressing_success(data),
                style={"marginBottom": "1.5rem"},
            ),

            html.Hr(style={"borderColor": "var(--border-light)", "margin": "1.5rem 0"}),

            # E+F — Side-by-side pitch maps
            html.Div(
                [
                    html.H6("Pitch Maps", className="buildup-subsection-title"),
                    html.Div(
                        [
                            # Left: all actions by type + median pressing line
                            html.Div(
                                [
                                    html.P(
                                        "Actions by type · white dotted = pressing line · purple dotted = offside line",
                                        className="kpi-subtitle",
                                        style={"marginBottom": "0.4rem", "textAlign": "center"},
                                    ),
                                    html.Div(
                                        dcc.Graph(
                                            figure=_build_actions_scatter(
                                                data.get("press_actions_detail", []),
                                                data.get("pressing_line_median"),
                                                data.get("offside_line_median"),
                                            ),
                                            config={"displayModeBar": False},
                                        ),
                                        className="pitch-dark-container",
                                    ),
                                ],
                                style={"flex": "1", "minWidth": "0"},
                            ),
                            # Right: zone density heatmap + outcome dots overlay
                            html.Div(
                                [
                                    html.P(
                                        "Action density (zones) · filled = successful press · open = unsuccessful",
                                        className="kpi-subtitle",
                                        style={"marginBottom": "0.4rem", "textAlign": "center"},
                                    ),
                                    html.Div(
                                        dcc.Graph(
                                            figure=_build_combined_heatmap_outcomes(
                                                data.get("zone_heatmap", {}),
                                                data.get("press_actions_detail", []),
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
        className="buildup-card ma-card",
        style={"padding": "1.5rem"},
    )
