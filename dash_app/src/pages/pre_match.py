"""
Opponent Analysis Page — Team & match selection flow, then analysis modules.

Routes: /team-analysis/opponent-analysis
"""

import dash_bootstrap_components as dbc
from dash import dcc, html

from src.config import AVAILABLE_SEASONS


def layout() -> html.Div:
    """Return the opponent analysis page with team/match selection flow."""
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
                        [
                            html.I(className="bi bi-arrow-left me-2"),
                            "Back",
                        ],
                        href="/team-analysis",
                        className="back-button",
                    ),
                    html.H2("Opponent Analysis", className="page-title"),
                    html.Div(
                        [
                            html.Label("Season", className="filter-label"),
                            dcc.Dropdown(
                                id="opponent-season-selector",
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

            # Hidden store to track selection state
            dcc.Store(id="opponent-selected-team", data=None),
            dcc.Store(id="opponent-selected-match", data=None),
            dcc.Store(id="opponent-active-module", data=None),

            # Teams grid — same as Team Overview
            html.Div(
                [
                    html.P(
                        "Select a team to view their matches.",
                        className="page-subtitle",
                    ),
                    dcc.Loading(
                        html.Div(id="opponent-teams-grid", className="teams-grid"),
                        type="circle",
                        color="#8a1f33",
                    ),
                ],
                id="opponent-team-selection",
            ),

            # Match list — shown after team is selected
            html.Div(
                id="opponent-match-selection",
                style={"display": "none"},
            ),

            # Analysis modules — shown after match is selected
            html.Div(
                id="opponent-analysis-content",
                style={"display": "none"},
            ),
        ],
        className="page-container",
    )
