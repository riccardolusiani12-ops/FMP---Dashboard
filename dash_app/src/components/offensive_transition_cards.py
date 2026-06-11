"""
Offensive Transitions — UI Components
======================================
Dash layout components for the Offensive Transition card inside the
Transitions module.

Mirrors ``defensive_structure_cards.py`` with the following differences:
  · Outcomes are P1 / P2 / P3  (not N1 / N2 / N3)
  · Shading on the pitch map is GREEN and covers x = 0 → 66.67
    (own + middle third, i.e. the area where ball-wins are plotted)
  · Pitch orientation label is inverted: ATK arrow points RIGHT (same
    as all other pitch maps in the system), but the detection threshold
    line sits at x = 50 (own half / midfield) instead of x = 33.33.
  · "Immediate Press" and "Organised Drop" KPIs are removed — those are
    defensive concepts.  The overview shows 3 KPIs instead of 5.
  · Zone labels in bar charts reflect the TEAM's own half:
      "Mid" (x 33.33–50), "Def. Third" (x 16.67–33.33), "Own Box" (x 0–16.67)
"""

from __future__ import annotations

from dash import html, dcc
import plotly.graph_objects as go

from src.styling.theme import COLORS_DARK, SEMANTIC_COLORS
from src.styling.plotly_template import apply_chart_theme
from src.styling.pitch_utils import draw_pitch
from src.styling.ui_components import ds_header

# ══════════════════════════════════════════════════════════════════════════════
# PALETTE — bound to the shared design system (values unchanged, see theme.py)
# ══════════════════════════════════════════════════════════════════════════════

PRIMARY          = COLORS_DARK["accent"]                 # "#8a1f33"
SUCCESS_COLOR    = SEMANTIC_COLORS["outcome_positive"]   # "#22c55e"
TRANSITION_COLOR = SEMANTIC_COLORS["outcome_positive"]   # green for offensive transitions

CORRIDOR_COLORS = {
    "L": SEMANTIC_COLORS["corridor_left"],
    "C": SEMANTIC_COLORS["corridor_centre"],
    "R": SEMANTIC_COLORS["corridor_right"],
}
CORRIDOR_LABELS = {"L": "Left", "C": "Centre", "R": "Right"}

ZONE_GROUP_LABELS = {
    "mid":     "Mid",
    "mid_low": "Def. Third",
    "low":     "Own Box",
}

# P1 (mildest) → P3 (most dangerous / best quality)
OUTCOME_COLORS = {
    "P1": SEMANTIC_COLORS["transition_p1"],   # light green
    "P2": SEMANTIC_COLORS["transition_p2"],   # green
    "P3": SEMANTIC_COLORS["transition_p3"],   # dark green
}

OUTCOME_LABELS = {
    "P1": "P1 — Sustained (15s+ or entered final third)",
    "P2": "P2 — Threatening (corner / free kick / cross in final third)",
    "P3": "P3 — Dangerous (shot / goal / penalty)",
}

_X_EDGES = [0, 16.67, 33.33, 50.0, 66.67, 83.33, 100.0]
_Y_EDGES = [0, 33.33, 66.67, 100.0]


# ══════════════════════════════════════════════════════════════════════════════
# SHARED HELPERS
# ══════════════════════════════════════════════════════════════════════════════

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


# NOTE (Phase 2a): the former private _draw_full_pitch() / _pitch_layout()
# helpers were replaced by the shared, theme-aware
# src.styling.pitch_utils.draw_pitch() (draw_zones=True reproduces the zone
# grid + corridor labels these helpers drew).


def _subsection_title(text: str) -> html.H6:
    return html.H6(
        text,
        className="buildup-subsection-title",
        style={
            "marginBottom": "0.5rem",
            "color": "var(--text-secondary)",
            "fontSize": "0.80rem",
            "textTransform": "uppercase",
            "letterSpacing": "0.05em",
        },
    )


