# Offensive Phase Analytics — Final Methodology

> **Last updated:** 28 April 2026 — PV row removed from Chain-to-Goal Matrix dashboard display (model kept; chain-to-goal matrix now shows N, xG, SoT%, GS only).

## Overview

The Offensive Phase is divided into **two sequential build-up stages** that track how a team progresses the ball from its own goal-line all the way into the opponent's final third. Each stage has dedicated analytics, outcome rules and dashboard sections.

| Stage | Module | Card title |
|-------|--------|------------|
| **Phase 1** — Build-up from Goalkeeper | `goalkeeper_buildup.py` | *GK Build-up (Goal Kicks)* |
| **Phase 2** — Build-up to Final Third | `final_third.py` | *Build-up to Final Third* |
| **Phase 3** — Chance Creation | `chance_creation.py` | *Chance Creation* |

A supporting **General Build-up** module (`general_buildup.py`) provides an open-play-only view with a simpler 6-category progression taxonomy. Phase 2 extends this with a richer 9-method classification, corridor analysis, post-entry zone reach, pitch visualisations and full outcome breakdowns. Phase 3 picks up from there — analysing how the entries that reached the final third materialise into shots, classifying the attack origin of each shot, and quantifying quality through xG and SoT% in the Chain-to-Goal Matrix.

---
---

# PHASE 1: BUILD-UP FROM GOALKEEPER (Goal Kick Analysis)

## Purpose

Analyse how effectively a team distributes the ball from goal kicks — the very first touch of the offensive phase.

**Code:** `dash_app/src/analytics/goalkeeper_buildup.py`
**UI:** `dash_app/src/components/buildup_cards.py`

---

## 1. Pitch Grid (18 Zones)

All zone references in the Offensive Phase use a shared 18-zone model based on the Opta 0–100 coordinate system:

```
   Z16  Z17  Z18     ← Opponent box      (x: 83.33–100)
   Z13  Z14  Z15     ← Attacking third    (x: 66.67–83.33)
   Z10  Z11  Z12     ← Upper middle third (x: 50–66.67)
    Z7   Z8   Z9     ← Lower middle third (x: 33.33–50)
    Z4   Z5   Z6     ← Defensive third    (x: 16.67–33.33)
    Z1   Z2   Z3     ← Own box            (x: 0–16.67)
```

**Formula:** `zone = row × 3 + col + 1` where `row = min(⌊x / 16.67⌋, 5)` and `col = min(⌊y / 33.33⌋, 2)`.

Opta axes: x = 0 at the team's own goal-line, x = 100 at the opponent's goal-line; y = 0 at the right touchline (broadcast view), y = 100 at the left touchline.

---

## 2. Goal Kick Detection

A goal kick is identified when the Opta `Goal Kick` qualifier column has the value `"Si"`. The taker can be the goalkeeper or any defender positioned in the goal area.

---

## 3. Distribution Type: Short vs Long

| Type | Condition | Meaning |
|------|-----------|---------|
| **Short** | First receiver in zones 1–6 (x ≤ 33.33) | Building patiently from deep |
| **Long** | First receiver in zones 7–18 (x > 33.33) | Direct distribution bypassing midfield |

**First-receiver identification:** the algorithm scans up to 20 subsequent events for the first teammate touch. If an interception by the opposition is found first, the outcome is immediately classified as negative.

**Output:** `short_count`, `long_count`, `short_pct`, `long_pct`.

---

## 4. Receiving Zone

The zone of the first receiver is recorded to reveal distribution patterns (central vs wide, deep vs progressive).

**Output:** `zone_counts` — frequency per zone; `zone_outcomes` — positive/negative split per zone.

---

## 5. Outcome Rules (15-Second Window)

| Outcome | Criteria |
|---------|----------|
| **Positive** | Team retains possession for ≥ 15 seconds from the first receiver's touch, **OR** a favourable event occurs within 15 s (foul won, ball out in team's favour, no interception) |
| **Negative** | Opposition gains possession within the 15-second window (interception, tackle, opponent touch) |

**Why 15 seconds?** Goal kicks are slow-developing plays; 15 s allows 2–3 passes and gives enough time to escape immediate pressing. Most goal-kick sequences succeed or fail within this window.

---

## 6. Data Flow

```
Raw CSV  →  Goal Kick Detection (Goal Kick == "Si")
         →  First Receiver Identification (next 20 events)
         →  Zone Classification (x, y → zone 1–18)
         →  Short / Long Classification
         →  Outcome Classification (15 s window)
         →  Aggregation
```

---

## 7. Reading the GK Build-up Card — Example

```
Total Goal Kicks: 15
  Short: 9 (60%)  ·  Long: 6 (40%)

Zone Distribution:
  Z5 (def. centre):  4   Z8 (midfield):  3   Z2 (own box left): 2

Outcomes:
  Positive: 10 (67%)  ·  Negative: 5 (33%)
```

**Interpretation:** the team prefers short distributions (60 %), mainly targeting the centre of the defensive third (Z5) and midfield (Z8). A 67 % positive rate indicates effective GK distribution above the typical Serie A average.

---
---

# PHASE 2: BUILD-UP TO FINAL THIRD

## Purpose

Analyse how a team progresses the ball from its own half into the opponent's final third during a match — covering frequency, corridor, method, zone reach, and outcomes.

**Code:** `dash_app/src/analytics/final_third.py`
**UI card:** `dash_app/src/components/final_third_cards.py`
**Pitch visuals:** `dash_app/src/components/final_third_pitch.py`

---

## 1. Core Definitions

