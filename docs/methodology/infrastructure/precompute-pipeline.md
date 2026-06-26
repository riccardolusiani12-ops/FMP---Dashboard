# Precompute Pipeline — Methodology

> **Dashboard location:** Cross-cutting infrastructure (runs at ingest; no UI surface)
> **Analysis type:** Infrastructure / data pipeline
> **Primary source file(s):** `analytics/precompute_serie_a.py` (`precompute_all`, `precompute_season`, the `precompute_season_*` functions); `analytics/data_loader.py` (`ensure_ready_data`, `_raw_data_is_newer`, `check_ready_data`)
> **Precomputed parquet(s):** all season-level parquets (listed below)
> **Last reviewed:** 2026-06-24

---

## 1 — Purpose

The precompute pipeline performs all heavy event-level analysis **once at ingest** and writes the results to Parquet, so that Dash callbacks never parse raw CSVs at request time. This is the architectural decision that makes the dashboard responsive: callbacks read small, ready Parquet tables instead of re-running multi-second analyses per interaction.

---

## 2 — Input Data

- **Input:** raw Opta event CSVs under `RAW_DATA_DIR/serie_a_*/events/*.csv`.
- **Output:** Parquet tables under `READY_DATA_DIR` (and intermediate `PROCESSED_DATA_DIR`).
- **Seasons covered:** all available (`AVAILABLE_SEASONS`, 2021/22–2025/26).
- **Scope:** per-season, plus cross-season aggregations.

---

## 3 — Methodology

### 3.1 — The precompute-at-ingest decision
Previously, callbacks read raw CSVs and ran analyses inline, which could take on the order of ~50 seconds. Moving all of this to a precompute step that writes Parquet reduced per-callback cost to sub-second reads. No raw CSV reads occur inside Dash callbacks.

### 3.2 — What is precomputed (`precompute_season` → `precompute_season_*`)
Per season, the pipeline writes (selected):
- Core: `matches_{s}`, `standings_{s}`, `points_progression_{s}`, `team_overview_{s}`, `ppda_{s}`, `season_teams_{s}`, `xg_{s}`, `formations_{s}`, `formation_lineups_{s}`.
- Offensive (`precompute_season_offensive`): `gk_events_{s}`, `ft_entries_{s}`, `shots_{s}` (incl. `is_penalty`), `offensive_summary_{s}`.
- Defensive / set-piece: `pressing_actions_{s}`, `pressing_summary_{s}`, `castle_summary_{s}`, `chances_conceded_summary_{s}`, `transitions_summary_{s}` (off_+def_), `corner_kicks_summary_{s}`.
- Style & players: `playing_style_league_{s}`, `player_season_{s}` (+ `player_season_{s}_k_table.json`).
- Cross-season: `league_summary.parquet`, `points_progression_all.parquet`.

### 3.3 — Staleness detection (`_raw_data_is_newer`)
Before serving, freshness is checked against three signals using the season's `standings` Parquet as reference:
1. The reference Parquet is missing/corrupted (`_is_readable_parquet`).
2. The newest CSV mtime is later than the Parquet mtime.
3. The CSV count differs from a stored fingerprint file (`.csv_count_{season}`) — catches files copied with old mtimes.
Any signal triggers recomputation.

### 3.4 — Ensure-ready chain (`ensure_ready_data`)
`ensure_ready_data(season)` recomputes when any key Parquet table is missing **or** the raw CSVs are newer (per §3.3). `check_ready_data` reports which ready tables exist and are readable (corrupted Parquets treated as missing). This chain guarantees the dashboard always serves fresh, valid data without manual intervention.

### 3.5 — Orchestration (`precompute_all`)
Runs `precompute_season` for each target season, then cross-season aggregations (`build_league_summary`). Invokable via CLI (`python -m ... precompute_serie_a [seasons]`).

---

## 4 — Key Metrics & Definitions

Not applicable — this is infrastructure. Its "outputs" are the Parquet tables consumed by every analytical component.

---

## 5 — Outputs

- **All season-level Parquet tables** (§3.2) under `READY_DATA_DIR`, plus cross-season `league_summary.parquet` and `points_progression_all.parquet`, and the player K-table JSON sidecar.

---

## 6 — Methodological Decisions & Rationale

- **Precompute-at-ingest over compute-in-callback:** the dominant design decision; trades a one-time ingest cost for sub-second interactivity and eliminates repeated CSV parsing.
- **Triple staleness signal:** mtime alone is unreliable when files are copied with preserved timestamps, so a CSV-count fingerprint is added; corruption is also treated as stale. This makes refresh robust to how new matchday data arrives.
- **Standings Parquet as the freshness reference:** a single, always-written table acts as the canonical "last precompute" marker for the season.
- **Compute each match bundle once:** expensive bundles (e.g. player PV) are computed once per match and routed to both teams, avoiding double work.

---

## 7 — Limitations & Known Issues

- **Reference-table coupling:** freshness keys off the standings Parquet; if it were updated independently of the others, staleness detection could be misled.
- **Full-season recompute granularity:** a single new match typically triggers a season recompute rather than an incremental update.
- **Build of the PV model is separate:** the PV model is built via its own CLI, not this pipeline (see [possession-value-model.md](../models/possession-value-model.md)).

---

## 8 — Relationship to Other Components

- **Upstream:** raw Opta CSVs, every `analytics/*` module that produces a season aggregate.
- **Downstream:** `data_loader.py` and the [caching-layer.md](caching-layer.md); every season-aggregate and Team Overview component reads these Parquets.
