# xG Summary (Team Overview) — Methodology

> **Dashboard location:** Team Overview → xG Summary
> **Analysis type:** Season-aggregate / League-wide
> **Primary source file(s):** `analytics/xg.py` — `compute_team_xg_summary()`, `load_season_shots()`; UI Team Overview via `data_loader.load_xg_summary`
> **Precomputed parquet(s):** `xg_{season}.parquet`
> **Last reviewed:** 2026-06-24

---

## 1 — Purpose

The xG Summary aggregates expected goals for and against for every team in a season, alongside actual goals, giving a model-based view of attacking and defensive quality that strips out finishing variance. It answers "is this team over- or under-performing its chances?".

---

## 2 — Input Data

- **Event types used:** shots `type_id ∈ {13,14,15,16}` (via `load_season_shots`), with per-shot xG from the model.
- **Qualifiers used:** inherited from the xG model (`Penalty`, `own goal`, etc.).
- **Coordinate system:** Opta normalised (xG geometry features).
- **Seasons covered:** all (2021/22–2025/26).
- **Scope:** season-aggregate, all teams.

---

## 3 — Methodology

### 3.1 — Season shots & xG
`load_season_shots(season)` loads every shot for the season with batch xG (full rebound + assist context), canonical team names, and `is_goal`. See [xg-model.md](../models/xg-model.md).

### 3.2 — xG for / against aggregation (`compute_team_xg_summary`)
- **xG for / GF / Shots:** grouped by the shooting team.
- **xG against (xGC) / GA / ShotsAgainst:** the opponent of each shot is resolved from the home/away canonical names, and the same shots are grouped by the conceding team.
- **xG_diff = xG − xGC**, rounded.

### 3.3 — Output table
Columns: `Team, Season, GF, GA, xG, xGC, xG_diff, Shots, ShotsAgainst`, sorted by xG descending.

---

## 4 — Key Metrics & Definitions

- **xG (for):** summed per-shot xG of the team's shots.
- **xGC (xG against):** summed per-shot xG of the opponent's shots.
- **xG_diff:** xG − xGC (net expected-goal balance).
- **GF / GA:** actual goals for / against.
- **Shots / ShotsAgainst:** shot volumes.

---

## 5 — Outputs

- **DataFrame:** `Team, Season, GF, GA, xG, xGC, xG_diff, Shots, ShotsAgainst`.
- **Visual outputs:** season xG summary table; xG vs. actual-goals comparison.
- **Parquet:** `xg_{season}.parquet` (via `load_xg_summary`).

---

## 6 — Methodological Decisions & Rationale

- **Summed per-shot xG:** the correct additive aggregation; xG for/against are sums, not averages.
- **Opponent resolution from canonical home/away:** ensures each shot's xG is credited to the correct conceding team without ambiguity.
- **xG_diff as the headline:** the net balance is the single most informative season indicator of underlying performance, separating process (xG) from outcome (goals).

---

## 7 — Limitations & Known Issues

- **Inherits xG-model limitations:** penalty fixed at 0.79, own goals 0, no tracking inputs (see [xg-model.md](../models/xg-model.md)).
- **Finishing/keeping noise not modelled:** GF−xG and GA−xGC over/under-performance is shown but not attributed to skill vs. variance.

---

## 8 — Relationship to Other Components

- **Upstream:** [xg-model.md](../models/xg-model.md) (`compute_team_xg_summary`, `load_season_shots`), `team_mapping.canonical_name()`, [precompute-pipeline.md](../infrastructure/precompute-pipeline.md) (`xg_{season}.parquet`).
- **Downstream:** Team Overview xG summary table; feeds the Playing Style Wheel's xG-based KPIs conceptually ([playing-style-wheel.md](playing-style-wheel.md)).

---

## 9 — League Comparison Modals

**xG (For) modal:** Clicking the xG card opens a league comparison table ranking all 20 Serie A teams by expected goals generated per match, alongside each team's xG share of total league xG. Values are displayed to 2 decimal places.

**xGC (Against) modal:** Clicking the xGC card opens a league comparison table ranking all 20 Serie A teams by expected goals conceded per match (ascending — lower is better), alongside each team's xGC share of total league xGC.
