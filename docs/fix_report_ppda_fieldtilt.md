# Fix report: Team Overview PPDA and Field Tilt % (coordinate frame + Field Tilt aggregation)

> Branch `fix/ppda-fieldtilt-frame` (from `main` @ `9b734ea`, tag `pre-fix-ppda-fieldtilt`). Not merged.
> Evidence for the bug: [frame_audit_ppda_fieldtilt.md](frame_audit_ppda_fieldtilt.md) (first commit on this branch).

## Summary

- **The flip is removed.** `x_from_own_goal` is now the raw Opta x, which is already team-relative. Zones, event filters and the PPDA ratio-of-sums are unchanged.
- **Field Tilt season value is now a ratio of sums:** Σ team final-third passes ÷ Σ (team + opponent) final-third passes. A match with no final-third passes adds 0 to both sums.
- **All 6 seasons are regenerated** through `python -m src.analytics.precompute_serie_a`. Parquet schema, column names and dtypes are unchanged. `team`, `matches` and `Season` are identical; every other column changes.
- **PPDA matches the audit's corrected values exactly** (max |diff| 0.00 in 2021/22, 2025/26 and 2026/27).
- **Field Tilt % now equals the wheel's G3 Field Tilt** in every season: r = 1.00, mean and max gap 0.00 pp. Before the fix, r was 0.67–0.90 and the gap 4.0–6.7 pp.
- **Tests:** 3 new tests fail on the old code and pass on the new. Full suite: 159 passed.

## Phase 0 — audit

### 0.1 Flip and aggregation (pre-fix `dash_app/src/analytics/ppda.py`)

| Item | Lines (pre-fix) |
|---|---|
| `_own_goal_x()` home/away × period flip, `own_goal_x` / `x_from_own_goal` columns | 144-159 |
| Consumers of `x_from_own_goal`: `compute_ppda()` (opponent passes ≤ 60, recoveries ≥ 40) | 183-199 |
| `compute_field_tilt()` (passes > 66.67) | 361-365 |
| `_compute_mean_seconds_to_regain_deprecated()` (dead code) | 275 |
| PPDA season value: Σ passes ÷ Σ recoveries, already a ratio of sums | 207-210 |
| Field Tilt season value: per-match share × 100, then **mean** over matches | 385-411 |

The old mean also dropped any match where the team had zero final-third passes, which biased the value upwards.

### 0.2 Raw counters for a ratio of sums

`ppda_{season}.parquet` has no per-match columns and none were added. `compute_field_tilt()` already builds the exact per-match counters from raw events: team final-third passes per (team, match) and both teams' total per match. The ratio of sums uses those counts directly, so no proxy was needed. The season `final_third_passes` column stays Σ team final-third passes.

### 0.3 Consumers

| Consumer | Uses | Threshold type |
|---|---|---|
| Team Overview KPI **PPDA** (`team_detail_callbacks.py:445`) | green if below league median | Relative |
| KPI **Field Tilt %** (`:450`) | green if above league median | Relative |
| KPI **PPDA Rank** (`:438-440`) | top / middle / bottom third of N | Relative |
| KPI **Pressing Tier** (`:455-471`) | rank percentile 80/60/40/20 | Relative |
| **PPDA Ranking** bar (`ppda.build_ppda_bar_figure`) | autoscaled axis | n/a |
| **PPDA vs Field Tilt** scatter (`ppda.build_ppda_scatter_figure`) | quadrant lines at league medians, axes from data min/max | Relative |
| `season_offensive_summary.compute_league_offensive_benchmarks()` fallback | only the `matches` column | Unaffected (`matches` unchanged) |
| `data_loader.load_ppda_summary()` | reads the parquet; raw fallback via `build_ppda_table()` | n/a |
| Style Evolution chart | wheel `G3_pct`, not the ppda parquet | Unaffected |
| Playing Style Wheel D2 / G3 | `pressing_summary` / offensive summaries | Unaffected |
| `theme.py` `ppda_good/medium/poor` (≤ 6 / 6–10 / > 10) | Match Analysis pressing cards only (narrow PPDA) | Absolute, but not this metric |
| `tests/test_ppda.py` | synthetic `x_from_own_goal` | — |

No Team Overview consumer uses an absolute PPDA or Field Tilt threshold.

### 0.4 Baseline

The pre-fix parquets for all 6 seasons were copied to the session scratchpad and match the parquets at tag `pre-fix-ppda-fieldtilt`. They are the "before" column below.

## Phase 1 — implementation

- `load_season_events()`: `own_goal_x = 0` (kept so the event table keeps its columns) and `x_from_own_goal = x`. The comment explains why there is no flip.
- `compute_field_tilt()`: per-match counters now cover every (team, match) pair present in the events, including zero-pass matches. The season value is Σ team ÷ Σ match total × 100, rounded to 2 dp. Teams with a zero season denominator get no value. The 66.67 cut-off, `is_pass` filter and output columns are unchanged.
- `compute_ppda()` is unchanged; it was already a ratio of sums.
- Regeneration: an all-season run of `precompute_serie_a` was started. After 2021/22 it was stopped and seasons 2022/23–2026/27 were run in parallel with `python -m src.analytics.precompute_serie_a <season>`. **Only the six `ppda_*.parquet` files are committed.** The run also rewrote unrelated tracked parquets (e.g. `xg_`, `shots_`, `offensive_summary_`, `chances_conceded_summary_2021_2022`). Those were restored to `HEAD` because they are outside the scope of this fix.

## Phase 2 — before / after

### Season summary

