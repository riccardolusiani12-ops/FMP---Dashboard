"""
Layout builder components for the Match Analysis and Opponent Analysis pages.

Extracted from src/callbacks/analysis_callbacks.py so that pure layout helpers
live in src/components/ and remain independently testable and reusable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import dash_bootstrap_components as dbc
from dash import dcc, html

from src.analytics.data_loader import load_season_matches_cached
from src.team_mapping import canonical_name, logo_url
from src.utils.logging import log
from src.utils.paths import list_match_files, parse_match_filename


# ---------------------------------------------------------------------------
# PRIVATE HELPERS
# ---------------------------------------------------------------------------

def _opponent_team(match_csv: Path, selected_team: str) -> str:
    info = parse_match_filename(match_csv)
    home = canonical_name(info["home"])
    away = canonical_name(info["away"])
    return away if canonical_name(selected_team).lower() == home.lower() else home


def _score_lookup(season: str) -> dict:
    """
    Return a dict keyed by (matchday_int, home_canonical, away_canonical)
    with value (home_goals, away_goals).
    """
    try:
        df = load_season_matches_cached(season)
        if df is None or df.empty:
            return {}
        out = {}
        for _, row in df.iterrows():
            key = (
                int(row.get("Matchday", 0)),
                str(row.get("Home", "")).strip(),
                str(row.get("Away", "")).strip(),
            )
            out[key] = (int(row.get("HG", 0)), int(row.get("AG", 0)))
        return out
    except Exception:
        return {}


def _safe_render(builder, *args) -> html.Div:
    """Call builder(*args) and return its result; on error return an alert."""
    try:
        return builder(*args)
    except Exception as exc:
        log.error("Error rendering analytics: %s", exc)
        return dbc.Alert(
            [html.I(className="bi bi-exclamation-triangle-fill me-2"),
             f"Could not render analytics: {exc}"],
            color="warning",
        )


def _offensive_phase(match_csv: Path, team: str) -> html.Div:
    from src.analytics.goalkeeper_buildup import analyse_goalkeeper_buildup
    from src.analytics.final_third import analyse_final_third
    from src.analytics.chance_creation import analyse_chance_creation
    from src.components.buildup_cards import goalkeeper_buildup_card
    from src.components.final_third_cards import final_third_card
    from src.components.chance_creation_cards import chance_creation_card

    return html.Div([
        _safe_render(goalkeeper_buildup_card, analyse_goalkeeper_buildup(match_csv, team)),
        html.Div(style={"height": "2rem"}),
        _safe_render(final_third_card, analyse_final_third(match_csv, team)),
        html.Div(style={"height": "2rem"}),
        _safe_render(chance_creation_card, analyse_chance_creation(match_csv, team)),
    ])


def _defensive_phase(match_csv: Path, team: str) -> html.Div:
    from src.analytics.defensive_pressing import analyse_defensive_pressing
    from src.analytics.defensive_structure import analyse_defensive_structure
    from src.components.defensive_pressing_cards import defensive_pressing_card
    from src.components.defensive_structure_cards import defensive_structure_card

    d1_data = analyse_defensive_pressing(match_csv, team)
    d2_data = analyse_defensive_structure(match_csv, team)

    # Pass D1 pressing_line_median into D2 data so the offside line chart
    # can overlay both reference lines without re-computing D1 metrics.
    d2_data["pressing_line_median"] = d1_data.get("pressing_line_median")

    # Pass offside line median into D1 data so the pressing pitch map can
    # overlay it as a purple dotted line alongside the pressing line.
    d1_data["offside_line_median"] = d2_data.get("offside_line_median")

    return html.Div([
        _safe_render(defensive_pressing_card, d1_data),
        html.Div(style={"height": "2rem"}),
        _safe_render(defensive_structure_card, d2_data),
    ])


# ---------------------------------------------------------------------------
# MATCH CARD  (grid card with logos, GW badge and result)
# ---------------------------------------------------------------------------

def _match_card(info: dict, prefix: str, score: Optional[tuple]) -> html.Div:
    """One card in the match-list grid — uses CSS .match-card classes."""
    home = canonical_name(info["home"])
    away = canonical_name(info["away"])
    gw   = info.get("week", "?")

    if score is not None:
        hg, ag = score
        score_el = html.Span(
            f"{hg} – {ag}",
            className="match-card-vs",
            style={"fontWeight": "700", "fontSize": "1.05rem",
                   "color": "var(--primary-light)"},
        )
    else:
        score_el = html.Span("vs", className="match-card-vs")

    return html.Div(
        html.Div(
            [
                html.Div(f"Gameweek {gw}", className="match-card-gw"),
                html.Div(
                    [
                        html.Div(
                            [
                                html.Img(src=logo_url(home),
                                         className="match-card-logo",
                                         alt=home),
                                html.Span(home, className="match-card-team-name"),
                            ],
                            className="match-card-team",
                        ),
                        score_el,
                        html.Div(
                            [
                                html.Img(src=logo_url(away),
                                         className="match-card-logo",
                                         alt=away),
                                html.Span(away, className="match-card-team-name"),
                            ],
                            className="match-card-team",
                        ),
                    ],
                    className="match-card-teams",
                ),
                html.Div(
                    [html.I(className="bi bi-geo-alt-fill me-1"),
                     html.Span(f"GW{gw}",
                               style={"fontSize": "0.75rem",
                                      "color": "var(--text-secondary)"}),
                    ],
                    className="match-card-venue",
                ),
            ],
            className="match-card",
        ),
        id={"type": f"{prefix}-match-item", "index": info["match_id"]},
        className="match-card-link",
        n_clicks=0,
    )


def _match_list_layout(season: str, team: str, prefix: str) -> html.Div:
    """Grid of match cards for the selected team, sorted by gameweek."""
    files      = list_match_files(season)
    team_lower = canonical_name(team).lower()
    scores     = _score_lookup(season)
    cards      = []

    for f in sorted(files, key=lambda p: int(parse_match_filename(p).get("week", 0) or 0)):
        info   = parse_match_filename(f)
        home_c = canonical_name(info["home"])
        away_c = canonical_name(info["away"])
        if team_lower not in (home_c.lower(), away_c.lower()):
            continue

        gw_int = int(info.get("week", 0) or 0)
        score  = scores.get((gw_int, home_c, away_c))
        cards.append(_match_card(info, prefix, score))

    if not cards:
        body = html.P(f"No matches found for {team} ({season.replace('_', '/')})",
                      className="text-muted")
    else:
        body = html.Div(cards, className="match-list-grid")

    return html.Div(
        [
            html.Div(
                [
                    html.Span(
                        [html.I(className="bi bi-arrow-left me-2"), "Back to Teams"],
                        id=f"{prefix}-back-to-teams",
                        className="back-button",
                        n_clicks=0,
                        style={"cursor": "pointer"},
                    ),
                    html.H4(f"Select a match \u2014 {team}",
                            className="mb-0 ms-3 section-title"),
                ],
                className="d-flex align-items-center mb-4",
            ),
            body,
        ]
    )


# ---------------------------------------------------------------------------
# MODULE SELECTOR  (phase cards after match is chosen)
# ---------------------------------------------------------------------------

def _module_card_active(icon: str, title: str, desc: str,
                         module_id: str, prefix: str) -> html.Div:
    return html.Div(
        [
            html.Div(html.I(className=f"bi {icon}"), className="module-icon"),
            html.Div(title,  className="module-title"),
            html.Div(desc,   className="module-desc"),
            html.Div(
                html.I(className="bi bi-arrow-right"),
                className="module-footer",
                style={"color": "var(--primary-light)"},
            ),
        ],
        className="module-card module-card-active",
        id={"type": f"{prefix}-module-card", "index": module_id},
        n_clicks=0,
    )


def _module_card_soon(icon: str, title: str, desc: str) -> html.Div:
    return html.Div(
        [
            html.Div(html.I(className=f"bi {icon}"), className="module-icon"),
            html.Div(title, className="module-title"),
            html.Div(desc,  className="module-desc"),
            html.Div(
                html.Span("Coming soon", className="badge-coming-soon"),
                className="module-footer",
            ),
        ],
        className="module-card",
    )


def _module_selector(match_label: str, prefix: str) -> html.Div:
    """Four-card module grid shown after a match is selected."""
    return html.Div(
        [
            html.Div(
                [
                    html.Span(
                        [html.I(className="bi bi-arrow-left me-2"), "Back to Matches"],
                        id=f"{prefix}-back-to-matches",
                        className="back-button",
                        n_clicks=0,
                        style={"cursor": "pointer"},
                    ),
                    html.H4(match_label,
                            className="mb-0 ms-3 section-title"),
                ],
                className="d-flex align-items-center mb-4",
            ),
            html.P("Select an analysis module to begin.",
                   className="page-subtitle",
                   style={"fontWeight": "400"}),

            html.Div(
                [
                    _module_card_active(
                        "bi-lightning-charge-fill",
                        "Offensive Phase",
                        "Goal-kick build-up, final third entries and chance creation.",
                        "offensive",
                        prefix,
                    ),
                    _module_card_active(
                        "bi-shield-fill",
                        "Defensive Phase",
                        "Pressing intensity, defensive actions and PPDA.",
                        "defensive",
                        prefix,
                    ),
                    _module_card_soon(
                        "bi-flag-fill",
                        "Set Pieces",
                        "Corner kicks, free kicks and throw-in analysis.",
                    ),
                    _module_card_soon(
                        "bi-file-earmark-pdf-fill",
                        "Match Report PDF",
                        "Export a full post-match report as a downloadable PDF.",
                    ),
                ],
                className="modules-grid",
            ),
        ]
    )


# ---------------------------------------------------------------------------
# ANALYSIS VIEW
# ---------------------------------------------------------------------------

def _analysis_view(match_csv: Path, team: str, match_label: str,
                   module: str, prefix: str) -> html.Div:
    """Full analysis view: header with back-to-modules + analysis content."""
    opponent = _opponent_team(match_csv, team)
    perspective = team if prefix == "ma" else opponent

    if module == "offensive":
        module_title = "Offensive Phase"
        icon_cls     = "bi bi-lightning-charge-fill"
        content      = dcc.Loading(
            _offensive_phase(match_csv, perspective),
            type="circle", color="#8a1f33",
        )
    else:
        module_title = "Defensive Phase"
        icon_cls     = "bi bi-shield-fill"
        content      = dcc.Loading(
            _defensive_phase(match_csv, perspective),
            type="circle", color="#8a1f33",
        )

    return html.Div(
        [
            # Navigation row: Back to Matches | Back to Modules | module title
            html.Div(
                [
                    html.Span(
                        [html.I(className="bi bi-arrow-left me-2"), "Back to Matches"],
                        id=f"{prefix}-back-to-matches",
                        className="back-button",
                        n_clicks=0,
                        style={"cursor": "pointer"},
                    ),
                    html.Span(
                        [html.I(className="bi bi-grid me-2"), "Back to Modules"],
                        id=f"{prefix}-back-to-modules",
                        className="back-button",
                        n_clicks=0,
                        style={"cursor": "pointer"},
                    ),
                    html.I(className=f"{icon_cls} me-2",
                           style={"color": "var(--primary-light)"}),
                    html.H4(f"{module_title} \u2014 {match_label}",
                            className="mb-0 ms-2 section-title"),
                ],
                className="d-flex align-items-center mb-4",
            ),
            content,
        ]
    )
