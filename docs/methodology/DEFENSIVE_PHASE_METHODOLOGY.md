# Defensive Phase Methodology

## Overview

The Defensive Phase analysis quantifies how a team defends — collectively, spatially, and effectively — in a single match. It is structured around two complementary modules:

| Module | File | Scope |
|---|---|---|
| **D1 — Pressing & Defensive Actions** | `src/analytics/defensive_pressing.py` | PPDA, pressing height, direction, success rate, heatmap |
| **D2 — High Regains** | `src/analytics/high_regains.py` | Ball recoveries in the attacking third linked to chance creation |

Both modules operate on raw Opta match-event CSVs and share the same coordinate frame.

---

## Coordinate System

All coordinates follow the **Opta convention from the analysed team's attacking perspective**:

- **x**: `0` = own goal-line → `100` = opponent goal-line
- **y**: `0` = right touchline → `100` = left touchline (broadcast view)

For PPDA, the opponent's passes are recorded from the opponent's own coordinate frame. To convert them to the analysed team's frame, a reflection is applied:

$$x_{\text{att}} = 100 - x_{\text{opp}}$$

This `x_att` value represents how deep into the opponent's half the pressing team is applying pressure.

---

## Section D1 — Pressing & Defensive Actions

### 1. Defensive Actions — Event Classification

The following Opta event types are classified as **defensive actions** and form the basis of all D1 metrics:

| Opta `type_id` | Event | Notes |
|---|---|---|
| `4` | Foul | Only `outcome = 0` (foul **committed** by pressing team). `outcome = 1` is the foul **won** by the victim — excluded. |
| `7` | Tackle | All tackles included regardless of outcome (success filter is applied separately in D2). |
| `8` | Interception | All interceptions. |
| `49` | Ball Recovery | All ball recoveries. |

> **Foul deduplication**: Opta logs every foul incident as two rows — one for the fouler (`outcome=0`) and one for the victim (`outcome=1`). Only the fouler row represents a defensive action and is retained.

### 2. Pitch Zones

The pitch is divided into three longitudinal zones based on `x`:

| Zone | x range | Meaning |
|---|---|---|
| **High press** | `x ≥ 66.67` | Defending in the opponent's final third |
| **Mid press** | `33.33 ≤ x < 66.67` | Defending in the middle third |
| **Low block** | `x < 33.33` | Defending in the own half |

The lateral (y) axis is divided into three corridors:

| Corridor | y range |
|---|---|
| **Left** | `y > 66.67` |
| **Centre** | `33.33 ≤ y ≤ 66.67` |
| **Right** | `y < 33.33` |

### 3. PPDA — Passes Allowed Per Defensive Action

PPDA measures pressing intensity:

$$\text{PPDA} = \frac{\text{Opponent passes in pressing zone}}{\text{Team defensive actions in pressing zone}}$$

A **lower PPDA** indicates a more intense press (fewer opponent passes per defensive action).

**Opponent passes (numerator)** include Opta events with `type_id ∈ {1, 2, 74}` (Pass, Offside Pass, Blocked Pass). Throw-ins (`type_id=1` with throw-in qualifier `= "Si"`) are also counted. The opponent's pass coordinates are reflected as `x_att = 100 − x_opp`, and only passes with `x_att ≤ 60` (i.e., in the opponent's own half plus middle third) are counted.

Four PPDA variants are computed:

| Variant | Pressing zone (opponent x_att) | Team actions zone (our x) |
|---|---|---|
| `ppda_overall` | `x_att ≤ 60` | `x ≥ 40` |
| `ppda_high` | `x_att ≤ 33.33` | `x ≥ 66.67` |
| `ppda_mid` | `33.33 < x_att ≤ 60` | `40 ≤ x < 66.67` |
| `ppda_overall_excl_long` | `x_att ≤ 60`, excluding long balls | `x ≥ 40` |

**Long-ball exclusion**: a pass is classified as a long ball if the F3 qualifier `#1` is `"Si"` or if the F3 qualifier `#212` (Length) is `≥ 32` metres.

### 4. Pressing Height

The **pressing line** is defined as the **median x-coordinate** of all defensive actions across the full pitch. A higher median `x` indicates a team that defends further up the pitch.

Counts and percentages are also provided for each of the three longitudinal zones (high, mid, low block).

### 5. Pressing Direction

Defensive actions are distributed across the three lateral corridors (Left, Centre, Right). Counts and percentages reflect the team's tendency to defend wide or centrally.

### 6. Pressing Success Rate

A defensive action is classified as **successful** if the team retains possession within **10 seconds** after the action.

#### Success / Failure Classification Logic

The full-match event stream is scanned in the 5-second window following each defensive action. The classification follows this priority order:

1. **Foul committed by the pressing team** (`type_id=4`, `outcome=0`): always classified as **FAILURE** — the referee stops play against the pressing team regardless of subsequent events.

2. **No meaningful event in the window** (all events are non-play or the window is empty): classified as **SUCCESS** — the pressing team holds possession silently.

3. **Last meaningful event in the window belongs to the pressing team**: **SUCCESS**.

4. **Last meaningful event belongs to the opponent**:
   - If the opponent's last event is a foul they committed on the pressing team (`type_id=4`): **SUCCESS** — the pressing team earns a free kick.
   - Otherwise: **FAILURE**.

> **Rationale for "last event" logic**: during a 5-second scramble, both teams may touch the ball. What matters for possession purposes is who holds the ball *at the end* of the window, not who touched it first. The last meaningful event in the window is the most reliable proxy for this.

> **Non-play events** (e.g., deleted events, period markers, time markers) are skipped and do not affect the classification.

Success rates are computed overall and broken down by **zone group** (high, mid, low) and by **corridor** (Left, Centre, Right).

### 7. 18-Zone Action Heatmap

Defensive actions are projected onto an **18-zone grid** (6 columns × 3 rows, as used across all modules) to produce a spatial density map. The zone assignment uses the shared `xy_to_zone()` utility function.

---

## Data Sources

| Source | Description |
|---|---|
| Opta match-event CSVs | Raw event stream per match under `data/raw/serie_a_<season>/events/` |
| F1 event type table | `F1_opta_event_types copia.csv` — maps `type_id` to event names |
| F3 qualifier table | `F3_opta_qualifier_types copia.csv` — maps qualifier codes to field names |

---

## Module Dependencies

```
defensive_pressing.py
  ├── goalkeeper_buildup.py   (_load_match_events, _is_same_team, xy_to_zone, NON_PLAY_EVENTS)
  ├── general_buildup.py      (build_possessions)
  └── team_mapping.py         (canonical_name)

high_regains.py
  ├── possession_value.py     (NON_PLAY_EVENTS, FT_X_THRESHOLD, SHOT_TYPE_IDS, PossessionValueModel)
  ├── general_buildup.py      (build_possessions)
  └── team_mapping.py         (canonical_name)
```
