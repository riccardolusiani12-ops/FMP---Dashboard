"""
Match Report tab – Match Analysis & Opponent Analysis sub-views.
Segmented control switches between the two.
"""

import dash_bootstrap_components as dbc
from dash import dcc, html

from src.registry.loaders import render_artifacts_for_analysis


def layout() -> html.Div:
    """Return match report layout with analysis toggle."""
    return html.Div(
        [
            html.H5(
                [
                    html.I(className="bi bi-journal-text me-2"),
                    "Match Report",
                ],
                className="text-light mb-3",
            ),
            # Match Analysis / Opponent Analysis toggle
            dbc.RadioItems(
                id="match-report-toggle",
                options=[
                    {"label": "Match Analysis", "value": "post"},
                    {"label": "Opponent Analysis", "value": "pre"},
                ],
                value="post",
                inline=True,
                className="mb-3 btn-group",
                inputClassName="btn-check",
                labelClassName="btn btn-outline-light btn-sm",
                labelCheckedClassName="btn btn-danger btn-sm",
            ),
            dcc.Loading(
                html.Div(id="match-report-content", children=[]),
                type="circle",
                color="#c8102e",
            ),
        ],
        className="p-3",
    )


def render_pre_match(season: str, team: str, match_id: str | None) -> list:
    """Opponent analysis: passing network, xT zones, team form."""
    components: list = []

    # Passing network
    pn = render_artifacts_for_analysis("passing_network", season=season, team=team, match_id=match_id)
    if pn:
        components.append(html.H6("🔗 Passing Network", className="text-light mt-2"))
        components.extend(pn)

    # xT zones
    xt = render_artifacts_for_analysis("xt", season=season, team=team, match_id=match_id)
    if xt:
        components.append(html.H6("⚡ Expected Threat (xT)", className="text-light mt-4"))
        components.extend(xt)

    if not components:
        components.append(
            dbc.Alert(
                [
                    html.I(className="bi bi-info-circle me-2"),
                    "No opponent analysis artifacts found. Select a match from the global filters.",
                ],
                color="secondary",
            )
        )

    return components


def render_post_match(season: str, team: str, match_id: str | None) -> list:
    """Match analysis: attacking phase, high regains, EPV, xT."""
    components: list = []

    # Attacking phase
    ap = render_artifacts_for_analysis("attacking_phase", season=season, team=team, match_id=match_id)
    if ap:
        components.append(html.H6("⚔️ Attacking Phase", className="text-light mt-2"))
        components.extend(ap)

    # High regains
    hr = render_artifacts_for_analysis("high_regains", season=season, team=team, match_id=match_id)
    if hr:
        components.append(html.H6("🔴 High Regains", className="text-light mt-4"))
        components.extend(hr)

    # EPV
    epv = render_artifacts_for_analysis("epv", season=season, team=team, match_id=match_id)
    if epv:
        components.append(html.H6("💎 Expected Possession Value", className="text-light mt-4"))
        components.extend(epv)

    # xT
    xt = render_artifacts_for_analysis("xt", season=season, team=team, match_id=match_id)
    if xt:
        components.append(html.H6("⚡ Expected Threat (xT)", className="text-light mt-4"))
        components.extend(xt)

    if not components:
        components.append(
            dbc.Alert(
                [
                    html.I(className="bi bi-info-circle me-2"),
                    "No match analysis artifacts found. Select a match from the global filters.",
                ],
                color="secondary",
            )
        )

    return components
