# Opponent Analysis — Chances Conceded (Season Aggregate) — Methodology

> **Dashboard location:** Opponent Analysis → Defensive Phase → Chances Conceded (season aggregate)
> **Analysis type:** Season-aggregate (per opponent, with league benchmarking)
> **Primary source file(s):** `analytics/precompute_serie_a.py` — `precompute_season_chances_conceded()`; UI `components/opp_season_chances_conceded_cards.py` (incl. `compute_clean_sheet_stats`, `compute_league_clean_sheets`)
> **Precomputed parquet(s):** `chances_conceded_summary_{season}.parquet` (per team)
> **Last reviewed:** 2026-06-24

---

## 1 — Purpose

Aggregates a team's chances conceded across a season and benchmarks it league-wide: xG against, shot-quality tiers conceded, and clean sheets. It gives opponent-prep a stable read of a team's defensive solidity (per-match logic: [chance-conceded.md](../../match-analysis/defensive-phase/chance-conceded.md)).

---

## 2 — Input Data

- **Event types used:** inherited — conceded shots (opponent shots, flipped) precomputed per team; scoreline goals for clean sheets.
- **Qualifiers used:** inherited (Big Chance, penalty/own-goal handling).
- **Coordinate system:** Opta normalised (0–100), defending frame (shots flipped).
- **Seasons covered:** all (2021/22–2025/26).
- **Scope:** season-aggregate per team.

---

## 3 — Methodology

### 3.1 — Source
`chances_conceded_summary_{season}.parquet` stores per-team season aggregates: total conceded shots, xG against, quality-tier distribution conceded, and supporting counts.

### 3.2 — xGA aggregation
Season xG against = sum of per-conceded-shot xG across all matches (additive). Quality-tier distribution conceded (Tiers 0/2/3) is summed across matches.

### 3.3 — Clean Sheet card (introduced in the 2025/26 build cycle)
`compute_clean_sheet_stats(season, team)` defines a **clean sheet** as any match in which the team conceded zero goals on the scoreline (home and away matches counted). It returns `clean_sheets`, `matches_played`, and `pct` (clean_sheets ÷ matches_played × 100). `compute_league_clean_sheets(season)` ranks all 20 teams for the comparison modal. This is the **first card** in the Chances Conceded section.

### 3.4 — League benchmarking
xGA and each quality tier are ranked across all 20 teams.

---

## 4 — Key Metrics & Definitions

- **xG against (xGA, season):** sum of conceded-shot xG.
- **Quality-tier distribution conceded:** counts in Tiers 0/2/3.
- **Clean sheets / clean-sheet %:** matches with zero goals conceded, and the share of matches played.
- **Big chances conceded:** Tier-2 conceded shots.

---

## 5 — Outputs

- **Visual outputs:** Clean Sheet card (first), xGA card with league comparison, conceded quality-tier distribution, league benchmarking bars.
- **Parquet:** reads `chances_conceded_summary_{season}.parquet`; clean sheets derived from match scorelines.

---

## 6 — Methodological Decisions & Rationale

- **Summed xGA:** the correct additive aggregation of expected goals against.
- **Clean sheet from scoreline, not shot model:** a clean sheet is a factual outcome (zero goals conceded), so it is read from the match result rather than inferred from xGA — making it a complementary, hard metric alongside the model-based xGA.
- **Clean Sheet card first:** placed at the head of the section as the headline defensive-solidity indicator (2025/26 addition).

---

## 7 — Limitations & Known Issues

- **Inherits match-module limitations:** see [chance-conceded.md](../../match-analysis/defensive-phase/chance-conceded.md) (single-opponent assumption, inherited xG limits).
- **Clean sheet counts own goals against the team's scoreline** as goals conceded (it is a scoreline measure), independent of the xG model.

---

## 8 — Relationship to Other Components

- **Upstream:** [chance-conceded.md](../../match-analysis/defensive-phase/chance-conceded.md) (per-match logic), [precompute-pipeline.md](../../infrastructure/precompute-pipeline.md) (`precompute_season_chances_conceded`), `team_mapping.canonical_name()`.
- **Downstream:** `components/opp_season_chances_conceded_cards.py`.
