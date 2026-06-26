# Opponent Analysis — Defensive Transitions (Season Aggregate) — Methodology

> **Dashboard location:** Opponent Analysis → Defensive Phase → Defensive Transitions (season aggregate)
> **Analysis type:** Season-aggregate (per opponent, with league benchmarking)
> **Primary source file(s):** `analytics/precompute_serie_a.py` — `precompute_season_transitions()`; UI `components/opp_season_transitions_cards.py` (`side="defensive"`)
> **Precomputed parquet(s):** `transitions_summary_{season}.parquet` (`def_*` columns)
> **Last reviewed:** 2026-06-24

---

## 1 — Purpose

Aggregates the counters a team *concedes* (defensive transitions) across a season and benchmarks it league-wide: how many qualifying transitions the opponent generates against the team, their N1/N2/N3 danger distribution, and where they originate. It gives opponent-prep a stable read of a team's transition vulnerability (per-match logic: [defensive-transitions.md](../../match-analysis/transitions/defensive-transitions.md)). This is the defensive mirror of [opp-season-offensive-transitions.md](opp-season-offensive-transitions.md).

---

## 2 — Input Data

- **Event types used:** inherited from `compute_defensive_transitions` (via `analyse_defensive_structure`) — Group A/B triggers, N1/N2/N3 confirmation. Precomputed per (team, match).
- **Coordinate system:** Opta normalised (0–100), 18-zone grid for the origins density map (defensive frame).
- **Seasons covered:** all (2021/22–2025/26).
- **Scope:** season-aggregate per team.

---

## 3 — Methodology

### 3.1 — Source
The same `transitions_summary_{season}.parquet`. Defensive fields: `def_n1_total`, `def_n2_total`, `def_n3_total`, `def_outcomes_by_zone_json` (zone → {N1,N2,N3}), `def_outcomes_by_corridor_json`, plus per-match means and zone_lights.

### 3.2 — Aggregation
N1/N2/N3 counts and the zone/corridor outcome dicts are aggregated across matches; transition rate per match where stored.

### 3.3 — Origins density map (red)
The defensive density map (`side="defensive"`, **red** lights) shows, per 18-zone, the season density of transitions the opponent generated against the team reaching high value: **redder = more high-value opponent counters from that zone** (i.e. more vulnerable zones). Same zone/colour machinery as the offensive map, defensive frame.

### 3.4 — League benchmarking
N1/N2/N3 totals and the transition rate conceded are ranked across all 20 teams.

---

## 4 — Key Metrics & Definitions

- **Qualifying defensive transitions (season):** total confirmed counters conceded.
- **N1/N2/N3 distribution:** danger-tier counts of conceded counters (N3 = opponent shot / penalty conceded).
- **Transition rate (conceded):** qualified ÷ possession losses.
- **Origins density (red) map:** per-zone density of high-value opponent counters (vulnerable zones).

---

## 5 — Outputs

- **Visual outputs:** N1/N2/N3 outcome distribution, red origins density map (18-zone), corridor split, league benchmarking.
- **Parquet:** reads `transitions_summary_{season}.parquet` (`def_*`).

---

## 6 — Methodological Decisions & Rationale

- **Shared parquet, `side` switch:** one precompute writes both perspectives; the UI renders the defensive side with N-tiers and the red map.
- **Red for conceded danger:** the colour encodes where the team is most exposed to counters, intuitively reading "danger zones".
- **Aggregate-ratio rates:** as with pressing, rates use summed numerators/denominators where applicable rather than means of per-match rates.

---

## 7 — Limitations & Known Issues

- **Spec note (documented, code wins):** the audit brief referred to P-tiers; the defensive view uses **N1/N2/N3** (the conceded perspective).
- **Inherits match-module limitations:** see [defensive-transitions.md](../../match-analysis/transitions/defensive-transitions.md).

---

## 8 — Relationship to Other Components

- **Upstream:** [defensive-transitions.md](../../match-analysis/transitions/defensive-transitions.md) (per-match logic), [precompute-pipeline.md](../../infrastructure/precompute-pipeline.md) (`precompute_season_transitions`), `team_mapping.canonical_name()`.
- **Downstream:** `components/opp_season_transitions_cards.py` (`side="defensive"`). Mirror of [opp-season-offensive-transitions.md](opp-season-offensive-transitions.md).