| Season | Metric | Teams changing rank | Max Δ rank | Spearman (before, after) | League mean before → after | SD before → after |
|---|---|---|---|---|---|---|
| 2021/2022 | PPDA | 13/20 | 5 | 0.91 | 9.29 → 15.77 | 1.35 → 2.76 |
| 2021/2022 | Field Tilt % | 18/20 | 6 | 0.92 | 50.0 → 50.11 | 5.0 → 9.47 |
| 2022/2023 | PPDA | 14/20 | 9 | 0.88 | 9.52 → 16.22 | 1.18 → 2.42 |
| 2022/2023 | Field Tilt % | 19/20 | 6 | 0.82 | 50.01 → 49.86 | 4.64 → 8.17 |
| 2023/2024 | PPDA | 17/20 | 3 | 0.96 | 11.12 → 18.72 | 1.51 → 3.1 |
| 2023/2024 | Field Tilt % | 18/20 | 6 | 0.82 | 50.0 → 49.89 | 5.8 → 8.74 |
| 2024/2025 | PPDA | 17/20 | 3 | 0.96 | 12.75 → 21.24 | 1.98 → 3.78 |
| 2024/2025 | Field Tilt % | 20/20 | 6 | 0.88 | 50.0 → 49.84 | 5.41 → 9.52 |
| 2025/2026 | PPDA | 14/20 | 5 | 0.94 | 12.86 → 21.5 | 2.32 → 4.52 |
| 2025/2026 | Field Tilt % | 17/20 | 8 | 0.86 | 50.0 → 49.67 | 5.94 → 10.78 |
| 2026/2027 | PPDA | 13/20 | 7 | 0.87 | 13.24 → 21.57 | 3.0 → 4.77 |
| 2026/2027 | Field Tilt % | 19/20 | 10 | 0.70 | 50.0 → 49.54 | 7.8 → 11.71 |

PPDA rises by 63–70 % in every season (league mean 9–13 → 16–22). Field Tilt spread grows by roughly 60–100 % (SD ~5–8 → ~8–12). Its league mean stays ≈ 50 %; it is no longer exactly 50 because a ratio of sums weights matches by volume.

### Check against the audit's corrected numbers

- **PPDA:** identical to the audit in 2021/22, 2025/26 and 2026/27 (max |diff| 0.00).
- **Field Tilt:** mean |diff| ≈ 0.7–1.05 pp, max 1.9–3.6 pp. The whole difference is the aggregation change. Recomputing with the new frame **and the old mean-of-matches** reproduces the audit within 0.05 pp, which is its 1-dp rounding.

### Cross-check with the Playing Style Wheel G3 Field Tilt

| Season | r before | mean gap before (pp) | r after | mean gap after (pp) | max gap after (pp) |
|---|---|---|---|---|---|
| 2021/2022 | 0.90 | 4.79 | 1.00 | 0.00 | 0.00 |
| 2022/2023 | 0.74 | 4.36 | 1.00 | 0.00 | 0.00 |
| 2023/2024 | 0.83 | 3.97 | 1.00 | 0.00 | 0.00 |
| 2024/2025 | 0.88 | 4.23 | 1.00 | 0.00 | 0.00 |
| 2025/2026 | 0.89 | 5.10 | 1.00 | 0.00 | 0.00 |
| 2026/2027 | 0.67 | 6.71 | 1.00 | 0.00 | 0.00 |

The two numbers are now identical. The audit expected a ~1 pp gap from aggregation and from `>` vs `≥ 66.67`. Once both use the same frame and a ratio of sums, the `>`/`≥` boundary makes no measurable difference.

### Per-season tables

Ranks: PPDA ascending (1 = lowest = most intense); Field Tilt descending (1 = highest). **Bold** = rank change (positive = moved up). "Audit corrected" columns appear only for the three seasons the audit covered.

### 2021/2022


**PPDA (Team Overview)**

| Team | PPDA before | PPDA after | Δ | Rank before | Rank after | Rank change | Audit corrected | after − audit |
|---|---|---|---|---|---|---|---|---|
| Hellas Verona | 7.14 | 11.67 | +4.53 | 1 | 1 | 0 | 11.67 | +0.00 |
| Milan | 7.72 | 11.83 | +4.11 | 4 | 2 | **+2** | 11.83 | +0.00 |
| Torino | 7.37 | 12.41 | +5.04 | 2 | 3 | **-1** | 12.41 | +0.00 |
| Atalanta | 7.65 | 12.44 | +4.79 | 3 | 4 | **-1** | 12.44 | +0.00 |
| Inter | 8.22 | 13.93 | +5.71 | 5 | 5 | 0 | 13.93 | +0.00 |
| Napoli | 8.62 | 14.20 | +5.58 | 7 | 6 | **+1** | 14.20 | +0.00 |
| Empoli | 9.43 | 14.70 | +5.27 | 12 | 7 | **+5** | 14.70 | +0.00 |
| Fiorentina | 8.45 | 14.73 | +6.28 | 6 | 8 | **-2** | 14.73 | +0.00 |
| Genoa | 9.46 | 15.03 | +5.57 | 14 | 9 | **+5** | 15.03 | +0.00 |
| Bologna | 9.37 | 15.24 | +5.87 | 11 | 10 | **+1** | 15.24 | +0.00 |
| Juventus | 9.31 | 15.49 | +6.18 | 10 | 11 | **-1** | 15.49 | +0.00 |
| Sassuolo | 9.14 | 16.02 | +6.88 | 8 | 12 | **-4** | 16.02 | +0.00 |
| Sampdoria | 9.58 | 16.26 | +6.68 | 15 | 13 | **+2** | 16.26 | +0.00 |
| Roma | 9.26 | 16.62 | +7.36 | 9 | 14 | **-5** | 16.62 | +0.00 |
| Lazio | 9.43 | 16.68 | +7.25 | 12 | 15 | **-3** | 16.68 | +0.00 |
| Cagliari | 10.14 | 18.01 | +7.87 | 16 | 16 | 0 | 18.01 | +0.00 |
| Udinese | 10.63 | 19.06 | +8.43 | 17 | 17 | 0 | 19.06 | +0.00 |
| Venezia | 11.36 | 19.88 | +8.52 | 18 | 18 | 0 | 19.88 | +0.00 |
| Spezia | 11.48 | 20.52 | +9.04 | 19 | 19 | 0 | 20.52 | +0.00 |
| Salernitana | 11.98 | 20.62 | +8.64 | 20 | 20 | 0 | 20.62 | +0.00 |

