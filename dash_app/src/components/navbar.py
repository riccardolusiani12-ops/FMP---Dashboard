"""
Top navigation bar component — Calcio Italiano.
"""

import dash_bootstrap_components as dbc
from dash import html

from src.config import APP_TITLE


def create_navbar() -> html.Nav:
    """Return the top navbar with brand title, navigation links, and theme toggle."""
    return html.Nav(
        html.Div(
            [
                # Brand
                html.A(
                    html.Div(
                        [
                            html.Img(
                                src="/assets/logos/italia.png",
                                className="navbar-logo",
                            ),
                            html.Span(
                                APP_TITLE,
                                className="navbar-brand-text",
                            ),
                        ],
                        className="navbar-brand",
                    ),
                    href="/",
                    className="navbar-brand-link",
                ),

                # Navigation links + theme toggle
                html.Div(
                    [
                        html.A("Home", href="/", className="nav-link"),
                        html.A("Team Overview", href="/serie-a", className="nav-link"),
                        html.A("Team Analysis", href="/team-analysis", className="nav-link"),

                        # Theme toggle button
                        html.Button(
                            html.I(className="bi bi-sun-fill", style={"fontSize": "0.95rem"}),
                            id="theme-toggle-btn",
                            className="theme-toggle-btn",
                            n_clicks=0,
                            title="Toggle light/dark theme",
                        ),
                    ],
                    className="navbar-links",
                ),
            ],
            className="navbar-inner",
        ),
        className="top-navbar",
    )
