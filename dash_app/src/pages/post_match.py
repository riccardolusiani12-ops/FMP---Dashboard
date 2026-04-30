"""
Match Analysis Page — Team & match selection flow, then analysis modules.

Routes: /team-analysis/match-analysis
"""

import dash_bootstrap_components as dbc
from dash import dcc, html

from src.config import AVAILABLE_SEASONS


def layout() -> html.Div:
    """Return the match analysis page with team/match selection flow."""
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
                    html.H2("Match Analysis", className="page-title"),
                    html.Div(
                        [
                            html.Label("Season", className="filter-label"),
                            dcc.Dropdown(
                                id="ma-season-selector",
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
            dcc.Store(id="ma-selected-team", data=None),
            dcc.Store(id="ma-selected-match", data=None),
            dcc.Store(id="ma-active-module", data=None),

            # Teams grid — same as Team Overview
            html.Div(
                [
                    html.P(
                        "Select a team to view their matches.",
                        className="page-subtitle",
                    ),
                    dcc.Loading(
                        html.Div(id="ma-teams-grid", className="teams-grid"),
                        type="circle",
                        color="#8a1f33",
                    ),
                ],
                id="ma-team-selection",
            ),

            # Match list — shown after team is selected
            html.Div(
                id="ma-match-selection",
                style={"display": "none"},
            ),

            # Analysis modules — shown after match is selected
            html.Div(
                id="ma-analysis-content",
                style={"display": "none"},
            ),
        ],
        className="page-container",
    )
