# Frame audit — Team Overview PPDA and Field Tilt %

> Read-only investigation. Branch `feature/glossary-page` (HEAD `a20a5d0`). No code, parquet, cache or test was modified.
> Scripts used (outside the repo): `frame_phase1.py`, `frame_phase2.py` (session scratchpad). Phase 2 calls `ppda.py`'s own functions in memory.

## Verdict: **BUG CONFIRMED**

The raw Opta event CSVs are **already team-relative**: every team attacks towards x = 100 in both halves, home or away. `ppda.load_season_events()` nevertheless flips x by home/away and period. It therefore mirrors **the away team's first-half events and the home team's second-half events**, which is ≈ 50 % of all rows, passes and ball recoveries in every season. Both PPDA zone filters and the Field Tilt final-third filter are applied to the mirrored half of the data.

- **Team Overview PPDA:** systematically too low (league mean 12.9 → 21.5 in 2025/26 once corrected); 13–14 of 20 teams change rank in each season tested, by up to 7 places.
- **Field Tilt %:** compressed towards 50 % (sd 5.9 → 9.7 in 2025/26); 15–19 of 20 teams change rank, by up to 11 places. The corrected values match the wheel's G3 Field Tilt, computed independently in the team-relative frame (r = 1.00, mean gap 1.0 pp; today r = 0.89, gap 5.1 pp).

The locked *definitions* (ball-recovery denominator, 60 % zone, final third > 66.67, mean of per-match tilt) are not in question; only the coordinate frame is.

## 1. The flip logic as found (Phase 0.1)

`dash_app/src/analytics/ppda.py`

| Item | Code | Lines |
|---|---|---|
| Home/away | `team_position` column of the raw CSV (`"home"` / `"away"`) | 61, 71, 117-122 |
| Period | `period_id` column (1 = first half; **any other value**, incl. 2, is treated as "second half") | 145-151 |
| Flip | `own_goal_x = 0` if (home, P1) or (away, P≠1), else `100`; `x_from_own_goal = x if own_goal_x == 0 else 100 − x` | 145-159 |
| Mirrored rows | **away team in period 1** and **home team in period 2** | 145-159 |
| PPDA zone | opponent passes with `x_from_own_goal ≤ 60` (`PPDA_ZONE_UPPER`) | 30, 182-186 |
| | pressing team's recoveries with `x_from_own_goal ≥ 40` (`PRESSING_ZONE_MIN`) | 31, 196-199 |
| Numerator | `event == "pass"` (any outcome) by the opponent, grouped by the pressing team | 112, 183-193 |
| Denominator | `event == "ball recovery"` by the pressing team | 113, 196-204 |
| Season PPDA | Σ passes ÷ Σ recoveries over the pooled season table (ratio of sums); per-match PPDA only for `ppda_std` | 207-245 |
| Field Tilt zone | passes with `x_from_own_goal > 66.67` (both teams) | 361-365 |
| Season Field Tilt | per-match team share × 100, then **mean** over matches | 387-410 |
| Origin | copied verbatim from `notebooks/05_ppda.ipynb`, cell 3: "Period 1 → Home attacks right … Period 2+ → directions swap" (an absolute-frame convention) | — |

The flip feeds `build_ppda_table()` (`ppda.py:424-457`), which `precompute_serie_a.precompute_season()` writes to `data/ready/ppda_{season}.parquet` (`precompute_serie_a.py:129-137`).

## 2. How other modules treat orientation (Phase 0.2)

No other module flips by home/away or period. All use raw x as team-relative, and mirror only *the opponent's* events with `100 − x`, which is consistent with team-relative data.

