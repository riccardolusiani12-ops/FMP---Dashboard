"""
Defensive Phase D2 — Defensive Structure & Transitions: UI Components
======================================================================
Dash layout components for the D2 card inside the Defensive Phase.

Sections rendered:
  Defensive Transitions
    · Transition Overview KPIs (5 cards)
    · Outcome KPIs  (N1 / N2 / N3)
    · Stacked Outcome Bar  (N3 | N2 | N1)
    · Outcomes by Zone  (High / Mid / Low)
    · Outcomes by Corridor  (L / C / R)
    · Transition Loss Origins Pitch Map
  D2.2a — Defensive Line Height (Offside Line)
  D2.2b — Offside Trap Panel
  D2.2c — Structural Mirror ("How the Opponent Attacked Us")

Follows the exact same visual patterns as defensive_pressing_cards.py.
"""

from __future__ import annotations

from dash import html, dcc
import plotly.graph_objects as go

# ═══════════════════════════════════════════════════════════════════════════════
# PALETTE
# ═══════════════════════════════════════════════════════════════════════════════

PRIMARY           = "#8a1f33"
HIGH_COLOR        = "#ef4444"
MID_COLOR         = "#f97316"
LOW_COLOR         = "#6b7280"
SUCCESS_COLOR     = "#22c55e"
FAIL_COLOR        = "#ef4444"

TRANSITION_COLOR  = "#f97316"
OFFSIDE_COLOR     = "#8b5cf6"
MIRROR_COLOR      = "#ef4444"

CORRIDOR_COLORS = {"L": "#3b82f6", "C": "#8b5cf6", "R": "#06b6d4"}
CORRIDOR_LABELS = {"L": "Left", "C": "Centre", "R": "Right"}

ZONE_GROUP_COLORS = {"high": HIGH_COLOR, "mid": MID_COLOR, "low": LOW_COLOR}
ZONE_GROUP_LABELS = {"high": "High", "mid": "Mid", "low": "Low"}

OUTCOME_COLORS = {
    "N1": "#f97316",   # orange
    "N2": "#ef4444",   # red
    "N3": "#7f1d1d",   # dark red
}

OUTCOME_LABELS = {
    "N1": "N1 — Sustained (15s+ or entered final third)",
    "N2": "N2 — Threatening (corner / free kick / cross in final third)",
    "N3": "N3 — Dangerous (shot / goal / penalty)",
}

