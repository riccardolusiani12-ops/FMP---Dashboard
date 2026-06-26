# Opponent Analysis — Defensive Castle (Season Aggregate) — Methodology

> **Dashboard location:** Opponent Analysis → Defensive Phase → Defensive Castle (season aggregate)
> **Analysis type:** Season-aggregate (per opponent, with league benchmarking)
> **Primary source file(s):** `analytics/precompute_serie_a.py` — `precompute_season_castle()`; UI `components/opp_season_castle_cards.py`
> **Precomputed parquet(s):** `castle_summary_{season}.parquet` (per team)
> **Last reviewed:** 2026-06-24

---

## 1 — Purpose

Aggregates a team's defensive-third (castle) defending across a season and benchmarks it league-wide: volume and type of deep defensive actions and their corridor distribution. It shows opponent-prep how a team holds its low block over a full season (per-match logic: [defensive-castle.md](../../match-analysis/defensive-phase/defensive-castle.md)).

---

## 2 — Input Data

- **Event types used:** inherited — castle actions `{4,7,8,12,44,45,49,74}` in the defensive third (`x < 33.33`), precomputed per team.
- **Qualifiers used:** inherited (`outcome` for fouls; box-aerial exclusion).
- **Coordinate system:** Opta normalised (0–100), own defensive third, 18-zone grid, corridors and sub-zones (box / deep_flank / def_third_edge).
- **Seasons covered:** all (2021/22–2025/26).
- **Scope:** season-aggregate per team.

---

## 3 — Methodology

### 3.1 — Source
`castle_summary_{season}.parquet` stores per-team season aggregates of castle actions by type, corridor, and sub-zone, plus per-match rates and the zone heatmap counts.

### 3.2 — Aggregation
Counts by action type, corridor (L/C/R), and sub-zone are summed across matches; per-match rates use matches played.

### 3.3 — League benchmarking
All 20 teams' castle aggregates are ranked for comparison bars/modals.

---

## 4 — Key Metrics & Definitions

- **Castle action count (by type / per match):** season volume of Fouls/Tackles/Interceptions/Clearances/Aerials/Challenges/Recoveries/Blocked Passes in the defensive third.
- **Corridor distribution (L/C/R):** which side the team is forced to defend.
- **Sub-zone distribution:** box / deep_flank / def_third_edge shares.
- **Zone heatmap (season):** accumulated 18-zone counts in the defensive third.

---

## 5 — Outputs

- **Visual outputs:** season defensive-third heatmap, action-type and corridor distributions, league benchmarking.
- **Parquet:** reads `castle_summary_{season}.parquet`.

---

## 6 — Methodological Decisions & Rationale

- **Wide action set retained:** as in the match module, clearances/aerials/recoveries are central to low-block defending and are included (unlike PPDA).
- **Precompute-then-read:** per-match castle analysis is computed once at ingest; the season view reads aggregates.
- **Corridor/sub-zone aggregation:** summing structural categories across the season reveals systematic defensive tendencies (e.g. consistently overloaded on one flank).

---

## 7 — Limitations & Known Issues

- **Inherits match-module limitations:** event-only defending, fixed box boundaries (see [defensive-castle.md](../../match-analysis/defensive-phase/defensive-castle.md)).
- **Benchmark completeness:** ranks assume all 20 teams precomputed.

---

## 8 — Relationship to Other Components

- **Upstream:** [defensive-castle.md](../../match-analysis/defensive-phase/defensive-castle.md) (per-match logic), [precompute-pipeline.md](../../infrastructure/precompute-pipeline.md) (`precompute_season_castle`), `team_mapping.canonical_name()`.
- **Downstream:** `components/opp_season_castle_cards.py`.
