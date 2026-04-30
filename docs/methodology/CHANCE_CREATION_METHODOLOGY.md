# Chance Creation Analysis Methodology

**Version**: 1.0 | **Date**: April 2026 | **Module**: `src/analytics/chance_creation.py`

---

## Table of Contents

1. [Overview](#overview)
2. [Data Pipeline](#data-pipeline)
3. [Attack Origin Classification](#attack-origin-classification)
4. [Shot Extraction & Metrics](#shot-extraction--metrics)
5. [Chain-to-Goal Matrix](#chain-to-goal-matrix)
6. [Quality Tiers](#quality-tiers)
7. [Integration with High Regains](#integration-with-high-regains)
8. [Output Structure](#output-structure)

---

## Overview

**Purpose**: Analyse how a team creates and converts shot opportunities.

**Scope**: 
- Identifies all shots taken by a team in a match
- Classifies the origin/method of each shot's attack
- Computes shot quality metrics (xG, xGOT, Possession Value)
- Builds a **Chain-to-Goal Matrix** showing how different attacking methods perform
- Detects high-regain goals (fast transitions from pressing recoveries)

**Key Insight**: "How does the team score? Through set pieces? Fast breaks? Build-up play? Crosses?" — Understanding this is critical for tactical evaluation.

---

## Data Pipeline

### 1. Input: Raw Match Events

**Source**: Opta CSV files (`data/raw/serie_a_*/events/*.csv`)

**Key columns used**:
```
event_type (or 'event')      → Event name (Pass, Shot, Ball recovery, etc.)
type_id                      → Opta event type code (13=Miss, 14=Post, 15=Saved, 16=Goal)
x, y                         → Pitch coordinates (0-100, Opta standard)
Pass End X, Pass End Y       → Destination of a pass
minute, second               → Match time
period_id (or 'period')      → Half (1 or 2)
team_name                    → Team identifier
player_name                  → Player who performed the action
outcome                      → Success (1) or Failure (0)
[Corner taken, Free kick taken, ...] → Set-piece qualifiers
Through ball, Cross, Long ball → Attack qualifiers
```

### 2. Event Normalization

**Step**: `_prepare_events(df)`

Handles both old and new Opta naming conventions:

```python
Renames (if needed):
  'event'              → 'event_type'
  'time_min'           → 'minute'
  'time_sec'           → 'second'
  'period_id'          → 'period'
  'Corner taken'       → 'corner_taken'
  'Free kick taken'    → 'free_kick_taken'
  [etc.]

Numeric coercions:
  x, y, minute, second, event_id, period, outcome, type_id → float

Sorting:
  Sort by period, minute, second, event_id

Helper column:
  _match_sec = minute × 60 + second  (match time in seconds)
```

### 3. Possession Chain Building

**Step**: `build_possessions(df)` (from `general_buildup.py`)

**Why**: Shots don't exist in isolation — they're the culmination of a possession chain. We need to group all events belonging to each team's continuous possession.

**Possession starts when**:
- The team on the ball changes (turnover)
- The period changes (halftime)
- A goal is scored (possession ends)
- A set-piece restart occurs (new possession context)

**Output columns added to DataFrame**:
```
poss_id          → Unique possession identifier (incremented per restart)
poss_team_name   → Team in possession
poss_origin      → How the possession started:
                   'open_play', 'corner', 'free_kick', 'throw_in',
                   'penalty', 'goal_kick', 'gk_hands'
poss_start_sec   → When the possession started (match seconds)
```

**Example**:
```
poss_id=42, team=Inter, origin='open_play', start=1200s
  └─ Pass (Barella, x=45)
  └─ Pass (Thuram, x=70)
  └─ Shot (Thuram, x=88) ← GOAL
  → Possession 42 ends with a goal
```

---

## Attack Origin Classification

**Purpose**: For each shot, determine **how** it was created — what attacking method led to it?

**Location**: `classify_attack_origin(shot_row, poss_events, poss_origin, poss_start_sec, match_df)`

### Classification Logic (Priority-Ordered)

#### Priority 1: Set Play ✅

**Definition**: Shot directly from a dead-ball restart within 12 seconds.

**Detection**:
1. Check if possession origin was a set piece (`poss_origin` ∈ {corner, free_kick, throw_in, penalty, goal_kick, gk_hands})
2. OR check if the shot itself is a penalty
3. OR search the possession events (12s lookback from shot) for:
   - Set-piece event types: "corner awarded", "free kick", "throw in", "penalty", "goal kick"
   - Set-piece qualifiers: "Corner taken", "Free kick taken", "Throw In", "Penalty", "Goal Kick", "Gk kick from hands"

**Example**:
```
50:22 Corner taken
50:28 Pass (Bastoni, x=85, y=30)
50:31 Shot (Bastoni, x=90) ← GOAL
Result: Set Play ✅ (within 12s of corner)
```

---

#### Priority 2: High Regain 🔴

**Definition**: Recovery in the attacking final third (x ≥ 66.67) followed by a fast shot (≤8s).

**Two cases**:

**Case A: Explicit recovery**
- Possession starts with a recovery event (ball recovery, interception, tackle)
- Recovery location: x ≥ 66.67
- Shot within 8 seconds of possession start

**Example**:
```
35:40 Sučić Ball recovery (x=80.1, Inter's attacking third)
35:41 Pass (x=79)
35:42 Shot (Thuram) ← GOAL
Result: High Regain ✅ (recovery at x=80 + shot in 2s)
```

**Case B: Direct-score turnover** (goal IS the recovery)
- Shot/goal is the **first play event** in its possession
- Previous possession belonged to opponent and ended with turnover:
  - Event type: Error, Dispossessed
  - OR outcome = 0 (failed pass/action)
- Turnover location (opponent coords) flips to our x ≥ 66.67
- Shot within 8 seconds of the turnover

**Example** (Lautaro's 51:00 goal):
```
Possession 282 (Torino):
  50:50 Masina Interception (x=26.7)
  50:58 Gineitis Pass, failed (x=14.0, outcome=0)
  50:59 Gineitis Error (x=12.8) ← Torino's end = Inter x ≈ 87.2

Possession 283 (Inter):
  51:00 Lautaro GOAL (x=93.7) ← First Inter event!
  
Flip: 100 - 12.8 = 87.2 ✅ (≥66.67)
Result: High Regain ✅ (1 second after opponent error)
```

---

#### Priority 3: Counter ⚡

**Definition**: Recovery in own/middle third (x < 66.67) + fast shot (≤8s).

- Possession starts with recovery (ball recovery, interception, tackle)
- Recovery location: x < 66.67 (NOT attacking final third)
- Shot within 8 seconds of possession start

**Example**:
```
10:00 Pavard Ball recovery (x=40, midfield)
10:03 Pass (x=60)
10:07 Shot (Thuram) ← GOAL
Result: Counter ✅ (recovery at x=40 + shot in 7s)
```

**Distinction from High Regain**: 
- **High Regain**: Win the ball while already attacking high up the pitch
- **Counter**: Win the ball back deeper and sprint forward to finish quickly

---

#### Priority 4: Through Ball 🎯

**Definition**: Shot preceded by a through-ball pass within 12 seconds.

**Detection**:
1. Search back 12s from shot for passes with "Through ball" qualifier
2. Check the **last pass before the shot** specifically

**Example**:
```
20:15 Barella Pass (Through ball) (x=50, pass end x=80)
20:18 Shot (Lautaro, x=85) ← GOAL
Result: Through Ball ✅ (through-ball in 3s)
```

---

#### Priority 5: Cross ✈️

**Definition**: Shot from a cross within 12 seconds.

**Detection** (two paths):

**Path A — Same-possession cross**:
1. Last pass before shot has "Cross" qualifier, OR
2. Last pass origin is wide zone (y < 25 or y > 75) in final third (x ≥ 66.67)
3. OR any pass in 12s lookback has cross qualifier

**Path B — Cross-to-header across possession boundary**:

A very common pattern in football: a cross is delivered → an aerial duel happens → the attacker heads the ball in. The aerial duel causes the possession builder to split the chain into separate possessions:

```
Poss N   (Inter):  ... → Bastoni cross (Cross=Si)
Poss N+1 (Torino): Biraghi aerial (lost)
Poss N+2 (Inter):  Thuram aerial (won) → Goal  ← shot is here
```

When no pass is found in the shot's possession **and** the possession starts with an aerial/header event, the detector looks back up to 3 possessions to find the previous same-team possession. If that possession contains a cross (qualifier or wide-zone pass) within the 12s window → classified as **Cross**.

**Example**:
```
61:37  Bastoni Pass (x=73.5, y=85.2) [Cross=Si, Pass End=95.7,40.7]
61:39  Biraghi Aerial (Torino, lost)      ← possession break
61:39  Thuram Aerial (Inter, won)          ← new possession starts
61:40  Thuram Goal (x=95.0, y=43.5)
Result: Cross ✅ (Bastoni's cross found in previous possession)
```

---

#### Priority 6: Out Box 📍

**Definition**: Shot from outside the penalty area.

- Shot location: x < 83.33 OR y < 21.1 OR y > 78.9
- (Penalty box: x ≥ 83.33 AND 21.1 ≤ y ≤ 78.9)

**Example**:
```
30:22 Shot (Barella, x=80, y=50) ← Outside box
Result: Out Box ✅ (long range)
```

---

#### Priority 7: Default → Through (Combination Play)

**Definition**: Build-up play, short passes, patient possession.

- No recovery, set piece, counter, through ball, cross, or out-box qualifier matched
- These are "Combination/Short Passing" plays mapped to "Through" in the matrix

**Example**:
```
5:00 Pass (x=45)
5:05 Pass (x=60)
5:10 Pass (x=75)
5:15 Shot (x=90) ← GOAL
Result: Through ✅ (patient build-up, no special method)
```

---

## Shot Extraction & Metrics

### 1. Shot Detection

**Criteria**: `type_id` ∈ {13, 14, 15, 16}

```
13 = Miss
14 = Post
15 = Saved Shot
16 = Goal
```

### 2. Per-Shot Metrics

For each shot, compute:

#### **xG (Expected Goals)**

**Source**: `compute_xg_for_shot(shot_row)` from `src/utils/xg_model.py`

**Inputs**:
- Distance to goal center (100, 50)
- Angle to goal
- Shot type (head, right foot, left foot, etc.)
- Set piece (penalty fixed at 0.79, own goal at 0.0)

**Formula** (simplified):
```python
if penalty:
    xG = 0.79
elif own_goal:
    xG = 0.0
else:
    # ML model trained on historical shot outcomes
    xG = model.predict([distance, angle, shot_type, ...])
    # Range: 0.0 (impossible) to ~1.0 (certain goal)
```

**Interpretation**: 
- xG = 0.10 → 10% chance this shot results in a goal
- xG = 0.50 → 50-50 shot
- xG = 0.80 → Likely to score

#### **xGOT (Expected Goals On Target)**

**Only computed for on-target shots** (type_id ∈ {15 [Saved], 16 [Goal]})

**Formula**:
```python
if on_target:
    xGOT = estimate_xgot(xG, shot_y, on_target)
else:
    xGOT = 0.0
```

**Logic**: Given that a shot is on target, what's the probability it's a goal? Adjusts based on keeper skill (approximated by y-coordinate — shots near corners are harder to save).

**Interpretation**: xGOT > xG suggests keeper made a mistake; xGOT < xG suggests keeper made a good save.

#### **PV (Possession Value)**

**Source**: `self._compute_shot_pv(poss_events, shot_row, poss_start_sec)`

**Two scenarios**:

**Scenario 1: Possession never entered final third**
```python
PV = get_xT(shot_location)  # Just the shot location's goal probability
```

**Scenario 2: Possession entered final third**
```python
# Find when possession crossed into final third (x ≥ 66.67)
ft_entry_time = first_event.time where x ≥ 66.67

# Compute delta from FT entry to shot location
PV = xT(shot_location) - xT(ft_entry_location)
```

**Interpretation**: 
- PV = +0.05 → The attacking sequence improved goal probability by 5 percentage points
- PV = -0.02 → Poor attacking execution (should have had a better location)
- PV = 0.00 → Possession value unchanged (low-quality move or defensive setup)

**Why this matters**: Separates "quality of chance creation" from "quality of shot finishing". A 0.10 xG goal might come from +0.15 PV (excellent build-up) or +0.02 PV (wasteful chance), revealing different tactical effectiveness.

#### **Is On Target**

```python
on_target = type_id in {15, 16}  # Saved Shot or Goal
```

#### **In Box**

```python
in_box = (x ≥ 83.33) AND (21.1 ≤ y ≤ 78.9)
```

#### **Is Goal**

```python
is_goal = type_id == 16
```

#### **Quality Tier** (0–3)

| Tier | Name | Criteria |
|---|---|---|
| 3 | Converted | `type_id == 16` (goal) |
| 2 | Threat | `on_target == True` OR `xG ≥ 0.20` (saved shot or high-quality miss) |
| 1 | Basic Danger | `type_id ∈ {13,14}` (miss/post) AND `xG ≥ 0.10` |
| 0 | Low Quality | `type_id == 14` (blocked) OR `xG < 0.10` |

---

## Chain-to-Goal Matrix

### Purpose

Summary table showing **how effectively each attack method produces goals**.

### Structure

```
Columns: 6
  Through | Cross | High Regain | Counter | Out Box | Set Play | TOTAL

Rows: 4
  PV    (average possession value across shots)
  xG    (sum of expected goals)
  xGOT  (sum of expected goals on target)
  GS    (actual goals scored)
```

### Calculation per Origin

```python
# Filter shots by origin
origin_shots = [s for s in all_shots if s["origin"] == origin]

# Per-metric aggregation
PV   = mean([s["PV"]       for s in origin_shots])    # Average
xG   = sum([s["xG"]        for s in origin_shots])    # Total
xGOT = sum([s["xGOT"]      for s in origin_shots if s["on_target"]])  # Total (on-target only)
GS   = count([s for s in origin_shots if s["is_goal"]])  # Count of goals
```

### Interpretation

**Example matrix**:
```
             Through   Cross   High Regain   Counter   Out Box   Set Play   TOTAL
PV             0.15    0.12      0.18         0.08      0.05      0.10      0.11
xG             1.50    0.40      0.26         0.39      0.21      0.12      2.88
xGOT           0.80    0.20      0.12         0.15      0.08      0.08      1.43
GS             3       0         1             0         0         1         5
```

**Reading**:
- **Through (Column 1)**: Team's main attacking method — 3 goals from 1.50 xG (clinical finishing)
- **High Regain**: Smaller sample (1 goal, 0.26 xG) but high PV (0.18) — elite counter-pressing
- **Counter**: Low conversion (0 goals from 0.39 xG) — missed opportunities on fast breaks
- **Set Play**: Reliable (1 goal) but low volume

---

## Quality Tiers

### Purpose

Segment shots by quality to understand **shot profile** (many low-quality vs. few high-quality).

### Tier Distribution

```python
# Count shots in each tier
tier_3_converted = count([s for s in shots if s["quality_tier"] == 3])
tier_2_threat    = count([s for s in shots if s["quality_tier"] == 2])
tier_1_danger    = count([s for s in shots if s["quality_tier"] == 1])
tier_0_low       = count([s for s in shots if s["quality_tier"] == 0])
```

### Interpretation

**Example**:
```
Tier 3 (Converted):    5 goals
Tier 2 (Threat):       6 shots
Tier 1 (Basic):        4 shots
Tier 0 (Low):          5 shots
Total:                20 shots

Interpretation: 25% of shots converted (elite level is 10–15%)
                30% were high-quality opportunities (threat level)
                50% were either converted or threatened (70% quality)
```

---

## Integration with High Regains

### High Regain KPIs

**Computed separately** by `compute_high_regain_kpis()` from `high_regains.py`

**Key metrics**:
```
total_high_regains       → Total regains at x ≥ 66.67 in open play
linked_to_shot           → Regains that led to shot within 15s
linked_to_goal           → Regains that led to goal within 15s
shot_conversion_rate     → linked_to_shot / total_high_regains
avg_time_to_shot_sec     → Mean time from regain to shot
total_pv_from_regains    → Sum of PV for linked chains
```

### Why Both Classifications?

- **High Regain (attack origin)**: "What origin led to THIS shot?" — Used in Chain-to-Goal Matrix
- **High Regain KPIs (separate metric)**: "How many times did the team regain the ball high up and what happened?" — Measures pressing effectiveness

**Example**:
```
High Regain KPIs:
  total_high_regains = 11
  linked_to_shot = 2
  linked_to_goal = 2
  shot_rate = 18%

Attack Origins (including High Regain goals):
  High Regain = 2 goals (same 2 that linked in KPIs)
```

---

## Output Structure

### Return Dict: `chance_creation_output`

```python
{
    "chain_to_goal_matrix": {
        "Through": {"PV": 0.15, "xG": 1.50, "xGOT": 0.80, "GS": 3},
        "Cross": {"PV": 0.12, "xG": 0.40, "xGOT": 0.20, "GS": 0},
        "High Regain": {"PV": 0.18, "xG": 0.26, "xGOT": 0.12, "GS": 1},
        "Counter": {"PV": 0.08, "xG": 0.39, "xGOT": 0.15, "GS": 0},
        "Out Box": {"PV": 0.05, "xG": 0.21, "xGOT": 0.08, "GS": 0},
        "Set Play": {"PV": 0.10, "xG": 0.12, "xGOT": 0.08, "GS": 1},
        "TOTAL": {"PV": 0.11, "xG": 2.88, "xGOT": 1.43, "GS": 5}
    },
    
    "shot_metrics": {
        "total_shots": 20,
        "goals_scored": 5,
        "avg_xg": 0.144,
        "avg_xgot": 0.072,
        "avg_pv": 0.107,
        "shots_on_target": 11,
        "shots_on_target_pct": 55.0,
        "avg_shot_distance": 28.5
    },
    
    "shot_quality_tiers": {
        "tier_3_converted": 5,
        "tier_2_threat": 6,
        "tier_1_danger": 4,
        "tier_0_low": 5
    },
    
    "shots_detail": [
        {
            "shot_idx": 0,
            "poss_id": 42,
            "origin": "Set Play",
            "x": 90.1, "y": 35.7,
            "type_id": 16,
            "is_goal": True,
            "on_target": True,
            "in_box": True,
            "xG": 0.352,
            "xGOT": 0.280,
            "PV": 0.058,
            "quality_tier": 3,
            "minute": 17, "second": 38,
            "player": "A. Bastoni",
            "event_type": "Goal"
        },
        # ... 19 more shots
    ],
    
    "high_regain_kpis": {
        "total_high_regains": 11,
        "linked_to_shot": 2,
        "linked_to_goal": 2,
        "shot_conversion_rate": 0.18,
        "goal_conversion_rate": 0.18,
        "avg_time_to_shot_sec": 3.0,
        "total_pv_from_regains": 0.248,
        "avg_pv_per_regain": 0.124,
        # ... more breakdown metrics
    }
}
```

### Dashboard Rendering

The output feeds three UI sections:

1. **Shot Overview** (KPI cards)
   - Total shots, Goals, avg xG, SoT%
   
2. **Chain-to-Goal Matrix** (5×4 table)
   - Shows PV, xG, xGOT, GS by attack origin
   
3. **High Regains Section** (KPI cards)
   - Regains, linked to shot, shot rate, PV added

4. **Quality Tier Breakdown** (stacked bar)
   - Visual distribution of shot quality

5. **Shots Detail** (expandable table)
   - Every shot with full metadata

---

## Key Assumptions & Limitations

### Assumptions

1. **Possession continuity**: Possessions are broken by team turnovers, goals, or set-piece restarts. "False" turnovers (e.g., out of play then throw-in) are treated as new possessions.

2. **Opta coordinate system**: x ∈ [0, 100] (own goal → opponent), y ∈ [0, 100] (right → left). Final third threshold is x ≥ 66.67.

3. **Shot classification**: Opta type_id 13–16 are exhaustive for shots. Blocked shots (type_id=14) are counted as shots but have zero xG.

4. **Direct-score turnovers**: Case B (opponent error → goal) assumes immediate previous possession in match_df. Resets after halftime.

### Limitations

1. **PV stability**: Possession Value requires a trained model (`possession_value.py`). Without it, falls back to fallback grid (hand-calibrated).

2. **High Regain linkage window**: Fixed at 15 seconds. Some chains might be faster/slower.

3. **No defensive context**: Attack origin classification is offensive-centric. Doesn't account for defensive setup or pressing intensity.

4. **Qualifiers accuracy**: Depends on Opta data quality. Missing qualifiers may misclassify crosses as through balls.

---

## Example: Full Match Analysis

**Match**: Inter vs Torino, 2025/26 GW1 (5–0)

### Input
- 20 shots by Inter
- 5 goals
- 2 high-regain goals (Thuram 35', Lautaro 51')

### Processing

1. **Normalize**: Convert column names, compute `_match_sec`
2. **Possessions**: Build 50+ possessions, tag by origin
3. **Shots**: Extract 20 Inter shots
4. **Classify origins**:
   - Bastoni 17': Set Play (corner)
   - Thuram 35': High Regain (Case A)
   - Lautaro 51': High Regain (Case B)
   - Thuram 61': Cross (cross-to-header, Path B)
   - Bonny 71': Through (build-up)
5. **Compute metrics**: xG, xGOT, PV for each shot
6. **Aggregate**: Chain-to-Goal Matrix, tiers, KPIs

### Output

```
Chain-to-Goal Matrix:
  Through:    1 goal,  0.39 xG, PV=0.15
  Cross:      1 goal,  0.72 xG, PV=0.12
  High Regain: 2 goals, 0.48 xG, PV=0.18
  Set Play:   1 goal,  0.12 xG, PV=0.10
  
Shot Metrics:
  20 shots, 5 goals (25% conversion)
  2.30 total xG, 1.43 xGOT
  
Quality Tiers:
  5 tier-3 (converted)
  6 tier-2 (threats)
  4 tier-1 (basic)
  5 tier-0 (low quality)

High Regains:
  11 total high regains
  2 linked to goals (18% conversion)
  PV from regains: +0.248
```

### Tactical Insights

- **Diverse finishing**: Goals from 4 different origins — no single-method dependency
- **High regain effective**: 2/2 regains converted (100%) — elite pressing efficiency
- **Cross delivery**: 1 goal from crosses (Thuram header) — Bastoni and Dimarco as key wide creators
- **Set piece solid**: 1/3 set-piece shots scored (33%) — above average
- **Overall clinical**: 25% shot conversion vs. 2.30 xG (6.8% baseline) = elite finishing

---

## See Also

- [`POSSESSION_VALUE_DESIGN.md`](./POSSESSION_VALUE_DESIGN.md) — xT/PV model details
- [`HIGH_REGAINS_METHODOLOGY.md`](./HIGH_REGAINS_METHODOLOGY.md) — High regain detection (if created)
- `src/utils/xg_model.py` — xG model implementation
- `src/analytics/general_buildup.py` — Possession building

---

**Last Updated**: April 3, 2026  
**Author**: Analytics Team  
**Status**: Documentation Complete