| Module | Handling | Reference |
|---|---|---|
| `playing_style.py` | states the CSVs are team-relative and uses raw x ("every team attacks left→right … in both periods, so zone thresholds apply directly without per-period flipping") | `playing_style.py:24-26, 46-52` |
| `defensive_pressing.py` | team actions in raw x ("Our x is already in attacking direction"); opponent passes mirrored `x_att = 100 − x` | `defensive_pressing.py:243-251, 285-293` |
| `defensive_structure.py` (transitions) | team fouls mirrored into the opponent frame `x_att = 100 − w_x`; opponent events raw | `defensive_structure.py:555` |
| `offensive_transitions.py` | "Opta 0-100 coordinate system, left-to-right"; opponent events mirrored `100 − w_x` | `offensive_transitions.py:46, 471-472` |
| `final_third.py` | raw x vs `FT_X_THRESHOLD = 66.67`, box `x ≥ 83.33` | `final_third.py:62, 316, 393, 915` |
| `chance_creation.py` | raw x (`x: 0→100 own goal → opponent goal`); opponent turnovers / own goals mirrored `100 − x` | `chance_creation.py:29, 668, 1263` |
| `chance_conceded.py` | opponent shots mirrored into the defending frame | `chance_conceded.py:93-94` |
| `goalkeeper_buildup.py`, `high_regains.py`, `corner_kicks.py`, `free_kicks.py`, `utils/pv_model.py` | raw x documented as "0 own goal → 100 opponent goal" | `goalkeeper_buildup.py:101`, `high_regains.py:22`, `corner_kicks.py:16`, `free_kicks.py:25`, `pv_model.py:36` |
| `possession_value.py` | uses `team_position` only as an `is_home` model feature, no flip | `possession_value.py:392, 435-436` |

## 3. Orientation evidence (Phase 1)

Matches (2026/27, 8 distinct teams, both roles, draw / home wins / away win):

| Match | Result | File |
|---|---|---|
| Roma – Inter (GW5) | 2-2 | `data/raw/serie_a_2026_2027/events/5_Roma_Inter_78i7x3bonxhac2f8kxwso6b6c.csv` |
| Juventus – Atalanta (GW5) | 2-0 | `…/5_Juventus_Atalanta_77a9rnv901wm3mwfoq92d1rf8.csv` |
| Venezia – Fiorentina (GW4) | 2-4 | `…/4_Venezia_Fiorentina_7627eeydx5wlv6wuxeu9y8s2c.csv` |
| Napoli – Bologna (GW4) | 1-0 | `…/4_Napoli_Bologna_754q3qu0cnnmdef8bdubia87o.csv` |

Columns:
- **Shots:** type_id 13–16, own goals excluded.
- **Passes into FT:** passes starting below x = 66.67 and ending at or beyond it, identified in the frame of each table.
- **Mean pass Δx:** mean of (Pass End X − x) over all passes; positive means the team plays towards x = 100.
- **GK events:** Save (10), Claim (11), Punch (41), Keeper pick-up (52), Keeper Sweeper (59) and goal kicks.

A team attacking towards x = 100 shows shots > 66, GK events < 20, and Δx > 0.


#### Roma – Inter

**Raw coordinates (no flip)**

| Team | Role | Half | Shots (n @ mean x) | Goals (n @ mean x) | Passes into FT (n @ mean start x) | Mean pass Δx (end − start) | GK events (n @ mean x) |
|---|---|---|---|---|---|---|---|
| AS Roma | home | 1 | 11 @ 84.5 | 2 @ 93.6 | 27 @ 55.7 | +4.1 | 6 @ 7.3 |
| AS Roma | home | 2 | 7 @ 86.9 | 0 | 23 @ 53.3 | +5.8 | 18 @ 7.1 |
| FC Internazionale Milano | away | 1 | 3 @ 93.7 | 0 | 28 @ 53.9 | +5.5 | 14 @ 7.9 |
| FC Internazionale Milano | away | 2 | 13 @ 85.7 | 2 @ 88.6 | 27 @ 57.8 | +5.2 | 14 @ 6.5 |

**After ppda.py flip (x_from_own_goal)**

| Team | Role | Half | Shots (n @ mean x) | Goals (n @ mean x) | Passes into FT (n @ mean start x) | Mean pass Δx (end − start) | GK events (n @ mean x) |
|---|---|---|---|---|---|---|---|
| AS Roma | home | 1 | 11 @ 84.5 | 2 @ 93.6 | 27 @ 55.7 | +4.1 | 6 @ 7.3 |
| AS Roma | home | 2 | 7 @ 13.1 | 0 | 6 @ 54.8 | -5.8 | 18 @ 92.9 |
| FC Internazionale Milano | away | 1 | 3 @ 6.3 | 0 | 14 @ 59.1 | -5.5 | 14 @ 92.1 |
| FC Internazionale Milano | away | 2 | 13 @ 85.7 | 2 @ 88.6 | 27 @ 57.8 | +5.2 | 14 @ 6.5 |

#### Juventus – Atalanta

**Raw coordinates (no flip)**

