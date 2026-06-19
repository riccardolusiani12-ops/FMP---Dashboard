"""
Opponent Analysis Page — Season-aggregate overview.

Routes: /team-analysis/opponent-analysis

Flow:
  1. User selects season + team  → four overview tiles appear
  2. Clicking "Offensive Phase"  → season-aggregate Offensive Phase view
  3. Other three tiles render as "Coming soon" placeholders

Store IDs used by analysis_callbacks._register_prefix (unchanged):
  opponent-selected-team      — team slug
  opponent-selected-match     — unused in season view (kept for compat)
  opponent-active-module      — unused in season view (kept for compat)

New store (season view only):
  opp-season-active-view      — "offensive" | None (controls which view shows)
"""

import dash_bootstrap_components as dbc
from dash import dcc, html

from src.config import AVAILABLE_SEASONS
from src.styling.ui_components import unified_dropdown


def layout() -> html.Div:
    """Return the Opponent Analysis page layout."""
    season_opts = [
        {"label": s.replace("_", "/"), "value": s}
        for s in AVAILABLE_SEASONS
    ]
    default_season = AVAILABLE_SEASONS[-1] if AVAILABLE_SEASONS else "2024_2025"

    return html.Div(
        [
            # Page header
            html.Div(
                [
                    html.A(
                        [html.I(className="bi bi-arrow-left me-2"), "Back"],
                        href="/team-analysis",
                        className="back-button",
                    ),
                    html.H2("Opponent Analysis", className="page-title"),
                ],
                className="page-header",
            ),

            # ── Stores ────────────────────────────────────────────────────────
            # Original three stores (still consumed by _register_prefix callbacks)
            dcc.Store(id="opponent-selected-team",  data=None),
            dcc.Store(id="opponent-selected-match", data=None),
            dcc.Store(id="opponent-active-module",  data=None),

            # Download sink (required by callback 9 in _register_prefix)
            dcc.Download(id="opponent-match-report-download"),

            # Season-level view store (new — owned by register_season_callbacks)
            dcc.Store(id="opp-season-active-view", data=None),
            # Carries {season, team} when Offensive Phase view is active;
            # triggers the three lazy-load section callbacks
            dcc.Store(id="opp-season-load-trigger", data=None),

            # ── Team selection ────────────────────────────────────────────────
            html.Div(
                [
                    html.Div(
                        [
                            html.P(
                                "Select a team to explore their season.",
                                className="page-subtitle",
                            ),
                            html.Div(
                                [
                                    html.Label("Season", className="filter-label"),
                                    unified_dropdown(
                                        "opponent-season-selector",
                                        season_opts,
                                        value=default_season,
                                        clearable=False,
                                    ),
                                ],
                                className="season-filter",
                            ),
                        ],
                        className="team-selection-header",
                    ),
                    dcc.Loading(
                        html.Div(id="opponent-teams-grid", className="teams-grid"),
                        type="circle",
                        color="#8a1f33",
                    ),
                ],
                id="opponent-team-selection",
            ),

            # ── Match list (kept for compat; hidden in season flow) ───────────
            html.Div(id="opponent-match-selection", style={"display": "none"}),

            # ── Season overview tiles + analysis content ──────────────────────
            # Shown once a team is selected; driven by opp-season-* callbacks
            html.Div(
                id="opp-season-content",
                style={"display": "none"},
            ),

            # ── Legacy analysis-content div (kept so _register_prefix callbacks
            #    don't break — they still Output to this id) ───────────────────
            html.Div(
                id="opponent-analysis-content",
                style={"display": "none"},
            ),
        ],
        className="page-container",
    )


# ─── Four overview tiles ──────────────────────────────────────────────────────

def _overview_tile(
    icon: str,
    title: str,
    desc: str,
    view_id: str,          # value stored in opp-season-active-view on click
    active: bool = False,  # False → coming-soon style
) -> html.Div:
    """One large clickable tile in the season overview grid."""
    if active:
        footer = html.Div(
            [
                html.I(className="bi bi-arrow-right me-1"),
                html.Span("Explore"),
            ],
            className="module-footer",
            style={"color": "var(--primary-light)"},
        )
        card_class = "module-card module-card-active"
        click_id   = {"type": "opp-season-tile", "index": view_id}
    else:
        footer = html.Div(
            html.Span("Coming soon", className="badge-coming-soon"),
            className="module-footer",
        )
        card_class = "module-card"
        click_id   = {"type": "opp-season-tile-soon", "index": view_id}

    return html.Div(
        [
            html.Div(html.I(className=f"bi {icon}"), className="module-icon"),
            html.Div(title, className="module-title"),
            html.Div(desc,  className="module-desc"),
            footer,
        ],
        className=card_class,
        id=click_id,
        n_clicks=0,
    )


def season_overview_tiles(team: str, season: str) -> html.Div:
    """
    Four-card season overview grid shown after team is selected.

    Parameters
    ----------
    team : str
        Canonical team name for the header.
    season : str
        Season key, e.g. ``"2025_2026"``.
    """
    season_label = season.replace("_", "/")
    return html.Div(
        [
            html.Div(
                [
                    html.Span(
                        [html.I(className="bi bi-arrow-left me-2"), "Back to Teams"],
                        id="opp-season-back-to-teams",
                        className="back-button",
                        n_clicks=0,
                        style={"cursor": "pointer"},
                    ),
                    html.H4(
                        f"{team} — {season_label}",
                        className="mb-0 ms-3 section-title",
                    ),
                ],
                className="d-flex align-items-center mb-4",
            ),
            html.P("Select a phase to begin.", className="page-subtitle",
                   style={"fontWeight": "400"}),
            html.Div(
                [
                    _overview_tile(
                        "bi-lightning-charge-fill",
                        "Offensive Phase Overview",
                        "GK build-up, final-third entries and chance creation — season aggregate.",
                        "offensive",
                        active=True,
                    ),
                    _overview_tile(
                        "bi-shield-fill",
                        "Defensive Phase Overview",
                        "Pressing intensity, defensive actions and defensive structure.",
                        "defensive",
                        active=True,
                    ),
                    _overview_tile(
                        "bi-arrow-left-right",
                        "Transitions Overview",
                        "Offensive and defensive transitions across the season.",
                        "transitions",
                        active=False,
                    ),
                    _overview_tile(
                        "bi-flag-fill",
                        "Set Pieces Overview",
                        "Corners, free kicks and throw-ins — season aggregate.",
                        "set_pieces",
                        active=False,
                    ),
                ],
                className="modules-grid",
            ),
        ]
    )
