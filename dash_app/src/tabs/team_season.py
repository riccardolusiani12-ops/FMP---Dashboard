"""
Team Season Performance tab – season trends, PPDA, points progression, league tables.
"""

import dash_bootstrap_components as dbc
from dash import dcc, html

from src.registry.loaders import render_artifacts_for_analysis


def layout() -> html.Div:
    """Return team season performance layout."""
    return html.Div(
        [
            html.H5(
                [
                    html.I(className="bi bi-graph-up-arrow me-2"),
                    "Team Season Performance",
                ],
                className="text-light mb-3",
            ),
            html.P(
                "Season-long trends: points progression, pressing intensity, defensive metrics.",
                className="text-muted mb-3",
            ),
            dcc.Loading(
                html.Div(id="team-season-content", children=[]),
                type="circle",
                color="#c8102e",
            ),
        ],
        className="p-3",
    )


def render_team_season_content(season: str, team: str) -> list:
    """Build team season tab content."""
    components: list = []

    # Points progression
    pts = render_artifacts_for_analysis("season_points_progression", season=season, team=team)
    if pts:
        components.append(html.H6("📈 Points Progression", className="text-light mt-2"))
        components.extend(pts)

    # PPDA
    ppda = render_artifacts_for_analysis("ppda", season=season, team=team)
    if ppda:
        components.append(html.H6("📊 PPDA – Pressing Intensity", className="text-light mt-4"))
        components.extend(ppda)

    # High regains (season aggregate)
    hr = render_artifacts_for_analysis("high_regains", season=season, team=team)
    if hr:
        components.append(html.H6("🔴 High Regains – Season", className="text-light mt-4"))
        components.extend(hr)

    # EPV season overview
    epv = render_artifacts_for_analysis("epv", season=season, team=team)
    if epv:
        components.append(html.H6("💎 EPV – Season", className="text-light mt-4"))
        components.extend(epv)

    if not components:
        components.append(
            dbc.Alert(
                [
                    html.I(className="bi bi-info-circle me-2"),
                    f"No season-level artifacts found for {team} – {season.replace('_', '/')}.",
                ],
                color="secondary",
            )
        )

    return components