| Team | Role | Half | Shots (n @ mean x) | Goals (n @ mean x) | Passes into FT (n @ mean start x) | Mean pass Δx (end − start) | GK events (n @ mean x) |
|---|---|---|---|---|---|---|---|
| Atalanta Bergamasca Calcio | away | 1 | 6 @ 86.5 | 0 | 34 @ 59.6 | +3.7 | 5 @ 6.6 |
| Atalanta Bergamasca Calcio | away | 2 | 5 @ 80.7 | 0 | 17 @ 55.4 | +4.0 | 17 @ 7.4 |
| Juventus FC | home | 1 | 3 @ 83.7 | 1 @ 87.6 | 21 @ 55.7 | +3.1 | 12 @ 5.6 |
| Juventus FC | home | 2 | 11 @ 87.4 | 1 @ 94.5 | 15 @ 53.2 | +3.5 | 13 @ 5.2 |

**After ppda.py flip (x_from_own_goal)**

| Team | Role | Half | Shots (n @ mean x) | Goals (n @ mean x) | Passes into FT (n @ mean start x) | Mean pass Δx (end − start) | GK events (n @ mean x) |
|---|---|---|---|---|---|---|---|
| Atalanta Bergamasca Calcio | away | 1 | 6 @ 13.5 | 0 | 4 @ 63.0 | -3.7 | 5 @ 93.4 |
| Atalanta Bergamasca Calcio | away | 2 | 5 @ 80.7 | 0 | 17 @ 55.4 | +4.0 | 17 @ 7.4 |
| Juventus FC | home | 1 | 3 @ 83.7 | 1 @ 87.6 | 21 @ 55.7 | +3.1 | 12 @ 5.6 |
| Juventus FC | home | 2 | 11 @ 12.6 | 1 @ 5.5 | 19 @ 60.8 | -3.5 | 13 @ 94.8 |

#### Venezia – Fiorentina

**Raw coordinates (no flip)**

| Team | Role | Half | Shots (n @ mean x) | Goals (n @ mean x) | Passes into FT (n @ mean start x) | Mean pass Δx (end − start) | GK events (n @ mean x) |
|---|---|---|---|---|---|---|---|
| ACF Fiorentina | away | 1 | 11 @ 89.8 | 2 @ 80.5 | 30 @ 51.8 | +5.4 | 5 @ 5.7 |
| ACF Fiorentina | away | 2 | 8 @ 88.0 | 2 @ 90.4 | 15 @ 48.5 | +8.5 | 12 @ 4.5 |
| Venezia FC | home | 1 | 3 @ 90.6 | 1 @ 85.2 | 25 @ 50.1 | +4.1 | 19 @ 6.8 |
| Venezia FC | home | 2 | 7 @ 83.7 | 1 @ 89.8 | 36 @ 56.4 | +3.3 | 8 @ 4.8 |

**After ppda.py flip (x_from_own_goal)**

| Team | Role | Half | Shots (n @ mean x) | Goals (n @ mean x) | Passes into FT (n @ mean start x) | Mean pass Δx (end − start) | GK events (n @ mean x) |
|---|---|---|---|---|---|---|---|
| ACF Fiorentina | away | 1 | 11 @ 10.2 | 2 @ 19.5 | 4 @ 62.3 | -5.4 | 5 @ 94.3 |
| ACF Fiorentina | away | 2 | 8 @ 88.0 | 2 @ 90.4 | 15 @ 48.5 | +8.5 | 12 @ 4.5 |
| Venezia FC | home | 1 | 3 @ 90.6 | 1 @ 85.2 | 25 @ 50.1 | +4.1 | 19 @ 6.8 |
| Venezia FC | home | 2 | 7 @ 16.3 | 1 @ 10.2 | 14 @ 60.4 | -3.3 | 8 @ 95.2 |

#### Napoli – Bologna

**Raw coordinates (no flip)**

| Team | Role | Half | Shots (n @ mean x) | Goals (n @ mean x) | Passes into FT (n @ mean start x) | Mean pass Δx (end − start) | GK events (n @ mean x) |
|---|---|---|---|---|---|---|---|
| Bologna FC 1909 | away | 1 | 3 @ 73.9 | 0 | 15 @ 53.1 | +4.2 | 9 @ 4.8 |
| Bologna FC 1909 | away | 2 | 2 @ 89.0 | 0 | 27 @ 52.5 | +5.0 | 11 @ 7.7 |
| SSC Napoli | home | 1 | 3 @ 84.2 | 0 | 29 @ 54.4 | +3.2 | 5 @ 2.1 |
| SSC Napoli | home | 2 | 11 @ 87.0 | 1 @ 93.3 | 46 @ 51.4 | +3.5 | 5 @ 2.8 |