_X_EDGES = [0, 16.67, 33.33, 50.0, 66.67, 83.33, 100.0]
_Y_EDGES = [0, 33.33, 66.67, 100.0]


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
    fig.add_shape(
        type="line", x0=50, x1=50, y0=0, y1=100,
        line=dict(color="rgba(255,255,255,0.22)", width=1, dash="dash"),
        layer="below",
    )
    # Own penalty box
    fig.add_shape(
        type="rect", x0=0, x1=16.5, y0=21, y1=79,
        line=dict(color="rgba(255,255,255,0.18)", width=1),
        fillcolor="rgba(0,0,0,0)",
    )
    # Attacking penalty box
    fig.add_shape(
        type="rect", x0=83.5, x1=100, y0=21, y1=79,
        line=dict(color="rgba(255,255,255,0.18)", width=1),
        fillcolor="rgba(0,0,0,0)",
    )
    fig.add_annotation(
        x=94, y=-6, text="ATK \u2192", showarrow=False,
        font=dict(size=9, color="rgba(255,255,255,0.30)"),
    )
    fig.add_annotation(
        x=6, y=-6, text="\u2190 OWN GOAL", showarrow=False,
        font=dict(size=9, color="rgba(255,255,255,0.30)"),
    )
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
    x_range: list | None = None,
) -> None:
    """Apply shared dark-theme layout."""
    x_range = x_range or [-2, 102]
    fig.update_layout(
        title=dict(text=title, font=dict(size=13, color="#f0f0f0"), x=0.5),
        xaxis=dict(range=x_range, showgrid=False, zeroline=False,
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


def _safe_pct(val: float | None, decimals: int = 1) -> str:
    if val is None:
        return "N/A"
    return f"{val:.{decimals}f}%"


def _safe_float(val: float | None, fmt: str = ".1f") -> str:
    if val is None:
        return "N/A"
    return format(val, fmt)


# ═══════════════════════════════════════════════════════════════════════════════
# TRANSITION OVERVIEW KPIs (5 cards)
# ═══════════════════════════════════════════════════════════════════════════════

def _section_transition_kpis(data: dict) -> html.Div:
    return html.Div(
        [
            _mini_kpi(
                "Total Transitions",
                data.get("total_transitions", 0),
                "all opponent ball recoveries — any zone, any outcome",
                TRANSITION_COLOR,
                "bi-arrow-repeat",
            ),
            _mini_kpi(
                "Qualified Transitions",
                data.get("qualified_transitions", 0),
                "transitions reaching N1, N2 or N3 outcome",
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
            _mini_kpi(
                "Immediate Press \u22645s",
                f"{data.get('immediate_press_rate', 0.0):.1f}%",
                "counter-press within 5 seconds",
                SUCCESS_COLOR,
                "bi-lightning-fill",
            ),
            _mini_kpi(
                "Organised Drop >10s",
                f"{data.get('drop_back_rate', 0.0):.1f}%",
                "no defensive action for 10s+",
                "#6b7280",
                "bi-arrow-down",
            ),
        ],
        className="team-kpi-row",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# OUTCOME KPI CARDS  (N1 / N2 / N3)
# ═══════════════════════════════════════════════════════════════════════════════

def _section_outcome_kpis(data: dict) -> html.Div:
    od = data.get("outcome_distribution", {})
    return html.Div(
        [
            _mini_kpi(
                "N1 \u2014 Sustained",
                od.get("N1", 0),
                "opp. held 15s+ without danger OR entered final third",
                "#f97316",
                "bi-hourglass-split",
            ),
            _mini_kpi(
                "N2 \u2014 Threatening",
                od.get("N2", 0),
                "corner / free kick / cross in final third",
                "#ef4444",
                "bi-flag-fill",
            ),
            _mini_kpi(
                "N3 \u2014 Dangerous",
                od.get("N3", 0),
                "shot on/off target \xb7 goal \xb7 penalty",
                "#7f1d1d",
                "bi-bullseye",
            ),
        ],
        className="team-kpi-row",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# STACKED OUTCOME BAR  (N3 | N2 | N1)
# ═══════════════════════════════════════════════════════════════════════════════

def _section_outcome_bar(data: dict) -> dcc.Graph:
    qualified    = data.get("qualified_transitions", 0) or 1  # avoid div/0
    outcome_dist = data.get("outcome_distribution", {})

    fig = go.Figure()
    for level, color in [("N3", "#7f1d1d"), ("N2", "#ef4444"), ("N1", "#f97316")]:
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
    fig.update_layout(
        barmode="stack",
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=0, b=0), height=42,
        xaxis=dict(showgrid=False, showticklabels=False, range=[0, 100], fixedrange=True),
        yaxis=dict(showgrid=False, showticklabels=False, fixedrange=True),
        showlegend=False,
    )
    return dcc.Graph(figure=fig, config={"displayModeBar": False})


# ═══════════════════════════════════════════════════════════════════════════════
# OUTCOMES BY ZONE  (High / Mid / Low)
# ═══════════════════════════════════════════════════════════════════════════════

def _section_outcomes_by_zone(data: dict) -> dcc.Graph:
    by_zone     = data.get("outcomes_by_zone", {})
    zone_labels = ["High", "Mid", "Low"]
    zone_keys   = ["high", "mid", "low"]

    fig = go.Figure()
    for level, color in [("N1", "#f97316"), ("N2", "#ef4444"), ("N3", "#7f1d1d")]:
        fig.add_trace(go.Bar(
            name=OUTCOME_LABELS[level],
            x=zone_labels,
            y=[by_zone.get(zk, {}).get(level, 0) for zk in zone_keys],
            marker_color=color,
            hovertemplate=f"{level} \u2014 %{{x}}: %{{y}}<extra></extra>",
        ))
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


# ═══════════════════════════════════════════════════════════════════════════════
# OUTCOMES BY CORRIDOR  (L / C / R)
# ═══════════════════════════════════════════════════════════════════════════════

def _section_outcomes_by_corridor(data: dict) -> dcc.Graph:
    by_corr     = data.get("outcomes_by_corridor", {})
    corr_labels = ["Left", "Centre", "Right"]
    corr_keys   = ["L", "C", "R"]

    fig = go.Figure()
    for level, color in [("N1", "#f97316"), ("N2", "#ef4444"), ("N3", "#7f1d1d")]:
        fig.add_trace(go.Bar(
            name=OUTCOME_LABELS[level],
            x=corr_labels,
            y=[by_corr.get(ck, {}).get(level, 0) for ck in corr_keys],
            marker_color=color,
            hovertemplate=f"{level} \u2014 %{{x}}: %{{y}}<extra></extra>",
        ))
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


# ═══════════════════════════════════════════════════════════════════════════════
# TRANSITION LOSS ORIGINS PITCH MAP
# ═══════════════════════════════════════════════════════════════════════════════

def _build_transition_pitch(origins: list[dict], offside_line_x: float | None = None) -> go.Figure:
    fig = go.Figure()
    _draw_full_pitch(fig)

    # Shaded orange: own attacking half + attacking third (x = 50 → 100)
    fig.add_shape(
        type="rect", x0=50.0, x1=100, y0=0, y1=100,
        fillcolor="rgba(249,115,22,0.08)",
        line=dict(color="rgba(0,0,0,0)", width=0),
        layer="below",
    )

    # Detection threshold line at x = 50 (attacking half boundary)
    fig.add_shape(
        type="line", x0=50.0, x1=50.0, y0=0, y1=100,
        line=dict(color="rgba(255,255,255,0.45)", width=1.5, dash="dash"),
    )
    fig.add_annotation(
        x=50.0, y=103,
        text="Ball loss threshold x=50",
        showarrow=False,
        font=dict(size=9, color="rgba(255,255,255,0.45)"),
        xanchor="center",
    )

    # Purple dotted offside line
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

    for level in ("N1", "N2", "N3"):
        pts = [r for r in origins if r.get("outcome") == level]
        if not pts:
            continue
        fig.add_trace(go.Scatter(
            x=[p["x"] for p in pts],
            y=[p["y"] for p in pts],
            mode="markers",
            name=OUTCOME_LABELS[level],
            marker=dict(color=OUTCOME_COLORS[level], size=9, opacity=0.85,
                        line=dict(color="rgba(255,255,255,0.35)", width=0.5)),
            hovertemplate="%{text}<br>x=%{x:.1f} \xb7 y=%{y:.1f}<extra></extra>",
            text=[
                f"{OUTCOME_LABELS.get(p['outcome'], p['outcome'])} | "
                f"{p.get('zone_group', '')} {p.get('corridor', '')} | "
                f"reaction: {p.get('reaction_time', 0.0):.1f}s"
                for p in pts
            ],
        ))

    _pitch_layout(
        fig,
        "Transition Loss Origins (Qualified \xb7 Middle + Attacking Third)",
        height=430,
        show_legend=True,
    )
    return fig


# ═══════════════════════════════════════════════════════════════════════════════
# D2.2b — OFFSIDE TRAP PANEL
# ═══════════════════════════════════════════════════════════════════════════════

def _section_offside_trap(d: dict) -> html.Div:
    clustering      = d.get("offside_clustering_index", 0.0)
    corr_dist       = d.get("offside_corridor_distribution", {"L": 0, "C": 0, "R": 0})
    height_dist     = d.get("offside_height_zone_distribution", {"high": 0, "mid": 0, "low": 0})

    dominant_flank = "N/A"
    if corr_dist:
        dominant_key = max(corr_dist, key=lambda k: corr_dist[k])
        dominant_flank = CORRIDOR_LABELS.get(dominant_key, dominant_key)

    high_offsides = height_dist.get("high", 0)

    kpi_row = html.Div(
        [
            _mini_kpi(
                "Clustering Index", f"{clustering}%",
                "% offsides within \xb15 of median line",
                OFFSIDE_COLOR, "bi-bullseye",
            ),
            _mini_kpi(
                "Dominant Flank", dominant_flank,
                "corridor with most offsides provoked",
                CORRIDOR_COLORS.get(
                    max(corr_dist, key=lambda k: corr_dist[k]) if corr_dist else "C",
                    OFFSIDE_COLOR
                ),
                "bi-arrows-expand-vertical",
            ),
            _mini_kpi(
                "High-Zone Offsides", high_offsides,
                "provoked in attacking third",
                HIGH_COLOR, "bi-arrow-up",
            ),
        ],
        className="team-kpi-row",
    )

    fig = go.Figure()
    for key in ("L", "C", "R"):
        count = corr_dist.get(key, 0)
        if count == 0:
            continue
        fig.add_trace(go.Bar(
            name=CORRIDOR_LABELS[key],
            x=[CORRIDOR_LABELS[key]],
            y=[count],
            marker_color=CORRIDOR_COLORS[key],
            text=[str(count)],
            textposition="outside",
            textfont=dict(size=10, color="#d0d0d0"),
            hovertemplate=f"{CORRIDOR_LABELS[key]}: {count}<extra></extra>",
        ))

    fig.update_layout(
        barmode="group",
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=20, r=10, t=10, b=30), height=120,
        xaxis=dict(showgrid=False, fixedrange=True,
                   tickfont=dict(color="var(--text-secondary)", size=10)),
        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.06)",
                   tickfont=dict(color="var(--text-secondary)", size=10),
                   fixedrange=True),
        showlegend=False,
        font=dict(color="var(--text-secondary)"),
    )

    return html.Div(
        [
            kpi_row,
            dcc.Graph(
                figure=fig,
                config={"displayModeBar": False},
                style={"marginTop": "0.5rem"},
            ),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# D2.2c — STRUCTURAL MIRROR
# ═══════════════════════════════════════════════════════════════════════════════

def _section_structural_mirror(d: dict) -> html.Div:
    ft_total        = d.get("opp_ft_entries_total", 0)
    dominant_method = d.get("opp_dominant_method") or "N/A"
    z14_pct         = d.get("opp_z14_pct", 0.0)
    positive_pct    = d.get("opp_positive_pct", 0.0)
    avg_passes      = d.get("opp_avg_passes_before_ft", 0.0)

    left_pct   = d.get("opp_ft_entry_left_pct",   0.0)
    centre_pct = d.get("opp_ft_entry_centre_pct", 0.0)
    right_pct  = d.get("opp_ft_entry_right_pct",  0.0)
    left_n     = d.get("opp_ft_entry_left_count",   0)
    centre_n   = d.get("opp_ft_entry_centre_count", 0)
    right_n    = d.get("opp_ft_entry_right_count",  0)

    dominant_label = dominant_method.replace("_", " ").title() if dominant_method != "N/A" else "N/A"

    corridor_fig = go.Figure()
    for key, pct, n, color in [
        ("L", left_pct, left_n, CORRIDOR_COLORS["L"]),
        ("C", centre_pct, centre_n, CORRIDOR_COLORS["C"]),
        ("R", right_pct, right_n, CORRIDOR_COLORS["R"]),
    ]:
        if n == 0:
            continue
        corridor_fig.add_trace(go.Bar(
            y=["Corridor"],
            x=[pct],
            orientation="h",
            name=CORRIDOR_LABELS[key],
            marker_color=color,
            text=[f"{CORRIDOR_LABELS[key]} {pct}%"],
            textposition="inside",
            textfont=dict(size=11, color="#fff"),
            hovertemplate=f"{CORRIDOR_LABELS[key]}: {n} ({pct}%)<extra></extra>",
        ))
    corridor_fig.update_layout(
        barmode="stack",
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=0, b=0), height=42,
        xaxis=dict(showgrid=False, showticklabels=False, range=[0, 100], fixedrange=True),
        yaxis=dict(showgrid=False, showticklabels=False, fixedrange=True),
        showlegend=False,
    )

    method_pcts   = d.get("opp_method_pcts", {})
    method_counts = d.get("opp_method_counts", {})
    METHOD_PALETTE = {
        "short_pass":            "#3b82f6",
        "long_ball":             "#ef4444",
        "individual_carry":      "#f97316",
        "through_ball":          "#22c55e",
        "cross":                 "#8b5cf6",
        "switch_of_play":        "#06b6d4",
        "set_piece":             "#fbbf24",
        "transition_recovery":   "#f43f5e",
        "high_regain":           "#84cc16",
    }
    method_fig = go.Figure()
    for method_key, pct in method_pcts.items():
        n = method_counts.get(method_key, 0)
        if n == 0:
            continue
        label = method_key.replace("_", " ").title()
        color = METHOD_PALETTE.get(method_key, "#6b7280")
        method_fig.add_trace(go.Bar(
            y=["Method"],
            x=[pct],
            orientation="h",
            name=label,
            marker_color=color,
            text=[f"{label} {pct}%"],
            textposition="inside",
            textfont=dict(size=11, color="#fff"),
            hovertemplate=f"{label}: {n} ({pct}%)<extra></extra>",
        ))
    method_fig.update_layout(
        barmode="stack",
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=0, b=0), height=42,
        xaxis=dict(showgrid=False, showticklabels=False, range=[0, 100], fixedrange=True),
        yaxis=dict(showgrid=False, showticklabels=False, fixedrange=True),
        showlegend=False,
    )

    return html.Div(
        [
            html.Div(
                "\U0001f4ca How the Opponent Attacked Us \u2014 opponent's Phase 2 read defensively",
                className="kpi-subtitle",
                style={
                    "background":    "rgba(239,68,68,0.10)",
                    "borderRadius":  "6px",
                    "padding":       "0.5rem 0.75rem",
                    "marginBottom":  "1rem",
                    "color":         "#ef4444",
                    "fontWeight":    "500",
                },
            ),
            html.Div(
                [
                    _mini_kpi(
                        "FT Entries Conceded", ft_total,
                        "opponent final third entries",
                        MIRROR_COLOR, "bi-door-open",
                    ),
                    _mini_kpi(
                        "Dominant Entry Method", dominant_label,
                        "most frequent entry method",
                        MIRROR_COLOR, "bi-arrow-right-circle-fill",
                    ),
                    _mini_kpi(
                        "Z14 Reach Rate", f"{z14_pct}%",
                        "central channel penetration",
                        "#fbbf24", "bi-crosshair",
                    ),
                    _mini_kpi(
                        "Positive Entry Rate", f"{positive_pct}%",
                        "entries with positive outcome",
                        FAIL_COLOR, "bi-exclamation-circle-fill",
                    ),
                    _mini_kpi(
                        "Avg Passes to FT", f"{avg_passes:.1f}",
                        "build-up depth before FT entry",
                        MID_COLOR, "bi-bezier2",
                    ),
                ],
                className="team-kpi-row",
            ),
            html.P(
                "FT Entries by Corridor",
                className="kpi-subtitle",
                style={"marginTop": "0.75rem", "marginBottom": "0.25rem"},
            ),
            dcc.Graph(
                figure=corridor_fig,
                config={"displayModeBar": False},
            ),
            html.P(
                "Entry Method Distribution",
                className="kpi-subtitle",
                style={"marginTop": "0.75rem", "marginBottom": "0.25rem"},
            ),
            dcc.Graph(
                figure=method_fig,
                config={"displayModeBar": False},
            ),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN CARD
# ═══════════════════════════════════════════════════════════════════════════════

def defensive_structure_card(data: dict) -> html.Div:
    """
    Full D2 card rendered below the D1 card inside the Defensive Phase section.

    Parameters
    ----------
    data : dict
        Output of ``analyse_defensive_structure()`` (with ``pressing_line_median``
        injected by analysis_callbacks._defensive_phase).
    """
    origins = data.get("transition_origins", [])

    return html.Div(
        [
            # ── Card header ────────────────────────────────────────────────────
            html.H5("Defensive Transition", className="buildup-card-title"),

            # ── Defensive Transitions ─────────────────────────────────────────
            _subsection_title("Defensive Transitions"),

            # KPI row: 5 cards
            _section_transition_kpis(data),

            _hr(),

            # Outcome KPI row: N1 / N2 / N3
            _section_outcome_kpis(data),

            # Stacked outcome bar
            html.Div(
                _section_outcome_bar(data),
                style={"marginTop": "0.5rem"},
            ),

            _hr(),

            # Outcomes by Zone
            _subsection_title("Outcomes by Zone"),
            _section_outcomes_by_zone(data),

            _hr(),

            # Outcomes by Corridor
            _subsection_title("Outcomes by Corridor"),
            _section_outcomes_by_corridor(data),

            _hr(),

            # Transition Loss Origins Pitch Map
            _subsection_title("Transition Loss Origins"),
            html.Div(
                [
                    html.P(
                        "Qualifying transitions only \xb7 Origin x \u2265 33.33 (middle + attacking third) \xb7 coloured by outcome",
                        className="kpi-subtitle",
                        style={"marginBottom": "0.4rem", "textAlign": "center"},
                    ),
                    html.Div(
                        dcc.Graph(
                            figure=_build_transition_pitch(origins, data.get("offside_line_median")),
                            config={"displayModeBar": False},
                        ),
                        className="pitch-dark-container",
                    ),
                ],
                style={"marginBottom": "1.5rem"},
            ),

        ],
        className="buildup-card",
        style={"padding": "1.5rem"},
    )
