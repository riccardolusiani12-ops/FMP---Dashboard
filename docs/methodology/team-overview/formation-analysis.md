# Formation Analysis — Methodology

> **Dashboard location:** Team Overview → Formations
> **Analysis type:** Season-aggregate
> **Primary source file(s):** `analytics/formations.py` — `extract_team_formations()`, `compute_formation_counts()`, `formation_display()`, `build_formation_pitch_figure()`, `assign_players_to_dots()`; UI Team Overview
> **Precomputed parquet(s):** `formations_{season}.parquet`, `formation_lineups_{season}.parquet`
> **Last reviewed:** 2026-06-24

---

## 1 — Purpose

Formation Analysis shows which formations a team used across a season, how often, and the typical XI/shape on a pitch diagram. It characterises a team's tactical setup and rotation at a glance.

---

## 2 — Input Data

- **Event types used:** `type_id 34` (Team setup → starting formation), `type_id 40` (Formation change → in-match changes).
- **Qualifiers used:** `Team Formation` / `formation` columns, `team_position`, jersey/position via `_parse_qualifiers`.
- **Coordinate system:** canonical formation templates (`_get_positions`) mapped to a pitch figure.
- **Seasons covered:** all (2021/22–2025/26).
- **Scope:** season-aggregate per team.

---

## 3 — Methodology

### 3.1 — Formation extraction (`extract_team_formations`)
Per match, the starting formation is read from the `type_id 34` Team setup event; in-match changes from `type_id 40`. Each record stores `match_file, team, formation_code, formation_str, is_starting, minute`. `formation_display(code)` converts the numeric code (e.g. 352) to a display string ("3-5-2").

### 3.2 — Formation frequency (`compute_formation_counts`)
Counts how often each formation was used across the season (typically restricted to formations appearing at least a minimum number of times via `min_count`).

### 3.3 — Formation pitch figure
`build_formation_pitch_figure` places players on the formation template; `assign_players_to_dots` uses the **Hungarian algorithm** (`_hungarian_assign`) to optimally assign players to template positions for a clean diagram.

---

## 4 — Key Metrics & Definitions

- **Formation (starting):** the `type_id 34` formation, as code and display string.
- **Formation frequency:** count of matches/usages per formation across the season.
- **Formation changes:** in-match `type_id 40` changes with minute.

---

## 5 — Outputs

- **DataFrame:** `match_file, team, formation_code, formation_str, is_starting, minute`; plus formation counts.
- **Visual outputs:** formation-count summary, formation pitch figure.
- **Parquet:** `formations_{season}.parquet`, `formation_lineups_{season}.parquet`.

---

## 6 — Methodological Decisions & Rationale

- **Formation from Opta team-setup events:** these are the authoritative formation markers; reading them directly is more reliable than inferring shape from average positions.
- **Minimum-count filter:** rare one-off formations (e.g. a 10-minute emergency reshape) are filtered from the headline frequency to show the team's genuine repertoire.
- **Hungarian assignment:** optimal player-to-slot matching avoids ambiguous nearest-dot placement in the pitch diagram.

---

## 7 — Limitations & Known Issues

- **Template, not measured positions:** the pitch figure shows nominal formation shape, not actual average player locations.
- **Depends on Opta formation tagging:** missing/late `type_id 34/40` events would mis-state formations.

---

## 8 — Relationship to Other Components

- **Upstream:** raw event CSVs, `team_mapping.canonical_name()`, [precompute-pipeline.md](../infrastructure/precompute-pipeline.md) (`precompute_formation_lineups`).
- **Downstream:** Team Overview formation card; shares logic with [match-report.md](../match-analysis/other/match-report.md).
