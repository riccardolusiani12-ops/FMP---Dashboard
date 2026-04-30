"""
Team Overview Page — Team selection grid with season dropdown.

Routes: /serie-a
"""

import dash_bootstrap_components as dbc
from dash import dcc, html, callback, Input, Output

from src.config import AVAILABLE_SEASONS
from src.team_mapping import teams_for_season, logo_url, team_slug


def layout() -> html.Div:
    """Return the Serie A team selection page."""
    season_opts = [
        {"label": s.replace("_", "/"), "value": s}
        for s in AVAILABLE_SEASONS
    ]
    default_season = AVAILABLE_SEASONS[-1] if AVAILABLE_SEASONS else "2024_2025"

    return html.Div(
        [
            # Page header
            html.Div(
                [
                    html.A(
                        html.I(className="bi bi-arrow-left"),
                        href="/",
                        className="back-button",
                    ),
                    html.H2("Team Overview", className="page-title"),
                    html.Div(
                        [
                            html.Label("Season", className="filter-label"),
                            dcc.Dropdown(
                                id="season-selector",
                                options=season_opts,
                                value=default_season,
                                clearable=False,
                                className="season-dropdown",
                            ),
                        ],
                        className="season-filter",
                    ),
                ],
                className="page-header",
            ),

            # Teams grid — populated by callback
            dcc.Loading(
                html.Div(id="teams-grid", className="teams-grid"),
                type="circle",
                color="#8a1f33",
            ),
        ],
        className="page-container",
    )