**Field Tilt %**

| Team | FT before | FT after | Δ | Rank before | Rank after | Rank change | Audit corrected | after − audit |
|---|---|---|---|---|---|---|---|---|
| Atalanta | 54.0 | 65.2 | +11.17 | 5 | 1 | **+4** | 64.0 | +1.16 |
| Fiorentina | 58.2 | 64.0 | +5.78 | 1 | 2 | **-1** | 63.3 | +0.65 |
| Inter | 57.6 | 62.2 | +4.60 | 2 | 3 | **-1** | 60.3 | +1.93 |
| Napoli | 56.8 | 61.0 | +4.18 | 3 | 4 | **-1** | 59.1 | +1.85 |
| Torino | 51.8 | 59.0 | +7.20 | 8 | 5 | **+3** | 58.4 | +0.60 |
| Milan | 52.1 | 57.4 | +5.34 | 7 | 6 | **+1** | 57.6 | -0.17 |
| Lazio | 53.4 | 57.3 | +3.86 | 6 | 7 | **-1** | 56.4 | +0.88 |
| Roma | 51.6 | 53.5 | +1.87 | 9 | 8 | **+1** | 53.0 | +0.45 |
| Hellas Verona | 50.5 | 53.3 | +2.85 | 11 | 9 | **+2** | 52.8 | +0.53 |
| Sassuolo | 54.7 | 50.4 | -4.31 | 4 | 10 | **-6** | 50.1 | +0.31 |
| Udinese | 45.7 | 47.9 | +2.14 | 14 | 11 | **+3** | 48.1 | -0.24 |
| Juventus | 49.7 | 45.9 | -3.85 | 12 | 12 | 0 | 46.5 | -0.61 |
| Bologna | 51.5 | 44.6 | -6.91 | 10 | 13 | **-3** | 45.0 | -0.40 |
| Empoli | 47.8 | 43.7 | -4.13 | 13 | 14 | **-1** | 44.8 | -1.11 |
| Cagliari | 44.4 | 42.4 | -2.07 | 18 | 15 | **+3** | 43.2 | -0.85 |
| Sampdoria | 45.5 | 41.8 | -3.70 | 15 | 16 | **-1** | 42.4 | -0.65 |
| Genoa | 44.6 | 41.1 | -3.45 | 17 | 17 | 0 | 41.9 | -0.78 |
| Spezia | 44.8 | 38.9 | -5.88 | 16 | 18 | **-2** | 38.8 | +0.12 |
| Salernitana | 41.7 | 38.6 | -3.09 | 20 | 19 | **+1** | 39.2 | -0.55 |
| Venezia | 43.6 | 34.2 | -9.43 | 19 | 20 | **-1** | 35.1 | -0.94 |

### 2022/2023


**PPDA (Team Overview)**

| Team | PPDA before | PPDA after | Δ | Rank before | Rank after | Rank change |
|---|---|---|---|---|---|---|
| Napoli | 7.56 | 11.63 | +4.07 | 2 | 1 | **+1** |
| Fiorentina | 7.00 | 12.05 | +5.05 | 1 | 2 | **-1** |
| Milan | 7.59 | 12.50 | +4.91 | 3 | 3 | 0 |
| Torino | 8.57 | 14.11 | +5.54 | 5 | 4 | **+1** |
| Inter | 9.47 | 14.37 | +4.90 | 8 | 5 | **+3** |
| Atalanta | 8.92 | 14.47 | +5.55 | 6 | 6 | 0 |
| Bologna | 8.36 | 14.73 | +6.37 | 4 | 7 | **-3** |
| Hellas Verona | 9.18 | 16.23 | +7.05 | 7 | 8 | **-1** |
| Juventus | 10.70 | 16.52 | +5.82 | 18 | 9 | **+9** |
| Spezia | 9.57 | 16.53 | +6.96 | 10 | 10 | 0 |
| Monza | 9.51 | 16.84 | +7.33 | 9 | 11 | **-2** |
| Lecce | 10.32 | 17.03 | +6.71 | 12 | 12 | 0 |
| Empoli | 10.51 | 17.18 | +6.67 | 17 | 13 | **+4** |
| Roma | 10.34 | 17.61 | +7.27 | 13 | 14 | **-1** |
| Udinese | 9.76 | 17.88 | +8.12 | 11 | 15 | **-4** |
| Sampdoria | 10.43 | 18.04 | +7.61 | 15 | 16 | **-1** |
| Lazio | 10.39 | 18.07 | +7.68 | 14 | 17 | **-3** |
| Sassuolo | 10.50 | 19.24 | +8.74 | 16 | 18 | **-2** |
| Cremonese | 10.76 | 19.46 | +8.70 | 19 | 19 | 0 |
| Salernitana | 10.98 | 19.83 | +8.85 | 20 | 20 | 0 |

