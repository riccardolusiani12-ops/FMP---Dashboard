"""
Tab content callbacks – render tab content based on selected tab + global filters.
Also handles KPI updates and settings actions.
"""

from __future__ import annotations

from dash import Input, Output, State, callback, html, no_update
import dash_bootstrap_components as dbc

from src.components.kpis import create_kpi_row
from src.analytics.data_loader import load_team_average_age
from src.registry.registry import ArtifactRegistry
from src.tabs import home, match_report, team_season, player_analysis, settings
from src.utils.caching import cache_clear
from src.utils.logging import log


def register_tab_callbacks(app):
    """Register tab-switching and content-rendering callbacks."""

    # ── Tab content renderer ──────────────────────────────────────────────
    @app.callback(
        Output("tab-content", "children"),
        Input("main-tabs", "value"),
        Input("filter-season", "value"),
        Input("filter-team", "value"),
        Input("filter-match", "value"),
    )
    def render_tab_content(
        tab: str,
        season: str | None,
        team: str | None,
        match_id: str | None,
    ):
        season = season or "2024_2025"
        team = team or "Bologna"

        try:
            if tab == "tab-home":
                return home.render_home_content(season, team)
            elif tab == "tab-match-report":
                return match_report.layout()
            elif tab == "tab-team-season":
                return team_season.render_team_season_content(season, team)
            elif tab == "tab-player":
                return player_analysis.render_player_content(season, team, match_id)
            elif tab == "tab-settings":
                return settings.layout()
            else:
                return dbc.Alert("Unknown tab selected.", color="warning")
        except Exception as exc:
            log.error("Error rendering tab %s: %s", tab, exc)
            return dbc.Alert(
                [
                    html.I(className="bi bi-exclamation-triangle-fill me-2"),
                    f"Error rendering tab: {exc}",
                ],
                color="danger",
                className="mt-3",
            )

    # ── Match report sub-toggle ───────────────────────────────────────────
    @app.callback(
        Output("match-report-content", "children"),
        Input("match-report-toggle", "value"),
        State("filter-season", "value"),
        State("filter-team", "value"),
        State("filter-match", "value"),
        prevent_initial_call=True,
    )
    def render_match_report_sub(
        toggle: str,
        season: str | None,
        team: str | None,
        match_id: str | None,
    ):
        season = season or "2024_2025"
        team = team or "Bologna"

        try:
            if toggle == "pre":
                return match_report.render_pre_match(season, team, match_id)
            else:
                return match_report.render_post_match(season, team, match_id)
        except Exception as exc:
            log.error("Error rendering match report: %s", exc)
            return dbc.Alert(f"Error: {exc}", color="danger")

    # ── KPI row updater ───────────────────────────────────────────────────
    @app.callback(
        Output("kpi-container", "children"),
        Input("filter-season", "value"),
        Input("filter-team", "value"),
    )
    def update_kpis(season: str | None, team: str | None):
        """
        Update KPI cards. For now uses artifact count as proxy.
        When real data pipelines are set up, replace with actual stats.
        """
        registry = ArtifactRegistry.instance()
        season = season or "2024_2025"
        team = team or "Bologna"

        # Count available artifacts as proxy KPIs
        all_arts = registry.query(season=season, team=team)
        match_arts = registry.query(season=season, team=team, analysis="attacking_phase")
        hr_arts = registry.query(season=season, team=team, analysis="high_regains")
        ppda_arts = registry.query(season=season, team=team, analysis="ppda")

        # Load average age from Transfermarkt data
        avg_age = load_team_average_age(team, season)
        mean_age_str = f"{avg_age:.1f}" if avg_age is not None else "–"

        return create_kpi_row(
            matches_played=str(len(match_arts)) if match_arts else "–",
            wins=str(len(all_arts)),
            goals_scored=str(len(hr_arts)) if hr_arts else "–",
            clean_sheets=str(len(ppda_arts)) if ppda_arts else "–",
            mean_age=mean_age_str,
        )

    # ── Settings: Data QA ─────────────────────────────────────────────────
    @app.callback(
        Output("settings-data-qa", "children"),
        Input("main-tabs", "value"),
    )
    def render_data_qa(tab: str):
        if tab == "tab-settings":
            return settings.render_data_qa()
        return no_update

    # ── Settings: Reload manifest ─────────────────────────────────────────
    @app.callback(
        Output("settings-action-feedback", "children"),
        Input("btn-reload-manifest", "n_clicks"),
        Input("btn-clear-cache", "n_clicks"),
        prevent_initial_call=True,
    )
    def handle_settings_actions(reload_clicks, clear_clicks):
        from dash import ctx

        triggered = ctx.triggered_id
        if triggered == "btn-reload-manifest":
            registry = ArtifactRegistry.instance()
            registry.load()
            return dbc.Alert("✅ Manifest reloaded.", color="success", duration=3000)
        elif triggered == "btn-clear-cache":
            cache_clear()
            return dbc.Alert("✅ Cache cleared.", color="success", duration=3000)
        return no_update

    log.info("Tab callbacks registered")
