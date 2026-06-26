# Opponent Analysis — Corner Kicks (Season Aggregate) — Methodology

> **Dashboard location:** Opponent Analysis → Set Pieces → Corner Kicks (season aggregate)
> **Analysis type:** Season-aggregate (per opponent, with league benchmarking)
> **Primary source file(s):** `analytics/precompute_serie_a.py` — `precompute_season_corner_kicks()`; UI `components/opp_season_corner_kicks_cards.py`
> **Precomputed parquet(s):** `corner_kicks_summary_{season}.parquet` (per team)
> **Last reviewed:** 2026-06-24

---

## 1 — Purpose

Aggregates a team's corner-kick attacking across a season and benchmarks it league-wide: how many corners, how productive, how delivered, and to which side. It gives opponent-prep a stable read of a team's corner routines and threat (per-match logic: [corner-kicks.md](../../match-analysis/set-pieces/corner-kicks.md)).

---

## 2 — Input Data

- **Event types used:** inherited — corners (`Corner taken`) precomputed per team, with delivery type, 9-zone, outcome, side (`is_left`), and taker.
- **Coordinate system:** Opta normalised (0–100), 9-zone goalmouth taxonomy (GA1–3, CA1–3, Edge, Front, Back), left/right delivery maps.
- **Seasons covered:** all (2021/22–2025/26).
- **Scope:** season-aggregate per team.

---

## 3 — Methodology

### 3.1 — Source
`corner_kicks_summary_{season}.parquet` stores per-team season aggregates: total corners; outcome counts (`goals` — which *includes* own goals, `shot_on_target`, `shot_off_target`, `cleared`, `second_phase`); `conversion_rate` (goals ÷ total corners × 100, season ratio); `delivery_counts_json`; `delivery_outcomes_json` (with **Own Goal kept as its own outcome key**); `zone_counts_json` (9 zones + Unknown); and per-corner records (`is_left`, end_x/y, outcome, delivery, zone, taker) to rebuild the two season delivery maps.

### 3.2 — KPI cards
Corners taken, goals from corners, conversion rate, shots from corners, corners left side, corners right side — each computed from the season aggregates; headline values are season averages per match where applicable.

### 3.3 — Own-goal handling
Own goals from corners are **included in the delivery-outcome matrix** (as their own `Own Goal` key, and folded into the `goals` outcome count) but are **excluded from the main Goals KPI** card so the headline reflects goals the team itself scored.

### 3.4 — Left/Right delivery maps
Per-corner records (with `is_left`) rebuild two separate season pitch panels — one for left-side corners, one for right — preserving the side-relative 9-zone semantics.

### 3.5 — League benchmarking
Corner volume, conversion, and shot output are ranked across all 20 teams.

---

## 4 — Key Metrics & Definitions

- **Corners taken:** season total (and per match).
- **Goals from corners:** corner-originated goals (headline excludes own goals).
- **Conversion rate:** goals ÷ corners (season ratio; this `goals` includes own goals).
- **Shots from corners:** corner-originated shots.
- **Corners left / right side:** split by `is_left`.
- **Delivery-type matrix:** counts by Inswinger/Outswinger/Straight/Short × outcome (incl. Own Goal).
- **9-zone distribution:** season corner-target zones.

---

## 5 — Outputs

- **Visual outputs:** delivery-type matrix, KPI cards (corners, goals, conversion, shots, left/right), two left/right delivery maps, 9-zone map, league benchmarking.
- **Parquet:** reads `corner_kicks_summary_{season}.parquet`.

---

## 6 — Methodological Decisions & Rationale

- **Own goals in the matrix but not the Goals KPI:** an own goal forced from a corner is a real product of the routine (so it belongs in the delivery-outcome matrix) but is not a goal the team *scored* (so it is excluded from the headline Goals card) — this split avoids both under- and over-crediting.
- **Per-corner records retained:** keeping the raw corner rows in the parquet lets the season delivery maps be rebuilt side-relative without re-parsing CSVs.
- **Conversion as a season ratio:** total goals ÷ total corners is the correct additive conversion, not a mean of per-match conversions.

---

## 7 — Limitations & Known Issues

- **Inherits match-module limitations:** see [corner-kicks.md](../../match-analysis/set-pieces/corner-kicks.md) (coordinate fallback for missing swing qualifiers, sequence-based outcomes).
- **`goals` outcome includes own goals:** the conversion-rate denominator/numerator uses this, so conversion is slightly higher than "team-scored goals ÷ corners".

---

## 8 — Relationship to Other Components

- **Upstream:** [corner-kicks.md](../../match-analysis/set-pieces/corner-kicks.md) (per-match logic), [precompute-pipeline.md](../../infrastructure/precompute-pipeline.md) (`precompute_season_corner_kicks`), `team_mapping.canonical_name()`.
- **Downstream:** `components/opp_season_corner_kicks_cards.py`.
