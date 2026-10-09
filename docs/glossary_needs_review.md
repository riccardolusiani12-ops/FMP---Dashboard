# Glossary `needs_review` entries (12)

**Reviewed and confirmed by owner on 2026-10-09; entries promoted (see glossary_review.md).**

> Read-only package for review. Generated from the registry on `feature/glossary-page` (base `44b7c1f`). No entry was changed.
> Registry files are under `dash_app/src/glossary/`. Code locations are where each methodology was derived from.
> Answer per entry: **yes** (promote to `ok`), or the correction to apply.

| # | id | Name | Section · module | Registry |
|---|---|---|---|---|
| 1 | `league_position` | Position | Team Overview · KPI Row | `entries_team_overview.py:47` |
| 2 | `season_record` | Season Record | Team Overview · KPI Row | `entries_team_overview.py:69` |
| 3 | `last_5_form` | Last 5 | Team Overview · KPI Row | `entries_team_overview.py:89` |
| 4 | `goal_difference` | Goal Diff. | Team Overview · KPI Row | `entries_team_overview.py:110` |
| 5 | `points_per_game` | PPG | Team Overview · KPI Row | `entries_team_overview.py:130` |
| 6 | `mean_age` | Mean Age | Team Overview · KPI Row | `entries_team_overview.py:151` |
| 7 | `starts` | Starts | Team Overview · Most-Used Formations; Opponent Analysis · Player Analysis | `entries_team_overview.py:253` |
| 8 | `lineup_minutes` | Minutes | Team Overview · Most-Used Formations | `entries_team_overview.py:287` |
| 9 | `lineup_avg_minutes` | Avg Min | Team Overview · Most-Used Formations | `entries_team_overview.py:307` |
| 10 | `pressing_tier` | Pressing Tier | Team Overview · Pressing Intensity | `entries_team_overview.py:839` |
| 11 | `immediate_press_rate` | Immediate Press ≤5s | Match Analysis · Transitions — Defensive Transition; Opponent Analysis · Transitions — Defensive Transitions | `entries_transitions_set_pieces.py:309` |
| 12 | `organised_drop_rate` | Organised Drop >10s | Match Analysis · Transitions — Defensive Transition; Opponent Analysis · Transitions — Defensive Transitions | `entries_transitions_set_pieces.py:333` |

## 1. `league_position` · Position

- **Section / module:** Team Overview · KPI Row
- **Registry:** `dash_app/src/glossary/entries_team_overview.py:47` · season_aggregation `sum` · source_doc —
- **Short definition:** The team's current place in the Serie A table for the selected season.
- **Formula:** `rank by Points, then Goal Difference, then Goals For`
- **Methodology (current text):**

> Source: the season standings table (standings_{season}.parquet), built by multi_season_standings.compute_standings() from final scorelines: 3 points for a win, 1 for a draw, 0 for a defeat.
>
> Teams are ordered by Points, then Goal Difference, then Goals For (descending). Head-to-head records, which the official Serie A tie-break uses, are not applied, so tied teams can be ordered differently from the official table.

- **Notes:** No current methodology document covers the standings KPIs.
- **Derived from:**
  - `dash_app/src/analytics/multi_season_standings.py:238-243` (sort by Points, GD, GF)
  - `dash_app/src/analytics/precompute_serie_a.py:103` (`Rank` = row order)
  - `dash_app/src/callbacks/team_detail_callbacks.py:187` (KPI reads `Rank`)

**Question:** Is this definition correct, and is ordering ties by Points → GD → GF (no head-to-head) acceptable, or should the text say the official tie-break is not replicated more prominently?

## 2. `season_record` · Season Record

- **Section / module:** Team Overview · KPI Row
- **Registry:** `dash_app/src/glossary/entries_team_overview.py:69` · season_aggregation `sum` · source_doc —
- **Short definition:** Matches won, drawn and lost so far this season (W · D · L).
- **Formula:** `W · D · L counts from final scorelines`
- **Methodology (current text):**

> Source: the season standings table (standings_{season}.parquet), built by multi_season_standings.compute_standings() from final scorelines: 3 points for a win, 1 for a draw, 0 for a defeat.
>
> W, D and L are the counts of wins, draws and defeats. The card icon is green when W > L, red when L > W, grey otherwise.

- **Notes:** No current methodology document covers the standings KPIs.
- **Derived from:**
  - `dash_app/src/analytics/multi_season_standings.py:207` (`compute_standings`, W/D/L)
  - `dash_app/src/callbacks/team_detail_callbacks.py:278` (icon colour W > L / L > W)