**After ppda.py flip (x_from_own_goal)**

| Team | Role | Half | Shots (n @ mean x) | Goals (n @ mean x) | Passes into FT (n @ mean start x) | Mean pass Δx (end − start) | GK events (n @ mean x) |
|---|---|---|---|---|---|---|---|
| Bologna FC 1909 | away | 1 | 3 @ 26.1 | 0 | 23 @ 60.5 | -4.2 | 9 @ 95.2 |
| Bologna FC 1909 | away | 2 | 2 @ 89.0 | 0 | 27 @ 52.5 | +5.0 | 11 @ 7.7 |
| SSC Napoli | home | 1 | 3 @ 84.2 | 0 | 29 @ 54.4 | +3.2 | 5 @ 2.1 |
| SSC Napoli | home | 2 | 11 @ 13.0 | 1 @ 6.7 | 9 @ 59.4 | -3.5 | 5 @ 97.2 |

**Conclusion (1.3):** in the raw files all 16 team-halves show shots at x ≈ 74–94, GK events at x ≈ 2–8 and a positive pass Δx. The raw frame is "**each team always attacks towards x = 100**"; it does **not** flip at half time and does **not** differ between home and away.

**After the flip (1.4):** exactly the **away team in the first half** and the **home team in the second half** become mirrored in every match: shots move to x ≈ 6–26, GK events to x ≈ 92–97, and pass Δx turns negative. The other two team-halves are untouched.

**Full-season census (raw):**

| Season | Team-halves with mean shot x > 50 | Team-halves with mean GK-event x < 50 |
|---|---|---|
| 2026/27 | 199 / 199 | 199 / 199 |
| 2025/26 | 1,493 / 1,496 | 1,504 / 1,504 |
| 2021/22 | 1,494 / 1,497 | 1,503 / 1,503 |

The 6 shot exceptions are all team-halves with only 1–2 long-range shots (e.g. Napoli–Cremonese 2025/26, away P1: one shot at x = 15.7). GK events never contradict the team-relative frame.

## 4. Impact (Phase 2)

Method:
- **Current:** `ppda.compute_ppda()` / `compute_field_tilt()` on `ppda.load_season_events(season)`, exactly as the code runs. The output was checked equal to the stored `ppda_{season}.parquet` (all three seasons: identical).
- **Corrected:** the same functions on a copy of the event table with `x_from_own_goal = x`, i.e. the flip removed, in memory only.
- **Ranks:** PPDA ascending (1 = lowest = most intense), Field Tilt descending (1 = highest). **Bold** = rank change.

**Why the values move**
- **PPDA:** for each mirrored team-half, the numerator takes the opponent's passes from the wrong end, and the denominator takes the team's *deep* recoveries (raw x ≤ 60) instead of its high ones. Deep recoveries are far more frequent, so PPDA is deflated for everyone, but unevenly: teams that recover a lot of ball deep look more "intense" than they are (e.g. Bologna 2026/27, rank 12 → 19).
- **Field Tilt:** half of each team's "final-third passes" are really its own-third passes (raw x < 33.33), so every team is pulled towards 50 % and the ranking blends territory with deep circulation (e.g. Torino 2026/27, 55.8 % → 43.1 %, rank 6 → 17).


### 2026/2027

Events mirrored by the flip (away P1 + home P2): 50.6% of rows; passes: 51.3%, recoveries: 50.1%

Baseline check: in-memory current code == ppda_2026_2027.parquet → PPDA True, Field Tilt True

**PPDA (Team Overview)** — lower = more intense; rank 1 = lowest PPDA