| Concept | Value | Source |
|---------|-------|--------|
| Final-third threshold | `x ≥ 66.67` | Opta 0–100 scale (≈ 70 m on a 105 m pitch) |
| Qualifying possession | duration ≥ 10 s | Filters rapid turnovers |
| Left corridor | `y > 66.67` | High y = left touchline (broadcast view) |
| Centre corridor | `33.33 ≤ y ≤ 66.67` | |
| Right corridor | `y < 33.33` | Low y = right touchline |
| Opposition box | `x ≥ 83.33`, `21 ≤ y ≤ 79` | Penalty-area approximation |

---

## 2. Possession Chains

A possession is a continuous sequence of events by one team. A **new** possession starts when:

- The ball-possessing team changes
- The period changes
- A goal is scored
- A set-piece restart occurs (corner, free kick, throw-in, goal kick, penalty)

Each possession receives a `poss_id` and a `poss_origin` (open play, corner, free kick, etc.). Only possessions lasting **≥ 10 seconds** are classified as *qualifying*.

---

## 3. Opta Data Foundations

### 3a. F1 — Event Types Used

| ID | Event | Role |
|----|-------|------|
| 1 | **Pass** | Main entry-detection event (via pass endpoint) and pass-chain tracking |
| 2 | **Offside Pass** | Treated identically to Pass for entry detection |
| 3 | **Take On** | Carry-based FT entry (same player, x crosses threshold) |
| 4 | **Foul** | Outcome: opponent foul → positive; team foul → negative |
| 6 | **Corner Awarded** | Immediate positive outcome |
| 7 | **Tackle** | Possession origin for `transition_recovery` |
| 8 | **Interception** | Possession origin for `transition_recovery` |
| 13 | **Miss** | Shot → immediate positive |
| 14 | **Post** | Shot → immediate positive |
| 15 | **Saved Shot** | Shot → immediate positive |
| 16 | **Goal** | Immediate positive; also breaks possession chain |
| 44 | **Aerial** | Excluded from box-touch count |
| 49 | **Ball Recovery** | Possession origin for `transition_recovery` |
| 50 | **Dispossessed** | Play event for possession boundaries |
| 61 | **Ball Touch** | Carry-based FT entry (same player, x crosses threshold) |
| 74 | **Blocked Pass** | Treated identically to Pass for entry detection |

### 3b. F3 — Qualifier Types Used

| ID | Qualifier | Usage |
|----|-----------|-------|
| **1** | Long ball | Method classifier: `long_ball` (or `Length ≥ 32`) |
| **2** | Cross | Method classifier: `cross` (priority 3) |
| **3** | Head pass | Stored as `head_pass_flag` per entry |
| **4** | Through ball | Method classifier: `through_ball` (highest priority) |
| **5** | Free kick taken | Possession origin → `free_kick` |
| **6** | Corner taken | Possession origin → `corner` |
| **9** | Penalty | Outcome (positive) and set-piece origin |
| **106** | Attacking Pass | Stored as `attacking_pass_flag` |
| **107** | Throw In | Possession origin → `throw_in` |
| **124** | Goal Kick | Possession origin → `goal_kick` |
| **140 / 141** | Pass End X / Y | Core to entry detection (`pass_end_x ≥ 66.67`) |
| **155** | Chipped | Stored as `chipped_flag` |
| **156** | Lay-off | Stored as `lay_off_flag` |
| **157** | Launch | Stored as `launch_flag` |
| **168** | Flick-on | Stored as `flick_on_flag` |
| **195** | Pull Back | Stored as `pull_back_flag` |
| **196** | Switch of play | Method classifier: `switch_of_play` (priority 2) |
| **210** | Assist | Stored as `assist` flag |
| **212** | Length | Fallback for `long_ball` when flag is absent |
| **213** | Angle | Loaded; available for future analysis |
| **214** | Big Chance | Stored as `big_chance` flag |
| **215** | Individual Play | Stored as `individual_play` flag |

---

## 4. Data Pipeline

```
Raw CSV (Opta F1 / F3 events)
    │
    ▼
1.  _load_match_events()             — load CSV, parse types
    │
    ▼
2.  Apply _QUALIFIER_RENAMES         — snake_case qualifier columns
    │
    ▼
3.  build_possessions()              — assign poss_id, poss_origin, _match_sec
    │
    ▼
4.  Filter to selected team
    │
    ▼
5.  build_possession_stats()         — possession %, qualifying count
    │
    ▼
6.  detect_ft_entries()              — scan each qualifying possession for
    │                                  x crossing from < 66.67 to ≥ 66.67
    │                                  (via pass endpoint OR carry by same player)
    │
    ▼
7.  _classify_ft_method()            — priority-based method (§5)
    │
    ▼
8.  _classify_outcome()              — scan forward events (§7)
    │
    ▼
9.  analyse_post_ft_zones()          — 10 s window post-entry (§6)
    │
    ▼
10. count_box_touches()              — all team touches in opp. box
    │
    ▼
11. compute_ft_metrics()             — aggregate everything into KPIs
```

---

## 5. Entry Method Classification (Priority Order)

Each entry is assigned **exactly one** method. The algorithm checks the following rules from top to bottom — first match wins.

> **Special case — High Regain:** This is the only method where the ball does *not* cross the FT line — it is *already* in the FT when won back. It is detected separately and pre-classified at detection time, bypassing the priority chain below.