**Field Tilt %**

| Team | FT before | FT after | Δ | Rank before | Rank after | Rank change |
|---|---|---|---|---|---|---|
| Napoli | 57.3 | 68.0 | +10.63 | 1 | 1 | 0 |
| Fiorentina | 53.2 | 67.2 | +14.02 | 6 | 2 | **+4** |
| Atalanta | 52.0 | 57.0 | +4.98 | 8 | 3 | **+5** |
| Inter | 56.9 | 55.8 | -1.06 | 2 | 4 | **-2** |
| Milan | 55.9 | 55.6 | -0.27 | 3 | 5 | **-2** |
| Torino | 52.3 | 55.4 | +3.09 | 7 | 6 | **+1** |
| Lazio | 48.6 | 53.3 | +4.65 | 12 | 7 | **+5** |
| Sassuolo | 48.6 | 51.1 | +2.54 | 13 | 8 | **+5** |
| Bologna | 54.5 | 48.9 | -5.63 | 5 | 9 | **-4** |
| Monza | 54.8 | 48.7 | -6.07 | 4 | 10 | **-6** |
| Udinese | 50.9 | 47.7 | -3.14 | 9 | 11 | **-2** |
| Spezia | 49.1 | 46.9 | -2.28 | 11 | 12 | **-1** |
| Roma | 47.5 | 46.3 | -1.13 | 15 | 13 | **+2** |
| Juventus | 50.0 | 45.5 | -4.55 | 10 | 14 | **-4** |
| Lecce | 43.2 | 45.1 | +1.88 | 19 | 15 | **+4** |
| Sampdoria | 45.8 | 41.8 | -3.98 | 17 | 16 | **+1** |
| Salernitana | 46.9 | 41.8 | -5.10 | 16 | 17 | **-1** |
| Hellas Verona | 41.1 | 41.5 | +0.35 | 20 | 18 | **+2** |
| Cremonese | 43.4 | 40.8 | -2.64 | 18 | 19 | **-1** |
| Empoli | 48.1 | 38.8 | -9.25 | 14 | 20 | **-6** |

### 2023/2024


**PPDA (Team Overview)**

| Team | PPDA before | PPDA after | Δ | Rank before | Rank after | Rank change |
|---|---|---|---|---|---|---|
| Napoli | 8.48 | 13.11 | +4.63 | 2 | 1 | **+1** |
| Fiorentina | 8.33 | 14.06 | +5.73 | 1 | 2 | **-1** |
| Atalanta | 9.82 | 16.06 | +6.24 | 3 | 3 | 0 |
| Frosinone | 10.11 | 16.07 | +5.96 | 6 | 4 | **+2** |
| Milan | 9.93 | 16.19 | +6.26 | 4 | 5 | **-1** |
| Torino | 10.41 | 16.45 | +6.04 | 8 | 6 | **+2** |
| Bologna | 10.01 | 16.60 | +6.59 | 5 | 7 | **-2** |
| Inter | 10.67 | 17.18 | +6.51 | 10 | 8 | **+2** |
| Hellas Verona | 10.33 | 17.46 | +7.13 | 7 | 9 | **-2** |
| Roma | 11.02 | 18.03 | +7.01 | 11 | 10 | **+1** |
| Lecce | 11.36 | 18.43 | +7.07 | 12 | 11 | **+1** |
| Lazio | 10.47 | 18.63 | +8.16 | 9 | 12 | **-3** |
| Juventus | 11.82 | 20.64 | +8.82 | 13 | 13 | 0 |
| Genoa | 12.80 | 20.90 | +8.10 | 16 | 14 | **+2** |
| Cagliari | 12.05 | 21.71 | +9.66 | 14 | 15 | **-1** |
| Sassuolo | 13.07 | 21.86 | +8.79 | 19 | 16 | **+3** |
| Empoli | 12.69 | 21.88 | +9.19 | 15 | 17 | **-2** |
| Monza | 12.81 | 22.53 | +9.72 | 17 | 18 | **-1** |
| Udinese | 12.95 | 23.03 | +10.08 | 18 | 19 | **-1** |
| Salernitana | 13.24 | 23.68 | +10.44 | 20 | 20 | 0 |

**Field Tilt %**

| Team | FT before | FT after | Δ | Rank before | Rank after | Rank change |
|---|---|---|---|---|---|---|
| Fiorentina | 57.4 | 68.0 | +10.67 | 3 | 1 | **+2** |
| Napoli | 57.1 | 65.6 | +8.45 | 4 | 2 | **+2** |
| Atalanta | 51.9 | 57.8 | +5.86 | 9 | 3 | **+6** |
| Inter | 58.0 | 57.7 | -0.23 | 2 | 4 | **-2** |
| Lazio | 49.7 | 56.4 | +6.69 | 10 | 5 | **+5** |
| Milan | 55.8 | 55.6 | -0.19 | 5 | 6 | **-1** |
| Bologna | 58.3 | 55.4 | -2.92 | 1 | 7 | **-6** |
| Torino | 52.2 | 53.4 | +1.23 | 8 | 8 | 0 |
| Roma | 53.6 | 51.2 | -2.34 | 7 | 9 | **-2** |
| Juventus | 49.6 | 48.5 | -1.05 | 11 | 10 | **+1** |
| Frosinone | 49.1 | 48.5 | -0.61 | 12 | 11 | **+1** |
| Monza | 55.2 | 47.6 | -7.63 | 6 | 12 | **-6** |
| Hellas Verona | 43.5 | 46.3 | +2.74 | 17 | 13 | **+4** |
| Sassuolo | 42.2 | 45.2 | +2.98 | 19 | 14 | **+5** |
| Cagliari | 43.0 | 42.0 | -0.93 | 18 | 15 | **+3** |
| Lecce | 46.5 | 41.0 | -5.43 | 14 | 16 | **-2** |
| Salernitana | 44.7 | 40.6 | -4.13 | 15 | 17 | **-2** |
| Genoa | 47.4 | 40.4 | -7.00 | 13 | 18 | **-5** |
| Empoli | 43.8 | 39.2 | -4.60 | 16 | 19 | **-3** |
| Udinese | 41.0 | 37.3 | -3.72 | 20 | 20 | 0 |

