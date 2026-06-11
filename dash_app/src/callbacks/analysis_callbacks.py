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

        if active_view == "offensive":
            from src.components.opponent_offensive_phase import offensive_phase_overview_card
            nav = html.Div(
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
            # Return the skeleton immediately — no heavy computation
            skeleton = html.Div([nav, offensive_phase_overview_card(season, team)])
            # Trigger value carries {season, team} so lazy callbacks can read it
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

    # ── GK section: short-pass radar toggle ────────────────────────────────
    @app.callback(
        Output("opp-season-gk-short-open",   "data"),
        Output("opp-season-gk-short-radar",  "style"),
        Output("opp-season-gk-radar-row",    "style"),
        Input("opp-season-gk-short-toggle",  "n_clicks"),
        State("opp-season-gk-short-open",    "data"),
        State("opp-season-gk-long-open",     "data"),
        prevent_initial_call=True,
    )
    def _gk_toggle_short(n, short_open, long_open):
        if not n:
            return no_update, no_update, no_update
        new_short = not short_open
        short_style = {"display": "block"} if new_short else {"display": "none"}
        either_open = new_short or bool(long_open)
        row_style = (
            {"display": "flex", "gap": "1.5rem", "marginTop": "0.5rem"}
            if either_open else {"display": "none"}
        )
        return new_short, short_style, row_style

    # ── GK section: long-ball radar toggle ─────────────────────────────────
    @app.callback(
        Output("opp-season-gk-long-open",   "data"),
        Output("opp-season-gk-long-radar",  "style"),
        Output("opp-season-gk-radar-row",   "style", allow_duplicate=True),
        Input("opp-season-gk-long-toggle",  "n_clicks"),
        State("opp-season-gk-long-open",    "data"),
        State("opp-season-gk-short-open",   "data"),
        prevent_initial_call=True,
    )
    def _gk_toggle_long(n, long_open, short_open):
        if not n:
            return no_update, no_update, no_update
        new_long = not long_open
        long_style = {"display": "block"} if new_long else {"display": "none"}
        either_open = bool(short_open) or new_long
        row_style = (
            {"display": "flex", "gap": "1.5rem", "marginTop": "0.5rem"}
            if either_open else {"display": "none"}
        )
        return new_long, long_style, row_style

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
        Output("opp-season-ft-modal-method",      "is_open"),
        Output("opp-season-ft-modal-method-body", "children"),
        Input("opp-season-ft-method-card",        "n_clicks"),
        State("opp-season-ft-entries-store",      "data"),
        State("opp-season-ft-modal-method",       "is_open"),
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
        Output("opp-season-ft-modal-success",      "is_open"),
        Output("opp-season-ft-modal-success-body", "children"),
        Input("opp-season-ft-success-card",        "n_clicks"),
        State("opp-season-ft-entries-store",       "data"),
        State("opp-season-ft-modal-success",       "is_open"),
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

    # ── FT section: Tempo modal ─────────────────────────────────────────────
    @app.callback(
        Output("opp-season-ft-modal-tempo",      "is_open"),
        Output("opp-season-ft-modal-tempo-body", "children"),
        Input("opp-season-ft-tempo-card",        "n_clicks"),
        State("opp-season-ft-entries-store",     "data"),
        State("opp-season-ft-modal-tempo",       "is_open"),
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
        Output("opp-season-ft-modal-boxtouches",      "is_open"),
        Output("opp-season-ft-modal-boxtouches-body", "children"),
        Input("opp-season-ft-boxtouches-card",        "n_clicks"),
        State("opp-season-ft-entries-store",          "data"),
        State("opp-season-ft-modal-boxtouches",       "is_open"),
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
