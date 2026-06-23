"""
Player Analysis — Callbacks
============================
Self-contained callbacks for the Player Analysis module (prefix "mp-").

All callbacks use prevent_initial_call=True and read {"csv", "team"} from the
``mp-match-store`` (set when the card is rendered), so they never iterate raw CSV
directly — they go through analyse_player_analysis() (cached per match) and apply
the same team-scoping as the initial render via _scope_to_team().

Registered once from app setup via register_player_analysis_callbacks(app).
"""

from __future__ import annotations

from pathlib import Path

from dash import ALL, Input, Output, State, ctx, no_update

from src.analytics.player_analysis import (
    KPI_DEFINITIONS,
    analyse_player_analysis,
)
from src.components.player_analysis_cards import (
    PREFIX,
    _leaderboard_figure,
    _scope_to_team,
    build_kpi_breakdown_modal_body,
    render_sequence_view,
)
from src.utils.pv_model import PossessionValueModel


def _store_csv_team(store):
    """Unpack the mp-match-store payload {"csv","team"} (tolerant of legacy str)."""
    if isinstance(store, dict):
        return store.get("csv"), store.get("team", "")
    return store, ""  # legacy: plain CSV path string


def register_player_analysis_callbacks(app):

    # 1. Sequence viewer — chip click OR dropdown change updates the rendered chain.
    @app.callback(
        Output(f"{PREFIX}-sequence-view", "children"),
        Output(f"{PREFIX}-sequence-dropdown", "value"),
        Input({"type": f"{PREFIX}-swing-chip", "index": ALL}, "n_clicks"),
        Input(f"{PREFIX}-sequence-dropdown", "value"),
        State(f"{PREFIX}-match-store", "data"),
        prevent_initial_call=True,
    )
    def _update_sequence(chip_clicks, dropdown_val, store):
        csv, _team = _store_csv_team(store)
        if not csv:
            return no_update, no_update

        trig = ctx.triggered_id
        poss_id = dropdown_val
        # If a chip fired, prefer its possession id (and sync the dropdown).
        if isinstance(trig, dict) and trig.get("type") == f"{PREFIX}-swing-chip":
            # Only honour the chip if it was actually clicked (n_clicks > 0).
            clicked = any(c for c in (chip_clicks or []))
            if clicked:
                poss_id = trig.get("index")

        if poss_id is None:
            return no_update, no_update

        # The full (unscoped) df is used to RENDER the chosen possession — scoping
        # only governs WHICH possessions are offered (chips/dropdown are already
        # team-scoped at render time), not how a selected chain is drawn.
        bundle = analyse_player_analysis(Path(csv))
        view = render_sequence_view(bundle["df"], int(poss_id),
                                    PossessionValueModel.get_instance())
        return view, poss_id

    # 2. Leaderboard bottom-toggle — rebuild all three bar charts.
    @app.callback(
        Output(f"{PREFIX}-leaderboard-off_pva", "figure"),
        Output(f"{PREFIX}-leaderboard-def_pva", "figure"),
        Output(f"{PREFIX}-leaderboard-total_pva", "figure"),
        Input(f"{PREFIX}-leaderboard-bottom-toggle", "value"),
        State(f"{PREFIX}-match-store", "data"),
        prevent_initial_call=True,
    )
    def _toggle_leaderboards(toggle_val, store):
        csv, team = _store_csv_team(store)
        if not csv:
            return no_update, no_update, no_update
        show_bottom = "bottom" in (toggle_val or [])
        bundle = _scope_to_team(analyse_player_analysis(Path(csv)), team)
        pva = bundle["pva"]
        minutes = bundle["minutes"]
        return (
            _leaderboard_figure(pva, minutes, "off_pva", team, show_bottom),
            _leaderboard_figure(pva, minutes, "def_pva", team, show_bottom),
            _leaderboard_figure(pva, minutes, "total_pva", team, show_bottom),
        )

    # 3. KPI breakdown modal — open on any In/Out KPI card click; fill the modal
    #    with that metric's definition + ranked per-player table (team-scoped).
    @app.callback(
        Output(f"{PREFIX}-kpi-modal", "is_open"),
        Output(f"{PREFIX}-kpi-modal-title", "children"),
        Output(f"{PREFIX}-kpi-modal-body", "children"),
        Input({"type": f"{PREFIX}-kpi-card", "section": ALL, "index": ALL}, "n_clicks"),
        State(f"{PREFIX}-match-store", "data"),
        State(f"{PREFIX}-kpi-modal", "is_open"),
        prevent_initial_call=True,
    )
    def _kpi_breakdown_modal(n_clicks_list, store, is_open):
        if not any(c for c in (n_clicks_list or [])):
            return no_update, no_update, no_update
        trig = ctx.triggered_id
        if not isinstance(trig, dict):
            return no_update, no_update, no_update

        metric = trig.get("index")
        section = trig.get("section")  # "in" | "out"
        meta = KPI_DEFINITIONS.get(metric)
        if not meta:
            return no_update, no_update, no_update

        csv, team = _store_csv_team(store)
        if not csv:
            return no_update, no_update, no_update

        bundle = _scope_to_team(analyse_player_analysis(Path(csv)), team)
        kpi_df = bundle["in_possession"] if section == "in" else bundle["out_possession"]
        title = metric.replace("_", " ").title()
        body = build_kpi_breakdown_modal_body(kpi_df, bundle["minutes"], metric)
        return True, title, body
