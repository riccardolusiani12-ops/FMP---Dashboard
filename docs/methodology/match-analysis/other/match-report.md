# Match Report — Methodology

> **Dashboard location:** Match Analysis → Match Report (Match Analysis / Opponent Analysis toggle)
> **Analysis type:** Match-level (presentation + lineup/formation extraction)
> **Primary source file(s):** `tabs/match_report.py` (UI shell), `analytics/formations.py` (`extract_team_formations`, `extract_formation_lineup_stats`, `build_formation_pitch_figure`, `assign_players_to_dots`), `src/registry/loaders.py` (artifact rendering)
> **Precomputed parquet(s):** Formation/lineup parquets written by `precompute_formation_lineups` (see [formation-analysis.md](../../team-overview/formation-analysis.md) and [precompute-pipeline.md](../../infrastructure/precompute-pipeline.md)).
> **Last reviewed:** 2026-06-24

---

## 1 — Purpose

The Match Report is the overview page for a selected match: formations, starting lineups, match metadata, and key player events. It gives the analyst the context for the rest of the Match Analysis tab — who played, in what shape, and how the match unfolded — before drilling into the phase-by-phase analytics. The tab itself is a thin presentation shell; the analytical substance (formation and lineup extraction) lives in `analytics/formations.py`.

---

## 2 — Input Data

- **Event types used:** `type_id 34` (Team setup → starting formation), `type_id 40` (Formation change → in-match changes); player/start metadata from team-setup qualifiers; goals/cards/substitutions from their respective Opta event types.
- **Qualifiers used:** `Team Formation` / `formation` columns, `team_position`, jersey/position qualifiers parsed via `_parse_qualifiers`.
- **Coordinate system:** formation pitch dots use canonical formation templates (`_get_positions`) mapped to a pitch figure.
- **Seasons covered:** all (2021/22–2025/26).
- **Scope:** per-match (with season aggregation available for lineup stats).

---

## 3 — Methodology

### 3.1 — UI shell (`tabs/match_report.py`)
The tab provides a Match Analysis / Opponent Analysis toggle and renders pre-computed artifacts via `render_artifacts_for_analysis`. It contains no analytics itself — it assembles and displays outputs produced by the formation/lineup extraction and the precompute pipeline.

### 3.2 — Formation extraction (`extract_team_formations`)
For each match, the **starting formation** is read from the `type_id 34` Team setup event and **in-match changes** from `type_id 40` Formation change events. Formations are stored both as a numeric code (e.g. 352) and a display string (e.g. "3-5-2", via `formation_display`), with `is_starting` and `minute`.

### 3.3 — Lineup stats (`extract_formation_lineup_stats`)
For matches where the team started in a given formation, per-player season aggregates are collected for starters (formation slots 1–11): starts, total minutes, average minutes per start, jersey, position code/label. When multiple players shared a slot, the top contributor (most starts) is primary; all are returned so the UI can show depth.

### 3.4 — Pitch figure (`build_formation_pitch_figure` + `assign_players_to_dots`)
Players are assigned to formation template positions. Slot-to-dot assignment uses the **Hungarian algorithm** (`_hungarian_assign`) to optimally match players to template coordinates, producing the formation pitch visualisation.

### 3.5 — Player events & metadata
Goals, cards, assists, and substitutions are attributed to players from their Opta events to populate the match timeline and lineup annotations.

---

## 4 — Key Metrics & Definitions

- **Starting formation:** the `type_id 34` formation, as code and display string.
- **Formation changes:** in-match `type_id 40` changes, with minute.
- **Lineup (starters):** slot 1–11 players with starts, minutes, position.
- **Player events:** goals / cards / assists / substitutions attributed per player.

---

## 5 — Outputs

- **Formation DataFrame:** `match_file, team, formation_code, formation_str, is_starting, minute`.
- **Lineup DataFrame:** `slot, player_id, name, jersey, pos_code, pos_label, starts, total_mins, avg_mins_per_start`.
- **Visual outputs:** formation pitch figure, lineup list, match metadata/timeline.
- **Parquet:** formation/lineup parquets via `precompute_formation_lineups`.

---

## 6 — Methodological Decisions & Rationale

- **Tab as a presentation shell:** keeping the Match Report UI free of analytics (rendering pre-computed artifacts) keeps callbacks fast and centralises formation logic in `formations.py`.
- **Formation from Team-setup events (`type_id 34/40`):** these are Opta's authoritative formation markers, so the starting shape and changes come directly from the data rather than being inferred from positions.
- **Hungarian assignment for dots:** optimally matching players to template slots avoids ad-hoc nearest-dot heuristics and produces a clean, unambiguous formation diagram.
- **Top-contributor-per-slot with full depth returned:** surfaces the primary XI while preserving rotation information for the UI.

---

## 7 — Limitations & Known Issues

- **Formation code is a template:** the pitch figure uses canonical formation templates, not actual average player positions, so it shows nominal shape rather than measured positioning.
- **Depends on Opta formation tagging:** missing or late `type_id 34/40` events would mis-state the formation.
- **Lineup aggregation is season-scoped per formation:** a player who started in multiple formations appears under each.

---

## 8 — Relationship to Other Components

- **Upstream:** `analytics/formations.py`, `team_mapping.canonical_name()`, the precompute pipeline (`precompute_formation_lineups`).
- **Downstream:** the Match Report UI; shares formation logic with Team Overview Formation Analysis ([formation-analysis.md](../../team-overview/formation-analysis.md)).
