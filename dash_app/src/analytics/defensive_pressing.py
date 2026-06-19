"""
Defensive Phase — D1: Pressing & Defensive Actions
====================================================
Quantifies how intensely and effectively a team presses the opposition
in a single match, covering:

  1. PPDA (Passes Allowed Per Defensive Action)
  2. Pressing Height (median x_att of defensive actions)
  3. Pressing Direction (Left / Centre / Right corridor split)
  4. Pressing Success (possession regained within 5 s)
  5. 18-Zone action density heatmap

Coordinate system (Opta, **from the analysed team's perspective**):
  x : 0 = own goal-line   → 100 = opponent goal-line
  y : 0 = right touchline → 100 = left touchline  (broadcast view)

For PPDA we need *opponent* passes in the pressing zone.  Because every
CSV row carries the acting team's coordinate system, we must convert
opponent coordinates to our own frame by reflecting: x_att = 100 − x_opp.

Opta event-type IDs used
────────────────────────
  PPDA denominator (industry-standard 4 types):
    4  Foul (committed)
    7  Tackle
    8  Interception
   45  Challenge (failed tackle)

  Wider defensive actions (pressing height / direction / success / heatmap):
    4  Foul     7  Tackle     8  Interception    12  Clearance
   44  Aerial  45  Challenge  49  Ball Recovery  74  Blocked Pass

  Opponent passes (PPDA numerator):
    1  Pass
    2  Offside Pass
   74  Blocked Pass
  (+107 Throw In qualifier treated as a pass)

  Long-ball exclusion (ppda_excl_long):
    F3 #1  "Long ball" qualifier == "Si"  OR  F3 #212 Length >= 32
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.analytics.goalkeeper_buildup import (
    _load_match_events,
    _is_same_team,
    _is_play_event,
    NON_PLAY_EVENTS,
    xy_to_zone,
)
from src.analytics.general_buildup import build_possessions
from src.team_mapping import canonical_name

log = logging.getLogger("dashboard.defensive_pressing")

# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

# PPDA pressing zone upper bound — opponent's x_att ≤ 60
# (opponent's own half + middle third; we reflect: x_att = 100 − x_opp)
PPDA_ZONE_UPPER: float = 60.0     # opponent has x_opp ≥ 40

# Sub-zone for high press (opponent's own third)
HIGH_PRESS_ZONE_UPPER: float = 33.33   # opponent has x_opp ≥ 66.67

# Mid press zone
MID_PRESS_LOWER: float = 33.33
MID_PRESS_UPPER: float = 60.0

# Pressing height zone boundaries (our attacking x)
# Actions in x ≥ 66.67   → High press (we press in their final third)
# Actions in 33.33–66.67 → Mid press
# Actions in x < 33.33   → Low block (we're defending in our own half)
HIGH_PRESS_X_MIN: float = 66.67
MID_PRESS_X_MIN:  float = 33.33

# Corridor boundaries (y axis)
LEFT_Y_MIN:   float = 66.67   # y > 66.67 = Left
RIGHT_Y_MAX:  float = 33.33   # y < 33.33 = Right

# Long-ball distance threshold (F3 #212 Length)
LONG_BALL_LENGTH: float = 32.0

# Pressing success window (seconds after defensive action)
PRESS_SUCCESS_SEC: float = 10.0

# Opta type_id sets
# Wide set used for pressing height / direction / success / heatmap:
#   4  Foul (committed)  7  Tackle   8  Interception  12  Clearance
#  44  Aerial            45 Challenge (auto-fail)      49  Ball Recovery
#  74  Blocked Pass
DEFENSIVE_ACTION_IDS: frozenset[int] = frozenset({4, 7, 8, 12, 44, 45, 49, 74})

# Narrow set used ONLY for the PPDA denominator (industry-standard definition:
# StatsBomb / Wyscout / Opta): tackles, interceptions, fouls, challenges.
PPDA_ACTION_IDS: frozenset[int] = frozenset({4, 7, 8, 45})

OPPONENT_PASS_IDS:    frozenset[int] = frozenset({1, 2, 74})

# Aerial duels (type_id=44) at x >= this threshold are in the opponent's box
# and represent ATTACKING header contests (from corners, crosses, set pieces),
# NOT defensive actions. They are excluded from all defensive counts.
AERIAL_TYPE_ID:        int   = 44
AERIAL_OPP_BOX_X_MIN: float = 83.33   # = final zone row start (zones 16-18)


def _is_team_def_action(row: pd.Series) -> bool:
    """
    Return True when a row is a genuine defensive action made BY the pressing team.

    Fouls (type_id=4) in Opta appear TWICE for every incident:
      * outcome=0 on the FOULER   → foul committed  → real defensive action
      * outcome=1 on the VICTIM   → foul won        → NOT a defensive action
    Tackles, Interceptions and Ball Recoveries are kept unconditionally.

    Aerial duels (type_id=44) at x >= 83.33 (opponent box, zones 16-18) are
    attacking header contests from corners/crosses and are NOT defensive actions.
    """
    tid = row.get("type_id")
    if pd.isna(tid) or int(tid) not in DEFENSIVE_ACTION_IDS:
        return False
    tid = int(tid)
    if tid == 4:  # Foul — committed side only
        outcome = row.get("outcome", 0)
        try:
            return int(outcome) == 0
        except (ValueError, TypeError):
            return False
    if tid == AERIAL_TYPE_ID:  # Aerial — exclude opponent-box attacking headers
        try:
            return float(row.get("x", 0) or 0) < AERIAL_OPP_BOX_X_MIN
        except (ValueError, TypeError):
            return False
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def analyse_defensive_pressing(match_csv: Path, team: str) -> dict[str, Any]:
    """
    Run the full D1 pressing analysis for *team* in the given match CSV.

    Returns a flat dict with all KPIs and detail lists consumed by the UI.
    """
    team_lower = canonical_name(str(team)).lower()

    df = _load_match_events(match_csv)
    if df.empty:
        return _empty_result()

    # Rename type_id column if present
    if "type_id" not in df.columns and "type_id" in df.columns:
        pass
    # ensure numeric type_id
    if "type_id" in df.columns:
        df["type_id"] = pd.to_numeric(df["type_id"], errors="coerce")

    # Build possession chains (for pressing success detection)
    df = build_possessions(df)

    # Split team / opponent
    team_df, opp_df = _separate_teams(df, team_lower)

    ppda        = compute_ppda(team_df, opp_df)
    height      = compute_pressing_height(team_df)
    direction   = compute_pressing_direction(team_df)
    success     = compute_pressing_success(team_df, df, team_lower)
    heatmap     = compute_action_heatmap(team_df)

    return {
        **ppda,
        **height,
        **direction,
        **success,
        "zone_heatmap":   heatmap,
        "def_actions_df": _build_actions_df(team_df),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 1. TEAM / OPPONENT SPLIT
# ═══════════════════════════════════════════════════════════════════════════════

def _separate_teams(
    df: pd.DataFrame, team_lower: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split full match dataframe into (team_events, opponent_events)."""
    mask = df["team_name"].apply(
        lambda t: canonical_name(str(t).strip()).lower() == team_lower
    )
    return df[mask].copy(), df[~mask].copy()