def _hr() -> html.Hr:
    return html.Hr(style={"borderColor": "var(--border-light)", "margin": "1.5rem 0"})


def _safe_float(val: float | None, fmt: str = ".1f") -> str:
    if val is None:
        return "N/A"
    return format(val, fmt)


# ══════════════════════════════════════════════════════════════════════════════
# TRANSITION OVERVIEW KPIs (3 cards — no press/drop metrics)
# ══════════════════════════════════════════════════════════════════════════════

def _section_transition_kpis(data: dict) -> html.Div:
    return html.Div(
        [
            _mini_kpi(
                "Total Transitions",
                data.get("total_transitions", 0),
                "ball recoveries by the team — any zone, any outcome",
                TRANSITION_COLOR,
                "bi-arrow-repeat",
            ),
            _mini_kpi(
                "Qualified Transitions",
                data.get("qualified_transitions", 0),
                "transitions reaching P1, P2 or P3 outcome",
                TRANSITION_COLOR,
                "bi-funnel-fill",
            ),
            _mini_kpi(
                "Transition Rate",
                f"{data.get('transition_rate', 0.0):.1f}%",
                "qualified transitions per total team possessions",
                TRANSITION_COLOR,
                "bi-percent",
            ),
        ],
        className="team-kpi-row",
    )


# ══════════════════════════════════════════════════════════════════════════════
# OUTCOME KPI CARDS  (P1 / P2 / P3)
# ══════════════════════════════════════════════════════════════════════════════

def _section_outcome_kpis(data: dict) -> html.Div:
    od = data.get("outcome_distribution", {})
    return html.Div(
        [
            _mini_kpi(
                "P1 \u2014 Sustained",
                od.get("P1", 0),
                "team held 15s+ OR reached the attacking third",
                OUTCOME_COLORS["P1"],
                "bi-hourglass-split",
            ),
            _mini_kpi(
                "P2 \u2014 Threatening",
                od.get("P2", 0),
                "corner / free kick / cross into the box",
                OUTCOME_COLORS["P2"],
                "bi-flag-fill",
            ),
            _mini_kpi(
                "P3 \u2014 Dangerous",
                od.get("P3", 0),
                "shot on/off target \xb7 goal \xb7 penalty",
                OUTCOME_COLORS["P3"],
                "bi-bullseye",
            ),
        ],
        className="team-kpi-row",
    )


# ══════════════════════════════════════════════════════════════════════════════
# STACKED OUTCOME BAR  (P3 | P2 | P1)
# ══════════════════════════════════════════════════════════════════════════════

def _section_outcome_bar(data: dict) -> dcc.Graph:
    qualified    = data.get("qualified_transitions", 0) or 1
    outcome_dist = data.get("outcome_distribution", {})

    fig = go.Figure()
    for level, color in [("P3", OUTCOME_COLORS["P3"]), ("P2", OUTCOME_COLORS["P2"]), ("P1", OUTCOME_COLORS["P1"])]:
        count = outcome_dist.get(level, 0)
        pct   = round(count / qualified * 100, 1)
        if count == 0:
            continue
        fig.add_trace(go.Bar(
            y=["Outcomes"],
            x=[pct],
            orientation="h",
            name=OUTCOME_LABELS[level],
            marker_color=color,
            text=[f"{level} {pct}%"],
            textposition="inside",
            textfont=dict(size=11, color="#fff"),
            hovertemplate=f"{OUTCOME_LABELS[level]}: {count} ({pct}%)<extra></extra>",
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
    return dcc.Graph(figure=fig, config={"displayModeBar": False})


# ══════════════════════════════════════════════════════════════════════════════
# OUTCOMES BY ZONE
# ══════════════════════════════════════════════════════════════════════════════

def _section_outcomes_by_zone(data: dict) -> dcc.Graph:
    by_zone     = data.get("outcomes_by_zone", {})
    zone_keys   = ["mid", "mid_low", "low"]
    zone_labels = [ZONE_GROUP_LABELS[k] for k in zone_keys]

    fig = go.Figure()
    for level, color in [("P1", OUTCOME_COLORS["P1"]), ("P2", OUTCOME_COLORS["P2"]), ("P3", OUTCOME_COLORS["P3"])]:
        fig.add_trace(go.Bar(
            name=OUTCOME_LABELS[level],
            x=zone_labels,
            y=[by_zone.get(zk, {}).get(level, 0) for zk in zone_keys],
            marker_color=color,
            hovertemplate=f"{level} \u2014 %{{x}}: %{{y}}<extra></extra>",
        ))
    apply_chart_theme(fig, "dark")
    fig.update_layout(
        barmode="group",
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=30, r=10, t=10, b=30), height=200,
        xaxis=dict(showgrid=False, fixedrange=True,
                   tickfont=dict(color="var(--text-secondary)", size=11)),
        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.06)",
                   tickfont=dict(color="var(--text-secondary)", size=10),
                   fixedrange=True),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                    font=dict(color="var(--text-secondary)", size=11)),
        font=dict(color="var(--text-secondary)"),
    )
    return dcc.Graph(figure=fig, config={"displayModeBar": False})


