# Opponent Analysis — Chance Creation (Season Aggregate) — Methodology

> **Dashboard location:** Opponent Analysis → Offensive Phase → Chance Creation (season aggregate)
> **Analysis type:** Season-aggregate (per opponent, with league benchmarking)
> **Primary source file(s):** `analytics/season_offensive_summary.py` — `compute_season_chance_creation()`, `compute_league_offensive_benchmarks()`; UI `components/opponent_offensive_phase.py`
> **Precomputed parquet(s):** `shots_{season}.parquet` (incl. `is_penalty`, `origin`), `offensive_summary_{season}.parquet`
> **Last reviewed:** 2026-06-24

---

## 1 — Purpose

Aggregates a team's shot and chance-creation profile across a season and benchmarks it league-wide: shot volume, xG, attack-origin distribution, big-chance rate, and penalties. It gives opponent-prep a stable read of how a team creates chances (per-shot logic: [chance-creation.md](../../match-analysis/offensive-phase/chance-creation.md), [attack-origin-classification.md](../../models/attack-origin-classification.md)).

---

## 2 — Input Data

- **Event types used:** inherited — shots precomputed into `shots_{season}.parquet` (one row per shot, with `xG`, `is_goal`, `on_target`, `origin`, `is_penalty`).
- **Qualifiers used:** inherited (Big Chance, Penalty, origin qualifiers).
- **Coordinate system:** Opta normalised (0–100).
- **Seasons covered:** all (2021/22–2025/26).
- **Scope:** season-aggregate per team.

---

## 3 — Methodology

### 3.1 — Source & matches played
`compute_season_chance_creation(season, team)` reads `shots_{season}.parquet`, filters to the team, derives matches played from `offensive_summary_{season}.parquet`.

### 3.2 — Aggregation
- **Total shots / per match**, **goals**, **on target / SoT%**, **xG total / per match** (summed across shots).
- **Top origin** (modal) and **origin counts**.
- **Per-origin data** (`origin_data`): for each of the 7 `ORIGIN_LABELS` — total, per-match, goals, and conversion % (goals ÷ shots of that origin).
- **Penalties:** the `is_penalty` column lets penalty xG and the penalty card be computed at season level using the same logic as the match view.

### 3.3 — League benchmarking
`compute_league_offensive_benchmarks(season)` computes the KPIs for all 20 teams; each KPI is ranked for the comparison modals/bars.

---

## 4 — Key Metrics & Definitions

- **Total shots / per match:** season volume and rate.
- **xG total / per match / xG per shot:** expected-goal output and average chance quality.
- **Non-penalty xG:** xG excluding penalty shots (penalty = 0.79 fixed; separable via `is_penalty`).
- **SoT% :** share of shots on target.
- **Origin distribution:** counts / per-match / goals / conversion % across the 7 origins.
- **Big chance rate:** share of Tier-2 (Big Chance) shots.
- **Penalty card (season):** penalties scored / awarded / conversion (same as match-level).

---

## 5 — Outputs

- **Result dict:** `metrics` (above, incl. `origin_data`), `shots` (records for the scatter), `matches`.
- **Visual outputs:** season shot scatter, origin breakdown, quality-tier distribution, penalty card, league benchmarking.
- **Parquet:** reads `shots_{season}.parquet`, `offensive_summary_{season}.parquet`.

---

## 6 — Methodological Decisions & Rationale

- **Summed xG, not averaged per-match xG:** season xG is the sum of per-shot xG, which is the correct additive aggregation.
- **Per-origin conversion at season level:** conversion % (goals ÷ shots) per origin reveals which creation patterns a team actually finishes, beyond raw volume.
- **`is_penalty` separation:** lets the season view report non-penalty xG and a penalty card identically to the match view, keeping penalties from distorting open-play chance quality.

---

## 7 — Limitations & Known Issues

- **Inherits match-module limitations:** see [chance-creation.md](../../match-analysis/offensive-phase/chance-creation.md), [attack-origin-classification.md](../../models/attack-origin-classification.md) (Combination catch-all), [shot-quality-tiers.md](../../models/shot-quality-tiers.md) (3-tier).
- **Conversion % on low-volume origins is noisy** (e.g. few set-piece shots → unstable conversion).

---

## 8 — Relationship to Other Components

- **Upstream:** [chance-creation.md](../../match-analysis/offensive-phase/chance-creation.md), [attack-origin-classification.md](../../models/attack-origin-classification.md), [xg-model.md](../../models/xg-model.md), [precompute-pipeline.md](../../infrastructure/precompute-pipeline.md).
- **Downstream:** `components/opponent_offensive_phase.py` chance-creation section.
