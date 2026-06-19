"""
Final Third Entry Analysis — UI Components
==========================================
Dash components for the Final Third Entry card inside
Offensive Phase → Build-up.

Follows the exact same patterns as general_buildup_cards.py.
"""

from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import html, dcc
import plotly.graph_objects as go

from src.styling.plotly_template import apply_chart_theme
from src.styling.ui_components import build_unified_modal, ds_header

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
# TEMPO CARD — clickable KPI, opens 15-minute windows modal
# ═══════════════════════════════════════════════════════════════════════════════

def _tempo_card(m: dict, prefix: str = "ma") -> html.Div:
    """
    Render the Tempo KPI card with passes per minute.
    Clicking the card opens a unified modal with the 15-minute window
    breakdown (converted from the old inline <details> expansion).
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

    trigger = html.Div(
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
            html.I(
                className="bi bi-box-arrow-up-right",
                style={"fontSize": "0.65rem", "color": "rgba(255,255,255,0.25)",
                       "position": "absolute", "top": "6px", "right": "8px"},
            ),
        ],
        className="kpi-card",
        id=f"{prefix}-tempo-modal-trigger",
        n_clicks=0,
        style={"cursor": "pointer", "position": "relative"},
    )

    modal = build_unified_modal(
        f"{prefix}-tempo-modal",
        f"{prefix}-tempo-modal-title",
        f"{prefix}-tempo-modal-body",
        title="Tempo — 15-Minute Windows",
        body=(html.Div(window_items) if window_items
              else html.P("No data.", style={"color": "#8899aa"})),
    )

    return html.Div([trigger, modal])


# ═══════════════════════════════════════════════════════════════════════════════
# POSSESSION MODAL HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

_PURPLE       = "#8b5cf6"
_PURPLE_DARK  = "#6d28d9"
_PURPLE_LIGHT = "#a78bfa"
_PURPLE_MID   = "#7c3aed"   # mid-tone for second (opponent) half fill


def _possession_bands_figure(
    bands: list[dict],
    team_name: str,
    opp_name: str,
) -> go.Figure:
    """
    Diverging horizontal bar chart — possession % per 15-min band.
    Team bars grow left (dark purple), opponent bars grow right (light purple).
    """
    if not bands:
        return go.Figure()

    visible = [b for b in bands if b["team_pct"] > 0 or b["opp_pct"] > 0]
    if not visible:
        visible = bands

    labels    = [b["label"]    for b in visible]
    team_pcts = [b["team_pct"] for b in visible]
    opp_pcts  = [b["opp_pct"]  for b in visible]

    fig = go.Figure()

    fig.add_trace(go.Bar(
        y=labels, x=[-v for v in team_pcts], orientation="h",
        name=team_name,
        marker_color=_PURPLE,
        marker_line=dict(color="rgba(255,255,255,0.10)", width=1),
        text=[f"{v}%" for v in team_pcts],
        textposition="inside", insidetextanchor="end",
        textfont=dict(size=11, color="#f0f0f0"),
        hovertemplate=f"{team_name}: %{{customdata}}%<extra></extra>",
        customdata=team_pcts,
    ))

    fig.add_trace(go.Bar(
        y=labels, x=opp_pcts, orientation="h",
        name=opp_name,
        marker_color=_PURPLE_LIGHT,
        marker_line=dict(color="rgba(255,255,255,0.10)", width=1),
        text=[f"{v}%" for v in opp_pcts],
        textposition="inside", insidetextanchor="start",
        textfont=dict(size=11, color="#1a0533"),
        hovertemplate=f"{opp_name}: %{{x}}%<extra></extra>",
    ))

    apply_chart_theme(fig, "dark")

    fig.update_layout(
        barmode="overlay",
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        height=max(300, len(visible) * 36 + 40),
        margin=dict(l=8, r=8, t=8, b=8),
        xaxis=dict(
            showgrid=False, showticklabels=False,
            zeroline=True, zerolinecolor="rgba(255,255,255,0.3)", zerolinewidth=1.5,
            range=[-105, 105], fixedrange=True,
        ),
        yaxis=dict(
            showgrid=False,
            tickfont=dict(size=11, color="#c4b5fd"),
            fixedrange=True, autorange="reversed",
        ),
        showlegend=True,
        legend=dict(
            orientation="h", y=1.06, x=0.5, xanchor="center",
            font=dict(size=11, color="#d0d0d0"), bgcolor="rgba(0,0,0,0)",
        ),
    )
    return fig


def _possession_pitch_figure(own_half_pct: float, opp_half_pct: float) -> go.Figure:
    """
    Football pitch with diagonal hatching. Purple colour scheme.
    The possession split line sits at own_half_pct% of the pitch width.
    Own half = bright purple; opponent half = dark purple.
    """
    import numpy as np

    fig = go.Figure()

    PW, PH = 100.0, 65.0

    # Split line clamped to reasonable range
    split_x = PW * max(0.20, min(0.80, own_half_pct / 100.0))

    # ── Half fills ────────────────────────────────────────────────────────────
    # Own half — bright purple
    fig.add_shape(type="rect", x0=0, y0=0, x1=split_x, y1=PH,
                  fillcolor="rgba(139,92,246,0.70)", line=dict(width=0))
    # Opponent half — darker / more muted purple
    fig.add_shape(type="rect", x0=split_x, y0=0, x1=PW, y1=PH,
                  fillcolor="rgba(109,40,217,0.50)", line=dict(width=0))

    # ── Diagonal hatch lines (same pattern both halves) ───────────────────────
    SPACING   = 6.0
    HATCH_COL = "rgba(255,255,255,0.18)"
    LINE_W    = 1.1

    def _clip(ax0, ay0, ax1, ay1, x_min, x_max):
        if ax1 <= ax0:
            return None
        slope = (ay1 - ay0) / (ax1 - ax0)
        if ax0 < x_min:
            ay0 += slope * (x_min - ax0); ax0 = x_min
        if ax1 > x_max:
            ay1 -= slope * (ax1 - x_max); ax1 = x_max
        return (ax0, ay0, ax1, ay1) if ax1 > ax0 else None

    for xs in np.arange(-PH, PW + PH, SPACING):
        x0_c, y0_c, x1_c, y1_c = xs, 0.0, xs + PH, PH
        for xlo, xhi in ((0, split_x), (split_x, PW)):
            seg = _clip(x0_c, y0_c, x1_c, y1_c, xlo, xhi)
            if seg:
                fig.add_shape(type="line",
                              x0=seg[0], y0=seg[1], x1=seg[2], y1=seg[3],
                              line=dict(color=HATCH_COL, width=LINE_W),
                              layer="above")

    # ── Pitch markings ────────────────────────────────────────────────────────
    def _rect(x0, y0, x1, y1, lw=1.5):
        fig.add_shape(type="rect", x0=x0, y0=y0, x1=x1, y1=y1,
                      fillcolor="rgba(0,0,0,0)",
                      line=dict(color="#ffffff", width=lw))

    _rect(0, 0, PW, PH, lw=2.0)                                   # boundary

    # Standard halfway line
    fig.add_shape(type="line", x0=PW/2, y0=0, x1=PW/2, y1=PH,
                  line=dict(color="#ffffff", width=1.5))

    # Possession split line (thicker, slightly opaque white)
    fig.add_shape(type="line", x0=split_x, y0=0, x1=split_x, y1=PH,
                  line=dict(color="rgba(255,255,255,0.90)", width=2.5))

    # Centre circle + spot
    fig.add_shape(type="circle",
                  x0=PW/2-9.15, y0=PH/2-9.15, x1=PW/2+9.15, y1=PH/2+9.15,
                  fillcolor="rgba(0,0,0,0)", line=dict(color="#ffffff", width=1.2))
    fig.add_trace(go.Scatter(
        x=[PW/2], y=[PH/2], mode="markers",
        marker=dict(color="#ffffff", size=4),
        showlegend=False, hoverinfo="skip",
    ))

    # Penalty areas
    pa_w, pa_h = 16.5, 40.32
    _rect(0, (PH-pa_h)/2, pa_w, (PH+pa_h)/2, lw=1.2)
    _rect(PW-pa_w, (PH-pa_h)/2, PW, (PH+pa_h)/2, lw=1.2)

    # 6-yard boxes
    ga_w, ga_h = 5.5, 18.32
    _rect(0, (PH-ga_h)/2, ga_w, (PH+ga_h)/2, lw=1.2)
    _rect(PW-ga_w, (PH-ga_h)/2, PW, (PH+ga_h)/2, lw=1.2)

    # Penalty spots
    fig.add_trace(go.Scatter(
        x=[11.0, PW-11.0], y=[PH/2, PH/2], mode="markers",
        marker=dict(color="#ffffff", size=3),
        showlegend=False, hoverinfo="skip",
    ))

    apply_chart_theme(fig, "dark")

    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        height=240, margin=dict(l=0, r=0, t=0, b=0),
        xaxis=dict(range=[0, PW], showgrid=False, showticklabels=False,
                   zeroline=False, fixedrange=True),
        yaxis=dict(range=[0, PH], showgrid=False, showticklabels=False,
                   zeroline=False, fixedrange=True, scaleanchor="x", scaleratio=1),
    )
    return fig


def _possession_modal(data: dict, prefix: str = "ma") -> dbc.Modal:
    """
    Build the possession detail modal for the analysed team only.
      1. Possession by 15-min bands (diverging bar chart)
      2. Pitch possession by area (own vs opponent half)
    No team toggle — always shows the analysed team's data.
    """
    m         = data.get("metrics", {})
    home_team = data.get("home_team", "Home")
    away_team = data.get("away_team", "Away")
    team_name = data.get("team_name", home_team)

    # Determine whether the analysed team is home or away
    from src.team_mapping import canonical_name as _cn
    is_home   = _cn(team_name).lower() == _cn(home_team).lower()
    opp_name  = away_team if is_home else home_team

    bands   = m.get("possession_bands",   [])
    by_area = m.get("possession_by_area", {"own_half_pct": 0.0, "opp_half_pct": 0.0})
    own_pct = by_area.get("own_half_pct", 0.0)
    opp_pct = by_area.get("opp_half_pct", 0.0)

    bands_fig = _possession_bands_figure(bands, team_name, opp_name)
    pitch_fig = _possession_pitch_figure(own_pct, opp_pct)

    # ── Section: Possession by Time ──────────────────────────────────────────
    bands_section = html.Div(
        [
            html.H6("POSSESSION BY TIME PERIOD",
                    style={"fontSize": "0.72rem", "fontWeight": "700",
                           "letterSpacing": "1.4px", "color": _PURPLE,
                           "textAlign": "center", "marginBottom": "0.75rem"}),
            dcc.Graph(figure=bands_fig, config={"displayModeBar": False}),
        ],
        style={"background": "var(--bg-card)", "borderRadius": "12px",
               "padding": "1.25rem", "marginBottom": "1rem"},
    )

    # ── Section: Possession by Area ──────────────────────────────────────────
    area_section = html.Div(
        [
            html.H6("POSSESSION BY PITCH AREA",
                    style={"fontSize": "0.72rem", "fontWeight": "700",
                           "letterSpacing": "1.4px", "color": _PURPLE,
                           "textAlign": "center", "marginBottom": "1rem"}),
            html.Div(
                [
                    # Own half label + value
                    html.Div(
                        [
                            html.Span("Own Half",
                                      style={"fontSize": "0.8rem",
                                             "color": "var(--text-secondary)",
                                             "display": "block",
                                             "textAlign": "right",
                                             "marginBottom": "4px"}),
                            html.Span(f"{own_pct}%",
                                      style={"fontSize": "2rem", "fontWeight": "700",
                                             "color": _PURPLE, "display": "block",
                                             "textAlign": "right"}),
                        ],
                        style={"flex": "0 0 auto", "paddingRight": "1rem",
                               "display": "flex", "flexDirection": "column",
                               "justifyContent": "center"},
                    ),
                    # Pitch figure
                    dcc.Graph(figure=pitch_fig, config={"displayModeBar": False},
                              style={"flex": "1", "minWidth": "0"}),
                    # Opponent half label + value
                    html.Div(
                        [
                            html.Span("Opponent Half",
                                      style={"fontSize": "0.8rem",
                                             "color": "var(--text-secondary)",
                                             "display": "block",
                                             "textAlign": "left",
                                             "marginBottom": "4px"}),
                            html.Span(f"{opp_pct}%",
                                      style={"fontSize": "2rem", "fontWeight": "700",
                                             "color": _PURPLE_LIGHT, "display": "block",
                                             "textAlign": "left"}),
                        ],
                        style={"flex": "0 0 auto", "paddingLeft": "1rem",
                               "display": "flex", "flexDirection": "column",
                               "justifyContent": "center"},
                    ),
                ],
                style={"display": "flex", "alignItems": "center"},
            ),
        ],
        style={"background": "var(--bg-card)", "borderRadius": "12px",
               "padding": "1.25rem"},
    )

    return build_unified_modal(
        f"{prefix}-possession-modal",
        f"{prefix}-possession-modal-title",
        f"{prefix}-possession-modal-body",
        title="Possession Detail",
        body=html.Div(
            [bands_section, area_section],
            style={"display": "flex", "flexDirection": "column"},
        ),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# A. POSSESSION OVERVIEW
# ═══════════════════════════════════════════════════════════════════════════════

def _section_possession(m: dict, prefix: str = "ma") -> html.Div:
    """Top-level overview: possession share + final-third entry rate + tempo."""
    # Clickable Possession % card — opens detail modal
    possession_kpi = html.Div(
        [
            html.Div(
                html.I(className="bi bi-pie-chart-fill",
                       style={"color": "#8b5cf6", "fontSize": "1.3rem"}),
                className="kpi-icon",
            ),
            html.Div(
                [
                    html.Span("Possession %", className="kpi-label"),
                    html.Span(f"{m['possession_pct']}%", className="kpi-value"),
                    html.Span("of match possession", className="kpi-subtitle",
                              style={"color": "#8b5cf6"}),
                ],
                className="kpi-text",
            ),
            html.I(
                className="bi bi-box-arrow-up-right",
                style={"fontSize": "0.65rem", "color": "rgba(255,255,255,0.25)",
                       "position": "absolute", "top": "6px", "right": "8px"},
            ),
        ],
        className="kpi-card",
        id=f"{prefix}-possession-modal-trigger",
        n_clicks=0,
        style={"cursor": "pointer", "position": "relative"},
    )

    return html.Div(
        [
            html.H6("Possession & Final Third Entry", className="buildup-subsection-title"),
            html.Div(
                [
                    possession_kpi,
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
                    _tempo_card(m, prefix=prefix),
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
    apply_chart_theme(fig, "dark")
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
    apply_chart_theme(fig, "dark")
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
    apply_chart_theme(fig, "dark")
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
                ds_header(
                    "Offensive Phase — Final Third", "bi-sign-merge-right-fill",
                    "Build-up to Final Third",
                    "How possessions progress into the final third — corridors, "
                    "methods and outcomes",
                ),
                html.P(
                    "No qualifying possession data found for this team in this match.",
                    className="text-muted",
                    style={"padding": "2rem", "textAlign": "center"},
                ),
            ],
            className="buildup-card ma-card",
        )

    sep = html.Hr(style={"borderColor": "var(--border-light)",
                         "margin": "1.5rem 0"})

    return html.Div(
        [
            ds_header(
                "Offensive Phase — Final Third", "bi-sign-merge-right-fill",
                "Build-up to Final Third",
                "How possessions progress into the final third — corridors, "
                "methods and outcomes",
            ),
            # Possession detail modal (toggled by the Possession % KPI card)
            _possession_modal(data, prefix="ma"),
            # A — Possession & entry overview (incl. tempo KPIs)
            _section_possession(m, prefix="ma"),
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
        className="buildup-card ma-card",
    )