# ══════════════════════════════════════════════════════════════════════════════
# OUTCOMES BY CORRIDOR
# ══════════════════════════════════════════════════════════════════════════════

def _section_outcomes_by_corridor(data: dict) -> dcc.Graph:
    by_corr     = data.get("outcomes_by_corridor", {})
    corr_labels = ["Left", "Centre", "Right"]
    corr_keys   = ["L", "C", "R"]

    fig = go.Figure()
    for level, color in [("P1", OUTCOME_COLORS["P1"]), ("P2", OUTCOME_COLORS["P2"]), ("P3", OUTCOME_COLORS["P3"])]:
        fig.add_trace(go.Bar(
            name=OUTCOME_LABELS[level],
            x=corr_labels,
            y=[by_corr.get(ck, {}).get(level, 0) for ck in corr_keys],
            marker_color=color,
            hovertemplate=f"{level} \u2014 %{{x}}: %{{y}}<extra></extra>",
        ))
    apply_chart_theme(fig, "dark")
    fig.update_layout(
        barmode="group",
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=30, r=10, t=10, b=30), height=200,
        xaxis=dict(showgrid=False, fixedrange=True,
                   tickfont=dict(color="var(--text-secondary)", size=11)),
        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.06)",
                   tickfont=dict(color="var(--text-secondary)", size=10),
                   fixedrange=True),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                    font=dict(color="var(--text-secondary)", size=11)),
        font=dict(color="var(--text-secondary)"),
    )
    return dcc.Graph(figure=fig, config={"displayModeBar": False})


# ══════════════════════════════════════════════════════════════════════════════
# TRANSITION ORIGINS PITCH MAP  (inverted: GREEN shading own + mid half)
# ══════════════════════════════════════════════════════════════════════════════

