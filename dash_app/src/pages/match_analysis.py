"""
Team Analysis Page — Hub for Match Analysis and Opponent Analysis.

Routes: /team-analysis
"""

import dash_bootstrap_components as dbc
from dash import html


def layout() -> html.Div:
    """Return the team analysis hub page."""
    return html.Div(
        [
            # Page header
            html.Div(
                [
                    html.A(
                        [
                            html.I(className="bi bi-arrow-left me-2"),
                        ],
                        href="/",
                        className="back-button",
                    ),
                    html.H2("Team Analysis", className="page-title"),
                ],
                className="page-header",
            ),

            html.P(
                "Select an analysis workflow to begin.",
                className="page-subtitle",
            ),

            # Navigation cards — Match Analysis on the left, Opponent Analysis on the right
            html.Div(
                [
                    # Match Analysis card (left) — was "Post-Match"
                    html.A(
                        html.Div(
                            [
                                html.Div(
                                    html.I(className="bi bi-bar-chart-line-fill"),
                                    className="home-card-icon",
                                ),
                                html.H3("Match Analysis", className="home-card-title"),
                                html.P(
                                    "Post-game tactical breakdown, attacking phases, "
                                    "high regains, and performance review",
                                    className="home-card-desc",
                                ),
                                html.Div(
                                    [
                                        html.Span("Open", className="home-card-cta-text"),
                                        html.I(className="bi bi-arrow-right"),
                                    ],
                                    className="home-card-cta",
                                ),
                            ],
                            className="home-card",
                        ),
                        href="/team-analysis/match-analysis",
                        className="home-card-link",
                    ),

                    # Opponent Analysis card (right) — was "Pre-Match"
                    html.A(
                        html.Div(
                            [
                                html.Div(
                                    html.I(className="bi bi-journal-text"),
                                    className="home-card-icon",
                                ),
                                html.H3("Opponent Analysis", className="home-card-title"),
                                html.P(
                                    "Tactical preparation, opponent analysis, "
                                    "passing networks, and team form review",
                                    className="home-card-desc",
                                ),
                                html.Div(
                                    [
                                        html.Span("Open", className="home-card-cta-text"),
                                        html.I(className="bi bi-arrow-right"),
                                    ],
                                    className="home-card-cta",
                                ),
                            ],
                            className="home-card",
                        ),
                        href="/team-analysis/opponent-analysis",
                        className="home-card-link",
                    ),
                ],
                className="home-cards-grid",
            ),
        ],
        className="page-container",
    )
