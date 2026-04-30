"""
Team Card Component — clickable team logo + name for the grid layout.
"""

from dash import html

from src.team_mapping import logo_url, team_slug


def team_card(team_name: str) -> html.A:
    """
    Create a clickable team card with logo and name.

    Parameters
    ----------
    team_name : str
        Canonical team display name (e.g. "Bologna", "Inter")

    Returns
    -------
    html.A — clickable card linking to /serie-a/team/<slug>
    """
    slug = team_slug(team_name)
    return html.A(
        html.Div(
            [
                html.Img(
                    src=logo_url(team_name),
                    className="team-card-logo",
                    alt=team_name,
                ),
                html.Span(team_name, className="team-card-name"),
            ],
            className="team-card",
        ),
        href=f"/serie-a/team/{slug}",
        className="team-card-link",
    )


def analysis_team_card(team_name: str, section_prefix: str) -> html.Div:
    """
    Create a clickable team card for analysis pages (Match Analysis / Opponent Analysis).

    Uses pattern-matching callbacks instead of <a> href navigation.
    The card click triggers a callback that stores the selected team.

    Parameters
    ----------
    team_name : str
        Canonical team display name (e.g. "Bologna", "Inter")
    section_prefix : str
        ID prefix for pattern matching ("ma" or "opponent")

    Returns
    -------
    html.Div — clickable card with pattern-matching ID
    """
    slug = team_slug(team_name)
    return html.Div(
        html.Div(
            [
                html.Img(
                    src=logo_url(team_name),
                    className="team-card-logo",
                    alt=team_name,
                ),
                html.Span(team_name, className="team-card-name"),
            ],
            className="team-card",
        ),
        id={"type": f"{section_prefix}-team-card", "index": slug},
        className="team-card-link",
        n_clicks=0,
    )