def _build_offensive_transition_pitch(origins: list[dict]) -> go.Figure:
    """
    Full-pitch scatter of offensive transition origins.

    Visual conventions
    ------------------
    • GREEN shaded zone: x = 0 → 50 (own half — where ball wins originate).
    • Detection threshold dashed line at x = 50 (halfway line).
    • Dots coloured by outcome: P1 light-green, P2 green, P3 dark-green.
    • Attack direction is left → right (standard orientation), same as all
      other pitch maps in the dashboard.
    """
    fig = go.Figure()

    # Green shaded own half: x = 0 → 50
    fig.add_shape(
        type="rect", x0=0, x1=50, y0=0, y1=100,
        fillcolor="rgba(34,197,94,0.08)",   # green tint
        line=dict(color="rgba(0,0,0,0)", width=0),
        layer="below",
    )

    # Detection threshold = halfway line (drawn by draw_pitch below)
    fig.add_annotation(
        x=50, y=103,
        text="Ball win threshold x=50",
        showarrow=False,
        font=dict(size=9, color="rgba(255,255,255,0.45)"),
        xanchor="center",
    )

    # Scatter dots per outcome level
    for level in ("P1", "P2", "P3"):
        pts = [r for r in origins if r.get("outcome") == level]
        if not pts:
            continue
        fig.add_trace(go.Scatter(
            x=[p["x"] for p in pts],
            y=[p["y"] for p in pts],
            mode="markers",
            name=OUTCOME_LABELS[level],
            marker=dict(
                color=OUTCOME_COLORS[level], size=9, opacity=0.85,
                line=dict(color="rgba(255,255,255,0.35)", width=0.5),
            ),
            hovertemplate="%{text}<br>x=%{x:.1f} \xb7 y=%{y:.1f}<extra></extra>",
            text=[
                f"{OUTCOME_LABELS.get(p['outcome'], p['outcome'])} | "
                f"{ZONE_GROUP_LABELS.get(p.get('zone_group', ''), p.get('zone_group', ''))} "
                f"{p.get('corridor', '')} | "
                f"time to outcome: {p.get('reaction_time', 0.0):.1f}s"
                for p in pts
            ],
        ))

    # Shared theming first (fonts, hover), then the canonical pitch markings
    # + layout from the design system (markings sit on layer="below").
    apply_chart_theme(fig, "dark")
    draw_pitch(
        fig,
        theme="dark",
        title="Offensive Transition Origins (Qualified \xb7 Own Half)",
        height=430,
        show_legend=True,
        draw_zones=True,
    )
    return fig


# ══════════════════════════════════════════════════════════════════════════════
# MAIN CARD
# ══════════════════════════════════════════════════════════════════════════════

def offensive_transition_card(data: dict) -> html.Div:
    """
    Full Offensive Transition card rendered inside the Transitions module.

    Parameters
    ----------
    data : dict
        Output of ``analyse_offensive_transitions()``.
    """
    origins = data.get("transition_origins", [])

    return html.Div(
        [
            # ── Card header (house style) ──────────────────────────────────────
            ds_header(
                "Transitions — Offensive", "bi-lightning-charge-fill",
                "Offensive Transition",
                "What happens after the team wins the ball — outcomes, zones "
                "and recovery origins",
            ),

            # ── Overview KPIs ─────────────────────────────────────────────────
            _subsection_title("Overview"),
            _section_transition_kpis(data),

            _hr(),

            # ── Outcome distribution ──────────────────────────────────────────
            _section_outcome_kpis(data),
            html.Div(
                _section_outcome_bar(data),
                style={"marginTop": "0.5rem"},
            ),

            _hr(),

            # ── Outcomes by Zone ──────────────────────────────────────────────
            _subsection_title("Outcomes by Zone"),
            _section_outcomes_by_zone(data),

            _hr(),

            # ── Outcomes by Corridor ──────────────────────────────────────────
            _subsection_title("Outcomes by Corridor"),
            _section_outcomes_by_corridor(data),

            _hr(),

            # ── Pitch Map ─────────────────────────────────────────────────────
            _subsection_title("Transition Origins"),
            html.Div(
                [
                    html.P(
                        "Qualifying transitions only \xb7 Ball won in own half (x \u2264 50) \xb7 coloured by outcome",
                        className="kpi-subtitle",
                        style={"marginBottom": "0.4rem", "textAlign": "center"},
                    ),
                    html.Div(
                        dcc.Graph(
                            figure=_build_offensive_transition_pitch(origins),
                            config={"displayModeBar": False},
                        ),
                        className="pitch-dark-container",
                    ),
                ],
                style={"marginBottom": "1.5rem"},
            ),
        ],
        className="buildup-card ma-card",
        style={"padding": "1.5rem"},
    )
