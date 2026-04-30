"""
Download callbacks – PDF export and CSV export.
"""

from __future__ import annotations

import io
import tempfile
from pathlib import Path

import pandas as pd
from dash import Input, Output, State, callback, dcc, no_update
import dash_bootstrap_components as dbc

from src.registry.registry import ArtifactRegistry
from src.reporting.pdf_builder import build_pdf_report
from src.utils.logging import log


def register_download_callbacks(app):
    """Register download-related callbacks."""

    # ── PDF Export ─────────────────────────────────────────────────────────
    @app.callback(
        Output("download-pdf", "data"),
        Input("btn-export-pdf", "n_clicks"),
        State("filter-season", "value"),
        State("filter-team", "value"),
        State("filter-match", "value"),
        State("main-tabs", "value"),
        prevent_initial_call=True,
    )
    def export_pdf(n_clicks, season, team, match_id, active_tab):
        if not n_clicks:
            return no_update

        season = season or "2024_2025"
        team = team or "Bologna"

        try:
            # Determine which analysis to export based on active tab
            tab_analysis_map = {
                "tab-home": ["season_points_progression", "high_regains", "ppda"],
                "tab-match-report": ["attacking_phase", "high_regains", "xt", "passing_network", "epv"],
                "tab-team-season": ["season_points_progression", "ppda", "high_regains", "epv"],
                "tab-player": ["xt", "epv"],
            }
            analyses = tab_analysis_map.get(active_tab, ["high_regains"])

            # Build PDF
            pdf_bytes = build_pdf_report(
                season=season,
                team=team,
                match_id=match_id,
                analyses=analyses,
                active_tab=active_tab or "tab-home",
            )

            filename = f"report_{team}_{season}"
            if match_id:
                filename += f"_{match_id[:8]}"
            filename += ".pdf"

            return dcc.send_bytes(pdf_bytes, filename)

        except Exception as exc:
            log.error("PDF export failed: %s", exc)
            return no_update

    # ── CSV Export ─────────────────────────────────────────────────────────
    @app.callback(
        Output("download-csv", "data"),
        Input("btn-export-csv", "n_clicks"),
        State("filter-season", "value"),
        State("filter-team", "value"),
        State("filter-match", "value"),
        State("main-tabs", "value"),
        prevent_initial_call=True,
    )
    def export_csv(n_clicks, season, team, match_id, active_tab):
        if not n_clicks:
            return no_update

        season = season or "2024_2025"
        team = team or "Bologna"

        try:
            registry = ArtifactRegistry.instance()

            # Find first table-format artifact for current selection
            for fmt in ("csv", "parquet", "table_json"):
                entries = registry.query(season=season, team=team, fmt=fmt)
                if entries:
                    entry = entries[0]
                    resolved = registry.resolve_path(entry)
                    if resolved.exists():
                        if fmt == "parquet":
                            df = pd.read_parquet(resolved)
                        elif fmt == "csv":
                            df = pd.read_csv(resolved)
                        else:
                            df = pd.read_json(resolved)

                        filename = f"data_{team}_{season}.csv"
                        return dcc.send_data_frame(df.to_csv, filename, index=False)

            log.warning("No table artifacts found for CSV export")
            return no_update

        except Exception as exc:
            log.error("CSV export failed: %s", exc)
            return no_update

    log.info("Download callbacks registered")
