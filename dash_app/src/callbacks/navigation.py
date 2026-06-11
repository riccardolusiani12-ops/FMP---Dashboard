"""
Navigation callbacks — URL routing and page rendering.
"""

from __future__ import annotations

from urllib.parse import urlparse, parse_qs

from dash import Input, Output, html, dcc
from src.pages import home, serie_a, team_detail, match_analysis, pre_match, post_match
from src.team_mapping import team_from_slug
from src.config import AVAILABLE_SEASONS


def register_navigation_callbacks(app):
    """Register the main URL → page content routing callback."""

    @app.callback(
        Output("page-content", "children"),
        Input("url", "pathname"),
        Input("url", "search"),
    )
    def display_page(pathname: str, search: str):
        """Route URL path to the corresponding page layout."""
        if pathname is None:
            pathname = "/"

        pathname = pathname.rstrip("/") or "/"

        # Home
        if pathname == "/":
            return home.layout()

        # Serie A team selection
        if pathname == "/serie-a":
            return serie_a.layout()

        # Team detail: /serie-a/team/<slug>
        if pathname.startswith("/serie-a/team/"):
            slug = pathname.replace("/serie-a/team/", "").strip("/")
            team_name = team_from_slug(slug)
            if team_name:
                # Extract ?season= query param from the URL (set by team_card)
                season = ""
                if search:
                    params = parse_qs(search.lstrip("?"))
                    season_list = params.get("season", [])
                    if season_list and season_list[0] in AVAILABLE_SEASONS:
                        season = season_list[0]
                return team_detail.layout(team_name=team_name, season=season)
            return _not_found(f"Team not found: {slug}")

        # Team Analysis hub
        if pathname == "/team-analysis":
            return match_analysis.layout()

        # Match Analysis (was post-match)
        if pathname == "/team-analysis/match-analysis":
            return post_match.layout()

        # Opponent Analysis (was pre-match)
        if pathname == "/team-analysis/opponent-analysis":
            return pre_match.layout()

        # Legacy redirects (keep old URLs working)
        if pathname == "/match-analysis":
            return match_analysis.layout()
        if pathname == "/match-analysis/pre-match":
            return pre_match.layout()
        if pathname == "/match-analysis/post-match":
            return post_match.layout()

        # 404
        return _not_found(pathname)


def _not_found(path: str) -> html.Div:
    """Return a styled 404 page."""
    return html.Div(
        [
            html.Div(
                [
                    html.H1("404", className="error-code"),
                    html.P("Page not found", className="error-message"),
                    html.A(
                        "← Back to Home",
                        href="/",
                        className="back-button",
                    ),
                ],
                className="error-container",
            ),
        ],
        className="page-container",
    )
