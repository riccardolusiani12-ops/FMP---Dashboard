# Glossary Metric Registry — Review Report

> Scope: data layer only (no UI). Pre-work tag: `pre-glossary-registry`.
> Registry: `dash_app/src/glossary/` · Tests: `dash_app/tests/test_glossary_registry.py`

## 1. Summary

| Item | Value |
|---|---|
| Registry entries | **177** (each metric defined once) |
| Entries shown in more than one section | 94 |
| UI metric labels inventoried | 430 rows (Team Overview 57 · Match Analysis 192 · Opponent Analysis 181) |
| Labels explicitly unmapped (visuals, no metric) | 6 |
| Entries flagged `needs_review` | 0 (12 reviewed and confirmed by owner on 2026-10-09, §5) |
| Entries flagged `pending_fix` | 5 (season aggregation fix pending, §5) |
| Season values that break the ratio-of-sums rule | 4 (reported, not fixed; originally 5, Field Tilt % since fixed on main) |
| Probable code defects found | 9 (reported, not fixed) |
| New tests | 1,676 cases, all pass · existing suite 156/156 unchanged |

**Most important findings (read these first)**

1. **FIXED on main (merge commit `5bb5600`, `fix/ppda-fieldtilt-frame`).** `load_season_events()` now uses raw x as stored, and the registry text is aligned (`_FRAME_ISSUE` removed). Original finding: **Team Overview PPDA and Field Tilt % use the wrong coordinate frame for half the events.** `ppda.load_season_events()` flips x by home/away and period (`ppda.py:145-159`), assuming absolute coordinates. The raw Opta files are already team-relative: in a sample match, the mean x of clearances is 9.8–15.4 for both teams in both halves (`data/raw/serie_a_2024_2025/events/10_Atalanta_Monza_*.csv`). For the away team in the first half and the home team in the second half, `x_from_own_goal` is inverted. Every other module (and `playing_style.py`, explicitly) treats x as team-relative.
2. **Wheel D1 "Chance Prevention" is not non-penalty, and not per 90.** It reads `xg_conceded_per_match` (`playing_style.py:249`), which sums *all* conceded xG, penalties at 0.79 included (`precompute_serie_a.py:1219`), and divides by matches. A1 "Chance Creation" is also per match, not per 90.
3. **Style Evolution mislabels A1–A3.** The labels are rotated: the chart titled "Patient Attack" plots A1 (npxG), "Shot Quality" plots A2, "Chance Creation" plots A3 (`playing_style_evolution_cards.py:44-46`).
4. **Four season values average per-match rates** instead of summing numerators and denominators: Possession %, Tempo, Immediate Press, Organised Drop (§6.A). Field Tilt % was originally on this list; it is now a ratio of season sums (fixed on main in `5bb5600`).
5. **Opponent own goals count as shots.** They are injected into the team's shot list as "Own Goal" rows, so they count in Total Shots, SoT %, the TOTAL column, the Chain-to-Goal Matrix, the season shots parquet and wheel A2/A3. This is not documented.

## 2. Phase 0 — Audit

### 2.1 Methodology docs (46 files)

| Classification | Files | Basis |
|---|---|---|
| **CURRENT: metric source** (32) | `team-overview/*` (6), `models/*` (4), `match-analysis/*` except match-report (11), `opponent-analysis/*` (10), plus `match-analysis/other/defensive-structure.md`, `high-regains.md` | every referenced function exists in `dash_app/src/analytics/` |
| **CURRENT: infrastructure, no metrics** (3) | `infrastructure/caching-layer.md`, `canonical-name.md`, `precompute-pipeline.md` | not metric definitions |
| **LEGACY: stale** (1) | `match-analysis/other/match-report.md` | its UI shell `tabs/match_report.py` and `src/registry/loaders.py` no longer exist; no Match Report page is routed |
| **LEGACY: archive** (10) | `_archive/*` (incl. its README) | marked superseded by `_archive/README.md` |

