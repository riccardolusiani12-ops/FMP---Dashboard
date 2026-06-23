#!/usr/bin/env python3
"""
Calcio Italiano — Serie A Analytics Dashboard
==============================================
Multi-page Plotly Dash application.
Run with: python app.py

Author: FMP Project
"""

from __future__ import annotations

import sys
import shutil
from pathlib import Path

# Ensure src package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

from src.config import APP_TITLE, DEBUG, LOGOS_SRC_DIR, LOGOS_DIR
from src.components.navbar import create_navbar
from src.callbacks.navigation import register_navigation_callbacks
from src.callbacks.serie_a_callbacks import register_serie_a_callbacks
from src.callbacks.team_detail_callbacks import register_team_detail_callbacks
from src.callbacks.analysis_callbacks import register_analysis_callbacks
from src.callbacks.player_analysis_callbacks import register_player_analysis_callbacks
from src.callbacks.theme_callbacks import register_theme_callbacks

# ── Bootstrap Icons CDN ──────────────────────────────────────────────────────
BOOTSTRAP_ICONS = (
    "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css"
)

# ── Google Fonts ─────────────────────────────────────────────────────────────
GOOGLE_FONTS = (
    "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap"
)


# ── Copy logos into assets/ so Dash can serve them ───────────────────────────
def _setup_logos():
    """Copy team logos from docs/logos/seriea into assets/logos/."""
    LOGOS_DIR.mkdir(parents=True, exist_ok=True)

    # Copy team logos
    if LOGOS_SRC_DIR.exists():
        for logo_file in LOGOS_SRC_DIR.glob("*.png"):
            dest = LOGOS_DIR / logo_file.name
            if not dest.exists():
                shutil.copy2(logo_file, dest)

    # Copy Italia logo from docs/logos/
    italia_src = LOGOS_SRC_DIR.parent / "italia.png"
    italia_dest = LOGOS_DIR / "italia.png"
    if italia_src.exists() and not italia_dest.exists():
        shutil.copy2(italia_src, italia_dest)


_setup_logos()


# ── Ensure precomputed data is fresh ─────────────────────────────────────────
def _ensure_fresh_data():
    """Check each season's raw data vs precomputed tables; recompute if stale."""
    from pathlib import Path
    from src.config import AVAILABLE_SEASONS, READY_DATA_DIR
    from src.analytics.data_loader import ensure_ready_data, invalidate_cache

    print("\n🔍 Checking data freshness …")
    any_refreshed = False
    for season in AVAILABLE_SEASONS:
        refreshed = ensure_ready_data(season)
        if refreshed:
            any_refreshed = True

    # Rebuild cross-season aggregations when:
    #   1. A season was just recomputed in this run, OR
    #   2. Any per-season parquet is newer than the cross-season file
    #      (catches stale aggregations left over from previous partial runs)
    cross_season_file = Path(READY_DATA_DIR) / "points_progression_all.parquet"
    need_cross_rebuild = any_refreshed

    if not need_cross_rebuild and cross_season_file.exists():
        cross_mtime = cross_season_file.stat().st_mtime
        for season in AVAILABLE_SEASONS:
            per_season = Path(READY_DATA_DIR) / f"points_progression_{season}.parquet"
            if per_season.exists() and per_season.stat().st_mtime > cross_mtime:
                print(f"  ⚠ Per-season file for {season} is newer than cross-season aggregation")
                need_cross_rebuild = True
                break

    if not need_cross_rebuild and not cross_season_file.exists():
        need_cross_rebuild = True

    if need_cross_rebuild:
        print("  Rebuilding cross-season aggregations …")
        from src.analytics.precompute_serie_a import build_league_summary
        build_league_summary()
        invalidate_cache()

    print("✅ Data check complete.\n")

    # Warm the in-memory match cache for every season
    from src.analytics.data_loader import load_season_matches_cached
    print("🔥 Warming match cache for all seasons …")
    for season in AVAILABLE_SEASONS:
        try:
            df = load_season_matches_cached(season)
            if df is not None and not df.empty:
                print(f"  ✓ Startup: ready data warmed for {season} ({len(df)} matches)")
            else:
                print(f"  ⚠ Startup: no match data available for {season} — skipping")
        except Exception as exc:
            print(f"  ✗ Startup: failed to warm cache for {season}: {exc}")
    print("🏁 Cache warm-up complete.\n")


_ensure_fresh_data()


# ── App initialization ───────────────────────────────────────────────────────
app = dash.Dash(
    __name__,
    external_stylesheets=[
        dbc.themes.DARKLY,
        BOOTSTRAP_ICONS,
        GOOGLE_FONTS,
    ],
    title=APP_TITLE,
    suppress_callback_exceptions=True,
    meta_tags=[
        {"name": "viewport", "content": "width=device-width, initial-scale=1"},
    ],
)

server = app.server

# ── App layout ───────────────────────────────────────────────────────────────
app.layout = html.Div(
    [
        # Theme persistence store
        dcc.Store(id="theme-store", data="dark", storage_type="session"),

        # URL routing
        dcc.Location(id="url", refresh=False),

        # Top navbar (always visible)
        create_navbar(),

        # Main content area — swapped by callbacks
        html.Div(id="page-content", className="main-content"),

        # Footer
        html.Footer(
            html.Div(
                [
                    html.Span(
                        "Calcio Italiano",
                        className="footer-brand",
                    ),
                    html.Span(" · "),
                    html.Span(
                        "Serie A Analytics Dashboard",
                        className="footer-subtitle",
                    ),
                    html.Span(" · "),
                    html.Span(
                        "Final Master Project",
                        className="footer-note",
                    ),
                ],
                className="footer-inner",
            ),
            className="app-footer",
        ),
    ],
    className="app-root",
    id="app-root",
)

# ── Register all callbacks ───────────────────────────────────────────────────
register_navigation_callbacks(app)
register_serie_a_callbacks(app)
register_team_detail_callbacks(app)
register_analysis_callbacks(app)
register_player_analysis_callbacks(app)
register_theme_callbacks(app)

# ── Run ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=DEBUG, host="127.0.0.1", port=8050)
