"""
Filter callbacks – update dropdown options based on global filter selections.
Populate team list from match filenames, match list from season + team.
"""

from __future__ import annotations

from dash import Input, Output, callback, no_update

from src.registry.registry import ArtifactRegistry
from src.utils.paths import list_match_files, parse_match_filename
from src.utils.caching import cached
from src.utils.logging import log
from src.config import DEFAULT_TEAM


@cached
def _teams_from_files(season: str) -> list[str]:
    """Extract unique team names from match filenames for a season."""
    files = list_match_files(season)
    teams: set[str] = set()
    for f in files:
        info = parse_match_filename(f)
        teams.add(info["home"])
        teams.add(info["away"])
    return sorted(teams)


@cached
def _matches_for_team(season: str, team: str | None) -> list[dict]:
    """Return match options filtered by team (home or away)."""
    files = list_match_files(season)
    matches = []
    for f in files:
        info = parse_match_filename(f)
        if team:
            if info["home"].lower() != team.lower() and info["away"].lower() != team.lower():
                continue
        matches.append({"label": info["label"], "value": info["match_id"]})
    return matches


def register_filter_callbacks(app):
    """Register all filter-related callbacks."""

    @app.callback(
        Output("filter-team", "options"),
        Output("filter-team", "value"),
        Input("filter-season", "value"),
    )
    def update_team_options(season: str | None):
        if not season:
            return [], None

        teams = _teams_from_files(season)
        options = [{"label": t, "value": t} for t in teams]

        # Keep Bologna selected if available
        value = DEFAULT_TEAM if DEFAULT_TEAM in teams else (teams[0] if teams else None)

        return options, value

    @app.callback(
        Output("filter-match", "options"),
        Output("filter-match", "value"),
        Input("filter-season", "value"),
        Input("filter-team", "value"),
    )
    def update_match_options(season: str | None, team: str | None):
        if not season:
            return [], None

        matches = _matches_for_team(season, team)
        return matches, None  # don't auto-select a match

    log.info("Filter callbacks registered")
