# Opponent Analysis — Offensive Transitions (Season Aggregate) — Methodology

> **Dashboard location:** Opponent Analysis → Offensive Phase → Offensive Transitions (season aggregate)
> **Analysis type:** Season-aggregate (per opponent, with league benchmarking)
> **Primary source file(s):** `analytics/precompute_serie_a.py` — `precompute_season_transitions()`; UI `components/opp_season_transitions_cards.py` (`side="offensive"`)
> **Precomputed parquet(s):** `transitions_summary_{season}.parquet` (`off_*` columns)
> **Last reviewed:** 2026-06-24

---

## 1 — Purpose

Aggregates a team's counter-attacking (offensive transitions) across a season and benchmarks it league-wide: how many counters qualify, their P1/P2/P3 danger distribution, and where they originate. It gives opponent-prep a stable read of a team's transition threat (per-match logic: [offensive-transitions.md](../../match-analysis/transitions/offensive-transitions.md)).

---

## 2 — Input Data

- **Event types used:** inherited from `analyse_offensive_transitions` — Group A/B triggers, P1/P2/P3 confirmation. Precomputed per (team, match).
- **Coordinate system:** Opta normalised (0–100), 18-zone grid for the origins density map.
- **Seasons covered:** all (2021/22–2025/26).
- **Scope:** season-aggregate per team.

---

## 3 — Methodology

### 3.1 — Source
`transitions_summary_{season}.parquet` stores both offensive (`off_`) and defensive (`def_`) columns per team. Offensive fields: `off_p1_total`, `off_p2_total`, `off_p3_total`, `off_outcomes_by_zone_json` (zone → {P1,P2,P3}), `off_outcomes_by_corridor_json` (corridor → {P1,P2,P3}), plus per-match means and "zone_lights" for the density map.

### 3.2 — Aggregation
P1/P2/P3 counts and the zone/corridor outcome dicts are aggregated across matches. Transition rate is derived per match where stored.

### 3.3 — Origins density map (green)
The offensive density map (`side="offensive"`, **green** lights) shows, per 18-zone, the season density of transitions reaching high value: **greener = more high-value counter-attacks originating from that zone**. The map is theme-aware.

### 3.4 — League benchmarking
P1/P2/P3 totals and the transition rate are ranked across all 20 teams.

---

## 4 — Key Metrics & Definitions

- **Qualifying offensive transitions (season):** total confirmed counters.
- **P1/P2/P3 distribution:** danger-tier counts (P3 = shot/penalty won).
- **Transition rate:** qualified ÷ ball recoveries.
- **Origins density (green) map:** per-zone density of high-value counters.

---

## 5 — Outputs

- **Visual outputs:** P1/P2/P3 outcome distribution, green origins density map (18-zone), corridor split, league benchmarking.
- **Parquet:** reads `transitions_summary_{season}.parquet` (`off_*`).

---

## 6 — Methodological Decisions & Rationale

- **Shared parquet with the defensive view:** offensive and defensive transitions are the same concept mirrored, so a single precompute writes both `off_` and `def_` columns; the UI selects `side` (see [opp-season-defensive-transitions.md](opp-season-defensive-transitions.md)).
- **Green for offensive value:** the colour encodes high-value counters from each zone, intuitively reading "where this team springs dangerous transitions".
- **Precompute-then-read:** per-match transition analysis is computed once at ingest.

---

## 7 — Limitations & Known Issues

- **Inherits match-module limitations:** see [offensive-transitions.md](../../match-analysis/transitions/offensive-transitions.md) (event-only, origin reconstruction).
- **Per-match-mean fields vs. totals:** some stored fields are per-match means; totals are the `*_total` columns — use the appropriate one for ratios.

---

## 8 — Relationship to Other Components

- **Upstream:** [offensive-transitions.md](../../match-analysis/transitions/offensive-transitions.md) (per-match logic), [precompute-pipeline.md](../../infrastructure/precompute-pipeline.md) (`precompute_season_transitions`), `team_mapping.canonical_name()`.
- **Downstream:** `components/opp_season_transitions_cards.py` (`side="offensive"`). Mirror of [opp-season-defensive-transitions.md](opp-season-defensive-transitions.md).
