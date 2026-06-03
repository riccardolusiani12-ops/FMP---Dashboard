"""
Corner Kicks Analysis — Set Pieces Phase
=========================================
Analyses corner kick events from Opta event CSV files.

Corner kick detection:
  type_id == 1 (Pass) AND "Corner taken" column == "Si"

Outputs:
  • Volume & outcomes summary (KPI row)
  • Delivery type breakdown (Inswinger / Outswinger / Straight / Short / Unknown)
  • Delivery zone counts (mapped to GA1–CA3 + Front/Back/Edge)
  • Defensive setup breakdown

Coordinate system (Opta):
  x: 0 → 100  (own goal → opponent goal)
  y: 0 → 100  (right touchline → left touchline)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from src.team_mapping import canonical_name

# Pitch geometry constants (Opta units)
SIX_YARD_L = 36.8
SIX_YARD_R = 63.2

# Penalty box boundaries (Opta units, x = 0→100 own→opp goal, y = 0→100)
BOX_DEPTH_X  = 83.33   # x where penalty area starts (distance from goal line)
BOX_WIDTH_L  = 21.1    # y — left edge of penalty box width
BOX_WIDTH_R  = 78.9    # y — right edge of penalty box width

# Delivery-zone geometry (video-verified 2025/2026)
# FrontZone  : x ≥ BOX_DEPTH_X  AND y < BOX_WIDTH_L or y > BOX_WIDTH_R
#              Wide near-byline corridor — short one-two passes (Group B)
# FrontZone2 : x < BOX_DEPTH_X  AND y < BOX_WIDTH_L or y > BOX_WIDTH_R
#              Wide strip behind box depth — flat driven Straight balls (Group A)
# Edge       : x < BOX_DEPTH_X  AND BOX_WIDTH_L ≤ y ≤ BOX_WIDTH_R
#              Outside-box central corridor — also mostly Straight (90 %)

log = logging.getLogger("dashboard.corner_kicks")

# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS — qualifier column names in the flat Opta CSV
# ═══════════════════════════════════════════════════════════════════════════════

# Corner detection
COL_CORNER_TAKEN = "Corner taken"   # Q6
COL_CROSS        = "Cross"          # Q2  (used to detect short corners)

# Delivery type columns
COL_INSWINGER  = "Inswinger"   # Q223
COL_OUTSWINGER = "Outswinger"  # Q224
COL_STRAIGHT   = "Straight"    # Q225

# Zone qualifier columns → diagram zone label
ZONE_COL_MAP: Dict[str, str] = {
    "Small box-left":       "GA1",   # Q61 — Near post 6-yard box
    "Small box-centre":     "GA2",   # Q16 — Centre 6-yard box
    "Small box-right":      "GA3",   # Q60 — Far post 6-yard box
    "Box-left":             "CA1",   # Q64 — Near post penalty area
    "Box-centre":           "CA2",   # Q17 — Centre penalty area
    "Box-right":            "CA3",   # Q63 — Far post penalty area
    "Box-deep left":        "Front", # Q65 — Deep wide near-post side
    "Box-deep right":       "Front", # Q62 — Deep wide far-post side
    "Out of box-deep left": "Back",  # Q69 — Behind penalty area near-post
    "Out of box-deep right":"Back",  # Q66 — Behind penalty area far-post
    "Out of box-left":      "Edge",  # Q68 — Edge of box near-post
    "Out of box-centre":    "Edge",  # Q18 — Edge of box centre
    "Out of box-right":     "Edge",  # Q67 — Edge of box far-post
}

# Defensive setup columns
COL_BOTH_POSTS = "Players on both posts"  # Q219
COL_NEAR_POST  = "Player on near post"    # Q220
COL_FAR_POST   = "Player on far post"     # Q221
COL_NO_POSTS   = "No players on posts"    # Q222

# Outcome detection — columns on subsequent events "From corner"
COL_FROM_CORNER = "From corner"

# Event type IDs
TYPE_PASS          = 1
TYPE_INTERCEPTION  = 8   # Opta type 8  — opposing team intercepts
TYPE_CLAIM         = 11  # Opta type 11 — GK catches crossed ball
TYPE_CLEARANCE     = 12  # Opta type 12 — defensive clearance
TYPE_MISS          = 13
TYPE_POST          = 14
TYPE_SAVED         = 15
TYPE_GOAL          = 16

# Columns that flag "leading to" outcomes (on the corner event itself)
COL_LEAD_ATTEMPT = "Leading to attempt"  # Q96
COL_LEAD_GOAL    = "Leading to goal"     # Q95


# ═══════════════════════════════════════════════════════════════════════════════
# INTERNAL HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _is_si(val) -> bool:
    """Return True if the Opta qualifier value is 'Si' (present)."""
    if pd.isna(val):
        return False
    return str(val).strip().lower() in ("si", "yes", "1", "true")


def _load_events(match_csv: Path) -> pd.DataFrame:
    """Load raw Opta CSV and return all events as a DataFrame."""
    try:
        df = pd.read_csv(match_csv, low_memory=False)
    except Exception as exc:
        log.error("Failed to load match CSV %s: %s", match_csv, exc)
        return pd.DataFrame()

    # Normalise numeric fields
    for col in ("type_id", "period_id", "time_min", "time_sec", "event_id", "outcome"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.sort_values(
        ["period_id", "time_min", "time_sec", "event_id"],
        na_position="last",
    ).reset_index(drop=True)
    return df


def _team_mask(df: pd.DataFrame, team: str) -> pd.Series:
    """Boolean mask for rows belonging to the selected team."""
    team_lower = canonical_name(team).lower()
    return df["team_name"].apply(
        lambda v: canonical_name(str(v)).lower() == team_lower
    )


def _classify_delivery(row: pd.Series) -> str:
    """Return delivery type string for a corner kick row.

    Priority order
    --------------
    1. Opta qualifier flags (authoritative when present):
         Inswinger (Q223) → Outswinger (Q224) → Straight (Q225)

    2. Coordinate-based fallback when ALL delivery qualifiers are absent
       (Opta tagging gap, confirmed 2025/2026 Serie A via video analysis).
       Uses Pass End X / Pass End Y to identify the delivery zone:

       ┌─────────────────────────────────────────────────────────────────┐
       │ Zone          │ Opta coords                     │ Label         │
       ├─────────────────────────────────────────────────────────────────┤
       │ Near-flag     │ end_x ≥ 93                      │ Short         │
       │ FrontZone     │ end_x ≥ 83.33                   │ Short         │
       │               │  AND end_y < 21.1 or > 78.9     │               │
       │               │  (wide byline corridor outside   │               │
       │               │   box width — video: short 1-2) │               │
       │ FrontZone2 /  │ end_x < 83.33                   │ Straight      │
       │ Edge          │  (outside box depth — video:     │               │
       │               │   flat driven ground pass)       │               │
       └─────────────────────────────────────────────────────────────────┘
    """
    if _is_si(row.get(COL_INSWINGER)):
        return "Inswinger"
    if _is_si(row.get(COL_OUTSWINGER)):
        return "Outswinger"
    if _is_si(row.get(COL_STRAIGHT)):
        return "Straight"

    # Resolve pass endpoint coordinates
    try:
        end_x = float(row.get("Pass End X"))
    except (TypeError, ValueError):
        end_x = None
    try:
        end_y = float(row.get("Pass End Y"))
    except (TypeError, ValueError):
        end_y = None

    no_cross = not _is_si(row.get(COL_CROSS))
    no_qualifier = (
        no_cross
        and not _is_si(row.get(COL_INSWINGER))
        and not _is_si(row.get(COL_OUTSWINGER))
        and not _is_si(row.get(COL_STRAIGHT))
    )

    if end_x is not None and no_cross:
        # ── Near-flag Short (original rule: ball barely left the flag area) ──
        if end_x >= 93.0:
            return "Short"

        if no_qualifier:
            # ── FrontZone Short (video-verified Group B) ──────────────────────
            # Ball lands inside box depth but outside box width:
            # the wide byline corridor — these are short one-two passes.
            in_front_zone = (
                end_x >= BOX_DEPTH_X
                and end_y is not None
                and (end_y < BOX_WIDTH_L or end_y > BOX_WIDTH_R)
            )
            if in_front_zone:
                return "Short"

            # ── FrontZone2 / Edge Straight (video-verified Group A + Edge) ──
            # Ball lands outside penalty box depth (x < 83.33), regardless
            # of y position — flat driven "Straight" delivery confirmed by
            # video analysis (Group A: outside box width; Edge: central strip).
            if end_x < BOX_DEPTH_X:
                return "Straight"

    return "Unknown"


def _classify_zone_by_coords(end_x: float, end_y: float, is_left_corner: bool) -> str:
    """
    Classify delivery zone from Pass End X/Y coordinates.

    Zones are relative to the corner side:
      GA1 = near-post 6-yard box
      GA2 = centre 6-yard box
      GA3 = far-post 6-yard box
      CA1 = near-post penalty area
      CA2 = centre penalty area
      CA3 = far-post penalty area
      Edge = edge of box (just outside penalty area depth)
      Front = near-post wide strip (outside box width)
      Back  = far-post wide strip (outside box width)
    """
    # 6-yard box depth
    # is_left_corner=True  → flag at Opta y≈100 (fig_x≈100) → near post = HIGH end_y (≥63.2)
    # is_left_corner=False → flag at Opta y≈0   (fig_x≈0)   → near post = LOW  end_y (≤36.8)
    if end_x >= 94.8:
        if is_left_corner:
            if end_y >= SIX_YARD_R:    return "GA1"   # near post (high y side)
            elif end_y >= SIX_YARD_L:  return "GA2"   # centre
            else:                       return "GA3"   # far post
        else:
            if end_y <= SIX_YARD_L:    return "GA1"   # near post (low y side)
            elif end_y <= SIX_YARD_R:  return "GA2"   # centre
            else:                       return "GA3"   # far post

    # Penalty area depth (inside box width)
    if end_x >= 83.33 and 21.1 <= end_y <= 78.9:
        if is_left_corner:
            if end_y >= SIX_YARD_R:    return "CA1"
            elif end_y >= SIX_YARD_L:  return "CA2"
            else:                       return "CA3"
        else:
            if end_y <= SIX_YARD_L:    return "CA1"
            elif end_y <= SIX_YARD_R:  return "CA2"
            else:                       return "CA3"

    # Edge strip – full penalty area width, just outside depth
    if 79.0 <= end_x < 83.33 and 21.1 <= end_y <= 78.9:
        return "Edge"

    # Front / Back (wide strips outside pen-area width)
    if is_left_corner:
        if end_y > 78.9: return "Front"   # near-post wide strip (high y side)
        if end_y < 21.1: return "Back"    # far-post wide strip
    else:
        if end_y < 21.1: return "Front"   # near-post wide strip (low y side)
        if end_y > 78.9: return "Back"    # far-post wide strip

    return "Other"


def _classify_def_setup(row: pd.Series) -> str:
    """Return defensive setup label for a corner kick row."""
    if _is_si(row.get(COL_BOTH_POSTS)):
        return "Both Posts"
    if _is_si(row.get(COL_NEAR_POST)):
        return "Near Post"
    if _is_si(row.get(COL_FAR_POST)):
        return "Far Post"
    if _is_si(row.get(COL_NO_POSTS)):
        return "No Posts"
    return "Unknown"


# Event type IDs to skip when looking for the first touch after a corner
_SETUP_TYPE_IDS: frozenset = frozenset({34, 32, 30, 35, 43})

# Opta types that signal the ball left play or a foul was called
TYPE_OUT          = 5   # Ball out of play (throw-in / goal kick)
TYPE_CORNER_AWARD = 6   # Ball goes out for a corner kick
TYPE_FOUL         = 4   # Foul committed


def _find_receiver(df: pd.DataFrame, corner_idx: int, team_lower: str,
                   period: int) -> Optional[str]:
    """
    Return the player_name of the first same-team touch after the corner.
    Scans the next 15 rows; skips setup/bookkeeping events.
    Returns None if not found.
    """
    window = df.iloc[corner_idx + 1: corner_idx + 16]
    for _, row in window.iterrows():
        if int(row.get("period_id", 0) or 0) != period:
            break
        tid = int(row.get("type_id", 0) or 0)
        if tid in _SETUP_TYPE_IDS:
            continue
        raw_team = str(row.get("team_name", "") or "").strip()
        if canonical_name(raw_team).lower() == team_lower:
            name = str(row.get("player_name", "") or "").strip()
            return name if name else None
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# OUTCOME DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

def _build_from_corner_outcomes(df: pd.DataFrame) -> Dict[str, int]:
    """
    Scan all events for "From corner" qualifier and tally outcomes.

    Returns a dict with keys:
      goal, shot_on_target, shot_off_target, cleared, second_phase
    """
    outcomes = {"goal": 0, "shot_on_target": 0, "shot_off_target": 0,
                "cleared": 0, "second_phase": 0}

    if COL_FROM_CORNER not in df.columns:
        return outcomes

    fc_mask = df[COL_FROM_CORNER].apply(_is_si)
    fc_df   = df[fc_mask]

    for _, row in fc_df.iterrows():
        tid = int(row.get("type_id", 0) or 0)
        if tid == TYPE_GOAL:
            outcomes["goal"] += 1
        elif tid == TYPE_SAVED:
            outcomes["shot_on_target"] += 1
        elif tid in (TYPE_MISS, TYPE_POST):
            outcomes["shot_off_target"] += 1

    # Second phase: "Leading to attempt" on corner events themselves
    if COL_LEAD_ATTEMPT in df.columns:
        outcomes["second_phase"] = int(
            df[df["type_id"] == TYPE_PASS][COL_LEAD_ATTEMPT].apply(_is_si).sum()
        )

    return outcomes


def _corner_outcome(corner_row: pd.Series, next_events: pd.DataFrame,
                    team_lower: str = "") -> str:
    """
    Determine the outcome of a single corner.

    Phase 1 — primary (reliable in ~99 % of Opta data):
        Scan events that carry the "From corner" qualifier.  The first *shot*
        type found determines the outcome.  Non-shot "From corner" events
        (headers, deflections, etc.) are skipped so the search continues
        through the whole sequence.

    Phase 2 — fallback (handles rare tagging gaps):
        If Phase 1 finds no shot, re-scan for the first shot by the
        corner-taking team within 10 seconds.  This catches sequences where
        Opta omitted the qualifier from every event (e.g. corner → clearance
        → immediate rebound shot, all untagged).  Counter-attacks are
        excluded by the same-team filter.
    """
    if next_events.empty:
        return "Cleared"

    period  = corner_row.get("period_id")
    t_start = (float(corner_row.get("time_min", 0) or 0) * 60
               + float(corner_row.get("time_sec", 0) or 0))

    # ── Pre-scan: find first opposing possession change within 25 s ──────────
    # A clearance (12), interception (8) or GK claim (11) by the opposing team
    # ends the direct corner sequence.  Any From-corner-tagged shot AFTER that
    # belongs to second-phase play and must NOT be credited to this corner.
    # We record the cutoff time and whether it was a clearance (→ "Cleared")
    # or another type of possession win (→ "Played On").
    #
    # Fast-path — immediately classify as "Cleared" when:
    #   • Ball goes directly out of play (type 5) or a new corner is awarded
    #     (type 6) within 10 s without a shot — ball in / out without a touch.
    #   • The attacking team commits a foul (type 4, same team) within 10 s.
    for _, row in next_events.iterrows():
        if row.get("period_id") != period:
            break
        r_t = (float(row.get("time_min", 0) or 0) * 60
               + float(row.get("time_sec", 0) or 0))
        if r_t - t_start > 10:
            break
        tid = int(row.get("type_id", 0) or 0)
        if tid in (TYPE_OUT, TYPE_CORNER_AWARD):
            return "Cleared"
        if tid == TYPE_FOUL and team_lower:
            ev_team = canonical_name(
                str(row.get("team_name", "") or "")
            ).lower()
            if ev_team == team_lower:
                return "Cleared"

    cutoff_t            = float("inf")
    cutoff_is_clearance = False

    _POSS_CHANGE_TYPES = (TYPE_CLEARANCE, TYPE_INTERCEPTION, TYPE_CLAIM)

    if team_lower:
        for _, row in next_events.iterrows():
            if row.get("period_id") != period:
                break
            r_t = (float(row.get("time_min", 0) or 0) * 60
                   + float(row.get("time_sec", 0) or 0))
            if r_t - t_start > 25:
                break
            tid     = int(row.get("type_id", 0) or 0)
            ev_team = canonical_name(
                str(row.get("team_name", "") or "")
            ).lower()
            if ev_team != team_lower and tid in _POSS_CHANGE_TYPES:
                cutoff_t = r_t
                # GK claim (11) and clearance (12) both end possession cleanly;
                # interception (8) also treated as Cleared now that Played On
                # is removed — the defending team won the ball regardless.
                cutoff_is_clearance = True
                break

    fc_col_present = COL_FROM_CORNER in next_events.columns

    # ── Phase 1: "From corner"-tagged shots before the cutoff ────────────────
    # Scan the FULL window and keep the *best* outcome found: a goal (incl.
    # own goal) always trumps any earlier shot off target in the sequence.
    # Priority: Own Goal = Goal > Shot on Target > Shot off Target.
    _P1_PRIORITY = {"Own Goal": 4, "Goal": 3, "Shot on Target": 2,
                    "Shot off Target": 1}
    best_p1: Optional[str] = None

    for _, row in next_events.iterrows():
        if row.get("period_id") != period:
            break
        r_t = (float(row.get("time_min", 0) or 0) * 60
               + float(row.get("time_sec", 0) or 0))
        if r_t - t_start > 25:
            break
        if r_t > cutoff_t:
            break  # possession already changed — stop
        if fc_col_present and not _is_si(row.get(COL_FROM_CORNER)):
            continue  # skip untagged events
        tid = int(row.get("type_id", 0) or 0)
        if tid not in (TYPE_GOAL, TYPE_SAVED, TYPE_MISS, TYPE_POST):
            continue
        ev_team = canonical_name(
            str(row.get("team_name", "") or "")
        ).lower()
        if tid == TYPE_GOAL:
            candidate = "Own Goal" if (team_lower and ev_team != team_lower) else "Goal"
        elif tid == TYPE_SAVED:
            candidate = "Shot on Target"
        else:
            candidate = "Shot off Target"
        if _P1_PRIORITY.get(candidate, 0) > _P1_PRIORITY.get(best_p1, 0):
            best_p1 = candidate
        if best_p1 in ("Goal", "Own Goal"):  # can't do better — stop early
            break

    if best_p1 is not None:
        return best_p1

    # ── Phase 2: fallback — same-team shot within 10 s, before the cutoff ────
    # Handles Opta data gaps where "From corner" is absent from every event.
    if team_lower:
        for _, row in next_events.iterrows():
            if row.get("period_id") != period:
                break
            r_t = (float(row.get("time_min", 0) or 0) * 60
                   + float(row.get("time_sec", 0) or 0))
            dt = r_t - t_start
            if dt > 10:
                break
            if r_t > cutoff_t:
                break  # possession already changed — stop
            tid = int(row.get("type_id", 0) or 0)
            if tid not in (TYPE_GOAL, TYPE_SAVED, TYPE_MISS, TYPE_POST):
                continue
            ev_team = canonical_name(
                str(row.get("team_name", "") or "")
            ).lower()
            is_own_goal_p2    = (tid == TYPE_GOAL  and ev_team != team_lower)
            is_attacking_shot = (tid in (TYPE_SAVED, TYPE_MISS, TYPE_POST)
                                 and ev_team == team_lower)
            is_goal           = (tid == TYPE_GOAL  and ev_team == team_lower)
            if is_goal:           return "Goal"
            if is_own_goal_p2:    return "Own Goal"
            if is_attacking_shot:
                if tid == TYPE_SAVED:             return "Shot on Target"
                if tid in (TYPE_MISS, TYPE_POST): return "Shot off Target"

    # ── Fallback ───────────────────────────────────────────────────────────────────────────
    # "Played On" has been removed.  When no shot/goal was found and no
    # possession-type qualifier drove "Second Phase Attack" (handled in the
    # main loop), the corner is classified as Cleared.
    return "Cleared"


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ANALYSIS FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════

def analyse_corner_kicks(match_csv: Path, team: str) -> dict:
    """
    Main entry point.  Returns a dict consumed by ``corner_kicks_card()``.

    Keys
    ----
    corners           : list[dict]   — one entry per corner kick event
    total             : int
    outcomes          : dict         — goal / shot_on_target / shot_off_target /
                                       cleared / second_phase counts
    delivery_counts   : dict[str→int]
    delivery_outcomes : dict[str→dict[str→int]]  — by delivery type
    zone_counts       : dict[str→int]            — diagram zone → count
    def_setup_counts  : dict[str→int]
    """
    empty = {
        "corners": [],
        "total": 0,
        "outcomes": {"goal": 0, "shot_on_target": 0, "shot_off_target": 0,
                     "cleared": 0, "second_phase": 0},
        "delivery_counts": {},
        "delivery_outcomes": {},
        "zone_counts": {},
        "def_setup_counts": {},
    }

    df = _load_events(match_csv)
    if df.empty:
        log.warning("Empty events DataFrame for %s", match_csv)
        return empty

    if "type_id" not in df.columns or COL_CORNER_TAKEN not in df.columns:
        log.warning("Missing required columns in %s", match_csv)
        return empty

    team_lower = canonical_name(team).lower()
    team_mask    = _team_mask(df, team)
    corner_mask  = (df["type_id"] == TYPE_PASS) & df[COL_CORNER_TAKEN].apply(_is_si)
    team_corners = df[team_mask & corner_mask].copy()

    if team_corners.empty:
        return {**empty, "total": 0}

    # ── Per-corner classification ────────────────────────────────────────────
    corners: List[dict] = []
    for idx, row in team_corners.iterrows():
        # Subsequent events (for outcome detection)
        next_ev = df.iloc[idx + 1:idx + 50] if idx + 1 < len(df) else pd.DataFrame()

        delivery  = _classify_delivery(row)
        def_setup = _classify_def_setup(row)
        outcome   = _corner_outcome(row, next_ev, team_lower)

        # ── Second Phase Attack override ─────────────────────────────────────
        # When no direct shot/goal was detected (outcome is still "Cleared"),
        # promote to "Second Phase Attack" if:
        #   • The corner row carries Q96 ("Leading to attempt") qualifier, OR
        #   • The delivery was "Short" (short corners are by definition indirect).
        if outcome == "Cleared":
            if _is_si(row.get(COL_LEAD_ATTEMPT)) or delivery == "Short":
                outcome = "Second Phase Attack"

        # Corner flag start position (Opta coords)
        start_x = float(row.get("x", 99.5) or 99.5)
        start_y = float(row.get("y", 50.0) or 50.0)
        is_left_corner = start_y >= 50  # Opta y≈100 = left touchline = left corner

        # Ball delivery destination (Pass End X/Y)
        end_x_raw = row.get("Pass End X")
        end_y_raw = row.get("Pass End Y")
        end_x = float(end_x_raw) if pd.notna(end_x_raw) else None
        end_y = float(end_y_raw) if pd.notna(end_y_raw) else None

        # Coordinate-based zone classification
        zone = _classify_zone_by_coords(end_x, end_y, is_left_corner) \
               if (end_x is not None and end_y is not None) else "Unknown"

        # Taker & receiver
        taker    = str(row.get("player_name", "") or "").strip() or None
        period_i = int(row.get("period_id", 1) or 1)
        receiver = _find_receiver(df, idx, team_lower, period_i)

        # When cleared or an own goal, the defending team touched the ball
        # first — suppress receiver so the hover only shows Taker / Type / Zone.
        if outcome in ("Cleared", "Own Goal"):
            receiver = None

        corners.append({
            "minute":       int(row.get("time_min", 0) or 0),
            "period":       period_i,
            "delivery":     delivery,
            "zone":         zone,
            "def_setup":    def_setup,
            "outcome":      outcome,
            "start_x":      start_x,
            "start_y":      start_y,
            "end_x":        end_x,
            "end_y":        end_y,
            "taker":        taker,
            "receiver":     receiver,
            "is_left":      is_left_corner,
        })

    # ── Aggregate outcomes ───────────────────────────────────────────────────
    outcomes = {"goal": 0, "shot_on_target": 0, "shot_off_target": 0,
                "cleared": 0, "second_phase": 0}
    for c in corners:
        oc = c["outcome"]
        if oc in ("Goal", "Own Goal"):
            outcomes["goal"] += 1
        elif oc == "Shot on Target":
            outcomes["shot_on_target"] += 1
        elif oc == "Shot off Target":
            outcomes["shot_off_target"] += 1
        elif oc == "Second Phase Attack":
            outcomes["second_phase"] += 1
        else:  # "Cleared"
            outcomes["cleared"] += 1

    # ── Delivery type breakdown ──────────────────────────────────────────────
    delivery_types = ["Inswinger", "Outswinger", "Straight", "Short", "Unknown"]
    delivery_counts: Dict[str, int] = {d: 0 for d in delivery_types}
    delivery_outcomes: Dict[str, Dict[str, int]] = {
        d: {"Goal": 0, "Own Goal": 0, "Shot on Target": 0, "Shot off Target": 0,
            "Cleared": 0, "Second Phase Attack": 0}
        for d in delivery_types
    }
    for c in corners:
        d = c["delivery"]
        delivery_counts[d] = delivery_counts.get(d, 0) + 1
        delivery_outcomes[d][c["outcome"]] = delivery_outcomes[d].get(c["outcome"], 0) + 1

    # ── Zone counts ─────────────────────────────────────────────────────────
    all_zones = ["GA1", "GA2", "GA3", "CA1", "CA2", "CA3", "Front", "Back", "Edge", "Unknown"]
    zone_counts: Dict[str, int] = {z: 0 for z in all_zones}
    for c in corners:
        z = c["zone"]
        zone_counts[z] = zone_counts.get(z, 0) + 1

    # ── Defensive setup ─────────────────────────────────────────────────────
    def_setup_counts: Dict[str, int] = {}
    for c in corners:
        ds = c["def_setup"]
        def_setup_counts[ds] = def_setup_counts.get(ds, 0) + 1

    return {
        "corners":           corners,
        "total":             len(corners),
        "outcomes":          outcomes,
        "delivery_counts":   delivery_counts,
        "delivery_outcomes": delivery_outcomes,
        "zone_counts":       zone_counts,
        "def_setup_counts":  def_setup_counts,
    }