### 2024/2025


**PPDA (Team Overview)**

| Team | PPDA before | PPDA after | Δ | Rank before | Rank after | Rank change |
|---|---|---|---|---|---|---|
| Bologna | 8.98 | 15.36 | +6.38 | 1 | 1 | 0 |
| Inter | 10.53 | 16.12 | +5.59 | 4 | 2 | **+2** |
| Atalanta | 9.77 | 16.33 | +6.56 | 2 | 3 | **-1** |
| Como | 10.44 | 18.35 | +7.91 | 3 | 4 | **-1** |
| Juventus | 11.17 | 18.38 | +7.21 | 5 | 5 | 0 |
| Napoli | 12.09 | 18.56 | +6.47 | 8 | 6 | **+2** |
| Roma | 12.33 | 18.75 | +6.42 | 9 | 7 | **+2** |
| Lazio | 11.79 | 20.17 | +8.38 | 6 | 8 | **-2** |
| Milan | 11.90 | 20.26 | +8.36 | 7 | 9 | **-2** |
| Lecce | 13.64 | 20.83 | +7.19 | 13 | 10 | **+3** |
| Genoa | 13.59 | 20.89 | +7.30 | 12 | 11 | **+1** |
| Udinese | 13.02 | 21.02 | +8.00 | 11 | 12 | **-1** |
| Fiorentina | 12.53 | 21.53 | +9.00 | 10 | 13 | **-3** |
| Empoli | 13.81 | 21.83 | +8.02 | 15 | 14 | **+1** |
| Venezia | 13.77 | 23.08 | +9.31 | 14 | 15 | **-1** |
| Torino | 14.57 | 25.64 | +11.07 | 17 | 16 | **+1** |
| Cagliari | 14.01 | 26.49 | +12.48 | 16 | 17 | **-1** |
| Parma | 15.72 | 26.64 | +10.92 | 19 | 18 | **+1** |
| Monza | 14.64 | 26.65 | +12.01 | 18 | 19 | **-1** |
| Hellas Verona | 16.66 | 27.95 | +11.29 | 20 | 20 | 0 |

**Field Tilt %**

| Team | FT before | FT after | Δ | Rank before | Rank after | Rank change |
|---|---|---|---|---|---|---|
| Atalanta | 55.5 | 66.2 | +10.73 | 3 | 1 | **+2** |
| Bologna | 54.8 | 65.0 | +10.22 | 4 | 2 | **+2** |
| Inter | 61.0 | 62.9 | +1.92 | 1 | 3 | **-2** |
| Lazio | 54.8 | 58.0 | +3.22 | 5 | 4 | **+1** |
| Como | 53.7 | 57.8 | +4.18 | 7 | 5 | **+2** |
| Juventus | 57.0 | 57.7 | +0.78 | 2 | 6 | **-4** |
| Roma | 52.4 | 56.5 | +4.11 | 8 | 7 | **+1** |
| Milan | 51.0 | 55.0 | +4.06 | 9 | 8 | **+1** |
| Napoli | 53.9 | 53.8 | -0.13 | 6 | 9 | **-3** |
| Fiorentina | 50.4 | 49.2 | -1.20 | 11 | 10 | **+1** |
| Udinese | 45.6 | 47.1 | +1.51 | 17 | 11 | **+6** |
| Torino | 46.6 | 45.0 | -1.63 | 14 | 12 | **+2** |
| Cagliari | 47.1 | 42.3 | -4.77 | 12 | 13 | **-1** |
| Parma | 46.9 | 41.5 | -5.39 | 13 | 14 | **-1** |
| Venezia | 43.4 | 41.3 | -2.14 | 18 | 15 | **+3** |
| Monza | 50.8 | 41.0 | -9.79 | 10 | 16 | **-6** |
| Genoa | 46.5 | 40.1 | -6.38 | 15 | 17 | **-2** |
| Empoli | 42.6 | 39.5 | -3.10 | 19 | 18 | **+1** |
| Hellas Verona | 39.9 | 38.7 | -1.23 | 20 | 19 | **+1** |
| Lecce | 46.2 | 38.0 | -8.20 | 16 | 20 | **-4** |

### 2025/2026


**PPDA (Team Overview)**