**Question:** Is this definition correct (W · D · L from final scorelines, icon colour by W vs L)?

## 3. `last_5_form` · Last 5

- **Section / module:** Team Overview · KPI Row
- **Registry:** `dash_app/src/glossary/entries_team_overview.py:89` · season_aggregation `sum` · source_doc —
- **Short definition:** Results of the team's five most recent league matches, oldest to newest.
- **Formula:** `last five Result values ordered by matchday`
- **Methodology (current text):**

> Source: points_progression_{season}.parquet (multi_season_standings.compute_points_progression()). The team's rows are sorted by Matchday and the last five `Result` letters (W/D/L) are shown as coloured badges.

- **Notes:** No current methodology document covers the standings KPIs.
- **Derived from:**
  - `dash_app/src/analytics/multi_season_standings.py:253` (`compute_points_progression`)
  - `dash_app/src/callbacks/team_detail_callbacks.py:230-246` (`_get_last_5`, `results[-5:]`)

**Question:** Is this definition correct (last five league results by matchday, oldest to newest)?

## 4. `goal_difference` · Goal Diff.

- **Section / module:** Team Overview · KPI Row
- **Registry:** `dash_app/src/glossary/entries_team_overview.py:110` · season_aggregation `sum` · source_doc —
- **Short definition:** Goals scored minus goals conceded in the league this season.
- **Formula:** `GF − GA`
- **Methodology (current text):**

> Source: the season standings table (standings_{season}.parquet), built by multi_season_standings.compute_standings() from final scorelines: 3 points for a win, 1 for a draw, 0 for a defeat.
>
> GF and GA are scoreline goals, so own goals count for the team that benefits. Shown with a sign; green if positive, red if negative.

- **Notes:** No current methodology document covers the standings KPIs.
- **Derived from:**
  - `dash_app/src/analytics/multi_season_standings.py:207` (`compute_standings`, GD = GF − GA)
  - `dash_app/src/callbacks/team_detail_callbacks.py:204` (colour)

**Question:** Is this definition correct (scoreline GF − GA, own goals credited to the benefiting team)?

## 5. `points_per_game` · PPG

- **Section / module:** Team Overview · KPI Row
- **Registry:** `dash_app/src/glossary/entries_team_overview.py:130` · season_aggregation `ratio_of_sums` · source_doc —
- **Short definition:** Average league points earned per match played this season.
- **Formula:** `Points ÷ matches played`
- **Methodology (current text):**

> Source: the season standings table (standings_{season}.parquet), built by multi_season_standings.compute_standings() from final scorelines: 3 points for a win, 1 for a draw, 0 for a defeat.
>
> PPG = Points ÷ MP, shown to 2 dp. Colour: green ≥ 2.00, orange ≥ 1.30, red below.
>
> **Season aggregate:** numerators and denominators are summed across all of the team's matches first and divided once (ratio of sums); the season value is not an average of per-match rates.

- **Notes:** No current methodology document covers the standings KPIs.
- **Derived from:**
  - `dash_app/src/callbacks/team_detail_callbacks.py:195-198` (Points ÷ MP, thresholds 2.0 / 1.3)

**Question:** Is this definition correct, and are the 2.00 / 1.30 colour thresholds intended?

## 6. `mean_age` · Mean Age

- **Section / module:** Team Overview · KPI Row
- **Registry:** `dash_app/src/glossary/entries_team_overview.py:151` · season_aggregation `external` · source_doc —
- **Short definition:** Average age of the squad as published by Transfermarkt for the season.
- **Formula:** — (none)
- **Methodology (current text):**

> External value: scraped from Transfermarkt's 'Età media' table (scripts/scrape_avg_age.py) into data/external/avg_age_serie_a.csv and read by data_loader.load_team_average_age(). Per the scraper's notes, Transfermarkt weights player ages by minutes played; the dashboard does not recompute it.
>
> Colour: green below 26, orange 26–28, red above 28.

- **Notes:** The only description is the LEGACY doc _archive/MEAN_AGE_KPI_IMPLEMENTATION.md, so no source_doc is set. The minutes-weighting claim is Transfermarkt's, not verified here.
- **Derived from:**
  - `dash_app/scripts/scrape_avg_age.py:7-8` (Transfermarkt 'Età media', minutes-weighted per its notes)
  - `dash_app/src/analytics/data_loader.py:565` (`load_team_average_age`)
  - `dash_app/src/callbacks/team_detail_callbacks.py:211` (colour < 26 / ≤ 28)

**Question:** Is this definition correct, and should the glossary state Transfermarkt's minutes-weighting as fact or as their claim?

