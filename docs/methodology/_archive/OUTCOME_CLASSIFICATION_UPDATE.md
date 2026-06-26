# Outcome Classification Update (v4)

## Problem
The outcome classification was incorrectly marking goal kicks as "negative" when:
1. A foul was committed **against** the team (they still retain possession for the free kick)
2. The ball went out of play while the team had possession (they keep the restart)

**Example**: Inter's first goal kick at 13:30 (Z3, Carlos Augusto):
- ❌ Previously marked as **NEGATIVE** (incorrectly)
- ✅ Now marked as **POSITIVE** (correct)
- Reason: A foul was committed at 13:41 against Inter, but Inter maintained possession from the goal kick through their passes until that foul

## Solution
Updated `_classify_outcome()` function in `src/analytics/goalkeeper_buildup.py` to:

### Positive Outcomes (possession retained):
- ✅ Possession held for ≥ 15 seconds
- ✅ **Foul committed against the team** (team gets the free kick restart)
- ✅ **Ball goes out of play** (team keeps the corner kick, throw-in, or goal kick)

### Negative Outcomes (possession lost):
- ❌ Opponent gains possession via interception, tackle, dispossession, etc.

## Code Changes

### Before (v3):
```python
def _classify_outcome(ref_iloc, team_lower, df):
    """Check if team retains possession for >= 15s"""
    for j in range(ref_iloc + 1, len(df)):
        if elapsed >= POSSESSION_WINDOW_SEC:
            return "positive"
        
        if not _is_play_event(row):
            continue
        
        if not _is_same_team(row, team_lower):
            return "negative"  # ❌ ANY opponent action = negative
    
    return "positive"
```

### After (v4):
```python
def _classify_outcome(ref_iloc, team_lower, df):
    """Check if team retained possession"""
    for j in range(ref_iloc + 1, len(df)):
        if elapsed >= POSSESSION_WINDOW_SEC:
            return "positive"
        
        if not _is_play_event(row):
            continue
        
        is_team_event = _is_same_team(row, team_lower)
        if is_team_event:
            continue  # Team still building
        
        # Opponent event — check type
        event_type = str(row.get("event_type", "")).strip().lower()
        
        if event_type == "foul":
            return "positive"  # ✅ Foul against team
        
        if event_type == "out":
            return "positive"  # ✅ Ball out = team keeps restart
        
        return "negative"  # ❌ Opponent possession gained
    
    return "positive"
```

## Results (2025/2026 GW30: Fiorentina vs Inter)

### Inter
- Total goal kicks: 6
- **Positive outcomes**: 2 (including the corrected first GK at 13:30)
- **Negative outcomes**: 4

### Fiorentina
- Total goal kicks: 6
- **Positive outcomes**: 4 (including correctly attributed "Out" events)
- **Negative outcomes**: 2

## Dash Visualization Impact
The pitch zone visualization now correctly displays:
- **Green dots (●)** for positive outcomes (foul restarts, sustained possession, out-of-play retains)
- **Red dots (●)** for negative outcomes (opponent possession gained)

Example: **Z3** on Inter's pitch now shows **1 positive** (the corrected first goal kick)

## Files Modified
- `src/analytics/goalkeeper_buildup.py` — Updated `_classify_outcome()` function
- Dash visualizations automatically reflect the updated data via existing `zone_outcomes` structure

## Validation Spreadsheet
Updated: `outputs/goal_kicks_validation_fiorentina_inter_gw30_2025_2026.csv`