| Team | PPDA current | PPDA corrected | Δ | Rank before | Rank after | Rank change |
|---|---|---|---|---|---|---|
| Roma | 8.14 | 12.04 | +3.90 | 1 | 1 | 0 |
| Juventus | 11.52 | 15.80 | +4.28 | 7 | 2 | **+5** |
| Inter | 9.80 | 16.16 | +6.36 | 3 | 3 | 0 |
| Venezia | 10.03 | 16.27 | +6.24 | 4 | 4 | 0 |
| Milan | 9.46 | 16.38 | +6.92 | 2 | 5 | **-3** |
| Como | 10.41 | 17.17 | +6.76 | 5 | 6 | **-1** |
| Frosinone | 11.39 | 18.46 | +7.07 | 6 | 7 | **-1** |
| Torino | 15.13 | 19.86 | +4.73 | 15 | 8 | **+7** |
| Udinese | 12.16 | 21.70 | +9.54 | 9 | 9 | 0 |
| Genoa | 13.23 | 22.14 | +8.91 | 10 | 10 | 0 |
| Sassuolo | 14.20 | 23.72 | +9.52 | 13 | 11 | **+2** |
| Monza | 11.70 | 23.88 | +12.18 | 8 | 12 | **-4** |
| Fiorentina | 14.93 | 24.05 | +9.12 | 14 | 13 | **+1** |
| Lazio | 13.46 | 24.20 | +10.74 | 11 | 14 | **-3** |
| Napoli | 17.32 | 24.24 | +6.92 | 18 | 15 | **+3** |
| Parma | 15.31 | 24.65 | +9.34 | 16 | 16 | 0 |
| Atalanta | 15.38 | 26.95 | +11.57 | 17 | 17 | 0 |
| Lecce | 18.94 | 27.05 | +8.11 | 20 | 18 | **+2** |
| Bologna | 14.00 | 27.28 | +13.28 | 12 | 19 | **-7** |
| Cagliari | 18.25 | 29.34 | +11.09 | 19 | 20 | **-1** |

**Field Tilt %** — higher = more territory; rank 1 = highest

| Team | Field Tilt current | Field Tilt corrected | Δ (pp) | Rank before | Rank after | Rank change |
|---|---|---|---|---|---|---|
| Roma | 53.2 | 70.4 | +17.2 | 8 | 1 | **+7** |
| Juventus | 57.4 | 65.6 | +8.2 | 5 | 2 | **+3** |
| Inter | 63.2 | 65.5 | +2.3 | 1 | 3 | **-2** |
| Como | 62.7 | 64.8 | +2.1 | 2 | 4 | **-2** |
| Venezia | 59.7 | 56.3 | -3.4 | 3 | 5 | **-2** |
| Milan | 58.4 | 54.7 | -3.6 | 4 | 6 | **-2** |
| Monza | 45.0 | 53.0 | +8.0 | 13 | 7 | **+6** |
| Napoli | 50.4 | 52.7 | +2.3 | 10 | 8 | **+2** |
| Lazio | 50.5 | 50.9 | +0.5 | 9 | 9 | 0 |
| Sassuolo | 49.2 | 50.6 | +1.3 | 11 | 10 | **+1** |
| Atalanta | 42.9 | 49.3 | +6.5 | 16 | 11 | **+5** |
| Bologna | 54.0 | 48.0 | -6.0 | 7 | 12 | **-5** |
| Udinese | 40.5 | 46.2 | +5.8 | 18 | 13 | **+5** |
| Fiorentina | 42.9 | 45.4 | +2.5 | 15 | 14 | **+1** |
| Frosinone | 39.0 | 43.9 | +4.9 | 20 | 15 | **+5** |
| Genoa | 44.8 | 43.4 | -1.5 | 14 | 16 | **-2** |
| Torino | 55.8 | 43.1 | -12.7 | 6 | 17 | **-11** |
| Lecce | 40.1 | 34.6 | -5.5 | 19 | 18 | **+1** |
| Cagliari | 49.1 | 33.6 | -15.5 | 12 | 19 | **-7** |
| Parma | 41.2 | 28.1 | -13.2 | 17 | 20 | **-3** |

Summary: teams whose PPDA rank changes 13/20, mean |Δ rank| 2.0, max 7, Spearman(current, corrected) 0.87; Field Tilt rank changes 19/20, mean |Δ rank| 3.6, max 11, Spearman 0.70; league mean PPDA 13.24 → 21.57; field-tilt spread (sd) 7.8 → 11.1

### 2025/2026

Events mirrored by the flip (away P1 + home P2): 50.0% of rows; passes: 50.4%, recoveries: 50.3%

Baseline check: in-memory current code == ppda_2025_2026.parquet → PPDA True, Field Tilt True

**PPDA (Team Overview)** — lower = more intense; rank 1 = lowest PPDA