## 7. `starts` · Starts

- **Section / module:** Team Overview · Most-Used Formations; Opponent Analysis · Player Analysis
- **Registry:** `dash_app/src/glossary/entries_team_overview.py:253` · season_aggregation `sum` · source_doc `docs/methodology/opponent-analysis/player-analysis/player-analysis.md`
- **Short definition:** Number of matches a player started.
- **Formula:** `count of matches started`
- **Methodology (current text):**

> Team Overview: in the formation squad panel ('View Squad'), Starts is the number of matches the player started in that formation's slot (slots 1–11), from formation_lineups_{season}.parquet; the player with most starts per slot is highlighted.
>
> Opponent Analysis: in the Squad Overview table, Starts is the number of season matches the player started (starting XI = first 11 distinct players of the team to record an on-ball event before any substitution).

- **Notes:** The formation-panel variant is only described in the LEGACY match-report.md (§3.3).
- **Derived from:**
  - Team Overview: `dash_app/src/analytics/precompute_serie_a.py:644,732` (`precompute_formation_lineups`, `starts += 1`)
  - Opponent Analysis: `dash_app/src/analytics/season_player_analysis.py:163,208`

**Question:** Is this definition correct for both variants (formation-slot starts in Team Overview vs season starts in Opponent Analysis)?

## 8. `lineup_minutes` · Minutes

- **Section / module:** Team Overview · Most-Used Formations
- **Registry:** `dash_app/src/glossary/entries_team_overview.py:287` · season_aggregation `sum` · source_doc —
- **Short definition:** Total minutes the player played in matches started in this formation.
- **Formula:** `Σ minutes over starts in the formation`
- **Methodology (current text):**

> From formation_lineups_{season}.parquet (precompute_formation_lineups): for every match the team started in the formation, the minutes of each starter are summed per player and slot.

- **Notes:** Only described in the LEGACY match-report.md (§3.3).
- **Derived from:**
  - `dash_app/src/analytics/precompute_serie_a.py:721,733` (`total_mins += minute_out`)

**Question:** Is this definition correct (minutes summed only over matches the player started in that formation slot)?

## 9. `lineup_avg_minutes` · Avg Min

- **Section / module:** Team Overview · Most-Used Formations
- **Registry:** `dash_app/src/glossary/entries_team_overview.py:307` · season_aggregation `ratio_of_sums` · source_doc —
- **Short definition:** Average minutes per start for the player in this formation.
- **Formula:** `Minutes ÷ Starts`
- **Methodology (current text):**

> Avg Min = total minutes ÷ starts in the formation slot, from formation_lineups_{season}.parquet.
>
> **Season aggregate:** numerators and denominators are summed across all of the team's matches first and divided once (ratio of sums); the season value is not an average of per-match rates.

- **Notes:** Only described in the LEGACY match-report.md (§3.3).
- **Derived from:**
  - `dash_app/src/analytics/precompute_serie_a.py:753` (`total_mins ÷ starts`, 1 dp)
  - `dash_app/src/callbacks/team_detail_callbacks.py:677` (display)

**Question:** Is this definition correct (total minutes ÷ starts in the formation slot)?

## 10. `pressing_tier` · Pressing Tier

- **Section / module:** Team Overview · Pressing Intensity
- **Registry:** `dash_app/src/glossary/entries_team_overview.py:839` · season_aggregation `rank_percentile` · source_doc —
- **Short definition:** A five-level label (Elite to Passive) from the team's PPDA rank.
- **Formula:** `pct = (1 − (rank − 1) ÷ (N − 1)) × 100; ≥80 Elite, ≥60 High, ≥40 Medium, ≥20 Low, else Passive`
- **Methodology (current text):**

> Derived only from PPDA Rank: rank is converted to a 0–100 percentile (1st = 100) and bucketed into Elite / High / Medium / Low / Passive at 80 / 60 / 40 / 20.
>
> **Two PPDA definitions (intentional, never merge):** Team Overview PPDA divides by the pressing team's *ball recoveries*; Match Analysis and Opponent Analysis PPDA divide by *tackles + interceptions + fouls committed + challenges*. The two numbers are not comparable.

- **Notes:** No methodology document describes the tier thresholds.
- **Derived from:**
  - `dash_app/src/callbacks/team_detail_callbacks.py:455-468` (percentile from rank, 80/60/40/20 cut-offs)

**Question:** Is this definition correct, and are the 80/60/40/20 rank-percentile cut-offs the intended tier rules?

## 11. `immediate_press_rate` · Immediate Press ≤5s