| Team | PPDA before | PPDA after | Δ | Rank before | Rank after | Rank change | Audit corrected | after − audit |
|---|---|---|---|---|---|---|---|---|
| Roma | 9.93 | 15.08 | +5.15 | 2 | 1 | **+1** | 15.08 | +0.00 |
| Inter | 9.99 | 16.08 | +6.09 | 3 | 2 | **+1** | 16.08 | +0.00 |
| Como | 9.27 | 16.18 | +6.91 | 1 | 3 | **-2** | 16.18 | +0.00 |
| Atalanta | 10.26 | 16.50 | +6.24 | 5 | 4 | **+1** | 16.50 | +0.00 |
| Napoli | 10.36 | 16.51 | +6.15 | 6 | 5 | **+1** | 16.51 | +0.00 |
| Juventus | 10.07 | 16.58 | +6.51 | 4 | 6 | **-2** | 16.58 | +0.00 |
| Bologna | 10.58 | 17.61 | +7.03 | 7 | 7 | 0 | 17.61 | +0.00 |
| Genoa | 12.62 | 19.11 | +6.49 | 9 | 8 | **+1** | 19.11 | +0.00 |
| Lecce | 13.33 | 20.67 | +7.34 | 10 | 9 | **+1** | 20.67 | +0.00 |
| Fiorentina | 12.40 | 22.00 | +9.60 | 8 | 10 | **-2** | 22.00 | +0.00 |
| Milan | 13.64 | 22.16 | +8.52 | 11 | 11 | 0 | 22.16 | +0.00 |
| Udinese | 13.67 | 22.89 | +9.22 | 12 | 12 | 0 | 22.89 | +0.00 |
| Hellas Verona | 13.92 | 24.44 | +10.52 | 13 | 13 | 0 | 24.44 | +0.00 |
| Torino | 15.46 | 24.52 | +9.06 | 19 | 14 | **+5** | 24.52 | +0.00 |
| Parma | 15.24 | 24.69 | +9.45 | 15 | 15 | 0 | 24.69 | +0.00 |
| Pisa | 15.28 | 24.82 | +9.54 | 16 | 16 | 0 | 24.82 | +0.00 |
| Sassuolo | 15.45 | 26.41 | +10.96 | 18 | 17 | **+1** | 26.41 | +0.00 |
| Cremonese | 16.08 | 26.81 | +10.73 | 20 | 18 | **+2** | 26.81 | +0.00 |
| Lazio | 14.32 | 27.25 | +12.93 | 14 | 19 | **-5** | 27.25 | +0.00 |
| Cagliari | 15.39 | 29.63 | +14.24 | 17 | 20 | **-3** | 29.63 | +0.00 |

**Field Tilt %**

| Team | FT before | FT after | Δ | Rank before | Rank after | Rank change | Audit corrected | after − audit |
|---|---|---|---|---|---|---|---|---|
| Inter | 60.6 | 68.9 | +8.26 | 1 | 1 | 0 | 67.3 | +1.59 |
| Como | 57.5 | 65.1 | +7.55 | 3 | 2 | **+1** | 64.0 | +1.09 |
| Juventus | 54.9 | 64.4 | +9.52 | 6 | 3 | **+3** | 64.1 | +0.34 |
| Roma | 55.5 | 63.1 | +7.63 | 5 | 4 | **+1** | 61.8 | +1.29 |
| Napoli | 58.0 | 60.8 | +2.82 | 2 | 5 | **-3** | 59.8 | +1.04 |
| Atalanta | 56.6 | 58.8 | +2.23 | 4 | 6 | **-2** | 58.1 | +0.70 |
| Bologna | 52.9 | 57.5 | +4.66 | 7 | 7 | 0 | 56.7 | +0.83 |
| Milan | 50.7 | 51.0 | +0.28 | 9 | 8 | **+1** | 50.9 | +0.05 |
| Lazio | 51.0 | 50.8 | -0.23 | 8 | 9 | **-1** | 50.8 | -0.05 |
| Fiorentina | 49.5 | 47.0 | -2.47 | 10 | 10 | 0 | 47.0 | -0.02 |
| Udinese | 46.3 | 45.1 | -1.15 | 16 | 11 | **+5** | 45.4 | -0.26 |
| Lecce | 39.6 | 43.7 | +4.06 | 20 | 12 | **+8** | 44.8 | -1.10 |
| Genoa | 48.5 | 43.5 | -5.06 | 12 | 13 | **-1** | 45.2 | -1.73 |
| Torino | 48.4 | 42.5 | -5.84 | 13 | 14 | **-1** | 43.2 | -0.68 |
| Hellas Verona | 40.8 | 41.5 | +0.72 | 19 | 15 | **+4** | 43.4 | -1.93 |
| Sassuolo | 48.7 | 41.1 | -7.65 | 11 | 16 | **-5** | 42.6 | -1.52 |
| Cremonese | 47.5 | 39.8 | -7.65 | 14 | 17 | **-3** | 40.2 | -0.36 |
| Cagliari | 47.1 | 36.8 | -10.31 | 15 | 18 | **-3** | 38.5 | -1.66 |
| Pisa | 42.2 | 36.2 | -5.97 | 18 | 19 | **-1** | 37.4 | -1.18 |
| Parma | 43.7 | 35.7 | -8.01 | 17 | 20 | **-3** | 38.8 | -3.12 |

### 2026/2027


**PPDA (Team Overview)**