Current docs that are never used as a `source_doc`: `style-evolution.md` (its KPIs are the wheel's), `xg-model.md` (cited inside methodology text), `high-regains.md` (its KPIs are not displayed, §8), `opp-season-defensive-castle.md` (castle entries cite the match doc).

### 2.2 UI inventory

The full table (label · section · module · file → registry id) is in **Appendix A** and, machine-readable, in `dash_app/src/glossary/ui_inventory.py`. Sources:
- Team Overview: `pages/team_detail.py`, `callbacks/team_detail_callbacks.py`, `components/playing_style_cards.py`, `playing_style_evolution_cards.py`, `analytics/ppda.py` (figure titles).
- Match Analysis: the `components/*_cards.py` that `components/analysis_cards.py` renders, plus `KPI_DEFINITIONS` in `analytics/player_analysis.py`.
- Opponent Analysis: `components/opponent_offensive_phase.py` and the `opp_season_*_cards.py` modules.

Not rendered, so not inventoried: `components/general_buildup_cards.py` (imported nowhere), `components/kpis.py` sample cards, and two functions in `defensive_structure_cards.py`, `_section_offside_trap` and `_section_structural_mirror` (defined, never called).

### 2.3 Conventions found

- **Static config** is Python modules (`src/config.py`, `team_mapping.py`, `styling/theme.py`, module-level constants). The repo uses no JSON config.
- **`.gitignore` excludes `*.json` globally** (not only `data/`), plus `data/*`. A JSON registry would be ignored anywhere in the repo.
- **Packages:** `dash_app/src/{analytics,components,callbacks,pages,styling,utils,models}`, imported as `src.*`.
- **Tests:** `dash_app/tests/test_*.py`. `conftest.py` puts `dash_app/` on `sys.path`; `pytest.ini` sets `testpaths = tests`.
- **Component ID prefixes:** `td-` / `team-` (Team Overview), `ma-` (Match Analysis), `opponent-` / `opp-season-` (Opponent Analysis).

### 2.4 Registry location and format (decision)

`dash_app/src/glossary/` is a Python package of dicts:
- `_common.py` holds the vocabularies, doc paths, canonical wording and the `metric()` constructor.
- `entries_*.py` hold the entries.
- `registry.py` assembles `METRICS`.
- `loader.py` exposes `lru_cache`'d accessors: `get_registry()`, `get_metric(id)`, `metrics_for_section(section)`, `metrics_for_module(section, module)`, all returning deep copies.
- `ui_inventory.py` maps each UI label to an id.

Why: it matches the repo's Python-config convention, it can't be swallowed by the `*.json` ignore rule, it lives outside `data/`, and wording constants keep phrasing identical across entries.

## 3. Schema

| Field | Notes |
|---|---|
| `id` | stable slug `[a-z0-9_]+` |
| `name` | exactly as displayed (primary label; alternative labels of the same metric are in the inventory) |
| `sections` | subset of `team_overview`, `match_analysis`, `opponent_analysis` |
| `module` | **dict** `{section: module/card name}`, always present (per section) |
| `short_definition` | 1–2 sentences, plain English |
| `formula` | compact, or `null` (maps) |
| `unit` | count, %, ratio, xG, per 90, percentile, rank, x (0–100), map, distribution, … |
| `reading` + `reading_note` | `higher_better` / `lower_better` / `contextual` + one line why |
| `methodology` | Markdown: filters, zones, windows, thresholds, edge cases, season aggregation, code-reference caveats |
| `notes` | caveats, incl. doc/UI-vs-code discrepancies |
| `source_doc` | CURRENT doc path, or `null` only when `status = needs_review` or the id is in the test allowlist `NO_SOURCE_DOC` (9 code-derived entries, §5) |
| `variants` | only when the same name means different things in different sections (used for `starts`) |
| `status` | `ok` / `needs_review` / `pending_fix` *(addition)*. `pending_fix` = a known code issue will change the value; the card shows "definition may change" |
| `season_aggregation` | how the season value is built: `sum`, `total_per_match`, `ratio_of_sums`, `mean_of_match_values`, `median_of_match_values`, `season_events`, `rank_percentile`, `shrinkage_adjusted`, `external`, or `null` (match only) *(addition — makes the ratio-of-sums rule testable)* |

**PPDA.** The two definitions are two distinct entries, never merged, each with an explicit note:
- `ppda_team_overview` (Team Overview, ball recoveries)
- `ppda_defensive_actions` (Opponent Analysis "PPDA", overall 60% zone, tackles + interceptions + fouls + challenges)

A third narrow-definition entry, `ppda_final_third`, covers the **Match Analysis** card, which shows the *high-zone* variant labelled "PPDA (Final Third)", not the overall one.

**Canonical wording** (in `_common.py`):
- final third = x ≥ 66.67
- penalty box = x ≥ 83.33, 21.1 ≤ y ≤ 78.9
- open play = possession not started by a corner, free kick, throw-in, goal kick, penalty or goalkeeper-hands restart
- corridors: Left y > 66.67, Right y < 33.33
- the 18-zone grid
- the ratio-of-sums sentence, and the mean-of-match-values deviation sentence

## 4. Counts per section and module

| Section | Module | Entries |
|---|---|---|
| team_overview | KPI Row | 6 |
| team_overview | Points Progression | 1 |
| team_overview | Most-Used Formations | 5 |
| team_overview | Offensive Production and Defensive Efficiency | 6 |
| team_overview | Playing Style Wheel · Style Evolution | 12 |
| team_overview | Pressing Intensity | 4 |
| **team_overview** | | **34** |
| match_analysis | Offensive Phase — Build-up from Goal Kicks | 11 |
| match_analysis | Offensive Phase — Build-up to Final Third | 14 |
| match_analysis | Offensive Phase — Chance Creation | 13 |
| match_analysis | Defensive Phase — Pressure | 11 |
| match_analysis | Defensive Phase — Defensive Castle | 7 |
| match_analysis | Defensive Phase — Chances Conceded | 12 |
| match_analysis | Transitions — Offensive Transition | 9 |
| match_analysis | Transitions — Defensive Transition | 11 |
| match_analysis | Set Pieces — Corner Kicks | 8 |
| match_analysis | Set Pieces — Free Kicks | 5 |
| match_analysis | Player Analysis | 21 |
| **match_analysis** | | **122** |
| opponent_analysis | Offensive Phase — GK Build-up (+1 shared "Matches") | 14 |
| opponent_analysis | Offensive Phase — Build-up to Final Third | 10 |
| opponent_analysis | Offensive Phase — Chance Creation | 10 |
| opponent_analysis | Defensive Phase — Defensive Pressing | 8 |
| opponent_analysis | Defensive Phase — Defensive Castle | 7 |
| opponent_analysis | Defensive Phase — Chances Conceded | 9 |
| opponent_analysis | Transitions — Offensive Transitions | 9 |
| opponent_analysis | Transitions — Defensive Transitions | 11 |
| opponent_analysis | Set Pieces — Corner Kicks | 9 |
| opponent_analysis | Player Analysis | 29 |
| **opponent_analysis** | | **116** |

(Section totals exceed 177 because 94 entries appear in more than one section.)

## 5. Review status

### 5.1 `needs_review` entries: cleared

All 12 entries originally flagged `needs_review` were reviewed and confirmed by the owner on 2026-10-09 (record: `docs/glossary_needs_review.md`). No definition, formula, methodology or notes text was changed; only the status.

| id | Name | Why it was flagged | New status |
|---|---|---|---|
| league_position | Position | no current doc; tie-break is Points → GD → GF, with no head-to-head | ok |
| season_record | Season Record | no current doc | ok |
| last_5_form | Last 5 | no current doc | ok |
| goal_difference | Goal Diff. | no current doc | ok |
| points_per_game | PPG | no current doc (colour thresholds 2.00 / 1.30 undocumented) | ok |
| mean_age | Mean Age | only the LEGACY `_archive/MEAN_AGE_KPI_IMPLEMENTATION.md`; external Transfermarkt value | ok |
| starts | Starts | Team Overview variant (formation panel) only in LEGACY `match-report.md` | ok |
| lineup_minutes | Minutes | only in LEGACY `match-report.md` | ok |
| lineup_avg_minutes | Avg Min | only in LEGACY `match-report.md` | ok |
| pressing_tier | Pressing Tier | tier thresholds (80/60/40/20 percentile of PPDA rank) undocumented | ok |
| immediate_press_rate | Immediate Press ≤5s | not in any doc; season value is a mean of match rates | **pending_fix** (§5.2) |
| organised_drop_rate | Organised Drop >10s | not in any doc; season value is a mean of match rates | **pending_fix** (§5.2) |

Nine of them have no methodology document (`source_doc` is `null`): `league_position`, `season_record`, `last_5_form`, `goal_difference`, `points_per_game`, `mean_age`, `lineup_minutes`, `lineup_avg_minutes`, `pressing_tier`. They are allowlisted explicitly in `test_glossary_registry.py` (`NO_SOURCE_DOC`, "code-derived, no methodology doc; reviewed by owner on 2026-10-09"); every other entry still needs a current `source_doc`.

### 5.2 `pending_fix` entries (5)

New status. The definition is correct, but a known code issue will change the value; the card shows a "definition may change" badge. All five belong to the open season-aggregation finding (§1 finding 4, §6.A): the season value is the mean of per-match values, not a ratio of sums. Their methodology keeps the "Season aggregate (code reference)" paragraph until the fix lands.

| id | Name | Season aggregation | Reason |
|---|---|---|---|
| `possession_pct` | Possession % | mean_of_match_values | season value = mean of per-match possession % (`precompute_serie_a.py:594`) |
| `tempo` | Tempo | mean_of_match_values | season value = mean of per-match passes/min (`precompute_serie_a.py:596`) |
| `immediate_press_rate` | Immediate Press ≤5s | mean_of_match_values | season value = mean of per-match rates (`precompute_serie_a.py:1491-1494`) |
| `organised_drop_rate` | Organised Drop >10s | mean_of_match_values | season value = mean of per-match rates (`precompute_serie_a.py:1491-1494`) |
| `ps_possession` | Possession (wheel P3) | rank_percentile | raw P3 = `ft_possession_pct`, the same per-match mean as Possession %; fixing that changes this percentile |

### 5.3 Other open findings (status unchanged, still pending)

These entries are affected by other open findings. Their status stays `ok`; the issue is described in their notes or methodology.

| Finding | Entries | Where |
|---|---|---|
| Wheel D1 Chance Prevention includes penalties and is per match (§1 finding 2, §6.B 2) | `ps_chance_prevention` | `playing_style.py:248-249` |
| Wheel A1 per match, not per 90; Style Evolution labels A1–A3 rotated (§1 findings 2-3, §6.B 3) | `ps_chance_creation`, `ps_patient_attack`, `ps_shot_quality` | `playing_style_evolution_cards.py:44-46` |
| Opponent own goals counted as shots (§1 finding 5, §6.C) | `total_shots`, `shots_in_box`, `sot_pct`, `xg_per_shot`, `team_goals`, `chain_to_goal_matrix`, `shot_quality_tiers`, `ps_patient_attack`, `ps_shot_quality` | chance creation shot list |
| Season corner Goals include own goals; the doc says excluded (§6.C) | `corner_goals` (and `corner_conversion_rate`, same outcome rule) | `corner_kicks._corner_outcome` |

## 6. Doc-vs-code and UI-vs-code discrepancies

In every case the registry follows the **code**; nothing was fixed.

### 6.A Season aggregation: ratio-of-sums rule not met

| Metric | Code | Where |
|---|---|---|
| ~~Field Tilt % (Team Overview)~~ | **FIXED on main (`5bb5600`)**: now Σ team ÷ Σ (team + opponent) final-third passes | `ppda.py:338-410` |
| Possession % (Opponent Analysis; also wheel P3) | mean of per-match possession % | `precompute_serie_a.py:594` |
| Tempo (Opponent Analysis) | mean of per-match passes/min | `precompute_serie_a.py:596` |
| Immediate Press, Organised Drop (Opponent Analysis) | mean of per-match rates | `precompute_serie_a.py:1491-1494` |

Related, but not ratio violations:
- Pressing Line (median) is a median of per-match medians (`precompute_serie_a.py:889`).
- Opp. Box Touches / match is a mean of per-match counts, which equals total ÷ matches analysed.

### 6.B Probable code defects (report only)

1. **FIXED on main (`5bb5600`).** ~~Team Overview PPDA / Field Tilt % frame inversion.~~ See §1. `ppda.py:145-159`.
2. **D1 includes penalties, and is per match.** The comment at `playing_style.py:248` ("xg_conceded already excludes pens") is wrong.
3. **Style Evolution A1–A3 labels rotated.** `playing_style_evolution_cards.py:44-46`.
4. **Offensive transitions: own foul counted as a penalty won.** A *team* foul committed (own row, outcome 0) inside the opponent box sets the P3 penalty flag (`offensive_transitions.py:409-413`).
5. **"Top method excluding short pass" returns the second-ranked method.** `sorted_excl[1]` instead of `[0]` (`season_offensive_summary.py:228`). The value is computed but not displayed.
6. **Formation share differs by code path.** With the parquet, the denominator is all formation records (`precompute_serie_a.py:159`); the raw fallback divides by qualifying formations only (`formations.py:339`).
7. **Unused constants.** `OUTCOME_NEGATIVE_SEC = 3`, `SET_PIECE_ENTRY_SEC = 12` and `RECOVERY_ENTRY_SEC = 8` are defined but never used (`final_third.py:71-81`); the method rule hard-codes 15 s and the outcome rule uses 5 s.
8. **xG differs between sections.** Match and Opponent Analysis xG uses the row-level API (no rebound/assist features, via `compute_xg_for_shot`); Team Overview uses the batch API. The same team-season can show different xG totals.
9. **"Possession by Time Period" band labels are off.** Bands are fixed 15-minute clock slices labelled `15' … 90', 45+', 90+'`. First-half stoppage time lands in the 45–60 band, and the 90–105 band is labelled "45+'" (`final_third.py:172-173`).

### 6.C Docs that disagree with code

| Doc | Doc says | Code does |
|---|---|---|
| `goal-distribution.md` §9, `xg-summary.md` §9 | league modals rank per match, with league share | rank **season totals**, no share |
| `playing-style-wheel.md` §5 | D2 = "pressing actions ÷ opponent passes" | opponent passes ÷ defensive actions (§3.2 of the same doc is right) |
| `playing-style-wheel.md` | D1 non-pen xGA per 90; A1 per 90 | all xGA per match; npxG per match |
| `playing-style-wheel.md` | D3 "GK-sweeper actions" | any player's tackles, interceptions and clearances at x ≤ 16.67 |
| `playing-style-wheel.md` §5 | P3 = share of open-play passes | time-based possession share (mean of matches) |
| `buildup-final-third.md` §3.1 | only open-play possessions scanned for entries | all origins; plus undocumented "high regain" entries for possessions starting in the final third |
| `buildup-final-third.md` §4 | Z14 / flank *reach* | KPI uses the **entry point's** zone (post-entry reach flags are computed but not shown) |
| `buildup-final-third.md` §3.3 | 7 methods | 8 stored keys (cross and long ball separate) |
| `defensive-pressing.md` §3.4 | success = team regains within 10 s | success = team has the *last* play event in a 10 s window (fouls and challenges always fail); code comments say 5 s |
| `defensive-transitions.md` §3.5 / §4 | rate = qualified ÷ losses in attacking half; dedup after a *confirmed* transition | rate ÷ **opponent ball recoveries** (any zone); dedup measured from the last accepted trigger |
| `offensive-transitions.md` §3.3 | "same guards as the defensive module" | dedup 8 s (not 30 s); foul guard checks the *team's* fouls; P1 time flag = any team event ≥ 15 s |
| `opp-season-defensive-transitions.md` §3.2 | rate "per match where stored" | ratio of season sums |
| `opp-season-corner-kicks.md` §3.2-3.3 | cards: corners, goals, conversion, shots, left side, right side; Goals KPI excludes own goals | cards: Corners, Goals, SoT, Soff, Cleared, 2nd Phase (all per match); **Goals includes own goals** |
| `corner-kicks.md` §3.5 | second phase when the attack continues | every **Short** corner without a direct shot becomes "Second Phase Attack" |
| `free-kicks.md` §2/§4 | deliveries "into the box" | every free-kick pass; 12 s outcome window undocumented |
| `opp-season-chance-creation.md` §4-5 | season view shows non-penalty xG, big-chance rate, quality tiers | not displayed (only shots, goals, SoT, xG total, origins, penalty card) |
| `chance-creation.md`, `chance-conceded.md` | — | opponent own goals counted as shots/SoT/goals (undocumented) |
| `attack-origin-classification.md` §3.4 | `_check_penalty_in_events()` populates `is_penalty` | function does not exist; `is_penalty` is computed inline in `_build_shot_detail` (`chance_creation.py:1214`) |
| `possession-value-model.md` | PVA built on `analytics/possession_value.py` (16×12 grid) | Player Analysis PVA uses the ML model in `utils/pv_model.py` (`pv_model_serie_a.pkl`) |
| `formation-analysis.md` | frequency of formations | counts include in-match changes (UI says "Starting shapes") |
| `match-report.md` | Match Report tab | stale: UI files gone (LEGACY) |

### 6.D UI text that disagrees with code

| UI text (file) | Code |
|---|---|
| Wheel info modals (`playing_style_cards.py:66-115`): D1 "per 90"; D2 "opposition touches"; P1 "GK passes … long balls ≥ 40 yards"; P3 "share of open-play passes"; G2 "passing/carrying distance" | see §6.C; P1 is goal kicks by first-receiver zone; G2 is passes only |
| Match Analysis origin caption "Set Piece → High Regain → Counter → Cross → Through Ball → Combination" (`chance_creation_cards.py:602`) | priority is Through Ball → Set Piece → Individual Play → High Regain → Cut Back → Cross → Combination; no "Counter" |
| Conceded origin captions (`chance_conceded_cards.py:275`, `opp_season_chances_conceded_cards.py:790`) | same priority mismatch |
| FT outcome "Lost within ≤ 3 s" (`final_third_cards.py:789`) | 5 s |
| FT short-pass hover "Patient build-up with ≥ 5 passes" (`final_third_cards.py:54`) | no pass-count rule |
| GK P1 "without leaving own half" (`buildup_cards.py:196`) | without reaching the final third |
| Transition Rate "per total team possessions" (`offensive_transition_cards.py`, `defensive_structure_cards.py:158`) | ÷ ball recoveries |
| Total Defensive Actions subtitle lists 5 types (`defensive_pressing_cards.py:129`) | 8 types incl. fouls, challenges, blocked passes |
| Castle "17–33 m line" (`defensive_castle_cards.py:154`) | Opta units (≈ 17.5–35 m) |
| "Starting shapes used three or more times" (`team_detail.py`) | count includes in-match changes |
| Ball Progressions definition mentions carries (`player_analysis.py:241`) | carries have no end point; only passes and take-ons count |
| "Possession Regains" label | only attacking-third regains (high regains) |

### 6.E Observations (not discrepancies, worth a decision)

- **Blocked shots count as on target.** SoT counts Opta type 15, which includes shots blocked by outfield players.
- **Box y-band varies by module.** 21.1–78.9 in chance creation and corners; 21–79 in box touches, castle and transitions.
- **Rates can exceed 100%.** The transition rate's numerator includes every trigger type, but its denominator counts only ball recoveries.
- **Player goals include own goals.** Own goals count as goals (and attempts) for the player who scored them.

## 7. UI metrics with no current documentation

The 9 code-derived entries allowlisted in §5.1 (all reviewed and confirmed by the owner). Two more are documented only in part:
- **Team Overview Points Progression** is covered only briefly, in `ppda-team-overview.md` §3.4.
- **Opponent Analysis Player Analysis** squad-overview columns (Apps, Min%, σ PVA, Adj /90, Raw /90) are described in code docstrings more than in the doc.

## 8. Documented metrics not shown in the UI (excluded from the registry)

| Metric(s) | Doc |
|---|---|
| High-regain KPIs: total high regains, linked to shot/goal, shot/goal conversion, avg time to shot, PV from regains, top regain zones, league table | `high-regains.md` (computed inside Chance Creation, never rendered) |
| xGOT; per-shot PV; chain PV | `chance-creation.md`, `possession-value-model.md` |
| PPDA overall, mid and excl. long balls (Match Analysis) | `defensive-pressing.md` (only `ppda_high` shown in Match Analysis) |
| Offside trap: clustering index, dominant flank, high-zone offsides, offside-line variance, half-split medians | `defensive-structure.md` (`_section_offside_trap` not called) |
| Structural mirror (opponent FT entries, Z14 reach rate, positive entry rate, avg passes to FT) | `defensive-structure.md` (`_section_structural_mirror` not called) |
| Average reaction time, counter-press response time (as KPIs) | transitions docs (reaction time only in map hover) |
| Corner defensive setup (Both Posts / Near / Far / No Posts) | `corner-kicks.md` |
| xG_diff, Shots / ShotsAgainst; PPDA std / matches | `xg-summary.md`, `ppda-team-overview.md` |
| Non-penalty xG, big-chance rate, quality tiers (season Chance Creation) | `opp-season-chance-creation.md` |
| Avg passes / seconds to entry (Match Analysis FT) | `buildup-final-third.md` (only in the unrendered general build-up card) |
| Formation change minutes | `formation-analysis.md` |
| Post-entry Z14 / wide / box reach flags | `buildup-final-third.md` |

## 9. LEGACY docs that contradict current ones

| Legacy doc | Contradiction |
|---|---|
| `_archive/CHANCE_CREATION_METHODOLOGY.md` | 4-tier shot quality (Tier 1 "Basic"); separate "Counter" origin; set piece within 12 s (current 15 s / ≤ 5 passes); through ball by 12 s lookback (current: assisting-pass qualifier); cross wide zone y < 25 / > 75 |
| `_archive/BUILDUP_TO_FINAL_THIRD_METHODOLOGY.md` | set-piece entry within 12 s and transition within 8 s (current: direct restart; 15 s); FT outcome thresholds ≥ 5 s / ≤ 3 s (code: 5 s only) |
| `_archive/DEFENSIVE_PHASE_METHODOLOGY.md` | press success scanned over a 5-second window (current constant 10 s) |
| `_archive/POSSESSION_VALUE_DESIGN.md` | high regain = Ball Recovery only (current: + interceptions and won tackles); regain-to-shot window 30 s (current 15 s) |
| `_archive/MEAN_AGE_KPI_IMPLEMENTATION.md` | no contradiction; the only description of Mean Age |
| `match-analysis/other/match-report.md` | describes a Match Report tab that no longer exists |

## 10. Verification checklist

- [x] **Only new files added.** `git diff --stat` is empty; `git status` lists only the 11 new files under `dash_app/src/glossary/` and `dash_app/tests/`, plus this report.
- [x] **New files visible in git.** `git check-ignore` matches none of them. The registry is Python, not JSON, because of the global `*.json` rule, and lives outside `data/`.
- [x] **Protected functions untouched.** `classify_attack_origin()`, `canonical_name()` and `compute_xg_for_shot()` were only read; no tracked file changed.
- [x] **Both PPDA definitions present and distinct.** `ppda_team_overview` (ball recoveries) vs `ppda_defensive_actions` / `ppda_final_third` (tackles + interceptions + fouls + challenges), enforced by `test_two_distinct_ppda_definitions`.
- [x] **PENALTY_XG = 0.79 and 83.33 confirmed against code.** `xg.py:88`, `chance_creation.py:78`; no `83.5` anywhere in code or registry, enforced by `test_penalty_xg_and_box_boundary_match_code`.
- [x] **New tests pass; existing suite unchanged.** 1,832 passed = 156 existing (same count and result as the pre-work baseline) + 1,676 new.
- [x] **Review report generated.** This file.

**Final registry path:** `dash_app/src/glossary/registry.py` (`METRICS`). Read it through `dash_app/src/glossary/loader.py`.

## Appendix A — UI metric inventory (Phase 0.2)

430 rows. TO = Team Overview, MA = Match Analysis, OA = Opponent Analysis. File paths are relative to `dash_app/src/`.

| Label as shown | Section | Module | Rendered in | Registry id |
|---|---|---|---|---|
| Position | TO | KPI Row | `callbacks/team_detail_callbacks.py` | `league_position` |
| Season Record | TO | KPI Row | `callbacks/team_detail_callbacks.py` | `season_record` |
| Last 5 | TO | KPI Row | `callbacks/team_detail_callbacks.py` | `last_5_form` |
| Goal Diff. | TO | KPI Row | `callbacks/team_detail_callbacks.py` | `goal_difference` |
| PPG | TO | KPI Row | `callbacks/team_detail_callbacks.py` | `points_per_game` |
| Mean Age | TO | KPI Row | `callbacks/team_detail_callbacks.py` | `mean_age` |
| Points Progression | TO | Points Progression | `pages/team_detail.py` | `points_progression` |
| Cumulative Points | TO | Points Progression | `analytics/multi_season_standings.py` | `points_progression` |
| Times Used | TO | Most-Used Formations | `callbacks/team_detail_callbacks.py` | `formation_times_used` |
| Share | TO | Most-Used Formations | `callbacks/team_detail_callbacks.py` | `formation_share` |
| Starts | TO | Most-Used Formations | `callbacks/team_detail_callbacks.py` | `starts` |
| Minutes | TO | Most-Used Formations | `callbacks/team_detail_callbacks.py` | `lineup_minutes` |
| Avg Min | TO | Most-Used Formations | `callbacks/team_detail_callbacks.py` | `lineup_avg_minutes` |
| Goals Scored | TO | Offensive Production and Defensive Efficiency | `callbacks/team_detail_callbacks.py` | `goals_scored` |
| Goals Conceded | TO | Offensive Production and Defensive Efficiency | `callbacks/team_detail_callbacks.py` | `goals_conceded` |
| xG | TO | Offensive Production and Defensive Efficiency | `callbacks/team_detail_callbacks.py` | `xg_for` |
| xGC | TO | Offensive Production and Defensive Efficiency | `callbacks/team_detail_callbacks.py` | `xg_against` |
| Expected (xG) | TO | Offensive Production and Defensive Efficiency | `callbacks/team_detail_callbacks.py` | `xg_for` |
| Goals Scored — League Comparison | TO | Offensive Production and Defensive Efficiency | `pages/team_detail.py` | `goals_scored` |
| Goals Conceded — League Comparison | TO | Offensive Production and Defensive Efficiency | `pages/team_detail.py` | `goals_conceded` |
| xG For — League Comparison | TO | Offensive Production and Defensive Efficiency | `pages/team_detail.py` | `xg_for` |
| xGC Against — League Comparison | TO | Offensive Production and Defensive Efficiency | `pages/team_detail.py` | `xg_against` |
| Goals Scored — 15-Minute Intervals | TO | Offensive Production and Defensive Efficiency | `pages/team_detail.py` | `goals_scored_by_interval` |
| Goals Conceded — 15-Minute Intervals | TO | Offensive Production and Defensive Efficiency | `pages/team_detail.py` | `goals_conceded_by_interval` |
| Chance Prevention | TO | Playing Style Wheel · Style Evolution | `components/playing_style_cards.py` | `ps_chance_prevention` |
| Defensive Intensity | TO | Playing Style Wheel · Style Evolution | `components/playing_style_cards.py` | `ps_defensive_intensity` |
| High Line | TO | Playing Style Wheel · Style Evolution | `components/playing_style_cards.py` | `ps_high_line` |
| Deep Build-up | TO | Playing Style Wheel · Style Evolution | `components/playing_style_cards.py` | `ps_deep_buildup` |
| Press Resistance | TO | Playing Style Wheel · Style Evolution | `components/playing_style_cards.py` | `ps_press_resistance` |
| Possession | TO | Playing Style Wheel · Style Evolution | `components/playing_style_cards.py` | `ps_possession` |
| Central Progression | TO | Playing Style Wheel · Style Evolution | `components/playing_style_cards.py` | `ps_central_progression` |
| Circulate | TO | Playing Style Wheel · Style Evolution | `components/playing_style_cards.py` | `ps_circulate` |
| Field Tilt | TO | Playing Style Wheel · Style Evolution | `components/playing_style_cards.py` | `ps_field_tilt` |
| Chance Creation | TO | Playing Style Wheel · Style Evolution | `components/playing_style_cards.py` | `ps_chance_creation` |
| Patient Attack | TO | Playing Style Wheel · Style Evolution | `components/playing_style_cards.py` | `ps_patient_attack` |
| Shot Quality | TO | Playing Style Wheel · Style Evolution | `components/playing_style_cards.py` | `ps_shot_quality` |
| Intensity | TO | Playing Style Wheel · Style Evolution | `components/playing_style_cards.py` | `ps_defensive_intensity` |
| Central Progr. | TO | Playing Style Wheel · Style Evolution | `components/playing_style_cards.py` | `ps_central_progression` |
| Chance Prevention | TO | Playing Style Wheel · Style Evolution | `components/playing_style_evolution_cards.py` | `ps_chance_prevention` |
| High Line | TO | Playing Style Wheel · Style Evolution | `components/playing_style_evolution_cards.py` | `ps_high_line` |
| Deep Build-up | TO | Playing Style Wheel · Style Evolution | `components/playing_style_evolution_cards.py` | `ps_deep_buildup` |
| Press Resistance | TO | Playing Style Wheel · Style Evolution | `components/playing_style_evolution_cards.py` | `ps_press_resistance` |
| Possession | TO | Playing Style Wheel · Style Evolution | `components/playing_style_evolution_cards.py` | `ps_possession` |
| Central Progression | TO | Playing Style Wheel · Style Evolution | `components/playing_style_evolution_cards.py` | `ps_central_progression` |
| Circulate | TO | Playing Style Wheel · Style Evolution | `components/playing_style_evolution_cards.py` | `ps_circulate` |
| Field Tilt | TO | Playing Style Wheel · Style Evolution | `components/playing_style_evolution_cards.py` | `ps_field_tilt` |
| Chance Creation | TO | Playing Style Wheel · Style Evolution | `components/playing_style_evolution_cards.py` | `ps_chance_creation` |
| Patient Attack | TO | Playing Style Wheel · Style Evolution | `components/playing_style_evolution_cards.py` | `ps_patient_attack` |
| Shot Quality | TO | Playing Style Wheel · Style Evolution | `components/playing_style_evolution_cards.py` | `ps_shot_quality` |
| Intensity | TO | Playing Style Wheel · Style Evolution | `components/playing_style_evolution_cards.py` | `ps_defensive_intensity` |
| PPDA Rank | TO | Pressing Intensity | `callbacks/team_detail_callbacks.py` | `ppda_rank` |
| PPDA | TO | Pressing Intensity | `callbacks/team_detail_callbacks.py` | `ppda_team_overview` |
| Field Tilt % | TO | Pressing Intensity | `callbacks/team_detail_callbacks.py` | `field_tilt_pct` |
| Pressing Tier | TO | Pressing Intensity | `callbacks/team_detail_callbacks.py` | `pressing_tier` |
| PPDA Ranking — Pressing Intensity | TO | Pressing Intensity | `analytics/ppda.py` | `ppda_team_overview` |
| PPDA vs Field Tilt | TO | Pressing Intensity | `analytics/ppda.py` | `ppda_team_overview` |
| Field Tilt % (higher = more attacking territory control) | TO | Pressing Intensity | `analytics/ppda.py` | `field_tilt_pct` |
| Total | MA | Offensive Phase — Build-up from Goal Kicks | `components/buildup_cards.py` | `gk_possessions` |
| Short | MA | Offensive Phase — Build-up from Goal Kicks | `components/buildup_cards.py` | `gk_short_pct` |
| Long | MA | Offensive Phase — Build-up from Goal Kicks | `components/buildup_cards.py` | `gk_long_pct` |
| First Receiver Zone Distribution | MA | Offensive Phase — Build-up from Goal Kicks | `components/buildup_cards.py` | `gk_first_receiver_zones` |
| Goal Kick — First Receiver Zones | MA | Offensive Phase — Build-up from Goal Kicks | `components/buildup_cards.py` | `gk_first_receiver_zones` |
| Outcome Classification | MA | Offensive Phase — Build-up from Goal Kicks | `components/buildup_cards.py` | `gk_outcome` |
| Positive | MA | Offensive Phase — Build-up from Goal Kicks | `components/buildup_cards.py` | `gk_outcome` |
| Negative | MA | Offensive Phase — Build-up from Goal Kicks | `components/buildup_cards.py` | `gk_outcome` |
| Established Possession | MA | Offensive Phase — Build-up from Goal Kicks | `components/buildup_cards.py` | `gk_p1_established_possession` |
| Reached Final Third | MA | Offensive Phase — Build-up from Goal Kicks | `components/buildup_cards.py` | `gk_p2_reached_final_third` |
| Created a Shot | MA | Offensive Phase — Build-up from Goal Kicks | `components/buildup_cards.py` | `gk_p3_created_shot` |
| Possession Lost | MA | Offensive Phase — Build-up from Goal Kicks | `components/buildup_cards.py` | `gk_n1_possession_lost` |
| Box Entry Conceded | MA | Offensive Phase — Build-up from Goal Kicks | `components/buildup_cards.py` | `gk_n2_box_entry_conceded` |
| Shot Conceded | MA | Offensive Phase — Build-up from Goal Kicks | `components/buildup_cards.py` | `gk_n3_shot_conceded` |
| Possession % | MA | Offensive Phase — Build-up to Final Third | `components/final_third_cards.py` | `possession_pct` |
| POSSESSION BY TIME PERIOD | MA | Offensive Phase — Build-up to Final Third | `components/final_third_cards.py` | `possession_by_time_period` |
| POSSESSION BY PITCH AREA | MA | Offensive Phase — Build-up to Final Third | `components/final_third_cards.py` | `possession_by_pitch_area` |
| Qualifying Poss. | MA | Offensive Phase — Build-up to Final Third | `components/final_third_cards.py` | `qualifying_possessions` |
| Total FT Entries | MA | Offensive Phase — Build-up to Final Third | `components/final_third_cards.py` | `ft_entries_total` |
| Qual. FT Entries | MA | Offensive Phase — Build-up to Final Third | `components/final_third_cards.py` | `ft_entries_qualifying` |
| Opp. Box Touches | MA | Offensive Phase — Build-up to Final Third | `components/final_third_cards.py` | `opp_box_touches` |
| Tempo | MA | Offensive Phase — Build-up to Final Third | `components/final_third_cards.py` | `tempo` |
| Tempo — 15-Minute Windows | MA | Offensive Phase — Build-up to Final Third | `components/final_third_cards.py` | `tempo` |
| Entry by Corridor | MA | Offensive Phase — Build-up to Final Third | `components/final_third_cards.py` | `ft_entry_corridor` |
| How — Entry Method | MA | Offensive Phase — Build-up to Final Third | `components/final_third_cards.py` | `ft_entry_method` |
| Zone 14 | MA | Offensive Phase — Build-up to Final Third | `components/final_third_cards.py` | `ft_zone14` |
| Flanks | MA | Offensive Phase — Build-up to Final Third | `components/final_third_cards.py` | `ft_flanks` |
| Entry Outcomes (Positive / Negative) | MA | Offensive Phase — Build-up to Final Third | `components/final_third_cards.py` | `ft_entry_outcome` |
| Outcomes by Corridor | MA | Offensive Phase — Build-up to Final Third | `components/final_third_cards.py` | `ft_entry_outcome` |
| Outcomes by Method | MA | Offensive Phase — Build-up to Final Third | `components/final_third_cards.py` | `ft_entry_outcome` |
| Entry Points — Method View | MA | Offensive Phase — Build-up to Final Third | `components/final_third_cards.py` | `ft_entry_map` |
| FT Entry Zones & Outcomes | MA | Offensive Phase — Build-up to Final Third | `components/final_third_cards.py` | `ft_entry_map` |
| Total Shots | MA | Offensive Phase — Chance Creation | `components/chance_creation_cards.py` | `total_shots` |
| In-Box | MA | Offensive Phase — Chance Creation | `components/chance_creation_cards.py` | `shots_in_box` |
| Out-Box | MA | Offensive Phase — Chance Creation | `components/chance_creation_cards.py` | `shots_out_box` |
| SoT % | MA | Offensive Phase — Chance Creation | `components/chance_creation_cards.py` | `sot_pct` |
| xG Total | MA | Offensive Phase — Chance Creation | `components/chance_creation_cards.py` | `xg_total` |
| xG/Shot | MA | Offensive Phase — Chance Creation | `components/chance_creation_cards.py` | `xg_per_shot` |
| Goals | MA | Offensive Phase — Chance Creation | `components/chance_creation_cards.py` | `team_goals` |
| Chain-to-Goal Matrix | MA | Offensive Phase — Chance Creation | `components/chance_creation_cards.py` | `chain_to_goal_matrix` |
| Attack Origin Breakdown | MA | Offensive Phase — Chance Creation | `components/chance_creation_cards.py` | `attack_origin` |
| Set Piece | MA | Offensive Phase — Chance Creation | `components/chance_creation_cards.py` | `attack_origin` |
| High Regain | MA | Offensive Phase — Chance Creation | `components/chance_creation_cards.py` | `attack_origin` |
| Cross | MA | Offensive Phase — Chance Creation | `components/chance_creation_cards.py` | `attack_origin` |
| Through Ball | MA | Offensive Phase — Chance Creation | `components/chance_creation_cards.py` | `attack_origin` |
| Cut Back | MA | Offensive Phase — Chance Creation | `components/chance_creation_cards.py` | `attack_origin` |
| Individual Play | MA | Offensive Phase — Chance Creation | `components/chance_creation_cards.py` | `attack_origin` |
| Combination | MA | Offensive Phase — Chance Creation | `components/chance_creation_cards.py` | `attack_origin` |
| Penalty | MA | Offensive Phase — Chance Creation | `components/chance_creation_cards.py` | `penalty_card` |
| Shot Quality Tiers | MA | Offensive Phase — Chance Creation | `components/chance_creation_cards.py` | `shot_quality_tiers` |
| Converted | MA | Offensive Phase — Chance Creation | `components/chance_creation_cards.py` | `shot_quality_tiers` |
| Big Chance | MA | Offensive Phase — Chance Creation | `components/chance_creation_cards.py` | `shot_quality_tiers` |
| Speculative | MA | Offensive Phase — Chance Creation | `components/chance_creation_cards.py` | `shot_quality_tiers` |
| xG by Attack Origin | MA | Offensive Phase — Chance Creation | `components/chance_creation_cards.py` | `xg_by_origin` |
| Attack Origin Zones | MA | Offensive Phase — Chance Creation | `components/chance_creation_cards.py` | `attack_origin_zones` |
| Total Defensive Actions | MA | Defensive Phase — Pressure | `components/defensive_pressing_cards.py` | `total_defensive_actions` |
| PPDA (Final Third) | MA | Defensive Phase — Pressure | `components/defensive_pressing_cards.py` | `ppda_final_third` |
| Press Success | MA | Defensive Phase — Pressure | `components/defensive_pressing_cards.py` | `press_success_rate` |
| Offsides Provoked | MA | Defensive Phase — Pressure | `components/defensive_pressing_cards.py` | `offsides_provoked` |
| Offside Line (median) | MA | Defensive Phase — Pressure | `components/defensive_pressing_cards.py` | `offside_line_median` |
| Pressing line | MA | Defensive Phase — Pressure | `components/defensive_pressing_cards.py` | `pressing_line_median` |
| Defensive Actions | MA | Defensive Phase — Pressure | `components/defensive_pressing_cards.py` | `defensive_actions_by_third` |
| Final Third | MA | Defensive Phase — Pressure | `components/defensive_pressing_cards.py` | `defensive_actions_by_third` |
| Middle Third | MA | Defensive Phase — Pressure | `components/defensive_pressing_cards.py` | `defensive_actions_by_third` |
| Own Third | MA | Defensive Phase — Pressure | `components/defensive_pressing_cards.py` | `defensive_actions_by_third` |
| High Press | MA | Defensive Phase — Pressure | `components/defensive_pressing_cards.py` | `defensive_actions_by_third` |
| Mid Press | MA | Defensive Phase — Pressure | `components/defensive_pressing_cards.py` | `defensive_actions_by_third` |
| Low Block | MA | Defensive Phase — Pressure | `components/defensive_pressing_cards.py` | `defensive_actions_by_third` |
| Pressing Direction | MA | Defensive Phase — Pressure | `components/defensive_pressing_cards.py` | `pressing_direction` |
| Pressing Success by Zone | MA | Defensive Phase — Pressure | `components/defensive_pressing_cards.py` | `press_success_by_zone` |
| Action Density + Press Outcomes | MA | Defensive Phase — Pressure | `components/defensive_pressing_cards.py` | `defensive_action_density` |
| Defensive Actions by Type | MA | Defensive Phase — Pressure | `components/defensive_pressing_cards.py` | `defensive_actions_by_type` |
| Def. Actions in 1st Third | MA | Defensive Phase — Defensive Castle | `components/defensive_castle_cards.py` | `castle_actions` |
| In Own Box | MA | Defensive Phase — Defensive Castle | `components/defensive_castle_cards.py` | `castle_in_own_box` |
| Wide Flanks | MA | Defensive Phase — Defensive Castle | `components/defensive_castle_cards.py` | `castle_wide_flanks` |
| Def. Third Edge | MA | Defensive Phase — Defensive Castle | `components/defensive_castle_cards.py` | `castle_def_third_edge` |
| Actions by Type | MA | Defensive Phase — Defensive Castle | `components/defensive_castle_cards.py` | `castle_actions_by_type` |
| Defensive Corridor | MA | Defensive Phase — Defensive Castle | `components/defensive_castle_cards.py` | `castle_corridor` |
| Zone Action Density — Defensive Third | MA | Defensive Phase — Defensive Castle | `components/defensive_castle_cards.py` | `castle_zone_density` |
| Total Shots Faced | MA | Defensive Phase — Chances Conceded | `components/chance_conceded_cards.py` | `shots_faced` |
| In-Box | MA | Defensive Phase — Chances Conceded | `components/chance_conceded_cards.py` | `shots_faced_in_box` |
| Out-Box | MA | Defensive Phase — Chances Conceded | `components/chance_conceded_cards.py` | `shots_faced_out_box` |
| SoT Faced % | MA | Defensive Phase — Chances Conceded | `components/chance_conceded_cards.py` | `sot_faced_pct` |
| xG Against | MA | Defensive Phase — Chances Conceded | `components/chance_conceded_cards.py` | `xg_conceded` |
| Goals Conceded | MA | Defensive Phase — Chances Conceded | `components/chance_conceded_cards.py` | `goals_conceded` |
| Big chances | MA | Defensive Phase — Chances Conceded | `components/chance_conceded_cards.py` | `big_chances_conceded` |
| Chain-to-Concede Matrix | MA | Defensive Phase — Chances Conceded | `components/chance_conceded_cards.py` | `chain_to_concede_matrix` |
| Attack Origin Breakdown | MA | Defensive Phase — Chances Conceded | `components/chance_conceded_cards.py` | `attack_origin_conceded` |
| Penalty | MA | Defensive Phase — Chances Conceded | `components/chance_conceded_cards.py` | `attack_origin_conceded` |
| xG Against by Attack Origin | MA | Defensive Phase — Chances Conceded | `components/chance_conceded_cards.py` | `xg_against_by_origin` |
| Shot Origin Zones — Defensive Frame | MA | Defensive Phase — Chances Conceded | `components/chance_conceded_cards.py` | `shot_origin_zones_defensive` |
| Shot Quality Tiers Conceded | MA | Defensive Phase — Chances Conceded | `components/chance_conceded_cards.py` | `shot_quality_tiers_conceded` |
| Total Transitions | MA | Transitions — Offensive Transition | `components/offensive_transition_cards.py` | `off_total_transitions` |
| Qualified Transitions | MA | Transitions — Offensive Transition | `components/offensive_transition_cards.py` | `off_qualified_transitions` |
| Transition Rate | MA | Transitions — Offensive Transition | `components/offensive_transition_cards.py` | `off_transition_rate` |
| P1 — Sustained | MA | Transitions — Offensive Transition | `components/offensive_transition_cards.py` | `off_p1_sustained` |
| P2 — Threatening | MA | Transitions — Offensive Transition | `components/offensive_transition_cards.py` | `off_p2_threatening` |
| P3 — Dangerous | MA | Transitions — Offensive Transition | `components/offensive_transition_cards.py` | `off_p3_dangerous` |
| Outcomes by Zone | MA | Transitions — Offensive Transition | `components/offensive_transition_cards.py` | `off_outcomes_by_zone` |
| Outcomes by Corridor | MA | Transitions — Offensive Transition | `components/offensive_transition_cards.py` | `off_outcomes_by_corridor` |
| Offensive Transition Origins (Qualified · Own Half) | MA | Transitions — Offensive Transition | `components/offensive_transition_cards.py` | `off_transition_origins` |
| Total Transitions | MA | Transitions — Defensive Transition | `components/defensive_structure_cards.py` | `def_total_transitions` |
| Qualified Transitions | MA | Transitions — Defensive Transition | `components/defensive_structure_cards.py` | `def_qualified_transitions` |
| Transition Rate | MA | Transitions — Defensive Transition | `components/defensive_structure_cards.py` | `def_transition_rate` |
| Immediate Press ≤5s | MA | Transitions — Defensive Transition | `components/defensive_structure_cards.py` | `immediate_press_rate` |
| Organised Drop >10s | MA | Transitions — Defensive Transition | `components/defensive_structure_cards.py` | `organised_drop_rate` |
| N1 — Sustained | MA | Transitions — Defensive Transition | `components/defensive_structure_cards.py` | `def_n1_sustained` |
| N2 — Threatening | MA | Transitions — Defensive Transition | `components/defensive_structure_cards.py` | `def_n2_threatening` |
| N3 — Dangerous | MA | Transitions — Defensive Transition | `components/defensive_structure_cards.py` | `def_n3_dangerous` |
| Outcomes by Zone | MA | Transitions — Defensive Transition | `components/defensive_structure_cards.py` | `def_outcomes_by_zone` |
| Outcomes by Corridor | MA | Transitions — Defensive Transition | `components/defensive_structure_cards.py` | `def_outcomes_by_corridor` |
| Transition Loss Origins (Qualified · Middle + Attacking Third) | MA | Transitions — Defensive Transition | `components/defensive_structure_cards.py` | `def_transition_origins` |
| Total Corners | MA | Set Pieces — Corner Kicks | `components/set_piece_cards.py` | `corners_total` |
| Goals | MA | Set Pieces — Corner Kicks | `components/set_piece_cards.py` | `corner_goals` |
| Shots on Target | MA | Set Pieces — Corner Kicks | `components/set_piece_cards.py` | `corner_shots_on_target` |
| Shots off Target | MA | Set Pieces — Corner Kicks | `components/set_piece_cards.py` | `corner_shots_off_target` |
| Cleared | MA | Set Pieces — Corner Kicks | `components/set_piece_cards.py` | `corner_cleared` |
| 2nd Phase | MA | Set Pieces — Corner Kicks | `components/set_piece_cards.py` | `corner_second_phase` |
| Delivery Type | MA | Set Pieces — Corner Kicks | `components/set_piece_cards.py` | `corner_delivery_type` |
| Inswinger | MA | Set Pieces — Corner Kicks | `components/set_piece_cards.py` | `corner_delivery_type` |
| Outswinger | MA | Set Pieces — Corner Kicks | `components/set_piece_cards.py` | `corner_delivery_type` |
| Straight | MA | Set Pieces — Corner Kicks | `components/set_piece_cards.py` | `corner_delivery_type` |
| Delivery Maps | MA | Set Pieces — Corner Kicks | `components/set_piece_cards.py` | `corner_delivery_zones` |
| GA1 | MA | Set Pieces — Corner Kicks | `components/set_piece_cards.py` | `corner_delivery_zones` |
| CA1 | MA | Set Pieces — Corner Kicks | `components/set_piece_cards.py` | `corner_delivery_zones` |
| Edge | MA | Set Pieces — Corner Kicks | `components/set_piece_cards.py` | `corner_delivery_zones` |
| Front Zone | MA | Set Pieces — Corner Kicks | `components/set_piece_cards.py` | `corner_delivery_zones` |
| Back Zone | MA | Set Pieces — Corner Kicks | `components/set_piece_cards.py` | `corner_delivery_zones` |
| Total Deliveries | MA | Set Pieces — Free Kicks | `components/set_piece_cards.py` | `fk_total_deliveries` |
| FK Deliveries — Volume & Outcomes | MA | Set Pieces — Free Kicks | `components/set_piece_cards.py` | `fk_delivery_outcomes` |
| Goals | MA | Set Pieces — Free Kicks | `components/set_piece_cards.py` | `fk_delivery_outcomes` |
| Shots on Target | MA | Set Pieces — Free Kicks | `components/set_piece_cards.py` | `fk_delivery_outcomes` |
| Shots off Target | MA | Set Pieces — Free Kicks | `components/set_piece_cards.py` | `fk_delivery_outcomes` |
| Hit Post | MA | Set Pieces — Free Kicks | `components/set_piece_cards.py` | `fk_delivery_outcomes` |
| Goals | MA | Set Pieces — Free Kicks | `components/set_piece_cards.py` | `fk_direct_shot_outcomes` |
| Shots on Target | MA | Set Pieces — Free Kicks | `components/set_piece_cards.py` | `fk_direct_shot_outcomes` |
| Shots off Target | MA | Set Pieces — Free Kicks | `components/set_piece_cards.py` | `fk_direct_shot_outcomes` |
| 2nd Phase / Foul | MA | Set Pieces — Free Kicks | `components/set_piece_cards.py` | `fk_delivery_outcomes` |
| Cleared / No Shot | MA | Set Pieces — Free Kicks | `components/set_piece_cards.py` | `fk_delivery_outcomes` |
| Delivery Type | MA | Set Pieces — Free Kicks | `components/set_piece_cards.py` | `fk_delivery_type` |
| Crossed into Box | MA | Set Pieces — Free Kicks | `components/set_piece_cards.py` | `fk_delivery_type` |
| Chipped / Lofted | MA | Set Pieces — Free Kicks | `components/set_piece_cards.py` | `fk_delivery_type` |
| Launch | MA | Set Pieces — Free Kicks | `components/set_piece_cards.py` | `fk_delivery_type` |
| Landing Zone | MA | Set Pieces — Free Kicks | `components/set_piece_cards.py` | `fk_delivery_type` |
| Total FK Shots | MA | Set Pieces — Free Kicks | `components/set_piece_cards.py` | `fk_total_shots` |
| Direct FK Shots — Volume & Outcomes | MA | Set Pieces — Free Kicks | `components/set_piece_cards.py` | `fk_direct_shot_outcomes` |
| Hit Post | MA | Set Pieces — Free Kicks | `components/set_piece_cards.py` | `fk_direct_shot_outcomes` |
| Blocked | MA | Set Pieces — Free Kicks | `components/set_piece_cards.py` | `fk_direct_shot_outcomes` |
| On Frame | MA | Set Pieces — Free Kicks | `components/set_piece_cards.py` | `fk_direct_shot_outcomes` |
| Goalmouth zone (GK perspective) | MA | Set Pieces — Free Kicks | `components/set_piece_cards.py` | `fk_direct_shot_outcomes` |
| Passes Completed | MA | Player Analysis | `components/player_analysis_cards.py` | `passes_completed` |
| Pass Completion % | MA | Player Analysis | `components/player_analysis_cards.py` | `pass_completion_pct` |
| Ball Progressions | MA | Player Analysis | `components/player_analysis_cards.py` | `ball_progressions` |
| Line Breaks | MA | Player Analysis | `components/player_analysis_cards.py` | `line_breaks` |
| Switches of Play | MA | Player Analysis | `components/player_analysis_cards.py` | `switches_of_play` |
| Crosses Completed | MA | Player Analysis | `components/player_analysis_cards.py` | `crosses_completed` |
| Take-Ons | MA | Player Analysis | `components/player_analysis_cards.py` | `take_ons` |
| Attempts at Goal | MA | Player Analysis | `components/player_analysis_cards.py` | `attempts_at_goal` |
| Goals | MA | Player Analysis | `components/player_analysis_cards.py` | `player_goals` |
| Tackles Won | MA | Player Analysis | `components/player_analysis_cards.py` | `tackles_won` |
| Tackles Made | MA | Player Analysis | `components/player_analysis_cards.py` | `tackles_made` |
| Interceptions | MA | Player Analysis | `components/player_analysis_cards.py` | `interceptions` |
| Blocks | MA | Player Analysis | `components/player_analysis_cards.py` | `blocks` |
| Clearances | MA | Player Analysis | `components/player_analysis_cards.py` | `clearances` |
| Aerial Duels Won | MA | Player Analysis | `components/player_analysis_cards.py` | `aerial_duels_won` |
| Possession Regains | MA | Player Analysis | `components/player_analysis_cards.py` | `possession_regains` |
| Offensive PVA | MA | Player Analysis | `components/player_analysis_cards.py` | `offensive_pva` |
| Defensive PVA | MA | Player Analysis | `components/player_analysis_cards.py` | `defensive_pva` |
| Total PVA | MA | Player Analysis | `components/player_analysis_cards.py` | `total_pva` |
| PVA per 90 | MA | Player Analysis | `components/player_analysis_cards.py` | `total_pva` |
| Event Map — Possession Value Added | MA | Player Analysis | `components/player_analysis_cards.py` | `offensive_pva` |
| Cumulative Possession Value | MA | Player Analysis | `components/player_analysis_cards.py` | `cumulative_possession_value` |
| Value added | MA | Player Analysis | `components/player_analysis_cards.py` | `cumulative_possession_value` |
| Value lost | MA | Player Analysis | `components/player_analysis_cards.py` | `cumulative_possession_value` |
| Top Passer | MA | Player Analysis | `components/player_analysis_cards.py` | `passes_completed` |
| Top Progressor | MA | Player Analysis | `components/player_analysis_cards.py` | `ball_progressions` |
| Top Crosser | MA | Player Analysis | `components/player_analysis_cards.py` | `crosses_completed` |
| Most Shots | MA | Player Analysis | `components/player_analysis_cards.py` | `attempts_at_goal` |
| Top Tackler | MA | Player Analysis | `components/player_analysis_cards.py` | `tackles_won` |
| Top Interceptor | MA | Player Analysis | `components/player_analysis_cards.py` | `interceptions` |
| Top in Air | MA | Player Analysis | `components/player_analysis_cards.py` | `aerial_duels_won` |
| Top Regains | MA | Player Analysis | `components/player_analysis_cards.py` | `possession_regains` |
| Att | MA | Player Analysis | `components/player_analysis_cards.py` | `passes_completed` |
| Cmp | MA | Player Analysis | `components/player_analysis_cards.py` | `passes_completed` |
| LB Att | MA | Player Analysis | `components/player_analysis_cards.py` | `line_breaks` |
| LB Cmp | MA | Player Analysis | `components/player_analysis_cards.py` | `line_breaks` |
| LB % | MA | Player Analysis | `components/player_analysis_cards.py` | `line_breaks` |
| Cross Att | MA | Player Analysis | `components/player_analysis_cards.py` | `crosses_completed` |
| Cross Cmp | MA | Player Analysis | `components/player_analysis_cards.py` | `crosses_completed` |
| Made | MA | Player Analysis | `components/player_analysis_cards.py` | `tackles_made` |
| Contested | MA | Player Analysis | `components/player_analysis_cards.py` | `aerial_duels_won` |
| Min | MA | Player Analysis | `components/player_analysis_cards.py` | `season_minutes` |
| Matches | OA | Offensive Phase — GK Build-up | `components/opponent_offensive_phase.py` | `matches_analysed` |
| GK Possessions | OA | Offensive Phase — GK Build-up | `components/opponent_offensive_phase.py` | `gk_possessions` |
| Short Pass % | OA | Offensive Phase — GK Build-up | `components/opponent_offensive_phase.py` | `gk_short_pct` |
| Long Ball % | OA | Offensive Phase — GK Build-up | `components/opponent_offensive_phase.py` | `gk_long_pct` |
| % success (Short Pass) | OA | Offensive Phase — GK Build-up | `components/opponent_offensive_phase.py` | `gk_short_success_rate` |
| % success (Long Ball) | OA | Offensive Phase — GK Build-up | `components/opponent_offensive_phase.py` | `gk_long_success_rate` |
| GK Short-Pass Success Rate — All Teams | OA | Offensive Phase — GK Build-up | `components/opponent_offensive_phase.py` | `gk_short_success_rate` |
| GK Long-Ball Success Rate — All Teams | OA | Offensive Phase — GK Build-up | `components/opponent_offensive_phase.py` | `gk_long_success_rate` |
| Outcome Breakdown — Short Pass | OA | Offensive Phase — GK Build-up | `components/opponent_offensive_phase.py` | `gk_outcome` |
| Outcome Breakdown — Long Ball | OA | Offensive Phase — GK Build-up | `components/opponent_offensive_phase.py` | `gk_outcome` |
| Positive Rate | OA | Offensive Phase — GK Build-up | `components/opponent_offensive_phase.py` | `gk_outcome` |
| GK Distribution End-Points | OA | Offensive Phase — GK Build-up | `components/opponent_offensive_phase.py` | `gk_first_receiver_zones` |
| Established Possession | OA | Offensive Phase — GK Build-up | `components/opponent_offensive_phase.py` | `gk_p1_established_possession` |
| Reached Final Third | OA | Offensive Phase — GK Build-up | `components/opponent_offensive_phase.py` | `gk_p2_reached_final_third` |
| Created a Shot | OA | Offensive Phase — GK Build-up | `components/opponent_offensive_phase.py` | `gk_p3_created_shot` |
| Possession Lost | OA | Offensive Phase — GK Build-up | `components/opponent_offensive_phase.py` | `gk_n1_possession_lost` |
| Box Entry Conceded | OA | Offensive Phase — GK Build-up | `components/opponent_offensive_phase.py` | `gk_n2_box_entry_conceded` |
| Shot Conceded | OA | Offensive Phase — GK Build-up | `components/opponent_offensive_phase.py` | `gk_n3_shot_conceded` |
| Possession % | OA | Offensive Phase — Build-up to Final Third | `components/opponent_offensive_phase.py` | `possession_pct` |
| Success Rate | OA | Offensive Phase — Build-up to Final Third | `components/opponent_offensive_phase.py` | `ft_success_rate` |
| Left Corridor | OA | Offensive Phase — Build-up to Final Third | `components/opponent_offensive_phase.py` | `ft_entry_corridor` |
| Central | OA | Offensive Phase — Build-up to Final Third | `components/opponent_offensive_phase.py` | `ft_entry_corridor` |
| Right Corridor | OA | Offensive Phase — Build-up to Final Third | `components/opponent_offensive_phase.py` | `ft_entry_corridor` |
| Opp. Box Touches | OA | Offensive Phase — Build-up to Final Third | `components/opponent_offensive_phase.py` | `opp_box_touches` |
| Opp. Box Touches / Match — League Ranking | OA | Offensive Phase — Build-up to Final Third | `components/opponent_offensive_phase.py` | `opp_box_touches` |
| Tempo | OA | Offensive Phase — Build-up to Final Third | `components/opponent_offensive_phase.py` | `tempo` |
| Top Method | OA | Offensive Phase — Build-up to Final Third | `components/opponent_offensive_phase.py` | `ft_top_method` |
| Entry Method Breakdown | OA | Offensive Phase — Build-up to Final Third | `components/opponent_offensive_phase.py` | `ft_entry_method` |
| Success Rate by Entry Method | OA | Offensive Phase — Build-up to Final Third | `components/opponent_offensive_phase.py` | `ft_success_rate` |
| Entry Timing — 15-min Bands | OA | Offensive Phase — Build-up to Final Third | `components/opponent_offensive_phase.py` | `ft_entry_timing` |
| Build-up Depth — Avg Passes Before Entry | OA | Offensive Phase — Build-up to Final Third | `components/opponent_offensive_phase.py` | `ft_build_depth` |
| FT Entry Points by Zone | OA | Offensive Phase — Build-up to Final Third | `components/opponent_offensive_phase.py` | `ft_entry_map` |
| Entry Points by Method — Season | OA | Offensive Phase — Build-up to Final Third | `components/opponent_offensive_phase.py` | `ft_entry_map` |
| Total Chances | OA | Offensive Phase — Chance Creation | `components/opponent_offensive_phase.py` | `total_shots` |
| Goals | OA | Offensive Phase — Chance Creation | `components/opponent_offensive_phase.py` | `team_goals` |
| SoT: | OA | Offensive Phase — Chance Creation | `components/opponent_offensive_phase.py` | `sot_pct` |
| xG Total | OA | Offensive Phase — Chance Creation | `components/opponent_offensive_phase.py` | `xg_total` |
| xG per Match — All Teams | OA | Offensive Phase — Chance Creation | `components/opponent_offensive_phase.py` | `xg_total` |
| Top Origin | OA | Offensive Phase — Chance Creation | `components/opponent_offensive_phase.py` | `top_origin` |
| Matches | OA | Offensive Phase — Chance Creation | `components/opponent_offensive_phase.py` | `matches_analysed` |
| Chances Created by Attack Origin | OA | Offensive Phase — Chance Creation | `components/opponent_offensive_phase.py` | `attack_origin` |
| ATTACK ORIGIN BREAKDOWN | OA | Offensive Phase — Chance Creation | `components/opponent_offensive_phase.py` | `attack_origin` |
| Set Piece | OA | Offensive Phase — Chance Creation | `components/opponent_offensive_phase.py` | `attack_origin` |
| High Regain | OA | Offensive Phase — Chance Creation | `components/opponent_offensive_phase.py` | `attack_origin` |
| Cross | OA | Offensive Phase — Chance Creation | `components/opponent_offensive_phase.py` | `attack_origin` |
| Through Ball | OA | Offensive Phase — Chance Creation | `components/opponent_offensive_phase.py` | `attack_origin` |
| Cut Back | OA | Offensive Phase — Chance Creation | `components/opponent_offensive_phase.py` | `attack_origin` |
| Individual Play | OA | Offensive Phase — Chance Creation | `components/opponent_offensive_phase.py` | `attack_origin` |
| Combination | OA | Offensive Phase — Chance Creation | `components/opponent_offensive_phase.py` | `attack_origin` |
| Conv % | OA | Offensive Phase — Chance Creation | `components/opponent_offensive_phase.py` | `origin_conversion_pct` |
| Penalty | OA | Offensive Phase — Chance Creation | `components/opponent_offensive_phase.py` | `penalty_card` |
| Goal Types — Season | OA | Offensive Phase — Chance Creation | `components/opponent_offensive_phase.py` | `goals_by_origin` |
| Attack Origin Zones | OA | Offensive Phase — Chance Creation | `components/opponent_offensive_phase.py` | `attack_origin_zones` |
| Actions / Match | OA | Defensive Phase — Defensive Pressing | `components/opp_season_pressing_cards.py` | `total_defensive_actions` |
| Defensive Actions / Match — League Comparison | OA | Defensive Phase — Defensive Pressing | `components/opp_season_pressing_cards.py` | `total_defensive_actions` |
| PPDA | OA | Defensive Phase — Defensive Pressing | `components/opp_season_pressing_cards.py` | `ppda_defensive_actions` |
| PPDA — League Comparison | OA | Defensive Phase — Defensive Pressing | `components/opp_season_pressing_cards.py` | `ppda_defensive_actions` |
| Press Success Rate | OA | Defensive Phase — Defensive Pressing | `components/opp_season_pressing_cards.py` | `press_success_rate` |
| Press Success Rate — League Comparison | OA | Defensive Phase — Defensive Pressing | `components/opp_season_pressing_cards.py` | `press_success_rate` |
| Pressing Line (median) | OA | Defensive Phase — Defensive Pressing | `components/opp_season_pressing_cards.py` | `pressing_line_median` |
| Pressing Line (Median) — League Comparison | OA | Defensive Phase — Defensive Pressing | `components/opp_season_pressing_cards.py` | `pressing_line_median` |
| Actions by Zone | OA | Defensive Phase — Defensive Pressing | `components/opp_season_pressing_cards.py` | `defensive_actions_by_third` |
| High Press | OA | Defensive Phase — Defensive Pressing | `components/opp_season_pressing_cards.py` | `defensive_actions_by_third` |
| Mid Press | OA | Defensive Phase — Defensive Pressing | `components/opp_season_pressing_cards.py` | `defensive_actions_by_third` |
| Low Block | OA | Defensive Phase — Defensive Pressing | `components/opp_season_pressing_cards.py` | `defensive_actions_by_third` |
| Own Third — League Comparison | OA | Defensive Phase — Defensive Pressing | `components/opp_season_pressing_cards.py` | `defensive_actions_by_third` |
| Middle Third — League Comparison | OA | Defensive Phase — Defensive Pressing | `components/opp_season_pressing_cards.py` | `defensive_actions_by_third` |
| Final Third — League Comparison | OA | Defensive Phase — Defensive Pressing | `components/opp_season_pressing_cards.py` | `defensive_actions_by_third` |
| Pressing Direction | OA | Defensive Phase — Defensive Pressing | `components/opp_season_pressing_cards.py` | `pressing_direction` |
| Press Success by Zone | OA | Defensive Phase — Defensive Pressing | `components/opp_season_pressing_cards.py` | `press_success_by_zone` |
| Pitch Map — Action Density & Press Outcomes | OA | Defensive Phase — Defensive Pressing | `components/opp_season_pressing_cards.py` | `defensive_action_density` |
| Def. Actions in 1st Third | OA | Defensive Phase — Defensive Castle | `components/opp_season_castle_cards.py` | `castle_actions` |
| In Own Box | OA | Defensive Phase — Defensive Castle | `components/opp_season_castle_cards.py` | `castle_in_own_box` |
| Wide Flanks | OA | Defensive Phase — Defensive Castle | `components/opp_season_castle_cards.py` | `castle_wide_flanks` |
| Def. Third Edge | OA | Defensive Phase — Defensive Castle | `components/opp_season_castle_cards.py` | `castle_def_third_edge` |
| Def. Actions / Match — League Comparison | OA | Defensive Phase — Defensive Castle | `components/opp_season_castle_cards.py` | `castle_actions` |
| In Own Box / Match — League Comparison | OA | Defensive Phase — Defensive Castle | `components/opp_season_castle_cards.py` | `castle_in_own_box` |
| Wide Flanks / Match — League Comparison | OA | Defensive Phase — Defensive Castle | `components/opp_season_castle_cards.py` | `castle_wide_flanks` |
| Def. Third Edge / Match — League Comparison | OA | Defensive Phase — Defensive Castle | `components/opp_season_castle_cards.py` | `castle_def_third_edge` |
| Actions by Type | OA | Defensive Phase — Defensive Castle | `components/opp_season_castle_cards.py` | `castle_actions_by_type` |
| Defensive Corridors | OA | Defensive Phase — Defensive Castle | `components/opp_season_castle_cards.py` | `castle_corridor` |
| Pitch Map — Zone Action Density | OA | Defensive Phase — Defensive Castle | `components/opp_season_castle_cards.py` | `castle_zone_density` |
| Clean Sheets | OA | Defensive Phase — Chances Conceded | `components/opp_season_chances_conceded_cards.py` | `clean_sheets` |
| Clean Sheets — League Comparison | OA | Defensive Phase — Chances Conceded | `components/opp_season_chances_conceded_cards.py` | `clean_sheets` |
| Shots / Match | OA | Defensive Phase — Chances Conceded | `components/opp_season_chances_conceded_cards.py` | `shots_faced` |
| On Target / Match | OA | Defensive Phase — Chances Conceded | `components/opp_season_chances_conceded_cards.py` | `on_target_conceded_per_match` |
| Goals Conceded / Match | OA | Defensive Phase — Chances Conceded | `components/opp_season_chances_conceded_cards.py` | `goals_conceded` |
| Big Chances / Match | OA | Defensive Phase — Chances Conceded | `components/opp_season_chances_conceded_cards.py` | `big_chances_conceded` |
| xG Conceded / Match | OA | Defensive Phase — Chances Conceded | `components/opp_season_chances_conceded_cards.py` | `xg_conceded` |
| Shots / Match — League Comparison | OA | Defensive Phase — Chances Conceded | `components/opp_season_chances_conceded_cards.py` | `shots_faced` |
| On Target / Match — League Comparison | OA | Defensive Phase — Chances Conceded | `components/opp_season_chances_conceded_cards.py` | `on_target_conceded_per_match` |
| Goals Conceded / Match — League Comparison | OA | Defensive Phase — Chances Conceded | `components/opp_season_chances_conceded_cards.py` | `goals_conceded` |
| Big Chances / Match — League Comparison | OA | Defensive Phase — Chances Conceded | `components/opp_season_chances_conceded_cards.py` | `big_chances_conceded` |
| xG Conceded / Match — League Comparison | OA | Defensive Phase — Chances Conceded | `components/opp_season_chances_conceded_cards.py` | `xg_conceded` |
| Origin of Chances Conceded | OA | Defensive Phase — Chances Conceded | `components/opp_season_chances_conceded_cards.py` | `attack_origin_conceded` |
| ATTACK ORIGIN BREAKDOWN | OA | Defensive Phase — Chances Conceded | `components/opp_season_chances_conceded_cards.py` | `attack_origin_conceded` |
| Penalty | OA | Defensive Phase — Chances Conceded | `components/opp_season_chances_conceded_cards.py` | `attack_origin_conceded` |
| SHOT ORIGIN ZONES — DEFENSIVE FRAME | OA | Defensive Phase — Chances Conceded | `components/opp_season_chances_conceded_cards.py` | `shot_origin_zones_defensive` |
| SHOT QUALITY TIERS CONCEDED | OA | Defensive Phase — Chances Conceded | `components/opp_season_chances_conceded_cards.py` | `shot_quality_tiers_conceded` |
| Transitions / Match | OA | Transitions — Offensive Transitions | `components/opp_season_transitions_cards.py` | `off_total_transitions` |
| Qualifying / Match | OA | Transitions — Offensive Transitions | `components/opp_season_transitions_cards.py` | `off_qualified_transitions` |
| Qualifying Rate | OA | Transitions — Offensive Transitions | `components/opp_season_transitions_cards.py` | `off_transition_rate` |
| Transitions / Match — League Comparison | OA | Transitions — Offensive Transitions | `components/opp_season_transitions_cards.py` | `off_total_transitions` |
| Qualifying Transitions / Match — League Comparison | OA | Transitions — Offensive Transitions | `components/opp_season_transitions_cards.py` | `off_qualified_transitions` |
| Qualifying Rate — League Comparison | OA | Transitions — Offensive Transitions | `components/opp_season_transitions_cards.py` | `off_transition_rate` |
| Outcome Distribution | OA | Transitions — Offensive Transitions | `components/opp_season_transitions_cards.py` | `off_qualified_transitions` |
| P1 — Sustained | OA | Transitions — Offensive Transitions | `components/opp_season_transitions_cards.py` | `off_p1_sustained` |
| P2 — Threatening | OA | Transitions — Offensive Transitions | `components/opp_season_transitions_cards.py` | `off_p2_threatening` |
| P3 — Dangerous | OA | Transitions — Offensive Transitions | `components/opp_season_transitions_cards.py` | `off_p3_dangerous` |
| Outcomes by Zone | OA | Transitions — Offensive Transitions | `components/opp_season_transitions_cards.py` | `off_outcomes_by_zone` |
| Outcomes by Corridor | OA | Transitions — Offensive Transitions | `components/opp_season_transitions_cards.py` | `off_outcomes_by_corridor` |
| Qualifying Transitions by Corridor | OA | Transitions — Offensive Transitions | `components/opp_season_transitions_cards.py` | `off_outcomes_by_corridor` |
| Pitch Map — Transition Origins Density | OA | Transitions — Offensive Transitions | `components/opp_season_transitions_cards.py` | `off_transition_origins` |
| Transitions / Match | OA | Transitions — Defensive Transitions | `components/opp_season_transitions_cards.py` | `def_total_transitions` |
| Qualifying / Match | OA | Transitions — Defensive Transitions | `components/opp_season_transitions_cards.py` | `def_qualified_transitions` |
| Qualifying Rate | OA | Transitions — Defensive Transitions | `components/opp_season_transitions_cards.py` | `def_transition_rate` |
| Transitions / Match — League Comparison | OA | Transitions — Defensive Transitions | `components/opp_season_transitions_cards.py` | `def_total_transitions` |
| Qualifying Transitions / Match — League Comparison | OA | Transitions — Defensive Transitions | `components/opp_season_transitions_cards.py` | `def_qualified_transitions` |
| Qualifying Rate — League Comparison | OA | Transitions — Defensive Transitions | `components/opp_season_transitions_cards.py` | `def_transition_rate` |
| Immediate Press | OA | Transitions — Defensive Transitions | `components/opp_season_transitions_cards.py` | `immediate_press_rate` |
| Organised Drop | OA | Transitions — Defensive Transitions | `components/opp_season_transitions_cards.py` | `organised_drop_rate` |
| Immediate Press Rate — League Comparison | OA | Transitions — Defensive Transitions | `components/opp_season_transitions_cards.py` | `immediate_press_rate` |
| Organised Drop Rate — League Comparison | OA | Transitions — Defensive Transitions | `components/opp_season_transitions_cards.py` | `organised_drop_rate` |
| Outcome Distribution | OA | Transitions — Defensive Transitions | `components/opp_season_transitions_cards.py` | `def_qualified_transitions` |
| N1 — Sustained | OA | Transitions — Defensive Transitions | `components/opp_season_transitions_cards.py` | `def_n1_sustained` |
| N2 — Threatening | OA | Transitions — Defensive Transitions | `components/opp_season_transitions_cards.py` | `def_n2_threatening` |
| N3 — Dangerous | OA | Transitions — Defensive Transitions | `components/opp_season_transitions_cards.py` | `def_n3_dangerous` |
| Outcomes by Zone | OA | Transitions — Defensive Transitions | `components/opp_season_transitions_cards.py` | `def_outcomes_by_zone` |
| Outcomes by Corridor | OA | Transitions — Defensive Transitions | `components/opp_season_transitions_cards.py` | `def_outcomes_by_corridor` |
| Qualifying Transitions by Corridor | OA | Transitions — Defensive Transitions | `components/opp_season_transitions_cards.py` | `def_outcomes_by_corridor` |
| Pitch Map — Transition Origins Density | OA | Transitions — Defensive Transitions | `components/opp_season_transitions_cards.py` | `def_transition_origins` |
| Corners / Match | OA | Set Pieces — Corner Kicks | `components/opp_season_corner_kicks_cards.py` | `corners_total` |
| Goals / Match | OA | Set Pieces — Corner Kicks | `components/opp_season_corner_kicks_cards.py` | `corner_goals` |
| % conv. | OA | Set Pieces — Corner Kicks | `components/opp_season_corner_kicks_cards.py` | `corner_conversion_rate` |
| Shots on Target / Match | OA | Set Pieces — Corner Kicks | `components/opp_season_corner_kicks_cards.py` | `corner_shots_on_target` |
| Shots off Target / Match | OA | Set Pieces — Corner Kicks | `components/opp_season_corner_kicks_cards.py` | `corner_shots_off_target` |
| Cleared / Match | OA | Set Pieces — Corner Kicks | `components/opp_season_corner_kicks_cards.py` | `corner_cleared` |
| 2nd Phase / Match | OA | Set Pieces — Corner Kicks | `components/opp_season_corner_kicks_cards.py` | `corner_second_phase` |
| Corners / Match — League Comparison | OA | Set Pieces — Corner Kicks | `components/opp_season_corner_kicks_cards.py` | `corners_total` |
| Corner Goals / Match — League Comparison | OA | Set Pieces — Corner Kicks | `components/opp_season_corner_kicks_cards.py` | `corner_goals` |
| Shots on Target / Match — League Comparison | OA | Set Pieces — Corner Kicks | `components/opp_season_corner_kicks_cards.py` | `corner_shots_on_target` |
| Shots off Target / Match — League Comparison | OA | Set Pieces — Corner Kicks | `components/opp_season_corner_kicks_cards.py` | `corner_shots_off_target` |
| Cleared / Match — League Comparison | OA | Set Pieces — Corner Kicks | `components/opp_season_corner_kicks_cards.py` | `corner_cleared` |
| 2nd Phase / Match — League Comparison | OA | Set Pieces — Corner Kicks | `components/opp_season_corner_kicks_cards.py` | `corner_second_phase` |
| Delivery Type | OA | Set Pieces — Corner Kicks | `components/opp_season_corner_kicks_cards.py` | `corner_delivery_type` |
| Delivery Maps | OA | Set Pieces — Corner Kicks | `components/opp_season_corner_kicks_cards.py` | `corner_delivery_zones` |
| Left-Side Corners | OA | Set Pieces — Corner Kicks | `components/opp_season_corner_kicks_cards.py` | `corner_delivery_zones` |
| Right-Side Corners | OA | Set Pieces — Corner Kicks | `components/opp_season_corner_kicks_cards.py` | `corner_delivery_zones` |
| Passes Completed | OA | Player Analysis | `components/opp_season_player_cards.py` | `passes_completed` |
| Pass Completion % | OA | Player Analysis | `components/opp_season_player_cards.py` | `pass_completion_pct` |
| Ball Progressions | OA | Player Analysis | `components/opp_season_player_cards.py` | `ball_progressions` |
| Line Breaks | OA | Player Analysis | `components/opp_season_player_cards.py` | `line_breaks` |
| Switches of Play | OA | Player Analysis | `components/opp_season_player_cards.py` | `switches_of_play` |
| Crosses Completed | OA | Player Analysis | `components/opp_season_player_cards.py` | `crosses_completed` |
| Take-Ons | OA | Player Analysis | `components/opp_season_player_cards.py` | `take_ons` |
| Attempts at Goal | OA | Player Analysis | `components/opp_season_player_cards.py` | `attempts_at_goal` |
| Goals | OA | Player Analysis | `components/opp_season_player_cards.py` | `player_goals` |
| Tackles Won | OA | Player Analysis | `components/opp_season_player_cards.py` | `tackles_won` |
| Tackles Made | OA | Player Analysis | `components/opp_season_player_cards.py` | `tackles_made` |
| Interceptions | OA | Player Analysis | `components/opp_season_player_cards.py` | `interceptions` |
| Blocks | OA | Player Analysis | `components/opp_season_player_cards.py` | `blocks` |
| Clearances | OA | Player Analysis | `components/opp_season_player_cards.py` | `clearances` |
| Aerial Duels Won | OA | Player Analysis | `components/opp_season_player_cards.py` | `aerial_duels_won` |
| Possession Regains | OA | Player Analysis | `components/opp_season_player_cards.py` | `possession_regains` |
| Offensive PVA | OA | Player Analysis | `components/opp_season_player_cards.py` | `offensive_pva` |
| Defensive PVA | OA | Player Analysis | `components/opp_season_player_cards.py` | `defensive_pva` |
| Total PVA | OA | Player Analysis | `components/opp_season_player_cards.py` | `total_pva` |
| PVA per 90 | OA | Player Analysis | `components/opp_season_player_cards.py` | `total_pva` |
| Adj PVA/90 | OA | Player Analysis | `components/opp_season_player_cards.py` | `total_pva` |
| Role | OA | Player Analysis | `components/opp_season_player_cards.py` | `role_group` |
| Apps | OA | Player Analysis | `components/opp_season_player_cards.py` | `appearances` |
| partial | OA | Player Analysis | `components/opp_season_player_cards.py` | `appearances` |
| Starts | OA | Player Analysis | `components/opp_season_player_cards.py` | `starts` |
| Min | OA | Player Analysis | `components/opp_season_player_cards.py` | `season_minutes` |
| low min | OA | Player Analysis | `components/opp_season_player_cards.py` | `season_minutes` |
| Min% | OA | Player Analysis | `components/opp_season_player_cards.py` | `minutes_share` |
| σ PVA | OA | Player Analysis | `components/opp_season_player_cards.py` | `pva_consistency` |
| Adj /90 | OA | Player Analysis | `components/opp_season_player_cards.py` | `adjusted_per90` |
| Raw /90 | OA | Player Analysis | `components/opp_season_player_cards.py` | `raw_per90` |
| Season % | OA | Player Analysis | `components/opp_season_player_cards.py` | `season_pct` |
| Role %ile | OA | Player Analysis | `components/opp_season_player_cards.py` | `role_percentile` |

**Explicitly unmapped (visuals without a metric of their own):**

| Label | Section | Module | Reason |
|---|---|---|---|
| Shot Map | MA | Offensive Phase — Chance Creation | Visual of individual shots (origin colour, goal markers); no own metric — covered by Total Shots, xG Total and Attack Origin Breakdown. |
| Shot Map — Defensive Half | MA | Defensive Phase — Chances Conceded | Visual of individual conceded shots; covered by Total Shots Faced and xG Against. |
| Distribution Chains | MA | Offensive Phase — Build-up from Goal Kicks | Event-chain viewer for each goal kick; illustrates Outcome Classification. |
| Delivery Chains | MA | Set Pieces — Free Kicks | Event-chain viewer for free-kick deliveries; illustrates FK delivery outcomes. |
| Possession Sequence Viewer | MA | Player Analysis | Container for the Cumulative Possession Value chart (mapped). |
| Playing Style — League Comparison (percentiles) | TO | Playing Style Wheel · Style Evolution | Modal table of the 12 wheel percentiles; each column is a mapped KPI. |

## Appendix B — Registry index

| id | Name | Sections | Status | Season aggregation | Source doc |
|---|---|---|---|---|---|
| `league_position` | Position | TO | ok | sum | — |
| `season_record` | Season Record | TO | ok | sum | — |
| `last_5_form` | Last 5 | TO | ok | sum | — |
| `goal_difference` | Goal Diff. | TO | ok | sum | — |
| `points_per_game` | PPG | TO | ok | ratio_of_sums | — |
| `mean_age` | Mean Age | TO | ok | external | — |
| `points_progression` | Points Progression | TO | ok | sum | team-overview/ppda-team-overview.md |
| `formation_times_used` | Times Used | TO | ok | sum | team-overview/formation-analysis.md |
| `formation_share` | Share | TO | ok | ratio_of_sums | team-overview/formation-analysis.md |
| `starts` | Starts | TO, OA | ok | sum | opponent-analysis/player-analysis/player-analysis.md |
| `lineup_minutes` | Minutes | TO | ok | sum | — |
| `lineup_avg_minutes` | Avg Min | TO | ok | ratio_of_sums | — |
| `goals_scored` | Goals Scored | TO | ok | sum | team-overview/goal-distribution.md |
| `goals_conceded` | Goals Conceded | TO, MA, OA | ok | total_per_match | match-analysis/defensive-phase/chance-conceded.md |
| `xg_for` | xG | TO | ok | sum | team-overview/xg-summary.md |
| `xg_against` | xGC | TO | ok | sum | team-overview/xg-summary.md |
| `goals_scored_by_interval` | Goals Scored — 15-Minute Intervals | TO | ok | sum | team-overview/goal-distribution.md |
| `goals_conceded_by_interval` | Goals Conceded — 15-Minute Intervals | TO | ok | sum | team-overview/goal-distribution.md |
| `ps_chance_prevention` | Chance Prevention | TO | ok | rank_percentile | team-overview/playing-style-wheel.md |
| `ps_defensive_intensity` | Defensive Intensity | TO | ok | rank_percentile | team-overview/playing-style-wheel.md |
| `ps_high_line` | High Line | TO | ok | rank_percentile | team-overview/playing-style-wheel.md |
| `ps_deep_buildup` | Deep Build-up | TO | ok | rank_percentile | team-overview/playing-style-wheel.md |
| `ps_press_resistance` | Press Resistance | TO | ok | rank_percentile | team-overview/playing-style-wheel.md |
| `ps_possession` | Possession | TO | pending_fix | rank_percentile | team-overview/playing-style-wheel.md |
| `ps_central_progression` | Central Progression | TO | ok | rank_percentile | team-overview/playing-style-wheel.md |
| `ps_circulate` | Circulate | TO | ok | rank_percentile | team-overview/playing-style-wheel.md |
| `ps_field_tilt` | Field Tilt | TO | ok | rank_percentile | team-overview/playing-style-wheel.md |
| `ps_chance_creation` | Chance Creation | TO | ok | rank_percentile | team-overview/playing-style-wheel.md |
| `ps_patient_attack` | Patient Attack | TO | ok | rank_percentile | team-overview/playing-style-wheel.md |
| `ps_shot_quality` | Shot Quality | TO | ok | rank_percentile | team-overview/playing-style-wheel.md |
| `ppda_team_overview` | PPDA | TO | ok | season_events | team-overview/ppda-team-overview.md |
| `ppda_rank` | PPDA Rank | TO | ok | rank_percentile | team-overview/ppda-team-overview.md |
| `field_tilt_pct` | Field Tilt % | TO | ok | ratio_of_sums | team-overview/ppda-team-overview.md |
| `pressing_tier` | Pressing Tier | TO | ok | rank_percentile | — |
| `matches_analysed` | Matches | OA | ok | sum | opponent-analysis/offensive-phase/opp-season-goalkeeper-buildup.md |
| `gk_possessions` | GK Possessions | MA, OA | ok | total_per_match | match-analysis/offensive-phase/goalkeeper-buildup.md |
| `gk_short_pct` | Short Pass % | MA, OA | ok | ratio_of_sums | match-analysis/offensive-phase/goalkeeper-buildup.md |
| `gk_long_pct` | Long Ball % | MA, OA | ok | ratio_of_sums | match-analysis/offensive-phase/goalkeeper-buildup.md |
| `gk_short_success_rate` | GK Short-Pass Success Rate | OA | ok | ratio_of_sums | opponent-analysis/offensive-phase/opp-season-goalkeeper-buildup.md |
| `gk_long_success_rate` | GK Long-Ball Success Rate | OA | ok | ratio_of_sums | opponent-analysis/offensive-phase/opp-season-goalkeeper-buildup.md |
| `gk_outcome` | Outcome Classification | MA, OA | ok | ratio_of_sums | match-analysis/offensive-phase/goalkeeper-buildup.md |
| `gk_p1_established_possession` | Established Possession | MA, OA | ok | sum | match-analysis/offensive-phase/goalkeeper-buildup.md |
| `gk_p2_reached_final_third` | Reached Final Third | MA, OA | ok | sum | match-analysis/offensive-phase/goalkeeper-buildup.md |
| `gk_p3_created_shot` | Created a Shot | MA, OA | ok | sum | match-analysis/offensive-phase/goalkeeper-buildup.md |
| `gk_n1_possession_lost` | Possession Lost | MA, OA | ok | sum | match-analysis/offensive-phase/goalkeeper-buildup.md |
| `gk_n2_box_entry_conceded` | Box Entry Conceded | MA, OA | ok | sum | match-analysis/offensive-phase/goalkeeper-buildup.md |
| `gk_n3_shot_conceded` | Shot Conceded | MA, OA | ok | sum | match-analysis/offensive-phase/goalkeeper-buildup.md |
| `gk_first_receiver_zones` | First Receiver Zone Distribution | MA, OA | ok | sum | match-analysis/offensive-phase/goalkeeper-buildup.md |
| `possession_pct` | Possession % | MA, OA | pending_fix | mean_of_match_values | match-analysis/offensive-phase/buildup-final-third.md |
| `possession_by_time_period` | POSSESSION BY TIME PERIOD | MA | ok | — | match-analysis/offensive-phase/buildup-final-third.md |
| `possession_by_pitch_area` | POSSESSION BY PITCH AREA | MA | ok | — | match-analysis/offensive-phase/buildup-final-third.md |
| `qualifying_possessions` | Qualifying Poss. | MA | ok | — | match-analysis/offensive-phase/buildup-final-third.md |
| `ft_entries_total` | Total FT Entries | MA | ok | — | match-analysis/offensive-phase/buildup-final-third.md |
| `ft_entries_qualifying` | Qual. FT Entries | MA | ok | sum | match-analysis/offensive-phase/buildup-final-third.md |
| `opp_box_touches` | Opp. Box Touches | MA, OA | ok | total_per_match | match-analysis/offensive-phase/buildup-final-third.md |
| `tempo` | Tempo | MA, OA | pending_fix | mean_of_match_values | match-analysis/offensive-phase/buildup-final-third.md |
| `ft_entry_corridor` | Entry by Corridor | MA, OA | ok | ratio_of_sums | match-analysis/offensive-phase/buildup-final-third.md |
| `ft_entry_method` | How — Entry Method | MA, OA | ok | ratio_of_sums | match-analysis/offensive-phase/buildup-final-third.md |
| `ft_top_method` | Top Method | OA | ok | ratio_of_sums | opponent-analysis/offensive-phase/opp-season-buildup-final-third.md |
| `ft_zone14` | Zone 14 | MA | ok | — | match-analysis/offensive-phase/buildup-final-third.md |
| `ft_flanks` | Flanks | MA | ok | — | match-analysis/offensive-phase/buildup-final-third.md |
| `ft_entry_outcome` | Entry Outcomes (Positive / Negative) | MA | ok | — | match-analysis/offensive-phase/buildup-final-third.md |
| `ft_success_rate` | Success Rate | OA | ok | ratio_of_sums | opponent-analysis/offensive-phase/opp-season-buildup-final-third.md |
| `ft_entry_timing` | Entry Timing — 15-min Bands | OA | ok | ratio_of_sums | opponent-analysis/offensive-phase/opp-season-buildup-final-third.md |
| `ft_build_depth` | Build-up Depth — Avg Passes Before Entry | OA | ok | ratio_of_sums | opponent-analysis/offensive-phase/opp-season-buildup-final-third.md |
| `ft_entry_map` | FT Entry Zones & Outcomes | MA, OA | ok | sum | match-analysis/offensive-phase/buildup-final-third.md |
| `total_shots` | Total Shots | MA, OA | ok | total_per_match | match-analysis/offensive-phase/chance-creation.md |
| `shots_in_box` | In-Box | MA | ok | — | match-analysis/offensive-phase/chance-creation.md |
| `shots_out_box` | Out-Box | MA | ok | — | match-analysis/offensive-phase/chance-creation.md |
| `sot_pct` | SoT % | MA, OA | ok | ratio_of_sums | match-analysis/offensive-phase/chance-creation.md |
| `xg_total` | xG Total | MA, OA | ok | total_per_match | match-analysis/offensive-phase/chance-creation.md |
| `xg_per_shot` | xG/Shot | MA | ok | — | match-analysis/offensive-phase/chance-creation.md |
| `team_goals` | Goals | MA, OA | ok | sum | match-analysis/offensive-phase/chance-creation.md |
| `chain_to_goal_matrix` | Chain-to-Goal Matrix | MA | ok | — | match-analysis/offensive-phase/chance-creation.md |
| `attack_origin` | Attack Origin Breakdown | MA, OA | ok | sum | models/attack-origin-classification.md |
| `penalty_card` | Penalty | MA, OA | ok | ratio_of_sums | models/attack-origin-classification.md |
| `shot_quality_tiers` | Shot Quality Tiers | MA | ok | — | models/shot-quality-tiers.md |
| `xg_by_origin` | xG by Attack Origin | MA | ok | — | match-analysis/offensive-phase/chance-creation.md |
| `attack_origin_zones` | Attack Origin Zones | MA, OA | ok | sum | match-analysis/offensive-phase/chance-creation.md |
| `top_origin` | Top Origin | OA | ok | sum | opponent-analysis/offensive-phase/opp-season-chance-creation.md |
| `origin_conversion_pct` | Conv % | OA | ok | ratio_of_sums | opponent-analysis/offensive-phase/opp-season-chance-creation.md |
| `goals_by_origin` | Goal Types — Season | OA | ok | sum | opponent-analysis/offensive-phase/opp-season-chance-creation.md |
| `total_defensive_actions` | Total Defensive Actions | MA, OA | ok | total_per_match | match-analysis/defensive-phase/defensive-pressing.md |
| `ppda_final_third` | PPDA (Final Third) | MA | ok | — | match-analysis/defensive-phase/defensive-pressing.md |
| `ppda_defensive_actions` | PPDA | OA | ok | ratio_of_sums | opponent-analysis/defensive-phase/opp-season-defensive-pressing.md |
| `press_success_rate` | Press Success Rate | MA, OA | ok | ratio_of_sums | match-analysis/defensive-phase/defensive-pressing.md |
| `offsides_provoked` | Offsides Provoked | MA | ok | — | match-analysis/other/defensive-structure.md |
| `offside_line_median` | Offside Line (median) | MA | ok | — | match-analysis/other/defensive-structure.md |
| `pressing_line_median` | Pressing Line (median) | MA, OA | ok | median_of_match_values | match-analysis/defensive-phase/defensive-pressing.md |
| `defensive_actions_by_third` | Defensive Actions | MA, OA | ok | ratio_of_sums | match-analysis/defensive-phase/defensive-pressing.md |
| `pressing_direction` | Pressing Direction | MA, OA | ok | ratio_of_sums | match-analysis/defensive-phase/defensive-pressing.md |
| `press_success_by_zone` | Pressing Success by Zone | MA, OA | ok | ratio_of_sums | match-analysis/defensive-phase/defensive-pressing.md |
| `defensive_action_density` | Action Density + Press Outcomes | MA, OA | ok | sum | match-analysis/defensive-phase/defensive-pressing.md |
| `defensive_actions_by_type` | Defensive Actions by Type | MA | ok | — | match-analysis/defensive-phase/defensive-pressing.md |
| `castle_actions` | Def. Actions in 1st Third | MA, OA | ok | total_per_match | match-analysis/defensive-phase/defensive-castle.md |
| `castle_in_own_box` | In Own Box | MA, OA | ok | total_per_match | match-analysis/defensive-phase/defensive-castle.md |
| `castle_wide_flanks` | Wide Flanks | MA, OA | ok | total_per_match | match-analysis/defensive-phase/defensive-castle.md |
| `castle_def_third_edge` | Def. Third Edge | MA, OA | ok | total_per_match | match-analysis/defensive-phase/defensive-castle.md |
| `castle_actions_by_type` | Actions by Type | MA, OA | ok | sum | match-analysis/defensive-phase/defensive-castle.md |
| `castle_corridor` | Defensive Corridor | MA, OA | ok | ratio_of_sums | match-analysis/defensive-phase/defensive-castle.md |
| `castle_zone_density` | Zone Action Density — Defensive Third | MA, OA | ok | sum | match-analysis/defensive-phase/defensive-castle.md |
| `shots_faced` | Total Shots Faced | MA, OA | ok | total_per_match | match-analysis/defensive-phase/chance-conceded.md |
| `shots_faced_in_box` | In-Box | MA | ok | — | match-analysis/defensive-phase/chance-conceded.md |
| `shots_faced_out_box` | Out-Box | MA | ok | — | match-analysis/defensive-phase/chance-conceded.md |
| `sot_faced_pct` | SoT Faced % | MA | ok | — | match-analysis/defensive-phase/chance-conceded.md |
| `on_target_conceded_per_match` | On Target / Match | OA | ok | total_per_match | opponent-analysis/defensive-phase/opp-season-chances-conceded.md |
| `xg_conceded` | xG Against | MA, OA | ok | total_per_match | match-analysis/defensive-phase/chance-conceded.md |
| `big_chances_conceded` | Big chances | MA, OA | ok | total_per_match | match-analysis/defensive-phase/chance-conceded.md |
| `chain_to_concede_matrix` | Chain-to-Concede Matrix | MA | ok | — | match-analysis/defensive-phase/chance-conceded.md |
| `attack_origin_conceded` | Attack Origin Breakdown | MA, OA | ok | sum | models/attack-origin-classification.md |
| `xg_against_by_origin` | xG Against by Attack Origin | MA | ok | — | match-analysis/defensive-phase/chance-conceded.md |
| `shot_origin_zones_defensive` | Shot Origin Zones — Defensive Frame | MA, OA | ok | sum | match-analysis/defensive-phase/chance-conceded.md |
| `shot_quality_tiers_conceded` | Shot Quality Tiers Conceded | MA, OA | ok | ratio_of_sums | models/shot-quality-tiers.md |
| `clean_sheets` | Clean Sheets | OA | ok | sum | opponent-analysis/defensive-phase/opp-season-chances-conceded.md |
| `off_total_transitions` | Total Transitions | MA, OA | ok | total_per_match | match-analysis/transitions/offensive-transitions.md |
| `off_qualified_transitions` | Qualified Transitions | MA, OA | ok | total_per_match | match-analysis/transitions/offensive-transitions.md |
| `off_transition_rate` | Transition Rate | MA, OA | ok | ratio_of_sums | match-analysis/transitions/offensive-transitions.md |
| `off_p1_sustained` | P1 — Sustained | MA, OA | ok | sum | match-analysis/transitions/offensive-transitions.md |
| `off_p2_threatening` | P2 — Threatening | MA, OA | ok | sum | match-analysis/transitions/offensive-transitions.md |
| `off_p3_dangerous` | P3 — Dangerous | MA, OA | ok | sum | match-analysis/transitions/offensive-transitions.md |
| `off_outcomes_by_zone` | Outcomes by Zone | MA, OA | ok | sum | match-analysis/transitions/offensive-transitions.md |
| `off_outcomes_by_corridor` | Outcomes by Corridor | MA, OA | ok | sum | match-analysis/transitions/offensive-transitions.md |
| `off_transition_origins` | Offensive Transition Origins (Qualified · Own Half) | MA, OA | ok | sum | opponent-analysis/transitions/opp-season-offensive-transitions.md |
| `def_total_transitions` | Total Transitions | MA, OA | ok | total_per_match | match-analysis/transitions/defensive-transitions.md |
| `def_qualified_transitions` | Qualified Transitions | MA, OA | ok | total_per_match | match-analysis/transitions/defensive-transitions.md |
| `def_transition_rate` | Transition Rate | MA, OA | ok | ratio_of_sums | match-analysis/transitions/defensive-transitions.md |
| `def_n1_sustained` | N1 — Sustained | MA, OA | ok | sum | match-analysis/transitions/defensive-transitions.md |
| `def_n2_threatening` | N2 — Threatening | MA, OA | ok | sum | match-analysis/transitions/defensive-transitions.md |
| `def_n3_dangerous` | N3 — Dangerous | MA, OA | ok | sum | match-analysis/transitions/defensive-transitions.md |
| `immediate_press_rate` | Immediate Press ≤5s | MA, OA | pending_fix | mean_of_match_values | match-analysis/transitions/defensive-transitions.md |
| `organised_drop_rate` | Organised Drop >10s | MA, OA | pending_fix | mean_of_match_values | match-analysis/transitions/defensive-transitions.md |
| `def_outcomes_by_zone` | Outcomes by Zone | MA, OA | ok | sum | match-analysis/transitions/defensive-transitions.md |
| `def_outcomes_by_corridor` | Outcomes by Corridor | MA, OA | ok | sum | match-analysis/transitions/defensive-transitions.md |
| `def_transition_origins` | Transition Loss Origins (Qualified · Middle + Attacking Third) | MA, OA | ok | sum | opponent-analysis/transitions/opp-season-defensive-transitions.md |
| `corners_total` | Total Corners | MA, OA | ok | total_per_match | match-analysis/set-pieces/corner-kicks.md |
| `corner_goals` | Goals | MA, OA | ok | total_per_match | match-analysis/set-pieces/corner-kicks.md |
| `corner_conversion_rate` | % conv. | OA | ok | ratio_of_sums | opponent-analysis/set-pieces/opp-season-corner-kicks.md |
| `corner_shots_on_target` | Shots on Target | MA, OA | ok | total_per_match | match-analysis/set-pieces/corner-kicks.md |
| `corner_shots_off_target` | Shots off Target | MA, OA | ok | total_per_match | match-analysis/set-pieces/corner-kicks.md |
| `corner_cleared` | Cleared | MA, OA | ok | total_per_match | match-analysis/set-pieces/corner-kicks.md |
| `corner_second_phase` | 2nd Phase | MA, OA | ok | total_per_match | match-analysis/set-pieces/corner-kicks.md |
| `corner_delivery_type` | Delivery Type | MA, OA | ok | ratio_of_sums | match-analysis/set-pieces/corner-kicks.md |
| `corner_delivery_zones` | Delivery Maps | MA, OA | ok | sum | match-analysis/set-pieces/corner-kicks.md |
| `fk_total_deliveries` | Total Deliveries | MA | ok | — | match-analysis/set-pieces/free-kicks.md |
| `fk_delivery_outcomes` | FK Deliveries — Volume & Outcomes | MA | ok | — | match-analysis/set-pieces/free-kicks.md |
| `fk_delivery_type` | Delivery Type | MA | ok | — | match-analysis/set-pieces/free-kicks.md |
| `fk_total_shots` | Total FK Shots | MA | ok | — | match-analysis/set-pieces/free-kicks.md |
| `fk_direct_shot_outcomes` | Direct FK Shots — Volume & Outcomes | MA | ok | — | match-analysis/set-pieces/free-kicks.md |
| `offensive_pva` | Offensive PVA | MA, OA | ok | shrinkage_adjusted | models/possession-value-model.md |
| `defensive_pva` | Defensive PVA | MA, OA | ok | shrinkage_adjusted | models/possession-value-model.md |
| `total_pva` | Total PVA | MA, OA | ok | shrinkage_adjusted | models/possession-value-model.md |
| `cumulative_possession_value` | Cumulative Possession Value | MA | ok | — | models/possession-value-model.md |
| `passes_completed` | Passes Completed | MA, OA | ok | shrinkage_adjusted | opponent-analysis/player-analysis/player-analysis.md |
| `pass_completion_pct` | Pass Completion % | MA, OA | ok | ratio_of_sums | opponent-analysis/player-analysis/player-analysis.md |
| `ball_progressions` | Ball Progressions | MA, OA | ok | shrinkage_adjusted | opponent-analysis/player-analysis/player-analysis.md |
| `line_breaks` | Line Breaks | MA, OA | ok | shrinkage_adjusted | opponent-analysis/player-analysis/player-analysis.md |
| `switches_of_play` | Switches of Play | MA, OA | ok | shrinkage_adjusted | opponent-analysis/player-analysis/player-analysis.md |
| `crosses_completed` | Crosses Completed | MA, OA | ok | shrinkage_adjusted | opponent-analysis/player-analysis/player-analysis.md |
| `take_ons` | Take-Ons | MA, OA | ok | shrinkage_adjusted | opponent-analysis/player-analysis/player-analysis.md |
| `attempts_at_goal` | Attempts at Goal | MA, OA | ok | shrinkage_adjusted | opponent-analysis/player-analysis/player-analysis.md |
| `player_goals` | Goals | MA, OA | ok | shrinkage_adjusted | opponent-analysis/player-analysis/player-analysis.md |
| `tackles_won` | Tackles Won | MA, OA | ok | shrinkage_adjusted | opponent-analysis/player-analysis/player-analysis.md |
| `tackles_made` | Tackles Made | MA, OA | ok | shrinkage_adjusted | opponent-analysis/player-analysis/player-analysis.md |
| `interceptions` | Interceptions | MA, OA | ok | shrinkage_adjusted | opponent-analysis/player-analysis/player-analysis.md |
| `blocks` | Blocks | MA, OA | ok | shrinkage_adjusted | opponent-analysis/player-analysis/player-analysis.md |
| `clearances` | Clearances | MA, OA | ok | shrinkage_adjusted | opponent-analysis/player-analysis/player-analysis.md |
| `aerial_duels_won` | Aerial Duels Won | MA, OA | ok | shrinkage_adjusted | opponent-analysis/player-analysis/player-analysis.md |
| `possession_regains` | Possession Regains | MA, OA | ok | shrinkage_adjusted | opponent-analysis/player-analysis/player-analysis.md |
| `role_group` | Role | OA | ok | sum | opponent-analysis/player-analysis/player-analysis.md |
| `appearances` | Apps | OA | ok | sum | opponent-analysis/player-analysis/player-analysis.md |
| `season_minutes` | Min | MA, OA | ok | sum | opponent-analysis/player-analysis/player-analysis.md |
| `minutes_share` | Min% | OA | ok | ratio_of_sums | opponent-analysis/player-analysis/player-analysis.md |
| `pva_consistency` | σ PVA | OA | ok | sum | opponent-analysis/player-analysis/player-analysis.md |
| `adjusted_per90` | Adj /90 | OA | ok | shrinkage_adjusted | opponent-analysis/player-analysis/player-analysis.md |
| `raw_per90` | Raw /90 | OA | ok | ratio_of_sums | opponent-analysis/player-analysis/player-analysis.md |
| `season_pct` | Season % | OA | ok | ratio_of_sums | opponent-analysis/player-analysis/player-analysis.md |
| `role_percentile` | Role %ile | OA | ok | rank_percentile | opponent-analysis/player-analysis/player-analysis.md |
