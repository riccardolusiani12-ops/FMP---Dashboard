# Opponent Analysis — Build-up to Final Third (Season Aggregate) — Methodology

> **Dashboard location:** Opponent Analysis → Offensive Phase → Build-up to Final Third (season aggregate)
> **Analysis type:** Season-aggregate (per opponent, with league benchmarking)
> **Primary source file(s):** `analytics/season_offensive_summary.py` — `compute_season_ft_entries()`, `compute_league_offensive_benchmarks()`; UI `components/opponent_offensive_phase.py`
> **Precomputed parquet(s):** `ft_entries_{season}.parquet`, `offensive_summary_{season}.parquet`
> **Last reviewed:** 2026-06-24

---

## 1 — Purpose

Aggregates a team's final-third entry profile across a season and benchmarks it league-wide: how often they enter, by which method, through which corridor, how patiently (tempo), and with what box presence and possession. It gives opponent-prep a stable picture of how a team progresses into the final third (per-match logic: [buildup-final-third.md](../../match-analysis/offensive-phase/buildup-final-third.md)).

---

## 2 — Input Data

- **Event types used:** inherited — final-third entries precomputed into `ft_entries_{season}.parquet` (one row per entry).
- **Qualifiers used:** inherited (through ball, switch, cross, long ball).
- **Coordinate system:** Opta normalised (0–100), final-third line `x = 66.67`, 18-zone grid.
- **Seasons covered:** all (2021/22–2025/26).
- **Scope:** season-aggregate per team.

---

## 3 — Methodology

### 3.1 — Source & matches played
`compute_season_ft_entries(season, team)` reads `ft_entries_{season}.parquet`, filters to the team, and derives matches played from `offensive_summary_{season}.parquet` (`matches_played`, gameweek fallback).

### 3.2 — Aggregation
- **Total entries / per match.**
- **Method distribution:** counts and percentages across the 8 stored method keys (`transition_recovery, through_ball, switch_of_play, set_piece, long_ball, cross_delivery, individual_carry, short_pass`); top method (and top method excluding `short_pass`).
- **Corridor distribution:** L/C/R counts and percentages.
- **Success rate:** positive ÷ total entries.
- **Per-match KPI cards** read from the summary parquet: `ft_possession_pct` (Possession %), `ft_box_touches_per_match` (Opposition Box Touches), `ft_passes_per_minute` (Tempo).

### 3.3 — 18-zone entry map
Entry records accumulate into the season 18-zone pitch map (zone counts summed across matches).

### 3.4 — League benchmarking
`compute_league_offensive_benchmarks(season)` computes each KPI for all 20 teams; benchmarking bar charts rank all teams.

---

## 4 — Key Metrics & Definitions

- **FT entries (total / per match):** season volume and rate.
- **Entry-method distribution:** relative frequency across the 8 methods.
- **Corridor distribution (L/C/R):** where the team enters.
- **Possession %:** team's season possession share (`ft_possession_pct`).
- **Opposition Box Touches (per match):** `ft_box_touches_per_match`.
- **Tempo:** passes per minute in qualifying possessions (`ft_passes_per_minute`).
- **Success rate:** share of positive final-third entries.

---

## 5 — Outputs

- **Result dict:** `metrics` (above), `entries` (records for the map), `matches`.
- **Visual outputs:** season 18-zone entry map, method breakdown, corridor distribution, Possession/Box-Touches/Tempo KPI cards, league benchmarking bars (all 20 teams).
- **Parquet:** reads `ft_entries_{season}.parquet`, `offensive_summary_{season}.parquet`.

---

## 6 — Methodological Decisions & Rationale

- **Per-match KPIs precomputed into the summary parquet:** possession %, box touches, and tempo are averaged at precompute time so the season view is a direct read, not a re-aggregation.
- **Relative method frequencies:** percentages (not raw counts) make teams with different entry volumes comparable.
- **Top-method-excluding-short_pass:** since `short_pass` is the default and dominates most teams, surfacing the leading *distinctive* method is more informative for opponent prep.

---

## 7 — Limitations & Known Issues

- **Inherits match-module limitations:** see [buildup-final-third.md](../../match-analysis/offensive-phase/buildup-final-third.md) (7-method taxonomy, qualifier-dependence).
- **Box touches / possession depend on precompute fields:** if the summary parquet lacks the `ft_*` fields they default to 0.

---

## 8 — Relationship to Other Components

- **Upstream:** [buildup-final-third.md](../../match-analysis/offensive-phase/buildup-final-third.md) (per-match logic), [precompute-pipeline.md](../../infrastructure/precompute-pipeline.md), `team_mapping.canonical_name()`.
- **Downstream:** `components/opponent_offensive_phase.py` final-third section.
