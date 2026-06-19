"""
Analysis page callbacks — team grid, match list, module selector and live
analysis rendering for Match Analysis and Opponent Analysis pages.

Callback ID prefixes:
  "ma"       -> Match Analysis  (post_match.py)
  "opponent" -> Opponent Analysis (pre_match.py) — season-aggregate view

Opponent Analysis uses a season-aggregate flow:
  - Team selection → four overview tiles (opp-season-content)
  - "Offensive Phase" tile click → offensive_phase_overview_card()
  - Other tiles render as "Coming soon" placeholders
New IDs all have the "opp-season-" prefix to avoid collisions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import dash_bootstrap_components as dbc
from dash import ALL, Input, Output, State, dcc, html, no_update

from src.analytics.data_loader import load_season_teams, load_season_matches_cached
from src.components.analysis_cards import (
    _match_card,
    _match_list_layout,
    _module_card_active,
    _module_card_soon,
    _module_selector,
    _analysis_view,
    _opponent_team,
    _score_lookup,
)
from src.components.team_card import analysis_team_card
from src.team_mapping import canonical_name, logo_url, team_from_slug
from src.utils.logging import log
from src.utils.paths import list_match_files, parse_match_filename


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _find_match_csv(season: str, match_id: str) -> Optional[Path]:
    for f in list_match_files(season):
        info = parse_match_filename(f)
        if info["match_id"] == match_id:
            return f
    return None


def _teams_grid_children(season: str, prefix: str) -> list:
    teams = load_season_teams(season)
    if not teams:
        return [html.P(f"No teams found for {season.replace('_', '/')}.",
                       className="text-muted")]
    return [analysis_team_card(t, prefix) for t in teams]

def register_analysis_callbacks(app):
    # Match Analysis: full match-centric flow
    _register_prefix(app, "ma")
    # Opponent Analysis: team-grid + season-aggregate flow (no match-level callbacks)
    _register_opponent_team_grid(app)
    _register_season_opponent_callbacks(app)


def _register_prefix(app, prefix: str):
    season_id          = f"{prefix}-season-selector"
    selected_team_id   = f"{prefix}-selected-team"
    selected_match_id  = f"{prefix}-selected-match"
    active_module_id   = f"{prefix}-active-module"
    team_selection_id  = f"{prefix}-team-selection"
    match_selection_id = f"{prefix}-match-selection"
    analysis_id        = f"{prefix}-analysis-content"
    teams_grid_id      = f"{prefix}-teams-grid"

    # 1. Teams grid on season change
    @app.callback(
        Output(teams_grid_id, "children"),
        Input(season_id, "value"),
        prevent_initial_call=False,
    )
    def _update_teams_grid(season, _p=prefix):
        if not season:
            return html.P("Please select a season.", className="text-muted")
        return _teams_grid_children(season, _p)

    # 2. Team card click -> store slug
    @app.callback(
        Output(selected_team_id, "data"),
        Input({"type": f"{prefix}-team-card", "index": ALL}, "n_clicks"),
        State({"type": f"{prefix}-team-card", "index": ALL}, "id"),
        prevent_initial_call=True,
    )
    def _store_team(n_clicks_list, id_list):
        for n, id_dict in zip(n_clicks_list, id_list):
            if n:
                return id_dict["index"]
        return no_update

    # 3. Match card click -> store match_id (and clear active module)
    @app.callback(
        Output(selected_match_id, "data"),
        Output(active_module_id,  "data", allow_duplicate=True),
        Input({"type": f"{prefix}-match-item", "index": ALL}, "n_clicks"),
        State({"type": f"{prefix}-match-item", "index": ALL}, "id"),
        prevent_initial_call=True,
    )
    def _store_match(n_clicks_list, id_list):
        for n, id_dict in zip(n_clicks_list, id_list):
            if n:
                return id_dict["index"], None
        return no_update, no_update

    # 4. Module card click -> store active module (skip match_report for download)
    @app.callback(
        Output(active_module_id, "data"),
        Input({"type": f"{prefix}-module-card", "index": ALL}, "n_clicks"),
        State({"type": f"{prefix}-module-card", "index": ALL}, "id"),
        prevent_initial_call=True,
    )
    def _store_module(n_clicks_list, id_list):
        for n, id_dict in zip(n_clicks_list, id_list):
            if n and id_dict["index"] != "match_report":
                return id_dict["index"]
        return no_update

    # 5. Back-to-modules button -> clear active module
    @app.callback(
        Output(active_module_id, "data", allow_duplicate=True),
        Input(f"{prefix}-back-to-modules", "n_clicks"),
        prevent_initial_call=True,
    )
    def _back_to_modules(n):
        if n:
            return None
        return no_update

    # 6. Show/hide sections + content (driven by all three stores)
    @app.callback(
        Output(team_selection_id,  "style"),
        Output(match_selection_id, "style"),
        Output(match_selection_id, "children"),
        Output(analysis_id,        "style"),
        Output(analysis_id,        "children"),
        Input(selected_team_id,  "data"),
        Input(selected_match_id, "data"),
        Input(active_module_id,  "data"),
        State(season_id, "value"),
        prevent_initial_call=True,
    )
    def _update_sections(team_slug, match_id, active_module, season, _p=prefix):
        show = {"display": "block"}
        hide = {"display": "none"}

        if not team_slug:
            return show, hide, no_update, hide, no_update

        team   = team_from_slug(team_slug) or team_slug
        season = season or ""

        if not match_id:
            return hide, show, _match_list_layout(season, team, _p), hide, no_update

        match_csv = _find_match_csv(season, match_id)
        if match_csv is None:
            err = dbc.Alert(
                f"Match CSV not found for id '{match_id}' in season {season}.",
                color="danger",
            )
            return hide, hide, no_update, show, err

        info  = parse_match_filename(match_csv)
        label = info["label"]

        if active_module in ("offensive", "defensive", "set_pieces", "transitions"):
            content = _analysis_view(match_csv, team, label, active_module, _p)
        else:
            content = _module_selector(label, _p)

        return hide, hide, no_update, show, content

    # 7. Back to teams
    @app.callback(
        Output(selected_team_id,  "data", allow_duplicate=True),
        Output(selected_match_id, "data", allow_duplicate=True),
        Output(active_module_id,  "data", allow_duplicate=True),
        Input(f"{prefix}-back-to-teams", "n_clicks"),
        prevent_initial_call=True,
    )
    def _back_to_teams(n):
        if n:
            return None, None, None
        return no_update, no_update, no_update

    # 8. Back to matches
    @app.callback(
        Output(selected_match_id, "data", allow_duplicate=True),
        Output(active_module_id,  "data", allow_duplicate=True),
        Input(f"{prefix}-back-to-matches", "n_clicks"),
        prevent_initial_call=True,
    )
    def _back_to_matches(n):
        if n:
            return None, None
        return no_update, no_update

    # 9a. Possession modal toggle (Match Analysis — Build-up to FT)
    @app.callback(
        Output(f"{prefix}-possession-modal", "is_open"),
        Input(f"{prefix}-possession-modal-trigger", "n_clicks"),
        State(f"{prefix}-possession-modal", "is_open"),
        prevent_initial_call=True,
    )
    def _toggle_possession_modal(n, is_open):
        if n:
            return not is_open
        return is_open

    # 9b. Tempo modal toggle (Match Analysis — Build-up to FT)
    @app.callback(
        Output(f"{prefix}-tempo-modal", "is_open"),
        Input(f"{prefix}-tempo-modal-trigger", "n_clicks"),
        State(f"{prefix}-tempo-modal", "is_open"),
        prevent_initial_call=True,
    )
    def _toggle_tempo_modal(n, is_open):
        if n:
            return not is_open
        return is_open


    # 9. Match Report card click -> generate PDF and send to browser
    @app.callback(
        Output(f"{prefix}-match-report-download", "data"),
        Input({"type": f"{prefix}-module-card", "index": "match_report"}, "n_clicks"),
        State(selected_match_id, "data"),
        State(season_id, "value"),
        prevent_initial_call=True,
    )
    def _download_match_report(n_clicks, match_id, season):
        if not n_clicks:
            return no_update

        log.info(f"Match Report download triggered: match_id={match_id}, season={season}")

        if not match_id:
            log.error("Match Report download: No match selected")
            return no_update

        if not season:
            log.error("Match Report download: No season selected")
            return no_update

        match_csv = _find_match_csv(season, match_id)
        if match_csv is None:
            log.error("Match Report download: CSV not found for season=%s, match_id=%s", season, match_id)
            log.error("Available match files in %s: %s", season, [str(f.name) for f in list_match_files(season)[:5]])
            return no_update

        try:
            log.info("Building PDF from: %s", match_csv)
            from src.reporting.match_report_pdf import build_match_report_pdf
            pdf_bytes = build_match_report_pdf(match_csv, season)
            log.info("PDF built successfully: %d bytes", len(pdf_bytes))

            info = parse_match_filename(match_csv)
            filename = f"match_report_GW{info.get('week','?')}_{info.get('home','?')}_{info.get('away','?')}.pdf"
            log.info("Sending PDF download: %s", filename)
            return dcc.send_bytes(pdf_bytes, filename)

        except Exception as exc:
            log.error("Match Report PDF generation failed: %s", exc, exc_info=True)
            return no_update


# ═══════════════════════════════════════════════════════════════════════════════
# OPPONENT ANALYSIS — SEASON-AGGREGATE CALLBACKS
# ═══════════════════════════════════════════════════════════════════════════════

def _register_opponent_team_grid(app):
    """
    Register the two stateless team-grid callbacks for Opponent Analysis.
    These mirror callbacks 1 & 2 from _register_prefix but are standalone
    because _register_prefix is no longer called for "opponent".
    """

    # 1. Teams grid on season change
    @app.callback(
        Output("opponent-teams-grid", "children"),
        Input("opponent-season-selector", "value"),
        prevent_initial_call=False,
    )
    def _opp_update_teams_grid(season):
        if not season:
            return html.P("Please select a season.", className="text-muted")
        return _teams_grid_children(season, "opponent")

    # 2. Team card click → store slug
    @app.callback(
        Output("opponent-selected-team", "data"),
        Input({"type": "opponent-team-card", "index": ALL}, "n_clicks"),
        State({"type": "opponent-team-card", "index": ALL}, "id"),
        prevent_initial_call=True,
    )
    def _opp_store_team(n_clicks_list, id_list):
        for n, id_dict in zip(n_clicks_list, id_list):
            if n:
                return id_dict["index"]
        return no_update


def _register_season_opponent_callbacks(app):
    """
    Register the season-level Opponent Analysis callbacks.

    IDs used (all prefixed opp-season- to avoid collisions):
      opp-season-active-view   Store  — "offensive" | None
      opp-season-content       Div    — tiles or analysis view
      opp-season-back-to-teams Span   — resets team store
    """

    # A. Team selected / view changed → show tiles or analysis skeleton
    #    Sets opp-season-load-trigger when entering offensive view so lazy
    #    section callbacks fire.  Returns the skeleton immediately (no heavy
    #    computation here).
    @app.callback(
        Output("opponent-team-selection",   "style"),
        Output("opp-season-content",        "style"),
        Output("opp-season-content",        "children"),
        Output("opp-season-load-trigger",   "data"),
        Input("opponent-selected-team",     "data"),
        Input("opp-season-active-view",     "data"),
        State("opponent-season-selector",   "value"),
        prevent_initial_call=True,
    )
    def _opp_season_show_content(team_slug, active_view, season):
        show = {"display": "block"}
        hide = {"display": "none"}

        if not team_slug:
            return show, hide, no_update, no_update

        from src.pages.pre_match import season_overview_tiles
        team   = team_from_slug(team_slug) or team_slug
        season = season or ""

        def _nav_bar() -> html.Div:
            return html.Div(
                [
                    html.Span(
                        [html.I(className="bi bi-arrow-left me-2"), "Back to Overview"],
                        id="opp-season-back-to-overview",
                        className="back-button",
                        n_clicks=0,
                        style={"cursor": "pointer"},
                    ),
                    html.Span(
                        [html.I(className="bi bi-arrow-left me-2"), "Back to Teams"],
                        id="opp-season-back-to-teams",
                        className="back-button ms-3",
                        n_clicks=0,
                        style={"cursor": "pointer"},
                    ),
                ],
                className="d-flex align-items-center mb-4",
            )

        if active_view == "offensive":
            from src.components.opponent_offensive_phase import offensive_phase_overview_card
            # Return the skeleton immediately — no heavy computation
            skeleton = html.Div([_nav_bar(), offensive_phase_overview_card(season, team)])
            # Trigger value carries {season, team} so lazy callbacks can read it
            trigger = {"season": season, "team": team}
            return hide, show, skeleton, trigger

        elif active_view == "defensive":
            def _placeholder(section_id: str) -> html.Div:
                return html.Div(
                    dcc.Loading(
                        html.Div(id=section_id),
                        type="circle",
                        color="#8a1f33",
                    ),
                    style={"minHeight": "120px"},
                    id=f"{section_id}-wrap",
                )

            skeleton = html.Div([
                _nav_bar(),
                _placeholder("opp-section-dp"),
                _placeholder("opp-section-dc"),
                _placeholder("opp-section-ccc"),
            ])
            trigger = {"season": season, "team": team}
            return hide, show, skeleton, trigger

        else:
            return hide, show, season_overview_tiles(team, season), no_update

    # B. "Offensive Phase" tile click → set active view
    @app.callback(
        Output("opp-season-active-view", "data"),
        Input({"type": "opp-season-tile", "index": ALL}, "n_clicks"),
        State({"type": "opp-season-tile", "index": ALL}, "id"),
        prevent_initial_call=True,
    )
    def _opp_season_tile_click(n_clicks_list, id_list):
        for n, id_dict in zip(n_clicks_list, id_list):
            if n:
                return id_dict["index"]
        return no_update

    # C. "Back to Teams" → reset team + view stores
    @app.callback(
        Output("opponent-selected-team",  "data", allow_duplicate=True),
        Output("opp-season-active-view",  "data", allow_duplicate=True),
        Input("opp-season-back-to-teams", "n_clicks"),
        prevent_initial_call=True,
    )
    def _opp_season_back_to_teams(n):
        if n:
            return None, None
        return no_update, no_update

    # D. "Back to Overview" → clear active view (stay on same team)
    @app.callback(
        Output("opp-season-active-view", "data", allow_duplicate=True),
        Input("opp-season-back-to-overview", "n_clicks"),
        prevent_initial_call=True,
    )
    def _opp_season_back_to_overview(n):
        if n:
            return None
        return no_update

    # ── Lazy section loaders ────────────────────────────────────────────────
    # Each fires when opp-season-load-trigger is set and populates one section.
    # dcc.Loading in the skeleton shows a spinner until the callback returns.

    @app.callback(
        Output("opp-section-gk", "children"),
        Input("opp-season-load-trigger", "data"),
        prevent_initial_call=True,
    )
    def _opp_load_gk(trigger):
        if not trigger:
            return no_update
        from src.components.opponent_offensive_phase import build_gk_section
        return build_gk_section(trigger["season"], trigger["team"])

    @app.callback(
        Output("opp-section-ft", "children"),
        Input("opp-season-load-trigger", "data"),
        prevent_initial_call=True,
    )
    def _opp_load_ft(trigger):
        if not trigger:
            return no_update
        from src.components.opponent_offensive_phase import build_ft_section
        return build_ft_section(trigger["season"], trigger["team"])

    @app.callback(
        Output("opp-section-cc", "children"),
        Input("opp-season-load-trigger", "data"),
        prevent_initial_call=True,
    )
    def _opp_load_cc(trigger):
        if not trigger:
            return no_update
        from src.components.opponent_offensive_phase import build_cc_section
        return build_cc_section(trigger["season"], trigger["team"])

    # ── GK section: Short Pass % modal — open/close ────────────────────────
    @app.callback(
        Output("opp-season-gk-sp-outcome-modal",       "is_open"),
        Output("opp-season-gk-sp-outcome-modal-title", "children"),
        Output("opp-season-gk-sp-outcome-modal-body",  "children"),
        Input("opp-season-gk-sp-card",                 "n_clicks"),
        State("opp-season-gk-sp-outcome-modal",        "is_open"),
        State("opp-season-load-trigger",               "data"),
        prevent_initial_call=True,
    )
    def _gk_sp_modal(n_clicks, is_open, trigger):
        if not n_clicks:
            return no_update, no_update, no_update
        if is_open:
            return False, no_update, no_update
        from src.analytics.season_offensive_summary import compute_season_gk_buildup
        from src.components.opponent_offensive_phase import _build_gk_outcome_donut
        season    = (trigger or {}).get("season", "")
        team_name = (trigger or {}).get("team", "")
        data      = compute_season_gk_buildup(season, team_name) if season else {}
        counts    = (data.get("metrics") or {}).get("short_granular_counts", {})
        body      = _build_gk_outcome_donut(counts, "Short Pass", team_name, season)
        return True, "Outcome Breakdown — Short Pass", body

    # ── GK section: Long Ball % modal — open/close ──────────────────────────
    @app.callback(
        Output("opp-season-gk-lb-outcome-modal",       "is_open"),
        Output("opp-season-gk-lb-outcome-modal-title", "children"),
        Output("opp-season-gk-lb-outcome-modal-body",  "children"),
        Input("opp-season-gk-lb-card",                 "n_clicks"),
        State("opp-season-gk-lb-outcome-modal",        "is_open"),
        State("opp-season-load-trigger",               "data"),
        prevent_initial_call=True,
    )
    def _gk_lb_modal(n_clicks, is_open, trigger):
        if not n_clicks:
            return no_update, no_update, no_update
        if is_open:
            return False, no_update, no_update
        from src.analytics.season_offensive_summary import compute_season_gk_buildup
        from src.components.opponent_offensive_phase import _build_gk_outcome_donut
        season    = (trigger or {}).get("season", "")
        team_name = (trigger or {}).get("team", "")
        data      = compute_season_gk_buildup(season, team_name) if season else {}
        counts    = (data.get("metrics") or {}).get("long_granular_counts", {})
        body      = _build_gk_outcome_donut(counts, "Long Ball", team_name, season)
        return True, "Outcome Breakdown — Long Ball", body

    # ── GK section: benchmark bar metric toggle ─────────────────────────────
    @app.callback(
        Output("opp-season-gk-bench-graph",     "figure"),
        Output("opp-season-gk-bench-short-btn", "style"),
        Output("opp-season-gk-bench-long-btn",  "style"),
        Input("opp-season-gk-bench-short-btn",  "n_clicks"),
        Input("opp-season-gk-bench-long-btn",   "n_clicks"),
        State("opp-season-load-trigger",        "data"),
        prevent_initial_call=True,
    )
    def _gk_bench_toggle(n_short, n_long, trigger):
        from dash import ctx as dash_ctx
        from src.analytics.season_offensive_summary import compute_league_offensive_benchmarks
        from src.components.opponent_offensive_phase import _build_gk_benchmark_bar
        from src.config import PRIMARY_COLOR as _PC

        if not trigger:
            return no_update, no_update, no_update

        triggered = dash_ctx.triggered_id
        metric = "long" if triggered == "opp-season-gk-bench-long-btn" else "short"

        benchmarks = compute_league_offensive_benchmarks(trigger["season"])
        fig = _build_gk_benchmark_bar(benchmarks, metric, trigger["team"])

        _active   = {"padding": "3px 12px", "fontSize": "0.75rem",
                     "background": _PC, "color": "white",
                     "border": f"1px solid {_PC}", "cursor": "pointer"}
        _inactive_short = {"padding": "3px 12px", "fontSize": "0.75rem",
                           "background": "transparent", "color": "#22c55e",
                           "border": "1px solid #22c55e", "cursor": "pointer"}
        _inactive_long  = {"padding": "3px 12px", "fontSize": "0.75rem",
                           "background": "transparent", "color": "#f97316",
                           "border": "1px solid #f97316", "cursor": "pointer"}

        if metric == "short":
            short_style = {**_active, "borderRadius": "12px 0 0 12px"}
            long_style  = {**_inactive_long, "borderRadius": "0 12px 12px 0"}
        else:
            short_style = {**_inactive_short, "borderRadius": "12px 0 0 12px"}
            long_style  = {**_active, "borderRadius": "0 12px 12px 0"}

        return fig, short_style, long_style

    # ── FT section: Top Method modal ───────────────────────────────────────
    @app.callback(
        Output("opp-season-ft-method-modal",      "is_open"),
        Output("opp-season-ft-method-modal-body", "children"),
        Input("opp-season-ft-method-card",        "n_clicks"),
        State("opp-season-ft-entries-store",      "data"),
        State("opp-season-ft-method-modal",       "is_open"),
        prevent_initial_call=True,
    )
    def _ft_modal_method(n, store, is_open):
        if not n:
            return no_update, no_update
        if is_open:
            return False, no_update

        from src.components.final_third_pitch import METHOD_COLORS
        from src.components.opponent_offensive_phase import _FT_METHOD_LABELS

        d             = store or {}
        method_pcts   = d.get("method_pcts", {})
        method_counts = d.get("method_counts", {})

        _ORDER = [
            "transition_recovery", "through_ball", "switch_of_play", "set_piece",
            "long_ball", "cross_delivery", "individual_carry", "short_pass",
        ]

        rows = []
        for key in _ORDER:
            count = method_counts.get(key, 0)
            if count == 0:
                continue
            pct   = method_pcts.get(key, 0.0)
            color = METHOD_COLORS.get(key, "#8a1f33")
            label = _FT_METHOD_LABELS.get(key, key)
            rows.append(
                html.Div(
                    [
                        html.Div(
                            html.Span(
                                style={
                                    "display": "inline-block",
                                    "width": "10px", "height": "10px",
                                    "borderRadius": "50%",
                                    "backgroundColor": color,
                                    "marginRight": "8px",
                                }
                            ),
                            style={"display": "flex", "alignItems": "center",
                                   "flex": "0 0 auto"},
                        ),
                        html.Span(label, style={
                            "flex": "1", "fontSize": "0.85rem",
                            "color": "#d0d0d0",
                        }),
                        html.Span(f"{count}", style={
                            "fontSize": "0.85rem", "color": "#8899aa",
                            "marginRight": "12px",
                        }),
                        html.Span(f"{pct}%", style={
                            "fontSize": "0.9rem", "fontWeight": "600",
                            "color": color, "minWidth": "42px",
                            "textAlign": "right",
                        }),
                    ],
                    style={
                        "display": "flex", "alignItems": "center",
                        "padding": "8px 4px",
                        "borderBottom": "1px solid rgba(255,255,255,0.06)",
                    },
                )
            )

        body = html.Div(rows) if rows else html.P("No data.", style={"color": "#8899aa"})
        return True, body

    # ── FT section: Success Rate modal ─────────────────────────────────────
    @app.callback(
        Output("opp-season-ft-success-modal",      "is_open"),
        Output("opp-season-ft-success-modal-body", "children"),
        Input("opp-season-ft-success-card",        "n_clicks"),
        State("opp-season-ft-entries-store",       "data"),
        State("opp-season-ft-success-modal",       "is_open"),
        prevent_initial_call=True,
    )
    def _ft_modal_success(n, store, is_open):
        if not n:
            return no_update, no_update
        if is_open:
            return False, no_update
        from src.components.opponent_offensive_phase import (
            _build_ft_success_by_method,
            _build_ft_build_depth,
        )
        entries = (store or {}).get("entries", [])
        fig_success = _build_ft_success_by_method(entries)
        fig_depth   = _build_ft_build_depth(entries)
        body = html.Div([
            dcc.Graph(figure=fig_success, config={"displayModeBar": False}),
            html.Hr(style={"borderColor": "rgba(255,255,255,0.08)",
                           "margin": "1rem 0"}),
            dcc.Graph(figure=fig_depth, config={"displayModeBar": False}),
        ])
        return True, body

    # ── FT section: Tempo modal (unified modal pilot) ───────────────────────
    @app.callback(
        Output("opp-season-ft-tempo-modal",      "is_open"),
        Output("opp-season-ft-tempo-modal-body", "children"),
        Input("opp-season-ft-tempo-card",        "n_clicks"),
        State("opp-season-ft-entries-store",     "data"),
        State("opp-season-ft-tempo-modal",       "is_open"),
        prevent_initial_call=True,
    )
    def _ft_modal_tempo(n, store, is_open):
        if not n:
            return no_update, no_update
        from src.components.opponent_offensive_phase import _build_ft_timing_chart
        if is_open:
            return False, no_update
        entries = (store or {}).get("entries", [])
        fig = _build_ft_timing_chart(entries)
        body = dcc.Graph(figure=fig, config={"displayModeBar": False})
        return True, body

    # ── FT section: Box Touches modal ───────────────────────────────────────
    @app.callback(
        Output("opp-season-ft-boxtouches-modal",      "is_open"),
        Output("opp-season-ft-boxtouches-modal-body", "children"),
        Input("opp-season-ft-boxtouches-card",        "n_clicks"),
        State("opp-season-ft-entries-store",          "data"),
        State("opp-season-ft-boxtouches-modal",       "is_open"),
        prevent_initial_call=True,
    )
    def _ft_modal_boxtouches(n, store, is_open):
        if not n:
            return no_update, no_update
        from src.components.opponent_offensive_phase import _build_ft_box_touches_rank
        from src.analytics.season_offensive_summary import compute_league_offensive_benchmarks
        if is_open:
            return False, no_update
        d = store or {}
        season    = d.get("season", "")
        team_name = d.get("team", "")
        benchmarks = compute_league_offensive_benchmarks(season)
        fig = _build_ft_box_touches_rank(benchmarks, team_name)
        body = dcc.Graph(figure=fig, config={"displayModeBar": False})
        return True, body

    # ── CC section: xG modal open/close ─────────────────────────────────────
    @app.callback(
        Output("opp-season-cc-xg-modal", "is_open"),
        Input("opp-season-cc-xg-card",   "n_clicks"),
        State("opp-season-cc-xg-modal",  "is_open"),
        prevent_initial_call=True,
    )
    def _cc_xg_modal_toggle(n_clicks, is_open):
        if n_clicks:
            return True
        return is_open

    # ── CC section: xG modal graph populate ─────────────────────────────────
    @app.callback(
        Output("opp-season-cc-xg-modal-graph", "figure"),
        Input("opp-season-cc-xg-modal",        "is_open"),
        State("opp-season-load-trigger",        "data"),
        prevent_initial_call=True,
    )
    def _cc_xg_modal_graph(is_open, trigger):
        if not is_open or not trigger:
            return no_update
        from src.analytics.season_offensive_summary import compute_league_offensive_benchmarks
        from src.components.opponent_offensive_phase import _build_cc_xg_bar
        from src.utils.caching import cache_get, cache_set

        season    = trigger["season"]
        team_name = trigger["team"]
        cache_key = f"opp_cc_xg_bar_{season}"
        benchmarks = cache_get(cache_key)
        if benchmarks is None:
            benchmarks = compute_league_offensive_benchmarks(season)
            cache_set(cache_key, benchmarks)
        return _build_cc_xg_bar(benchmarks, team_name)

    # ── CC section: Goal Types modal open/close ──────────────────────────────
    @app.callback(
        Output("opp-season-cc-goal-types-modal", "is_open"),
        Input("opp-season-cc-origin-card",       "n_clicks"),
        State("opp-season-cc-goal-types-modal",  "is_open"),
        prevent_initial_call=True,
    )
    def _cc_goal_types_modal_toggle(n_clicks, is_open):
        if n_clicks:
            return True
        return is_open

    # ── CC section: Goal Types modal graph populate ───────────────────────────
    @app.callback(
        Output("opp-season-cc-goal-types-graph",  "figure"),
        Input("opp-season-cc-goal-types-modal",   "is_open"),
        State("opp-season-load-trigger",          "data"),
        prevent_initial_call=True,
    )
    def _cc_goal_types_modal_graph(is_open, trigger):
        if not is_open or not trigger:
            return no_update
        from src.analytics.season_offensive_summary import compute_season_chance_creation
        from src.components.opponent_offensive_phase import _build_goal_types_chart
        from src.utils.caching import cache_get, cache_set

        season    = trigger["season"]
        team_name = trigger["team"]
        cache_key = f"opp_cc_goal_types_{team_name}_{season}"
        shots = cache_get(cache_key)
        if shots is None:
            data = compute_season_chance_creation(season, team_name)
            shots = data["shots"]
            cache_set(cache_key, shots)
        return _build_goal_types_chart(shots, team_name, season)

    # ── Defensive Pressing: lazy section loader ─────────────────────────────
    @app.callback(
        Output("opp-section-dp", "children"),
        Input("opp-season-load-trigger", "data"),
        prevent_initial_call=True,
    )
    def _opp_load_dp(trigger):
        if not trigger:
            return no_update
        from src.components.opp_season_pressing_cards import build_pressing_section
        return build_pressing_section(trigger["season"], trigger["team"])

    # ── Defensive Pressing: per-zone success modals ─────────────────────────
    # One callback per zone (high / mid / low) — matches the fixed modal IDs
    # produced by build_unified_modal() in opp_season_pressing_cards.py.

    for _zone_key in ("high", "mid", "low"):
        _mk = _zone_key  # capture loop variable

        @app.callback(
            Output(f"opp-season-press-modal-{_mk}",       "is_open"),
            Output(f"opp-season-press-modal-{_mk}-body",  "children"),
            Input({"type": "opp-season-press-zone-tile", "index": _mk}, "n_clicks"),
            State("opp-season-press-store", "data"),
            State(f"opp-season-press-modal-{_mk}", "is_open"),
            prevent_initial_call=True,
        )
        def _dp_zone_modal(n, store, is_open, _zk=_mk):
            if not n:
                return no_update, no_update
            if is_open:
                return False, no_update
            from src.components.opp_season_pressing_cards import _zone_modal_body
            by_zone = (store or {}).get("press_success_by_zone", {})
            body = html.Div(
                _zone_modal_body(_zk, by_zone),
                style={"padding": "0.5rem"},
            )
            return True, body

    # ── Defensive Pressing: Actions/Match league-comparison modal (C2) ──────
    @app.callback(
        Output("opp-season-press-modal-actions-pm",      "is_open"),
        Output("opp-season-press-modal-actions-pm-body", "children"),
        Input("opp-season-press-kpi-actions-pm",         "n_clicks"),
        State("opp-season-press-store",                  "data"),
        State("opp-season-press-modal-actions-pm",       "is_open"),
        prevent_initial_call=True,
    )
    def _dp_modal_actions_pm(n, store, is_open):
        if not n:
            return no_update, no_update
        if is_open:
            return False, no_update
        from src.components.opp_season_pressing_cards import (
            load_league_pressing_summary, _league_table,
        )
        d = store or {}
        season    = d.get("season", "")
        team_name = d.get("team", "")
        # season stored as "2025/2026" label — convert back to key for parquet lookup
        season_key = season.replace("/", "_")
        summary = load_league_pressing_summary(season_key)
        body = _league_table(
            summary, "actions_per_match", "Actions/M",
            team_name, ascending=False, fmt=".1f",
        )
        return True, body

    # ── Defensive Pressing: PPDA league-comparison modal (C4) ───────────────
    @app.callback(
        Output("opp-season-press-modal-ppda",      "is_open"),
        Output("opp-season-press-modal-ppda-body", "children"),
        Input("opp-season-press-kpi-ppda",         "n_clicks"),
        State("opp-season-press-store",            "data"),
        State("opp-season-press-modal-ppda",       "is_open"),
        prevent_initial_call=True,
    )
    def _dp_modal_ppda(n, store, is_open):
        if not n:
            return no_update, no_update
        if is_open:
            return False, no_update
        from src.components.opp_season_pressing_cards import (
            load_league_pressing_summary, _league_table,
        )
        d = store or {}
        season    = d.get("season", "")
        team_name = d.get("team", "")
        season_key = season.replace("/", "_")
        summary = load_league_pressing_summary(season_key)
        body = _league_table(
            summary, "ppda_overall", "PPDA",
            team_name, ascending=True, fmt=".2f",
        )
        return True, body

    # ── Defensive Pressing: Press Success Rate league-comparison modal ────────
    @app.callback(
        Output("opp-season-press-modal-success-rate",      "is_open"),
        Output("opp-season-press-modal-success-rate-body", "children"),
        Input("opp-season-press-kpi-success-rate",         "n_clicks"),
        State("opp-season-press-store",                    "data"),
        State("opp-season-press-modal-success-rate",       "is_open"),
        prevent_initial_call=True,
    )
    def _dp_modal_success_rate(n, store, is_open):
        if not n:
            return no_update, no_update
        if is_open:
            return False, no_update
        from src.components.opp_season_pressing_cards import (
            load_league_pressing_summary, _league_table,
        )
        d = store or {}
        season    = d.get("season", "")
        team_name = d.get("team", "")
        season_key = season.replace("/", "_")
        summary = load_league_pressing_summary(season_key)
        body = _league_table(
            summary, "press_success_rate", "Success Rate (%)",
            team_name, ascending=False, fmt=".1f",
        )
        return True, body

    # ── Defensive Pressing: Pressing Line (Median) league-comparison modal ────
    @app.callback(
        Output("opp-season-press-modal-offside-line",      "is_open"),
        Output("opp-season-press-modal-offside-line-body", "children"),
        Input("opp-season-press-kpi-offside-line",         "n_clicks"),
        State("opp-season-press-store",                    "data"),
        State("opp-season-press-modal-offside-line",       "is_open"),
        prevent_initial_call=True,
    )
    def _dp_modal_offside_line(n, store, is_open):
        if not n:
            return no_update, no_update
        if is_open:
            return False, no_update
        from src.components.opp_season_pressing_cards import (
            load_league_pressing_summary, _league_table,
        )
        d = store or {}
        season    = d.get("season", "")
        team_name = d.get("team", "")
        season_key = season.replace("/", "_")
        summary = load_league_pressing_summary(season_key)
        body = _league_table(
            summary, "pressing_line_median", "Pressing Line (median x)",
            team_name, ascending=False, fmt=".1f",
        )
        return True, body

    # ── Defensive Pressing: Zone KPI league-comparison modals ────────────────
    # One callback per zone card (own / mid / final third).
    for _zk, _zid in (("low", "low"), ("mid", "mid"), ("high", "high")):
        _zone_key = _zk
        _zone_id  = _zid

        @app.callback(
            Output(f"opp-season-press-modal-zone-{_zone_id}",      "is_open"),
            Output(f"opp-season-press-modal-zone-{_zone_id}-body", "children"),
            Input(f"opp-season-press-kpi-zone-{_zone_id}",         "n_clicks"),
            State("opp-season-press-store",                         "data"),
            State(f"opp-season-press-modal-zone-{_zone_id}",       "is_open"),
            prevent_initial_call=True,
        )
        def _dp_modal_zone(n, store, is_open, _zk=_zone_key):
            if not n:
                return no_update, no_update
            if is_open:
                return False, no_update
            from src.components.opp_season_pressing_cards import (
                load_league_pressing_summary, _zone_league_comparison_body,
            )
            d = store or {}
            season    = d.get("season", "")
            team_name = d.get("team", "")
            season_key = season.replace("/", "_")
            summary = load_league_pressing_summary(season_key)
            body = html.Div(
                _zone_league_comparison_body(summary, _zk, team_name),
                style={"padding": "0.5rem"},
            )
            return True, body

    # ── Defensive Castle: lazy section loader ───────────────────────────────
    @app.callback(
        Output("opp-section-dc", "children"),
        Input("opp-season-load-trigger", "data"),
        prevent_initial_call=True,
    )
    def _opp_load_dc(trigger):
        if not trigger:
            return no_update
        from src.components.opp_season_castle_cards import build_castle_section
        return build_castle_section(trigger["season"], trigger["team"])

    # ── Defensive Castle: KPI league-comparison modals ──────────────────────
    # Tuple: (slug, kpi_id, metric_col, ascending, fmt, share_subzone_col)
    # share_subzone_col=None for the overall actions-pm card (no sub-zone denominator)
    _CASTLE_KPI_MODALS = [
        ("actions-pm",  "opp-season-castle-kpi-actions-pm",  "actions_per_match",         True, ".1f", None),
        ("own-box",     "opp-season-castle-kpi-own-box",      "in_own_box_per_match",      True, ".1f", "in_own_box_total"),
        ("wide-flanks", "opp-season-castle-kpi-wide-flanks",  "wide_flanks_per_match",     True, ".1f", "wide_flanks_total"),
        ("def-edge",    "opp-season-castle-kpi-def-edge",     "def_third_edge_per_match",  True, ".1f", "def_third_edge_total"),
    ]

    _CASTLE_KPI_LABELS = {
        "actions_per_match":         "Actions/M",
        "in_own_box_per_match":      "Own Box/M",
        "wide_flanks_per_match":     "Flanks/M",
        "def_third_edge_per_match":  "Edge/M",
    }

    for _slug, _kpi_id, _metric_col, _asc, _fmt, _share_sub in _CASTLE_KPI_MODALS:
        _s   = _slug
        _kid = _kpi_id
        _mc  = _metric_col
        _a   = _asc
        _f   = _fmt
        _ss  = _share_sub

        @app.callback(
            Output(f"opp-season-castle-modal-{_s}",      "is_open"),
            Output(f"opp-season-castle-modal-{_s}-body", "children"),
            Input(_kid,                                    "n_clicks"),
            State("opp-season-castle-store",              "data"),
            State(f"opp-season-castle-modal-{_s}",       "is_open"),
            prevent_initial_call=True,
        )
        def _castle_kpi_modal(n, store, is_open, _mc=_mc, _a=_a, _f=_f, _ss=_ss):
            if not n:
                return no_update, no_update
            if is_open:
                return False, no_update
            from src.components.opp_season_castle_cards import (
                load_league_castle_summary, _league_table,
            )
            d = store or {}
            season    = d.get("season", "")
            team_name = d.get("team", "")
            season_key = season.replace("/", "_")
            summary = load_league_castle_summary(season_key)
            label = _CASTLE_KPI_LABELS.get(_mc, _mc.replace("_", " ").title())
            body = _league_table(
                summary, _mc, label, team_name,
                ascending=_a, fmt=_f,
                share_total_col="total_actions" if _ss else None,
                share_subzone_col=_ss,
            )
            return True, body

    # ── Defensive Castle: Action Types modal ────────────────────────────────
    @app.callback(
        Output("opp-season-castle-modal-action-types",       "is_open"),
        Output("opp-season-castle-modal-action-types-title", "children"),
        Output("opp-season-castle-modal-action-types-body",  "children"),
        Input("opp-season-castle-kpi-action-types",          "n_clicks"),
        State("opp-season-castle-store",                     "data"),
        State("opp-season-castle-modal-action-types",        "is_open"),
        prevent_initial_call=True,
    )
    def _castle_action_types_modal(n, store, is_open):
        if not n:
            return no_update, no_update, no_update
        if is_open:
            return False, no_update, no_update

        d = store or {}
        team_name       = d.get("team", "")
        season          = d.get("season", "")
        actions_by_type = d.get("actions_by_type", [])
        total           = d.get("total_actions", 1) or 1

        title = f"Defensive Actions by Type — {team_name}  {season}"

        if not actions_by_type:
            body = html.P("No data available.", style={"color": "#8899aa"})
            return True, title, body

        header = html.Div(
            [
                html.Span("Action Type", style={"flex": "1", "color": "#8899aa",
                                                "fontSize": "0.75rem"}),
                html.Span("Count",       style={"minWidth": "4rem", "textAlign": "right",
                                                "color": "#8899aa", "fontSize": "0.75rem"}),
                html.Span("% of Total",  style={"minWidth": "5rem", "textAlign": "right",
                                                "color": "#8899aa", "fontSize": "0.75rem"}),
            ],
            style={"display": "flex", "padding": "6px 10px",
                   "borderBottom": "1px solid rgba(255,255,255,0.15)", "marginBottom": "2px"},
        )
        rows = []
        for action, count in actions_by_type:
            pct = round(count / total * 100, 1)
            rows.append(
                html.Div(
                    [
                        html.Span(action, style={"flex": "1", "fontSize": "0.88rem",
                                                 "color": "var(--text-primary)"}),
                        html.Span(str(count), style={"minWidth": "4rem", "textAlign": "right",
                                                      "fontSize": "0.88rem",
                                                      "color": "var(--text-secondary)"}),
                        html.Span(f"{pct}%",  style={"minWidth": "5rem", "textAlign": "right",
                                                      "fontSize": "0.9rem", "fontWeight": "600",
                                                      "color": "var(--text-primary)"}),
                    ],
                    style={
                        "display": "flex", "padding": "6px 10px",
                        "borderBottom": "1px solid rgba(255,255,255,0.05)",
                        "alignItems": "center",
                    },
                )
            )
        body = html.Div(
            [header, *rows],
            style={"maxHeight": "460px", "overflowY": "auto",
                   "borderRadius": "6px", "border": "1px solid rgba(255,255,255,0.07)"},
        )
        return True, title, body

    # ── Chances Conceded: lazy section loader ───────────────────────────────
    @app.callback(
        Output("opp-section-ccc", "children"),
        Input("opp-season-load-trigger", "data"),
        prevent_initial_call=True,
    )
    def _opp_load_ccc(trigger):
        if not trigger:
            return no_update
        from src.components.opp_season_chances_conceded_cards import build_cc_conceded_section
        return build_cc_conceded_section(trigger["season"], trigger["team"])

    # ── Chances Conceded: Overview KPI league-comparison modals ─────────────
    # Tuple: (slug, kpi_id, metric_col, fmt, total_col, show_xg_total)
    _CC_CONCEDED_KPI_MODALS = [
        ("shots-pm",       "opp-season-cc-conceded-kpi-shots-pm",       "shots_per_match",            ".1f",  "total_shots",          False),
        ("on-target-pm",   "opp-season-cc-conceded-kpi-on-target-pm",   "on_target_per_match",        ".1f",  "on_target_total",      False),
        ("goals-pm",       "opp-season-cc-conceded-kpi-goals-pm",       "goals_conceded_per_match",   ".2f",  "goals_conceded_total", False),
        ("big-chances-pm", "opp-season-cc-conceded-kpi-big-chances-pm", "big_chances_per_match",      ".1f",  "big_chances_total",    False),
        ("xg-pm",          "opp-season-cc-conceded-kpi-xg-pm",          "xg_conceded_per_match",      ".2f",  "xg_conceded_total",    True),
    ]

    for _slug, _kpi_id, _metric_col, _fmt, _total_col, _xg_flag in _CC_CONCEDED_KPI_MODALS:
        _s   = _slug
        _kid = _kpi_id
        _mc  = _metric_col
        _f   = _fmt
        _tc  = _total_col
        _xg  = _xg_flag

        @app.callback(
            Output(f"opp-season-cc-conceded-modal-{_s}",      "is_open"),
            Output(f"opp-season-cc-conceded-modal-{_s}-body", "children"),
            Input(_kid,                                         "n_clicks"),
            State("opp-season-cc-conceded-store",              "data"),
            State(f"opp-season-cc-conceded-modal-{_s}",       "is_open"),
            prevent_initial_call=True,
        )
        def _cc_conceded_kpi_modal(n, store, is_open, _mc=_mc, _f=_f, _tc=_tc, _xg=_xg):
            if not n:
                return no_update, no_update
            if is_open:
                return False, no_update
            from src.components.opp_season_chances_conceded_cards import (
                load_league_cc_conceded_summary, _league_table,
            )
            d = store or {}
            season    = d.get("season", "")
            team_name = d.get("team", "")
            season_key = season.replace("/", "_")
            summary = load_league_cc_conceded_summary(season_key)
            label = _mc.replace("_", " ").replace("per match", "/M").title()
            body = _league_table(
                summary, _mc, label, team_name,
                ascending=True, fmt=_f,
                total_col=_tc,
                show_xg_total=_xg,
            )
            return True, body

    # ── Chances Conceded: Origin breakdown league-comparison modals ──────────
    from src.analytics.chance_creation import ORIGIN_LABELS as _OPP_ORIGIN_LABELS

    for _origin in _OPP_ORIGIN_LABELS:
        _orig   = _origin
        _slug   = _origin.lower().replace(" ", "_")
        _kpi_id = f"opp-season-cc-conceded-kpi-origin-{_slug}"
        _modal  = f"opp-season-cc-conceded-modal-origin-{_slug}"

        @app.callback(
            Output(f"{_modal}",      "is_open"),
            Output(f"{_modal}-body", "children"),
            Input(_kpi_id,            "n_clicks"),
            State("opp-season-cc-conceded-store", "data"),
            State(f"{_modal}",       "is_open"),
            prevent_initial_call=True,
        )
        def _cc_conceded_origin_modal(n, store, is_open, _orig=_orig, _slug=_slug):
            if not n:
                return no_update, no_update
            if is_open:
                return False, no_update
            from src.components.opp_season_chances_conceded_cards import (
                load_league_cc_conceded_summary, _league_table,
            )
            d = store or {}
            season    = d.get("season", "")
            team_name = d.get("team", "")
            season_key = season.replace("/", "_")
            summary = load_league_cc_conceded_summary(season_key)
            pm_col  = f"{_slug}_per_match"
            tot_col = f"{_slug}_total"
            body = _league_table(
                summary, pm_col, f"{_orig}/M", team_name,
                ascending=True, fmt=".1f",
                total_col=tot_col,
                show_xg_total=False,
            )
            return True, body
