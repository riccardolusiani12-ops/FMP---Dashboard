# Goal Distribution — Methodology

> **Dashboard location:** Team Overview → Goal Distribution (by 15-minute window)
> **Analysis type:** Season-aggregate
> **Primary source file(s):** `analytics/goal_distribution.py` — `compute_goal_distribution()`, `_minute_to_bin()`, `_effective_minute()`, `_process_match_file()`; UI via Team Overview
> **Precomputed parquet(s):** Loaded via `data_loader.load_goal_distribution`; computed from CSVs / precompute.
> **Last reviewed:** 2026-06-24

---

## 1 — Purpose

Goal Distribution shows when in a match a team scores and concedes, bucketed into 15-minute windows across the season. It reveals temporal patterns — fast starters, late faders, strong finishers — that a flat goals-for/against total hides.

---

## 2 — Input Data

- **Event types used:** goal events (and own goals attributed to the conceding/scoring side as appropriate), per match.
- **Qualifiers used:** `period_id`, `time_min` for minute/period.
- **Coordinate system:** not used.
- **Seasons covered:** all (2021/22–2025/26).
- **Scope:** season-aggregate per team.

---

## 3 — Methodology

### 3.1 — 15-minute bins
Goals are bucketed into **6 bins** of 15 minutes: 0–15, 15–30, 30–45, 45–60, 60–75, 75–90 (`BINS` / `BIN_LABELS`). The result is always 6 rows.

### 3.2 — Stoppage-time handling (`_effective_minute`)
- **First-half stoppage** (`period_id == 1` and `minute ≥ 45`): the minute is capped at **44**, mapping the goal into the **30–45** bin (so 45+1' first-half goals don't leak into the 45–60 bin).
- **Second-half stoppage** (`period_id == 2` and `minute ≥ 90`): left as-is, falling naturally into the **75–90** bin.

### 3.3 — Scored vs. conceded (`_process_match_file`)
For each match, goals are attributed to the team (scored) or its opponent (conceded) and counted into the appropriate bin. The two distributions are tracked separately.

---

## 4 — Key Metrics & Definitions

- **Goals scored by bin:** count of the team's goals in each 15-minute window.
- **Goals conceded by bin:** count of goals conceded in each window.

---

## 5 — Outputs

- **DataFrame:** columns `bin, scored, conceded` (6 rows).
- **Visual output:** goal-distribution bar chart (scored vs. conceded by 15-minute bin).
- **Parquet:** via `load_goal_distribution`.

---

## 6 — Methodological Decisions & Rationale

- **First-half stoppage capped to 44':** without this, a 45+2' goal (recorded as minute 47) would fall into the 45–60 (second-half opening) bin, misrepresenting it as an early-second-half goal; capping keeps it in the correct first-half-closing window.
- **Second-half stoppage left in 75–90:** late goals belong to the closing window, which is the analytically meaningful bucket ("scores late").
- **Always 6 rows:** a fixed bin structure makes the chart and any cross-team comparison consistent.

---

## 7 — Limitations & Known Issues

- **Bin edges are coarse:** a goal on the 15th minute boundary is assigned by the half-open interval rule; very-fine timing nuance is lost.
- **Stoppage time is folded into adjacent bins:** the chart does not show a separate stoppage-time bucket; long added-time periods are absorbed into 30–45 / 75–90.

---

## 8 — Relationship to Other Components

- **Upstream:** raw event CSVs, `team_mapping.canonical_name()`.
- **Downstream:** Team Overview Goal Distribution chart (`data_loader.load_goal_distribution`).

---

## 9 — League Comparison Modals

**Goals Scored modal:** Clicking the Goals Scored card opens a league comparison table ranking all 20 Serie A teams by goals scored per match for the selected season, alongside each team's share of total league goals. The selected team's row is highlighted.

**Goals Conceded modal:** Clicking the Goals Conceded card opens a league comparison table ranking all 20 Serie A teams by goals conceded per match (ascending — fewer is better), alongside each team's share of total league goals conceded.
