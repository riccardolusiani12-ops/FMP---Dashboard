"""
Defensive Phase — D3: Defensive Castle (Own Defensive Third)
=============================================================
Quantifies all defensive actions made by the defending team INSIDE their
own defensive third (x < 33.33 in the team's coordinate frame).

Opta defensive action event type IDs used
─────────────────────────────────────────
  4   Foul        — committed only (outcome == 0)
  7   Tackle
  8   Interception
  12  Clearance
  44  Aerial      — aerial duel
  45  Challenge   — failed to dispossess opponent who dribbled past
  49  Ball Recovery
  74  Blocked Pass

Coordinate system (Opta, **from the analysed team's perspective**):
  x : 0 = own goal-line   → 100 = opponent goal-line
  y : 0 = right touchline → 100 = left touchline  (broadcast view)

Defensive third:  x ∈ [0, 33.33)
  Zones 1-3  → x ∈ [0, 16.67)   — deep defensive block (own box area)
  Zones 4-6  → x ∈ [16.67, 33.33) — edge of defensive third

Within each x-band, three y-corridors:
  Left   → y ∈ (66.67, 100]
  Centre → y ∈ [33.33, 66.67]
  Right  → y ∈ [0, 33.33)

Own box boundary (Opta):  x ∈ [0, 16.5],  y ∈ [21, 79]
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from src.analytics.goalkeeper_buildup import (
    _load_match_events,
    xy_to_zone,
)
from src.team_mapping import canonical_name

log = logging.getLogger("dashboard.defensive_castle")

# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

# Defensive third threshold (x-axis, team's own perspective)
DEF_THIRD_X_MAX: float = 33.33

# Own penalty box boundaries (Opta standard)
OWN_BOX_X_MAX: float = 16.5
OWN_BOX_Y_MIN: float = 21.0
OWN_BOX_Y_MAX: float = 79.0

# Corridor boundaries
LEFT_Y_MIN:   float = 66.67
RIGHT_Y_MAX:  float = 33.33

# Sub-zone x boundary inside defensive third
DEEP_X_MAX: float = 16.67   # x < 16.67  → deep / box-level zone

# Action type IDs
CASTLE_ACTION_IDS: frozenset[int] = frozenset({4, 7, 8, 12, 44, 45, 49, 74})
FOUL_TYPE_ID:      int             = 4
AERIAL_TYPE_ID:    int             = 44

# Aerial duels (type_id=44) at x >= this threshold are opponent-box attacking
# header contests (from corners, crosses, set pieces) — NOT defensive actions.
# This is shared with defensive_pressing.py for consistency.
AERIAL_OPP_BOX_X_MIN: float = 83.33

# Human-readable labels per event type
ACTION_LABELS: dict[int, str] = {
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
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _corridor(y: float) -> str:
    if y > LEFT_Y_MIN:
        return "L"
    if y < RIGHT_Y_MAX:
        return "R"
    return "C"


def _subzone(x: float, y: float) -> str:
    """Classify action into 'box', 'deep_flank', or 'def_third_edge'."""
    if x <= OWN_BOX_X_MAX and OWN_BOX_Y_MIN <= y <= OWN_BOX_Y_MAX:
        return "box"
    if x <= DEEP_X_MAX:
        return "deep_flank"
    return "def_third_edge"


def _is_castle_action(row: pd.Series) -> bool:
    """
    Return True for genuine defensive actions inside the defensive third.

    Aerial duels (type_id=44) at x >= 83.33 (opponent box) are attacking
    header contests and are excluded. In practice D3 already filters x < 33.33,
    so this guard is defensive-in-depth for consistency with D1.
    """
    tid = row.get("type_id")
    if pd.isna(tid):
        return False
    tid = int(tid)
    if tid not in CASTLE_ACTION_IDS:
        return False
    # Fouls: only the committed side (outcome == 0)
    if tid == FOUL_TYPE_ID:
        try:
            return int(row.get("outcome", 0)) == 0
        except (ValueError, TypeError):
            return False
    # Aerials in opponent box are attacking headers, not defensive actions
    if tid == AERIAL_TYPE_ID:
        try:
            return float(row.get("x", 0) or 0) < AERIAL_OPP_BOX_X_MIN
        except (ValueError, TypeError):
            return False
    return True


def _safe_x(row: pd.Series) -> float | None:
    try:
        return float(row["x"])
    except (KeyError, TypeError, ValueError):
        return None


def _safe_y(row: pd.Series) -> float | None:
    try:
        return float(row["y"])
    except (KeyError, TypeError, ValueError):
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def analyse_defensive_castle(match_csv: Path, team: str) -> dict[str, Any]:
    """
    Compute D3 Defensive Castle metrics for *team* in the given match CSV.

    Returns a flat dict consumed by ``defensive_castle_card()``.
    """
    team_lower = canonical_name(str(team)).lower()

    df = _load_match_events(match_csv)
    if df.empty:
        return _empty_result()

    if "type_id" in df.columns:
        df["type_id"] = pd.to_numeric(df["type_id"], errors="coerce")
    if "outcome" in df.columns:
        df["outcome"] = pd.to_numeric(df["outcome"], errors="coerce")

    # Filter to selected team
    team_mask = df["team_name"].apply(
        lambda t: canonical_name(str(t).strip()).lower() == team_lower
    )
    team_df = df[team_mask].copy()

    # Filter to defensive actions in the defensive third
    castle_rows: list[dict] = []
    for _, row in team_df.iterrows():
        if not _is_castle_action(row):
            continue
        x = _safe_x(row)
        y = _safe_y(row)
        if x is None or y is None:
            continue
        if x >= DEF_THIRD_X_MAX:
            continue  # outside defensive third

        tid    = int(row["type_id"])
        label  = ACTION_LABELS.get(tid, f"Type {tid}")
        corr   = _corridor(y)
        sub    = _subzone(x, y)
        zone   = xy_to_zone(x, y)

        try:
            minute = int(row.get("min", row.get("minute", 0)))
        except (ValueError, TypeError):
            minute = 0
        player = str(row.get("player_name", row.get("player", "?")))

        castle_rows.append({
            "x":       x,
            "y":       y,
            "type_id": tid,
            "action":  label,
            "corridor": corr,
            "subzone": sub,
            "zone":    zone,
            "minute":  minute,
            "player":  player,
        })

    if not castle_rows:
        return _empty_result()

    # ── Aggregates ────────────────────────────────────────────────────────────
    total = len(castle_rows)

    # By action type
    by_type: dict[str, int] = {}
    for rec in castle_rows:
        by_type[rec["action"]] = by_type.get(rec["action"], 0) + 1

    # By corridor
    by_corridor: dict[str, int] = {"L": 0, "C": 0, "R": 0}
    for rec in castle_rows:
        by_corridor[rec["corridor"]] += 1

    corr_total = total or 1
    by_corridor_pct = {
        k: round(v / corr_total * 100, 1) for k, v in by_corridor.items()
    }

    # By sub-zone
    by_subzone: dict[str, int] = {"box": 0, "deep_flank": 0, "def_third_edge": 0}
    for rec in castle_rows:
        by_subzone[rec["subzone"]] += 1

    box_pct       = round(by_subzone["box"]            / total * 100, 1)
    deep_pct      = round(by_subzone["deep_flank"]     / total * 100, 1)
    edge_pct      = round(by_subzone["def_third_edge"] / total * 100, 1)

    # Zone counts (zones 1-6 inside defensive third)
    zone_counts: dict[int, int] = {}
    for rec in castle_rows:
        z = rec["zone"]
        zone_counts[z] = zone_counts.get(z, 0) + 1

    # Per-type percentage breakdown
    by_type_pct = {k: round(v / total * 100, 1) for k, v in by_type.items()}

    return {
        "total_actions":      total,
        "by_type":            by_type,
        "by_type_pct":        by_type_pct,
        "by_corridor":        by_corridor,
        "by_corridor_pct":    by_corridor_pct,
        "by_subzone":         by_subzone,
        "box_pct":            box_pct,
        "deep_flank_pct":     deep_pct,
        "def_third_edge_pct": edge_pct,
        "zone_counts":        zone_counts,
        "actions_detail":     castle_rows,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# EMPTY RESULT
# ═══════════════════════════════════════════════════════════════════════════════

def _empty_result() -> dict[str, Any]:
    return {
        "total_actions":      0,
        "by_type":            {},
        "by_type_pct":        {},
        "by_corridor":        {"L": 0, "C": 0, "R": 0},
        "by_corridor_pct":    {"L": 0.0, "C": 0.0, "R": 0.0},
        "by_subzone":         {"box": 0, "deep_flank": 0, "def_third_edge": 0},
        "box_pct":            0.0,
        "deep_flank_pct":     0.0,
        "def_third_edge_pct": 0.0,
        "zone_counts":        {},
        "actions_detail":     [],
    }
