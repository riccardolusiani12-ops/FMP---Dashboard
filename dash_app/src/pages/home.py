"""
Home Page — Landing screen with two main navigation cards.

Routes: /
"""

import dash_bootstrap_components as dbc
from dash import html


def layout() -> html.Div:
    """Return the home landing page layout."""
    return html.Div(
        [
            # Hero section
            html.Div(
                [
                    html.Img(
                        src="/assets/logos/italia.png",
                        className="home-hero-logo",
                    ),
                    html.H1("Calcio Italiano", className="home-hero-title"),
                    html.P(
                        "Serie A Analytics Dashboard",
                        className="home-hero-subtitle",
                    ),
                ],
                className="home-hero",
            ),

            # Navigation cards
            html.Div(
                [
                    # Serie A card
                    html.A(
                        html.Div(
                            [
                                html.Div(
                                    html.I(className="bi bi-trophy-fill"),
                                    className="home-card-icon",
                                ),
                                html.H3("Team Overview", className="home-card-title"),
                                html.P(
                                    "Season standings, team performance, and league analytics",
                                    className="home-card-desc",
                                ),
                                html.Div(
                                    [
                                        html.Span("Explore", className="home-card-cta-text"),
                                        html.I(className="bi bi-arrow-right"),
                                    ],
                                    className="home-card-cta",
                                ),
                            ],
                            className="home-card",
                        ),
                        href="/serie-a",
                        className="home-card-link",
                    ),

                    # Team Analysis card
                    html.A(
                        html.Div(
                            [
                                html.Div(
                                    html.I(className="bi bi-clipboard-data-fill"),
                                    className="home-card-icon",
                                ),
                                html.H3("Team Analysis", className="home-card-title"),
                                html.P(
                                    "Match analysis and opponent tactical breakdown",
                                    className="home-card-desc",
                                ),
                                html.Div(
                                    [
                                        html.Span("Explore", className="home-card-cta-text"),
                                        html.I(className="bi bi-arrow-right"),
                                    ],
                                    className="home-card-cta",
                                ),
                            ],
                            className="home-card",
                        ),
                        href="/team-analysis",
                        className="home-card-link",
                    ),
                ],
                className="home-cards-grid",
            ),
        ],
        className="home-container",
    )