| Team | PPDA current | PPDA corrected | Δ | Rank before | Rank after | Rank change |
|---|---|---|---|---|---|---|
| Roma | 9.93 | 15.08 | +5.15 | 2 | 1 | **+1** |
| Inter | 9.99 | 16.08 | +6.09 | 3 | 2 | **+1** |
| Como | 9.27 | 16.18 | +6.91 | 1 | 3 | **-2** |
| Atalanta | 10.26 | 16.50 | +6.24 | 5 | 4 | **+1** |
| Napoli | 10.36 | 16.51 | +6.15 | 6 | 5 | **+1** |
| Juventus | 10.07 | 16.58 | +6.51 | 4 | 6 | **-2** |
| Bologna | 10.58 | 17.61 | +7.03 | 7 | 7 | 0 |
| Genoa | 12.62 | 19.11 | +6.49 | 9 | 8 | **+1** |
| Lecce | 13.33 | 20.67 | +7.34 | 10 | 9 | **+1** |
| Fiorentina | 12.40 | 22.00 | +9.60 | 8 | 10 | **-2** |
| Milan | 13.64 | 22.16 | +8.52 | 11 | 11 | 0 |
| Udinese | 13.67 | 22.89 | +9.22 | 12 | 12 | 0 |
| Hellas Verona | 13.92 | 24.44 | +10.52 | 13 | 13 | 0 |
| Torino | 15.46 | 24.52 | +9.06 | 19 | 14 | **+5** |
| Parma | 15.24 | 24.69 | +9.45 | 15 | 15 | 0 |
| Pisa | 15.28 | 24.82 | +9.54 | 16 | 16 | 0 |
| Sassuolo | 15.45 | 26.41 | +10.96 | 18 | 17 | **+1** |
| Cremonese | 16.08 | 26.81 | +10.73 | 20 | 18 | **+2** |
| Lazio | 14.32 | 27.25 | +12.93 | 14 | 19 | **-5** |
| Cagliari | 15.39 | 29.63 | +14.24 | 17 | 20 | **-3** |

**Field Tilt %** — higher = more territory; rank 1 = highest

| Team | Field Tilt current | Field Tilt corrected | Δ (pp) | Rank before | Rank after | Rank change |
|---|---|---|---|---|---|---|
| Inter | 60.6 | 67.3 | +6.7 | 1 | 1 | 0 |
| Juventus | 54.9 | 64.1 | +9.2 | 6 | 2 | **+4** |
| Como | 57.5 | 64.0 | +6.4 | 3 | 3 | 0 |
| Roma | 55.5 | 61.8 | +6.3 | 5 | 4 | **+1** |
| Napoli | 58.0 | 59.8 | +1.7 | 2 | 5 | **-3** |
| Atalanta | 56.6 | 58.1 | +1.6 | 4 | 6 | **-2** |
| Bologna | 52.9 | 56.7 | +3.9 | 7 | 7 | 0 |
| Milan | 50.7 | 50.9 | +0.2 | 9 | 8 | **+1** |
| Lazio | 51.0 | 50.8 | -0.1 | 8 | 9 | **-1** |
| Fiorentina | 49.5 | 47.0 | -2.4 | 10 | 10 | 0 |
| Udinese | 46.3 | 45.4 | -0.9 | 16 | 11 | **+5** |
| Genoa | 48.5 | 45.2 | -3.3 | 12 | 12 | 0 |
| Lecce | 39.6 | 44.8 | +5.2 | 20 | 13 | **+7** |
| Hellas Verona | 40.8 | 43.4 | +2.7 | 19 | 14 | **+5** |
| Torino | 48.4 | 43.2 | -5.1 | 13 | 15 | **-2** |
| Sassuolo | 48.7 | 42.6 | -6.1 | 11 | 16 | **-5** |
| Cremonese | 47.5 | 40.2 | -7.3 | 14 | 17 | **-3** |
| Parma | 43.7 | 38.8 | -4.9 | 17 | 18 | **-1** |
| Cagliari | 47.1 | 38.5 | -8.6 | 15 | 19 | **-4** |
| Pisa | 42.2 | 37.4 | -4.8 | 18 | 20 | **-2** |

Summary: teams whose PPDA rank changes 14/20, mean |Δ rank| 1.4, max 5, Spearman(current, corrected) 0.94; Field Tilt rank changes 15/20, mean |Δ rank| 2.3, max 7, Spearman 0.86; league mean PPDA 12.86 → 21.50; field-tilt spread (sd) 5.9 → 9.7

### 2021/2022

Events mirrored by the flip (away P1 + home P2): 49.6% of rows; passes: 49.7%, recoveries: 49.8%

Baseline check: in-memory current code == ppda_2021_2022.parquet → PPDA True, Field Tilt True

**PPDA (Team Overview)** — lower = more intense; rank 1 = lowest PPDA

