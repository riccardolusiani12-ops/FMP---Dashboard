"""
Team Detail Page — KPIs and charts for a selected team.

Routes: /serie-a/team/<team-slug>
"""

import dash_bootstrap_components as dbc
from dash import dcc, html

from src.config import AVAILABLE_SEASONS


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
            # Page header: Back | Logo | Team name | Season dropdown
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
                    # Season selector in header
                    html.Div(
                        [
                            html.Label("Season", className="filter-label"),
                            dcc.Dropdown(
                                id="team-season-selector",
                                options=season_options,
                                value=default_season,
                                clearable=False,
                                className="season-dropdown",
                            ),
                        ],
                        className="season-filter",
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
                            html.Div(
                                [
                                    html.I(className="bi bi-graph-up me-2"),
                                    html.H4(
                                        "Points Progression",
                                        className="section-title mb-0",
                                    ),
                                ],
                                className="section-header",
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
                        ],
                        className="chart-section",
                    ),

                    # Section: Pressing Intensity (PPDA)
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.I(className="bi bi-speedometer2 me-2"),
                                    html.H4(
                                        "Pressing Intensity",
                                        className="section-title mb-0",
                                    ),
                                ],
                                className="section-header",
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

                    # Section: Most-Used Formations
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.I(className="bi bi-diagram-3-fill me-2"),
                                    html.H4(
                                        "Most-Used Formations",
                                        className="section-title mb-0",
                                    ),
                                ],
                                className="section-header",
                            ),
                            dcc.Loading(
                                html.Div(
                                    id="formations-row",
                                    className="formations-row",
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
                            html.Div(
                                [
                                    html.I(className="bi bi-crosshair me-2"),
                                    html.H4(
                                        "Goals & Expected Goals",
                                        className="section-title mb-0",
                                    ),
                                ],
                                className="section-header",
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

                    # Section: Goal Distribution by 15-Minute Windows
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.I(className="bi bi-clock-history me-2"),
                                    html.H4(
                                        "Goals by 15-Minute Intervals",
                                        className="section-title mb-0",
                                    ),
                                ],
                                className="section-header",
                            ),
                            dcc.Loading(
                                html.Div(
                                    id="goal-distribution-block",
                                    className="goal-distribution-block",
                                ),
                                type="circle",
                                color="#8a1f33",
                            ),
                        ],
                        className="chart-section",
                    ),

                    _placeholder_section(
                        "Expected Threat (xT)",
                        "bi-lightning-fill",
                        "Expected Threat analysis will be available here.",
                    ),
                    _placeholder_section(
                        "High Regains",
                        "bi-bullseye",
                        "High regain analysis will be available here.",
                    ),
                ],
                className="team-charts-container",
            ),
        ],
        className="page-container",
    )


def _placeholder_section(title: str, icon: str, description: str) -> html.Div:
    """Create a placeholder section for future KPI modules."""
    return html.Div(
        [
            html.Div(
                [
                    html.I(className=f"bi {icon} me-2"),
                    html.H4(title, className="section-title mb-0"),
                ],
                className="section-header",
            ),
            html.Div(
                [
                    html.I(
                        className="bi bi-hourglass-split",
                        style={"fontSize": "2rem", "opacity": 0.3},
                    ),
                    html.P(description, className="placeholder-text"),
                ],
                className="placeholder-content",
            ),
        ],
        className="chart-section placeholder-section",
    )