| Team | PPDA before | PPDA after | Δ | Rank before | Rank after | Rank change | Audit corrected | after − audit |
|---|---|---|---|---|---|---|---|---|
| Roma | 8.14 | 12.04 | +3.90 | 1 | 1 | 0 | 12.04 | +0.00 |
| Juventus | 11.52 | 15.80 | +4.28 | 7 | 2 | **+5** | 15.80 | +0.00 |
| Inter | 9.80 | 16.16 | +6.36 | 3 | 3 | 0 | 16.16 | +0.00 |
| Venezia | 10.03 | 16.27 | +6.24 | 4 | 4 | 0 | 16.27 | +0.00 |
| Milan | 9.46 | 16.38 | +6.92 | 2 | 5 | **-3** | 16.38 | +0.00 |
| Como | 10.41 | 17.17 | +6.76 | 5 | 6 | **-1** | 17.17 | +0.00 |
| Frosinone | 11.39 | 18.46 | +7.07 | 6 | 7 | **-1** | 18.46 | +0.00 |
| Torino | 15.13 | 19.86 | +4.73 | 15 | 8 | **+7** | 19.86 | +0.00 |
| Udinese | 12.16 | 21.70 | +9.54 | 9 | 9 | 0 | 21.70 | +0.00 |
| Genoa | 13.23 | 22.14 | +8.91 | 10 | 10 | 0 | 22.14 | +0.00 |
| Sassuolo | 14.20 | 23.72 | +9.52 | 13 | 11 | **+2** | 23.72 | +0.00 |
| Monza | 11.70 | 23.88 | +12.18 | 8 | 12 | **-4** | 23.88 | +0.00 |
| Fiorentina | 14.93 | 24.05 | +9.12 | 14 | 13 | **+1** | 24.05 | +0.00 |
| Lazio | 13.46 | 24.20 | +10.74 | 11 | 14 | **-3** | 24.20 | +0.00 |
| Napoli | 17.32 | 24.24 | +6.92 | 18 | 15 | **+3** | 24.24 | +0.00 |
| Parma | 15.31 | 24.65 | +9.34 | 16 | 16 | 0 | 24.65 | +0.00 |
| Atalanta | 15.38 | 26.95 | +11.57 | 17 | 17 | 0 | 26.95 | +0.00 |
| Lecce | 18.94 | 27.05 | +8.11 | 20 | 18 | **+2** | 27.05 | +0.00 |
| Bologna | 14.00 | 27.28 | +13.28 | 12 | 19 | **-7** | 27.28 | +0.00 |
| Cagliari | 18.25 | 29.34 | +11.09 | 19 | 20 | **-1** | 29.34 | +0.00 |

**Field Tilt %**

| Team | FT before | FT after | Δ | Rank before | Rank after | Rank change | Audit corrected | after − audit |
|---|---|---|---|---|---|---|---|---|
| Roma | 53.2 | 70.4 | +17.17 | 8 | 1 | **+7** | 70.4 | -0.04 |
| Como | 62.7 | 65.6 | +2.88 | 2 | 2 | 0 | 64.8 | +0.76 |
| Juventus | 57.4 | 65.3 | +7.92 | 5 | 3 | **+2** | 65.6 | -0.32 |
| Inter | 63.2 | 64.1 | +0.90 | 1 | 4 | **-3** | 65.5 | -1.41 |
| Venezia | 59.7 | 57.8 | -1.97 | 3 | 5 | **-2** | 56.3 | +1.45 |
| Monza | 45.0 | 52.7 | +7.67 | 13 | 6 | **+7** | 53.0 | -0.31 |
| Milan | 58.4 | 52.5 | -5.80 | 4 | 7 | **-3** | 54.7 | -2.15 |
| Napoli | 50.4 | 52.2 | +1.80 | 10 | 8 | **+2** | 52.7 | -0.47 |
| Lazio | 50.5 | 52.2 | +1.78 | 9 | 8 | **+1** | 50.9 | +1.33 |
| Sassuolo | 49.2 | 50.5 | +1.25 | 11 | 10 | **+1** | 50.6 | -0.12 |
| Atalanta | 42.9 | 49.6 | +6.69 | 16 | 11 | **+5** | 49.3 | +0.26 |
| Bologna | 54.0 | 48.2 | -5.85 | 7 | 12 | **-5** | 48.0 | +0.20 |
| Udinese | 40.5 | 47.8 | +7.35 | 18 | 13 | **+5** | 46.2 | +1.61 |
| Fiorentina | 42.9 | 45.6 | +2.67 | 15 | 14 | **+1** | 45.4 | +0.21 |
| Frosinone | 39.0 | 43.4 | +4.44 | 20 | 15 | **+5** | 43.9 | -0.50 |
| Torino | 55.8 | 42.4 | -13.41 | 6 | 16 | **-10** | 43.1 | -0.68 |
| Genoa | 44.8 | 40.2 | -4.60 | 14 | 17 | **-3** | 43.4 | -3.18 |
| Lecce | 40.1 | 33.7 | -6.40 | 19 | 18 | **+1** | 34.6 | -0.86 |
| Cagliari | 49.1 | 30.0 | -19.11 | 12 | 19 | **-7** | 33.6 | -3.64 |
| Parma | 41.2 | 26.6 | -14.63 | 17 | 20 | **-3** | 28.1 | -1.49 |

## Phase 3 — tests (`dash_app/tests/test_ppda.py`)

| Test | What it checks | Old code | New code |
|---|---|---|---|
| `test_load_season_events_keeps_team_relative_frame` | Synthetic raw CSV with one match, home and away teams, both halves. Shots at x 88–91 and GK events (Save, Claim) at x 5–7 for every team-half. After `load_season_events()`, every shot must have `x_from_own_goal` > 66.67 and every GK event < 33.33. Also checks 8 final-third passes per team in `compute_field_tilt()`. | **FAIL** (`('Away FC', 1)`: the mirrored team-half) | pass |
| `test_compute_field_tilt_ratio_of_sums` | Two matches: A 9 / B 1, then A 10 / B 90, plus a third match with zero final-third passes. Expects A = 19/110 (17.27 %), not the 50 % mean. | **FAIL** | pass |
| `test_compute_field_tilt_counts_matches_with_zero_team_passes` | A match where the team has 0 final-third passes still adds the opponent's passes to its denominator (A = 25 %). | **FAIL** | pass |

