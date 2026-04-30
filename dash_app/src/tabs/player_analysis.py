"""
Player Analysis tab – viewer for player-level precomputed outputs.
"""

import dash_bootstrap_components as dbc
from dash import dcc, html

from src.registry.loaders import render_artifacts_for_analysis


def layout() -> html.Div:
    """Return player analysis layout."""
    return html.Div(
        [
            html.H5(
                [
                    html.I(className="bi bi-person-fill me-2"),
                    "Player Analysis",
                ],
                className="text-light mb-3",
            ),
            html.P(
                "Player-level metrics: xT contributions, progressive actions, EPV delta per player.",
                className="text-muted mb-3",
            ),
            dcc.Loading(
                html.Div(id="player-analysis-content", children=[]),
                type="circle",
                color="#c8102e",
            ),
        ],
        className="p-3",
    )


def render_player_content(season: str, team: str, match_id: str | None = None) -> list:
    """Build player analysis content from artifacts tagged as player-level."""
    components: list = []

    # Look for player-tagged artifacts across analyses
    for analysis in ["xt", "epv", "attacking_phase", "passing_network"]:
        arts = render_artifacts_for_analysis(analysis, season=season, team=team, match_id=match_id)
        # Only include if tagged as player (handled at manifest level)
        if arts and not isinstance(arts[0], dbc.Alert):
            components.append(
                html.H6(
                    f"👤 {analysis.replace('_', ' ').title()}",
                    className="text-light mt-3",
                )
            )
            components.extend(arts)

    if not components:
        components.append(
            dbc.Alert(
                [
                    html.I(className="bi bi-info-circle me-2"),
                    "No player-level artifacts found. ",
                    "Tag artifacts with player-level data in the manifest to see them here.",
                ],
                color="secondary",
            )
        )

    return components
