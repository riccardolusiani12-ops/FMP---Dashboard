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
from dash import dcc, html, Input, Output, State, no_update

from src.config import PRIMARY_COLOR
from src.components.final_third_pitch import (
    METHOD_COLORS,
    METHOD_LABELS,
    OUTCOME_COLORS,
    _draw_pitch_base,
    _base_layout,
)

# ─── Shared colour constants (mirror ppda.py) ─────────────────────────────────
_NEUTRAL   = "#4a6274"
_HIGHLIGHT = PRIMARY_COLOR  # "#8a1f33"

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


def _section_header(title: str, icon: str) -> html.Div:
    """Sub-section header consistent with match-analysis card headers."""
    return html.Div(
        [
            html.I(className=f"bi {icon} me-2",
                   style={"color": "var(--primary-light)", "fontSize": "1.1rem"}),
            html.Span(title, className="buildup-section-title"),
        ],
        className="buildup-section-header",
        style={"marginBottom": "1rem"},
    )


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

    header = html.Div(
        [
            html.I(className="bi bi-lightning-charge-fill me-2",
                   style={"color": "var(--primary-light)", "fontSize": "1.2rem"}),
            html.H5(
                f"Offensive Phase Overview — {team_name}  ({season_label})",
                className="mb-0",
                style={"color": "var(--text-primary)", "fontWeight": "600"},
            ),
        ],
        className="d-flex align-items-center mb-4",
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
        fig.update_layout(
            template="plotly_dark", title=title,
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        )
        return fig

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
    fig.add_vline(
        x=avg_val,
        line=dict(color="rgba(255,255,255,0.45)", width=1.5, dash="dash"),
        annotation_text=f"Avg {avg_val:.2f}",
        annotation_position="top right",
        annotation_font=dict(size=10, color="rgba(255,255,255,0.55)"),
    )
    fig.update_layout(
        template="plotly_dark",
        title=dict(text=title, font=dict(size=14, color="white")),
        xaxis=dict(title=x_label, gridcolor="rgba(255,255,255,0.06)", zeroline=False),
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
            # Short Pass % card with expand toggle
            html.Div(
                [
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
                        ],
                        style={"display": "flex", "alignItems": "center", "flex": "1"},
                    ),
                    html.Span(
                        html.I(className="bi bi-graph-up",
                               style={"fontSize": "0.85rem"}),
                        id="opp-season-gk-short-toggle",
                        n_clicks=0,
                        title="Show outcome breakdown",
                        style={
                            "cursor": "pointer", "padding": "3px 6px",
                            "borderRadius": "12px",
                            "background": "rgba(34,197,94,0.12)",
                            "color": "#22c55e",
                            "display": "inline-flex", "alignItems": "center",
                            "alignSelf": "flex-start",
                        },
                    ),
                ],
                className="kpi-card",
                style={"display": "flex", "alignItems": "center", "gap": "6px",
                       "flexWrap": "nowrap"},
            ),
            # Long Ball % card with expand toggle
            html.Div(
                [
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
                        ],
                        style={"display": "flex", "alignItems": "center", "flex": "1"},
                    ),
                    html.Span(
                        html.I(className="bi bi-graph-up",
                               style={"fontSize": "0.85rem"}),
                        id="opp-season-gk-long-toggle",
                        n_clicks=0,
                        title="Show outcome breakdown",
                        style={
                            "cursor": "pointer", "padding": "3px 6px",
                            "borderRadius": "12px",
                            "background": "rgba(249,115,22,0.12)",
                            "color": "#f97316",
                            "display": "inline-flex", "alignItems": "center",
                            "alignSelf": "flex-start",
                        },
                    ),
                ],
                className="kpi-card",
                style={"display": "flex", "alignItems": "center", "gap": "6px",
                       "flexWrap": "nowrap"},
            ),
        ],
        className="team-kpi-row",
    )

    # Inline radar charts (hidden by default, toggled by callbacks)
    short_radar_fig = _build_outcome_radar(m["short_granular_counts"], "short")
    long_radar_fig  = _build_outcome_radar(m["long_granular_counts"],  "long")

    radar_row = html.Div(
        [
            # Short Pass radar panel
            html.Div(
                dcc.Graph(
                    id="opp-season-gk-short-radar",
                    figure=short_radar_fig,
                    config={"displayModeBar": False},
                    style={"display": "none"},
                ),
                id="opp-season-gk-short-radar-wrap",
                style={"flex": "1", "minWidth": "0"},
            ),
            # Long Ball radar panel
            html.Div(
                dcc.Graph(
                    id="opp-season-gk-long-radar",
                    figure=long_radar_fig,
                    config={"displayModeBar": False},
                    style={"display": "none"},
                ),
                id="opp-season-gk-long-radar-wrap",
                style={"flex": "1", "minWidth": "0"},
            ),
        ],
        id="opp-season-gk-radar-row",
        style={"display": "none", "gap": "1.5rem", "marginTop": "0.5rem"},
    )

    # Stores for toggle state
    stores = html.Div(
        [
            dcc.Store(id="opp-season-gk-short-open", data=False),
            dcc.Store(id="opp-season-gk-long-open",  data=False),
        ]
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
            _section_header("GK Build-up — Season Aggregate", "bi-person-fill"),
            stores,
            kpi_row,
            radar_row,
            _two_col(
                dcc.Graph(figure=fig_pitch, config={"displayModeBar": False}),
                bench_panel,
            ),
        ],
        className="analysis-section",
        style={"marginBottom": "2rem"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SUB-SECTION 2 — FINAL THIRD ENTRIES  (lazy)
# ═══════════════════════════════════════════════════════════════════════════════

# Human-readable labels for the Top Method dropdown (excl. short_pass)
_FT_METHOD_LABELS = {
    "transition_recovery": "Transition / Recovery",
    "through_ball":        "Through Ball",
    "switch_of_play":      "Switch of Play",
    "set_piece":           "Set-Piece",
    "long_ball":           "Long Ball",
    "cross_delivery":      "Cross Delivery",
    "individual_carry":    "Individual Carry",
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
    KPI card for Top Method (excl. Short Pass) with an embedded dropdown
    that lets the user inspect any other method's frequency.

    Default: second-most-common method excluding short_pass.
    Dropdown: all methods with non-zero count, excluding short_pass,
              sorted descending by frequency, with % shown in label.

    Component IDs: opp-season-ft-method-dropdown, opp-season-ft-method-value,
                   opp-season-ft-method-subtitle.
    """
    method_counts = m.get("method_counts", {})
    method_pcts   = m.get("method_pcts",   {})
    default_key   = m.get("top_method_excl_short", "individual_carry")

    # Build dropdown options: all non-short_pass methods with count > 0,
    # sorted descending by frequency
    options = []
    for key, count in sorted(method_counts.items(), key=lambda x: x[1], reverse=True):
        if key == "short_pass" or count == 0:
            continue
        pct = method_pcts.get(key, 0.0)
        label = _FT_METHOD_LABELS.get(key, key)
        options.append({"label": f"{label} — {pct}%", "value": key})

    if not options:
        # Fallback: no data
        return _mini_kpi(
            "Top Method (excl. Short Pass)", "—", "no data",
            "#8899aa", "bi-bar-chart-fill",
        )

    default_pct = method_pcts.get(default_key, 0.0)
    default_label = _FT_METHOD_LABELS.get(default_key, default_key)
    default_color = METHOD_COLORS.get(default_key, "#8a1f33")

    return html.Div(
        [
            html.Div(
                html.I(className="bi bi-bar-chart-fill",
                       style={"color": default_color, "fontSize": "1.3rem"}),
                className="kpi-icon",
                id="opp-season-ft-method-icon",
            ),
            html.Div(
                [
                    html.Span("Top Method (excl. Short Pass)", className="kpi-label"),
                    html.Span(
                        id="opp-season-ft-method-value",
                        children=f"{default_pct}%",
                        className="kpi-value",
                    ),
                    dcc.Dropdown(
                        id="opp-season-ft-method-dropdown",
                        options=options,
                        value=default_key,
                        clearable=False,
                        searchable=False,
                        style={
                            "fontSize": "0.72rem",
                            "marginTop": "4px",
                            "backgroundColor": "rgba(15,25,35,0.9)",
                            "color": "#d0d0d0",
                            "border": "1px solid rgba(255,255,255,0.12)",
                            "borderRadius": "6px",
                        },
                        className="opp-ft-method-select",
                    ),
                ],
                className="kpi-text",
            ),
        ],
        className="kpi-card",
        id="opp-season-ft-method-card",
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
    data = compute_season_ft_entries(season, team_name)
    m    = data["metrics"]
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
            # 2. Top Method (excl. Short Pass) — interactive dropdown card
            _build_top_method_card(m),
            # 3. Success Rate
            _mini_kpi("Success Rate", f"{m['success_rate']}%",
                      "possession retained after entry", "#22c55e", "bi-check2-circle"),
            # 4-6. Corridor cards
            _mini_kpi("Left Corridor",  f"{cp['L']}%", "of entries",
                      "#3b82f6", "bi-arrow-up"),
            _mini_kpi("Central",        f"{cp['C']}%", "of entries",
                      "#8b5cf6", "bi-align-center"),
            _mini_kpi("Right Corridor", f"{cp['R']}%", "of entries",
                      "#06b6d4", "bi-arrow-up"),
            # 7. Opp. Box Touches
            _mini_kpi("Opp. Box Touches", f"{bta:.0f}",
                      "avg per match in penalty area", "#ef4444", "bi-box-arrow-in-down-right"),
            # 8. Tempo
            _mini_kpi("Tempo", f"{ppm}",
                      "avg passes/min (qual. possessions)", "#f59e0b", "bi-lightning-fill"),
        ],
        className="team-kpi-row",
    )

    # Store the method_pcts data for the dropdown callback
    method_store = dcc.Store(
        id="opp-season-ft-method-store",
        data={"method_pcts": m.get("method_pcts", {}),
              "method_counts": m.get("method_counts", {})},
    )

    fig_pitch = _build_ft_zone_pitch(data["entries"])
    fig_bench = _build_benchmark_bar(
        benchmarks, "ft_per_match",
        "Final Third Entries / Match — All Teams",
        "Entries per match", team_name,
    )

    return html.Div(
        [
            _section_header("Build-up to Final Third — Season Aggregate",
                            "bi-box-arrow-in-right"),
            method_store,
            kpi_row,
            _two_col(
                dcc.Graph(
                    id="opp-season-ft-zone-pitch",
                    figure=fig_pitch,
                    config={"displayModeBar": False},
                ),
                dcc.Graph(figure=fig_bench, config={"displayModeBar": False}),
            ),
        ],
        className="analysis-section",
        style={"marginBottom": "2rem"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SUB-SECTION 3 — CHANCE CREATION  (lazy)
# ═══════════════════════════════════════════════════════════════════════════════

# Tier colours / labels
_TIER_COLORS = {3: "#22c55e", 2: "#f97316", 0: "#6b7280"}
_TIER_LABELS = {3: "Goal", 2: "Big Chance", 0: "Speculative"}


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
    kpi_row = html.Div(
        [
            _mini_kpi("Total Chances", m["total_shots"],
                      f"{m['shots_per_match']}/match", "#3b82f6", "bi-crosshair"),
            _mini_kpi("Goals", m["goals"],
                      f"SoT: {m['on_target']}  ({m['sot_pct']}%)",
                      "#22c55e", "bi-trophy-fill"),
            _mini_kpi("xG Total", f"{m['xg_total']:.2f}",
                      f"{m['xg_per_match']:.2f} xG/match",
                      "#8b5cf6", "bi-graph-up-arrow"),
            _mini_kpi("Top Origin", top_origin, "most frequent attack type",
                      ORIGIN_COLORS.get(top_origin, PRIMARY_COLOR),
                      ORIGIN_ICONS.get(top_origin, "bi-lightning-charge")),
            _mini_kpi("Matches", data["matches"], "analysed",
                      "#8899aa", "bi-calendar3"),
        ],
        className="team-kpi-row",
    )

    # Shot scatter (attacking half)
    fig_pitch = go.Figure()
    for tier in (3, 2, 0):
        pts = [s for s in data["shots"] if s.get("quality_tier") == tier]
        if pts:
            fig_pitch.add_trace(go.Scatter(
                x=[float(s.get("x", 0)) for s in pts],
                y=[float(s.get("y", 50)) for s in pts],
                mode="markers",
                name=_TIER_LABELS[tier],
                marker=dict(color=_TIER_COLORS[tier], size=8, opacity=0.8,
                            line=dict(color="rgba(255,255,255,0.3)", width=0.5)),
                hovertemplate=(
                    f"<b>{_TIER_LABELS[tier]}</b><br>"
                    "xG: %{text}<br>x=%{x:.1f}, y=%{y:.1f}<extra></extra>"
                ),
                text=[f"{s.get('xG', 0.0):.3f}" for s in pts],
            ))
    _draw_pitch_base(fig_pitch, draw_zones=False)
    _base_layout(fig_pitch, "Shots — Season (by quality tier)", height=400, show_legend=True)
    fig_pitch.update_layout(
        xaxis=dict(range=[48, 102], showgrid=False, zeroline=False,
                   showticklabels=False, fixedrange=True),
        legend=dict(orientation="v", yanchor="middle", y=0.5, xanchor="left", x=1.01,
                    font=dict(size=10, color="#d0d0d0"),
                    bgcolor="rgba(15,25,35,0.8)",
                    bordercolor="rgba(255,255,255,0.1)", borderwidth=1),
        margin=dict(l=10, r=110, t=40, b=20),
    )

    fig_bench = _build_benchmark_bar(
        benchmarks, "xg_per_match",
        "xG / Match — All Teams",
        "xG per match", team_name,
    )

    return html.Div(
        [
            _section_header("Chance Creation — Season Aggregate",
                            "bi-lightning-charge-fill"),
            kpi_row,
            _two_col(
                dcc.Graph(figure=fig_pitch, config={"displayModeBar": False}),
                dcc.Graph(figure=fig_bench, config={"displayModeBar": False}),
            ),
        ],
        className="analysis-section",
        style={"marginBottom": "2rem"},
    )
