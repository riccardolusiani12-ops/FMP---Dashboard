"""
KPI cards row – top summary metrics.
"""

from typing import Optional

import dash_bootstrap_components as dbc
from dash import html


def kpi_card(title: str, value: str, subtitle: str = "", icon: str = "bi-graph-up", color: str = "primary") -> dbc.Col:
    """Single KPI card."""
    return dbc.Col(
        dbc.Card(
            dbc.CardBody(
                [
                    html.Div(
                        [
                            html.I(className=f"bi {icon}", style={"fontSize": "1.4rem", "opacity": 0.7}),
                            html.H5(title, className="mb-0 ms-2 text-muted", style={"fontSize": "0.75rem"}),
                        ],
                        className="d-flex align-items-center mb-2",
                    ),
                    html.H3(value, className=f"mb-0 fw-bold text-{color}"),
                    html.Small(subtitle, className="text-muted") if subtitle else None,
                ],
                className="py-2 px-3",
            ),
            className="border-0 h-100",
            style={"backgroundColor": "rgba(44,62,80,0.5)"},
        ),
        xs=6,
        sm=6,
        md=3,
        lg=3,
        className="mb-3",
    )


def create_kpi_row(
    matches_played: str = "–",
    wins: str = "–",
    goals_scored: str = "–",
    clean_sheets: str = "–",
    mean_age: str = "–",
) -> dbc.Row:
    """Create the KPI cards row with provided values."""
    return dbc.Row(
        [
            kpi_card("Matches Played", matches_played, icon="bi-calendar-check"),
            kpi_card("Wins", wins, icon="bi-trophy", color="success"),
            kpi_card("Goals Scored", goals_scored, icon="bi-bullseye", color="danger"),
            kpi_card("Clean Sheets", clean_sheets, icon="bi-shield-check", color="info"),
            kpi_card("Mean Age", mean_age, icon="bi-people-fill", color="warning"),
        ],
        className="g-3",
        id="kpi-row",
    )


def empty_kpi_row() -> dbc.Row:
    """Return KPI row with placeholder values."""
    return create_kpi_row()
