"""
Serie A page callbacks — populate the team grid based on season selection.

Refactored to use precomputed ready tables via data_loader instead of
scanning raw CSV filenames on every season change.
"""

from __future__ import annotations

from dash import Input, Output, html

from src.analytics.data_loader import load_season_teams
from src.components.team_card import team_card


def register_serie_a_callbacks(app):
    """Register callbacks for the Serie A team selection page."""

    @app.callback(
        Output("teams-grid", "children"),
        Input("season-selector", "value"),
        prevent_initial_call=False,
    )
    def update_teams_grid(season: str | None):
        """Populate the teams grid when a season is selected."""
        if not season:
            return html.P("Please select a season.", className="text-muted")

        teams = load_season_teams(season)
        if not teams:
            return html.P(
                f"No teams found for season {season.replace('_', '/')}.",
                className="text-muted",
            )

        # Pass selected season so Team Detail page opens pre-filtered
        return [team_card(t, season=season) for t in teams]
