"""
Chance Creation Analysis — Phase 3 of the Offensive Phase
==========================================================
Analyses shot events within possessions that entered the Final Third,
classifying each shot's **attack origin** and building the
**Chain-to-Goal Matrix** with supporting shot metrics.

This is the THIRD and final offensive phase:
  1. Build-up from GK  (goalkeeper_buildup.py)
  2. General Build-up   (general_buildup.py)
  3. Chance Creation    (THIS MODULE)

Core outputs:
  • Chain-to-Goal Matrix: 6 attack origins × 4 rows (N, xG, SoT%, GS)
  • Supporting shot metrics (volume, location, quality, SoT%)
  • Per-method breakdowns

Attack origin classification (priority-ordered):
  1. Set Piece    — shot directly from an attacking restart (≤ 5 passes, within 15 s)
                   Goal kicks / GK distribution are excluded (defensive restarts).
  2. High Regain  — recovery in final third + shot within 8 s;
                   excludes recoveries from opponent set-piece contexts.
  3. Counter      — recovery in own/middle third + shot within 8 s
  4. Cross        — cross qualifier or wide-zone FT pass (open play)
  5. Through Ball — through-ball qualifier on preceding pass (qualifier-detected only)
  Default: Combination — patient passing build-up (in-box OR out-of-box)

Coordinate system:
  x: 0→100 (own goal → opponent goal)
  y: 0→100 (right touchline → left touchline)
  Final Third:  x ≥ 66.67
  Penalty Box:  x ≥ 83.33 AND 21.1 ≤ y ≤ 78.9
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

import numpy as np
import pandas as pd

from src.analytics.possession_value import (
    PossessionValueModel as _LegacyPossessionValueModel,
    get_pv_model,
    get_xt_zone,
    FT_X_THRESHOLD,
    SHOT_TYPE_IDS,
    NON_PLAY_EVENTS,
)
from src.utils.pv_model import PossessionValueModel

# Module-level ML Possession Value model singleton.
# Loaded once on first import; all shot PV calculations use this instance.
_pv = PossessionValueModel.get_instance()
from src.analytics.goalkeeper_buildup import (
    _load_match_events,
    _is_same_team,
    _is_play_event,
    xy_to_zone,
)
from src.analytics.general_buildup import (
    build_possessions,
    _is_set_piece,
)
from src.analytics.high_regains import compute_high_regain_kpis
from src.team_mapping import canonical_name
from src.utils.xg_model import compute_xg_for_shot, estimate_xgot

log = logging.getLogger("dashboard.chance_creation")

# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

# Pitch zones
PENALTY_BOX_X_MIN = 83.33
PENALTY_BOX_Y_MIN = 21.1
PENALTY_BOX_Y_MAX = 78.9

# Attack origin detection thresholds
SET_PIECE_LOOKBACK_SEC = 15.0   # window before shot to detect a restart event
COUNTER_MAX_SEC = 8.0
THROUGH_BALL_LOOKBACK_SEC = 12.0

# Maximum passes from a restart to the shot for it to still count as Set Piece.
# If more passes were played the possession is reclassified as Open Play.
SET_PIECE_MAX_PASSES = 5

# Origin labels (column order for the matrix — roughly by speed of attack)
ORIGIN_LABELS = [
    "Set Piece", "High Regain", "Counter", "Cross", "Through Ball", "Combination",
]
ORIGIN_DEFAULT = "Combination"  # patient passing-chain build-up (in-box or out-of-box)

# High Regain: recovery in attacking third + fast shot
# Counter:     recovery in own/middle third + fast shot
HIGH_REGAIN_X_MIN = FT_X_THRESHOLD  # 66.67 — recovery must be in the final third

# Metric row labels (all sums / counts for consistent aggregation)
MATRIX_ROWS = ["N", "xG", "SoT%", "GS"]

# Attacking set-piece restart event types (lowercase).
# Goal kicks and GK distribution are EXCLUDED — they are defensive restarts
# used for possession recycling, not attacking set pieces.
SET_PIECE_EVENTS = frozenset({
    "corner awarded", "free kick", "throw in", "penalty",
})

# Attacking set-piece qualifier columns (Opta CSV).
# Goal Kick / gk_kick_from_hands intentionally omitted — defensive restarts.
SET_PIECE_QUALIFIER_COLS = (
    "Corner taken", "corner_taken",
    "Free kick taken", "free_kick_taken",
    "Throw In", "throw_in",
    "Throw In set piece",
    "Penalty", "penalty",
)

# Possession-origin labels that represent attacking dead-ball restarts.
# goal_kick / gk_hands are excluded — they are defensive restarts.
SET_PIECE_ORIGINS = frozenset({
    "corner", "free_kick", "throw_in", "penalty",
})

# Recovery / turnover event types for counter detection
RECOVERY_EVENTS = frozenset({
    "ball recovery", "interception", "tackle",
})

# Opponent event types that indicate a turnover (for direct-score detection)
# When these occur at the opponent's end, the scoring team effectively
# "regains" the ball even without an explicit recovery event.
TURNOVER_EVENTS = frozenset({
    "error", "dispossessed",
})


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _is_in_penalty_box(x: float, y: float) -> bool:
    """Check if coordinates are inside the penalty box."""
    return x >= PENALTY_BOX_X_MIN and PENALTY_BOX_Y_MIN <= y <= PENALTY_BOX_Y_MAX


def _is_on_target(row: pd.Series) -> bool:
    """Check if a shot is on target (saved or goal)."""
    type_id = row.get("type_id")
    if pd.notna(type_id):
        tid = int(type_id)
        return tid in (15, 16)  # Saved Shot or Goal
    event = str(row.get("event_type", row.get("event", ""))).strip().lower()
    return event in ("saved shot", "goal")


def _is_goal(row: pd.Series) -> bool:
    """Check if a shot is a goal."""
    type_id = row.get("type_id")
    if pd.notna(type_id):
        return int(type_id) == 16
    event = str(row.get("event_type", row.get("event", ""))).strip().lower()
    return event == "goal"


def _match_sec(row: pd.Series) -> float:
    """Get match second from a row, trying multiple column names."""
    ms = row.get("_match_sec")
    if pd.notna(ms):
        return float(ms)
    m = row.get("time_min", row.get("minute", 0)) or 0
    s = row.get("time_sec", row.get("second", 0)) or 0
    return float(m) * 60 + float(s)


def _has_qualifier(row: pd.Series, *col_names: str) -> bool:
    """Check if any of the given qualifier columns has a truthy value."""
    for col in col_names:
        val = str(row.get(col, "")).strip().lower()
        if val in ("si", "yes", "1", "true"):
            return True
    return False


# ═══════════════════════════════════════════════════════════════════════════════
# ATTACK ORIGIN CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════════

def classify_attack_origin(
    shot_row: pd.Series,
    poss_events: pd.DataFrame,
    poss_origin: str = "open_play",
    poss_start_sec: float = 0.0,
    match_df: Optional[pd.DataFrame] = None,
) -> str:
    """
    Classify a shot's attack origin using priority-ordered rules.

    Parameters
    ----------
    shot_row : pd.Series
        The shot event row.
    poss_events : pd.DataFrame
        All events in the same possession, sorted by time.
    poss_origin : str
        Possession origin label from Phase 2 (e.g. "corner", "free_kick").
    poss_start_sec : float
        Match-second when the possession started.
    match_df : pd.DataFrame, optional
        Full match events DataFrame (with possession IDs). Required for
        detecting direct-score turnovers (e.g. opponent error → goal).

    Returns
    -------
    str — one of: "Set Piece", "High Regain", "Counter", "Through Ball",
          "Cross", "Combination"
    """
    shot_sec = _match_sec(shot_row)
    shot_x = float(shot_row.get("x", 0))
    shot_y = float(shot_row.get("y", 50))

    # ── Priority 1: Set Piece ──
    # Check if shot occurs within 12s of a dead-ball restart event
    if _check_set_piece(shot_row, shot_sec, poss_events, poss_origin,
                        match_df=match_df):
        log.debug("Shot at %.0fs classified: Set Piece", shot_sec)
        return "Set Piece"

    # ── Priority 2: High Regain ──
    # Recovery in the attacking final third (x ≥ 66.67) + shot within 8s
    if _check_high_regain(poss_events, shot_sec, poss_start_sec,
                          shot_row=shot_row, match_df=match_df):
        log.debug("Shot at %.0fs classified: High Regain", shot_sec)
        return "High Regain"

    # ── Priority 3: Counter ──
    # Recovery in own/middle third (x < 66.67) + shot within 8s
    if _check_counter(poss_origin, poss_events, shot_sec, poss_start_sec):
        log.debug("Shot at %.0fs classified: Counter", shot_sec)
        return "Counter"

    # ── Priority 4: Cross ──
    # More specific: wide-zone final-third pass + final-third shot
    if _check_cross(shot_row, shot_sec, poss_events, match_df=match_df):
        log.debug("Shot at %.0fs classified: Cross", shot_sec)
        return "Cross"

    # ── Priority 5: Through Ball ──
    # Only qualifier-detected through balls (F3 #4); default Combination
    # handles patient build-up without the qualifier.
    if _check_through_ball(shot_row, shot_sec, poss_events):
        log.debug("Shot at %.0fs classified: Through Ball", shot_sec)
        return "Through Ball"

    # ── Default: Combination — patient passing-chain build-up.
    # Covers both in-box and out-of-box shots that don't match the
    # above origins.  Shot location is exposed separately in Section A
    # (shots_in_box / shots_out_box KPIs), not via the origin column.
    log.debug("Shot at %.0fs classified: Combination (default)", shot_sec)
    return "Combination"


def _is_set_piece_event(row: pd.Series) -> bool:
    """Return ``True`` if *row* is a dead-ball restart event.

    Checks both the event-type string and any set-piece qualifier column.
    """
    et = str(row.get("event_type", row.get("event", ""))).strip().lower()
    if et in SET_PIECE_EVENTS:
        return True
    for col in SET_PIECE_QUALIFIER_COLS:
        val = str(row.get(col, "")).strip().lower()
        if val in ("si", "yes", "1", "true"):
            return True
    return False


def _check_set_piece(
    shot_row: pd.Series,
    shot_sec: float,
    poss_events: pd.DataFrame,
    poss_origin: str,
    *,
    match_df: Optional[pd.DataFrame] = None,
) -> bool:
    """Check if the shot originates directly from a dead-ball restart.

    A shot is classified as **Set Piece** when **both** conditions hold:
      1. A restart event (corner, free kick, throw-in, penalty, goal kick)
         occurred within ``SET_PIECE_LOOKBACK_SEC`` (15 s) of the shot.
      2. No more than ``SET_PIECE_MAX_PASSES`` (5) passes were played
         between the restart and the shot.

    Condition 2 ensures that a set piece played short in the team's own
    half and built up through many passes (e.g. a free kick in the own
    third leading to a long possession) is classified as Open Play rather
    than Set Piece.

    The restart event is searched in:
      A. The shot's own possession (via ``poss_origin`` or inline event).
      B. Up to 3 previous possessions via ``match_df`` — handles the
         common pattern where an aerial duel splits the corner / free-kick
         possession from the possession containing the shot:
           Poss N   (team):  corner taken → cross
           Poss N+1 (opp):   aerial (won/lost)
           Poss N+2 (team):  header / shot  ← shot lives here
    """
    # Penalty is always Set Piece regardless of pass count
    if _has_qualifier(shot_row, "Penalty", "penalty"):
        return True

    lookback_start = shot_sec - SET_PIECE_LOOKBACK_SEC
    shot_poss_id = shot_row.get("poss_id")

    # Count passes in the current possession before the shot
    passes_in_poss = sum(
        1
        for i in range(len(poss_events))
        if _match_sec(poss_events.iloc[i]) < shot_sec
        and str(poss_events.iloc[i].get(
            "event_type", poss_events.iloc[i].get("event", "")
        )).strip().lower() == "pass"
    )

    # ── A. Current possession ──────────────────────────────────────────────
    # Fast path: poss_origin is itself a set piece
    if poss_origin in SET_PIECE_ORIGINS:
        poss_start = (
            _match_sec(poss_events.iloc[0]) if not poss_events.empty else shot_sec
        )
        if poss_start >= lookback_start:
            # Gate on pass count: many passes → Open Play, not Set Piece
            return passes_in_poss <= SET_PIECE_MAX_PASSES

    # Inline set-piece event within the current possession
    for i in range(len(poss_events)):
        row = poss_events.iloc[i]
        row_sec = _match_sec(row)
        if row_sec < lookback_start or row_sec >= shot_sec:
            continue
        if _is_set_piece_event(row):
            return passes_in_poss <= SET_PIECE_MAX_PASSES

    # ── B. Previous possessions (up to 3 hops) ────────────────────────────
    if match_df is None or "poss_id" not in match_df.columns or pd.isna(shot_poss_id):
        return False

    poss_start_sec = (
        _match_sec(poss_events.iloc[0]) if not poss_events.empty else shot_sec
    )

    for offset in range(1, 4):
        prev_id = int(shot_poss_id) - offset
        prev_poss = match_df[match_df["poss_id"] == prev_id]
        if prev_poss.empty:
            continue

        # Stop walking back if the entire possession is before the window
        if _match_sec(prev_poss.iloc[-1]) < lookback_start:
            break

        sp_found = False
        sp_time: Optional[float] = None

        # Check poss_origin of the previous possession
        if "poss_origin" in prev_poss.columns:
            prev_origin = str(prev_poss["poss_origin"].iloc[0])
            if prev_origin in SET_PIECE_ORIGINS:
                prev_start = _match_sec(prev_poss.iloc[0])
                if prev_start >= lookback_start:
                    sp_found = True
                    sp_time = prev_start

        # Also scan inline events of the previous possession
        if not sp_found:
            for i in range(len(prev_poss)):
                row = prev_poss.iloc[i]
                row_sec = _match_sec(row)
                if row_sec < lookback_start:
                    continue
                if row_sec >= poss_start_sec:
                    break
                if _is_set_piece_event(row):
                    sp_found = True
                    sp_time = row_sec
                    break

        if sp_found and sp_time is not None:
            # Count passes from the restart to the start of the shot possession
            passes_after_sp_in_prev = sum(
                1
                for i in range(len(prev_poss))
                if sp_time < _match_sec(prev_poss.iloc[i]) < poss_start_sec
                and str(prev_poss.iloc[i].get(
                    "event_type", prev_poss.iloc[i].get("event", "")
                )).strip().lower() == "pass"
            )
            total_passes = passes_after_sp_in_prev + passes_in_poss
            log.debug(
                "Set piece found in prev poss %d at %.0fs; %d total passes to shot",
                prev_id, sp_time, total_passes,
            )
            return total_passes <= SET_PIECE_MAX_PASSES

    return False


def _find_first_recovery(poss_events: pd.DataFrame):
    """Find the first recovery event in a possession.

    Returns
    -------
    tuple[str, float, float] | None
        ``(event_type, x_coord, match_sec)`` of the first recovery event,
        or ``None`` if no recovery starts the possession.
    """
    for i in range(len(poss_events)):
        row = poss_events.iloc[i]
        et = str(row.get("event_type", row.get("event", ""))).strip().lower()
        if et in NON_PLAY_EVENTS or et == "":
            continue
        if et in RECOVERY_EVENTS:
            x = row.get("x")
            x_val = float(x) if pd.notna(x) else 0.0
            sec = _match_sec(row)
            return (et, x_val, sec)
        # First play event is not a recovery
        return None
    return None


def _check_high_regain(
    poss_events: pd.DataFrame,
    shot_sec: float,
    poss_start_sec: float,
    *,
    shot_row: Optional[pd.Series] = None,
    match_df: Optional[pd.DataFrame] = None,
) -> bool:
    """Check if shot originates from a high regain (recovery in the
    attacking final third, x ≥ 66.67).

    A high regain is detected in two ways:

    **Case A — Explicit recovery in the possession:**
      - Possession starts with a recovery event (ball recovery,
        interception, tackle) at x ≥ 66.67.
      - Shot occurs within ``COUNTER_MAX_SEC`` (8s) of possession start.

    **Case B — Direct-score turnover (no explicit recovery):**
      - The shot/goal is the first (and often only) play event in the
        possession — the player scores directly from an opponent error
        or bad pass.
      - The previous possession belonged to the opponent and ended with
        a turnover (Error, Dispossessed, or failed pass) at a location
        that maps to the attacking final third.
      - Shot occurs within ``COUNTER_MAX_SEC`` (8s) of the turnover.

    Case B handles situations like: opponent defender plays a bad back-
    pass, the attacker intercepts and scores immediately — there is no
    explicit "ball recovery" event, the goal IS the recovery.
    """
    if poss_events.empty:
        return False

    # ── Case A: explicit recovery ──
    rec = _find_first_recovery(poss_events)
    if rec is not None:
        _et, rec_x, _rec_sec = rec
        if rec_x >= HIGH_REGAIN_X_MIN:
            # Directionality guard: a recovery deep in the final third while
            # defending an opponent set piece is NOT a high press.  Check the
            # immediately preceding possession — if it was an opponent set
            # piece, this recovery is a defensive clearance, not a high regain.
            if match_df is not None and "poss_id" in match_df.columns:
                shot_poss_id = (
                    shot_row.get("poss_id") if shot_row is not None else None
                )
                if pd.notna(shot_poss_id):
                    prev_id = int(shot_poss_id) - 1
                    prev_poss = match_df[match_df["poss_id"] == prev_id]
                    if not prev_poss.empty and "poss_origin" in prev_poss.columns:
                        prev_origin = str(prev_poss["poss_origin"].iloc[0])
                        if prev_origin in SET_PIECE_ORIGINS:
                            log.debug(
                                "High regain suppressed: recovery at x=%.1f "
                                "follows opponent %s (set piece context)",
                                rec_x, prev_origin,
                            )
                            return False
            elapsed = shot_sec - poss_start_sec
            return 0 <= elapsed <= COUNTER_MAX_SEC
        # Recovery exists but not in final third → not a high regain
        return False

    # ── Case B: direct-score turnover ──
    # Only attempt if we have the full match DataFrame
    if match_df is None or shot_row is None:
        return False
    if "poss_id" not in match_df.columns:
        return False

    # Check that the shot is the first play event in its possession
    shot_poss_id = shot_row.get("poss_id")
    if pd.isna(shot_poss_id):
        return False

    first_play_is_shot = False
    for i in range(len(poss_events)):
        row = poss_events.iloc[i]
        et = str(row.get("event_type", row.get("event", ""))).strip().lower()
        if et in NON_PLAY_EVENTS or et == "":
            continue
        # First play event in this possession
        tid = row.get("type_id")
        if pd.notna(tid) and int(tid) in SHOT_TYPE_IDS:
            first_play_is_shot = True
        break

    if not first_play_is_shot:
        return False

    # Look at the immediately preceding possession
    prev_poss_id = int(shot_poss_id) - 1
    prev_poss = match_df[match_df["poss_id"] == prev_poss_id]
    if prev_poss.empty:
        return False

    # Previous possession must be from the opponent
    shot_team = str(shot_row.get("team_name", "")).strip().lower()
    prev_team = str(prev_poss["team_name"].dropna().iloc[-1]).strip().lower() \
        if not prev_poss["team_name"].dropna().empty else ""
    if prev_team == shot_team:
        return False  # Same team — not a turnover

    # Find the last meaningful event in the previous possession
    last_evt = None
    for i in range(len(prev_poss) - 1, -1, -1):
        row = prev_poss.iloc[i]
        et = str(row.get("event_type", row.get("event", ""))).strip().lower()
        if et not in NON_PLAY_EVENTS and et != "":
            last_evt = row
            break

    if last_evt is None:
        return False

    last_et = str(last_evt.get("event_type", last_evt.get("event", ""))).strip().lower()
    last_outcome = last_evt.get("outcome")

    # Turnover check: Error, Dispossessed, or failed pass/action
    is_turnover = (
        last_et in TURNOVER_EVENTS
        or (pd.notna(last_outcome) and int(last_outcome) == 0)
    )
    if not is_turnover:
        return False

    # Location check: opponent's x → flip to our attacking x
    opp_x = last_evt.get("x")
    if pd.isna(opp_x):
        return False
    our_x = 100.0 - float(opp_x)  # Flip coordinates

    if our_x < HIGH_REGAIN_X_MIN:
        return False

    # Time check: shot within 8s of the turnover
    turnover_sec = _match_sec(last_evt)
    elapsed = shot_sec - turnover_sec
    return 0 <= elapsed <= COUNTER_MAX_SEC


def _check_counter(
    poss_origin: str,
    poss_events: pd.DataFrame,
    shot_sec: float,
    poss_start_sec: float,
) -> bool:
    """Check if shot is from a counter-attack.

    A counter-attack is a possession that:
      - Starts with a recovery event (ball recovery, interception, tackle)
      - The recovery occurs OUTSIDE the final third (x < 66.67)
      - The shot occurs within ``COUNTER_MAX_SEC`` (8s) of possession start

    Recoveries in the final third are classified as "High Regain" instead.
    """
    if poss_events.empty:
        return False

    rec = _find_first_recovery(poss_events)
    if rec is None:
        return False

    _et, rec_x, _rec_sec = rec

    # Recovery must be OUTSIDE the final third (own/middle third)
    if rec_x >= HIGH_REGAIN_X_MIN:
        return False

    # Shot within 8 seconds of possession start
    elapsed = shot_sec - poss_start_sec
    return 0 <= elapsed <= COUNTER_MAX_SEC


def _check_through_ball(
    shot_row: pd.Series,
    shot_sec: float,
    poss_events: pd.DataFrame,
) -> bool:
    """Check if shot is from a through ball."""
    lookback_start = shot_sec - THROUGH_BALL_LOOKBACK_SEC

    # Check the last pass before the shot
    last_pass = None
    for i in range(len(poss_events) - 1, -1, -1):
        row = poss_events.iloc[i]
        row_sec = _match_sec(row)
        if row_sec >= shot_sec:
            continue
        if row_sec < lookback_start:
            break
        et = str(row.get("event_type", row.get("event", ""))).strip().lower()
        if et == "pass":
            last_pass = row
            break

    # Check last pass for through ball qualifier
    if last_pass is not None:
        if _has_qualifier(last_pass, "Through ball", "through_ball"):
            return True

    # Check any pass in the 12s lookback window
    for i in range(len(poss_events)):
        row = poss_events.iloc[i]
        row_sec = _match_sec(row)
        if row_sec < lookback_start:
            continue
        if row_sec >= shot_sec:
            break
        et = str(row.get("event_type", row.get("event", ""))).strip().lower()
        if et == "pass" and _has_qualifier(row, "Through ball", "through_ball"):
            return True

    return False


def _check_cross(
    shot_row: pd.Series,
    shot_sec: float,
    poss_events: pd.DataFrame,
    *,
    match_df: Optional[pd.DataFrame] = None,
) -> bool:
    """Check if shot is from a cross.

    Handles the common cross-to-header pattern where the possession
    builder splits the chain at an aerial duel:

        Poss N   (same team): ... → Cross pass
        Poss N+1 (opponent):  Aerial (lost)
        Poss N+2 (same team): Aerial (won) → Goal   ← shot is here

    When no pass is found inside the shot's possession and the
    possession starts with an aerial event, we look back into the
    previous same-team possession (within the 12 s window) for a
    cross.
    """
    lookback_start = shot_sec - THROUGH_BALL_LOOKBACK_SEC

    if _check_cross_in_events(shot_sec, lookback_start, poss_events):
        return True

    # ── Cross-to-header fallback ──
    # If no cross was found in the current possession, the cross may
    # live in a previous same-team possession separated by an aerial.
    if match_df is not None and "poss_id" in poss_events.columns:
        first_evt = poss_events.iloc[0]
        first_et = str(
            first_evt.get("event_type", first_evt.get("event", ""))
        ).strip().lower()

        # Only trigger when the possession starts with an aerial or a
        # header-type event (the receiver of the cross).
        if first_et in ("aerial", "clearance", "headed duel",
                        "ball recovery"):
            shot_poss = int(poss_events["poss_id"].iloc[0])
            shot_team = str(shot_row.get("team_name", "")).strip().lower()

            # Walk backwards through prior possessions (max 3 hops
            # to cover the Poss N+1 opponent aerial gap).
            for offset in range(1, 4):
                prev_id = shot_poss - offset
                prev_poss = match_df[match_df["poss_id"] == prev_id]
                if prev_poss.empty:
                    continue

                prev_team = str(
                    prev_poss["team_name"].iloc[-1]
                ).strip().lower()

                # Only consider same-team possessions
                if canonical_name(prev_team) != canonical_name(shot_team):
                    continue

                # Respect the 12 s lookback window
                last_sec = _match_sec(prev_poss.iloc[-1])
                if last_sec < lookback_start:
                    break  # too old — no point checking further

                if _check_cross_in_events(
                    shot_sec, lookback_start, prev_poss
                ):
                    log.debug(
                        "Cross detected in prev poss %d for shot at %.0fs",
                        prev_id, shot_sec,
                    )
                    return True

    return False


def _check_cross_in_events(
    shot_sec: float,
    lookback_start: float,
    events: pd.DataFrame,
) -> bool:
    """Return True if *events* contains a cross within the window."""
    # Find the last pass before the shot
    last_pass = None
    for i in range(len(events) - 1, -1, -1):
        row = events.iloc[i]
        row_sec = _match_sec(row)
        if row_sec >= shot_sec:
            continue
        if row_sec < lookback_start:
            break
        et = str(row.get("event_type", row.get("event", ""))).strip().lower()
        if et == "pass":
            last_pass = row
            break

    if last_pass is not None:
        # Cross qualifier flag
        if _has_qualifier(last_pass, "Cross"):
            return True

        # Wide zone + final third pass origin
        pass_x = last_pass.get("x")
        pass_y = last_pass.get("y")
        if pd.notna(pass_x) and pd.notna(pass_y):
            px, py = float(pass_x), float(pass_y)
            if px >= FT_X_THRESHOLD and (py < 25.0 or py > 75.0):
                return True

    # Also check any pass in the lookback window with Cross qualifier
    for i in range(len(events)):
        row = events.iloc[i]
        row_sec = _match_sec(row)
        if row_sec < lookback_start:
            continue
        if row_sec >= shot_sec:
            break
        et = str(row.get("event_type", row.get("event", ""))).strip().lower()
        if et == "pass" and _has_qualifier(row, "Cross"):
            return True

    return False


# ═══════════════════════════════════════════════════════════════════════════════
# SHOT QUALITY TIERS
# ═══════════════════════════════════════════════════════════════════════════════

def classify_shot_quality(
    type_id: int,
    xg_value: float,
    is_on_target: bool,
    is_goal_event: bool,
) -> int:
    """
    Classify shot into quality tier (0–3).

    Level 3 — Converted:    outcome == "goal"
    Level 2 — Big Chance:   outcome == "saved" OR xG ≥ 0.20
    Level 1 — Promising:    outcome in {"miss", "post"} AND xG ≥ 0.10
    Level 0 — Speculative:  outcome == "blocked" OR xG < 0.10
    """
    if is_goal_event:
        return 3
    if is_on_target or xg_value >= 0.20:
        return 2
    if type_id in (13, 14) and xg_value >= 0.10:  # miss or post
        return 1
    return 0


# ═══════════════════════════════════════════════════════════════════════════════
# CHANCE CREATION ANALYZER
# ═══════════════════════════════════════════════════════════════════════════════

class ChanceCreationAnalyzer:
    """
    Analyse shot events within a match to produce the Chain-to-Goal Matrix
    and supporting shot metrics.

    Parameters
    ----------
    pv_model : PossessionValueModel
        Pre-built Possession Value model for xT lookups.
    xg_model : optional
        Not used directly — xG is computed via ``compute_xg_for_shot()``.
    """

    def __init__(
        self,
        pv_model: Any = None,
        xg_model: Optional[Any] = None,
    ):
        self.pv_model = pv_model
        self.xg_model = xg_model

    # ── Main entry point ──────────────────────────────────────────────────

    def analyze(
        self,
        match_df: pd.DataFrame,
        team: str,
    ) -> dict:
        """
        Analyse chance creation for one team in one match.

        Parameters
        ----------
        match_df : pd.DataFrame
            Full match events DataFrame (from CSV).
        team : str
            Team name to analyse.

        Returns
        -------
        dict — the ``chance_creation_output`` structure defined in the spec.
            Includes ``high_regain_kpis`` sub-dict with high-regain metrics.
        """
        team_lower = canonical_name(team).lower()

        # 1. Build possessions
        df = self._prepare_events(match_df)
        df = build_possessions(df)

        # 2. Find all shots for this team
        shots_detail = self._extract_shots(df, team_lower)

        if not shots_detail:
            log.warning("No shots found for team %s", team)
            return self._empty_output()

        # 3. Count qualifying possessions
        team_mask = df["poss_team_name"].apply(
            lambda t: canonical_name(str(t).strip()).lower() == team_lower
        )
        total_possessions = df.loc[team_mask, "poss_id"].nunique()

        # 4. Build outputs
        matrix = self.build_chain_to_goal_matrix(shots_detail)
        shot_metrics = self.compute_shot_metrics(shots_detail, total_possessions)
        quality_tiers = self._compute_quality_tiers(shots_detail)

        # 5. High-regain KPIs (integrated into Chance Creation)
        hr_kpis = compute_high_regain_kpis(
            match_df, team, pv_model=self.pv_model,
        )

        log.info("Chance creation for %s: %d shots, %d goals, "
                 "total xG=%.2f, origins=%s, high_regains=%d",
                 team, len(shots_detail),
                 sum(1 for s in shots_detail if s["is_goal"]),
                 sum(s["xG"] for s in shots_detail),
                 {o: sum(1 for s in shots_detail if s["origin"] == o)
                  for o in ORIGIN_LABELS},
                 hr_kpis.get("total_high_regains", 0))

        return {
            "chain_to_goal_matrix": matrix,
            "shot_metrics": shot_metrics,
            "shot_quality_tiers": quality_tiers,
            "shots_detail": shots_detail,
            "high_regain_kpis": hr_kpis,
        }

    # ── Event preparation ─────────────────────────────────────────────────

    def _prepare_events(self, df: pd.DataFrame) -> pd.DataFrame:
        """Prepare raw events DataFrame for analysis."""
        df = df.copy()

        # Rename columns if needed (handle both naming conventions)
        renames = {
            "event": "event_type",
            "time_min": "minute",
            "time_sec": "second",
            "period_id": "period",
            "contestant_id": "team_id",
            "Corner taken": "corner_taken",
            "Free kick taken": "free_kick_taken",
            "Throw In": "throw_in",
            "Gk kick from hands": "gk_kick_from_hands",
            "Through ball": "through_ball",
            "Long ball": "long_ball",
        }
        for orig, new in renames.items():
            if orig in df.columns and new not in df.columns:
                df[new] = df[orig]

        # Numeric conversions
        for col in ("x", "y", "Pass End X", "Pass End Y", "Length",
                    "minute", "second", "event_id", "period", "outcome"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # Sort
        sort_cols = [c for c in ["period", "minute", "second", "event_id"]
                     if c in df.columns]
        if sort_cols:
            df = df.sort_values(sort_cols).reset_index(drop=True)

        # Match seconds
        df["_match_sec"] = df["minute"].fillna(0) * 60 + df["second"].fillna(0)

        return df

    # ── Shot extraction ───────────────────────────────────────────────────

    def _extract_shots(
        self,
        df: pd.DataFrame,
        team_lower: str,
    ) -> List[dict]:
        """Extract and classify all shots for a team."""
        shots_detail = []

        # Identify shot rows
        shot_mask = df["type_id"].isin(list(SHOT_TYPE_IDS))
        team_mask = df["team_name"].apply(
            lambda t: canonical_name(str(t).strip()).lower() == team_lower
            if pd.notna(t) else False
        )
        team_shots = df[shot_mask & team_mask]

        for idx in team_shots.index:
            shot_row = df.loc[idx]
            poss_id = shot_row.get("poss_id")
            if pd.isna(poss_id):
                log.warning("Shot at idx %d has no possession ID — skipping", idx)
                continue

            # Get possession events
            poss_events = df[df["poss_id"] == poss_id].copy()

            # Possession metadata
            poss_origin = poss_events["poss_origin"].iloc[0] if "poss_origin" in poss_events.columns else "open_play"
            poss_start_sec = poss_events["_match_sec"].iloc[0] if not poss_events.empty else 0.0

            # Classify attack origin
            origin = classify_attack_origin(
                shot_row, poss_events, poss_origin, poss_start_sec,
                match_df=df,
            )

            # Compute xG
            xg_val = compute_xg_for_shot(shot_row)

            # Shot details
            shot_x = float(shot_row.get("x", 0))
            shot_y = float(shot_row.get("y", 50))
            type_id = int(shot_row.get("type_id", 13))
            on_target = type_id in (15, 16)
            is_goal_event = type_id == 16

            # xGOT (only for on-target shots)
            xgot_val = estimate_xgot(xg_val, shot_y, on_target) if on_target else 0.0

            # Compute PV for this shot's chain
            pv_val = self._compute_shot_pv(poss_events, shot_row, poss_start_sec)

            # Quality tier
            quality_tier = classify_shot_quality(
                type_id, xg_val, on_target, is_goal_event,
            )

            detail = {
                "shot_idx": int(idx),
                "poss_id": int(poss_id),
                "origin": origin,
                "x": round(shot_x, 2),
                "y": round(shot_y, 2),
                "type_id": type_id,
                "is_goal": is_goal_event,
                "on_target": on_target,
                "in_box": _is_in_penalty_box(shot_x, shot_y),
                "xG": round(xg_val, 4),
                "xGOT": round(xgot_val, 4),
                "PV": round(pv_val, 4),
                "quality_tier": quality_tier,
                "minute": int(shot_row.get("minute", 0) or 0),
                "second": int(shot_row.get("second", 0) or 0),
                "period": int(shot_row.get("period", 1) or 1),
                "player": str(shot_row.get("player_name", "")).strip(),
                "event_type": str(shot_row.get("event_type",
                                               shot_row.get("event", ""))).strip(),
            }
            shots_detail.append(detail)

            log.debug("Shot %d: origin=%s, xG=%.3f, PV=%.4f, goal=%s",
                      idx, origin, xg_val, pv_val, is_goal_event)

        return shots_detail

    def _compute_shot_pv(
        self,
        poss_events: pd.DataFrame,
        shot_row: pd.Series,
        poss_start_sec: float,
    ) -> float:
        """
        Compute Possession Value for a single shot.

        Logic:
        ------
        1. Find the first event in the possession where x ≥ 66.67
           (= entry into the final third).
        2. If found:
               PV = _pv.delta(x_entry, y_entry → x_shot, y_shot)
           This measures how much P(goal) changed from the FT-entry
           point to the shot location.
        3. If not found (possession was already in the FT from the start,
           or no non-shot events recorded):
               PV = _pv.score(x_shot, y_shot, type_id=16)  [absolute]
        4. Clamp result to [−0.5, 0.5] — values outside this range
           indicate data errors, not real contributions.
        """
        shot_x = float(shot_row.get("x", 0) or 0)
        shot_y = float(shot_row.get("y", 50) or 50)

        # ── Find first final-third entry event (non-shot) ──────────────
        ft_entry_row: Optional[pd.Series] = None
        for i in range(len(poss_events)):
            row = poss_events.iloc[i]
            # Skip shot events — we want the entry point, not the shot
            tid = row.get("type_id")
            if pd.notna(tid) and int(tid) in SHOT_TYPE_IDS:
                continue
            et = str(row.get("event_type", row.get("event", ""))).strip().lower()
            if et in NON_PLAY_EVENTS or et == "":
                continue
            x = row.get("x")
            if pd.notna(x) and float(x) >= FT_X_THRESHOLD:
                ft_entry_row = row
                break
            # Also promote via pass end-point entering the FT
            end_x = row.get("Pass End X", row.get("pass_end_x"))
            if pd.notna(end_x) and float(end_x) >= FT_X_THRESHOLD:
                ft_entry_row = row
                break

        # ── Compute PV ────────────────────────────────────────────────
        if ft_entry_row is not None:
            entry_x = float(ft_entry_row.get("x", 0) or 0)
            entry_y = float(ft_entry_row.get("y", 50) or 50)
            type_id_from = int(ft_entry_row.get("type_id", 1) or 1)
            pv_val = _pv.delta(
                x_from=entry_x, y_from=entry_y,
                x_to=shot_x, y_to=shot_y,
                type_id_from=type_id_from,
                type_id_to=16,   # Opta typeId for Goal
            )
        else:
            # Possession was already in the FT, or no non-shot events:
            # use absolute score at shot location
            pv_val = _pv.score(shot_x, shot_y, type_id=16)

        # Clamp: values outside [−0.5, 0.5] indicate data artefacts
        return float(max(-0.5, min(0.5, pv_val)))

    # ── Chain-to-Goal Matrix ──────────────────────────────────────────────

    def build_chain_to_goal_matrix(
        self,
        shots: List[dict],
    ) -> dict:
        """
        Build the 6-column × 4-row Chain-to-Goal Matrix.

        Columns (ordered by attack speed): Set Piece | High Regain | Counter
                                           | Cross | Through Ball | Combination | TOTAL
        Rows (all sums for consistent aggregation): N | xG (sum) | SoT% (%) | GS (count)
        """
        matrix: Dict[str, Dict[str, float]] = {}

        for origin in ORIGIN_LABELS:
            origin_shots = [s for s in shots if s["origin"] == origin]
            matrix[origin] = self._compute_origin_metrics(origin_shots)

        # TOTAL column
        matrix["TOTAL"] = self._compute_origin_metrics(shots)

        return matrix

    def _compute_origin_metrics(self, shots: List[dict]) -> Dict[str, float]:
        """
        Compute N, xG (sum), SoT% (%), GS for a set of shots.

        All four rows use the same aggregation philosophy (counts, sums or rates)
        so the columns are directly comparable across rows.
        """
        if not shots:
            return {"N": 0, "xG": 0.0, "SoT%": 0.0, "GS": 0}

        n = len(shots)
        xg_values = [s["xG"] for s in shots]
        on_target = sum(1 for s in shots if s["on_target"])
        goals = sum(1 for s in shots if s["is_goal"])
        sot_pct = round(on_target / n * 100, 1) if n else 0.0

        return {
            "N": n,
            "xG": round(sum(xg_values), 2),
            "SoT%": sot_pct,
            "GS": goals,
        }

    # ── Shot Metrics ──────────────────────────────────────────────────────

    def compute_shot_metrics(
        self,
        shots: List[dict],
        total_possessions: int,
    ) -> dict:
        """Compute supporting shot volume, location, quality metrics."""
        total = len(shots)
        if total == 0:
            return self._empty_shot_metrics()

        in_box = sum(1 for s in shots if s["in_box"])
        out_box = total - in_box

        sot_in_box = sum(1 for s in shots if s["in_box"] and s["on_target"])
        sot_out_box = sum(1 for s in shots if not s["in_box"] and s["on_target"])
        sot_total = sot_in_box + sot_out_box

        xg_total = sum(s["xG"] for s in shots)
        safe_total = max(total, 1)
        safe_in = max(in_box, 1)
        safe_out = max(out_box, 1)
        safe_poss = max(total_possessions, 1)

        return {
            "shots_total": total,
            "shots_in_box": in_box,
            "shots_out_box": out_box,
            "pct_in_box": round(in_box / safe_total * 100, 2),
            "pct_out_box": round(out_box / safe_total * 100, 2),
            "sot_pct_total": round(sot_total / safe_total * 100, 2),
            "sot_pct_in_box": round(sot_in_box / safe_in * 100, 2),
            "sot_pct_out_box": round(sot_out_box / safe_out * 100, 2),
            "shot_freq_pct": round(total / safe_poss * 100, 2),
            "xg_per_possession": round(xg_total / safe_poss, 2),
            "xg_per_shot": round(xg_total / safe_total, 2),
        }

    def _empty_shot_metrics(self) -> dict:
        return {
            "shots_total": 0, "shots_in_box": 0, "shots_out_box": 0,
            "pct_in_box": 0.0, "pct_out_box": 0.0,
            "sot_pct_total": 0.0, "sot_pct_in_box": 0.0,
            "sot_pct_out_box": 0.0,
            "shot_freq_pct": 0.0, "xg_per_possession": 0.0,
            "xg_per_shot": 0.0,
        }

    # ── Shot Quality Tiers ────────────────────────────────────────────────

    def _compute_quality_tiers(self, shots: List[dict]) -> dict:
        """Compute shot quality tier distribution."""
        total = max(len(shots), 1)
        tiers = {0: 0, 1: 0, 2: 0, 3: 0}

        for s in shots:
            tier = s.get("quality_tier", 0)
            tiers[tier] = tiers.get(tier, 0) + 1

        return {
            "level_3_converted": {
                "count": tiers[3],
                "pct": round(tiers[3] / total * 100, 2),
            },
            "level_2_threat": {
                "count": tiers[2],
                "pct": round(tiers[2] / total * 100, 2),
            },
            "level_1_danger": {
                "count": tiers[1],
                "pct": round(tiers[1] / total * 100, 2),
            },
            "level_0_low": {
                "count": tiers[0],
                "pct": round(tiers[0] / total * 100, 2),
            },
        }

    # ── Empty output ──────────────────────────────────────────────────────

    def _empty_output(self) -> dict:
        """Return a zeroed-out output when no shots are found."""
        empty_origin = {"N": 0, "PV": 0.0, "xG": 0.0, "SoT%": 0.0, "GS": 0}
        from src.analytics.high_regains import _empty_kpis as _empty_hr_kpis
        return {
            "chain_to_goal_matrix": {
                label: dict(empty_origin) for label in ORIGIN_LABELS + ["TOTAL"]
            },
            "shot_metrics": self._empty_shot_metrics(),
            "shot_quality_tiers": {
                "level_3_converted": {"count": 0, "pct": 0.0},
                "level_2_threat": {"count": 0, "pct": 0.0},
                "level_1_danger": {"count": 0, "pct": 0.0},
                "level_0_low": {"count": 0, "pct": 0.0},
            },
            "shots_detail": [],
            "high_regain_kpis": _empty_hr_kpis(15),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT  (match-level analysis)
# ═══════════════════════════════════════════════════════════════════════════════

def analyse_chance_creation(
    match_csv: Path,
    team_name: str,
    pv_model: Optional[Any] = None,
) -> dict:
    """
    Run the full chance creation analysis for one team in one match.

    Parameters
    ----------
    match_csv : Path
        Path to the match CSV file.
    team_name : str
        Team name to analyse.
    pv_model : PossessionValueModel, optional
        Pre-built PV model. If None, will be loaded/built automatically.

    Returns
    -------
    dict — the ``chance_creation_output`` structure.
    """
    # Load match data
    df = pd.read_csv(match_csv, low_memory=False)
    if df.empty:
        log.warning("Empty match data for %s", match_csv)
        return ChanceCreationAnalyzer(
            pv_model or get_pv_model()
        )._empty_output()

    # Get/build PV model
    if pv_model is None:
        pv_model = get_pv_model()

    # Run analysis
    analyzer = ChanceCreationAnalyzer(pv_model)
    return analyzer.analyze(df, team_name)
