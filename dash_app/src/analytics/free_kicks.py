"""
Free Kicks Analysis — Set Pieces Phase
========================================
Analyses free kick events from Opta event CSV files.

Free kick detection:
  • FK pass delivery : type_id == 1  + qualifier "Free kick taken" == "Si"  (Q5)
  • Direct FK shot   : type_id in (13/14/15/16) + qualifier "Free kick" == "Si" (Q26)
  Penalties (Q9) are excluded from both buckets.

FK type classification (pass deliveries):
  Crossed into Box  → Q2  (Cross)
  Chipped / Lofted  → Q155 (Chipped)
  Long Ball         → Q1  (Long ball)
  Launch            → Q157 (Launch)
  Short             → none of the above

Outputs:
  • Volume & outcomes summary (KPI row)
  • Delivery type breakdown (counts + outcome table)
  • Direct shots      → pitch map (origin) + goalmouth figure + descriptors
  • Deliveries        → pitch map (origin → landing) + zone table

Coordinate system (Opta):
  x : 0 → 100  (own goal → opponent goal)
  y : 0 → 100  (right touchline → left touchline)
  Goalmouth Q102 (Y) : full-pitch Y coordinate; goal posts at Y≈44.62 (GK-right) and Y≈55.38 (GK-left).
                        Lower Q102 = GK’s right;  Higher Q102 = GK’s left.
  Goalmouth Q103 (Z) : height scale; Low/High zone boundary ≈20.  figure_y = Q103 × 2.5
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from src.team_mapping import canonical_name

log = logging.getLogger("dashboard.free_kicks")

# ═══════════════════════════════════════════════════════════════════════════════
# COLUMN NAMES — Opta flat-CSV qualifier column headers
# ═══════════════════════════════════════════════════════════════════════════════

# FK detection
COL_FK_TAKEN  = "Free kick taken"   # Q5  — on pass events
COL_FREE_KICK = "Free kick"         # Q26 — on shot events (direct FK)
COL_SET_PIECE = "Set piece"         # Q24 — pattern-of-play on FK-derived shots
COL_PENALTY   = "Penalty"           # Q9  — exclude penalties

# FK delivery type qualifiers (on pass events)
COL_CROSS      = "Cross"            # Q2
COL_CHIPPED    = "Chipped"          # Q155
COL_LONG_BALL  = "Long ball"        # Q1
COL_LAUNCH     = "Launch"           # Q157
COL_CORNER_SIT = "Corner situation" # Q96  — second phase
COL_ASSIST_COL = "Assist"           # Q210 — pass was an assist

# FK delivery spin / swing qualifiers
COL_INSWINGER  = "Inswinger"        # Q223
COL_OUTSWINGER = "Outswinger"       # Q224
COL_STRAIGHT   = "Straight"         # Q225

# ── Delivery qualifier columns shown in hover  →  display label ───────────
DELIVERY_QUAL_COLS: Dict[str, str] = {
    "Inswinger":    "Inswinger",
    "Outswinger":   "Outswinger",
    "Straight":     "Straight",
    "Chipped":      "Chipped",
    "Right footed": "Right Foot",
    "Left footed":  "Left Foot",
    "Head":         "Header",
}

# Goalmouth coordinate columns
COL_GM_Y = "Goal Mouth Y Coordinate"  # Q102  full-pitch Y where ball crossed line (lower=GK-right, higher=GK-left)
COL_GM_Z = "Goal Mouth Z Coordinate"  # Q103  height scale; Low/High boundary ≈20; figure_y = Q103×2.5

# Miss-direction qualifier columns (Q73/Q74/Q75 — from ATTACKER'S perspective)
# In the goalmouth figure (GK POV): Q73 Left → right side of figure (x>100),
#                                    Q75 Right → left side of figure (x<0),
#                                    Q74 High  → above crossbar (y>100).
COL_MISS_LEFT  = "Left"   # Q73: missed/hit left of goal (attacker's left = GK's right)
COL_MISS_HIGH  = "High"   # Q74: over the bar
COL_MISS_RIGHT = "Right"  # Q75: missed/hit right of goal (attacker's right = GK's left)
COL_BLOCKED   = "Blocked"              # Q82   shot was blocked by outfield player
COL_BLOCKED_X = "Blocked X Coordinate" # Q146  Opta x of block point
COL_BLOCKED_Y = "Blocked Y Coordinate" # Q147  Opta y of block point

# Pass destination columns
COL_PASS_END_X = "Pass End X"   # Q140
COL_PASS_END_Y = "Pass End Y"   # Q141

# ── Delivery zone columns  →  display label ────────────────────────────────
ZONE_COLS: Dict[str, str] = {
    "Small box-centre":      "SB-Centre",
    "Small box-right":       "SB-Right",
    "Small box-left":        "SB-Left",
    "Box-centre":            "Box-Centre",
    "Box-right":             "Box-Right",
    "Box-left":              "Box-Left",
    "Box-deep right":        "Box-Deep-R",
    "Box-deep left":         "Box-Deep-L",
    "Out of box-centre":     "OOB-Centre",
    "Out of box-right":      "OOB-Right",
    "Out of box-left":       "OOB-Left",
    "Out of box-deep right": "OOB-Deep-R",
    "Out of box-deep left":  "OOB-Deep-L",
    "35+ centre":            "35+-Centre",
    "35+ right":             "35+-Right",
    "35+ left":              "35+-Left",
}

# ── Goalmouth zone qualifier columns  →  display label ────────────────────
GOALMOUTH_ZONE_COLS: Dict[str, str] = {
    "Low Left":      "Low Left",
    "Low Centre":    "Low Centre",
    "Low Right":     "Low Right",
    "High Left":     "High Left",
    "High Centre":   "High Centre",
    "High Right":    "High Right",
    "Blocked":       "Blocked",
    "Hit Woodwork":  "Woodwork",
    "Saved Off Line": "Saved Off Line",
}

# Estimated centre coordinates for goalmouth zones stored as (gm_y, gm_z) i.e.
# (Q102, Q103) fallback values.  _gm_to_fig(gm_y, gm_z) in set_piece_cards.py
# transforms these to figure coordinates:
#   figure_x = (55.38 - gm_y) / 10.76 * 100
#   figure_y = gm_z * 2.5
# Zone centres in figure coords: Low L=(16.7,25), Low C=(50,25), Low R=(83.3,25),
#                                 High L=(16.7,75), High C=(50,75), High R=(83.3,75)
GOALMOUTH_ZONE_POSITIONS: Dict[str, tuple] = {
    "Low Left":       (53.6, 10.0),   # fig (16.7, 25)
    "Low Centre":     (50.0, 10.0),   # fig (50,   25)
    "Low Right":      (46.4, 10.0),   # fig (83.3, 25)
    "High Left":      (53.6, 30.0),   # fig (16.7, 75)
    "High Centre":    (50.0, 30.0),   # fig (50,   75)
    "High Right":     (46.4, 30.0),   # fig (83.3, 75)
    "Blocked":        (50.0, 20.0),   # fig (50,   50)
    "Woodwork":       (50.0, 38.0),   # fig (50,   95)
    "Saved Off Line": (50.0,  2.0),   # fig (50,    5)
}

# ── Body part qualifier columns  →  display label ─────────────────────────
BODY_PART_COLS: Dict[str, str] = {
    "Right footed": "Right Foot",
    "Left footed":  "Left Foot",
    "Head":         "Header",
}

# ── Shot descriptor qualifier columns  →  display label ───────────────────
SHOT_DESC_COLS: Dict[str, str] = {
    "Strong":       "Strong",
    "Weak":         "Weak",
    "Rising":       "Rising",
    "Dipping":      "Dipping",
    "Swerve Left":  "Swerve Left",
    "Swerve Right": "Swerve Right",
    "Big Chance":   "Big Chance",
    "Deflection":   "Deflected",
}

# ── Event type IDs ─────────────────────────────────────────────────────────
TYPE_PASS  = 1
TYPE_MISS  = 13
TYPE_POST  = 14
TYPE_SAVED = 15
TYPE_GOAL  = 16
SHOT_TYPES = frozenset({TYPE_MISS, TYPE_POST, TYPE_SAVED, TYPE_GOAL})

# ── FK type display order ──────────────────────────────────────────────────
FK_TYPE_ORDER: List[str] = [
    "Direct Shot",
    "Crossed into Box",
    "Chipped / Lofted",
    "Long Ball",
    "Short",
    "Launch",
    "Unknown",
]

# ═══════════════════════════════════════════════════════════════════════════════
# INTERNAL HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _is_si(val) -> bool:
    """Return True when an Opta qualifier value is 'Si' (present)."""
    if pd.isna(val):
        return False
    return str(val).strip().lower() in ("si", "yes", "1", "true")


def _load_events(match_csv: Path) -> pd.DataFrame:
    try:
        df = pd.read_csv(match_csv, low_memory=False)
    except Exception as exc:
        log.error("Failed to load %s: %s", match_csv, exc)
        return pd.DataFrame()
    for col in ("type_id", "period_id", "time_min", "time_sec", "event_id", "outcome"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.sort_values(
        ["period_id", "time_min", "time_sec", "event_id"],
        na_position="last",
    ).reset_index(drop=True)


def _team_mask(df: pd.DataFrame, team: str) -> pd.Series:
    team_lower = canonical_name(team).lower()
    return df["team_name"].apply(
        lambda v: canonical_name(str(v)).lower() == team_lower
    )


def _classify_fk_delivery_type(row: pd.Series) -> str:
    """Return the delivery-type label for a FK pass row."""
    if _is_si(row.get(COL_CROSS)):
        return "Crossed into Box"
    if _is_si(row.get(COL_CHIPPED)):
        return "Chipped / Lofted"
    if _is_si(row.get(COL_LONG_BALL)):
        return "Long Ball"
    if _is_si(row.get(COL_LAUNCH)):
        return "Launch"
    return "Short"


def _get_zone(row: pd.Series) -> Optional[str]:
    for col, label in ZONE_COLS.items():
        if col in row.index and _is_si(row.get(col)):
            return label
    return None


def _get_goalmouth_zone(row: pd.Series) -> Optional[str]:
    for col, label in GOALMOUTH_ZONE_COLS.items():
        if col in row.index and _is_si(row.get(col)):
            return label
    return None


def _get_body_part(row: pd.Series) -> Optional[str]:
    for col, label in BODY_PART_COLS.items():
        if col in row.index and _is_si(row.get(col)):
            return label
    return None


def _get_descriptors(row: pd.Series) -> List[str]:
    return [label for col, label in SHOT_DESC_COLS.items()
            if col in row.index and _is_si(row.get(col))]


def _get_delivery_qualifiers(row: pd.Series) -> List[str]:
    """Return list of delivery qualifier labels (spin, foot, etc.) for hover."""
    return [label for col, label in DELIVERY_QUAL_COLS.items()
            if col in row.index and _is_si(row.get(col))]


def _shot_outcome_from_type(type_id: int) -> str:
    return {
        TYPE_GOAL:  "Goal",
        TYPE_SAVED: "Shot on Target",
        TYPE_MISS:  "Shot off Target",
        TYPE_POST:  "Hit Post",
    }.get(type_id, "Unknown")


_SKIP_TYPE_IDS = frozenset({32, 34, 30, 35, 43, 71})

# ── Opta type IDs relevant to FK delivery outcome classification ───────────────
# OPP defensive actions that immediately end the delivery sequence ("Cleared")
_OPP_DISRUPT_TYPES = frozenset({
    12,   # Clearance          — opponent heads/kicks the ball away
    8,    # Interception       — opponent cuts the pass before it reaches anyone
    11,   # Claim              — GK catches the cross
    74,   # Blocked Pass       — opponent close-blocks the delivery
    52,   # Keeper Pick-up     — GK collects the ball (short FK, ball rolls to GK)
})
# Ball permanently out of play
_OUT_TYPES    = frozenset({5, 6})   # Out, Corner Awarded
_AERIAL_TYPE  = 44
_FOUL_TYPE    = 4


def _find_receiver(
    df: pd.DataFrame,
    fk_idx: int,
    team_lower: str,
    period: int,
) -> Optional[str]:
    """
    Return the player_name of the first same-team touch after the FK.
    Scans the next 15 rows; skips bookkeeping events.
    """
    window = df.iloc[fk_idx + 1: fk_idx + 16]
    for _, row in window.iterrows():
        if int(row.get("period_id", 0) or 0) != period:
            break
        tid = int(row.get("type_id", 0) or 0)
        if tid in _SKIP_TYPE_IDS:
            continue
        raw_team = str(row.get("team_name", "") or "").strip()
        if canonical_name(raw_team).lower() == team_lower:
            name = str(row.get("player_name", "") or "").strip()
            return name if name else None
    return None


def _fk_delivery_outcome_and_chain(
    df: pd.DataFrame,
    fk_idx: int,
    period: int,
    t_start: float,
    team_lower: str,
) -> tuple:
    """
    Classify the outcome of a FK pass delivery by tracing the event chain.

    Taxonomy (in order of precedence):
    ─────────────────────────────────────────────────────────────────────────────
    Any OPP defensive action encountered → terminates the sequence immediately:

      Cleared          — OPP clearance (12), interception (8), GK claim (11),
                         blocked pass (74), GK pick-up (52), or aerial won (44/oc=1)
      Foul Won         — OPP commits a foul (4) → team wins free kick
      Cleared / No Shot — ball goes out of play (5/6); or OPP shot (ball lost)

    TEAM actions advance the chain:
      Goal             — team scores (16)
      Shot on Target   — team's saved shot (15)
      Shot off Target  — team miss (13)
      Hit Post         — team hits post (14)
      [team touches]   — continue scanning

    Window expires (12 s) without an OPP disruption:
      Second Phase     — team_touched is True  (team maintained possession)
      Cleared / No Shot — team never touched   (ball drifted away)
    """
    chain: list = []
    team_touched = False

    for j in range(fk_idx + 1, min(fk_idx + 80, len(df))):
        row = df.iloc[j]

        # ── Period boundary ─────────────────────────────────────────────────
        if int(row.get("period_id", 0) or 0) != period:
            break

        # ── 12-second window ────────────────────────────────────────────────
        r_t = (float(row.get("time_min", 0) or 0) * 60
               + float(row.get("time_sec", 0) or 0))
        if r_t - t_start > 12.0:
            break

        # ── Skip bookkeeping events ──────────────────────────────────────────
        tid = int(row.get("type_id", 0) or 0)
        if tid in _SKIP_TYPE_IDS:
            continue

        is_team = (
            canonical_name(str(row.get("team_name", "") or "")).lower()
            == team_lower
        )
        et = str(row.get("event") or row.get("event_type") or "").strip().lower()

        chain.append({
            "player":     str(row.get("player_name", "") or "?").strip(),
            "event_type": et,
            "is_team":    is_team,
            "minute":     int(row.get("time_min", 0) or 0),
            "second":     int(row.get("time_sec", 0) or 0),
            "x":          float(row["x"]) if pd.notna(row.get("x")) else None,
            "y":          float(row["y"]) if pd.notna(row.get("y")) else None,
        })

        # ════════════════════════════════════════════════════════════════════
        # OPP events — each one terminates the delivery sequence
        # ════════════════════════════════════════════════════════════════════
        if not is_team:

            # Foul committed by OPP → team wins free kick
            if tid == _FOUL_TYPE:
                return "Foul Won", chain

            # Ball permanently out of play (throw-in / goal kick / corner)
            if tid in _OUT_TYPES:
                return "Cleared / No Shot", chain

            # OPP defensive disruption — delivery was not successful
            if tid in _OPP_DISRUPT_TYPES:
                return "Cleared", chain

            # Aerial duel by OPP
            if tid == _AERIAL_TYPE:
                if int(row.get("outcome", 0) or 0) == 1:
                    # OPP won the header → delivery cleared
                    return "Cleared", chain
                # OPP lost the aerial → treat as team winning it
                team_touched = True
                continue

            # OPP shot means we've completely lost possession
            if tid in SHOT_TYPES:
                return "Cleared / No Shot", chain

            # Any other OPP ball-play event (pass etc.) also terminates
            # possession gained in the delivery phase
            if tid in (TYPE_PASS, 3, 49, 50, 61):
                return "Cleared / No Shot", chain

        # ════════════════════════════════════════════════════════════════════
        # TEAM events — advance the chain
        # ════════════════════════════════════════════════════════════════════
        else:
            team_touched = True

            # Team shot → classify by event type
            if tid in SHOT_TYPES:
                return _shot_outcome_from_type(tid), chain

    # ── Time window expired ──────────────────────────────────────────────────
    if team_touched:
        return "Second Phase", chain
    return "Cleared / No Shot", chain


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ANALYSIS FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════

def analyse_free_kicks(match_csv: Path, team: str) -> dict:
    """
    Main entry point — returns a dict consumed by ``free_kicks_card()``.

    Keys
    ----
    free_kicks          : list[dict]  — one entry per FK event (pass OR direct shot)
    direct_shots        : list[dict]  — subset: direct FK shots only
    deliveries          : list[dict]  — subset: FK pass deliveries only
    total               : int
    outcomes            : dict[str→int]   — outcome label → count
    fk_type_counts      : dict[str→int]
    fk_type_outcomes    : dict[str→dict[str→int]]
    zone_counts         : dict[str→int]   — delivery landing zone → count
    goalmouth_zone_counts : dict[str→int]
    body_part_counts    : dict[str→int]
    descriptor_counts   : dict[str→int]
    """
    empty = {
        "free_kicks": [], "direct_shots": [], "deliveries": [],
        "total": 0, "outcomes": {}, "fk_type_counts": {}, "fk_type_outcomes": {},
        "zone_counts": {}, "goalmouth_zone_counts": {},
        "body_part_counts": {}, "descriptor_counts": {},
    }

    df = _load_events(match_csv)
    if df.empty:
        log.warning("Empty DataFrame for %s", match_csv)
        return empty

    if "type_id" not in df.columns:
        log.warning("Missing type_id column in %s", match_csv)
        return empty

    team_lower  = canonical_name(team).lower()
    team_mask   = _team_mask(df, team)
    pen_col_ok  = COL_PENALTY in df.columns

    # ── Direct FK shots: type_id in (13,14,15,16) + Q26, exclude Q9 ─────────
    direct_shots_rows = pd.DataFrame()
    if COL_FREE_KICK in df.columns:
        dmask = df["type_id"].isin(SHOT_TYPES) & df[COL_FREE_KICK].apply(_is_si)
        if pen_col_ok:
            dmask &= ~df[COL_PENALTY].apply(_is_si)
        direct_shots_rows = df[team_mask & dmask].copy()

    # ── FK pass deliveries: type_id == 1 + Q5, exclude Q9 ───────────────────
    fk_pass_rows = pd.DataFrame()
    if COL_FK_TAKEN in df.columns:
        pmask = (df["type_id"] == TYPE_PASS) & df[COL_FK_TAKEN].apply(_is_si)
        if pen_col_ok:
            pmask &= ~df[COL_PENALTY].apply(_is_si)
        fk_pass_rows = df[team_mask & pmask].copy()

    if direct_shots_rows.empty and fk_pass_rows.empty:
        return empty

    free_kicks:   List[dict] = []
    direct_shots: List[dict] = []
    deliveries:   List[dict] = []

    # ── Process direct FK shots ──────────────────────────────────────────────
    for idx, row in direct_shots_rows.iterrows():
        # Skip FKs taken from own half — not relevant to offensive analysis
        if float(row.get("x", 0) or 0) < 50:
            continue

        tid     = int(row.get("type_id", 0) or 0)
        outcome = _shot_outcome_from_type(tid)

        # A blocked shot (Q82) is stopped by an outfield player before reaching the GK.
        # Override outcome and use block coordinates as the ball's end point on the pitch.
        is_blocked = _is_si(row.get(COL_BLOCKED))
        if is_blocked:
            outcome = "Blocked"

        gm_y_raw = row.get(COL_GM_Y)
        gm_z_raw = row.get(COL_GM_Z)
        gm_y = float(gm_y_raw) if pd.notna(gm_y_raw) else None
        gm_z = float(gm_z_raw) if pd.notna(gm_z_raw) else None

        gm_zone = _get_goalmouth_zone(row)

        # Blocked shots never reach the goal — suppress goalmouth plotting
        if is_blocked:
            gm_y = gm_z = gm_zone = None
        elif gm_y is None and gm_zone in GOALMOUTH_ZONE_POSITIONS:
            # Fall back to zone-centre coordinates when Q102/Q103 absent
            gm_y, gm_z = GOALMOUTH_ZONE_POSITIONS[gm_zone]

        # Miss direction qualifiers (Q73/Q74/Q75): only meaningful for TYPE_MISS
        miss_left  = tid == TYPE_MISS and _is_si(row.get(COL_MISS_LEFT))
        miss_high  = tid == TYPE_MISS and _is_si(row.get(COL_MISS_HIGH))
        miss_right = tid == TYPE_MISS and _is_si(row.get(COL_MISS_RIGHT))

        # Trajectory end point: block coords for blocked shots; for on-target shots
        # we can derive pitch endpoint from blocked coords or leave None (line omitted).
        bx_raw = row.get(COL_BLOCKED_X)
        by_raw = row.get(COL_BLOCKED_Y)
        traj_end_x = float(bx_raw) if is_blocked and pd.notna(bx_raw) else None
        traj_end_y = float(by_raw) if is_blocked and pd.notna(by_raw) else None

        entry: dict = {
            "minute":         int(row.get("time_min", 0) or 0),
            "period":         int(row.get("period_id", 1) or 1),
            "fk_type":        "Direct Shot",
            "outcome":        outcome,
            "start_x":        float(row.get("x", 85) or 85),
            "start_y":        float(row.get("y", 50) or 50),
            "end_x":          traj_end_x,
            "end_y":          traj_end_y,
            "zone":           None,
            "goalmouth_zone": gm_zone,
            "goalmouth_y":    gm_y,
            "goalmouth_z":    gm_z,
            "body_part":      _get_body_part(row),
            "descriptors":    _get_descriptors(row),
            "taker":          str(row.get("player_name", "") or "").strip() or None,
            "receiver":        None,
            "is_blocked":     is_blocked,
            "is_direct_shot": True,
            "miss_left":      miss_left,
            "miss_high":      miss_high,
            "miss_right":     miss_right,
        }
        direct_shots.append(entry)
        free_kicks.append(entry)

    # ── Process FK pass deliveries ───────────────────────────────────────────
    for idx, row in fk_pass_rows.iterrows():
        # Skip FKs taken from own half — not relevant to offensive analysis
        if float(row.get("x", 0) or 0) < 50:
            continue

        fk_type  = _classify_fk_delivery_type(row)
        period   = int(row.get("period_id", 1) or 1)
        t_start  = float(row.get("time_min", 0) or 0) * 60 + float(row.get("time_sec", 0) or 0)

        outcome, chain = _fk_delivery_outcome_and_chain(
            df, idx, period, t_start, team_lower
        )

        end_x_raw = row.get(COL_PASS_END_X)
        end_y_raw = row.get(COL_PASS_END_Y)
        end_x = float(end_x_raw) if pd.notna(end_x_raw) else None
        end_y = float(end_y_raw) if pd.notna(end_y_raw) else None

        entry = {
            "minute":         int(row.get("time_min", 0) or 0),
            "period":         period,
            "fk_type":        fk_type,
            "outcome":        outcome,
            "start_x":        float(row.get("x", 80) or 80),
            "start_y":        float(row.get("y", 50) or 50),
            "end_x":          end_x,
            "end_y":          end_y,
            "zone":           _get_zone(row),
            "goalmouth_zone": None,
            "goalmouth_y":    None,
            "goalmouth_z":    None,
            "body_part":      None,
            "descriptors":    [],
            "qualifiers":     _get_delivery_qualifiers(row),
            "chain":          chain,
            "taker":          str(row.get("player_name", "") or "").strip() or None,
            "receiver":       _find_receiver(df, idx, team_lower, period),
            "is_direct_shot": False,
        }
        deliveries.append(entry)
        free_kicks.append(entry)

    if not free_kicks:
        return empty

    # ── Aggregate counts ─────────────────────────────────────────────────────
    outcomes: Dict[str, int] = {}
    fk_type_counts: Dict[str, int] = {}
    fk_type_outcomes: Dict[str, Dict[str, int]] = {}

    for fk in free_kicks:
        oc = fk["outcome"]
        t  = fk["fk_type"]
        outcomes[oc] = outcomes.get(oc, 0) + 1
        fk_type_counts[t] = fk_type_counts.get(t, 0) + 1
        if t not in fk_type_outcomes:
            fk_type_outcomes[t] = {}
        fk_type_outcomes[t][oc] = fk_type_outcomes[t].get(oc, 0) + 1

    zone_counts: Dict[str, int] = {}
    for fk in deliveries:
        z = fk.get("zone")
        if z:
            zone_counts[z] = zone_counts.get(z, 0) + 1

    gm_zone_counts: Dict[str, int] = {}
    body_part_counts: Dict[str, int] = {}
    descriptor_counts: Dict[str, int] = {}

    for fk in direct_shots:
        gz = fk.get("goalmouth_zone")
        if gz:
            gm_zone_counts[gz] = gm_zone_counts.get(gz, 0) + 1
        bp = fk.get("body_part")
        if bp:
            body_part_counts[bp] = body_part_counts.get(bp, 0) + 1
        for d in fk.get("descriptors", []):
            descriptor_counts[d] = descriptor_counts.get(d, 0) + 1

    return {
        "free_kicks":            free_kicks,
        "direct_shots":          direct_shots,
        "deliveries":            deliveries,
        "total":                 len(free_kicks),
        "outcomes":              outcomes,
        "fk_type_counts":        fk_type_counts,
        "fk_type_outcomes":      fk_type_outcomes,
        "zone_counts":           zone_counts,
        "goalmouth_zone_counts": gm_zone_counts,
        "body_part_counts":      body_part_counts,
        "descriptor_counts":     descriptor_counts,
    }
