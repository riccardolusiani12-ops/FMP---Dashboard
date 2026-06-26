# PPDA (Team Overview) — Methodology

> **Dashboard location:** Team Overview → Pressing / PPDA league table, scatter, bar, points progression
> **Analysis type:** Season-aggregate / League-wide
> **Primary source file(s):** `analytics/ppda.py` — `load_season_events()`, `compute_ppda()`, `compute_field_tilt()`, `build_ppda_table()`, `build_ppda_bar_figure()`, `build_ppda_scatter_figure()`; UI `pages/serie_a.py` / `team_detail.py`
> **Precomputed parquet(s):** `ppda_{season}.parquet` (PPDA + field tilt), `points_progression_{season}.parquet`
> **Last reviewed:** 2026-06-24

---

## 1 — Purpose

The Team Overview PPDA gives a season-long, league-wide view of pressing intensity for all 20 clubs, alongside field tilt (territorial dominance) and points progression. It is the "where does this team sit in the league" pressing view, complementary to the per-match Match Analysis PPDA. **Critically, it uses a different (broader) PPDA denominator than the Match Analysis variant.**

---

## 2 — Input Data

- **Event types used:** `is_pass` (event == "pass") for opponent passes; **`is_regain` (event == "ball recovery")** for the pressing-team denominator; passes in the final third for field tilt.
- **Qualifiers used:** `outcome` (success), team_position (home/away resolution).
- **Coordinate system:** Opta normalised, with `x_from_own_goal` reflected so each team's pressing is measured in a common frame. PPDA zone: passer `x_from_own_goal ≤ PPDA_ZONE_UPPER = 60`; regains at `x_from_own_goal ≥ PRESSING_ZONE_MIN = 40`. Field-third line 66.67.
- **Seasons covered:** all (2021/22–2025/26).
- **Scope:** season-aggregate, all teams.

---

## 3 — Methodology

### 3.1 — Season PPDA (`compute_ppda`)
- **Numerator:** opponent passes in their own defensive zone (`x_from_own_goal ≤ 60`), grouped by the pressing team.
- **Denominator:** the pressing team's **ball recoveries** (`is_regain`) in the same zone (`x_from_own_goal ≥ 40`).
- **PPDA = passes allowed ÷ ball recoveries**, computed as an aggregate ratio over the season. Per-match PPDA is also computed to give a standard deviation (`ppda_std`) and match count.

### 3.2 — Field tilt (`compute_field_tilt`)
Field Tilt (%) = team's final-third passes ÷ total final-third passes (both teams) × 100, where the final third is `x_from_own_goal > 66.67`. It measures territorial dominance.

### 3.3 — League table & figures
`build_ppda_table` ranks all teams (ascending PPDA = most intense first). `build_ppda_bar_figure` ranks teams by PPDA; `build_ppda_scatter_figure` plots two dimensions (e.g. PPDA vs. field tilt / another pressing axis) to position teams.

### 3.4 — Points progression
Cumulative points per team across matchdays (from `points_progression_{season}.parquet`), plotted as a season trajectory.

---

## 4 — Key Metrics & Definitions

- **PPDA (Team Overview):** opponent passes in their defensive zone ÷ **pressing team's ball recoveries** in the same zone. Lower = more intense.
- **PPDA std / matches:** dispersion and count of per-match PPDA.
- **Field tilt (%):** share of all final-third passes made by the team.
- **Points progression:** cumulative league points by matchday.

---

## 5 — Outputs

- **League table:** `team_short, passes_allowed, ball_recoveries, PPDA, matches, ppda_std` (+ field tilt).
- **Figures:** PPDA bar (ranking), PPDA scatter (two dimensions), points-progression line.
- **Parquet:** `ppda_{season}.parquet`, `points_progression_{season}.parquet`.

---

## 6 — Methodological Decisions & Rationale

- **Ball-recoveries denominator (the key difference):** the Team Overview PPDA defines a defensive action as a **ball recovery** (`is_regain`), giving `PPDA = passes allowed ÷ ball recoveries`. This is **broader and different** from the Match Analysis PPDA, whose denominator is the narrow `{tackles, interceptions, fouls, challenges}` set and explicitly *excludes* ball recoveries (see [defensive-pressing.md](../match-analysis/defensive-phase/defensive-pressing.md)). The two PPDA numbers are therefore not directly comparable: the Team Overview value uses recoveries as the pressing-success proxy, the Match Analysis value uses the industry-standard challenge set. This divergence is intentional and is the single most important caveat when reading PPDA across the two tabs.
- **Aggregate-ratio season PPDA:** summed passes ÷ summed recoveries, with per-match PPDA only used for the std-dev band.
- **Field tilt as a complementary axis:** PPDA measures pressing; field tilt measures territory — plotting them together separates "press hard" from "dominate territory".

---

## 7 — Limitations & Known Issues

- **Two PPDA definitions in the app:** the same metric name carries different denominators in Team Overview vs. Match Analysis — documented here and in [defensive-pressing.md](../match-analysis/defensive-phase/defensive-pressing.md); the season Opponent-Analysis pressing view ([opp-season-defensive-pressing.md](../opponent-analysis/defensive-phase/opp-season-defensive-pressing.md)) follows the *Match Analysis* narrow definition, not this one.
- **Ball-recovery tagging dependence:** Opta logs `ball recovery` selectively, so the denominator reflects Opta's recovery definition.
- **`compute_mean_seconds_to_regain` is deprecated** in favour of field tilt.

---

## 8 — Relationship to Other Components

- **Upstream:** raw event CSVs, `team_mapping` short names, [precompute-pipeline.md](../infrastructure/precompute-pipeline.md) (`ppda_{season}.parquet`).
- **Downstream:** Team Overview pressing table/figures; points-progression chart. Contrast denominators with [defensive-pressing.md](../match-analysis/defensive-phase/defensive-pressing.md) and [opp-season-defensive-pressing.md](../opponent-analysis/defensive-phase/opp-season-defensive-pressing.md).
