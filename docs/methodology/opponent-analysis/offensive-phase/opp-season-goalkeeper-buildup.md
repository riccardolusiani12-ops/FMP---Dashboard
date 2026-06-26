# Opponent Analysis — GK Build-up (Season Aggregate) — Methodology

> **Dashboard location:** Opponent Analysis → Offensive Phase → Goalkeeper Build-up (season aggregate)
> **Analysis type:** Season-aggregate (per opponent, with league benchmarking)
> **Primary source file(s):** `analytics/season_offensive_summary.py` — `compute_season_gk_buildup()`, `compute_league_offensive_benchmarks()`; UI via `components/opponent_offensive_phase.py`
> **Precomputed parquet(s):** `gk_events_{season}.parquet`, `offensive_summary_{season}.parquet`
> **Last reviewed:** 2026-06-24

---

## 1 — Purpose

This view aggregates a team's goal-kick build-up across a full season and benchmarks it against all 20 Serie A clubs, so an analyst preparing for an opponent can see that team's typical build-up tendencies (short vs long, success rate, where the ball lands) rather than a single match. The per-match logic is identical to the match-level module ([goalkeeper-buildup.md](../../match-analysis/offensive-phase/goalkeeper-buildup.md)); this layer aggregates and ranks.

---

## 2 — Input Data

- **Event types used:** inherited — goal kicks only (per-match GK build-up records precomputed into `gk_events_{season}.parquet`, one row per GK possession event).
- **Qualifiers used:** inherited from the match module (`Goal Kick` etc.).
- **Coordinate system:** Opta normalised (0–100), 18-zone grid.
- **Seasons covered:** all (2021/22–2025/26).
- **Scope:** season-aggregate per team.

---

## 3 — Methodology

### 3.1 — Source
`compute_season_gk_buildup(season, team)` reads the precomputed `gk_events_{season}.parquet` (all teams) and filters to the team. Matches played (`mp`) comes from `offensive_summary_{season}.parquet` (`matches_played`), falling back to distinct gameweeks.

### 3.2 — Aggregation
- **Short / Long** counts and percentages from `pass_type` (short = first-receiver Z1–Z6).
- **Positive %** from `outcome == "positive"` over all goal kicks.
- **Short / Long success rates** = positive ÷ count within each type.
- **Avg per match** = total ÷ matches played.
- **Granular counts** (P1/P2/P3, N1/N2/N3) overall and split by short/long.
- **Zone map**: first-receiver zone counts (from event records).

### 3.3 — League benchmarking
`compute_league_offensive_benchmarks(season)` aggregates the same KPIs for all 20 teams; the selected team's value is ranked against the league for the comparison modals/bars.

---

## 4 — Key Metrics & Definitions

- **Total goal kicks / per match:** season volume and rate.
- **Short / Long % :** distribution of build-up by first-receiver zone.
- **Positive % :** share of goal kicks where possession was retained ≥15 s.
- **Short / Long success rate:** retention rate within each build-up type.
- **Granular P1–P3 / N1–N3:** retention quality / loss severity distribution.
- **Zone heatmap (season):** accumulated first-receiver zones.

---

## 5 — Outputs

- **Result dict:** `metrics` (above), `events` (per-event records for the scatter), `matches`.
- **Visual outputs:** season 18-zone heatmap, short/long + success KPI cards with league-comparison modals.
- **Parquet:** reads `gk_events_{season}.parquet`, `offensive_summary_{season}.parquet`.

---

## 6 — Methodological Decisions & Rationale

- **Precompute-then-aggregate:** the heavy per-match GK analysis is run once at ingest and stored, so the season view is a fast filter+aggregate rather than re-parsing CSVs.
- **Matches-played from the summary parquet:** ensures per-match rates use the correct denominator even when a team missed gameweeks, with a gameweek-count fallback.
- **Success rates within type:** separating short vs long success avoids a blended number hiding that a team is, say, excellent short but poor long.

---

## 7 — Limitations & Known Issues

- **Inherits match-module limitations:** see [goalkeeper-buildup.md](../../match-analysis/offensive-phase/goalkeeper-buildup.md) (Opta `Goal Kick` dependence, short/long-only taxonomy).
- **Benchmark needs all teams precomputed:** ranks assume the league parquet is complete for the season.

---

## 8 — Relationship to Other Components

- **Upstream:** [goalkeeper-buildup.md](../../match-analysis/offensive-phase/goalkeeper-buildup.md) (per-match logic), [precompute-pipeline.md](../../infrastructure/precompute-pipeline.md) (`precompute_season_offensive`), `team_mapping.canonical_name()`.
- **Downstream:** `components/opponent_offensive_phase.py` GK build-up section.
