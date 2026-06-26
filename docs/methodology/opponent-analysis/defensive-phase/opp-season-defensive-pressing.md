# Opponent Analysis — Defensive Pressing (Season Aggregate) — Methodology

> **Dashboard location:** Opponent Analysis → Defensive Phase → Pressing (season aggregate)
> **Analysis type:** Season-aggregate (per opponent, with league benchmarking)
> **Primary source file(s):** `analytics/precompute_serie_a.py` — `precompute_season_pressing()`; UI `components/opp_season_pressing_cards.py`
> **Precomputed parquet(s):** `pressing_actions_{season}.parquet`, `pressing_summary_{season}.parquet`
> **Last reviewed:** 2026-06-24

---

## 1 — Purpose

Aggregates a team's pressing across a season and benchmarks it league-wide: PPDA, pressing height/direction, and total defensive activity. It gives opponent-prep a stable read of how aggressively and where a team presses (per-match logic: [defensive-pressing.md](../../match-analysis/defensive-phase/defensive-pressing.md)).

---

## 2 — Input Data

- **Event types used:** inherited from the match module — PPDA denominator `{4,7,8,45}`; wide defensive set `{4,7,8,12,44,45,49,74}`; opponent passes `{1,2,74}`. Precomputed per (team, match) into the parquets.
- **Qualifiers used:** inherited (`Long ball`, `Throw In`).
- **Coordinate system:** Opta normalised (0–100), pressing zones reflected via `x_att = 100 − x`.
- **Seasons covered:** all (2021/22–2025/26).
- **Scope:** season-aggregate per team.

---

## 3 — Methodology

### 3.1 — Source
`pressing_summary_{season}.parquet` stores, per team: `total_def_actions`, `actions_per_match`, and PPDA numerators/denominators for each zone — `ppda_num_overall/den_overall/overall`, `ppda_num_high/den_high/high`, `ppda_num_mid/den_mid/mid` — plus height/direction aggregates. `pressing_actions_{season}.parquet` holds one row per defensive action for the heatmap.

### 3.2 — Season PPDA = aggregate ratio
Season PPDA is computed as **aggregate numerator ÷ aggregate denominator** (sum of opponent passes ÷ sum of defensive actions across all matches), **not** the mean of per-match PPDA values. Storing the numerator and denominator separately is what enables this correct aggregation.

### 3.3 — Height & direction
Pressing height (High/Mid/Low) and direction (L/C/R) are aggregated across the season from the per-action records.

### 3.4 — League benchmarking
All 20 teams' season PPDA and pressing metrics are ranked for the comparison bars/modals.

---

## 4 — Key Metrics & Definitions

- **Season PPDA (overall/high/mid):** Σ opponent passes ÷ Σ defensive actions in the pressing zone.
- **Pressing height:** season distribution across High/Mid/Low thirds.
- **Pressing direction:** season L/C/R distribution.
- **Total defensive actions / per match:** wide-set defensive volume.

---

## 5 — Outputs

- **Visual outputs:** season PPDA cards (with league-comparison), pressing-height/direction summaries, action heatmap, league benchmarking bars.
- **Parquet:** reads `pressing_summary_{season}.parquet`, `pressing_actions_{season}.parquet`.

---

## 6 — Methodological Decisions & Rationale

- **Aggregate-ratio PPDA (critical):** averaging per-match PPDAs over-weights low-activity matches and is statistically wrong for a ratio; summing numerators and denominators first gives the true season pressing intensity. Numerator/denominator are precomputed and stored precisely so this aggregation is possible.
- **Narrow PPDA denominator preserved:** the season view uses the same `{tackles, interceptions, fouls, challenges}` denominator as the match view (see [defensive-pressing.md](../../match-analysis/defensive-phase/defensive-pressing.md)) — this differs from the Team Overview PPDA variant ([ppda-team-overview.md](../../team-overview/ppda-team-overview.md)).
- **Precompute-then-read:** per-match pressing is computed once at ingest and stored, so the season view is a fast read.

---

## 7 — Limitations & Known Issues

- **Inherits match-module limitations:** event-only pressing, success heuristic (see [defensive-pressing.md](../../match-analysis/defensive-phase/defensive-pressing.md)).
- **Benchmark completeness:** ranks assume all 20 teams precomputed for the season.

---

## 8 — Relationship to Other Components

- **Upstream:** [defensive-pressing.md](../../match-analysis/defensive-phase/defensive-pressing.md) (per-match logic), [precompute-pipeline.md](../../infrastructure/precompute-pipeline.md) (`precompute_season_pressing`), `team_mapping.canonical_name()`.
- **Downstream:** `components/opp_season_pressing_cards.py`. Contrast with [ppda-team-overview.md](../../team-overview/ppda-team-overview.md) (different denominator).
