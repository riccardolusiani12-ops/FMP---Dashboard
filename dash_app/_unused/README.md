# _unused/

Dead code removed from the live application on 2026-06-24.
These files were part of the legacy manifest/tab UI architecture superseded
by the current page-based routing system. They are preserved here for reference
and can be permanently deleted once the cleanup branch is merged and verified.

## Contents
- `callbacks/` — tabs_callbacks.py, filters_callbacks.py (never registered in app.py)
- `tabs/` — home, match_report, team_season, player_analysis, settings (superseded by src/pages/)
- `registry/` — loaders, registry, manifest_schema (manifest-based artifact system, retired)
- `components/tables.py` — DataTable helper with zero importers
- `analytics/multi_season_standings_v1.py` — superseded by multi_season_standings.py
- `reporting/` — empty legacy sub-package (__init__.py only)
- `scripts/` — _debug_cols.py, _debug_fk.py (ad-hoc root-level debug scripts)
