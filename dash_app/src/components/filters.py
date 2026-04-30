"""
Global filter bar – always visible below the navbar.
Dropdowns for competition, season, team, match.
"""

import dash_bootstrap_components as dbc
from dash import dcc, html

from src.config import (
    AVAILABLE_SEASONS,
    DEFAULT_COMPETITION,
    DEFAULT_SEASON,
    DEFAULT_TEAM,
)


def _dropdown(
    label: str,
    id: str,
    options: list[dict],
    value=None,
    multi: bool = False,
    clearable: bool = True,
    placeholder: str = "Select…",
) -> dbc.Col:
    """Helper: a labeled dropdown inside a Col."""
    return dbc.Col(
        [
            html.Label(label, className="small text-muted mb-1"),
            dcc.Dropdown(
                id=id,
                options=options,
                value=value,
                multi=multi,
                clearable=clearable,
                placeholder=placeholder,
                className="dash-dropdown-dark",
                style={"fontSize": "0.85rem"},
            ),
        ],
        xs=12,
        sm=6,
        md=4,
        lg=3,
        className="mb-2",
    )


def create_filters_bar() -> dbc.Card:
    """Return the global filter bar card."""

    season_opts = [
        {"label": s.replace("_", "/"), "value": s} for s in AVAILABLE_SEASONS
    ]
    # Default season: pick latest available or fall back
    default_season = AVAILABLE_SEASONS[-1] if AVAILABLE_SEASONS else DEFAULT_SEASON

    return dbc.Card(
        dbc.CardBody(
            dbc.Row(
                [
                    # Competition
                    _dropdown(
                        "Competition",
                        "filter-competition",
                        [{"label": "Serie A", "value": "Serie A"}],
                        value=DEFAULT_COMPETITION,
                        clearable=False,
                    ),
                    # Season
                    _dropdown(
                        "Season",
                        "filter-season",
                        season_opts,
                        value=default_season,
                        clearable=False,
                    ),
                    # Team
                    _dropdown(
                        "Team",
                        "filter-team",
                        [],  # populated by callback
                        value=DEFAULT_TEAM,
                        placeholder="All teams",
                    ),
                    # Match
                    _dropdown(
                        "Match",
                        "filter-match",
                        [],  # populated by callback
                        placeholder="All matches",
                    ),
                ],
                className="g-2 align-items-end",
            ),
            className="py-2 px-3",
        ),
        className="mb-3 border-0",
        style={"backgroundColor": "rgba(44,62,80,0.5)"},
    )
