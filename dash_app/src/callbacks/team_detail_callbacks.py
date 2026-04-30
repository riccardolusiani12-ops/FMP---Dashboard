"""
Team Detail page callbacks — load standings chart and KPIs for selected team.

Refactored to use precomputed Parquet tables via data_loader.
Callbacks now perform lightweight filter + render operations instead of
re-reading hundreds of raw CSV files.

The team is fixed for the page; the season is selectable from the header.
KPIs: League Position · Last 5 Form · Goal Difference.
"""

from __future__ import annotations

from dash import Input, Output, State, html, dcc, no_update
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

from src.team_mapping import logo_url
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
    load_xg_summary,
    load_goal_distribution,
    load_team_average_age,
)


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
        prevent_initial_call=False,
    )
    def update_chart(context: dict, selected_season: str):
        """Build the points progression chart for the selected team."""
        team = context.get("team", "")

        # Load all-season progression from precomputed Parquet
        progression = load_all_points_progression()

        highlight = selected_season.replace("_", "/") if selected_season else ""
        fig = build_standings_figure(
            progression,
            team=team,
            highlight_season=highlight,
        )
        return fig

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
                _form_card([]),
                _kpi_card("Goal Diff.", "–", "bi-bullseye", "#FFA15A"),
                _kpi_card("PPG", "–", "bi-star-fill", "#19D3F3"),
                _kpi_card("Mean Age", "–", "bi-people-fill", "#FFA15A"),
            ]

        team_row = standings[standings["Team"] == team]
        if team_row.empty:
            return [
                _kpi_card("Position", "–", "bi-trophy-fill", "#636EFA"),
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
        ppg_color = "#00CC96" if ppg >= 2.0 else ("#FFA15A" if ppg >= 1.3 else "#EF553B")

        # Last 5 results from precomputed progression
        last_5 = _get_last_5(team, season_key)

        # Goal difference color
        gd_color = "#00CC96" if gd > 0 else ("#EF553B" if gd < 0 else "#8899aa")

        # Mean Age from Transfermarkt scrape
        avg_age = load_team_average_age(team, season_key)
        if avg_age is not None:
            age_str = f"{avg_age:.1f}"
            # Color: green if < 26 (young), orange if 26-28 (balanced), red if > 28 (old)
            age_color = "#00CC96" if avg_age < 26 else ("#FFA15A" if avg_age <= 28 else "#EF553B")
        else:
            age_str = "–"
            age_color = "#8899aa"

        kpis = [
            _kpi_card("Position", pos_str, "bi-trophy-fill", "#636EFA"),
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

    def _form_card(results: list[str]) -> html.Div:
        """Create the Last 5 Form KPI card with colored badges."""
        color_map = {
            "W": "#00CC96",  # green
            "D": "#8899aa",  # grey
            "L": "#EF553B",  # red
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
        rank_color = "#00CC96" if rank <= total * 0.33 else (
            "#FFA15A" if rank <= total * 0.66 else "#EF553B"
        )

        # PPDA value
        ppda_str = f"{ppda_val:.2f}"
        ppda_color = "#00CC96" if ppda_val < ppda_df["PPDA"].median() else "#EF553B"

        # Field Tilt percentage
        if field_tilt is not None and not (isinstance(field_tilt, float) and field_tilt != field_tilt):
            tilt_str = f"{field_tilt:.1f}%"
            tilt_color = "#00CC96" if field_tilt > ppda_df["field_tilt"].median() else "#FFA15A"
        else:
            tilt_str = "–"
            tilt_color = "#8899aa"

        # Pressing tier (percentile-based)
        percentile = (1 - (rank - 1) / max(total - 1, 1)) * 100
        if percentile >= 80:
            tier = "Elite"
            tier_color = "#00CC96"
        elif percentile >= 60:
            tier = "High"
            tier_color = "#19D3F3"
        elif percentile >= 40:
            tier = "Medium"
            tier_color = "#FFA15A"
        elif percentile >= 20:
            tier = "Low"
            tier_color = "#EF553B"
        else:
            tier = "Passive"
            tier_color = "#EF553B"

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
        Input("team-season-selector", "value"),
        Input("team-context", "data"),
        prevent_initial_call=False,
    )
    def update_formations(selected_season: str, context: dict):
        """Build the formations visual block from precomputed/raw data."""
        team = context.get("team", "")
        if not team or not selected_season:
            return html.P("Select a team and season.", className="text-muted")

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
            )

        cards = []
        for i, row in formations.iterrows():
            form_str = row["formation_str"]
            count = int(row["count"])
            pct = float(row["pct"])

            fig = build_formation_pitch_figure(form_str, count=count, pct=pct)

            rank_labels = ["Most Used", "2nd Most Used", "3rd Most Used"]
            rank_label = rank_labels[i] if i < len(rank_labels) else ""

            card = html.Div(
                [
                    # Rank badge
                    html.Div(
                        rank_label,
                        className="formation-rank-badge",
                    ),
                    # Formation name
                    html.H5(
                        form_str,
                        className="formation-name",
                    ),
                    # Pitch figure
                    dcc.Graph(
                        figure=fig,
                        config={"displayModeBar": False, "staticPlot": True},
                        responsive=False,
                        className="formation-pitch",
                    ),
                    # Stats row
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
                ],
                className="formation-card",
            )
            cards.append(card)

        return cards

    # ══════════════════════════════════════════════════════════
    # GOALS & xG SECTION CALLBACK
    # ══════════════════════════════════════════════════════════

    @app.callback(
        Output("goals-xg-block", "children"),
        Input("team-season-selector", "value"),
        Input("team-context", "data"),
        prevent_initial_call=False,
    )
    def update_goals_xg(selected_season: str, context: dict):
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
                           "bi-bullseye", "#00CC96"),
                _stat_card("Goals Conceded", str(ga), f"xGC: {xgc_val:.1f}",
                           "bi-shield-x", "#EF553B"),
                _stat_card("xG", f"{xg_val:.1f}",
                           f"{'↑' if xg_over >= 0 else '↓'} {abs(xg_over):.1f} vs actual",
                           "bi-graph-up-arrow",
                           "#00CC96" if xg_over >= 0 else "#FFA15A"),
                _stat_card("xGC", f"{xgc_val:.1f}",
                           f"{'↑' if xgc_over > 0 else '↓'} {abs(xgc_over):.1f} vs actual",
                           "bi-graph-down-arrow",
                           "#00CC96" if xgc_over <= 0 else "#EF553B"),
            ],
            className="goals-xg-kpi-row",
        )

        # Build comparison bar chart
        bar_fig = _build_goals_xg_bar_chart(gf, ga, xg_val, xgc_val, team)

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
                _stat_card("Goals Scored", str(gf), "", "bi-bullseye", "#00CC96"),
                _stat_card("Goals Conceded", str(ga), "", "bi-shield-x", "#EF553B"),
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
        title: str, value: str, subtitle: str, icon: str, color: str
    ) -> html.Div:
        """Create a stat card for the goals/xG block."""
        children = [
            html.Div(
                html.I(className=f"bi {icon}"),
                className="kpi-icon",
                style={"color": color},
            ),
            html.Div(
                [
                    html.Span(title, className="kpi-label"),
                    html.Span(value, className="kpi-value", style={"color": color}),
                    html.Small(subtitle, className="kpi-subtitle text-muted")
                    if subtitle else None,
                ],
                className="kpi-text",
            ),
        ]
        return html.Div(
            [c for c in children if c is not None],
            className="kpi-card",
        )

    def _build_goals_xg_bar_chart(
        gf: int, ga: int, xg: float, xgc: float, team: str
    ) -> go.Figure:
        """Build a grouped bar chart comparing Goals vs xG."""
        categories = ["Goals Scored", "Goals Conceded"]
        actual_vals = [gf, ga]
        expected_vals = [xg, xgc]

        fig = go.Figure()

        fig.add_trace(go.Bar(
            x=categories,
            y=actual_vals,
            name="Actual",
            marker_color=["#00CC96", "#EF553B"],
            text=[str(v) for v in actual_vals],
            textposition="outside",
            textfont=dict(color="white", size=13, family="Inter"),
        ))

        fig.add_trace(go.Bar(
            x=categories,
            y=expected_vals,
            name="Expected (xG)",
            marker_color=["rgba(0,204,150,0.35)", "rgba(239,85,59,0.35)"],
            marker_line=dict(
                color=["#00CC96", "#EF553B"],
                width=2,
            ),
            text=[f"{v:.1f}" for v in expected_vals],
            textposition="outside",
            textfont=dict(color="white", size=13, family="Inter"),
        ))

        fig.update_layout(
            template="plotly_dark",
            title=dict(
                text=f"Goals vs Expected Goals — {team}",
                font=dict(size=15, color="white"),
            ),
            barmode="group",
            paper_bgcolor="#1b2838",
            plot_bgcolor="#1b2838",
            xaxis=dict(
                tickfont=dict(size=12, color="white"),
                gridcolor="rgba(255,255,255,0.06)",
            ),
            yaxis=dict(
                title="Count",
                gridcolor="rgba(255,255,255,0.06)",
                tickfont=dict(size=11, color="white"),
            ),
            legend=dict(
                font=dict(size=11, color="white"),
                bgcolor="rgba(0,0,0,0.3)",
                bordercolor="rgba(255,255,255,0.1)",
                borderwidth=1,
            ),
            height=360,
            margin=dict(t=60, l=50, r=30, b=50),
        )

        return fig

    # ══════════════════════════════════════════════════════════
    # GOAL DISTRIBUTION (15-MIN INTERVALS) CALLBACK
    # ══════════════════════════════════════════════════════════

    @app.callback(
        Output("goal-distribution-block", "children"),
        Input("team-season-selector", "value"),
        Input("team-context", "data"),
        prevent_initial_call=False,
    )
    def update_goal_distribution(selected_season: str, context: dict):
        """Build the goals by 15-minute intervals visual block."""
        team = context.get("team", "")
        if not team or not selected_season:
            return html.P("Select a team and season.", className="text-muted")

        dist_df = load_goal_distribution(team, selected_season)

        if dist_df is None or dist_df.empty:
            return html.Div(
                [
                    html.I(
                        className="bi bi-info-circle me-2",
                        style={"fontSize": "1.2rem", "opacity": 0.5},
                    ),
                    html.P(
                        "No goal distribution data available for this season.",
                        className="text-muted mb-0",
                    ),
                ],
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "justifyContent": "center",
                    "padding": "2rem",
                },
            )

        return _build_goal_distribution_card(dist_df, team)

    def _build_goal_distribution_card(
        dist_df, team: str
    ) -> html.Div:
        """Build the 15-minute goal distribution visual card."""
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
                        "backgroundColor": f"rgba(0, 204, 150, {intensity:.2f})",
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
                        "backgroundColor": f"rgba(239, 85, 59, {intensity:.2f})",
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
                    style={"color": "#00CC96", "fontWeight": "600"},
                ),
                html.Span(
                    " · ",
                    style={"color": "var(--text-muted)", "margin": "0 6px"},
                ),
                html.Span(
                    f"{total_conceded} conceded",
                    style={"color": "#EF553B", "fontWeight": "600"},
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
                                    style={"color": "#00CC96", "fontSize": "1rem"},
                                ),
                                html.Span(
                                    "Scored",
                                    className="gd-row-label",
                                    style={"color": "#00CC96"},
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
                                    style={"color": "#EF553B", "fontSize": "1rem"},
                                ),
                                html.Span(
                                    "Conceded",
                                    className="gd-row-label",
                                    style={"color": "#EF553B"},
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
