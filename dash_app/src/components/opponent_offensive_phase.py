"""
Opponent Analysis — Offensive Phase Overview
=============================================
Season-aggregate view of a team's offensive phase, composed of three
sub-sections loaded lazily via separate callbacks:

  1. GK Build-up         → opp-section-gk
  2. Final Third Entries → opp-section-ft
  3. Chance Creation     → opp-section-cc

Public entry points
-------------------
    offensive_phase_overview_card(season, team_name)
        Returns the page skeleton immediately (no heavy computation).
        Three placeholder divs are populated by lazy callbacks.

    build_gk_section(season, team_name)     → html.Div
    build_ft_section(season, team_name)     → html.Div
    build_cc_section(season, team_name)     → html.Div
        Called by dedicated callbacks; each does its own aggregation + benchmark.
"""

from __future__ import annotations

import plotly.graph_objects as go
import dash_bootstrap_components as dbc
from dash import dcc, html, Input, Output, State, no_update

from src.config import PRIMARY_COLOR
from src.components.final_third_pitch import (
    METHOD_COLORS,
    METHOD_LABELS,
    OUTCOME_COLORS,
)
from src.styling.theme import COLORS_DARK, SEMANTIC_COLORS
from src.styling.plotly_template import apply_chart_theme
from src.styling.pitch_utils import draw_pitch
from src.styling.ui_components import build_unified_modal, ds_header

# ─── Shared colour constants — bound to the design system (values unchanged) ──
_NEUTRAL   = SEMANTIC_COLORS["benchmark_neutral"]   # "#4a6274" (mirror ppda.py)
_HIGHLIGHT = COLORS_DARK["accent"]                  # "#8a1f33" (== PRIMARY_COLOR)

# ─── Outcome tier metadata (from buildup_cards.py) ────────────────────────────
_GRANULAR_TIERS = [
    ("P1", "Established Possession", "#22c55e"),
    ("P2", "Reached Final Third",    "#16a34a"),
    ("P3", "Created a Shot",         "#15803d"),
    ("N1", "Possession Lost",        "#f97316"),
    ("N2", "Box Entry Conceded",     "#ef4444"),
    ("N3", "Shot Conceded",          "#dc2626"),
]


# ─── Shared mini-KPI helper ───────────────────────────────────────────────────

def _mini_kpi(label: str, value, subtitle: str, color: str, icon: str) -> html.Div:
    """Single mini KPI card, consistent with final_third_cards._mini_kpi."""
    return html.Div(
        [
            html.Div(
                html.I(className=f"bi {icon}",
                       style={"color": color, "fontSize": "1.3rem"}),
                className="kpi-icon",
            ),
            html.Div(
                [
                    html.Span(label,       className="kpi-label"),
                    html.Span(str(value),  className="kpi-value"),
                    html.Span(subtitle,    className="kpi-subtitle",
                              style={"color": color}),
                ],
                className="kpi-text",
            ),
        ],
        className="kpi-card",
    )


def _section_header(title: str, icon: str,
                    eyebrow: str = "Opponent Analysis",
                    subtitle: str = "") -> html.Div:
    """House-style section header (delegates to the shared ds_header)."""
    return ds_header(eyebrow, icon, title, subtitle)


# ═══════════════════════════════════════════════════════════════════════════════
# SKELETON — returned immediately, no computation
# ═══════════════════════════════════════════════════════════════════════════════

def offensive_phase_overview_card(season: str, team_name: str) -> html.Div:
    """
    Return the Offensive Phase Overview page skeleton immediately.

    The three heavy sub-sections are empty placeholder divs that are
    filled by separate lazy callbacks (one per section), each wrapped
    in dcc.Loading so the user sees a spinner per section.

    Parameters
    ----------
    season : str
        Season key, e.g. ``"2025_2026"``.
    team_name : str
        Canonical team name.
    """
    season_label = season.replace("_", "/")

    # House-style page header (ma-card scope provides the ds-* styles)
    header = html.Div(
        ds_header(
            "Opponent Analysis — Season View", "bi-lightning-charge-fill",
            f"Offensive Phase Overview — {team_name}  ({season_label})",
            "Season-aggregate GK build-up, final third entries and chance "
            "creation, benchmarked against the league",
        ),
        className="ma-card",
        style={"marginBottom": "0.5rem", "paddingTop": "12px"},
    )

    def _placeholder(section_id: str) -> html.Div:
        return html.Div(
            dcc.Loading(
                html.Div(id=section_id),
                type="circle",
                color="#8a1f33",
            ),
            style={"minHeight": "120px"},
            id=f"{section_id}-wrap",
        )

    return html.Div(
        [
            header,
            _placeholder("opp-section-gk"),
            html.Hr(style={"borderColor": "rgba(255,255,255,0.08)",
                            "margin": "0.5rem 0 1.5rem"}),
            _placeholder("opp-section-ft"),
            html.Hr(style={"borderColor": "rgba(255,255,255,0.08)",
                            "margin": "0.5rem 0 1.5rem"}),
            _placeholder("opp-section-cc"),
        ],
        style={"padding": "0"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# BENCHMARKING BAR CHART (replicates build_ppda_bar_figure exactly)
# ═══════════════════════════════════════════════════════════════════════════════

def _build_benchmark_bar(
    benchmarks: dict,
    metric_key: str,
    title: str,
    x_label: str,
    highlight_team: str,
) -> go.Figure:
    """
    Horizontal bar chart ranking all teams by *metric_key*.

    Replicates build_ppda_bar_figure() visual style:
      - Sorted descending (best at top)
      - Highlighted team in PRIMARY_COLOR; others in #4a6274
      - League average as a vertical dashed line
      - Dark theme, no legend
    """
    if not benchmarks:
        fig = go.Figure()
        fig.update_layout(title=title)
        return apply_chart_theme(fig, "dark")

    pairs = sorted(
        [(team, float(vals.get(metric_key, 0.0))) for team, vals in benchmarks.items()],
        key=lambda t: t[1],
        reverse=True,
    )
    teams  = [p[0] for p in pairs]
    values = [p[1] for p in pairs]
    hl_lower = highlight_team.strip().lower()
    colors = [
        _HIGHLIGHT if t.strip().lower() == hl_lower else _NEUTRAL
        for t in teams
    ]
    avg_val = sum(values) / len(values) if values else 0.0

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=values, y=teams,
        orientation="h",
        marker=dict(color=colors, line=dict(width=0)),
        text=[f"{v:.2f}" for v in values],
        textposition="outside",
        textfont=dict(size=10, color="#c8d0d8"),
        hovertemplate="<b>%{y}</b><br>" + x_label + ": %{x:.2f}<extra></extra>",
    ))
    # Phase 4: avg line/label in a neutral slate readable on BOTH themes (the
    # JS observer does not repaint annotations; was white-on-dark only).
    fig.add_vline(
        x=avg_val,
        line=dict(color="rgba(116,139,156,0.85)", width=1.5, dash="dash"),
        annotation_text=f"Avg {avg_val:.2f}",
        annotation_position="top right",
        annotation_font=dict(size=10, color="#748b9c"),
    )
    apply_chart_theme(fig, "dark")
    fig.update_layout(
        title=dict(text=title, font=dict(size=14)),
        xaxis=dict(title=x_label, zeroline=False),
        yaxis=dict(title="", autorange="reversed", tickfont=dict(size=10)),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=max(420, len(teams) * 30),
        margin=dict(l=130, r=70, t=50, b=40),
        showlegend=False,
        bargap=0.25,
    )
    return fig