| Team | PPDA current | PPDA corrected | Δ | Rank before | Rank after | Rank change |
|---|---|---|---|---|---|---|
| Hellas Verona | 7.14 | 11.67 | +4.53 | 1 | 1 | 0 |
| Milan | 7.72 | 11.83 | +4.11 | 4 | 2 | **+2** |
| Torino | 7.37 | 12.41 | +5.04 | 2 | 3 | **-1** |
| Atalanta | 7.65 | 12.44 | +4.79 | 3 | 4 | **-1** |
| Inter | 8.22 | 13.93 | +5.71 | 5 | 5 | 0 |
| Napoli | 8.62 | 14.20 | +5.58 | 7 | 6 | **+1** |
| Empoli | 9.43 | 14.70 | +5.27 | 12 | 7 | **+5** |
| Fiorentina | 8.45 | 14.73 | +6.28 | 6 | 8 | **-2** |
| Genoa | 9.46 | 15.03 | +5.57 | 14 | 9 | **+5** |
| Bologna | 9.37 | 15.24 | +5.87 | 11 | 10 | **+1** |
| Juventus | 9.31 | 15.49 | +6.18 | 10 | 11 | **-1** |
| Sassuolo | 9.14 | 16.02 | +6.88 | 8 | 12 | **-4** |
| Sampdoria | 9.58 | 16.26 | +6.68 | 15 | 13 | **+2** |
| Roma | 9.26 | 16.62 | +7.36 | 9 | 14 | **-5** |
| Lazio | 9.43 | 16.68 | +7.25 | 12 | 15 | **-3** |
| Cagliari | 10.14 | 18.01 | +7.87 | 16 | 16 | 0 |
| Udinese | 10.63 | 19.06 | +8.43 | 17 | 17 | 0 |
| Venezia | 11.36 | 19.88 | +8.52 | 18 | 18 | 0 |
| Spezia | 11.48 | 20.52 | +9.04 | 19 | 19 | 0 |
| Salernitana | 11.98 | 20.62 | +8.64 | 20 | 20 | 0 |

**Field Tilt %** — higher = more territory; rank 1 = highest

| Team | Field Tilt current | Field Tilt corrected | Δ (pp) | Rank before | Rank after | Rank change |
|---|---|---|---|---|---|---|
| Atalanta | 54.0 | 64.0 | +10.0 | 5 | 1 | **+4** |
| Fiorentina | 58.2 | 63.3 | +5.2 | 1 | 2 | **-1** |
| Inter | 57.6 | 60.3 | +2.7 | 2 | 3 | **-1** |
| Napoli | 56.8 | 59.1 | +2.4 | 3 | 4 | **-1** |
| Torino | 51.8 | 58.4 | +6.6 | 8 | 5 | **+3** |
| Milan | 52.1 | 57.6 | +5.6 | 7 | 6 | **+1** |
| Lazio | 53.4 | 56.4 | +3.0 | 6 | 7 | **-1** |
| Roma | 51.6 | 53.0 | +1.4 | 9 | 8 | **+1** |
| Hellas Verona | 50.5 | 52.8 | +2.3 | 11 | 9 | **+2** |
| Sassuolo | 54.7 | 50.1 | -4.6 | 4 | 10 | **-6** |
| Udinese | 45.7 | 48.1 | +2.3 | 14 | 11 | **+3** |
| Juventus | 49.7 | 46.5 | -3.3 | 12 | 12 | 0 |
| Bologna | 51.5 | 45.0 | -6.5 | 10 | 13 | **-3** |
| Empoli | 47.8 | 44.8 | -3.0 | 13 | 14 | **-1** |
| Cagliari | 44.4 | 43.2 | -1.2 | 18 | 15 | **+3** |
| Sampdoria | 45.5 | 42.4 | -3.1 | 15 | 16 | **-1** |
| Genoa | 44.6 | 41.9 | -2.7 | 17 | 17 | 0 |
| Salernitana | 41.7 | 39.2 | -2.6 | 20 | 18 | **+2** |
| Spezia | 44.8 | 38.8 | -6.0 | 16 | 19 | **-3** |
| Venezia | 43.6 | 35.1 | -8.5 | 19 | 20 | **-1** |

Summary: teams whose PPDA rank changes 13/20, mean |Δ rank| 1.6, max 5, Spearman(current, corrected) 0.91; Field Tilt rank changes 18/20, mean |Δ rank| 1.9, max 6, Spearman 0.91; league mean PPDA 9.29 → 15.77; field-tilt spread (sd) 5.0 → 8.7