The full suite (`pytest tests`) gives **159 passed**: the 156 tests that existed before plus the 3 above. No existing test was edited or broke.

## Phase 4 — downstream review (report only, nothing edited)

### 4.1 UI and doc text that describes the old frame or quotes ranges

| Place | Text | Action needed |
|---|---|---|
| `docs/methodology/team-overview/ppda-team-overview.md:21` | "Opta normalised, with `x_from_own_goal` reflected so each team's pressing is measured in a common frame." | Rewrite: raw x is team-relative (every team attacks towards x = 100 in both halves) and is used as is. |
| same file, §3.2 (line 35) | Field Tilt formula with no aggregation stated | Add: season value = Σ team ÷ Σ (team + opponent) final-third passes; now identical to wheel G3. |
| same file, line 22 | "Seasons covered: all (2021/22–2025/26)" | Stale: 2026/27 is covered too (not frame-related). |
| `ppda.py` scatter quadrant labels (`build_ppda_scatter_figure`, `corners` dict) | "Elite Pressing — Low PPDA · Low Tilt", "Passive Pressing — High PPDA · High Tilt", "Low Pressing Activity — Low PPDA · High Tilt", "Defensive Focus — High PPDA · Low Tilt" | Not frame text, but with the corrected data the top pressers (e.g. Roma, Inter, Juventus 2026/27: low PPDA, high tilt) fall in the quadrant labelled "Low Pressing Activity". The labels need a product decision. |
| `ppda.py` module docstring (line 11) and `team_detail_callbacks.update_ppda_scatter` docstring | "PPDA vs regain seconds scatter" / "PPDA vs regain scatter" | Stale (the axis is Field Tilt); cosmetic. |
| `notebooks/05_ppda.ipynb` cell 3 | "Period 1 → Home attacks right … Period 2+ → directions swap" | Origin of the bug. **Left untouched** as instructed; it still describes the wrong frame. |
| `dash_app/scripts/generate_demo_artifacts.py:105` | demo PPDA drawn from 7–14 | Demo data only; the old range no longer matches real Team Overview values (≈ 12–30). |
| Team Overview section subtitle, KPI labels, bar title/axis, hover text | "PPDA ranking and field tilt vs the rest of the league", "PPDA (lower = more intense)" | No change needed (no frame or range wording). |
| `docs/glossary_review.md` (on `feature/glossary-page`) §1 finding 1 (line 21), §6.B item 1 (line 176) | reports the frame inversion as open | Mark as fixed on this branch. |

### 4.2 Glossary registry entries to update (`feature/glossary-page`, `dash_app/src/glossary/entries_team_overview.py`). Not edited.

1. **`_FRAME_ISSUE` constant (lines 43-50).** Delete it, together with its uses in `ppda_team_overview` (line 798) and `field_tilt_pct` (line 843). Current text:
   > "**Coordinate frame (code reference):** ppda.load_season_events() flips x to `x_from_own_goal` using home/away and period, assuming absolute coordinates. The raw Opta files are already team-relative (verified in the Phase 0 audit), so for the away team in the first half and the home team in the second half the frame is inverted. Reported in docs/glossary_review.md; not changed."

   Suggested replacement, if a frame note is still wanted: "x is used as stored: the raw Opta files are team-relative, so every team attacks towards x = 100 in both halves."
2. **`ppda_team_overview`** (line 777): remove `_FRAME_ISSUE`. The definition, formula and `SEASON_RATIO` stay as they are.
3. **`field_tilt_pct`** (line 827):
   - `short_definition` "The team's average share of the final-third passes played in its matches." → "The team's share of all final-third passes played in its matches over the season."
   - `formula` "mean over matches of team final-third passes ÷ both teams' final-third passes × 100" → "Σ team final-third passes ÷ Σ (team + opponent) final-third passes × 100"
   - methodology "The season value is the mean of these per-match tilts." plus `SEASON_MEAN_DEVIATION` → the ratio-of-sums sentence plus `SEASON_RATIO`
   - remove `_FRAME_ISSUE`
   - `notes` "Not the same number as the wheel's 'Field Tilt' (G3), which is a ratio of season sums in the team-relative frame." → "Same value as the wheel's 'Field Tilt' (G3) raw; the wheel shows it as a league percentile."
   - `season_aggregation="mean_of_match_values"` → `"ratio_of_sums"`
4. **`ps_field_tilt`** (line 682) `notes`: "Different from the 'Field Tilt %' KPI in Pressing Intensity, which is a mean of per-match tilts computed in a different coordinate frame." → "Raw value equals the 'Field Tilt %' KPI in Pressing Intensity; the wheel shows its league percentile."
5. **`ppda_rank`** and **`pressing_tier`**: no frame text. No change needed beyond the values themselves.
6. `glossary_registry` tests on that branch may pin `season_aggregation` for `field_tilt_pct`. Check them when merging.

### 4.3 Thresholds and tiers

No recalibration is needed. Every Team Overview colour and tier is relative: league median (PPDA, Field Tilt), rank thirds (PPDA Rank) and rank percentile 80/60/40/20 (Pressing Tier). The scatter quadrants also split at league medians. The only absolute PPDA bands in the app (`theme.py` ≤ 6 / 6–10 / > 10) belong to the Match Analysis narrow PPDA, which this fix does not affect. Values will look different in absolute terms: PPDA ≈ 12–30 instead of 7–19, and Field Tilt ≈ 27–70 % instead of 39–63 %. Any narrative that quotes the old levels needs updating.
