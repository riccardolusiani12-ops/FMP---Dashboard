"""
Team Detail page callbacks — load standings chart and KPIs for selected team.

Refactored to use precomputed Parquet tables via data_loader.
Callbacks now perform lightweight filter + render operations instead of
re-reading hundreds of raw CSV files.

The team is fixed for the page; the season is selectable from the header.
KPIs: League Position · Last 5 Form · Goal Difference.
"""

from __future__ import annotations

from dash import Input, Output, State, html, dcc, no_update, ctx, ALL
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

from src.team_mapping import logo_url
from src.styling.theme import SEMANTIC_COLORS
from src.styling.plotly_template import apply_chart_theme
from src.analytics.multi_season_standings import build_standings_figure
from src.analytics.ppda import build_ppda_bar_figure, build_ppda_scatter_figure
from src.analytics.formations import build_formation_pitch_figure
from src.analytics.data_loader import (
    load_standings,
    load_points_progression,
    load_all_points_progression,
    load_ppda_summary,
    load_team_overview,
    load_formation_counts,
    load_formation_lineup,
    load_formation_positions,
    load_xg_summary,
    load_goal_distribution,
    load_team_average_age,
    load_playing_style,
)
from src.styling.ui_components import build_unified_modal


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """'#22c55e' → (34, 197, 94) — for building rgba() intensity fills."""
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


# Harmonised good/bad pair used across this page's KPI cards, form badges,
# goal tiles and goals-vs-xG bars (Phase 1: was #00CC96 / #EF553B).
_GREEN = SEMANTIC_COLORS["goals_scored"]     # "#22c55e"
_RED = SEMANTIC_COLORS["goals_conceded"]     # "#ef4444"