**Corroboration (2025/26):** the wheel's G3 "Field Tilt" (`playing_style.py`, team-relative frame, ratio of season sums) against Field Tilt %:

| | Pearson r with G3 | Mean absolute gap |
|---|---|---|
| Field Tilt % as computed today | 0.89 | 5.1 pp |
| Field Tilt % with the flip removed | **1.00** | **1.0 pp** |

The remaining 1.0 pp is explained by the locked aggregation difference (mean of per-match tilts vs ratio of sums) and by `>` vs `≥ 66.67`.

## 5. Everything that relies on the same logic

| Place | What it shows / does | Reference |
|---|---|---|
| `precompute_serie_a.precompute_season()` | writes `ppda_{season}.parquet` (PPDA, passes_allowed, ball_recoveries, ppda_std, matches, final_third_passes, field_tilt, rank) | `precompute_serie_a.py:129-137` |
| `data_loader.load_ppda_summary()` | reads the parquet; falls back to `build_ppda_table()` from raw | `data_loader.py:242-259` |
| Team Overview → Pressing Intensity: **PPDA**, **PPDA Rank**, **Field Tilt %**, **Pressing Tier** KPI cards | colours vs league median; tier from rank | `team_detail_callbacks.py:400-478` |
| Team Overview → **PPDA Ranking — Pressing Intensity** bar chart | `build_ppda_bar_figure()` | `team_detail_callbacks.py:380-384`, `ppda.py:460` |
| Team Overview → **PPDA vs Field Tilt** scatter (quadrants at league medians) | `build_ppda_scatter_figure()` | `team_detail_callbacks.py:393-397`, `ppda.py:534` |
| `season_offensive_summary.compute_league_offensive_benchmarks()` fallback | uses only the `matches` column of the PPDA table (frame-insensitive in practice) | `season_offensive_summary.py:426-436` |
| `_compute_mean_seconds_to_regain_deprecated()` | same frame; dead code | `ppda.py:264-341` |
| Glossary registry: `ppda_team_overview`, `ppda_rank`, `field_tilt_pct`, `pressing_tier` | methodology already carries the "coordinate frame (code reference)" caveat | `src/glossary/entries_team_overview.py` |
| `docs/glossary_review.md` §1 finding 1, §6.B item 1 | reported the suspicion | — |
| `tests/test_ppda.py` | unit tests feed `x_from_own_goal` directly; **no test covers the orientation step** | `tests/test_ppda.py` |

Not affected: the Opponent/Match Analysis PPDA (`defensive_pressing.py`), the wheel's D2 and G3, and every other module listed in §2.

## 6. Proposed minimal fix (description only — nothing applied)

1. **`ppda.load_season_events()`:** stop flipping. Set `x_from_own_goal = x`, because the raw x is already the distance from the team's own goal. The `own_goal_x` helper can be removed, or kept constant at 0 for column compatibility. Nothing else in `compute_ppda()` / `compute_field_tilt()` changes: zones, event filters and aggregation stay as locked.
2. **Regenerate** `data/ready/ppda_{season}.parquet` for every season by re-running the PPDA step of `precompute_season()`, then invalidate the data-loader cache.
3. **Add a regression test** on orientation, e.g. a two-period synthetic match where each team's passes sit at high x in both halves, asserting `x_from_own_goal == x`. Optionally add a data sanity test that each team-half's mean GK-event x is below 50.
4. **Follow-ups once fixed:**
   - Remove the frame caveat from the four glossary entries and from `docs/glossary_review.md`; until then those entries are good candidates for `status: "pending_fix"`, which the glossary page already supports.
   - Review any narrative that quotes absolute Team Overview PPDA levels: they rise by ≈ 60–70 % (league means 9–13 → 16–22).
   - Colour thresholds based on the league median and the rank-based Pressing Tier are relative, so they need no change.
5. **Out of scope:** the mean-of-matches aggregation of Field Tilt % (a separate, already-reported ratio-of-sums deviation).

## 7. Verification checklist

- [x] `git status` shows only this report (untracked) — no other file created or modified.
- [x] No parquet or cache file modified: `data/ready/ppda_*.parquet` timestamps unchanged (Jun 23 / Sep 30); scripts only read CSVs and parquets.
- [x] Evidence tables for 4 matches included (§3), plus full-season census.
- [x] Impact tables for the current season (2026/27) and two earlier seasons (2025/26, 2021/22) included (§4).
- [x] Verdict stated: **BUG CONFIRMED**.