- **Section / module:** Match Analysis · Transitions — Defensive Transition; Opponent Analysis · Transitions — Defensive Transitions
- **Registry:** `dash_app/src/glossary/entries_transitions_set_pieces.py:309` · season_aggregation `mean_of_match_values` · source_doc `docs/methodology/match-analysis/transitions/defensive-transitions.md`
- **Short definition:** Share of the team's ball losses after which it made a defensive action within 5 seconds.
- **Formula:** `transitions with first counter-press action ≤ 5 s ÷ recorded transitions × 100`
- **Methodology (current text):**

> **Detection (defensive_structure.compute_defensive_transitions):** every event of the match is scanned. Triggers: the opponent's Ball Recovery (49), Interception (8) or won Tackle (7, outcome 1); or the team's Dispossessed (50), Error (51) or failed Ball Touch (61, outcome 0). Origin = the trigger location (team triggers) or the team's last play event before it (opponent triggers). The loss must be at x ≥ 50 (the team's attacking half). A trigger is skipped when the opponent's next possession starts from a set piece, when the origin event is an out, aerial, challenge, keeper pick-up or shot, when the opponent committed a foul in the previous 3 s, or when it comes less than 30 s after the previous accepted trigger.
>
> Counter-press actions: the team's Foul (4), Tackle (7), Interception (8), Aerial (44), Challenge (45) or Ball Recovery (49) in the 25 s window. The denominator is every recorded transition, qualified or not. Opponent Analysis labels it 'Immediate Press'.
>
> **Season aggregate (code reference):** the season value is the arithmetic mean of the per-match values, not a ratio of summed numerators and denominators. This deviates from the ratio-of-sums rule and is reported in docs/glossary_review.md; it has not been changed.
>
> League comparison modal: ranks all 20 teams on the season rate.

- **Notes:** Not described in the defensive-transitions methodology docs.
- **Derived from:**
  - `dash_app/src/analytics/defensive_structure.py:79` (`IMMEDIATE_PRESS_SEC = 5.0`)
  - `dash_app/src/analytics/defensive_structure.py:238` (`compute_defensive_transitions`), rate at `:679-686`
  - `dash_app/src/analytics/precompute_serie_a.py:1491-1493` (season = mean of match rates)

**Question:** Is this definition correct, including the 5 s window and the denominator of all recorded (not only qualified) transitions?

## 12. `organised_drop_rate` · Organised Drop >10s

- **Section / module:** Match Analysis · Transitions — Defensive Transition; Opponent Analysis · Transitions — Defensive Transitions
- **Registry:** `dash_app/src/glossary/entries_transitions_set_pieces.py:333` · season_aggregation `mean_of_match_values` · source_doc `docs/methodology/match-analysis/transitions/defensive-transitions.md`
- **Short definition:** Share of the team's ball losses after which it made no defensive action for more than 10 seconds.
- **Formula:** `transitions with no counter-press action or first action > 10 s ÷ recorded transitions × 100`
- **Methodology (current text):**

> **Detection (defensive_structure.compute_defensive_transitions):** every event of the match is scanned. Triggers: the opponent's Ball Recovery (49), Interception (8) or won Tackle (7, outcome 1); or the team's Dispossessed (50), Error (51) or failed Ball Touch (61, outcome 0). Origin = the trigger location (team triggers) or the team's last play event before it (opponent triggers). The loss must be at x ≥ 50 (the team's attacking half). A trigger is skipped when the opponent's next possession starts from a set piece, when the origin event is an out, aerial, challenge, keeper pick-up or shot, when the opponent committed a foul in the previous 3 s, or when it comes less than 30 s after the previous accepted trigger.
>
> Counter-press actions as for Immediate Press. Losses with a first action between 5 and 10 s count in neither rate. Opponent Analysis labels it 'Organised Drop'.
>
> **Season aggregate (code reference):** the season value is the arithmetic mean of the per-match values, not a ratio of summed numerators and denominators. This deviates from the ratio-of-sums rule and is reported in docs/glossary_review.md; it has not been changed.
>
> League comparison modal: ranks all 20 teams on the season rate.

- **Notes:** Not described in the defensive-transitions methodology docs.
- **Derived from:**
  - `dash_app/src/analytics/defensive_structure.py:80` (`DROP_BACK_SEC = 10.0`)
  - `dash_app/src/analytics/defensive_structure.py:238` (`compute_defensive_transitions`), rate at `:687-693`
  - `dash_app/src/analytics/precompute_serie_a.py:1492-1494` (season = mean of match rates)

**Question:** Is this definition correct, including the > 10 s / no-action rule and the 5–10 s gap that counts in neither rate?
