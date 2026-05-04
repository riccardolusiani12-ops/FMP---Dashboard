"""
Analysis page callbacks — team grid, match list, module selector and live
analysis rendering for Match Analysis and Opponent Analysis pages.

Callback ID prefixes:
  "ma"       -> Match Analysis  (post_match.py)
  "opponent" -> Opponent Analysis (pre_match.py)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import dash_bootstrap_components as dbc
from dash import ALL, Input, Output, State, dcc, html, no_update

from src.analytics.data_loader import load_season_teams, load_season_matches_cached
from src.components.analysis_cards import (
    _match_card,
    _match_list_layout,
    _module_card_active,
    _module_card_soon,
    _module_selector,
    _analysis_view,
    _opponent_team,
    _score_lookup,
)
from src.components.team_card import analysis_team_card
from src.team_mapping import canonical_name, logo_url, team_from_slug
from src.utils.logging import log
from src.utils.paths import list_match_files, parse_match_filename


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _find_match_csv(season: str, match_id: str) -> Optional[Path]:
    for f in list_match_files(season):
        info = parse_match_filename(f)
        if info["match_id"] == match_id:
            return f
    return None


def _teams_grid_children(season: str, prefix: str) -> list:
    teams = load_season_teams(season)
    if not teams:
        return [html.P(f"No teams found for {season.replace('_', '/')}.",
                       className="text-muted")]
    return [analysis_team_card(t, prefix) for t in teams]

def register_analysis_callbacks(app):
    for prefix in ("ma", "opponent"):
        _register_prefix(app, prefix)


def _register_prefix(app, prefix: str):
    season_id          = f"{prefix}-season-selector"
    selected_team_id   = f"{prefix}-selected-team"
    selected_match_id  = f"{prefix}-selected-match"
    active_module_id   = f"{prefix}-active-module"
    team_selection_id  = f"{prefix}-team-selection"
    match_selection_id = f"{prefix}-match-selection"
    analysis_id        = f"{prefix}-analysis-content"
    teams_grid_id      = f"{prefix}-teams-grid"

    # 1. Teams grid on season change
    @app.callback(
        Output(teams_grid_id, "children"),
        Input(season_id, "value"),
        prevent_initial_call=False,
    )
    def _update_teams_grid(season, _p=prefix):
        if not season:
            return html.P("Please select a season.", className="text-muted")
        return _teams_grid_children(season, _p)

    # 2. Team card click -> store slug
    @app.callback(
        Output(selected_team_id, "data"),
        Input({"type": f"{prefix}-team-card", "index": ALL}, "n_clicks"),
        State({"type": f"{prefix}-team-card", "index": ALL}, "id"),
        prevent_initial_call=True,
    )
    def _store_team(n_clicks_list, id_list):
        for n, id_dict in zip(n_clicks_list, id_list):
            if n:
                return id_dict["index"]
        return no_update

    # 3. Match card click -> store match_id (and clear active module)
    @app.callback(
        Output(selected_match_id, "data"),
        Output(active_module_id,  "data", allow_duplicate=True),
        Input({"type": f"{prefix}-match-item", "index": ALL}, "n_clicks"),
        State({"type": f"{prefix}-match-item", "index": ALL}, "id"),
        prevent_initial_call=True,
    )
    def _store_match(n_clicks_list, id_list):
        for n, id_dict in zip(n_clicks_list, id_list):
            if n:
                return id_dict["index"], None
        return no_update, no_update

    # 4. Module card click -> store active module
    @app.callback(
        Output(active_module_id, "data"),
        Input({"type": f"{prefix}-module-card", "index": ALL}, "n_clicks"),
        State({"type": f"{prefix}-module-card", "index": ALL}, "id"),
        prevent_initial_call=True,
    )
    def _store_module(n_clicks_list, id_list):
        for n, id_dict in zip(n_clicks_list, id_list):
            if n:
                return id_dict["index"]
        return no_update

    # 5. Back-to-modules button -> clear active module
    @app.callback(
        Output(active_module_id, "data", allow_duplicate=True),
        Input(f"{prefix}-back-to-modules", "n_clicks"),
        prevent_initial_call=True,
    )
    def _back_to_modules(n):
        if n:
            return None
        return no_update

    # 6. Show/hide sections + content (driven by all three stores)
    @app.callback(
        Output(team_selection_id,  "style"),
        Output(match_selection_id, "style"),
        Output(match_selection_id, "children"),
        Output(analysis_id,        "style"),
        Output(analysis_id,        "children"),
        Input(selected_team_id,  "data"),
        Input(selected_match_id, "data"),
        Input(active_module_id,  "data"),
        State(season_id, "value"),
        prevent_initial_call=True,
    )
    def _update_sections(team_slug, match_id, active_module, season, _p=prefix):
        show = {"display": "block"}
        hide = {"display": "none"}

        if not team_slug:
            return show, hide, no_update, hide, no_update

        team   = team_from_slug(team_slug) or team_slug
        season = season or ""

        if not match_id:
            return hide, show, _match_list_layout(season, team, _p), hide, no_update

        match_csv = _find_match_csv(season, match_id)
        if match_csv is None:
            err = dbc.Alert(
                f"Match CSV not found for id '{match_id}' in season {season}.",
                color="danger",
            )
            return hide, hide, no_update, show, err

        info  = parse_match_filename(match_csv)
        label = info["label"]

        if active_module in ("offensive", "defensive"):
            content = _analysis_view(match_csv, team, label, active_module, _p)
        else:
            content = _module_selector(label, _p)

        return hide, hide, no_update, show, content

    # 7. Back to teams
    @app.callback(
        Output(selected_team_id,  "data", allow_duplicate=True),
        Output(selected_match_id, "data", allow_duplicate=True),
        Output(active_module_id,  "data", allow_duplicate=True),
        Input(f"{prefix}-back-to-teams", "n_clicks"),
        prevent_initial_call=True,
    )
    def _back_to_teams(n):
        if n:
            return None, None, None
        return no_update, no_update, no_update

    # 8. Back to matches
    @app.callback(
        Output(selected_match_id, "data", allow_duplicate=True),
        Output(active_module_id,  "data", allow_duplicate=True),
        Input(f"{prefix}-back-to-matches", "n_clicks"),
        prevent_initial_call=True,
    )
    def _back_to_matches(n):
        if n:
            return None, None
        return no_update, no_update