def _two_col(left: dcc.Graph, right: dcc.Graph) -> html.Div:
    """Render two graphs side by side, wrapping on narrow screens."""
    return html.Div(
        [
            html.Div(left,  style={"flex": "1", "minWidth": "0"}),
            html.Div(right, style={"flex": "1", "minWidth": "0"}),
        ],
        style={"display": "flex", "gap": "1.5rem",
               "marginTop": "1.5rem", "flexWrap": "wrap"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SUB-SECTION 1 — GK BUILD-UP  (lazy)
# ═══════════════════════════════════════════════════════════════════════════════

def _build_outcome_radar(granular_counts: dict, pass_type: str) -> go.Figure:
    """
    Pizza chart showing the % breakdown across P1/P2/P3/N1/N2/N3 for one
    distribution type (short or long).

    Positive outcomes (P1–P3): green gradient (light → dark as quality rises).
    Negative outcomes (N1–N3): red gradient  (light → dark as severity rises).
    """
    # Order: positive first, then negative — both light→dark within their group
    _SLICE_META = [
        ("P1", "Established Possession", "#4ade80"),  # light green
        ("P2", "Reached Final Third",    "#16a34a"),  # mid green
        ("P3", "Created a Shot",         "#14532d"),  # dark green
        ("N1", "Possession Lost",        "#fca5a5"),  # light red
        ("N2", "Box Entry Conceded",     "#dc2626"),  # mid red
        ("N3", "Shot Conceded",          "#7f1d1d"),  # dark red
    ]

    codes  = [t[0] for t in _SLICE_META]
    labels = [f"{t[0]} — {t[1]}" for t in _SLICE_META]
    colors = [t[2] for t in _SLICE_META]
    counts = [granular_counts.get(c, 0) for c in codes]

    type_label = "Short Pass" if pass_type == "short" else "Long Ball"

    fig = go.Figure(go.Pie(
        labels=labels,
        values=counts,
        marker=dict(
            colors=colors,
            line=dict(color="rgba(255,255,255,0.15)", width=1),
        ),
        textinfo="percent+label",
        textfont=dict(size=10, color="white"),
        insidetextorientation="radial",
        hole=0,
        hovertemplate="<b>%{label}</b><br>Count: %{value}<br>Share: %{percent}<extra></extra>",
        sort=False,
        direction="clockwise",
    ))
    apply_chart_theme(fig, "dark")
    fig.update_layout(
        title=dict(
            text=f"Outcome Breakdown — {type_label}",
            font=dict(size=12, color="white"), x=0.5,
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=320,
        margin=dict(l=10, r=150, t=50, b=20),
        legend=dict(
            orientation="v",
            yanchor="middle", y=0.5,
            xanchor="left",   x=1.01,
            font=dict(size=10, color="#d0d0d0"),
            bgcolor="rgba(15,25,35,0.8)",
            bordercolor="rgba(255,255,255,0.1)",
            borderwidth=1,
        ),
        showlegend=True,
    )
    return fig


# Colour map reused in both the legacy radar and the new donut
_DONUT_SLICE_META = [
    ("P1", "Established Possession", "#4ade80"),  # light green
    ("P2", "Reached Final Third",    "#16a34a"),  # mid green
    ("P3", "Created a Shot",         "#14532d"),  # dark green
    ("N1", "Possession Lost",        "#fca5a5"),  # light red
    ("N2", "Box Entry Conceded",     "#dc2626"),  # mid red
    ("N3", "Shot Conceded",          "#7f1d1d"),  # dark red
]


def _build_gk_outcome_donut(
    granular_counts: dict,
    metric_label: str,
    team_name: str = "",
    season: str = "",
) -> html.Div:
    """
    Animated donut chart (hole=0.60) for the GK outcome breakdown modal.

    Segments ordered P1→P2→P3→[gap]→N1→N2→N3 (positive then negative).
    Centre hole shows combined positive rate. Legend is right of the ring.
    Returns an html.Div containing the dcc.Graph plus a subtitle paragraph.
    """
    codes  = [m[0] for m in _DONUT_SLICE_META]
    descs  = [m[1] for m in _DONUT_SLICE_META]
    colors = [m[2] for m in _DONUT_SLICE_META]
    raw_counts = [granular_counts.get(c, 0) for c in codes]
    total      = sum(raw_counts) or 1

    # Positive rate for centre annotation
    pos_count = sum(granular_counts.get(c, 0) for c in ("P1", "P2", "P3"))
    pos_rate  = f"{pos_count / total * 100:.1f}%"

    # Suppress percentage label on segments below 3% to avoid clutter
    seg_text = [
        f"{v / total * 100:.1f}%" if v / total >= 0.03 else ""
        for v in raw_counts
    ]

    # Build trace data: insert invisible gap segment between P3 and N1
    all_codes   = codes[:3] + ["_gap"] + codes[3:]
    all_descs   = descs[:3] + [""]     + descs[3:]
    all_colors  = colors[:3] + ["rgba(0,0,0,0)"] + colors[3:]
    all_counts  = raw_counts[:3] + [0.001] + raw_counts[3:]
    all_text    = seg_text[:3] + [""] + seg_text[3:]

    labels = [
        f"{c} — {d}" if c != "_gap" else ""
        for c, d in zip(all_codes, all_descs)
    ]
    custom = [
        f"{d}<br>n={v}<br>{v / total * 100:.1f}%" if c != "_gap" else ""
        for c, d, v in zip(all_codes, all_descs, all_counts)
    ]

    fig = go.Figure(
        go.Pie(
            labels=labels,
            values=all_counts,
            text=all_text,
            customdata=custom,
            marker=dict(
                colors=all_colors,
                line=dict(color="rgba(255,255,255,0.18)", width=1.5),
            ),
            textinfo="text",
            textposition="outside",
            textfont=dict(size=12, color="white"),
            hole=0.60,
            hovertemplate="%{customdata}<extra></extra>",
            sort=False,
            direction="clockwise",
            showlegend=True,
        ),
        layout=dict(
            transition=dict(duration=600, easing="cubic-in-out"),
        ),
    )

    apply_chart_theme(fig, "dark")
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=400,
        margin=dict(l=20, r=180, t=40, b=60),
        annotations=[
            dict(
                text=f"<b>{pos_rate}</b>",
                x=0.5, y=0.55,
                xref="paper", yref="paper",
                xanchor="center", yanchor="middle",
                showarrow=False,
                font=dict(size=20, color="white"),
            ),
            dict(
                text="Positive Rate",
                x=0.5, y=0.42,
                xref="paper", yref="paper",
                xanchor="center", yanchor="middle",
                showarrow=False,
                font=dict(size=12, color="rgba(200,200,200,0.75)"),
            ),
        ],
        legend=dict(
            orientation="v",
            xanchor="left",   x=1.02,
            yanchor="middle", y=0.5,
            font=dict(size=12, color="#d0d0d0"),
            bgcolor="rgba(13,17,23,0.7)",
            borderwidth=0,
            traceorder="normal",
        ),
        showlegend=True,
    )

    subtitle_parts = []
    if team_name:
        subtitle_parts.append(team_name)
    if season:
        subtitle_parts.append(season.replace("_", "/"))
    subtitle_text = " · ".join(subtitle_parts) if subtitle_parts else ""

    return html.Div(
        [
            html.Div(
                dcc.Graph(
                    figure=fig,
                    config={"displayModeBar": False},
                    style={"width": "100%", "transition": "opacity 0.4s ease"},
                ),
                style={"animation": "fadeSlideIn 0.5s ease-out both"},
            ),
            html.P(
                subtitle_text,
                style={
                    "fontSize": "12px",
                    "color": "var(--text-muted)",
                    "textAlign": "center",
                    "marginTop": "0.25rem",
                },
            ) if subtitle_text else None,
        ]
    )


def _build_gk_zone_pitch(events: list[dict]) -> go.Figure:
    """
    18-zone pitch showing count of GK distributions whose endpoint (recv_x/y)
    fell in each zone, with red gradient fill and green/red outcome indicators.

    Replicates pitch_zone_figure() from pitch_zones.py with a red colorscale
    and uses recv_x/recv_y as the endpoint coordinate.
    """
    from src.components.pitch_zones import X_EDGES, Y_EDGES, COLS

    # Accumulate counts per zone
    zone_counts: dict[int, int] = {}
    zone_pos:    dict[int, int] = {}
    zone_neg:    dict[int, int] = {}

    for e in events:
        rx = e.get("recv_x")
        ry = e.get("recv_y")
        if rx is None or ry is None:
            continue
        try:
            rx, ry = float(rx), float(ry)
        except (TypeError, ValueError):
            continue

        x = max(0.0, min(100.0, rx))
        y = max(0.0, min(100.0, ry))
        row = min(int(x / (100.0 / 6)), 5)
        col = min(int(y / (100.0 / 3)), 2)
        zone = row * 3 + col + 1

        zone_counts[zone] = zone_counts.get(zone, 0) + 1
        outcome = str(e.get("outcome", "negative"))
        if outcome == "positive":
            zone_pos[zone] = zone_pos.get(zone, 0) + 1
        else:
            zone_neg[zone] = zone_neg.get(zone, 0) + 1

    fig = go.Figure()
    max_count = max(zone_counts.values()) if zone_counts else 1

    for zone_num in range(1, 19):
        row = (zone_num - 1) // COLS
        col = (zone_num - 1) % COLS
        x0, x1 = X_EDGES[row], X_EDGES[row + 1]
        y0, y1 = Y_EDGES[col], Y_EDGES[col + 1]
        cx = (x0 + x1) / 2
        cy = (y0 + y1) / 2

        count = zone_counts.get(zone_num, 0)
        intensity = count / max_count if max_count else 0

        # Red gradient: transparent → vivid red
        r = int(120 + (220 - 120) * intensity)
        g = int(30 + (40 - 30) * (1 - intensity))
        b = int(30 + (40 - 30) * (1 - intensity))
        alpha = 0.1 + 0.65 * intensity
        fill_color = f"rgba({r},{g},{b},{alpha})"

        fig.add_shape(
            type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
            line=dict(color="rgba(255,255,255,0.15)", width=1),
            fillcolor=fill_color, layer="below",
        )

        if count > 0:
            # Total count centred
            fig.add_annotation(
                x=cx, y=cy + 5,
                text=f"<b>{count}</b>",
                showarrow=False,
                font=dict(size=14, color="#f0f0f0"),
            )
            fig.add_annotation(
                x=cx, y=cy - 4,
                text=f"Z{zone_num}",
                showarrow=False,
                font=dict(size=8, color="rgba(255,255,255,0.45)"),
            )
            # Green/red outcome indicators
            pos_n = zone_pos.get(zone_num, 0)
            neg_n = zone_neg.get(zone_num, 0)
            indicator = ""
            if pos_n:
                indicator += f"<span style='color:#22c55e'>●{pos_n}</span>"
            if neg_n:
                if indicator:
                    indicator += " "
                indicator += f"<span style='color:#ef4444'>●{neg_n}</span>"
            if indicator:
                fig.add_annotation(
                    x=cx, y=cy - 12,
                    text=indicator,
                    showarrow=False,
                    font=dict(size=9),
                )
        else:
            fig.add_annotation(
                x=cx, y=cy,
                text=f"Z{zone_num}",
                showarrow=False,
                font=dict(size=8, color="rgba(255,255,255,0.22)"),
            )

    # Pitch markings
    fig.add_shape(type="line", x0=50, x1=50, y0=0, y1=100,
                  line=dict(color="rgba(255,255,255,0.18)", width=1, dash="dot"))
    fig.add_shape(type="rect", x0=0,    x1=16.5, y0=21, y1=79,
                  line=dict(color="rgba(255,255,255,0.12)", width=1))
    fig.add_shape(type="rect", x0=83.5, x1=100,  y0=21, y1=79,
                  line=dict(color="rgba(255,255,255,0.12)", width=1))
    fig.add_annotation(x=92, y=-5, text="ATK →", showarrow=False,
                       font=dict(size=9, color="rgba(255,255,255,0.35)"))
    fig.add_annotation(x=8,  y=-5, text="← OWN GOAL", showarrow=False,
                       font=dict(size=9, color="rgba(255,255,255,0.35)"))

    apply_chart_theme(fig, "dark")
    fig.update_layout(
        title=dict(text="GK Distribution End-Points",
                   font=dict(size=13, color="#f0f0f0"), x=0.5),
        xaxis=dict(range=[-2, 102], showgrid=False, zeroline=False,
                   showticklabels=False, fixedrange=True),
        yaxis=dict(range=[-10, 105], showgrid=False, zeroline=False,
                   showticklabels=False, fixedrange=True,
                   scaleanchor="x", scaleratio=0.68),
        plot_bgcolor="rgba(15,25,35,0.7)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=40, b=20),
        height=400,
        showlegend=False,
    )
    return fig


def _build_gk_benchmark_bar(
    benchmarks: dict,
    metric: str,
    team_name: str,
) -> go.Figure:
    """Horizontal bar ranking all teams by *metric*. Accepts 'short' or 'long'."""
    if metric == "short":
        metric_key = "gk_short_success_rate"
        title      = "GK Short-Pass Success Rate — All Teams"
        x_label    = "Short-pass success rate (%)"
    else:
        metric_key = "gk_long_success_rate"
        title      = "GK Long-Ball Success Rate — All Teams"
        x_label    = "Long-ball success rate (%)"

    return _build_benchmark_bar(benchmarks, metric_key, title, x_label, team_name)


def build_gk_section(season: str, team_name: str) -> html.Div:
    """
    Build the GK Build-up sub-section for one team+season.

    Called by a dedicated lazy callback; does its own caching via
    compute_season_gk_buildup() and compute_league_offensive_benchmarks().
    """
    from src.analytics.season_offensive_summary import (
        compute_season_gk_buildup,
        compute_league_offensive_benchmarks,
    )

    data = compute_season_gk_buildup(season, team_name)
    m    = data["metrics"]
    benchmarks = compute_league_offensive_benchmarks(season)

    # ── KPI row: Matches | GK Possessions | Short Pass % | Long Ball % ──────
    kpi_row = html.Div(
        [
            _mini_kpi("Matches", data["matches"], "analysed",
                      "#8899aa", "bi-calendar3"),
            _mini_kpi("GK Possessions", m["total"],
                      f"{m['avg_per_match']}/match avg",
                      "#3b82f6", "bi-person-fill"),
            # Short Pass % card — clickable, opens outcome breakdown modal
            html.Div(
                [
                    html.Div(
                        html.I(className="bi bi-arrow-right",
                               style={"color": "#22c55e", "fontSize": "1.3rem"}),
                        className="kpi-icon",
                    ),
                    html.Div(
                        [
                            html.Span("Short Pass %", className="kpi-label"),
                            html.Span(f"{m['short_pct']}%", className="kpi-value"),
                            html.Span(f"{m['short_success_rate']}% success",
                                      className="kpi-subtitle",
                                      style={"color": "#22c55e"}),
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
                id="opp-season-gk-sp-card",
                n_clicks=0,
                style={"cursor": "pointer", "position": "relative"},
            ),
            # Long Ball % card — clickable, opens outcome breakdown modal
            html.Div(
                [
                    html.Div(
                        html.I(className="bi bi-arrow-up-right",
                               style={"color": "#f97316", "fontSize": "1.3rem"}),
                        className="kpi-icon",
                    ),
                    html.Div(
                        [
                            html.Span("Long Ball %", className="kpi-label"),
                            html.Span(f"{m['long_pct']}%", className="kpi-value"),
                            html.Span(f"{m['long_success_rate']}% success",
                                      className="kpi-subtitle",
                                      style={"color": "#f97316"}),
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
                id="opp-season-gk-lb-card",
                n_clicks=0,
                style={"cursor": "pointer", "position": "relative"},
            ),
        ],
        className="team-kpi-row",
    )

    # Modals for outcome breakdown (body populated by callbacks)
    sp_modal = build_unified_modal(
        "opp-season-gk-sp-outcome-modal",
        "opp-season-gk-sp-outcome-modal-title",
        "opp-season-gk-sp-outcome-modal-body",
        title="Outcome Breakdown — Short Pass",
        size="lg",
    )
    lb_modal = build_unified_modal(
        "opp-season-gk-lb-outcome-modal",
        "opp-season-gk-lb-outcome-modal-title",
        "opp-season-gk-lb-outcome-modal-body",
        title="Outcome Breakdown — Long Ball",
        size="lg",
    )

    # ── Zone pitch (replaces scatter) ────────────────────────────────────────
    fig_pitch = _build_gk_zone_pitch(data["events"])

    # ── Benchmark bar (default: short pass; togglable via button group) ──────
    fig_bench_short = _build_gk_benchmark_bar(benchmarks, "short", team_name)
    fig_bench_long  = _build_gk_benchmark_bar(benchmarks, "long",  team_name)

    bench_toggle = html.Div(
        [
            html.Button(
                "Short Pass", id="opp-season-gk-bench-short-btn",
                n_clicks=0,
                className="btn btn-sm",
                style={
                    "padding": "3px 12px", "fontSize": "0.75rem",
                    "borderRadius": "12px 0 0 12px",
                    "background": PRIMARY_COLOR, "color": "white",
                    "border": f"1px solid {PRIMARY_COLOR}",
                    "cursor": "pointer",
                },
            ),
            html.Button(
                "Long Ball", id="opp-season-gk-bench-long-btn",
                n_clicks=0,
                className="btn btn-sm",
                style={
                    "padding": "3px 12px", "fontSize": "0.75rem",
                    "borderRadius": "0 12px 12px 0",
                    "background": "transparent", "color": "#f97316",
                    "border": "1px solid #f97316",
                    "cursor": "pointer",
                },
            ),
        ],
        style={"display": "flex", "justifyContent": "flex-end",
               "marginBottom": "0.4rem"},
    )

    dcc.Store(id="opp-season-gk-bench-metric", data="short")

    bench_panel = html.Div(
        [
            bench_toggle,
            dcc.Graph(
                id="opp-season-gk-bench-graph",
                figure=fig_bench_short,
                config={"displayModeBar": False},
            ),
        ]
    )

    return html.Div(
        [
            _section_header(
                "GK Build-up — Season Aggregate", "bi-person-fill",
                eyebrow="Opponent — GK Distribution",
                subtitle="Where goal kicks end up, distribution outcomes and "
                         "league benchmarks",
            ),
            sp_modal,
            lb_modal,
            kpi_row,
            _two_col(
                # pitch-dark-container: dark pitch stays dark in light mode
                # (skip-list convention; Phase 4 audit fix)
                html.Div(
                    dcc.Graph(figure=fig_pitch, config={"displayModeBar": False}),
                    className="pitch-dark-container",
                ),
                bench_panel,
            ),
        ],
        className="analysis-section buildup-card ma-card",
        style={"marginBottom": "2rem", "padding": "1.5rem"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SUB-SECTION 2 — FINAL THIRD ENTRIES  (lazy)
# ═══════════════════════════════════════════════════════════════════════════════

# Human-readable labels for the Top Method dropdown
_FT_METHOD_LABELS = {
    "transition_recovery": "Transition / Recovery",
    "through_ball":        "Through Ball",
    "switch_of_play":      "Switch of Play",
    "set_piece":           "Set-Piece",
    "long_ball":           "Long Ball",
    "cross_delivery":      "Cross Delivery",
    "individual_carry":    "Individual Carry",
    "short_pass":          "Short Pass",
}


def _build_ft_zone_pitch(entries: list[dict]) -> "go.Figure":
    """
    18-zone pitch showing count of FT entries whose entry point (entry_x/entry_y)
    fell in each zone.  Styled identically to _build_gk_zone_pitch:
      - Red intensity gradient (more entries = more saturated red)
      - Green/red outcome indicator dots per zone
    """
    from src.components.pitch_zones import X_EDGES, Y_EDGES, COLS

    zone_counts: dict[int, int] = {}
    zone_pos:    dict[int, int] = {}
    zone_neg:    dict[int, int] = {}

    for e in entries:
        ex = e.get("entry_x")
        ey = e.get("entry_y")
        if ex is None or ey is None:
            continue
        try:
            ex, ey = float(ex), float(ey)
        except (TypeError, ValueError):
            continue

        x = max(0.0, min(100.0, ex))
        y = max(0.0, min(100.0, ey))
        row = min(int(x / (100.0 / 6)), 5)
        col = min(int(y / (100.0 / 3)), 2)
        zone = row * 3 + col + 1

        zone_counts[zone] = zone_counts.get(zone, 0) + 1
        outcome = str(e.get("outcome", "negative"))
        if outcome == "positive":
            zone_pos[zone] = zone_pos.get(zone, 0) + 1
        else:
            zone_neg[zone] = zone_neg.get(zone, 0) + 1

    fig = go.Figure()
    max_count = max(zone_counts.values()) if zone_counts else 1

    for zone_num in range(1, 19):
        row = (zone_num - 1) // COLS
        col = (zone_num - 1) % COLS
        x0, x1 = X_EDGES[row], X_EDGES[row + 1]
        y0, y1 = Y_EDGES[col], Y_EDGES[col + 1]
        cx = (x0 + x1) / 2
        cy = (y0 + y1) / 2

        count = zone_counts.get(zone_num, 0)
        intensity = count / max_count if max_count else 0

        r = int(120 + (220 - 120) * intensity)
        g = int(30 + (40 - 30) * (1 - intensity))
        b = int(30 + (40 - 30) * (1 - intensity))
        alpha = 0.1 + 0.65 * intensity
        fill_color = f"rgba({r},{g},{b},{alpha})"

        fig.add_shape(
            type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
            line=dict(color="rgba(255,255,255,0.15)", width=1),
            fillcolor=fill_color, layer="below",
        )

        if count > 0:
            fig.add_annotation(
                x=cx, y=cy + 5,
                text=f"<b>{count}</b>",
                showarrow=False,
                font=dict(size=14, color="#f0f0f0"),
            )
            fig.add_annotation(
                x=cx, y=cy - 4,
                text=f"Z{zone_num}",
                showarrow=False,
                font=dict(size=8, color="rgba(255,255,255,0.45)"),
            )
            pos_n = zone_pos.get(zone_num, 0)
            neg_n = zone_neg.get(zone_num, 0)
            indicator = ""
            if pos_n:
                indicator += f"<span style='color:#22c55e'>●{pos_n}</span>"
            if neg_n:
                if indicator:
                    indicator += " "
                indicator += f"<span style='color:#ef4444'>●{neg_n}</span>"
            if indicator:
                fig.add_annotation(
                    x=cx, y=cy - 12,
                    text=indicator,
                    showarrow=False,
                    font=dict(size=9),
                )
        else:
            fig.add_annotation(
                x=cx, y=cy,
                text=f"Z{zone_num}",
                showarrow=False,
                font=dict(size=8, color="rgba(255,255,255,0.22)"),
            )

    # FT line
    fig.add_shape(type="line", x0=66.67, x1=66.67, y0=0, y1=100,
                  line=dict(color="rgba(255,255,255,0.5)", width=2, dash="dash"))
    fig.add_shape(type="line", x0=50, x1=50, y0=0, y1=100,
                  line=dict(color="rgba(255,255,255,0.18)", width=1, dash="dot"))
    fig.add_shape(type="rect", x0=0,    x1=16.5, y0=21, y1=79,
                  line=dict(color="rgba(255,255,255,0.12)", width=1))
    fig.add_shape(type="rect", x0=83.5, x1=100,  y0=21, y1=79,
                  line=dict(color="rgba(255,255,255,0.12)", width=1))
    fig.add_annotation(x=92, y=-5, text="ATK →", showarrow=False,
                       font=dict(size=9, color="rgba(255,255,255,0.35)"))
    fig.add_annotation(x=8,  y=-5, text="← OWN GOAL", showarrow=False,
                       font=dict(size=9, color="rgba(255,255,255,0.35)"))

    apply_chart_theme(fig, "dark")
    fig.update_layout(
        title=dict(text="FT Entry Points by Zone",
                   font=dict(size=13, color="#f0f0f0"), x=0.5),
        xaxis=dict(range=[-2, 102], showgrid=False, zeroline=False,
                   showticklabels=False, fixedrange=True),
        yaxis=dict(range=[-10, 105], showgrid=False, zeroline=False,
                   showticklabels=False, fixedrange=True,
                   scaleanchor="x", scaleratio=0.68),
        plot_bgcolor="rgba(15,25,35,0.7)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=40, b=20),
        height=400,
        showlegend=False,
    )
    return fig


def _build_top_method_card(m: dict) -> html.Div:
    """
    Clickable KPI card showing top method label + %.
    Opens a modal with the full method breakdown.
    """
    method_counts = m.get("method_counts", {})
    method_pcts   = m.get("method_pcts",   {})
    default_key   = m.get("top_method", "short_pass")

    has_data = any(v > 0 for v in method_counts.values())
    if not has_data:
        return _mini_kpi(
            "Top Method", "—", "no data",
            "#8899aa", "bi-bar-chart-fill",
        )

    top_pct   = method_pcts.get(default_key, 0.0)
    top_label = _FT_METHOD_LABELS.get(default_key, default_key)
    top_color = METHOD_COLORS.get(default_key, "#8a1f33")

    return html.Div(
        [
            html.Div(
                html.I(className="bi bi-bar-chart-fill",
                       style={"color": top_color, "fontSize": "1.3rem"}),
                className="kpi-icon",
            ),
            html.Div(
                [
                    html.Span("Top Method", className="kpi-label"),
                    html.Span(f"{top_pct}%", className="kpi-value"),
                    html.Span(top_label, className="kpi-subtitle",
                              style={"color": top_color}),
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
        id="opp-season-ft-method-card",
        n_clicks=0,
        style={"cursor": "pointer", "position": "relative"},
    )


def _build_ft_entry_scatter(entries: list[dict]) -> "go.Figure":
    """
    Season-aggregate pitch scatter of FT entry points, coloured by method.

    Replicates ft_entry_scatter_method() from final_third_pitch.py exactly,
    including short_pass entries.
    """
    _METHOD_ORDER = [
        "transition_recovery", "through_ball", "switch_of_play", "set_piece",
        "long_ball", "cross_delivery", "individual_carry", "short_pass",
    ]

    grouped: dict[str, list] = {k: [] for k in _METHOD_ORDER}
    for e in entries:
        m = e.get("method", "short_pass")
        x = e.get("entry_x", 0)
        y = e.get("entry_y", 50)
        minute = int(e.get("minute", 0))
        corridor = e.get("corridor", "?")
        outcome = e.get("outcome", "negative")
        player = e.get("player", "?")
        grouped.setdefault(m, []).append(
            (x, y, f"{minute}' {player} [{corridor}] [{outcome}]")
        )

    fig = go.Figure()
    for method in _METHOD_ORDER:
        pts = grouped.get(method, [])
        if not pts:
            continue
        fig.add_trace(go.Scatter(
            x=[p[0] for p in pts],
            y=[p[1] for p in pts],
            mode="markers",
            name=METHOD_LABELS[method],
            marker=dict(
                color=METHOD_COLORS[method],
                size=8,
                opacity=0.8,
                line=dict(color="rgba(255,255,255,0.4)", width=0.5),
            ),
            hovertemplate=(
                f"<b>{METHOD_LABELS[method]}</b><br>"
                "x=%{x:.1f}, y=%{y:.1f}<br>"
                "%{text}<extra></extra>"
            ),
            text=[p[2] for p in pts],
            showlegend=True,
        ))

    # Phase 3: migrated to the shared design-system pitch (the private
    # _draw_pitch_base/_base_layout helpers were removed in Phase 2b — this
    # also fixes the broken import that made this page fail to load).
    apply_chart_theme(fig, "dark")
    draw_pitch(
        fig, theme="dark",
        title="Entry Points by Method — Season",
        height=400, show_legend=True,
        draw_zones=True, highlight_final_third=True,
    )
    fig.update_layout(
        margin=dict(l=10, r=130, t=40, b=20),
        legend=dict(font=dict(size=9)),
    )
    return fig


def _build_ft_success_by_method(entries: list[dict]) -> go.Figure:
    """
    Horizontal bar chart — success rate (% positive) per entry method.
    Bars coloured by method colour; league-average reference line.
    Only shows methods that have at least one entry.
    """
    _METHOD_ORDER = [
        "transition_recovery", "through_ball", "switch_of_play", "set_piece",
        "long_ball", "cross_delivery", "individual_carry", "short_pass",
    ]
    counts: dict[str, int] = {}
    positives: dict[str, int] = {}
    for e in entries:
        m = e.get("method", "short_pass")
        counts[m]    = counts.get(m, 0) + 1
        if e.get("outcome") == "positive":
            positives[m] = positives.get(m, 0) + 1

    methods, rates, colors = [], [], []
    for m in _METHOD_ORDER:
        c = counts.get(m, 0)
        if c == 0:
            continue
        rate = round(positives.get(m, 0) / c * 100, 1)
        methods.append(METHOD_LABELS[m])
        rates.append(rate)
        colors.append(METHOD_COLORS[m])

    if not methods:
        fig = go.Figure()
        apply_chart_theme(fig, "dark")
        fig.update_layout(
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        return fig

    avg = round(sum(rates) / len(rates), 1)

    fig = go.Figure(go.Bar(
        x=rates, y=methods,
        orientation="h",
        marker=dict(color=colors, line=dict(width=0)),
        text=[f"{r}%" for r in rates],
        textposition="outside",
        textfont=dict(size=10, color="#c8d0d8"),
        hovertemplate="<b>%{y}</b><br>Success rate: %{x:.1f}%<extra></extra>",
    ))
    fig.add_vline(
        x=avg,
        line=dict(color="rgba(255,255,255,0.45)", width=1.5, dash="dash"),
        annotation_text=f"Avg {avg}%",
        annotation_position="top right",
        annotation_font=dict(size=10, color="rgba(255,255,255,0.55)"),
    )
    apply_chart_theme(fig, "dark")
    fig.update_layout(
        title=dict(text="Success Rate by Entry Method", font=dict(size=13, color="white")),
        xaxis=dict(title="% Positive Outcomes", range=[0, 110],
                   gridcolor="rgba(255,255,255,0.06)", zeroline=False),
        yaxis=dict(title="", autorange="reversed", tickfont=dict(size=10)),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=max(320, len(methods) * 38),
        margin=dict(l=140, r=60, t=50, b=40),
        showlegend=False,
        bargap=0.3,
    )
    return fig


def _build_ft_timing_chart(entries: list[dict]) -> go.Figure:
    """
    Bar chart of FT entry count across 6 match-time bands (0–15, …, 75–90+),
    with a success-rate line overlay on a secondary y-axis.
    """
    _BANDS = [(0, 15), (15, 30), (30, 45), (45, 60), (60, 75), (75, 91)]
    _LABELS = ["0–15'", "15–30'", "30–45'", "45–60'", "60–75'", "75–90+'"]

    band_counts   = [0] * 6
    band_positive = [0] * 6

    for e in entries:
        try:
            minute = int(e.get("minute", 0))
        except (TypeError, ValueError):
            continue
        for i, (lo, hi) in enumerate(_BANDS):
            if lo <= minute < hi:
                band_counts[i] += 1
                if e.get("outcome") == "positive":
                    band_positive[i] += 1
                break

    rates = [
        round(band_positive[i] / band_counts[i] * 100, 1) if band_counts[i] > 0 else 0.0
        for i in range(6)
    ]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=_LABELS, y=band_counts,
        name="Entries",
        marker=dict(color=_HIGHLIGHT, opacity=0.85, line=dict(width=0)),
        hovertemplate="<b>%{x}</b><br>Entries: %{y}<extra></extra>",
        yaxis="y",
    ))
    fig.add_trace(go.Scatter(
        x=_LABELS, y=rates,
        name="Success %",
        mode="lines+markers",
        line=dict(color="#22c55e", width=2),
        marker=dict(size=6, color="#22c55e"),
        hovertemplate="<b>%{x}</b><br>Success rate: %{y:.1f}%<extra></extra>",
        yaxis="y2",
    ))
    apply_chart_theme(fig, "dark")
    fig.update_layout(
        title=dict(text="Entry Timing — Count & Success Rate by 15-min Band",
                   font=dict(size=13, color="white")),
        xaxis=dict(title="Match period", gridcolor="rgba(255,255,255,0.06)"),
        yaxis=dict(title="Entries", gridcolor="rgba(255,255,255,0.06)", zeroline=False),
        yaxis2=dict(title="Success %", overlaying="y", side="right",
                    range=[0, 110], showgrid=False, zeroline=False,
                    ticksuffix="%", tickfont=dict(color="#22c55e")),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=340,
        margin=dict(l=50, r=60, t=50, b=50),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    font=dict(size=10, color="#d0d0d0")),
        bargap=0.25,
    )
    return fig


def _build_ft_box_touches_rank(benchmarks: dict, team_name: str) -> go.Figure:
    """
    Horizontal bar chart ranking all teams by avg opponent box touches per match.
    """
    return _build_benchmark_bar(
        benchmarks,
        "ft_box_touches_per_match",
        "Opp. Box Touches / Match — All Teams",
        "Avg box touches per match",
        team_name,
    )


def _build_ft_build_depth(entries: list[dict]) -> go.Figure:
    """
    Horizontal bar chart — average passes before FT entry per method.
    Answers: how direct is each entry route?
    """
    _METHOD_ORDER = [
        "transition_recovery", "through_ball", "switch_of_play", "set_piece",
        "long_ball", "cross_delivery", "individual_carry", "short_pass",
    ]
    total_passes: dict[str, float] = {}
    counts: dict[str, int] = {}

    for e in entries:
        m = e.get("method", "short_pass")
        try:
            pb = float(e.get("passes_before", 0) or 0)
        except (TypeError, ValueError):
            pb = 0.0
        total_passes[m] = total_passes.get(m, 0.0) + pb
        counts[m]       = counts.get(m, 0) + 1

    methods, avgs, colors = [], [], []
    for m in _METHOD_ORDER:
        c = counts.get(m, 0)
        if c == 0:
            continue
        avg = round(total_passes.get(m, 0.0) / c, 1)
        methods.append(METHOD_LABELS[m])
        avgs.append(avg)
        colors.append(METHOD_COLORS[m])

    if not methods:
        fig = go.Figure()
        apply_chart_theme(fig, "dark")
        fig.update_layout(
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        return fig

    fig = go.Figure(go.Bar(
        x=avgs, y=methods,
        orientation="h",
        marker=dict(color=colors, line=dict(width=0)),
        text=[f"{v}" for v in avgs],
        textposition="outside",
        textfont=dict(size=10, color="#c8d0d8"),
        hovertemplate="<b>%{y}</b><br>Avg passes before entry: %{x:.1f}<extra></extra>",
    ))
    apply_chart_theme(fig, "dark")
    fig.update_layout(
        title=dict(text="Build-up Depth — Avg Passes Before Entry",
                   font=dict(size=13, color="white")),
        xaxis=dict(title="Avg passes before entry",
                   gridcolor="rgba(255,255,255,0.06)", zeroline=False),
        yaxis=dict(title="", autorange="reversed", tickfont=dict(size=10)),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=max(320, len(methods) * 38),
        margin=dict(l=140, r=60, t=50, b=40),
        showlegend=False,
        bargap=0.3,
    )
    return fig


def _clickable_kpi(label: str, value, subtitle: str, color: str, icon: str,
                   card_id: str) -> html.Div:
    """KPI card identical to _mini_kpi but with an id, n_clicks, and pointer cursor."""
    return html.Div(
        [
            html.Div(
                html.I(className=f"bi {icon}",
                       style={"color": color, "fontSize": "1.3rem"}),
                className="kpi-icon",
            ),
            html.Div(
                [
                    html.Span(label,       className="kpi-label"),
                    html.Span(str(value),  className="kpi-value"),
                    html.Span(subtitle,    className="kpi-subtitle",
                              style={"color": color}),
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
        id=card_id,
        n_clicks=0,
        style={"cursor": "pointer", "position": "relative"},
    )


def build_ft_section(season: str, team_name: str) -> html.Div:
    """
    Build the Final Third Entries sub-section for one team+season.

    Called by a dedicated lazy callback.
    """
    from src.analytics.season_offensive_summary import (
        compute_season_ft_entries,
        compute_league_offensive_benchmarks,
    )
    data       = compute_season_ft_entries(season, team_name)
    m          = data["metrics"]
    benchmarks = compute_league_offensive_benchmarks(season)

    cp  = m["corridor_pcts"]
    ppm = m.get("passes_per_minute", 0.0)
    pct = m.get("possession_pct", 0.0)
    bta = m.get("box_touches_per_match", 0.0)

    kpi_row = html.Div(
        [
            # 1. Possession %
            _mini_kpi("Possession %", f"{pct}%",
                      "avg ball possession per match", "#8b5cf6", "bi-pie-chart-fill"),
            # 2. Top Method — interactive dropdown card
            _build_top_method_card(m),
            # 3. Success Rate — clickable → modal with success by method
            _clickable_kpi("Success Rate", f"{m['success_rate']}%",
                           "possession retained after entry", "#22c55e",
                           "bi-check2-circle", "opp-season-ft-success-card"),
            # 4-6. Corridor cards
            _mini_kpi("Left Corridor",  f"{cp['L']}%", "of entries",
                      "#3b82f6", "bi-arrow-up"),
            _mini_kpi("Central",        f"{cp['C']}%", "of entries",
                      "#8b5cf6", "bi-align-center"),
            _mini_kpi("Right Corridor", f"{cp['R']}%", "of entries",
                      "#06b6d4", "bi-arrow-up"),
            # 7. Opp. Box Touches — clickable → modal with league ranking
            _clickable_kpi("Opp. Box Touches", f"{bta:.0f}",
                           "avg per match in penalty area", "#ef4444",
                           "bi-box-arrow-in-down-right", "opp-season-ft-boxtouches-card"),
            # 8. Tempo — clickable → modal with timing chart
            _clickable_kpi("Tempo", f"{ppm}",
                           "avg passes/min (qual. possessions)", "#f59e0b",
                           "bi-lightning-fill", "opp-season-ft-tempo-card"),
        ],
        className="team-kpi-row",
    )

    # ── Stores ────────────────────────────────────────────────────────────────
    # entries + team stored for modal callbacks (avoid re-loading parquet)
    entries_store = dcc.Store(
        id="opp-season-ft-entries-store",
        data={"entries":      data["entries"],
              "team":         team_name,
              "season":       season,
              "method_pcts":  m.get("method_pcts", {}),
              "method_counts": m.get("method_counts", {})},
    )

    # ── Modals ────────────────────────────────────────────────────────────────
    modal_method     = build_unified_modal("opp-season-ft-method-modal",
                                           "opp-season-ft-method-modal-title",
                                           "opp-season-ft-method-modal-body",
                                           title="Entry Method Breakdown")
    modal_success    = build_unified_modal("opp-season-ft-success-modal",
                                           "opp-season-ft-success-modal-title",
                                           "opp-season-ft-success-modal-body",
                                           title="Success Rate by Entry Method")
    modal_tempo      = build_unified_modal("opp-season-ft-tempo-modal",
                                           "opp-season-ft-tempo-modal-title",
                                           "opp-season-ft-tempo-modal-body",
                                           title="Entry Timing — 15-min Bands")
    modal_boxtouches = build_unified_modal("opp-season-ft-boxtouches-modal",
                                           "opp-season-ft-boxtouches-modal-title",
                                           "opp-season-ft-boxtouches-modal-body",
                                           title="Opp. Box Touches / Match — League Ranking")

    # ── Charts ────────────────────────────────────────────────────────────────
    fig_pitch   = _build_ft_zone_pitch(data["entries"])
    fig_scatter = _build_ft_entry_scatter(data["entries"])

    return html.Div(
        [
            _section_header(
                "Build-up to Final Third — Season Aggregate",
                "bi-box-arrow-in-right",
                eyebrow="Opponent — Final Third",
                subtitle="Entry methods, zones, timing and league benchmarks",
            ),
            entries_store,
            modal_method,
            modal_success,
            modal_tempo,
            modal_boxtouches,
            kpi_row,
            _two_col(
                # pitch-dark-container: dark pitches stay dark in light mode
                # (skip-list convention; Phase 4 audit fix)
                html.Div(
                    dcc.Graph(
                        id="opp-season-ft-zone-pitch",
                        figure=fig_pitch,
                        config={"displayModeBar": False},
                    ),
                    className="pitch-dark-container",
                ),
                html.Div(
                    dcc.Graph(
                        id="opp-season-ft-entry-scatter",
                        figure=fig_scatter,
                        config={"displayModeBar": False},
                    ),
                    className="pitch-dark-container",
                ),
            ),
        ],
        className="analysis-section buildup-card ma-card",
        style={"marginBottom": "2rem", "padding": "1.5rem"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SUB-SECTION 3 — CHANCE CREATION  (lazy)
# ═══════════════════════════════════════════════════════════════════════════════

# Origin colour palette for Goal Types chart (reuses ORIGIN_COLORS from chance_creation_cards)
_CC_ORIGIN_ORDER = [
    "Set Piece", "High Regain", "Cross", "Through Ball",
    "Cut Back", "Individual Play", "Combination",
]


def _build_cc_xg_bar(benchmarks: dict, team_name: str) -> go.Figure:
    """Horizontal bar ranking all teams by xG/match. Reused by modal callback."""
    return _build_benchmark_bar(
        benchmarks, "xg_per_match",
        "xG per Match — All Teams",
        "xG per match", team_name,
    )


def _build_goal_types_chart(shots: list, team_name: str, season: str) -> go.Figure:
    """
    Horizontal bar chart of goals by attack origin for the selected team/season.
    Bars sorted descending by goal count; each labelled with count and %.
    """
    from src.components.chance_creation_cards import ORIGIN_COLORS

    goal_counts: dict[str, int] = {}
    for s in shots:
        if s.get("is_goal"):
            origin = s.get("origin", "Combination")
            goal_counts[origin] = goal_counts.get(origin, 0) + 1

    if not goal_counts:
        fig = go.Figure()
        apply_chart_theme(fig, "dark")
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            annotations=[dict(
                text="No goal data available for this selection.",
                x=0.5, y=0.5, xref="paper", yref="paper",
                showarrow=False, font=dict(size=14, color="#8899aa"),
            )],
            height=220,
            margin=dict(l=10, r=10, t=40, b=10),
        )
        return fig

    total_goals = sum(goal_counts.values())
    # Sort descending by count, preserving canonical order for ties
    sorted_origins = sorted(
        [o for o in _CC_ORIGIN_ORDER if goal_counts.get(o, 0) > 0],
        key=lambda o: goal_counts[o],
        reverse=True,
    )

    counts = [goal_counts[o] for o in sorted_origins]
    pcts   = [round(goal_counts[o] / total_goals * 100) for o in sorted_origins]
    colors = [ORIGIN_COLORS.get(o, "#3b82f6") for o in sorted_origins]
    labels = [f"{c}  ({p}%)" for c, p in zip(counts, pcts)]

    season_label = season.replace("_", "/")
    fig = go.Figure(go.Bar(
        x=counts,
        y=sorted_origins,
        orientation="h",
        marker=dict(color=colors, line=dict(width=0)),
        text=labels,
        textposition="outside",
        textfont=dict(size=11, color="#c8d0d8"),
        hovertemplate="<b>%{y}</b><br>Goals: %{x}<extra></extra>",
    ))
    apply_chart_theme(fig, "dark")
    fig.update_layout(
        title=dict(
            text=f"Goals by Origin — {team_name} {season_label}",
            font=dict(size=13, color="white"),
        ),
        xaxis=dict(
            title="Goals",
            gridcolor="rgba(255,255,255,0.06)",
            zeroline=False,
        ),
        yaxis=dict(title="", autorange="reversed", tickfont=dict(size=11)),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=max(280, len(sorted_origins) * 44 + 80),
        margin=dict(l=130, r=90, t=50, b=40),
        showlegend=False,
        bargap=0.3,
    )
    return fig


def build_cc_section(season: str, team_name: str) -> html.Div:
    """
    Build the Chance Creation sub-section for one team+season.

    Called by a dedicated lazy callback.
    """
    from src.analytics.season_offensive_summary import (
        compute_season_chance_creation,
        compute_league_offensive_benchmarks,
    )
    from src.components.chance_creation_cards import ORIGIN_COLORS, ORIGIN_ICONS

    data = compute_season_chance_creation(season, team_name)
    m    = data["metrics"]
    benchmarks = compute_league_offensive_benchmarks(season)

    top_origin = m["top_origin"]
    top_origin_color = ORIGIN_COLORS.get(top_origin, PRIMARY_COLOR)
    top_origin_icon  = ORIGIN_ICONS.get(top_origin, "bi-lightning-charge")

    # ── xG Total KPI card — clickable (opens xG league bar modal) ──────────
    xg_kpi_card = html.Div(
        [
            html.Div(
                html.I(className="bi bi-graph-up-arrow",
                       style={"color": "#8b5cf6", "fontSize": "1.3rem"}),
                className="kpi-icon",
            ),
            html.Div(
                [
                    html.Span("xG Total", className="kpi-label"),
                    html.Span(f"{m['xg_total']:.2f}", className="kpi-value"),
                    html.Span(f"{m['xg_per_match']:.2f} xG/match",
                              className="kpi-subtitle",
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
        id="opp-season-cc-xg-card",
        n_clicks=0,
        style={"cursor": "pointer", "position": "relative",
               "transition": "box-shadow 0.15s ease"},
    )

    # ── Top Origin KPI card — clickable (opens Goal Types modal) ───────────
    top_origin_card = html.Div(
        [
            html.Div(
                html.I(className=f"bi {top_origin_icon}",
                       style={"color": top_origin_color, "fontSize": "1.3rem"}),
                className="kpi-icon",
            ),
            html.Div(
                [
                    html.Span("Top Origin", className="kpi-label"),
                    html.Span(top_origin, className="kpi-value"),
                    html.Span("most frequent attack type",
                              className="kpi-subtitle",
                              style={"color": top_origin_color}),
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
        id="opp-season-cc-origin-card",
        n_clicks=0,
        style={"cursor": "pointer", "position": "relative",
               "transition": "box-shadow 0.15s ease"},
    )

    kpi_row = html.Div(
        [
            _mini_kpi("Total Chances", m["total_shots"],
                      f"{m['shots_per_match']}/match", "#3b82f6", "bi-crosshair"),
            _mini_kpi("Goals", m["goals"],
                      f"SoT: {m['on_target']}  ({m['sot_pct']}%)",
                      "#22c55e", "bi-trophy-fill"),
            xg_kpi_card,
            top_origin_card,
            _mini_kpi("Matches", data["matches"], "analysed",
                      "#8899aa", "bi-calendar3"),
        ],
        className="team-kpi-row",
    )

    # ── xG modal ───────────────────────────────────────────────────────────
    # Persistent Graph body: a second callback fills the figure when is_open
    # flips (two-callback populate pattern), so the Graph must live in the
    # layout permanently rather than being callback-injected.
    xg_modal = build_unified_modal(
        "opp-season-cc-xg-modal",
        "opp-season-cc-xg-modal-title",
        "opp-season-cc-xg-modal-body",
        title="xG per Match — All Teams",
        size="xl",
        body=dcc.Graph(
            id="opp-season-cc-xg-modal-graph",
            style={"height": "520px"},
            config={"displayModeBar": False},
        ),
    )

    # ── Goal Types modal — chart + origin table ────────────────────────────
    # Build the "Chances Created by Attack Origin" table from origin_data,
    # which is already computed at render time. Sorted descending by total.
    from src.analytics.chance_creation import ORIGIN_LABELS as _GT_ORIGIN_LABELS
    _gt_od = m.get("origin_data", {})
    _gt_rows_data = sorted(
        [
            (o, _gt_od.get(o, {}))
            for o in _GT_ORIGIN_LABELS
            if _gt_od.get(o, {}).get("total", 0) > 0
        ],
        key=lambda x: x[1].get("total", 0),
        reverse=True,
    )

    _gt_header = html.Div(
        [
            html.Span("Origin",          style={"flex": "1",          "color": "#8899aa", "fontSize": "0.75rem"}),
            html.Span("Total",           style={"minWidth": "3.5rem", "textAlign": "right", "color": "#8899aa", "fontSize": "0.75rem"}),
            html.Span("/ Match",         style={"minWidth": "3.5rem", "textAlign": "right", "color": "#8899aa", "fontSize": "0.75rem"}),
            html.Span("Goals",           style={"minWidth": "3rem",   "textAlign": "right", "color": "#8899aa", "fontSize": "0.75rem"}),
            html.Span("Conv %",          style={"minWidth": "4rem",   "textAlign": "right", "color": "#8899aa", "fontSize": "0.75rem"}),
        ],
        style={"display": "flex", "padding": "6px 10px",
               "borderBottom": "1px solid rgba(255,255,255,0.15)", "marginBottom": "2px"},
    )
    _gt_table_rows = []
    for _o, _info in _gt_rows_data:
        _cnt  = _info.get("total", 0)
        _pm   = _info.get("per_match", 0.0)
        _g    = _info.get("goals_total", 0)
        _conv = _info.get("conversion_pct")
        _conv_str = f"{_conv:.1f}%" if _conv is not None else "—"
        _gt_table_rows.append(
            html.Div(
                [
                    html.Span(_o,           style={"flex": "1",          "fontSize": "0.88rem", "color": "var(--text-primary)"}),
                    html.Span(str(_cnt),    style={"minWidth": "3.5rem", "textAlign": "right",  "fontSize": "0.88rem", "color": "var(--text-secondary)"}),
                    html.Span(f"{_pm:.1f}", style={"minWidth": "3.5rem", "textAlign": "right",  "fontSize": "0.88rem", "color": "var(--text-secondary)"}),
                    html.Span(str(_g),      style={"minWidth": "3rem",   "textAlign": "right",  "fontSize": "0.88rem", "color": "var(--text-secondary)"}),
                    html.Span(_conv_str,    style={"minWidth": "4rem",   "textAlign": "right",  "fontSize": "0.9rem",  "fontWeight": "600", "color": "var(--text-primary)"}),
                ],
                style={"display": "flex", "padding": "6px 10px",
                       "borderBottom": "1px solid rgba(255,255,255,0.05)",
                       "alignItems": "center"},
            )
        )

    _gt_origin_table = html.Div(
        [
            html.H6("Chances Created by Attack Origin",
                    style={"color": "var(--text-secondary)", "fontSize": "0.82rem",
                           "marginBottom": "0.5rem", "marginTop": "1.25rem",
                           "textTransform": "uppercase", "letterSpacing": "0.05em"}),
            html.Div(
                [_gt_header, *_gt_table_rows],
                style={"borderRadius": "6px", "border": "1px solid rgba(255,255,255,0.07)"},
            ),
        ],
    )

    goal_types_modal = build_unified_modal(
        "opp-season-cc-goal-types-modal",
        "opp-season-cc-goal-types-modal-title",
        "opp-season-cc-goal-types-modal-body",
        title="Goal Types — Season",
        body=html.Div([
            dcc.Graph(
                id="opp-season-cc-goal-types-graph",
                style={"height": "400px"},
                config={"displayModeBar": False},
            ),
            _gt_origin_table,
        ]),
    )

    # ── Attack Origin Breakdown — per-origin cards with goals + conversion ──
    from src.analytics.chance_creation import ORIGIN_LABELS as _ORIGIN_LABELS
    from src.components.chance_creation_cards import (
        extract_penalty_stats,
        set_piece_count_excl_penalties,
        penalty_origin_card,
        ORIGIN_COLORS as _CC_ORIGIN_COLORS,
        ORIGIN_ICONS  as _CC_ORIGIN_ICONS,
    )

    # Penalty stats derived from shot-level list (carries is_penalty after re-run)
    _shots_list   = data.get("shots", [])
    _pen_stats    = extract_penalty_stats(_shots_list)
    _sp_excl_cnt  = set_piece_count_excl_penalties(_shots_list)

    _origin_data = m.get("origin_data", {})
    _origin_cards = []
    for _o in _ORIGIN_LABELS:
        _info = _origin_data.get(_o, {})
        _cnt  = _info.get("total", 0)
        # For Set Piece, replace the raw total with penalty-excluded count
        if _o == "Set Piece":
            _cnt = _sp_excl_cnt
        if _cnt == 0:
            continue
        _pm        = _info.get("per_match", 0.0)
        _goals     = _info.get("goals_total", 0)
        _conv      = _info.get("conversion_pct")
        _oc        = _CC_ORIGIN_COLORS.get(_o, "#6b7280")
        _oi        = _CC_ORIGIN_ICONS.get(_o, "bi-activity")

        _conv_line = (
            html.Span(
                f"{_goals} goals ({_conv:.1f}% conversion)",
                className="kpi-subtitle",
                style={"color": "var(--text-muted)", "fontSize": "0.72rem"},
            )
            if _conv is not None else None
        )
        _origin_cards.append(
            html.Div(
                [
                    html.Div(
                        html.I(className=f"bi {_oi}",
                               style={"color": _oc, "fontSize": "1.3rem"}),
                        className="kpi-icon",
                    ),
                    html.Div(
                        [
                            html.Span(_o, className="kpi-label"),
                            html.Span(f"{_pm:.1f}", className="kpi-value"),
                            html.Span(f"Total: {_cnt}",
                                      className="kpi-subtitle",
                                      style={"color": _oc}),
                            *([] if _conv_line is None else [_conv_line]),
                        ],
                        className="kpi-text",
                    ),
                ],
                className="kpi-card",
            )
        )

    # Penalty card appended last — no component ID (matches pattern of other cards here)
    _origin_cards.append(penalty_origin_card(
        awarded=_pen_stats["awarded"],
        scored=_pen_stats["scored"],
        conversion_rate=_pen_stats["conversion_rate"],
    ))

    attack_origin_breakdown_div = html.Div(
        [
            html.H6("ATTACK ORIGIN BREAKDOWN", className="buildup-subsection-title"),
            html.Div(
                "How each chance was created — priority: "
                "Through Ball → Set Piece → Individual Play → High Regain → Cut Back → Cross → Combination · Penalty",
                style={"fontSize": "0.78rem", "color": "var(--text-muted)",
                       "marginBottom": "0.6rem"},
            ),
            html.Div(_origin_cards, className="team-kpi-row",
                     style={"flexWrap": "wrap"}),
        ],
        style={"marginTop": "1.5rem"},
    )

    # ── Attack Origin Zones — Season Aggregate ────────────────────────────
    _AOZ_X_EDGES = [0, 16.67, 33.33, 50.0, 66.67, 83.33, 100.0]
    _AOZ_Y_EDGES = [0, 33.33, 66.67, 100.0]
    _AOZ_N_COLS  = 3

    def _classify_18zone(x: float, y: float) -> int:
        row = min(int(x / 16.67), 5)
        col = min(int(y / 33.33), 2)
        return row * 3 + col + 1

    zone_pos: dict[int, int] = {z: 0 for z in range(1, 19)}
    zone_neg: dict[int, int] = {z: 0 for z in range(1, 19)}
    for s in data["shots"]:
        z = _classify_18zone(float(s.get("x", 0)), float(s.get("y", 50)))
        if s.get("is_goal") or s.get("on_target"):
            zone_pos[z] += 1
        else:
            zone_neg[z] += 1

    fig_zones = go.Figure()

    max_count = max((zone_pos[z] + zone_neg[z] for z in range(1, 19)), default=1) or 1

    for zone_num in range(1, 19):
        row = (zone_num - 1) // _AOZ_N_COLS
        col = (zone_num - 1) % _AOZ_N_COLS
        x0 = _AOZ_X_EDGES[row];  x1 = _AOZ_X_EDGES[row + 1]
        y0 = _AOZ_Y_EDGES[col];  y1 = _AOZ_Y_EDGES[col + 1]
        cx = (x0 + x1) / 2;      cy = (y0 + y1) / 2

        pos   = zone_pos[zone_num]
        neg   = zone_neg[zone_num]
        total = pos + neg
        intensity = total / max_count if max_count else 0
        fill_a = 0.08 + 0.50 * intensity if total else 0.04
        fill   = f"rgba(138, 31, 51, {fill_a:.2f})"

        fig_zones.add_shape(
            type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
            line=dict(color="rgba(255,255,255,0.10)", width=0.5),
            fillcolor=fill, layer="below",
        )

        if total > 0:
            fig_zones.add_annotation(
                x=cx, y=cy + 4, text=f"<b>{total}</b>", showarrow=False,
                font=dict(size=16, color="#f0f0f0"),
            )
            fig_zones.add_annotation(
                x=cx, y=cy - 4, text=f"Z{zone_num}", showarrow=False,
                font=dict(size=9, color="rgba(255,255,255,0.55)"),
            )
            dot_parts: list[str] = []
            if pos > 0:
                dot_parts.append(f"<span style='color:#22c55e'>●{pos}</span>")
            if neg > 0:
                dot_parts.append(f"<span style='color:#ef4444'>●{neg}</span>")
            if dot_parts:
                fig_zones.add_annotation(
                    x=cx, y=cy - 12, text=" ".join(dot_parts), showarrow=False,
                    font=dict(size=10),
                )
        else:
            fig_zones.add_annotation(
                x=cx, y=cy, text=f"Z{zone_num}", showarrow=False,
                font=dict(size=9, color="rgba(255,255,255,0.18)"),
            )

    # Corridor dividers
    for y_val in (33.33, 66.67):
        fig_zones.add_shape(
            type="line", x0=0, x1=100, y0=y_val, y1=y_val,
            line=dict(color="rgba(255,255,255,0.12)", width=1), layer="below",
        )
    for x_val in _AOZ_X_EDGES[1:-1]:
        fig_zones.add_shape(
            type="line", x0=x_val, x1=x_val, y0=0, y1=100,
            line=dict(color="rgba(255,255,255,0.12)", width=1), layer="below",
        )

    # Pitch outline, halfway line, penalty areas
    fig_zones.add_shape(
        type="rect", x0=0, x1=100, y0=0, y1=100,
        line=dict(color="rgba(255,255,255,0.35)", width=1.5),
        fillcolor="rgba(0,0,0,0)",
    )
    fig_zones.add_shape(
        type="line", x0=50, x1=50, y0=0, y1=100,
        line=dict(color="rgba(255,255,255,0.25)", width=1, dash="dash"),
        layer="below",
    )
    fig_zones.add_shape(
        type="rect", x0=0, x1=16.5, y0=21, y1=79,
        line=dict(color="rgba(255,255,255,0.18)", width=1),
        fillcolor="rgba(0,0,0,0)",
    )
    fig_zones.add_shape(
        type="rect", x0=83.5, x1=100, y0=21, y1=79,
        line=dict(color="rgba(255,255,255,0.18)", width=1),
        fillcolor="rgba(0,0,0,0)",
    )
    fig_zones.add_shape(
        type="line", x0=66.67, x1=66.67, y0=0, y1=100,
        line=dict(color="rgba(255,255,255,0.6)", width=2, dash="dash"),
    )
    fig_zones.add_annotation(
        x=92, y=-6, text="ATK →", showarrow=False,
        font=dict(size=9, color="rgba(255,255,255,0.35)"),
    )
    fig_zones.add_annotation(
        x=8, y=-6, text="← OWN GOAL", showarrow=False,
        font=dict(size=9, color="rgba(255,255,255,0.35)"),
    )

    apply_chart_theme(fig_zones, "dark")
    fig_zones.update_layout(
        plot_bgcolor="rgba(15,25,35,0.7)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=10, b=20),
        height=400,
        xaxis=dict(range=[-2, 102], showgrid=False, showticklabels=False,
                   fixedrange=True, zeroline=False),
        yaxis=dict(range=[-10, 105], showgrid=False, showticklabels=False,
                   fixedrange=True, zeroline=False,
                   scaleanchor="x", scaleratio=0.68),
        showlegend=False,
    )

    attack_origin_zones_div = html.Div(
        [
            html.H6("Attack Origin Zones", className="buildup-subsection-title"),
            html.Div(
                [
                    html.Span("● ", style={"color": "#22c55e", "fontSize": "0.85rem"}),
                    html.Span("on target / goal", style={
                        "fontSize": "0.75rem", "color": "var(--text-muted)",
                        "marginRight": "1rem",
                    }),
                    html.Span("● ", style={"color": "#ef4444", "fontSize": "0.85rem"}),
                    html.Span("miss / block", style={
                        "fontSize": "0.75rem", "color": "var(--text-muted)",
                    }),
                ],
                style={"marginBottom": "0.5rem"},
            ),
            html.Div(
                dcc.Graph(figure=fig_zones, config={"displayModeBar": False}),
                className="pitch-dark-container",
            ),
        ],
        style={"marginTop": "1.5rem"},
    )

    return html.Div(
        [
            _section_header(
                "Chance Creation — Season Aggregate",
                "bi-lightning-charge-fill",
                eyebrow="Opponent — Chance Creation",
                subtitle="Shot volume, xG benchmarks, goals by origin and "
                         "attack origin zones",
            ),
            xg_modal,
            goal_types_modal,
            kpi_row,
            attack_origin_breakdown_div,
            attack_origin_zones_div,
        ],
        className="analysis-section buildup-card ma-card",
        style={"marginBottom": "2rem", "padding": "1.5rem"},
    )
