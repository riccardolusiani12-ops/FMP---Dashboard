"""
Team Detail Page — KPIs and charts for a selected team.

Routes: /serie-a/team/<team-slug>
"""

import dash_bootstrap_components as dbc
from dash import dcc, html

from src.styling.ui_components import build_unified_modal

from src.config import AVAILABLE_SEASONS


def _ds_header(eyebrow: str, icon: str, title: str, subtitle: str) -> html.Div:
    """House-style card header: uppercase eyebrow + icon, bold title, muted subtitle."""
    return html.Div(
        [
            html.Div(
                [html.I(className=f"bi {icon}"), html.Span(eyebrow)],
                className="ds-eyebrow",
            ),
            html.H4(title, className="ds-title"),
            html.P(subtitle, className="ds-sub"),
        ],
        className="ds-header",
    )


def layout(team_name: str = "", season: str = "") -> html.Div:
    """Return the team detail page layout."""
    # Default to the latest season
    default_season = season if season else (
        AVAILABLE_SEASONS[-1] if AVAILABLE_SEASONS else "2025_2026"
    )
    season_options = [
        {"label": s.replace("_", "/"), "value": s}
        for s in AVAILABLE_SEASONS
    ]

    return html.Div(
        [
            # Page header: Back | Logo | Team name
            html.Div(
                [
                    html.A(
                        [
                            html.I(className="bi bi-arrow-left me-2"),
                            "Back to teams",
                        ],
                        href="/serie-a",
                        className="back-button",
                    ),
                    html.Div(
                        [
                            html.Img(
                                id="team-detail-logo",
                                className="team-detail-logo",
                            ),
                            html.H2(
                                team_name or "Team",
                                id="team-detail-name",
                                className="page-title mb-0",
                            ),
                        ],
                        className="team-detail-header-info",
                    ),
                    # Hidden season store — season pills and URL param write here;
                    # all detail-page callbacks read from this single source of truth.
                    dcc.Dropdown(
                        id="team-season-selector",
                        options=season_options,
                        value=default_season,
                        clearable=False,
                        style={"display": "none"},
                    ),
                ],
                className="page-header team-detail-page-header",
            ),

            # Hidden store for team context
            dcc.Store(id="team-context", data={"team": team_name, "season": default_season}),

            # KPI summary row (dynamic)
            html.Div(id="team-kpi-row", className="team-kpi-row"),

            # Chart sections
            html.Div(
                [
                    # Section: Points Progression
                    html.Div(
                        [
                            _ds_header(
                                "Season Trends", "bi-graph-up",
                                "Points Progression",
                                "Cumulative points by matchday — all seasons, "
                                "selected season highlighted",
                            ),
                            # Season selector pills (mirror the header dropdown)
                            html.Div(
                                id="season-pills-row",
                                className="season-pills-row",
                            ),
                            dcc.Loading(
                                dcc.Graph(
                                    id="standings-chart",
                                    config={
                                        "displayModeBar": True,
                                        "displaylogo": False,
                                        "modeBarButtonsToRemove": [
                                            "lasso2d", "select2d",
                                        ],
                                    },
                                    className="chart-container",
                                ),
                                type="circle",
                                color="#8a1f33",
                            ),
                            # Static zone legend below the chart
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.Span(
                                                className="standings-legend-swatch",
                                                style={"backgroundColor": "#0E1E5B"},
                                            ),
                                            html.Span("CHAMPIONS LEAGUE", className="standings-legend-label"),
                                        ],
                                        className="standings-legend-item",
                                    ),
                                    html.Div(className="standings-legend-divider"),
                                    html.Div(
                                        [
                                            html.Span(
                                                className="standings-legend-swatch",
                                                style={"backgroundColor": "#F47E01"},
                                            ),
                                            html.Span("EUROPA / CONFERENCE", className="standings-legend-label"),
                                        ],
                                        className="standings-legend-item",
                                    ),
                                    html.Div(className="standings-legend-divider"),
                                    html.Div(
                                        [
                                            html.Span(
                                                className="standings-legend-swatch",
                                                style={"backgroundColor": "#FF1A1A"},
                                            ),
                                            html.Span("RELEGATION", className="standings-legend-label"),
                                        ],
                                        className="standings-legend-item",
                                    ),
                                ],
                                className="standings-zone-legend",
                            ),
                        ],
                        className="chart-section",
                    ),

                    # Section: Most-Used Formations
                    html.Div(
                        [
                            _ds_header(
                                "Tactical Setup", "bi-diagram-3-fill",
                                "Most-Used Formations",
                                "Starting shapes used three or more times — "
                                "click a card to see the squad",
                            ),
                            dcc.Loading(
                                html.Div(
                                    id="formations-row",
                                    className="formations-row",
                                ),
                                type="circle",
                                color="#8a1f33",
                            ),
                            # Store tracks which formation card is active
                            dcc.Store(id="selected-formation-store", data=None),
                            # Lineup panel — hidden until a card is clicked
                            dcc.Loading(
                                html.Div(
                                    id="formation-lineup-panel",
                                    className="formation-lineup-panel",
                                    style={"display": "none"},
                                ),
                                type="circle",
                                color="#8a1f33",
                            ),
                        ],
                        className="chart-section",
                    ),

                    # Section: Goals & xG
                    html.Div(
                        [
                            _ds_header(
                                "Performance", "bi-crosshair",
                                "Offensive Production and Defensive Efficiency",
                                "Goals scored and conceded against their expected (xG) values",
                            ),
                            dcc.Loading(
                                html.Div(
                                    id="goals-xg-block",
                                    className="goals-xg-block",
                                ),
                                type="circle",
                                color="#8a1f33",
                            ),
                        ],
                        className="chart-section",
                    ),

                    # Section: Playing Style Wheel
                    html.Div(
                        [
                            _ds_header(
                                "Style Profile", "bi-pie-chart-fill",
                                "Playing Style Wheel",
                                "12 KPIs across four phases — each a within-"
                                "Serie A season percentile (0–99)",
                            ),
                            dcc.Loading(
                                html.Div(id="team-ps-container"),
                                type="circle",
                                color="#8a1f33",
                            ),
                        ],
                        className="chart-section",
                    ),

                    # Section: Style Evolution (cross-season trend charts)
                    dcc.Loading(
                        html.Div(id="team-ps-evo-container"),
                        type="circle",
                        color="#8a1f33",
                    ),

                    # Section: Pressing Intensity (PPDA)
                    html.Div(
                        [
                            _ds_header(
                                "Pressing", "bi-speedometer2",
                                "Pressing Intensity",
                                "PPDA ranking and field tilt vs the rest of the league",
                            ),
                            # PPDA KPI row
                            html.Div(
                                id="ppda-kpi-row",
                                className="team-kpi-row ppda-kpi-row",
                            ),
                            # Side-by-side charts
                            html.Div(
                                [
                                    html.Div(
                                        dcc.Loading(
                                            dcc.Graph(
                                                id="ppda-bar-chart",
                                                config={
                                                    "displayModeBar": True,
                                                    "displaylogo": False,
                                                    "modeBarButtonsToRemove": [
                                                        "lasso2d", "select2d",
                                                    ],
                                                },
                                                className="chart-container ppda-chart",
                                            ),
                                            type="circle",
                                            color="#8a1f33",
                                        ),
                                        className="ppda-chart-col",
                                    ),
                                    html.Div(
                                        dcc.Loading(
                                            dcc.Graph(
                                                id="ppda-scatter-chart",
                                                config={
                                                    "displayModeBar": True,
                                                    "displaylogo": False,
                                                    "modeBarButtonsToRemove": [
                                                        "lasso2d", "select2d",
                                                    ],
                                                },
                                                className="chart-container ppda-chart",
                                            ),
                                            type="circle",
                                            color="#8a1f33",
                                        ),
                                        className="ppda-chart-col",
                                    ),
                                ],
                                className="ppda-charts-row",
                            ),
                        ],
                        className="chart-section",
                    ),

                ],
                className="team-charts-container",
            ),
            # Modals: Goals by 15-Minute Intervals (one per metric)
            build_unified_modal(
                modal_id="td-scored-interval-modal",
                title_id="td-scored-interval-modal-title",
                body_id="td-scored-interval-modal-body",
                title="Goals Scored — 15-Minute Intervals",
                size="lg",
            ),
            build_unified_modal(
                modal_id="td-conceded-interval-modal",
                title_id="td-conceded-interval-modal-title",
                body_id="td-conceded-interval-modal-body",
                title="Goals Conceded — 15-Minute Intervals",
                size="lg",
            ),
            # Performance — league comparison modals
            build_unified_modal(
                modal_id="td-goals-scored-league-modal",
                title_id="td-goals-scored-league-modal-title",
                body_id="td-goals-scored-league-modal-body",
                title="Goals Scored — League Comparison",
                size="lg",
            ),
            build_unified_modal(
                modal_id="td-goals-conceded-league-modal",
                title_id="td-goals-conceded-league-modal-title",
                body_id="td-goals-conceded-league-modal-body",
                title="Goals Conceded — League Comparison",
                size="lg",
            ),
            build_unified_modal(
                modal_id="td-xg-league-modal",
                title_id="td-xg-league-modal-title",
                body_id="td-xg-league-modal-body",
                title="xG For — League Comparison",
                size="lg",
            ),
            build_unified_modal(
                modal_id="td-xgc-league-modal",
                title_id="td-xgc-league-modal-title",
                body_id="td-xgc-league-modal-body",
                title="xGC Against — League Comparison",
                size="lg",
            ),
            # Playing Style — league comparison table
            build_unified_modal(
                modal_id="team-ps-modal",
                title_id="team-ps-modal-title",
                body_id="team-ps-modal-body",
                title="Playing Style — League Comparison (percentiles)",
                size="xl",
            ),
        ],
        # "team-overview" scopes the Phase 1 design-system restyle to this page
        # (.kpi-card etc. are shared classes — see REDESIGN_TRACKER.md Phase 1).
        className="page-container team-overview",
    )