| Priority | Method | Detection Rule | Description |
|----------|--------|---------------|--------------|
| ★ | **High Regain** | Ball recovery / interception / successful tackle with `x ≥ 66.67`, open play only. First play event of the possession. | Ball won back directly inside the final third |
| 1 | **Transition / Recovery** | Ball won back via recovery / interception / tackle in the **own 1st third** (`x ≤ 33.33`) **and** FT reached within 8 s | Wins regardless of how the ball is progressed (long ball, carry, passes) |
| 2 | **Through Ball** | F3 #4 qualifier on the entry pass **or** last pass in the chain | Penetrative pass splitting the defence |
| 3 | **Switch of Play** | F3 #196 qualifier on entry pass or last pass | Lateral pass changing the point of attack |
| 4 | **Set-Piece** | Possession origin is a set-piece **and** `passes_before_count == 0` (the restart pass itself crosses the FT line — no intermediate touches in own half) | Set-piece played directly into the final third |
| 5 | **Long Ball** | F3 #1 qualifier **or** `Length ≥ 32` on entry or last pass **or** F3 #2 cross qualifier (a cross from outside the FT is a direct/aerial ball) | Direct pass over 32 m, aerial ball, or cross from own half |
| 6 | **Individual Carry** | Same player carries/dribbles across the FT line (ball touch / take on) | Dribble or run with the ball into FT |
| 7 | **Short Pass** | Default — none of the above matched | Patient build-up with ≥ 5 passes (includes one-two / give-and-go patterns) |

### Design Rationale

- **High Regain is a special / exception method.** Unlike the others, the ball is already inside the FT. It is detected independently (possessions whose first play event is a recovery-type at x ≥ 66.67) and is not subject to the priority chain. This ensures that a high-press ball recovery is never mis-classified as Short Pass or Transition.
- **Transition first (among standard entries):** A counter-attack launched from the own third is the dominant tactical identity of the sequence, regardless of the delivery method used to reach the FT.
- **Cross → Long Ball:** Crosses recorded inside a match almost always originate from *within* the final third. A cross-qualifier event whose origin is *outside* the FT (x < 66.67) is by definition a direct long/aerial delivery — functionally identical to a long ball. There is no separate “Cross” entry method.
- **Set-piece tightened:** If the team plays the set piece short in their own half and then builds up through passes before entering the FT, the dominant pattern is the subsequent build-up, not the dead ball. Only a restart whose very first pass crosses the FT threshold counts as a Set-Piece entry.

### High Regain — Detection Details

| Criterion | Value |
|-----------|-------|
| Recovery event types | Ball recovery, Interception, Tackle (outcome = 1 only) |
| x threshold | `x ≥ 66.67` (attacking third) |
| Phase | Open play only (set-piece possession origins excluded) |
| Which event | First play event of the possession |
| Entry point | Coordinates of the recovery event itself |
| `elapsed_sec` | 0 (ball is already in the FT at the moment of recovery) |
| Double-counting | None — `detect_ft_entries()` skips possessions whose first event has `x ≥ 66.67` |

This definition mirrors `notebooks/01_high_regains.ipynb` and `src/analytics/high_regains.py`, extended to also include interceptions and successful tackles (in line with the dashboard High Regains module).

---

## 6. Dashboard Sections & KPIs

The *Build-up to Final Third* card in the dashboard is assembled by `final_third_card()` and displays the following sections in order:

### Section A — Possession & Final Third Entry

| KPI | Formula |
|-----|---------|
| **Possession %** | `team_poss_time / total_match_poss_time × 100` (play events only) |
| **Qualifying Possessions** | Count of team possessions with duration ≥ 10 s |
| **Total FT Entries** | All detected crossings (including non-qualifying possessions) |
| **Qual. FT Entries** | Entries from qualifying possessions only |
| **FT Entry %** | `possessions_with_≥1_FT_entry / qualifying_possessions × 100` |
| **Opp. Box Touches** | Team events in opposition box (`x ≥ 83.33`, `21 ≤ y ≤ 79`), excluding duels, fouls and non-play events |

### Section B — Entry by Corridor

Entries grouped by the **y-coordinate at the point the ball crosses the FT line**:

| Corridor | Condition |
|----------|-----------|
| Left | `y > 66.67` |
| Centre | `33.33 ≤ y ≤ 66.67` |
| Right | `y < 33.33` |

Displayed as KPI cards (count) plus a horizontal stacked bar (percentages).

### Section C — How: Entry Method

Each entry method is displayed as a **KPI card** showing:
- The method label and icon
- The total count
- A short description of what the method means (e.g., *"Penetrative pass splitting the defence"* for Through Ball)

Below the cards, a **horizontal stacked bar** shows the percentage distribution of all methods. This avoids redundancy — the cards focus on counts and descriptions while the bar handles percentages.

The priority order is shown as a subtitle above the cards:
> **High Regain** ★ | Transition → Through Ball → Switch of Play → Set-Piece → Long Ball → Carry → Short Pass

### Section D — Post-Entry Zone Reach

For each entry, the **entry zone** (where the ball first appears in the FT) is checked:

| KPI | Zone(s) | Description |
|-----|---------|-------------|
| **Zone 14** | Z14 | Central danger zone (x 66.67–83.33, y 33.33–66.67) |
| **Flanks** | Z13, Z15, Z16, Z18 | Wide channels inside the final third |

Each is displayed as a count/total (percentage) card.

### Section E — Pitch Visualisations

Two half-pitch plots:

1. **Entry Points — Method View:** scatter plot of all entries, colour-coded by method (hover shows player name, method, timing).
2. **FT Entry Zones & Outcomes:** zone heatmap showing entry concentration and positive/negative outcomes by area.

### Section F — Entry Outcomes (Positive / Negative)

Two outcome cards showing count, percentage and description:

