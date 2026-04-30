# Goal Kick Build-up Analysis Bug Fix

## Issue Summary
The **Build-up from Goal Kicks** section in the Match Analysis (Offensive Phase) was showing only 2 goal kick distributions instead of the actual 8 from Inter's goalkeeper in the Inter vs Roma match (5-2, 2025/2026).

## Root Causes (Two Issues)

### Issue 1: Position Filter Too Restrictive
**Location**: `goalkeeper_buildup.py`, function `_is_goal_kick()` (line ~196)

**Problem**: The function required `position == 'GK'` to identify goal kicks:
```python
# Must be GK position
if str(row.get("position", "")).strip().upper() != "GK":
    return False
```

**Why It Failed**: Modern football tactics allow defenders (CBs, LBs, RBs) to take goal kicks from the goal area. In the Inter vs Roma match:
- Y. Sommer (GK) took 2 goal kicks ✓ **Counted**
- A. Bastoni (CB) took 2 goal kicks ✗ **Filtered out** 
- F. Acerbi (CB) took 4 goal kicks ✗ **Filtered out**

This alone eliminated 6 of 8 goal kicks.

**Solution**: Removed the position filter. Goal kicks are reliably identified by the Opta `Goal Kick == "Si"` flag, so position validation is unnecessary and overly restrictive.

### Issue 2: Team Name Matching Inconsistency  
**Location**: `goalkeeper_buildup.py`, function `analyse_goalkeeper_buildup()` (line 376)

**Problem**: Team name was converted to lowercase without using the `canonical_name()` function:
```python
team_lower = team_name.strip().lower()  # ← WRONG
```

But other helper functions (`_is_same_team()`, `_is_goal_kick()`) expected canonical names:
```python
return canonical_name(raw).lower() == team_lower  # Expects canonical form
```

**Why It Failed**: 
- Function receives: `"FC Internazionale Milano"`
- Sets `team_lower = "fc internazionale milano"` (plain lowercase)
- Helper functions use: `canonical_name("FC Internazionale Milano") → "Inter"` → `"inter"`
- No match occurred, filtering out all results

**Solution**: Use `canonical_name()` for consistency:
```python
team_lower = canonical_name(team_name).lower()  # ← CORRECT
```

## Changes Made

### File: `dash_app/src/analytics/goalkeeper_buildup.py`

#### Change 1: Updated module docstring (lines 1-17)
- Changed from "Goalkeeper Build-up Analysis" to "Goal Kick Build-up Analysis"
- Updated to clarify that goal kicks can be taken by goalkeepers or defenders
- Removed reference to "GK open-play distributions"

#### Change 2: Removed position filter in `_is_goal_kick()` function (lines 166-200)
- **Removed**: The `position == 'GK'` validation
- **Updated docstring**: Clarified that position is NOT used as a filter
- **Reason**: Opta's `Goal Kick == "Si"` flag is the authoritative indicator

#### Change 3: Fixed team name matching in `analyse_goalkeeper_buildup()` (line 376)
- **Changed**: `team_lower = team_name.strip().lower()`
- **To**: `team_lower = canonical_name(team_name).lower()`
- **Reason**: Ensures consistency with how other functions do team matching

## Verification Results

### Before Fix
- Inter vs Roma match showed only 2 goal kick distributions

### After Fix
**Inter (Home)**
- Total Goal Kicks: **8** ✓
- Short Kicks: 7 (87.5%)
- Long Kicks: 1 (12.5%)
- Positive Outcomes: 1
- Negative Outcomes: 7

**Roma (Away)**
- Total Goal Kicks: **8** ✓ (previously likely ~2)
- Short Kicks: 3 (37.5%)
- Long Kicks: 5 (62.5%)
- Positive Outcomes: 0
- Negative Outcomes: 8

## Impact
This fix ensures that:
1. **All goal kicks are counted**, regardless of whether they're taken by the goalkeeper or defenders
2. **Team filtering works correctly** across all tactical variations
3. **The dashboard now displays accurate build-up statistics** for goal kick analysis
4. Both **offensive and defensive** teams' goal kick data are tracked completely

## Testing
The fix was validated using the Inter vs Roma match (GW31, 2025/2026 season):
- Match file: `31_Inter_Roma_qzr4j7v0ic3d0lnvgrdlx2xg.csv`
- Confirmed all 8 Inter goal kicks are now detected (previously: 2)
- Confirmed all 8 Roma goal kicks are now detected