def register_team_detail_callbacks(app):
    """Register callbacks for the team detail page."""

    # ── 1. Initial page load: set logo ──
    @app.callback(
        Output("team-detail-logo", "src"),
        Input("team-context", "data"),
        prevent_initial_call=False,
    )
    def set_team_logo(context: dict):
        """Set the team logo once on page load."""
        team = context.get("team", "")
        return logo_url(team) if team else ""

    # ── 2. Chart: Points Progression (all seasons, highlight selected) ──
    @app.callback(
        Output("standings-chart", "figure"),
        Input("team-context", "data"),
        Input("team-season-selector", "value"),
        Input("theme-store", "data"),
        prevent_initial_call=False,
    )
    def update_chart(context: dict, selected_season: str, theme: str):
        """Build the points progression chart for the selected team."""
        team = context.get("team", "")

        # Load all-season progression from precomputed Parquet
        progression = load_all_points_progression()

        # Official final/current rank for the highlighted season — feeds the
        # end-of-line position badge (presentation only).
        final_pos = None
        if team and selected_season:
            standings = load_standings(selected_season)
            if not standings.empty:
                trow = standings[standings["Team"] == team]
                if not trow.empty and "Rank" in trow.columns:
                    final_pos = _ordinal(int(trow.iloc[0]["Rank"]))

        highlight = selected_season.replace("_", "/") if selected_season else ""
        fig = build_standings_figure(
            progression,
            team=team,
            highlight_season=highlight,
            theme=theme or "dark",
            final_position=final_pos,
        )
        return fig

    # ── 2b. Season selector pills (mirror of the header dropdown) ──
    @app.callback(
        Output("season-pills-row", "children"),
        Input("team-season-selector", "value"),
        prevent_initial_call=False,
    )
    def update_season_pills(selected_season: str):
        """Render one pill per season; the selected one is accent-filled."""
        from src.config import AVAILABLE_SEASONS
        pills = []
        for s in AVAILABLE_SEASONS:
            active = (s == selected_season)
            pills.append(
                html.Button(
                    s.replace("_", "/"),
                    id={"type": "season-pill", "index": s},
                    className=(
                        "season-pill season-pill--active" if active
                        else "season-pill"
                    ),
                    n_clicks=0,
                )
            )
        return pills

    @app.callback(
        Output("team-season-selector", "value"),
        Input({"type": "season-pill", "index": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def select_season_pill(n_clicks_list):
        """Pill click → set the existing season dropdown value (single source
        of truth), so every season-driven callback fires exactly as before."""
        if not n_clicks_list or not any(n_clicks_list):
            return no_update
        triggered = ctx.triggered_id
        if not triggered:
            return no_update
        return triggered["index"]

    # ── 3. KPIs: react to season selector ──
    @app.callback(
        Output("team-kpi-row", "children"),
        Input("team-season-selector", "value"),
        Input("team-context", "data"),
        prevent_initial_call=False,
    )
    def update_kpis(selected_season: str, context: dict):
        """Build dynamic KPI cards for the selected team & season."""
        team = context.get("team", "")
        return _build_kpis(team, selected_season)

    # ── KPI builder ──────────────────────────────────────────────

    def _build_kpis(team: str, season_key: str) -> list:
        """Build KPI cards: League Position, Last 5 Form, Goal Difference, PPG, Mean Age."""
        if not team or not season_key:
            return []

        season_label = season_key.replace("_", "/") if season_key else ""

        # Load precomputed standings (fast Parquet read)
        standings = load_standings(season_key)
        if standings.empty:
            return [
                _kpi_card("Position", "–", "bi-trophy-fill", "#636EFA"),
                _record_card(0, 0, 0, empty=True),
                _form_card([]),
                _kpi_card("Goal Diff.", "–", "bi-bullseye", "#FFA15A"),
                _kpi_card("PPG", "–", "bi-star-fill", "#19D3F3"),
                _kpi_card("Mean Age", "–", "bi-people-fill", "#FFA15A"),
            ]

        team_row = standings[standings["Team"] == team]
        if team_row.empty:
            return [
                _kpi_card("Position", "–", "bi-trophy-fill", "#636EFA"),
                _record_card(0, 0, 0, empty=True),
                _form_card([]),
                _kpi_card("Goal Diff.", "–", "bi-bullseye", "#FFA15A"),
                _kpi_card("PPG", "–", "bi-star-fill", "#19D3F3"),
                _kpi_card("Mean Age", "–", "bi-people-fill", "#FFA15A"),
            ]

        row = team_row.iloc[0]
        position = int(row["Rank"]) if "Rank" in row.index else 0
        gd = int(row["GD"])
        mp = int(row["MP"]) if "MP" in row.index else 0
        pts = int(row["Points"]) if "Points" in row.index else 0

        pos_str = _ordinal(position) if position > 0 else "–"

        # PPG = Points Per Game
        ppg = pts / mp if mp > 0 else 0.0
        ppg_str = f"{ppg:.2f}"
        # Color: green if >= 2.0, orange if >= 1.3, red otherwise
        ppg_color = _GREEN if ppg >= 2.0 else ("#FFA15A" if ppg >= 1.3 else _RED)

        # Last 5 results from precomputed progression
        last_5 = _get_last_5(team, season_key)

        # Goal difference color
        gd_color = _GREEN if gd > 0 else (_RED if gd < 0 else "#8899aa")

        # Mean Age from Transfermarkt scrape
        avg_age = load_team_average_age(team, season_key)
        if avg_age is not None:
            age_str = f"{avg_age:.1f}"
            # Color: green if < 26 (young), orange if 26-28 (balanced), red if > 28 (old)
            age_color = _GREEN if avg_age < 26 else ("#FFA15A" if avg_age <= 28 else _RED)
        else:
            age_str = "–"
            age_color = "#8899aa"

        w = int(row["W"]) if "W" in row.index else 0
        d = int(row["D"]) if "D" in row.index else 0
        l = int(row["L"]) if "L" in row.index else 0

        kpis = [
            _kpi_card("Position", pos_str, "bi-trophy-fill", "#636EFA"),
            _record_card(w, d, l),
            _form_card(last_5),
            _kpi_card("Goal Diff.", f"{gd:+d}", "bi-bullseye", gd_color),
            _kpi_card("PPG", ppg_str, "bi-star-fill", ppg_color),
            _kpi_card("Mean Age", age_str, "bi-people-fill", age_color),
        ]
        return kpis

    def _get_last_5(team: str, season_key: str) -> list[str]:
        """Get last 5 match results (W/D/L) from precomputed data."""
        progression = load_points_progression(season_key)
        if progression.empty:
            return []

        season_label = season_key.replace("_", "/")
        tdf = progression[
            (progression["Team"] == team) &
            (progression["Season"] == season_label)
        ].sort_values("Matchday")

        if tdf.empty:
            return []

        results = tdf["Result"].tolist()
        return results[-5:]

    def _ordinal(n: int) -> str:
        """Return ordinal string: 1st, 2nd, 3rd, 4th, ..."""
        if 11 <= (n % 100) <= 13:
            suffix = "th"
        else:
            suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
        return f"{n}{suffix}"

    def _kpi_card(title: str, value: str, icon: str, color: str) -> html.Div:
        """Create a single KPI card."""
        return html.Div(
            [
                html.Div(
                    html.I(className=f"bi {icon}"),
                    className="kpi-icon",
                    style={"color": color},
                ),
                html.Div(
                    [
                        html.Span(title, className="kpi-label"),
                        html.Span(value, className="kpi-value", style={"color": color}),
                    ],
                    className="kpi-text",
                ),
            ],
            className="kpi-card",
        )

    def _record_card(w: int, d: int, l: int, empty: bool = False) -> html.Div:
        """Create the Season Record KPI card showing W · D · L with letter labels."""
        icon_color = _GREEN if (not empty and w > l) else (_RED if (not empty and l > w) else "#8899aa")

        if empty:
            record_content = html.Span("–", className="kpi-value", style={"color": "#8899aa"})
        else:
            record_content = html.Div(
                [
                    html.Div(
                        [
                            html.Span(str(w), className="record-num", style={"color": _GREEN}),
                            html.Span("W", className="record-ltr"),
                        ],
                        className="record-cell",
                    ),
                    html.Span("·", className="record-dot"),
                    html.Div(
                        [
                            html.Span(str(d), className="record-num", style={"color": "#8899aa"}),
                            html.Span("D", className="record-ltr"),
                        ],
                        className="record-cell",
                    ),
                    html.Span("·", className="record-dot"),
                    html.Div(
                        [
                            html.Span(str(l), className="record-num", style={"color": _RED}),
                            html.Span("L", className="record-ltr"),
                        ],
                        className="record-cell",
                    ),
                ],
                className="record-row",
            )

        return html.Div(
            [
                html.Div(
                    html.I(className="bi bi-clipboard-data-fill"),
                    className="kpi-icon",
                    style={"color": icon_color},
                ),
                html.Div(
                    [
                        html.Span("Season Record", className="kpi-label"),
                        record_content,
                    ],
                    className="kpi-text",
                ),
            ],
            className="kpi-card",
        )

    def _form_card(results: list[str]) -> html.Div:
        """Create the Last 5 Form KPI card with colored badges."""
        color_map = {
            "W": _GREEN,  # green
            "D": "#8899aa",  # grey
            "L": _RED,  # red
        }

        if not results:
            badges = [html.Span("–", className="form-badge",
                                style={"backgroundColor": "#8899aa"})]
        else:
            badges = [
                html.Span(
                    r,
                    className="form-badge",
                    style={"backgroundColor": color_map.get(r, "#8899aa")},
                )
                for r in results
            ]

        return html.Div(
            [
                html.Div(
                    html.I(className="bi bi-bar-chart-fill"),
                    className="kpi-icon",
                    style={"color": "#AB63FA"},
                ),
                html.Div(
                    [
                        html.Span("Last 5", className="kpi-label"),
                        html.Div(badges, className="form-badges-row"),
                    ],
                    className="kpi-text",
                ),
            ],
            className="kpi-card",
        )

    # ══════════════════════════════════════════════════════════
    # PPDA SECTION CALLBACKS
    # ══════════════════════════════════════════════════════════

    # ── 4. PPDA Bar Chart ──
    @app.callback(
        Output("ppda-bar-chart", "figure"),
        Input("team-season-selector", "value"),
        Input("team-context", "data"),
        prevent_initial_call=False,
    )
    def update_ppda_bar(selected_season: str, context: dict):
        """Build the PPDA ranking bar chart from precomputed data."""
        team = context.get("team", "")
        ppda_df = load_ppda_summary(selected_season)
        return build_ppda_bar_figure(ppda_df, highlight_team=team)

    # ── 5. PPDA Scatter Chart ──
    @app.callback(
        Output("ppda-scatter-chart", "figure"),
        Input("team-season-selector", "value"),
        Input("team-context", "data"),
        prevent_initial_call=False,
    )
    def update_ppda_scatter(selected_season: str, context: dict):
        """Build the PPDA vs regain scatter chart from precomputed data."""
        team = context.get("team", "")
        ppda_df = load_ppda_summary(selected_season)
        return build_ppda_scatter_figure(ppda_df, highlight_team=team)

    # ── 6. PPDA KPI Cards ──
    @app.callback(
        Output("ppda-kpi-row", "children"),
        Input("team-season-selector", "value"),
        Input("team-context", "data"),
        prevent_initial_call=False,
    )
    def update_ppda_kpis(selected_season: str, context: dict):
        """Build PPDA-specific KPI cards from precomputed data."""
        team = context.get("team", "")
        ppda_df = load_ppda_summary(selected_season)
        return _build_ppda_kpis(team, ppda_df)

    def _build_ppda_kpis(team: str, ppda_df) -> list:
        """Build PPDA KPI cards: Rank, PPDA Value, Mean Seconds, Pressing Tier."""
        if ppda_df is None or ppda_df.empty or not team:
            return [
                _kpi_card("PPDA Rank", "–", "bi-bar-chart-steps", "#636EFA"),
                _kpi_card("PPDA", "–", "bi-speedometer2", "#FFA15A"),
                _kpi_card("Field Tilt %", "–", "bi-shield-fill", "#19D3F3"),
                _kpi_card("Pressing Tier", "–", "bi-layers-fill", "#AB63FA"),
            ]

        team_row = ppda_df[ppda_df["team_short"] == team]
        if team_row.empty:
            return [
                _kpi_card("PPDA Rank", "–", "bi-bar-chart-steps", "#636EFA"),
                _kpi_card("PPDA", "–", "bi-speedometer2", "#FFA15A"),
                _kpi_card("Field Tilt %", "–", "bi-shield-fill", "#19D3F3"),
                _kpi_card("Pressing Tier", "–", "bi-layers-fill", "#AB63FA"),
            ]

        row = team_row.iloc[0]
        rank = int(row["rank"])
        total = len(ppda_df)
        ppda_val = row["PPDA"]
        field_tilt = row.get("field_tilt", None)

        # Rank string
        rank_str = f"{_ordinal(rank)}"
        rank_color = _GREEN if rank <= total * 0.33 else (
            "#FFA15A" if rank <= total * 0.66 else _RED
        )

        # PPDA value
        ppda_str = f"{ppda_val:.2f}"
        ppda_color = _GREEN if ppda_val < ppda_df["PPDA"].median() else _RED

        # Field Tilt percentage
        if field_tilt is not None and not (isinstance(field_tilt, float) and field_tilt != field_tilt):
            tilt_str = f"{field_tilt:.1f}%"
            tilt_color = _GREEN if field_tilt > ppda_df["field_tilt"].median() else "#FFA15A"
        else:
            tilt_str = "–"
            tilt_color = "#8899aa"

        # Pressing tier (percentile-based)
        percentile = (1 - (rank - 1) / max(total - 1, 1)) * 100
        if percentile >= 80:
            tier = "Elite"
            tier_color = _GREEN
        elif percentile >= 60:
            tier = "High"
            tier_color = "#19D3F3"
        elif percentile >= 40:
            tier = "Medium"
            tier_color = "#FFA15A"
        elif percentile >= 20:
            tier = "Low"
            tier_color = _RED
        else:
            tier = "Passive"
            tier_color = _RED

        return [
            _kpi_card("PPDA Rank", rank_str, "bi-bar-chart-steps", rank_color),
            _kpi_card("PPDA", ppda_str, "bi-speedometer2", ppda_color),
            _kpi_card("Field Tilt %", tilt_str, "bi-shield-fill", tilt_color),
            _kpi_card("Pressing Tier", tier, "bi-layers-fill", tier_color),
        ]

    # ══════════════════════════════════════════════════════════
    # FORMATIONS SECTION CALLBACK
    # ══════════════════════════════════════════════════════════

    @app.callback(
        Output("formations-row", "children"),
        Output("selected-formation-store", "data"),
        Input("team-season-selector", "value"),
        Input("team-context", "data"),
        prevent_initial_call=False,
    )
    def update_formations(selected_season: str, context: dict):
        """Build the formations visual block from precomputed/raw data."""
        team = context.get("team", "")
        if not team or not selected_season:
            return html.P("Select a team and season.", className="text-muted"), None

        formations = load_formation_counts(team, selected_season, min_count=3)

        if formations.empty:
            return html.Div(
                [
                    html.I(className="bi bi-info-circle me-2",
                           style={"fontSize": "1.2rem", "opacity": 0.5}),
                    html.P(
                        "No formations used 3 or more times this season.",
                        className="text-muted mb-0",
                    ),
                ],
                className="formations-empty",
                style={"display": "flex", "alignItems": "center",
                       "justifyContent": "center", "padding": "2rem"},
            ), None

        cards = []
        for i, row in formations.iterrows():
            form_str = row["formation_str"]
            count = int(row["count"])
            pct = float(row["pct"])

            lineup_df   = load_formation_lineup(team, selected_season, form_str)
            positions_df = load_formation_positions(team, selected_season, form_str)
            fig = build_formation_pitch_figure(
                form_str, count=count, pct=pct,
                lineup_df=lineup_df if not lineup_df.empty else None,
                positions_df=positions_df if not positions_df.empty else None,
            )

            rank_labels = ["Most Used", "2nd Most Used", "3rd Most Used"]
            rank_label = rank_labels[i] if i < len(rank_labels) else ""

            card = html.Div(
                [
                    html.Div(rank_label, className="formation-rank-badge"),
                    html.H5(form_str, className="formation-name"),
                    dcc.Graph(
                        figure=fig,
                        config={"displayModeBar": False},
                        responsive=False,
                        className="formation-pitch",
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Span("Times Used", className="formation-stat-label"),
                                    html.Span(str(count), className="formation-stat-value"),
                                ],
                                className="formation-stat",
                            ),
                            html.Div(
                                [
                                    html.Span("Share", className="formation-stat-label"),
                                    html.Span(f"{pct:.0f}%", className="formation-stat-value"),
                                ],
                                className="formation-stat",
                            ),
                        ],
                        className="formation-stats-row",
                    ),
                    html.Div(
                        [
                            html.I(className="bi bi-people-fill me-1"),
                            html.Span("View Squad"),
                        ],
                        className="formation-view-lineup-btn",
                    ),
                ],
                id={"type": "formation-card", "index": form_str},
                className="formation-card formation-card-clickable",
                n_clicks=0,
            )
            cards.append(card)

        return cards, None

    # ══════════════════════════════════════════════════════════
    # FORMATION CARD CLICK → STORE SELECTED FORMATION
    # ══════════════════════════════════════════════════════════

    @app.callback(
        Output("selected-formation-store", "data", allow_duplicate=True),
        Input({"type": "formation-card", "index": ALL}, "n_clicks"),
        State("selected-formation-store", "data"),
        prevent_initial_call=True,
    )
    def select_formation_card(n_clicks_list, current_selection):
        if not any(n_clicks_list):
            return no_update
        triggered = ctx.triggered_id
        if not triggered:
            return no_update
        clicked_formation = triggered["index"]
        # Toggle off if clicking the already-selected card
        if current_selection == clicked_formation:
            return None
        return clicked_formation

    # ══════════════════════════════════════════════════════════
    # FORMATION LINEUP PANEL CALLBACK
    # ══════════════════════════════════════════════════════════

    @app.callback(
        Output("formation-lineup-panel", "children"),
        Output("formation-lineup-panel", "style"),
        Input("selected-formation-store", "data"),
        State("team-context", "data"),
        State("team-season-selector", "value"),
        prevent_initial_call=True,
    )
    def update_formation_lineup(formation_str, context, selected_season):
        """Render the per-position player stats panel for the selected formation."""
        if not formation_str:
            return [], {"display": "none"}

        team = (context or {}).get("team", "")
        if not team or not selected_season:
            return [], {"display": "none"}

        df = load_formation_lineup(team, selected_season, formation_str)
        if df.empty:
            return (
                html.P("No lineup data available for this formation.",
                       className="text-muted p-3"),
                {"display": "block"},
            )

        pos_label_color = {"GK": "#3cb371", "DEF": "#8a1f33", "MID": "#4a90d9", "FWD": "#f5a623"}

        # Build one player card per SLOT (top contributor only for the pitch marker)
        top_per_slot = df.drop_duplicates("slot").set_index("slot")

        # --- Build player cards list (all players, grouped by slot) ---
        slot_groups = df.groupby("slot")
        slots_sorted = sorted(slot_groups.groups.keys())

        player_cards = []
        for slot in slots_sorted:
            group = slot_groups.get_group(slot)
            # Position badge colour
            pos_label = group.iloc[0]["pos_label"]
            badge_color = pos_label_color.get(pos_label, "#666")

            for _, player in group.iterrows():
                is_top = player["starts"] == group["starts"].max() and group.index[0] == player.name
                card = html.Div(
                    [
                        # Jersey + pos badge
                        html.Div(
                            [
                                html.Span(
                                    f"#{player['jersey']}",
                                    className="flp-jersey",
                                ),
                                html.Span(
                                    pos_label,
                                    className="flp-pos-badge",
                                    style={"background": badge_color},
                                ),
                            ],
                            className="flp-header",
                        ),
                        # Player name
                        html.Div(player["name"], className="flp-name"),
                        # Stats
                        html.Div(
                            [
                                html.Div([
                                    html.Span("Starts", className="flp-stat-label"),
                                    html.Span(str(player["starts"]), className="flp-stat-value"),
                                ], className="flp-stat"),
                                html.Div([
                                    html.Span("Minutes", className="flp-stat-label"),
                                    html.Span(str(player["total_mins"]), className="flp-stat-value"),
                                ], className="flp-stat"),
                                html.Div([
                                    html.Span("Avg Min", className="flp-stat-label"),
                                    html.Span(str(player["avg_mins_per_start"]), className="flp-stat-value"),
                                ], className="flp-stat"),
                            ],
                            className="flp-stats-row",
                        ),
                    ],
                    className=f"flp-player-card{'  flp-player-card--primary' if is_top else ' flp-player-card--depth'}",
                )
                player_cards.append(card)

        panel_content = html.Div(
            [
                # Panel header
                html.Div(
                    [
                        html.Div(
                            [
                                html.I(className="bi bi-people-fill me-2"),
                                html.Span(
                                    f"Most Used Players — {formation_str}",
                                    className="flp-panel-title",
                                ),
                            ],
                            className="flp-panel-header-left",
                        ),
                        html.Div(
                            "Click the active formation card again to close",
                            className="flp-panel-hint",
                        ),
                    ],
                    className="flp-panel-header",
                ),
                # Player cards grid
                html.Div(player_cards, className="flp-cards-grid"),
            ],
            className="flp-panel-inner",
        )

        return panel_content, {"display": "block"}

    # ══════════════════════════════════════════════════════════
    # GOALS & xG SECTION CALLBACK
    # ══════════════════════════════════════════════════════════

    @app.callback(
        Output("goals-xg-block", "children"),
        Input("team-season-selector", "value"),
        Input("team-context", "data"),
        Input("theme-store", "data"),
        prevent_initial_call=False,
    )
    def update_goals_xg(selected_season: str, context: dict, theme: str):
        """Build the goals & xG stats block."""
        team = context.get("team", "")
        if not team or not selected_season:
            return html.P("Select a team and season.", className="text-muted")

        xg_df = load_xg_summary(selected_season)

        if xg_df is None or xg_df.empty:
            # Fallback: show only goals from standings
            return _build_goals_only_block(team, selected_season)

        team_row = xg_df[xg_df["Team"] == team]
        if team_row.empty:
            return _build_goals_only_block(team, selected_season)

        row = team_row.iloc[0]
        xg_val = float(row["xG"])
        xgc_val = float(row["xGC"])

        # Use standings for official GF/GA (includes own goals)
        standings = load_standings(selected_season)
        st_row = standings[standings["Team"] == team]
        if not st_row.empty:
            gf = int(st_row.iloc[0]["GF"])
            ga = int(st_row.iloc[0]["GA"])
        else:
            gf = int(row["GF"])
            ga = int(row["GA"])

        # xG performance indicators
        xg_over = gf - xg_val  # > 0 = over-performing xG
        xgc_over = ga - xgc_val  # > 0 = under-performing defensively

        # Build KPI cards + bar chart
        kpi_cards = html.Div(
            [
                _stat_card("Goals Scored", str(gf), f"xG: {xg_val:.1f}",
                           "bi-bullseye", _GREEN,
                           interval_button_id="td-scored-interval-open",
                           league_button_id="td-goals-scored-league-open"),
                _stat_card("Goals Conceded", str(ga), f"xGC: {xgc_val:.1f}",
                           "bi-shield-x", _RED,
                           interval_button_id="td-conceded-interval-open",
                           league_button_id="td-goals-conceded-league-open"),
                _stat_card("xG", f"{xg_val:.1f}",
                           f"{'↑' if xg_over >= 0 else '↓'} {abs(xg_over):.1f} vs actual",
                           "bi-graph-up-arrow",
                           _GREEN if xg_over >= 0 else "#FFA15A",
                           league_button_id="td-xg-league-open"),
                _stat_card("xGC", f"{xgc_val:.1f}",
                           f"{'↑' if xgc_over > 0 else '↓'} {abs(xgc_over):.1f} vs actual",
                           "bi-graph-down-arrow",
                           _GREEN if xgc_over <= 0 else _RED,
                           league_button_id="td-xgc-league-open"),
            ],
            className="goals-xg-kpi-row",
        )

        # Build comparison bar chart
        bar_fig = _build_goals_xg_bar_chart(gf, ga, xg_val, xgc_val, team,
                                             theme=theme or "dark")

        chart_div = html.Div(
            dcc.Graph(
                figure=bar_fig,
                config={"displayModeBar": False},
                className="goals-xg-chart",
            ),
            className="goals-xg-chart-container",
        )

        return html.Div([kpi_cards, chart_div])

    def _build_goals_only_block(team: str, season_key: str) -> html.Div:
        """Fallback block showing only goals (no xG data)."""
        standings = load_standings(season_key)
        if standings.empty:
            return html.P("No data available.", className="text-muted")

        team_row = standings[standings["Team"] == team]
        if team_row.empty:
            return html.P("No data for this team.", className="text-muted")

        row = team_row.iloc[0]
        gf = int(row["GF"])
        ga = int(row["GA"])

        return html.Div(
            [
                _stat_card("Goals Scored", str(gf), "", "bi-bullseye", _GREEN,
                           interval_button_id="td-scored-interval-open",
                           league_button_id="td-goals-scored-league-open"),
                _stat_card("Goals Conceded", str(ga), "", "bi-shield-x", _RED,
                           interval_button_id="td-conceded-interval-open",
                           league_button_id="td-goals-conceded-league-open"),
                html.Div(
                    [
                        html.I(className="bi bi-info-circle me-1",
                               style={"opacity": 0.5}),
                        html.Small(
                            "xG data not yet available for this season.",
                            className="text-muted",
                        ),
                    ],
                    style={"display": "flex", "alignItems": "center",
                           "padding": "0.5rem 0"},
                ),
            ],
            className="goals-xg-kpi-row",
        )

    def _stat_card(
        title: str, value: str, subtitle: str, icon: str, color: str,
        interval_button_id: str | None = None,
        league_button_id: str | None = None,
    ) -> html.Div:
        """Create a stat card for the goals/xG block."""
        text_children = [
            html.Span(title, className="kpi-label"),
            html.Span(value, className="kpi-value", style={"color": color}),
            html.Small(subtitle, className="kpi-subtitle text-muted")
            if subtitle else None,
        ]
        if interval_button_id:
            text_children.append(
                html.Button(
                    [html.I(className="bi bi-clock-history me-1"), "View Breakdown"],
                    id=interval_button_id,
                    n_clicks=0,
                    className="kpi-interval-btn",
                )
            )
        if league_button_id:
            text_children.append(
                html.Button(
                    [html.I(className="bi bi-bar-chart-fill me-1"), "League Comparison"],
                    id=league_button_id,
                    n_clicks=0,
                    className="kpi-interval-btn",
                )
            )
        children = [
            html.Div(
                html.I(className=f"bi {icon}"),
                className="kpi-icon",
                style={"color": color},
            ),
            html.Div(
                [c for c in text_children if c is not None],
                className="kpi-text",
            ),
        ]
        return html.Div(
            children,
            className="kpi-card",
        )

    def _build_goals_xg_bar_chart(
        gf: int, ga: int, xg: float, xgc: float, team: str, theme: str = "dark"
    ) -> go.Figure:
        """Build a grouped bar chart comparing Goals vs xG."""
        categories = ["Goals Scored", "Goals Conceded"]
        actual_vals = [gf, ga]
        expected_vals = [xg, xgc]

        green_rgb = _hex_to_rgb(_GREEN)
        red_rgb = _hex_to_rgb(_RED)

        fig = go.Figure()

        fig.add_trace(go.Bar(
            x=categories,
            y=actual_vals,
            name="Actual",
            marker_color=[_GREEN, _RED],
            text=[str(v) for v in actual_vals],
            textposition="outside",
            textfont=dict(size=13),
        ))

        fig.add_trace(go.Bar(
            x=categories,
            y=expected_vals,
            name="Expected (xG)",
            marker_color=[
                f"rgba({green_rgb[0]},{green_rgb[1]},{green_rgb[2]},0.35)",
                f"rgba({red_rgb[0]},{red_rgb[1]},{red_rgb[2]},0.35)",
            ],
            marker_line=dict(
                color=[_GREEN, _RED],
                width=2,
            ),
            text=[f"{v:.1f}" for v in expected_vals],
            textposition="outside",
            textfont=dict(size=13),
        ))

        apply_chart_theme(fig, theme)
        fig.update_layout(
            title=dict(text=f"Goals vs Expected Goals — {team}"),
            barmode="group",
            xaxis=dict(tickfont=dict(size=12), showgrid=False),
            yaxis=dict(title="Count", tickfont=dict(size=11)),
            height=360,
            margin=dict(t=60, l=50, r=30, b=50),
        )

        return fig

    # ══════════════════════════════════════════════════════════
    # GOAL DISTRIBUTION MODALS — OPEN / CLOSE
    # ══════════════════════════════════════════════════════════

    @app.callback(
        Output("td-scored-interval-modal", "is_open"),
        Input("td-scored-interval-open", "n_clicks"),
        State("td-scored-interval-modal", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_scored_interval_modal(n_clicks, is_open):
        if n_clicks:
            return not is_open
        return is_open

    @app.callback(
        Output("td-conceded-interval-modal", "is_open"),
        Input("td-conceded-interval-open", "n_clicks"),
        State("td-conceded-interval-modal", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_conceded_interval_modal(n_clicks, is_open):
        if n_clicks:
            return not is_open
        return is_open

    # ── Modal body: Goals Scored intervals ──
    @app.callback(
        Output("td-scored-interval-modal-body", "children"),
        Input("td-scored-interval-open", "n_clicks"),
        State("team-season-selector", "value"),
        State("team-context", "data"),
        prevent_initial_call=True,
    )
    def load_scored_interval_modal(n_clicks, selected_season, context):
        if not n_clicks:
            return no_update
        team = (context or {}).get("team", "")
        if not team or not selected_season:
            return html.P("Select a team and season.", className="text-muted")
        dist_df = load_goal_distribution(team, selected_season)
        if dist_df is None or dist_df.empty:
            return html.P("No data available.", className="text-muted")
        return _build_single_metric_card(dist_df, metric="scored")

    # ── Modal body: Goals Conceded intervals ──
    @app.callback(
        Output("td-conceded-interval-modal-body", "children"),
        Input("td-conceded-interval-open", "n_clicks"),
        State("team-season-selector", "value"),
        State("team-context", "data"),
        prevent_initial_call=True,
    )
    def load_conceded_interval_modal(n_clicks, selected_season, context):
        if not n_clicks:
            return no_update
        team = (context or {}).get("team", "")
        if not team or not selected_season:
            return html.P("Select a team and season.", className="text-muted")
        dist_df = load_goal_distribution(team, selected_season)
        if dist_df is None or dist_df.empty:
            return html.P("No data available.", className="text-muted")
        return _build_single_metric_card(dist_df, metric="conceded")

    # ══════════════════════════════════════════════════════════
    # GOALS & xG LEAGUE COMPARISON MODALS
    # ══════════════════════════════════════════════════════════

    def _perf_league_table(xg_df, standings_df, metric: str, highlight_team: str) -> html.Div:
        """Build a ranked league table (# | Team | total) for Goals Scored, Goals Conceded, xG, or xGC."""
        from src.team_mapping import canonical_name
        from src.styling.theme import COLORS_DARK

        _HL = COLORS_DARK["accent"]

        if metric in ("goals_scored", "goals_conceded"):
            if standings_df is None or standings_df.empty:
                return html.P("No league data available.", style={"color": "#8899aa"})
            df = standings_df.copy()
            if metric == "goals_scored":
                df["_val"] = df["GF"]
                col_label = "Goals Scored"
                ascending = False
                fmt = "d"
            else:
                df["_val"] = df["GA"]
                col_label = "Goals Conceded"
                ascending = True
                fmt = "d"
        else:
            if xg_df is None or xg_df.empty:
                return html.P("No xG league data available.", style={"color": "#8899aa"})
            df = xg_df.copy()
            if metric == "xg":
                df["_val"] = df["xG"]
                col_label = "xG"
                ascending = False
                fmt = ".2f"
            else:
                df["_val"] = df["xGC"]
                col_label = "xGC"
                ascending = True
                fmt = ".2f"

        df = df.dropna(subset=["_val"]).sort_values("_val", ascending=ascending).reset_index(drop=True)
        df["_rank"] = range(1, len(df) + 1)

        hl_lower = canonical_name(highlight_team).lower()

        header = html.Div(
            [
                html.Span("#",        style={"width": "2rem", "color": "#8899aa",
                                              "fontSize": "0.75rem", "flexShrink": "0"}),
                html.Span("Team",     style={"flex": "1", "color": "#8899aa",
                                              "fontSize": "0.75rem"}),
                html.Span(col_label,  style={"color": "#8899aa", "fontSize": "0.75rem",
                                              "minWidth": "6rem", "textAlign": "right"}),
            ],
            style={"display": "flex", "padding": "6px 10px",
                   "borderBottom": "1px solid rgba(255,255,255,0.15)", "marginBottom": "2px"},
        )

        rows = []
        for _, row in df.iterrows():
            team_name = str(row.get("Team", ""))
            val = row["_val"]
            rank = int(row["_rank"])
            is_hl = canonical_name(team_name).lower() == hl_lower

            row_style: dict = {
                "display": "flex", "padding": "6px 10px",
                "borderBottom": "1px solid rgba(255,255,255,0.05)",
                "alignItems": "center",
            }
            if is_hl:
                row_style.update({
                    "background": f"{_HL}22",
                    "borderLeft": f"3px solid {_HL}",
                })

            rows.append(
                html.Div(
                    [
                        html.Span(str(rank), style={"width": "2rem", "color": "#8899aa",
                                                     "fontSize": "0.8rem", "flexShrink": "0"}),
                        html.Span(team_name, style={
                            "flex": "1",
                            "fontWeight": "700" if is_hl else "400",
                            "color": _HL if is_hl else "var(--text-primary)",
                            "fontSize": "0.88rem",
                        }),
                        html.Span(format(val, fmt), style={
                            "fontWeight": "700" if is_hl else "400",
                            "color": _HL if is_hl else "var(--text-secondary)",
                            "fontSize": "0.9rem", "minWidth": "6rem", "textAlign": "right",
                        }),
                    ],
                    style=row_style,
                )
            )

        return html.Div(
            [header, *rows],
            style={
                "maxHeight": "460px", "overflowY": "auto",
                "borderRadius": "6px",
                "border": "1px solid rgba(255,255,255,0.07)",
            },
        )

    @app.callback(
        Output("td-goals-scored-league-modal", "is_open"),
        Output("td-goals-scored-league-modal-body", "children"),
        Input("td-goals-scored-league-open", "n_clicks"),
        State("td-goals-scored-league-modal", "is_open"),
        State("team-season-selector", "value"),
        State("team-context", "data"),
        prevent_initial_call=True,
    )
    def toggle_goals_scored_league_modal(n_clicks, is_open, selected_season, context):
        if not n_clicks:
            return no_update, no_update
        if is_open:
            return False, no_update
        team = (context or {}).get("team", "")
        try:
            standings = load_standings(selected_season)
            body = _perf_league_table(None, standings, "goals_scored", team)
        except Exception:
            return False, html.P("No data available.", className="text-muted")
        return True, body

    @app.callback(
        Output("td-goals-conceded-league-modal", "is_open"),
        Output("td-goals-conceded-league-modal-body", "children"),
        Input("td-goals-conceded-league-open", "n_clicks"),
        State("td-goals-conceded-league-modal", "is_open"),
        State("team-season-selector", "value"),
        State("team-context", "data"),
        prevent_initial_call=True,
    )
    def toggle_goals_conceded_league_modal(n_clicks, is_open, selected_season, context):
        if not n_clicks:
            return no_update, no_update
        if is_open:
            return False, no_update
        team = (context or {}).get("team", "")
        try:
            standings = load_standings(selected_season)
            body = _perf_league_table(None, standings, "goals_conceded", team)
        except Exception:
            return False, html.P("No data available.", className="text-muted")
        return True, body

    @app.callback(
        Output("td-xg-league-modal", "is_open"),
        Output("td-xg-league-modal-body", "children"),
        Input("td-xg-league-open", "n_clicks"),
        State("td-xg-league-modal", "is_open"),
        State("team-season-selector", "value"),
        State("team-context", "data"),
        prevent_initial_call=True,
    )
    def toggle_xg_league_modal(n_clicks, is_open, selected_season, context):
        if not n_clicks:
            return no_update, no_update
        if is_open:
            return False, no_update
        team = (context or {}).get("team", "")
        try:
            xg_df = load_xg_summary(selected_season)
            standings = load_standings(selected_season)
            body = _perf_league_table(xg_df, standings, "xg", team)
        except Exception:
            return False, html.P("No data available.", className="text-muted")
        return True, body

    @app.callback(
        Output("td-xgc-league-modal", "is_open"),
        Output("td-xgc-league-modal-body", "children"),
        Input("td-xgc-league-open", "n_clicks"),
        State("td-xgc-league-modal", "is_open"),
        State("team-season-selector", "value"),
        State("team-context", "data"),
        prevent_initial_call=True,
    )
    def toggle_xgc_league_modal(n_clicks, is_open, selected_season, context):
        if not n_clicks:
            return no_update, no_update
        if is_open:
            return False, no_update
        team = (context or {}).get("team", "")
        try:
            xg_df = load_xg_summary(selected_season)
            standings = load_standings(selected_season)
            body = _perf_league_table(xg_df, standings, "xgc", team)
        except Exception:
            return False, html.P("No data available.", className="text-muted")
        return True, body

    # ══════════════════════════════════════════════════════════
    # PLAYING STYLE WHEEL SECTION
    # ══════════════════════════════════════════════════════════

    # ── Wheel render — reacts to team, season and theme ──
    @app.callback(
        Output("team-ps-container", "children"),
        Input("team-context", "data"),
        Input("team-season-selector", "value"),
        Input("theme-store", "data"),
        prevent_initial_call=False,
    )
    def update_playing_style(context: dict, selected_season: str, theme: str):
        """Render the Playing Style Wheel for the selected team/season/theme.

        Theme is a true Input (not State) because the client-side toggle
        observer does not re-patch polar charts — the wheel rebuilds here.
        """
        from src.components.playing_style_cards import playing_style_wheel_card
        team = (context or {}).get("team", "")
        if not team or not selected_season:
            return html.P("Select a team and season.", className="text-muted")
        df_league = load_playing_style(selected_season)
        return playing_style_wheel_card(
            team, selected_season, df_league, theme=theme or "dark",
        )

    # ── Modal open/close ──
    @app.callback(
        Output("team-ps-modal", "is_open"),
        Input("team-ps-modal-open", "n_clicks"),
        State("team-ps-modal", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_playing_style_modal(n_clicks, is_open):
        if n_clicks:
            return not is_open
        return is_open

    # ── Modal body — league comparison table ──
    @app.callback(
        Output("team-ps-modal-body", "children"),
        Input("team-ps-modal-open", "n_clicks"),
        State("team-season-selector", "value"),
        State("team-context", "data"),
        prevent_initial_call=True,
    )
    def load_playing_style_modal(n_clicks, selected_season, context):
        if not n_clicks:
            return no_update
        from src.components.playing_style_cards import _build_league_comparison_table
        team = (context or {}).get("team", "")
        df_league = load_playing_style(selected_season)
        if df_league is None or df_league.empty:
            return html.P("No data available.", className="text-muted")
        return _build_league_comparison_table(df_league, team)

    # ── Per-KPI explanation modals (12 open/close callbacks) ──
    from src.components.playing_style_cards import register_playing_style_kpi_modals
    register_playing_style_kpi_modals(app)

    # ══════════════════════════════════════════════════════════
    # STYLE EVOLUTION SECTION
    # ══════════════════════════════════════════════════════════

    @app.callback(
        Output("team-ps-evo-container", "children"),
        Input("team-context", "data"),
        Input("theme-store", "data"),
        prevent_initial_call=False,
    )
    def render_style_evolution(context: dict, theme: str):
        from src.components.playing_style_evolution_cards import style_evolution_card
        from src.analytics.data_loader import load_playing_style_all_seasons
        team = (context or {}).get("team", "")
        if not team:
            return no_update
        df_all = load_playing_style_all_seasons(team)
        if df_all is None or df_all.empty:
            return html.Div(
                "No multi-season data available for this team.",
                className="text-muted p-3",
            )
        return style_evolution_card(team, df_all, theme=theme or "dark")

    def _build_single_metric_card(dist_df, metric: str) -> html.Div:
        """Render interval tiles for a single metric ('scored' or 'conceded')."""
        scored_hex = SEMANTIC_COLORS["goals_scored"]
        conceded_hex = SEMANTIC_COLORS["goals_conceded"]

        if metric == "scored":
            hex_color = scored_hex
            rgb = _hex_to_rgb(scored_hex)
            vals = dist_df["scored"].tolist()
            icon = "bi-bullseye"
            row_label = "Scored"
            noun = "scored"
        else:
            hex_color = conceded_hex
            rgb = _hex_to_rgb(conceded_hex)
            vals = dist_df["conceded"].tolist()
            icon = "bi-shield-x"
            row_label = "Conceded"
            noun = "conceded"

        bins = dist_df["bin"].tolist()
        total = sum(vals)
        max_val = max(vals) if vals else 0

        tiles = []
        for b, val in zip(bins, vals):
            intensity = (0.25 + 0.75 * (val / max_val)) if max_val > 0 else 0.25
            pct_str = f"{(val / total * 100):.0f}% of total" if total > 0 else ""
            tiles.append(
                html.Div(
                    [
                        html.Span(str(val), className="gd-tile-value"),
                        html.Span(b, className="gd-tile-label"),
                    ],
                    className="gd-tile",
                    style={"backgroundColor": f"rgba({rgb[0]},{rgb[1]},{rgb[2]},{intensity:.2f})"},
                    title=f"{b}: {val} goal{'s' if val != 1 else ''} {noun}"
                          + (f" ({pct_str})" if pct_str else ""),
                )
            )

        return html.Div(
            [
                html.Div(
                    [
                        html.Div(
                            [
                                html.I(className=f"bi {icon}",
                                       style={"color": hex_color, "fontSize": "1rem"}),
                                html.Span(row_label, className="gd-row-label",
                                          style={"color": hex_color}),
                            ],
                            className="gd-row-header",
                        ),
                        html.Div(tiles, className="gd-tiles-row"),
                    ],
                    className="gd-row",
                ),
                html.Div(
                    html.Span(
                        f"{total} {noun}",
                        style={"color": hex_color, "fontWeight": "600"},
                    ),
                    className="gd-summary",
                ),
            ],
            className="gd-card-inner",
        )

    def _build_goal_distribution_card(
        dist_df, team: str
    ) -> html.Div:
        """Build the 15-minute goal distribution visual card."""
        # Semantic colours from the design system (values unchanged, hues
        # harmonised with the rest of the dashboard — see theme.py).
        scored_hex = SEMANTIC_COLORS["goals_scored"]
        conceded_hex = SEMANTIC_COLORS["goals_conceded"]
        scored_rgb = _hex_to_rgb(scored_hex)
        conceded_rgb = _hex_to_rgb(conceded_hex)

        scored_vals = dist_df["scored"].tolist()
        conceded_vals = dist_df["conceded"].tolist()
        bins = dist_df["bin"].tolist()

        total_scored = sum(scored_vals)
        total_conceded = sum(conceded_vals)
        max_scored = max(scored_vals) if scored_vals else 0
        max_conceded = max(conceded_vals) if conceded_vals else 0

        # Build the scored row tiles
        scored_tiles = []
        for i, (b, val) in enumerate(zip(bins, scored_vals)):
            # Intensity: scale opacity based on value relative to max
            if max_scored > 0:
                intensity = 0.25 + 0.75 * (val / max_scored)
            else:
                intensity = 0.25

            pct_str = ""
            if total_scored > 0:
                pct = (val / total_scored) * 100
                pct_str = f"{pct:.0f}% of total"

            scored_tiles.append(
                html.Div(
                    [
                        html.Span(
                            str(val),
                            className="gd-tile-value",
                        ),
                        html.Span(
                            b,
                            className="gd-tile-label",
                        ),
                    ],
                    className="gd-tile",
                    style={
                        "backgroundColor": f"rgba({scored_rgb[0]}, {scored_rgb[1]}, {scored_rgb[2]}, {intensity:.2f})",
                    },
                    title=f"{b}: {val} goal{'s' if val != 1 else ''} scored"
                          + (f" ({pct_str})" if pct_str else ""),
                )
            )

        # Build the conceded row tiles
        conceded_tiles = []
        for i, (b, val) in enumerate(zip(bins, conceded_vals)):
            if max_conceded > 0:
                intensity = 0.25 + 0.75 * (val / max_conceded)
            else:
                intensity = 0.25

            pct_str = ""
            if total_conceded > 0:
                pct = (val / total_conceded) * 100
                pct_str = f"{pct:.0f}% of total"

            conceded_tiles.append(
                html.Div(
                    [
                        html.Span(
                            str(val),
                            className="gd-tile-value",
                        ),
                        html.Span(
                            b,
                            className="gd-tile-label",
                        ),
                    ],
                    className="gd-tile",
                    style={
                        "backgroundColor": f"rgba({conceded_rgb[0]}, {conceded_rgb[1]}, {conceded_rgb[2]}, {intensity:.2f})",
                    },
                    title=f"{b}: {val} goal{'s' if val != 1 else ''} conceded"
                          + (f" ({pct_str})" if pct_str else ""),
                )
            )

        # Summary line
        summary = html.Div(
            [
                html.Span(
                    f"{total_scored} scored",
                    style={"color": scored_hex, "fontWeight": "600"},
                ),
                html.Span(
                    " · ",
                    style={"color": "var(--text-muted)", "margin": "0 6px"},
                ),
                html.Span(
                    f"{total_conceded} conceded",
                    style={"color": conceded_hex, "fontWeight": "600"},
                ),
                html.Span(
                    f" · {total_scored + total_conceded} total goals",
                    style={"color": "var(--text-secondary)"},
                ),
            ],
            className="gd-summary",
        )

        return html.Div(
            [
                # Scored row
                html.Div(
                    [
                        html.Div(
                            [
                                html.I(
                                    className="bi bi-bullseye",
                                    style={"color": scored_hex, "fontSize": "1rem"},
                                ),
                                html.Span(
                                    "Scored",
                                    className="gd-row-label",
                                    style={"color": scored_hex},
                                ),
                            ],
                            className="gd-row-header",
                        ),
                        html.Div(scored_tiles, className="gd-tiles-row"),
                    ],
                    className="gd-row",
                ),
                # Conceded row
                html.Div(
                    [
                        html.Div(
                            [
                                html.I(
                                    className="bi bi-shield-x",
                                    style={"color": conceded_hex, "fontSize": "1rem"},
                                ),
                                html.Span(
                                    "Conceded",
                                    className="gd-row-label",
                                    style={"color": conceded_hex},
                                ),
                            ],
                            className="gd-row-header",
                        ),
                        html.Div(conceded_tiles, className="gd-tiles-row"),
                    ],
                    className="gd-row",
                ),
                # Summary
                summary,
            ],
            className="gd-card-inner",
        )