| Outcome | Description |
|---------|-------------|
| **Positive** | Retained ≥ 5 s **OR** shot / corner / foul won / penalty / goal |
| **Negative** | Lost within ≤ 3 s **OR** foul conceded **OR** opponent restart |

*Neutral outcomes (3–5 s, no trigger) are computed but not displayed in the summary cards.*

### Section G — Outcomes by Corridor

Horizontal stacked bar: positive vs negative for each corridor (Left / Centre / Right).

### Section H — Outcomes by Method

Horizontal stacked bar: positive vs negative for each entry method (only methods with ≥ 1 entry shown).

---

## 7. Outcome Classification — Detailed Rules

After each FT entry, the algorithm scans forward through the **full match** event stream (both teams).

### Positive (any of the following)

1. **Shot by team:** saved shot, miss, post or goal (F1 #13, #14, #15, #16)
2. **Goal scored:** by the attacking team (F1 #16)
3. **Corner awarded:** F1 #6
4. **Foul by opponent:** Opta foul row where the opponent committed (outcome = 0 on opponent row) (F1 #4)
5. **Penalty won:** F3 #9 qualifier on a team event
6. **Retained ≥ 5 s:** the team still has the ball after 5 seconds of play

### Negative (any of the following)

1. **Possession lost within ≤ 3 s:** opponent gains the ball quickly
2. **Attacking foul:** the team commits a foul in the FT (F1 #4, outcome = 0 on team row)
3. **Opponent possession:** opponent event before any positive trigger

### Neutral

- Possession boundary reached between 3–5 s with no positive or negative trigger.
- End of match data with team still having the ball but under 5 s elapsed.

### Why These Thresholds?

| Threshold | Value | Reasoning |
|-----------|-------|-----------|
| Positive retention | **≥ 5 s** | Long enough to execute 1–2 actions (receive, pass, shoot); short enough to avoid crediting stalled possession |
| Negative loss | **≤ 3 s** | Faster than positive because losing the ball immediately is a clear failed entry |
| Post-entry window (zones) | **10 s** | Allows enough time to observe where the ball travels within the FT after entry |

---

## 8. Additional Metrics

| Metric | Formula | Insight |
|--------|---------|---------|
| **Avg Passes to FT** | Mean of `passes_before_count` across all entries | Build-up tempo indicator |
| **Avg Seconds to FT** | Mean of `elapsed_sec` across all entries | Progression speed |

### Per-Entry Flags (Stored, Not Yet Aggregated)

Each entry record stores boolean flags from Opta qualifiers for future sub-type analysis:

| Flag | F3 ID | Meaning |
|------|-------|---------|
| `chipped_flag` | #155 | Pass was lofted / chipped |
| `launch_flag` | #157 | Long pass aimed at a zone (not a player) |
| `lay_off_flag` | #156 | Ball laid into the path of a teammate's run |
| `flick_on_flag` | #168 | Headed flick forward |
| `pull_back_flag` | #195 | Cut-back from the by-line |
| `head_pass_flag` | #3 | Pass with the head |
| `attacking_pass_flag` | #106 | Pass in the opponent's half |
| `big_chance` | #214 | Opta Big Chance designation |
| `individual_play` | #215 | Chance created without an assist |

---

## 9. Reading the Build-up to Final Third Card — Example

**Scenario: Inter vs Roma, GW18 (2025-26)**

```
POSSESSION & ENTRY
  Possession:       58.3%
  Qualifying Poss.: 41
  Total FT Entries: 34        (incl. non-qualifying)
  Qual. FT Entries: 28
  FT Entry %:       63.4%    (26 poss. with ≥1 entry / 41 qual.)
  Box Touches:       19

CORRIDOR
  Left:   9 (32%)   ·   Centre: 12 (43%)   ·   Right: 7 (25%)

ENTRY METHOD
  High Regain:            3   — Ball won back directly inside the final third
  Transition / Recovery:  4   — Ball won in own third, FT reached within 8 s
  Through Ball:           2   — Penetrative pass splitting the defence
  Switch of Play:         1   — Lateral pass changing the point of attack
  Set-Piece:              3   — Set-piece played directly into the final third
  Long Ball:              5   — Direct pass over 32 m, aerial ball, or cross from own half
  Individual Carry:       2   — Dribble or run with the ball into FT
  Short Pass:            11   — Patient build-up with ≥ 5 passes
  [Stacked bar: Short Pass 35% · Long Ball 16% · Transition 13% · High Regain 10% · ...]

POST-ENTRY ZONES
  Zone 14: 8 / 28 (28.6%)    — Central danger zone
  Flanks:  11 / 28 (39.3%)   — Wide channels

OUTCOMES
  Positive: 16 (57.1%)       — Retained ≥5 s OR shot / corner / foul / penalty / goal
  Negative: 9 (32.1%)        — Lost within ≤3 s OR foul conceded OR opponent restart
  [Neutral: 3 (10.7%) — not shown on card]

OUTCOMES BY CORRIDOR
  Left:   ████████░░  6 pos / 2 neg
  Centre: █████████░  8 pos / 3 neg
  Right:  ████░░░░░░  2 pos / 4 neg

OUTCOMES BY METHOD
  Short Pass:    ██████░░  7 pos / 3 neg
  Long Ball:     ███░░░░░  2 pos / 2 neg
  Transition:    ████░░░░  3 pos / 1 neg
  ...
```

**Interpretation:**
- Inter **dominate possession** (58 %) and convert it efficiently into FT entries (63 %).
- **Short passing** (36 %) is the dominant method — patient build-up through midfield.
- **Central corridor** (43 %) reflects midfield control; left side is a secondary route.
- **57 % positive rate** — more than half of all entries create danger or sustained pressure.
- **Right corridor is the weak link** — more negative than positive outcomes, suggesting the opposition defends that side effectively.
- **Zone 14 reached 29 % of the time** — central danger zone is accessed in roughly 1 in 3.5 entries.

---
---

# PHASE 1 VS PHASE 2: COMPARISON

| Aspect | GK Build-up (Phase 1) | Build-up to Final Third (Phase 2) |
|--------|----------------------|-----------------------------------|
| **Starting point** | Goal kick | Any possession |
| **Retention window** | 15 seconds | 5 s (positive) / 3 s (negative) |
| **Key question** | Can the GK start clean? | Can the team reach the final third productively? |
| **Entry focus** | First receiver location | FT-line crossing |
| **Method taxonomy** | Short vs Long | 9 methods (priority-based) |
| **Success metric** | Retention after distribution | Danger creation after FT entry |
| **Typical sample** | 10–20 per match | 15–35 per match |
| **Tactical insight** | GK distribution preference | Overall attacking pattern & style |

---

# GENERAL BUILD-UP MODULE (Supporting)

The `general_buildup.py` module provides a **simpler, open-play-only** view with a 6-category progression taxonomy:

| Category | Detection |
|----------|-----------|
| Through Ball | Opta Through ball flag |
| Long Ball / Direct | Opta Long ball flag or Length ≥ 30 |
| Recovery + Quick | Ball recovery / interception / tackle origin + entry within 8 s |
| Individual Carry | Same player carries across FT line |
| Short Passing | ≥ 5 passes before entry |
| Other | Default |

It also tracks **post-Z3** metrics (Z14 control, wide play, box entries) within a 10-second window, plus extra insights (avg passes before entry, avg seconds to entry). This module is displayed in the *General Build-up — Open Play* card.

---

# IMPLEMENTATION NOTES

1. **High Regain detection is separate.** `detect_high_regain_ft_entries()` runs independently from `detect_ft_entries()`. Because `detect_ft_entries()` skips possessions whose first event is already at `x ≥ 66.67`, the two detectors are mutually exclusive — zero double-counting. The method value is set at detection time; `_classify_ft_method()` is not called for these entries.

2. **No hard set-piece exclusion.** The Phase 2 module does not exclude set-piece-origin possessions. Set-piece entries are only classified as `set_piece` method when the **restart pass itself** crosses the FT line (`passes_before_count == 0`). If the team plays the restart short in their own half and then builds up, the entry is classified by its dominant play pattern (short pass, long ball, etc.).

3. **Cross qualifier → Long Ball.** The Opta Cross qualifier (F3 #2) on a pass originating outside the FT is treated as `long_ball`. In-match crosses almost always originate from *inside* the final third; a cross from outside is a direct/aerial delivery. The “Cross” method has been removed from the taxonomy.

4. **Qualifier renaming.** `_load_match_events()` (in `goalkeeper_buildup.py`) renames a subset of Opta columns. The `_QUALIFIER_RENAMES` dict in `final_third.py` adds the remaining qualifiers needed for this analysis.

5. **Long ball threshold.** Opta defines “Long ball” as “over 35 yards”. The code uses `Length ≥ 32` (Opta units ≈ metres on a 100×100 grid) as a fallback when the flag is missing — approximately equivalent.

6. **Through ball sparsity.** The Through ball qualifier (F3 #4) is sparsely populated in Serie A data (~1–4 per match across all teams). When the flag is present but `Pass End X/Y` coordinates are missing, the code infers the endpoint from the next event's position.

7. **Box touches.** Duels (aerial / ground), tackles, fouls, cards and all non-play events are excluded. Each qualifying action in the box is counted individually.

8. **Entry method cards show descriptions, not percentages.** The method cards display the total count and a short textual description (e.g., *“Penetrative pass splitting the defence”*). Percentages are shown exclusively in the stacked bar below, avoiding redundancy.

9. **Outcome terminology.** The negative outcome card uses *“foul conceded”* (standard football terminology) rather than *“foul surrendered”*.

---

---
---

# PHASE 3: CHANCE CREATION

## Purpose

Analyse how a team creates and converts shot opportunities — the final stage of the offensive phase. Phase 3 answers: *"How does the team score? Through set pieces? Fast transitions? Patient build-up? Crosses?"*

**Code:** `dash_app/src/analytics/chance_creation.py`
**UI card:** `dash_app/src/components/chance_creation_cards.py`
**xG model:** `dash_app/src/utils/xg_model.py` → `src/analytics/xg.py`

---

## 1. Core Definitions

| Concept | Value | Source |
|---------|-------|--------|
| Penalty box | `x ≥ 83.33` AND `21.1 ≤ y ≤ 78.9` | Opta 0–100 scale |
| Shot event types | `type_id` ∈ {13, 14, 15, 16} | Miss, Post, Saved, Goal |
| On-target shot | `type_id` ∈ {15, 16} | Saved Shot or Goal |
| Set-piece lookback | 15 s | Window before shot |
| Set-piece max passes | 5 | Passes from restart to shot; more than this → Combination |
| Attacking restarts only | Corner, Free Kick, Throw-In, Penalty | Goal kicks / GK distribution are **excluded** (defensive restarts) |
| Counter / High Regain window | 8 s | From possession start to shot |
| Through ball lookback | 12 s | Window before shot |
| High Regain threshold | `x ≥ 66.67` | Recovery inside final third |

---

## 2. Opta Event Types Used

| type_id | Event | Role |
|---------|-------|------|
| 4 | Foul | Set-piece detection (free kick context) |
| 6 | Corner Awarded | Set-piece possession origin |
| 7 | Tackle | Possession origin for Counter / High Regain |
| 8 | Interception | Possession origin for Counter / High Regain |
| 13 | Miss | Shot event |
| 14 | Post | Shot event |
| 15 | Saved Shot | Shot event (on target) |
| 16 | Goal | Shot event (on target + goal) |
| 49 | Ball Recovery | Possession origin for Counter / High Regain |
| 50 | Dispossessed | Turnover detection (Case B) |

**Key qualifier columns:** `Through ball`, `Cross`, `Corner taken`, `Free kick taken`, `Throw In`, `Penalty`.
(Goal Kick / Gk kick from hands are **not** used as set-piece triggers — they are defensive restarts.)

---

## 3. Data Pipeline

```
Raw CSV (Opta F1 / F3 events)
    │
    ▼
1.  _prepare_events()            — normalise column names, numeric types,
    │                              sort by period / minute / second / event_id,
    │                              compute _match_sec
    │
    ▼
2.  build_possessions()          — (reused from general_buildup.py)
    │                              assign poss_id, poss_origin, poss_team_name,
    │                              poss_start_sec
    │
    ▼
3.  _extract_shots()             — identify all shots for the selected team
    │                              (type_id ∈ {13, 14, 15, 16})
    │
    ▼
4.  classify_attack_origin()     — priority-ordered origin classification
    │                              (§4 below)
    │
    ▼
5.  compute_xg_for_shot()        — xG via existing XGModel (xg.py)
    │
    ▼
6.  classify_shot_quality()      — quality tier 0–3
    │
    ▼
7.  build_chain_to_goal_matrix() — 6 origins × 4 rows (N, xG, SoT%, GS)
    │
    ▼
8.  compute_shot_metrics()       — volume, location, SoT% metrics
    │
    ▼
9.  compute_high_regain_kpis()   — separate pressing KPIs
    │                              (from high_regains.py)
    │
    ▼
10. Output dict
```

---

## 4. Attack Origin Classification (Priority Order)

Each shot is assigned **exactly one** origin. The algorithm checks the following rules from top to bottom — first match wins.

| Priority | Origin | Icon | Detection Rule |
|----------|--------|------|---------------|
| 1 | **Set Piece** | 🚩 | Possession started from an **attacking** dead-ball restart (corner, free kick, throw-in, penalty) **AND** ≤ 5 passes to the shot; OR shot is a penalty. **Goal kicks are excluded** — they are defensive restarts. |
| 2 | **High Regain** | 🔴 | Possession starts with a recovery event (`x ≥ 66.67`) + shot within 8 s **[Case A]** — OR — shot is the first play event and the previous opponent possession ended with a turnover at flipped x ≥ 66.67, within 8 s **[Case B]**. **Suppressed** when the preceding possession was an opponent attacking set piece (defensive clearance context). |
| 3 | **Counter** | ⚡ | Possession starts with a recovery event (`x < 66.67`) + shot within 8 s |
| 4 | **Cross** | ↗ | Last pass before shot has `Cross` qualifier **OR** pass origin is in wide zone (`y < 25` or `y > 75`) inside the final third — with a **cross-to-header fallback** that looks up to 3 possessions back for same-team cross when shot possession starts with an aerial event |
| 5 | **Through Ball** | 🎯 | Any pass in the 12 s lookback has `Through ball` qualifier (F3 #4); checked last pass first, then all passes in window. **Qualifier-detected only** — patient build-up without the qualifier falls to Combination. |
| Default | **Combination** | ↑↑ | None of the above matched — patient passing-chain build-up. Covers both in-box and out-of-box shots. Shot location (in-box vs out-of-box) is tracked separately in the Shot Overview KPIs, not via the origin column. |

### Set Piece Detection — Two Conditions Required

A shot is classified **Set Piece** only when **both** hold:
1. An **attacking** restart event (corner, free kick, throw-in, penalty) is found within 15 s of the shot.
2. ≤ 5 passes were played from the restart to the shot.

**Goal kicks are intentionally excluded.** A goal kick is a defensive restart used for possession recycling, not an attacking set piece. A team that builds out from a goal kick through 3 passes and then shoots would inflate the Set Piece count without it being tactically meaningful.

**Why the pass-count gate?** A set piece played short in the team’s own half and built up through many passes (e.g. Zielinski’s goal: Inter free kick in own third → 8 passes → goal) should be **Combination**, not Set Piece. The origin was a restart, but the dominant tactical identity of the sequence is the build-up play that followed it.

**Why the 3-possession lookback?** A corner or free kick often triggers a possession split at an aerial duel:
```
Poss N   (team):  corner taken → cross
Poss N+1 (opp):   aerial (lost by team)
Poss N+2 (team):  header / shot  ← shot lives here
```
The shot’s possession has `poss_origin = "open_play"` because the possession started from an aerial, not a restart. Without the lookback, these would be misclassified (e.g. Bastoni shot at min 24 from a corner → previously shown as Through Ball; Lautaro shot at min 40 from a set-piece cross → previously shown as Cross). The lookback walks back up to 3 possessions and checks their `poss_origin` or inline events.

### High Regain — Case B (Direct-Score Turnover)

This handles the situation where an attacker scores directly from an opponent mistake — there is no explicit “ball recovery” event because the goal *is* the recovery:

```
Prev. possession (opponent):
  Last event = Error / Dispossessed / failed action at opp_x
  → Flip: our_x = 100 − opp_x ≥ 66.67

Current possession (team):
  First play event = Shot/Goal (within 8 s of the turnover)
→ Classified: High Regain
```

### High Regain — Directionality Guard

A ball recovery deep in the final third while **defending** an opponent set piece is a clearance, not a high press. If the immediately preceding possession was an opponent attacking restart (corner, free kick, throw-in, penalty), the Case A High Regain classification is suppressed. Such recoveries fall to Counter (if fast) or Combination (default).

```
Prev. possession (opponent): corner taken → cross
Current possession (team):   ball recovery at x=72 → shot
→ NOT High Regain (set-piece defensive context → Counter or Combination)
```

### Cross-to-Header Fallback

A cross delivered into the box frequently causes a possession split at the aerial duel. The pattern is:

```
Poss N   (team):   … → Cross pass (Cross=Si or wide-zone FT pass)
Poss N+1 (opp):   Aerial (lost)
Poss N+2 (team):  Aerial (won) → Shot/Goal  ← shot is here
```

When no cross is found inside the shot's own possession *and* the possession starts with an aerial/clearance/ball-recovery event, the detector walks back up to 3 possessions and searches the last same-team possession for a cross within the 12 s window.

---

## 5. Shot Metrics

### Per-Shot Metrics

| Metric | Formula / Source |
|--------|----------------|
| **xG** | `compute_xg_for_shot()` → delegates to `src/analytics/xg.py` (trained logistic regression on distance, angle, shot type, set-piece flag) |
| **On target** | `type_id` ∈ {15, 16} |
| **In box** | `x ≥ 83.33` AND `21.1 ≤ y ≤ 78.9` |
| **Is goal** | `type_id == 16` |

### Shot Quality Tiers

| Tier | Name | Criteria | Display colour |
|------|------|----------|---------------|
| **3** | Converted | Goal (`type_id == 16`) | Green |
| **2** | Big Chance | On target **OR** `xG ≥ 0.20` | Orange |
| **1** | Promising | Miss/Post (`type_id` ∈ {13,14}) AND `xG ≥ 0.10` | Yellow |
| **0** | Speculative | Blocked **OR** `xG < 0.10` | Grey |

### Aggregate Shot Metrics

| KPI | Formula |
|-----|---------|
| **Shots Total / In Box / Out Box** | Raw counts |
| **% In/Out Box** | `in_box / total × 100` |
| **SoT %** | `on_target / total × 100` (overall, in-box split, out-box split) |
| **Shot Frequency %** | `total_shots / total_team_possessions × 100` |
| **xG per Possession** | `sum_xG / total_team_possessions` |
| **xG per Shot** | `sum_xG / total_shots` |

---

## 6. Chain-to-Goal Matrix

The centrepiece of Phase 3 — a 6 × 4 table (6 attack origins + TOTAL column, 4 metric rows) showing how each attack origin converts into quality and goals.

### Design Principles

- **Consistent aggregation:** all four rows use the same philosophy — counts, sums, or rates — so any two columns in the same row are directly comparable.
- **N row added:** shot counts make the other rows interpretable (e.g. a column with high xG but N=1 is a single lucky shot, not a systematic pattern).
- **SoT% replaces xGOT:** shots-on-target percentage is directly computable from Opta data with no approximation. xGOT required tracking data (shot placement, goalkeeper position) that is not available; the approximation (`xGOT ≈ xG ± small constant`) added noise rather than signal.
- **Out Box removed as an origin:** shot location (in-box vs out-of-box) is a *where* dimension, not a *how the attack was built* dimension. It is tracked in the Shot Overview KPIs (Section A). All shots that don’t match a specific tactical origin fall to **Combination** regardless of distance.
- **Through Ball = qualifier-detected only:** only shots preceded by an Opta F3 #4 qualifier within 12 s. Patient build-up without the qualifier → Combination.
- **Combination = renamed default:** replaces the previous “Open Play” label. More descriptive: it signals patient passing-chain play, not just “not a set piece”.

### Structure

```
              Set Piece  High Regain  Counter  Cross  Through Ball  Combination  TOTAL
N (shots)       sum        sum          sum     sum      sum           sum         sum
xG              sum        sum          sum     sum      sum           sum         sum
SoT%            %          %            %       %        %             %           %
GS              count      count        count   count    count         count       count
```

### Column Order

Ordered roughly by **speed of attack** (set piece → fast transitions → build-up):

> **Set Piece** → **High Regain** → **Counter** → **Cross** → **Through Ball** → **Combination**

### Row Definitions

| Row | Aggregation | Interpretation |
|-----|-------------|---------------|
| **N** | Count of shots | Volume — makes xG and SoT% interpretable |
| **xG** | Sum of all shots from this origin | Total expected goal output by method |
| **SoT%** | On-target shots / N × 100 | Shot quality (placement) by method |
| **GS** | Count of goals | Actual finishing by method |

---

## 7. High Regain KPIs (Integrated)

Computed separately by `compute_high_regain_kpis()` (from `high_regains.py`) and embedded in the Phase 3 output. These measure **pressing effectiveness** independently of the shot origin classification.

| KPI | Description |
|-----|-------------|
| `total_high_regains` | All ball recoveries at x ≥ 66.67 in open play |
| `linked_to_shot` | Regains followed by a shot within 15 s |
| `linked_to_goal` | Regains followed by a goal within 15 s |
| `shot_conversion_rate` | `linked_to_shot / total_high_regains` |
| `goal_conversion_rate` | `linked_to_goal / total_high_regains` |
| `avg_time_to_shot_sec` | Mean time from regain to shot |

**Why both High Regain origin AND High Regain KPIs?**
- **Attack Origin "High Regain"** answers: *"Which specific shot was born from a high press?"*
- **High Regain KPIs** answer: *"How many high-press recoveries did the team make, and how dangerous were they overall?"*

---

## 8. Dashboard Sections

The Chance Creation card (`chance_creation_cards.py`) displays the following sections:

### Section A — Shot Volume & Location

KPI cards:
- Total shots · Shots in box · Shots out of box
- SoT % (total)
- Shot Frequency % · xG Total · xG per Shot
- Goals (with SoT% subtitle)

### Section B — Attack Origin Breakdown

KPI cards (one per origin, count + xG) with icon and colour. Horizontal stacked bar (percentages). Priority order displayed as subtitle:

> **Set Piece** → **High Regain** → **Counter** → **Cross** → **Through Ball** → **Combination** (default)

Colours follow the origin palette:

| Origin | Colour |
|--------|--------|
| Set Piece | Green |
| High Regain | Red |
| Counter | Orange |
| Cross | Cyan |
| Through Ball | Purple |
| Combination | Blue |

### Section C — xG by Attack Origin

Horizontal bar chart: xG sum per origin (active origins only).

### Section D — Attack Origin Zones

Full-pitch 18-zone grid: shot density heatmap with green (on-target/goal) and red (miss/blocked) outcome dots per zone.

### Section E — Shot Map

Half-pitch scatter plot: shot locations coloured by origin; stars = goals, circles = non-goal shots.

### Section F — Shot Quality Tiers

Donut chart + four KPI cards (Converted / Big Chance / Promising / Speculative).

### Section G — Chain-to-Goal Matrix

The 6 × 4 table (Set Piece | High Regain | Counter | Cross | Through Ball | Combination | TOTAL) with colour-coded row labels (N grey, xG blue, SoT% pink, GS green). The TOTAL column is highlighted. The highest-value cell per row is colour-accented.


## 9. Reading the Chance Creation Card — Example

**Scenario: Inter vs Bologna, GW18 (2025-26) — 3-1 win**

```
SHOT VOLUME & LOCATION
  Shots total:        18    (in box: 13 · out box: 5)
  SoT %:             61.1%
  xG Total:           2.85   (xG/Shot: 0.158)
  Goals:               3     (SoT%: 61.1%)

CHAIN-TO-GOAL MATRIX
                Set Piece  High Regain  Counter  Cross  Through Ball  Combination  TOTAL
  N               1           2           2       3         0            10          18
  xG             0.45        0.31        0.28    0.41       0.00         1.40        2.85
  SoT%          100.0%      100.0%      50.0%   66.7%      —            50.0%       61.1%
  GS              1           1           0       1         0             0            3

ATTACK ORIGINS
  Set Piece:              1 — Dead-ball situation (direct, ≤ 5 passes, attacking restart)
  High Regain:            2 — Ball won in final third + immediate shot
  Counter:                2 — Fast break from own/middle third recovery
  Cross:                  3 — Wide delivery into the box
  Through Ball:           0 — Qualifier-detected splitting pass
  Combination:           10 — Patient passing-chain build-up (5 in-box, 5 out-box)

SHOT QUALITY TIERS
  Converted (Tier 3):     3 (16.7%)
  Big Chance (Tier 2):    6 (33.3%)   ← on target or xG ≥ 0.20
  Promising (Tier 1):     4 (22.2%)   ← xG ≥ 0.10
  Speculative (Tier 0):   5 (27.8%)

HIGH REGAIN KPIs
  Total regains:          11
  Linked to shot:          4 (36%)
  Linked to goal:          2 (18%)
```

**Interpretation:**
- **Combination is the dominant origin** (10 shots, 0 goals, 1.40 xG) — Inter build patiently through midfield. Low conversion so far but high volume sustains pressure.
- **High Regain is high-value** — 100% SoT rate and 1 goal from 0.31 xG across just 2 shots. Elite counter-pressing converts to danger.
- **Set Piece delivers** — 1 goal from 1 shot (0.45 xG converted); Bastoni from a corner (correctly classified: shot within 2 passes of the corner delivery, no goal-kick inflation).
- **Cross contributes** — 3 shots, 1 goal, 66.7% SoT. Thuram aerial from Bastoni cross.
- **N row is essential:** High Regain and Set Piece look impressive in xG/GS rows, but N=2 and N=1 respectively — context prevents over-reading small samples.
- **50% of shots are Tier 2/3** — half their shots seriously threaten the goalkeeper.

---
---

# SERIE A BENCHMARKS (2025-26)

From analysed matches:

### Phase 1 — GK Build-up

| Metric | Typical range |
|--------|---------------|
| Goal kicks per match per team | 10–20 |
| Short distribution % | 40–70 % |
| Positive outcome rate | 55–75 % |

### Phase 2 — Build-up to Final Third

| Metric | Typical range |
|--------|---------------|
| FT entries per team per match | 15–35 |
| Dominant entry methods | Usually `long_ball` and `short_pass` |
| Through balls per match | 0–3 (rare but high-value) |
| Crosses as FT entries | Very rare (most crosses originate inside the FT) |
| Positive outcome rate | 45–65 % |
| Z14 reach rate | 20–35 % |

### Phase 3 — Chance Creation

| Metric | Typical range |
|--------|---------------|
| Shots per team per match | 10–20 |
| Shots on target % | 35–55 % |
| Shots in box % | 55–75 % |
| xG per shot | 0.10–0.18 |
| xG per possession | 0.04–0.10 |
| Dominant attack origins | `Combination` and `Set Piece` |
| High Regain linked to shot % | 15–40 % |
| Shot quality Tier 2+3 % | 35–55 % |