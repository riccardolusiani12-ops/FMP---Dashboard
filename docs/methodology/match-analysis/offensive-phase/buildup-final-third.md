# Build-up to Final Third — Methodology

> **Dashboard location:** Match Analysis → Offensive Phase → Build-up to Final Third
> **Analysis type:** Match-level
> **Primary source file(s):** `analytics/final_third.py` (`analyse_final_third`, `detect_ft_entries`, `_classify_ft_method`, `compute_tempo_metrics`); supporting `analytics/general_buildup.py` (`build_possessions`); UI `components/final_third_cards.py`, `final_third_pitch.py`
> **Precomputed parquet(s):** None per match (season aggregate: [opp-season-buildup-final-third.md](../../opponent-analysis/offensive-phase/opp-season-buildup-final-third.md)).
> **Last reviewed:** 2026-06-24
>
> *§2-standard methodology; the legacy `BUILDUP_TO_FINAL_THIRD_METHODOLOGY.md` is retained as a narrative record.*

---

## 1 — Purpose

This component measures how a team progresses the ball from build-up into the attacking final third: how often it enters, by which method (carry, through ball, cross, switch, long ball, transition, etc.), through which corridor, how patiently (tempo), and with what success once inside. It profiles a team's build-up identity and its effectiveness at breaking into dangerous areas.

---

## 2 — Input Data

- **Event types used:** open-play possession events (from `build_possessions`), passes, carries, recoveries; full match df for outcome lookup.
- **Qualifiers used:** `Through ball` (F3 #4), `Switch of play` (F3 #196), `Cross` (F3 #2), `Long ball` (F3 #1) / `Length`, set-piece origins.
- **Coordinate system:** Opta normalised (0–100). **Final-third line `FT_X_THRESHOLD = 66.67`**; entry = a possession crossing from `x < 66.67` to `x ≥ 66.67`. Corridors: Left (`y > 66.67`), Right (`y < 33.33`), Centre otherwise. Central danger zone Z14; box `x ≥ 83.33`.
- **Seasons covered:** any match with a CSV.
- **Scope:** per-match only.

---

## 3 — Methodology

### 3.1 — Possession sequences (`build_possessions`)
Events are segmented into possessions with an origin label (open play / set-piece type). Only the analysed team's open-play possessions are considered for entries; tempo additionally filters to "qualifying" possessions ≥10 s.

### 3.2 — Final-third entry detection (`detect_ft_entries`)
For each possession, find the first play event; if it already starts in the final third (`x ≥ 66.67`) the possession is skipped (no "entry"). Otherwise the moment the ball crosses the line is recorded as an entry, along with the pass chain leading up to it (for method classification), the entry coordinates, corridor, length, and elapsed time.

### 3.3 — Entry-method classification (`_classify_ft_method`) — priority order
First match wins:
1. **transition_recovery** — possession started from a defensive recovery (ball recovery / interception / tackle) in the own half (`poss_start_x ≤ 50`) and the final third is reached within 15 s.
2. **through_ball** — `Through ball` (F3 #4) on the entry event or any of the last 3 passes.
3. **switch_of_play** — `Switch of play` (F3 #196) on the entry event or last 3 passes.
4. **set_piece** — set-piece restart played *directly* into the final third (`passes_before_count == 0`).
5a. **cross_delivery** — `Cross` (F3 #2) qualifier (evaluated before distance so a long cross stays a cross).
5b. **long_ball** — `Long ball` qualifier or `Length ≥ LONG_PASS_DISTANCE` (1-pass window).
6. **individual_carry** — the same player carried/dribbled across the line.
7. **short_pass** *(default)* — patient build-up, including one-two/combination patterns.

### 3.4 — Corridor & post-entry analysis
Each entry is tagged L/C/R by `entry_y`. Post-entry analysis (`analyse_post_ft_zones`) tracks whether the possession reached the central danger zone (Z14), the wide channels (flanks), the box, and whether the outcome was positive/negative.

### 3.5 — Tempo (`compute_tempo_metrics`)
Over qualifying possessions (≥10 s), tempo = **passes per minute**: total passes ÷ active duration (minutes between first and last qualifying pass). Also computed per 15-minute window (`tempo_windows`).

### 3.6 — Box touches & aggregate metrics (`compute_ft_metrics`)
Counts entries, entry rate, method distribution, corridor distribution, z14/flank reach, positive/negative outcome split, average passes and seconds to entry, possession %, and opposition box touches.

---

## 4 — Key Metrics & Definitions

- **FT entries (total) & entry rate:** number of possessions crossing `x = 66.67`, and as a rate.
- **Entry-method distribution:** counts/percentages across the 7 methods (§3.3).
- **Corridor distribution:** L/C/R share of entries.
- **Z14 reach / flank reach:** share of entries that reached the central danger zone / wide channels.
- **Tempo (passes/min):** pass rate in qualifying (≥10 s) possessions, overall and per 15-min window.
- **Avg passes / seconds to entry:** build-up directness.
- **Possession %:** team's share of possession.
- **Box touches:** touches in the opponent box.
- **Outcome (positive/negative):** whether the final-third possession was constructive.

---

## 5 — Outputs

- **`metrics` dict** (`analyse_final_third`): `total_ft_entries`, `corridor_counts`/`pcts`, `method_counts`/`pcts`, `zone_reach` (z14, flanks), `outcomes` (positive/negative), `avg_passes_before_entry`, `avg_seconds_to_entry`, `possession_pct`, plus tempo and box-touch metrics.
- **Visual outputs:** zone-entry pitch map (18-zone), entry-method breakdown, corridor distribution, tempo card/windows.
- **No parquet** — live per match. (Also consumed by the defensive "structural mirror", [defensive-structure.md](../other/defensive-structure.md).)

---

## 6 — Methodological Decisions & Rationale

- **`x = 66.67` entry line:** the standard final-third boundary; an "entry" is the crossing event, so a possession already in the final third is not double-counted.
- **Priority-ordered method classification:** first-party qualifiers (through ball, switch, cross, long ball) outrank heuristics, and transition is checked first because a fast recovery-to-final-third counts as a transition regardless of the entry pass type.
- **Set-piece method only when direct (`passes_before_count == 0`):** a set piece built through several passes into the final third is open-play progression, not a set-piece entry.
- **Tempo on qualifying (≥10 s) possessions:** excludes one-touch clearances and broken sequences so passes/min reflects genuine build-up, not noise.
- **Last-3-pass window for through-ball/switch:** captures continuation passes immediately after the defining action so the method survives a short relay.

---

## 7 — Limitations & Known Issues

- **Entry counts the first crossing only:** re-entries within the same possession after dropping out are not separately counted.
- **Method heuristics inherit qualifier gaps:** missing Cross/Long ball/Length tags can shift an entry into the `short_pass` default.
- **Tempo duration is event-bounded:** active duration uses first/last qualifying pass times, approximating possession time.
- **Spec note:** the audit brief listed "9 methods"; the implementation uses **7** (§3.3). Code wins.

---

## 8 — Relationship to Other Components

- **Upstream:** `general_buildup.build_possessions`, the 18-zone grid, `team_mapping.canonical_name()`.
- **Downstream:** `components/final_third_cards.py` / `final_third_pitch.py`; the defensive structural mirror ([defensive-structure.md](../other/defensive-structure.md)); season aggregate [opp-season-buildup-final-third.md](../../opponent-analysis/offensive-phase/opp-season-buildup-final-third.md).
