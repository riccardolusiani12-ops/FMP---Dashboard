"""
Home tab – Bologna season overview.
Shows high-level KPIs and overview artifacts for the current season.
"""

import dash_bootstrap_components as dbc
from dash import dcc, html

from src.registry.loaders import render_artifacts_for_analysis


def layout() -> html.Div:
    """Return the static skeleton; content loaded by callback."""
    return html.Div(
        [
            html.H5(
                [
                    html.I(className="bi bi-house-door-fill me-2"),
                    "Season Overview",
                ],
                className="text-light mb-3",
            ),
            html.P(
                "Overview of Bologna's current season – KPIs, standings trend, and key metrics.",
                className="text-muted mb-3",
            ),
            # Dynamic content filled by callback
            dcc.Loading(
                html.Div(id="home-content", children=[]),
                type="circle",
                color="#c8102e",
            ),
        ],
        className="p-3",
    )


def render_home_content(season: str, team: str) -> list:
    """Build home tab content from artifacts."""
    components: list = []

    # Season points progression
    pts = render_artifacts_for_analysis("season_points_progression", season=season, team=team)
    if pts:
        components.append(html.H6("📈 Season Points Progression", className="text-light mt-3"))
        components.extend(pts)

    # High regains overview
    hr = render_artifacts_for_analysis("high_regains", season=season, team=team)
    if hr:
        components.append(html.H6("🔴 High Regains", className="text-light mt-4"))
        components.extend(hr)

    # PPDA overview
    ppda = render_artifacts_for_analysis("ppda", season=season, team=team)
    if ppda:
        components.append(html.H6("📊 PPDA (Pressing Intensity)", className="text-light mt-4"))
        components.extend(ppda)

    if not components:
        components.append(
            dbc.Alert(
                [
                    html.I(className="bi bi-info-circle me-2"),
                    f"No artifacts found for {team} – {season.replace('_', '/')}. ",
                    "Generate outputs from notebooks and update the manifest.",
                ],
                color="secondary",
                className="mt-3",
            )
        )

    return components