# ═══════════════════════════════════════════════════════════════════════════════
# 2. PPDA
# ═══════════════════════════════════════════════════════════════════════════════

def compute_ppda(team_df: pd.DataFrame, opp_df: pd.DataFrame) -> dict:
    """
    Compute four PPDA variants:
      ppda_overall, ppda_high, ppda_mid, ppda_overall_excl_long

    For each zone, the denominator is team defensive actions in the
    SAME zone (mapped to our coordinate frame).
    """

    def _is_def_action(row: pd.Series) -> bool:
        return _is_team_def_action(row)

    def _is_opp_pass(row: pd.Series) -> bool:
        tid = row.get("type_id")
        if pd.isna(tid):
            return False
        tid = int(tid)
        if tid in OPPONENT_PASS_IDS:
            return True
        # Throw-in qualifier counts as opponent pass
        throw_in = str(row.get("Throw In", row.get("throw_in", ""))).strip().lower()
        if throw_in in ("si", "yes", "1", "true") and tid == 1:
            return True
        return False

    def _is_long_ball(row: pd.Series) -> bool:
        lb = str(row.get("Long ball", row.get("long_ball", ""))).strip().lower()
        if lb in ("si", "yes", "1", "true"):
            return True
        try:
            length = float(row.get("Length", row.get("length", 0)) or 0)
            return length >= LONG_BALL_LENGTH
        except (ValueError, TypeError):
            return False

    def _x_att_opp(row: pd.Series) -> float:
        """Convert opponent's x to 'opponent's attack direction' (reflecting)."""
        x = row.get("x")
        if pd.isna(x):
            return np.nan
        # Opponent's x=0 is their own goal; reflected = 100 − x gives their
        # attacking x (distance from their own goal → how deep we are pressing).
        return 100.0 - float(x)

    # ── Opponent passes with pressing-zone x_att ──────────────────────────────
    opp_pass_mask = opp_df.apply(_is_opp_pass, axis=1)
    opp_passes    = opp_df[opp_pass_mask].copy()
    opp_passes["x_att"] = opp_passes.apply(_x_att_opp, axis=1)

    opp_overall = opp_passes[opp_passes["x_att"] <= PPDA_ZONE_UPPER]
    opp_high    = opp_passes[opp_passes["x_att"] <= HIGH_PRESS_ZONE_UPPER]
    opp_mid     = opp_passes[
        (opp_passes["x_att"] > MID_PRESS_LOWER) &
        (opp_passes["x_att"] <= MID_PRESS_UPPER)
    ]

    opp_overall_excl = opp_overall[~opp_overall.apply(_is_long_ball, axis=1)]

    # ── Team defensive actions with our attacking x ────────────────────────────
    # PPDA denominator uses the narrow industry-standard 4-type set (PPDA_ACTION_IDS),
    # not the wider DEFENSIVE_ACTION_IDS used by height/direction/success/heatmap.
    def _is_ppda_action(row: pd.Series) -> bool:
        tid = row.get("type_id")
        if pd.isna(tid) or int(tid) not in PPDA_ACTION_IDS:
            return False
        # Foul: committed side only (outcome=0)
        if int(tid) == 4:
            outcome = row.get("outcome", 0)
            try:
                return int(outcome) == 0
            except (ValueError, TypeError):
                return False
        return True

    def_mask   = team_df.apply(_is_ppda_action, axis=1)
    def_acts   = team_df[def_mask].copy()

    # For PPDA denominator we use team actions in the SAME zone (our x coordinate)
    # Our x is already in attacking direction (0=own goal, 100=opp goal).
    # Press zone in our frame: x ≥ (100 − PPDA_ZONE_UPPER) = 40
    denom_overall = def_acts[def_acts["x"] >= (100.0 - PPDA_ZONE_UPPER)]
    denom_high    = def_acts[def_acts["x"] >= (100.0 - HIGH_PRESS_ZONE_UPPER)]
    denom_mid     = def_acts[
        (def_acts["x"] >= (100.0 - MID_PRESS_UPPER)) &
        (def_acts["x"] <  (100.0 - MID_PRESS_LOWER))
    ]

    def _safe_ppda(num: int, den: int) -> float | None:
        if den == 0:
            return None
        return round(num / den, 2)

    num_overall      = len(opp_overall)
    num_high         = len(opp_high)
    num_mid          = len(opp_mid)
    num_overall_excl = len(opp_overall_excl)

    den_overall = len(denom_overall)
    den_high    = len(denom_high)
    den_mid     = len(denom_mid)

    # Total defensive actions (full pitch, for Section A KPI) — uses the wide
    # DEFENSIVE_ACTION_IDS set, not the narrow PPDA set, so the displayed count
    # reflects all defensive activity (clearances, aerials, recoveries, etc.).
    wide_def_mask = team_df.apply(_is_team_def_action, axis=1)
    total_def_actions = int(wide_def_mask.sum())

    return {
        "ppda_overall":           _safe_ppda(num_overall, den_overall),
        "ppda_high":              _safe_ppda(num_high, den_high),
        "ppda_mid":               _safe_ppda(num_mid, den_mid),
        "ppda_overall_excl_long": _safe_ppda(num_overall_excl, den_overall),
        # Raw counts for transparency
        "ppda_num_overall":       num_overall,
        "ppda_num_high":          num_high,
        "ppda_num_mid":           num_mid,
        "ppda_den_overall":       den_overall,
        "ppda_den_high":          den_high,
        "ppda_den_mid":           den_mid,
        "total_def_actions":      total_def_actions,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 3. PRESSING HEIGHT
# ═══════════════════════════════════════════════════════════════════════════════

def compute_pressing_height(team_df: pd.DataFrame) -> dict:
    """
    Where along the pitch does the team apply defensive pressure?

    Returns:
      pressing_line_median  — median x of all defensive actions
      high_press_count/pct  — defensive actions in x ≥ 66.67
      mid_press_count/pct   — defensive actions in 33.33 ≤ x < 66.67
      low_block_count/pct   — defensive actions in x < 33.33
    """
    def_mask = team_df.apply(_is_team_def_action, axis=1)
    acts = team_df[def_mask & team_df["x"].notna()].copy()
    acts["x"] = acts["x"].astype(float)

    if acts.empty:
        return {
            "pressing_line_median": None,
            "high_press_count": 0, "high_press_pct": 0.0,
            "mid_press_count":  0, "mid_press_pct":  0.0,
            "low_block_count":  0, "low_block_pct":  0.0,
        }

    total = len(acts)
    high  = acts[acts["x"] >= HIGH_PRESS_X_MIN]
    mid   = acts[(acts["x"] >= MID_PRESS_X_MIN) & (acts["x"] < HIGH_PRESS_X_MIN)]
    low   = acts[acts["x"] < MID_PRESS_X_MIN]

    def _pct(n: int) -> float:
        return round(n / total * 100, 1) if total else 0.0

    return {
        "pressing_line_median": round(float(acts["x"].median()), 1),
        "high_press_count": len(high),
        "high_press_pct":   _pct(len(high)),
        "mid_press_count":  len(mid),
        "mid_press_pct":    _pct(len(mid)),
        "low_block_count":  len(low),
        "low_block_pct":    _pct(len(low)),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 4. PRESSING DIRECTION
# ═══════════════════════════════════════════════════════════════════════════════

def compute_pressing_direction(team_df: pd.DataFrame) -> dict:
    """
    Where along the WIDTH of the pitch do defensive actions concentrate?

    Corridor split (same as Phase 2 / offensive):
      Left   — y > 66.67
      Centre — 33.33 ≤ y ≤ 66.67
      Right  — y < 33.33
    """
    def_mask = team_df.apply(_is_team_def_action, axis=1)
    acts = team_df[def_mask & team_df["y"].notna()].copy()
    acts["y"] = acts["y"].astype(float)

    if acts.empty:
        return {
            "pressing_left_count":   0, "pressing_left_pct":   0.0,
            "pressing_centre_count": 0, "pressing_centre_pct": 0.0,
            "pressing_right_count":  0, "pressing_right_pct":  0.0,
        }

    total  = len(acts)
    left   = acts[acts["y"] > LEFT_Y_MIN]
    centre = acts[(acts["y"] >= RIGHT_Y_MAX) & (acts["y"] <= LEFT_Y_MIN)]
    right  = acts[acts["y"] < RIGHT_Y_MAX]

    def _pct(n: int) -> float:
        return round(n / total * 100, 1) if total else 0.0

    return {
        "pressing_left_count":   len(left),
        "pressing_left_pct":     _pct(len(left)),
        "pressing_centre_count": len(centre),
        "pressing_centre_pct":   _pct(len(centre)),
        "pressing_right_count":  len(right),
        "pressing_right_pct":    _pct(len(right)),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 5. PRESSING SUCCESS
# ═══════════════════════════════════════════════════════════════════════════════

def compute_pressing_success(
    team_df: pd.DataFrame,
    full_df: pd.DataFrame,
    team_lower: str,
) -> dict:
    """
    A press is successful when the team gains possession within PRESS_SUCCESS_SEC
    seconds of the defensive action.

    Returns overall press_success_rate and breakdowns by zone group and corridor.
    """
    def_mask = team_df.apply(_is_team_def_action, axis=1)
    acts = team_df[def_mask & team_df["x"].notna() & team_df["y"].notna()].copy()
    acts["x"] = acts["x"].astype(float)
    acts["y"] = acts["y"].astype(float)

    if acts.empty:
        return _empty_success()

    # Tag each action with zone group and corridor
    acts["zone_group"] = acts["x"].apply(_x_to_zone_group)
    acts["corridor"]   = acts["y"].apply(_y_to_corridor)

    # For each action, check next 5 s of full_df for a team possession start
    results: list[dict] = []
    full_sorted = full_df.sort_values(["period", "minute", "second", "event_id"]).reset_index(drop=True)

    for _, act in acts.iterrows():
        # Use minute+second to build match_sec; guard against NaN seconds
        act_min = float(act.get("minute", 0) or 0)
        act_s   = float(act.get("second", 0) or 0)
        act_sec = act_min * 60.0 + act_s
        act_per = act.get("period")

        # Recompute _match_sec for the whole window using the same formula so
        # the comparison is consistent (avoids stale / NaN _match_sec values).
        win_mask = (
            (full_sorted["period"] == act_per) &
            (full_sorted["_match_sec"] > act_sec) &
            (full_sorted["_match_sec"] <= act_sec + PRESS_SUCCESS_SEC)
        )
        window = full_sorted[win_mask]

        # ── Early-exit: certain events are ALWAYS a failure ────────────────
        # Foul committed (4, outcome=0): referee stops play against us.
        # Challenge (45): by Opta definition the opponent successfully dribbled
        #   past our player → the opponent kept the ball → never a success.
        act_tid = int(act.get("type_id", 0) or 0)
        if act_tid in (4, 45):
            results.append({"success": False, "zone_group": act["zone_group"], "corridor": act["corridor"]})
            continue

        # ── "Last event in window" possession logic ─────────────────────────
        # We scan ALL events in the 5-second window and find the last one that
        # is meaningful (not noise). If that final event belongs to the pressing
        # team  → SUCCESS  (they still had the ball at the end of the window).
        # If it belongs to the opponent → FAILURE (opponent regained by then).
        # If the window has no meaningful events → SUCCESS (silent possession).
        #
        # Exception: if the opponent's final event is a foul committed on our
        # player → set piece won → SUCCESS.
        #
        # This handles scrambles correctly: even if the opponent touches the ball
        # momentarily inside the window, what matters is who ends up with it.
        last_team:  str | None = None
        last_tid:   int        = 0
        for _, w_row in window.iterrows():
            et = str(w_row.get("event_type", "")).strip().lower()
            if et in NON_PLAY_EVENTS or et == "":
                continue
            last_team = canonical_name(str(w_row.get("team_name", "")).strip()).lower()
            last_tid  = int(w_row.get("type_id", 0) or 0)

        if last_team is None:
            # No meaningful event in window → possession held silently
            success = True
        elif last_team == team_lower:
            success = True
        else:
            # Opponent had the ball last — unless they committed a foul on us
            success = (last_tid == 4)

        results.append({
            "success":    success,
            "zone_group": act["zone_group"],
            "corridor":   act["corridor"],
        })

    res_df = pd.DataFrame(results)
    total  = len(res_df)

    def _rate(sub: pd.DataFrame) -> float:
        if sub.empty:
            return 0.0
        return round(sub["success"].sum() / len(sub) * 100, 1)

    overall_rate = _rate(res_df)

    # By zone group
    zone_success: dict[str, dict] = {}
    for zg in ("high", "mid", "low"):
        sub = res_df[res_df["zone_group"] == zg]
        zone_success[zg] = {
            "total":   len(sub),
            "success": int(sub["success"].sum()) if not sub.empty else 0,
            "rate":    _rate(sub),
        }

    # By corridor
    corr_success: dict[str, dict] = {}
    for cor in ("L", "C", "R"):
        sub = res_df[res_df["corridor"] == cor]
        corr_success[cor] = {
            "total":   len(sub),
            "success": int(sub["success"].sum()) if not sub.empty else 0,
            "rate":    _rate(sub),
        }

    # Per-action detail list for scatter plotting
    acts_reset = acts.reset_index(drop=True)
    detail: list[dict] = []
    for i, act_row in acts_reset.iterrows():
        r = results[i] if i < len(results) else {"success": False, "zone_group": "", "corridor": ""}
        tid = int(act_row.get("type_id", 0) or 0)
        detail.append({
            "x":         round(float(act_row["x"]), 1),
            "y":         round(float(act_row["y"]), 1),
            "action":    _TYPE_LABEL.get(tid, "Unknown"),
            "player":    str(act_row.get("player_name", "")).strip(),
            "minute":    int(act_row.get("minute", 0) or 0),
            "zone_group": r["zone_group"],
            "corridor":  r["corridor"],
            "success":   r["success"],
        })

    return {
        "press_success_rate":         overall_rate,
        "press_success_total":        total,
        "press_success_successful":   int(res_df["success"].sum()),
        "press_success_by_zone":      zone_success,
        "press_success_by_corridor":  corr_success,
        "press_actions_detail":       detail,
    }


def _empty_success() -> dict:
    empty_zg  = {zg: {"total": 0, "success": 0, "rate": 0.0} for zg in ("high", "mid", "low")}
    empty_cor = {c:  {"total": 0, "success": 0, "rate": 0.0} for c  in ("L", "C", "R")}
    return {
        "press_success_rate":        0.0,
        "press_success_total":       0,
        "press_success_successful":  0,
        "press_success_by_zone":     empty_zg,
        "press_success_by_corridor": empty_cor,
        "press_actions_detail":      [],
    }


def _x_to_zone_group(x: float) -> str:
    if x >= HIGH_PRESS_X_MIN:
        return "high"
    if x >= MID_PRESS_X_MIN:
        return "mid"
    return "low"


def _y_to_corridor(y: float) -> str:
    if y > LEFT_Y_MIN:
        return "L"
    if y < RIGHT_Y_MAX:
        return "R"
    return "C"


# ═══════════════════════════════════════════════════════════════════════════════
# 6. 18-ZONE ACTION HEATMAP
# ═══════════════════════════════════════════════════════════════════════════════

def compute_action_heatmap(team_df: pd.DataFrame) -> dict[int, int]:
    """
    Return {zone_number: count} for all defensive actions over the 18-zone grid.
    """
    def_mask = team_df.apply(_is_team_def_action, axis=1)
    acts = team_df[def_mask & team_df["x"].notna() & team_df["y"].notna()]

    counts: dict[int, int] = {z: 0 for z in range(1, 19)}
    for _, row in acts.iterrows():
        z = xy_to_zone(float(row["x"]), float(row["y"]))
        counts[z] = counts.get(z, 0) + 1
    return counts


# ═══════════════════════════════════════════════════════════════════════════════
# 7. HELPER — actions dataframe for detailed table
# ═══════════════════════════════════════════════════════════════════════════════

def _build_actions_df(team_df: pd.DataFrame) -> list[dict]:
    """Return a lightweight list of dicts for the detailed actions table."""
    def_mask = team_df.apply(_is_team_def_action, axis=1)
    acts = team_df[def_mask].copy()
    records = []
    for _, row in acts.iterrows():
        tid = int(row.get("type_id", 0) or 0)
        records.append({
            "player":    str(row.get("player_name", "")).strip(),
            "action":    _TYPE_LABEL.get(tid, "Unknown"),
            "minute":    int(row.get("minute", 0) or 0),
            "x":         round(float(row["x"]), 1) if pd.notna(row.get("x")) else None,
            "y":         round(float(row["y"]), 1) if pd.notna(row.get("y")) else None,
            "zone":      xy_to_zone(float(row["x"]), float(row["y"]))
                         if pd.notna(row.get("x")) and pd.notna(row.get("y")) else None,
            "zone_group": _x_to_zone_group(float(row["x"])) if pd.notna(row.get("x")) else None,
            "corridor":  _y_to_corridor(float(row["y"])) if pd.notna(row.get("y")) else None,
            "outcome":   int(row.get("outcome", 0) or 0),
        })
    return records


_TYPE_LABEL = {
    4:  "Foul",
    7:  "Tackle",
    8:  "Interception",
    12: "Clearance",
    44: "Aerial",
    45: "Challenge",
    49: "Ball Recovery",
    74: "Blocked Pass",
}


# ═══════════════════════════════════════════════════════════════════════════════
# EMPTY RESULT FALLBACK
# ═══════════════════════════════════════════════════════════════════════════════

def _empty_result() -> dict[str, Any]:
    return {
        # PPDA
        "ppda_overall":           None,
        "ppda_high":              None,
        "ppda_mid":               None,
        "ppda_overall_excl_long": None,
        "ppda_num_overall":       0,
        "ppda_num_high":          0,
        "ppda_num_mid":           0,
        "ppda_den_overall":       0,
        "ppda_den_high":          0,
        "ppda_den_mid":           0,
        "total_def_actions":      0,
        # Height
        "pressing_line_median":   None,
        "high_press_count":       0, "high_press_pct":   0.0,
        "mid_press_count":        0, "mid_press_pct":    0.0,
        "low_block_count":        0, "low_block_pct":    0.0,
        # Direction
        "pressing_left_count":    0, "pressing_left_pct":   0.0,
        "pressing_centre_count":  0, "pressing_centre_pct": 0.0,
        "pressing_right_count":   0, "pressing_right_pct":  0.0,
        # Success
        **_empty_success(),
        # Heatmap
        "zone_heatmap": {z: 0 for z in range(1, 19)},
        "def_actions_df": [],
    }
