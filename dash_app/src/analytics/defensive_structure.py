"""
Defensive Phase — D2: Defensive Transitions & Defensive Structure
=================================================================
Quantifies how well a team manages the transition moment (losing
possession) and maintains defensive shape, covering:

  1. Defensive Transitions        (D2.1)
  2. Offside Line & Trap          (D2.2a / D2.2b)
  3. Structural Mirror            (D2.2c — opponent Phase 2 view)
  4. Aerial Duels (Own Half)      (D2.2d)

Coordinate system (Opta, **from the analysed team's perspective**):
  x : 0 = own goal-line   → 100 = opponent goal-line
  y : 0 = right touchline → 100 = left touchline  (broadcast view)

Opponent reflection:
  x_att = 100 − x_opp   converts opponent frame to our attacking frame
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

log = logging.getLogger("dashboard.defensive_structure")

# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

# Zone boundaries (shared)
HIGH_X_MIN:  float = 66.67
MID_X_MIN:   float = 33.33
LEFT_Y_MIN:  float = 66.67
RIGHT_Y_MAX: float = 33.33

# Z14 box (zone 14 approximation — Team A attacking frame)
Z14_X_MIN: float = 66.67
Z14_X_MAX: float = 83.33
Z14_Y_MIN: float = 33.33
Z14_Y_MAX: float = 66.67

# ── Defensive transition detection (new methodology) ────────────────────────
# TRIGGER : Team A loses possession at x ≥ ATTACKING_HALF_MIN (Team A's frame).
# CONFIRM : Team B must reach OPP_ATT_THIRD_MIN in their own raw x within
#           TRANSITION_WINDOW_SEC.  Team B raw x is in their own attacking
#           direction, so:  100 − Team_B_raw_x = x in Team A's frame.
#           OPP_ATT_THIRD_MIN (66.67) == Team A's defensive third boundary.
ATTACKING_HALF_MIN:    float = 50.0    # min loss-x in Team A's frame
OPP_ATT_THIRD_MIN:     float = 66.67   # Team B raw-x for their att. third
TRANSITION_WINDOW_SEC: float = 25.0   # seconds window after possession loss
FAST_TRANSITION_SEC:   float = 10.0    # fast: Team B confirms in ≤ 10 s
SLOW_TRANSITION_SEC:   float = 15.0    # slow: Team B confirms in > 15 s

# Foul / set-piece / dedup guards
FOUL_TYPE_ID:          int   = 4       # Opta F24 foul-committed event
FOUL_GUARD_SEC:        float = 3.0     # look-back window to detect fouls
DEDUP_WINDOW_SEC:      float = 30.0    # min gap between consecutive confirmed transitions

# Counter-press detection
# Any of these event types by the ANALYSED TEAM inside the transition window
# counts as a pressing response (tackle attempt, interception, challenge,
# aerial duel, foul, or ball recovery).
COUNTER_PRESS_ACTION_IDS: frozenset[int] = frozenset({4, 7, 8, 44, 45, 49})
IMMEDIATE_PRESS_SEC: float = 5.0    # ≤ 5 s = immediate counter-press
DROP_BACK_SEC:       float = 10.0   # > 10 s (or no action) = organised drop

# Single-event touchline filter:
# A possession consisting of exactly 1 event in the deep touchline zone
# (y > TOUCHLINE_Y_MAX or y < TOUCHLINE_Y_MIN) is almost always a fragment
# from a throw-in or corner sequence, not a genuine open-play possession.
TOUCHLINE_Y_MAX: float = 85.0
TOUCHLINE_Y_MIN: float = 15.0

# Last-event type IDs that indicate Team A was NOT in controlled possession:
#   5  = Out           — ball already going out of play
#  44  = Aerial        — contested aerial duel (ball was never "held")
#  45  = Challenge     — contested duel; the opponent had the ball and dribbled
#  52  = Keeper pick-up — GK controlled, not a field-turnover
DEFENSIVE_LOSS_TYPE_IDS: frozenset[int] = frozenset({5, 44, 45, 52})

# Dangerous area boundaries (Team B raw x/y) for N2 outcome classification
# Z14 equivalent  : Team B raw x ≥ OPP_CENTRAL_X_MIN AND y in central band
# Inside box      : Team B raw x ≥ OPP_BOX_X_MIN AND y ∈ [OPP_BOX_Y_MIN, OPP_BOX_Y_MAX]
# Deep flank      : Team B raw x ≥ OPP_DEEP_ATT_X_MIN (any corridor) —
#                   covers dangerous wide positions before the box that are
#                   not captured by the central-channel or box checks.
OPP_CENTRAL_X_MIN:   float = 66.67
OPP_DEEP_ATT_X_MIN:  float = 75.0   # deep attacking third (any corridor → N2)
OPP_BOX_X_MIN:       float = 83.5
OPP_BOX_Y_MIN:       float = 21.0
OPP_BOX_Y_MAX:       float = 79.0
CENTRAL_Y_MIN:       float = 33.33
CENTRAL_Y_MAX:       float = 66.67

# Offside
OFFSIDE_PASS_TYPE_ID:     int = 2
OFFSIDE_PROVOKED_TYPE_ID: int = 55

# Pass type ID (controlled-possession filter)
PASS_TYPE_ID: int = 1

# Shot type IDs
SHOT_TYPE_IDS: frozenset[int] = frozenset({13, 14, 15, 16})

# Corner type ID (Opta F24: corner awarded)
CORNER_TYPE_ID: int = 6

# ── Transition trigger event sets ────────────────────────────────────────────
# Group A — events logged for the OPPONENT (opponent gains possession).
#   49 = Ball Recovery : opponent keeps ball for ≥2 passes/an attacking play
#   8  = Interception  : opponent cuts off our pass, unambiguous possession change
#   (7 = Tackle won handled separately — requires outcome == 1 filter)
TRANSITION_OPP_TRIGGER_IDS: frozenset[int] = frozenset({49, 8})

# Group B — events logged for the TEAM (our player loses the ball).
#   50 = Dispossessed : our player successfully tackled and loses possession
#   51 = Error        : player mistake directly causing an opponent chance
#   (61 = Ball Touch handled separately — requires outcome == 0 filter)
TRANSITION_TEAM_TRIGGER_IDS: frozenset[int] = frozenset({50, 51})

# poss_origin values that indicate a set-piece restart (not open-play transitions)
SET_PIECE_ORIGINS: frozenset[str] = frozenset({
    "corner", "free_kick", "throw_in", "goal_kick", "penalty", "gk_hands",
})

# Box boundary (same as goalkeeper_buildup)
BOX_X: float = 83.33


# ═══════════════════════════════════════════════════════════════════════════════
# COORDINATE HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _x_to_zone_group(x: float) -> str:
    if x >= HIGH_X_MIN:
        return "high"
    if x >= MID_X_MIN:
        return "mid"
    return "low"


def _y_to_corridor(y: float) -> str:
    if y > LEFT_Y_MIN:
        return "L"
    if y < RIGHT_Y_MAX:
        return "R"
    return "C"


# ═══════════════════════════════════════════════════════════════════════════════
# SHARED OFFSIDE EVENTS HELPER
# ═══════════════════════════════════════════════════════════════════════════════

def _get_offside_events(
    team_df: pd.DataFrame,
    opp_df: pd.DataFrame,
) -> list[dict]:
    """
    Collect all offside-related events where the analysed team's defence
    provoked an offside, and return a list of dicts with keys:
    {x, y, minute, source}.

    Only type_id == OFFSIDE_PROVOKED_TYPE_ID (55) from team_df is used.
    That event is awarded by Opta to the last defender of the defending
    team, so its x/y directly gives the defensive line height in the
    analysed team's coordinate frame.

    The former "opp_pass" fallback (type_id=2 from opp_df reflected) has
    been removed because:
      • type_id=2 records the PASSER's position, not the defender's line.
      • Reflecting the passer's x gives a spurious value for incidents
        where the opponent passed from deep in their own half.
      • Every type_id=55 event is always present alongside its paired
        type_id=2 event, so no data is lost.
    """
    events: list[dict] = []

    provoked = team_df[
        pd.to_numeric(team_df.get("type_id", pd.Series(dtype=float)), errors="coerce")
        == OFFSIDE_PROVOKED_TYPE_ID
    ]
    for _, row in provoked.iterrows():
        x = row.get("x")
        y = row.get("y")
        if pd.isna(x) or pd.isna(y):
            continue
        events.append({
            "x":      float(x),
            "y":      float(y),
            "minute": int(row.get("minute", 0) or 0),
            "source": "provoked",
        })

    return events


# ═══════════════════════════════════════════════════════════════════════════════
# D2.1 — DEFENSIVE TRANSITIONS
# ═══════════════════════════════════════════════════════════════════════════════

# ── Qualifier detection helpers ─────────────────────────────────────────────

def _has_cross_qualifier(row) -> bool:
    val = str(row.get("Cross", row.get("cross", ""))).strip().lower()
    return val in ("si", "yes", "1", "true")


def _pass_end_x(row) -> float:
    v = row.get("Pass End X", row.get("pass_end_x", None))
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _has_penalty_qualifier(row) -> bool:
    val = str(row.get("Penalty", row.get("penalty", ""))).strip().lower()
    return val in ("si", "yes", "1", "true")


def compute_defensive_transitions(
    team_df: pd.DataFrame,
    opp_df: pd.DataFrame,
    full_df: pd.DataFrame,
    team_lower: str,
) -> dict:
    """
    Detect and analyse defensive transitions for the analysed team.

    WHAT CHANGED FROM THE PREVIOUS POSSESSION-BOUNDARY IMPLEMENTATION
    ==================================================================
    The previous version iterated over consecutive possession pairs from
    ``build_possessions()``, triggering on any Team A → Team B handoff.
    This was imprecise because:
      • It relied entirely on the possession engine's segmentation, which
        sometimes fragments a single counter-attack into multiple possession
        IDs (e.g. a 1-event team touch mid-episode creates a spurious pair).
      • Some genuine trigger events (Dispossessed, type_id=50) are logged on
        the TEAM's own rows, not the opponent's, and were therefore missed.

    The new approach scans every row of ``full_df`` individually and checks
    whether a specific Opta event type represents the exact moment of
    possession loss, split into two groups based on which team's event stream
    the trigger appears in.

    EVENTS USED AS TRANSITION TRIGGERS
    ====================================
    Group A — Opponent events (opponent has just gained possession):
      - type_id=49, Ball Recovery [PRIMARY TRIGGER]:
          Opta only logs this when the recovering team subsequently keeps the
          ball for ≥2 passes or sustains an attacking play.  It is the
          strongest and most selective signal of a genuine possession change.
      - type_id=8, Interception:
          Opponent player cuts off our pass before it reaches its target.
          Unambiguous open-play possession change.
      - type_id=7, Tackle, outcome==1 only:
          Opponent physically wins the ball from our player AND retains it.
          outcome=0 (tackle attempt without confirmed retention) is excluded.

    Group B — Team events (our player has just lost the ball):
      - type_id=50, Dispossessed:
          Our player is successfully tackled and explicitly loses possession.
          This event is on OUR event rows, which is why it was missed by the
          previous possession-pair approach.
      - type_id=51, Error:
          Player mistake directly causing an opponent chance.  Always
          open-play by definition and the highest-danger trigger.
      - type_id=61, Ball Touch, outcome==0 only:
          Our player failed to control the ball — a loose touch that the
          opponent recovers.  outcome=1 (ball struck player unintentionally)
          is excluded because the ball was never under our control.

    EVENTS EXPLICITLY EXCLUDED AND WHY
    ====================================
      - type_id=5  (Out)         : ball goes out → throw-in / goal kick
                                   restart, not an open-play transition.
      - type_id=6  (Corner)      : set-piece restart.
      - type_id=2  (Offside Pass): leads to a free-kick restart.
      - type_id=9  (Turnover)    : marked "NO LONGER USED" in Opta F1.
      - type_id=4  (Foul victim) : foul leads to a free-kick restart.
      - type_id=44 (Aerial)      : contested aerial — ball was never held by
                                   either team; excluded via DEFENSIVE_LOSS_TYPE_IDS.
      - type_id=45 (Challenge)   : contested duel; excluded via same guard.
      - type_id=52 (GK pick-up)  : GK controlled ball; not a field turnover.
      - All shot types (13,14,15,16): attacking attempt, not a turnover.

    HOW THE ALGORITHM WORKS (STEP BY STEP)
    ========================================
    1. Sort ``full_df`` by [period, _match_sec, event_id].  Pre-compute
       ``_team_lower``, ``_tid`` and ``_out`` integer columns for speed.
    2. Build a ``poss_origin_map`` (poss_id → poss_origin) from the
       ``poss_origin`` column added by ``build_possessions()``.
    3. Scan every row:
       a. Determine if it is a Group A or Group B trigger.
       b. Resolve ORIGIN COORDINATES:
            Group B (team’s row): use the trigger event’s own x, y — that
              is exactly where our player lost the ball.
            Group A (opponent’s row): scan backwards through ``full_sorted``
              to find the last Team A play event (using ``_is_play_event``)
              in the same period and use its x, y.
       c. Discard if origin_x < ATTACKING_HALF_MIN (50) — transition must
          start in the offensive half.
       d. Discard if the origin event type is a contested duel
          (DEFENSIVE_LOSS_TYPE_IDS), a shot (SHOT_TYPE_IDS), or has
          out-of-bounds coordinates.
       e. SET-PIECE EXCLUSION: look up the poss_origin of the opponent’s
          next possession via poss_origin_map.  If it is in SET_PIECE_ORIGINS
          (corner, free_kick, throw_in, goal_kick, penalty, gk_hands), skip
          — the trigger led to an organised restart, not a transition.
       f. FOUL GUARD: if the opponent committed a foul (type_id=4) within
          FOUL_GUARD_SEC before the trigger, the ball was not genuinely won
          (it will be a free kick for our team); skip.
       g. DEDUPLICATION: if a confirmed transition was already recorded within
          DEDUP_WINDOW_SEC, skip (same counter-attack episode).
       h. WINDOW SCAN: scan [trigger_sec, trigger_sec + TRANSITION_WINDOW_SEC]
          for opponent events.  CONFIRM when opponent raw x ≥ OPP_ATT_THIRD_MIN.
          Accumulate outcome flags (shot, dangerous central, deep flank, box,
          set piece won).  Handle offside-pass coordinate correction.
       i. If not confirmed, discard.  Otherwise classify N1/N2/N3 and record.
    4. Aggregate counts, rates, zone breakdowns and return the result dict.

    WHAT REMAINS UNCHANGED
    =======================
    - Outcome classification (N1 / N2 / N3) is identical.
    - Output dict keys are identical — no changes to the card rendering layer.
    - Transition window scanning (confirmation + outcome flags) is unchanged.
    - Offside-pass coordinate correction in the window is unchanged.
    - Set-piece exclusion via poss_origin is unchanged (now applied at
      trigger time rather than possession-pair iteration time).
    """
    try:
        full_sorted = full_df.sort_values(
            ["period", "_match_sec", "event_id"],
            na_position="last",
        ).reset_index(drop=True)

        if "_match_sec" not in full_sorted.columns:
            full_sorted["_match_sec"] = (
                full_sorted["minute"].fillna(0).astype(float) * 60.0
                + full_sorted["second"].fillna(0).astype(float)
            )

        total_team_poss = (
            team_df["poss_id"].nunique() if "poss_id" in team_df.columns else 1
        ) or 1

        if "poss_id" not in full_sorted.columns:
            return _empty_transitions()

        # ── total_transitions: raw opp Ball Recovery count ───────────────────
        opp_ball_recoveries = opp_df[
            pd.to_numeric(opp_df["type_id"], errors="coerce") == 49
        ]
        total_transitions = len(opp_ball_recoveries)

        # ── Pre-compute fast-lookup columns ──────────────────────────────────
        full_sorted["_tl"] = full_sorted["team_name"].apply(
            lambda t: canonical_name(str(t).strip()).lower()
        )
        full_sorted["_tid"] = (
            pd.to_numeric(full_sorted["type_id"], errors="coerce")
            .fillna(-1).astype(int)
        )
        full_sorted["_out"] = (
            pd.to_numeric(full_sorted["outcome"], errors="coerce")
            .fillna(-1).astype(int)
        )

        # ── Build poss_id → poss_origin lookup ───────────────────────────────
        poss_origin_map: dict[int, str] = {}
        if "poss_origin" in full_sorted.columns:
            for pid, origin in (
                full_sorted.dropna(subset=["poss_id"])
                .groupby("poss_id")["poss_origin"]
                .first()
                .items()
            ):
                poss_origin_map[int(pid)] = str(origin or "open_play")

        n_rows      = len(full_sorted)
        transitions: list[dict] = []
        last_trigger_sec: float = -9999.0

        for idx in range(n_rows):
            row    = full_sorted.iloc[idx]
            w_team = row["_tl"]
            is_team = (w_team == team_lower)
            is_opp  = (not is_team) and (w_team != "")

            if not is_team and not is_opp:
                continue

            tid     = int(row["_tid"])
            out_val = int(row["_out"])

            # ── identify trigger group ────────────────────────────────────────
            group = ""
            if is_opp:
                if tid in TRANSITION_OPP_TRIGGER_IDS:
                    group = "A"
                elif tid == 7 and out_val == 1:   # Tackle won
                    group = "A"
            elif is_team:
                if tid in TRANSITION_TEAM_TRIGGER_IDS:
                    group = "B"
                elif tid == 61 and out_val == 0:  # Failed ball touch
                    group = "B"

            if not group:
                continue

            trigger_sec = float(row.get("_match_sec", 0) or 0)
            period      = row.get("period")

            # ── set-piece exclusion ───────────────────────────────────────────
            _poss_id_raw = row.get("poss_id")
            try:
                _poss_id = int(float(_poss_id_raw)) if pd.notna(_poss_id_raw) else None
            except (ValueError, TypeError):
                _poss_id = None

            if group == "A":
                opp_origin = poss_origin_map.get(_poss_id, "open_play") if _poss_id else "open_play"
            else:
                opp_origin = "open_play"
                for fwd in range(idx + 1, min(idx + 50, n_rows)):
                    fwd_row = full_sorted.iloc[fwd]
                    fwd_tl  = fwd_row["_tl"]
                    if fwd_tl != team_lower and fwd_tl != "":
                        fwd_pid_raw = fwd_row.get("poss_id")
                        try:
                            fwd_pid = int(float(fwd_pid_raw)) if pd.notna(fwd_pid_raw) else None
                        except (ValueError, TypeError):
                            fwd_pid = None
                        if fwd_pid is not None:
                            opp_origin = poss_origin_map.get(fwd_pid, "open_play")
                        break

            if opp_origin in SET_PIECE_ORIGINS:
                continue

            # ── resolve origin coordinates ────────────────────────────────────
            if group == "B":
                ox_raw = row.get("x")
                oy_raw = row.get("y")
                origin_x   = float(ox_raw) if pd.notna(ox_raw) else None
                origin_y   = float(oy_raw) if pd.notna(oy_raw) else None
                origin_tid = tid
            else:
                origin_x = origin_y = None
                origin_tid = -1
                for bk in range(idx - 1, max(idx - 300, -1), -1):
                    bk_row = full_sorted.iloc[bk]
                    if bk_row.get("period") != period:
                        break
                    if bk_row["_tl"] != team_lower:
                        continue
                    bk_et = str(bk_row.get("event_type", "")).strip().lower()
                    if bk_et in NON_PLAY_EVENTS or bk_et == "":
                        continue
                    ox_raw = bk_row.get("x")
                    oy_raw = bk_row.get("y")
                    origin_x   = float(ox_raw) if pd.notna(ox_raw) else None
                    origin_y   = float(oy_raw) if pd.notna(oy_raw) else None
                    origin_tid = int(bk_row["_tid"])
                    break

            if origin_x is None:
                continue

            # ── trigger must be in Team A's offensive half ────────────────────
            if origin_x < ATTACKING_HALF_MIN:
                continue

            # ── event-type guards ─────────────────────────────────────────────
            if origin_tid in DEFENSIVE_LOSS_TYPE_IDS:
                continue
            if origin_tid in SHOT_TYPE_IDS:
                continue

            _oy = float(origin_y or 50.0)
            if not (0.0 <= origin_x <= 100.0 and 0.0 <= _oy <= 100.0):
                continue

            # ── foul guard ────────────────────────────────────────────────────
            foul_guard_mask = (
                (full_sorted["period"] == period)
                & (full_sorted["_match_sec"] >= trigger_sec - FOUL_GUARD_SEC)
                & (full_sorted["_match_sec"] <= trigger_sec + 1.0)
                & (full_sorted["_tl"] != team_lower)
                & (full_sorted["_tl"] != "")
                & (full_sorted["_tid"] == FOUL_TYPE_ID)
            )
            if foul_guard_mask.any():
                continue

            # ── deduplication ─────────────────────────────────────────────────
            if trigger_sec - last_trigger_sec < DEDUP_WINDOW_SEC:
                continue

            last_trigger_sec = trigger_sec
            corridor = _y_to_corridor(_oy)

            # ── scan transition window ────────────────────────────────────────
            win_mask = (
                (full_sorted["period"] == period)
                & (full_sorted["_match_sec"] >= trigger_sec)
                & (full_sorted["_match_sec"] <= trigger_sec + TRANSITION_WINDOW_SEC)
            )
            window = full_sorted[win_mask]

            n3_shot_flag:    bool = False
            n3_penalty_flag: bool = False
            n2_corner_flag:  bool = False
            n2_foul_flag:    bool = False
            n2_cross_flag:   bool = False
            n1_depth_flag:   bool = False
            n1_time_flag:    bool = False
            reaction_time_raw: float | None = None
            team_first_press_sec: float | None = None   # time of team's first counter-press action

            for _, w_row in window.iterrows():
                w_tl  = w_row["_tl"]
                w_tid = int(w_row["_tid"])
                w_out = int(w_row["_out"])
                w_x_raw = w_row.get("x")
                w_y_raw = w_row.get("y")
                w_x   = float(w_x_raw) if pd.notna(w_x_raw) else None
                w_y   = float(w_y_raw) if pd.notna(w_y_raw) else 50.0
                w_sec = float(w_row.get("_match_sec", trigger_sec))

                if w_tl == team_lower:
                    # Track counter-press response: first team defensive action in window
                    if team_first_press_sec is None and w_tid in COUNTER_PRESS_ACTION_IDS:
                        team_first_press_sec = w_sec - trigger_sec
                    # Team's own events — detect fouls only
                    if w_tid == FOUL_TYPE_ID and w_out == 0 and w_x is not None:
                        x_att = 100.0 - w_x
                        if _has_penalty_qualifier(w_row) or (
                            x_att >= BOX_X
                            and OPP_BOX_Y_MIN <= w_y <= OPP_BOX_Y_MAX
                        ):
                            n3_penalty_flag = True
                            if reaction_time_raw is None:
                                reaction_time_raw = w_sec - trigger_sec
                        elif x_att >= OPP_ATT_THIRD_MIN:
                            n2_foul_flag = True
                            if reaction_time_raw is None:
                                reaction_time_raw = w_sec - trigger_sec
                    continue

                if w_tl == "" or w_x is None:
                    continue

                # Opponent events
                # N3: shot
                if w_tid in SHOT_TYPE_IDS:
                    n3_shot_flag = True
                    if reaction_time_raw is None:
                        reaction_time_raw = w_sec - trigger_sec

                # N2: corner in final third
                if w_tid == CORNER_TYPE_ID and w_x >= OPP_ATT_THIRD_MIN:
                    n2_corner_flag = True
                    if reaction_time_raw is None:
                        reaction_time_raw = w_sec - trigger_sec

                # N2: cross into the box
                if (
                    w_tid == PASS_TYPE_ID
                    and _has_cross_qualifier(w_row)
                    and _pass_end_x(w_row) >= BOX_X
                ):
                    n2_cross_flag = True
                    if reaction_time_raw is None:
                        reaction_time_raw = w_sec - trigger_sec

                # N1: reached opponent's final third (our defensive third)
                if w_x >= OPP_ATT_THIRD_MIN:
                    n1_depth_flag = True
                    if reaction_time_raw is None:
                        reaction_time_raw = w_sec - trigger_sec

                # N1: held possession ≥ 15 s
                if w_sec - trigger_sec >= 15.0:
                    n1_time_flag = True

            # Determine worst outcome reached
            if n3_shot_flag or n3_penalty_flag:
                outcome: str | None = "N3"
            elif n2_corner_flag or n2_foul_flag or n2_cross_flag:
                outcome = "N2"
            elif n1_depth_flag or n1_time_flag:
                outcome = "N1"
            else:
                outcome = None  # non-qualified

            reaction_time = (
                round(reaction_time_raw, 2)
                if reaction_time_raw is not None
                else TRANSITION_WINDOW_SEC
            )

            transitions.append({
                "x":                   origin_x,
                "y":                   _oy,
                "zone_group":          _x_to_zone_group(origin_x),
                "corridor":            corridor,
                "outcome":             outcome,
                "reaction_time":       reaction_time,
                "match_sec":           trigger_sec,
                "team_first_press_sec": team_first_press_sec,
            })

        # ── Aggregate ─────────────────────────────────────────────────────────
        qualified = [t for t in transitions if t["outcome"] is not None]
        q  = len(qualified)
        n1 = sum(1 for t in qualified if t["outcome"] == "N1")
        n2 = sum(1 for t in qualified if t["outcome"] == "N2")
        n3 = sum(1 for t in qualified if t["outcome"] == "N3")

        transition_rate = round(q / total_team_poss * 100, 1) if total_team_poss else 0.0

        react_times = [t["reaction_time"] for t in qualified]
        avg_reaction = round(float(np.mean(react_times)), 2) if react_times else 0.0

        avg_react_by_zone: dict[str, float] = {"high": 0.0, "mid": 0.0, "low": 0.0}
        for zg in ("high", "mid", "low"):
            zt = [t["reaction_time"] for t in qualified if t["zone_group"] == zg]
            if zt:
                avg_react_by_zone[zg] = round(float(np.mean(zt)), 2)

        outcomes_by_zone: dict[str, dict[str, int]] = {
            zg: {"N1": 0, "N2": 0, "N3": 0}
            for zg in ("high", "mid", "low")
        }
        for t in qualified:
            outcomes_by_zone[t["zone_group"]][t["outcome"]] += 1

        outcomes_by_corridor: dict[str, dict[str, int]] = {
            c: {"N1": 0, "N2": 0, "N3": 0}
            for c in ("L", "C", "R")
        }
        for t in qualified:
            outcomes_by_corridor[t["corridor"]][t["outcome"]] += 1

        origins = [
            {
                "x":            t["x"],
                "y":            t["y"],
                "zone_group":   t["zone_group"],
                "corridor":     t["corridor"],
                "outcome":      t["outcome"],
                "reaction_time": t["reaction_time"],
            }
            for t in qualified
            if t["x"] >= MID_X_MIN
        ]

        all_t = len(transitions)
        if all_t > 0:
            immediate_press_rate = round(
                sum(
                    1 for t in transitions
                    if t["team_first_press_sec"] is not None
                    and t["team_first_press_sec"] <= IMMEDIATE_PRESS_SEC
                ) / all_t * 100, 1
            )
            drop_back_rate = round(
                sum(
                    1 for t in transitions
                    if t["team_first_press_sec"] is None
                    or t["team_first_press_sec"] > DROP_BACK_SEC
                ) / all_t * 100, 1
            )
        else:
            immediate_press_rate = 0.0
            drop_back_rate       = 0.0

        return {
            "total_transitions":         total_transitions,
            "qualified_transitions":     q,
            "transition_rate":           transition_rate,
            "immediate_press_rate":      immediate_press_rate,
            "drop_back_rate":            drop_back_rate,
            "avg_reaction_time_sec":     avg_reaction,
            "avg_reaction_time_by_zone": avg_react_by_zone,
            "avg_transition_depth_dx":   0.0,
            "outcome_distribution":      {"N1": n1, "N2": n2, "N3": n3},
            "outcomes_by_zone":          outcomes_by_zone,
            "outcomes_by_corridor":      outcomes_by_corridor,
            "transition_origins":        origins,
        }

    except Exception:
        log.exception("compute_defensive_transitions failed")
        return _empty_transitions()


def _empty_transitions() -> dict:
    return {
        "total_transitions":         0,
        "qualified_transitions":     0,
        "transition_rate":           0.0,
        "immediate_press_rate":      0.0,
        "drop_back_rate":            0.0,
        "avg_reaction_time_sec":     0.0,
        "avg_reaction_time_by_zone": {"high": 0.0, "mid": 0.0, "low": 0.0},
        "avg_transition_depth_dx":   0.0,
        "outcome_distribution":      {"N1": 0, "N2": 0, "N3": 0},
        "outcomes_by_zone": {
            "high": {"N1": 0, "N2": 0, "N3": 0},
            "mid":  {"N1": 0, "N2": 0, "N3": 0},
            "low":  {"N1": 0, "N2": 0, "N3": 0},
        },
        "outcomes_by_corridor": {
            "L": {"N1": 0, "N2": 0, "N3": 0},
            "C": {"N1": 0, "N2": 0, "N3": 0},
            "R": {"N1": 0, "N2": 0, "N3": 0},
        },
        "transition_origins": [],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# D2.2.1 — OFFSIDE LINE
# ═══════════════════════════════════════════════════════════════════════════════

def compute_offside_line(
    team_df: pd.DataFrame,
    opp_df: pd.DataFrame,
    full_df: pd.DataFrame,
    team_lower: str,
) -> dict:
    """Compute defensive line height via offside event x-coordinates."""
    try:
        events = _get_offside_events(team_df, opp_df)

        if not events:
            return {
                "offside_line_median":       None,
                "offside_line_variance":     None,
                "offside_count":             0,
                "offside_line_first_half":   None,
                "offside_line_second_half":  None,
                "offside_events_detail":     [],
            }

        xs = [e["x"] for e in events]
        median_x = round(float(np.median(xs)), 1)
        std_x    = round(float(np.std(xs)), 2)

        first_half  = [e["x"] for e in events if e["minute"] < 45]
        second_half = [e["x"] for e in events if e["minute"] >= 45]

        return {
            "offside_line_median":       median_x,
            "offside_line_variance":     std_x,
            "offside_count":             len(events),
            "offside_line_first_half":   round(float(np.median(first_half)), 1)  if first_half  else None,
            "offside_line_second_half":  round(float(np.median(second_half)), 1) if second_half else None,
            "offside_events_detail":     events,
        }

    except Exception:
        log.exception("compute_offside_line failed")
        return {
            "offside_line_median":       None,
            "offside_line_variance":     None,
            "offside_count":             0,
            "offside_line_first_half":   None,
            "offside_line_second_half":  None,
            "offside_events_detail":     [],
        }


# ═══════════════════════════════════════════════════════════════════════════════
# D2.2.2 — OFFSIDE TRAP
# ═══════════════════════════════════════════════════════════════════════════════

def compute_offside_trap(
    team_df: pd.DataFrame,
    opp_df: pd.DataFrame,
    full_df: pd.DataFrame,
    team_lower: str,
) -> dict:
    """Compute offside trap metrics — clustering index, corridor, zone distribution."""
    try:
        events = _get_offside_events(team_df, opp_df)
        n = len(events)

        empty = {
            "offsides_provoked":              0,
            "offside_corridor_distribution":  {"L": 0, "C": 0, "R": 0},
            "offside_corridor_pcts":          {"L": 0.0, "C": 0.0, "R": 0.0},
            "offside_zone_distribution":      {z: 0 for z in range(1, 19)},
            "offside_clustering_index":       0.0,
            "offside_height_zone_distribution": {"high": 0, "mid": 0, "low": 0},
        }

        if n == 0:
            return empty

        xs = [e["x"] for e in events]
        median_x = float(np.median(xs))

        # Clustering index: % within ±5 of median
        in_cluster = sum(1 for x in xs if abs(x - median_x) <= 5.0)
        clustering_index = round(in_cluster / n * 100, 1)

        # Corridor distribution
        corr_dist: dict[str, int] = {"L": 0, "C": 0, "R": 0}
        for e in events:
            corr_dist[_y_to_corridor(e["y"])] += 1
        corr_pcts = {k: round(v / n * 100, 1) for k, v in corr_dist.items()}

        # Zone distribution (18-zone)
        zone_dist: dict[int, int] = {z: 0 for z in range(1, 19)}
        for e in events:
            z = xy_to_zone(e["x"], e["y"])
            zone_dist[z] = zone_dist.get(z, 0) + 1

        # Height zone distribution (based on x)
        height_dist: dict[str, int] = {"high": 0, "mid": 0, "low": 0}
        for e in events:
            height_dist[_x_to_zone_group(e["x"])] += 1

        return {
            "offsides_provoked":              n,
            "offside_corridor_distribution":  corr_dist,
            "offside_corridor_pcts":          corr_pcts,
            "offside_zone_distribution":      zone_dist,
            "offside_clustering_index":       clustering_index,
            "offside_height_zone_distribution": height_dist,
        }

    except Exception:
        log.exception("compute_offside_trap failed")
        return {
            "offsides_provoked":              0,
            "offside_corridor_distribution":  {"L": 0, "C": 0, "R": 0},
            "offside_corridor_pcts":          {"L": 0.0, "C": 0.0, "R": 0.0},
            "offside_zone_distribution":      {z: 0 for z in range(1, 19)},
            "offside_clustering_index":       0.0,
            "offside_height_zone_distribution": {"high": 0, "mid": 0, "low": 0},
        }


# ═══════════════════════════════════════════════════════════════════════════════
# D2.2.3 — STRUCTURAL MIRROR
# ═══════════════════════════════════════════════════════════════════════════════

def compute_structural_mirror(match_csv: Path, opponent_name: str) -> dict:
    """
    Mirror the opponent's Phase 2 offensive analysis to understand how they
    attacked us.  Calls analyse_final_third(match_csv, opponent_name).
    All keys are prefixed with "opp_".
    """
    _opp_empty: dict[str, Any] = {
        "opp_ft_entries_total":        0,
        "opp_ft_entry_left_count":     0,
        "opp_ft_entry_centre_count":   0,
        "opp_ft_entry_right_count":    0,
        "opp_ft_entry_left_pct":       0.0,
        "opp_ft_entry_centre_pct":     0.0,
        "opp_ft_entry_right_pct":      0.0,
        "opp_method_counts":           {},
        "opp_method_pcts":             {},
        "opp_z14_count":               0,
        "opp_z14_pct":                 0.0,
        "opp_flanks_count":            0,
        "opp_flanks_pct":              0.0,
        "opp_positive_count":          0,
        "opp_negative_count":          0,
        "opp_positive_pct":            0.0,
        "opp_avg_passes_before_ft":    0.0,
        "opp_avg_seconds_to_ft":       0.0,
        "opp_possession_pct":          0.0,
        "opp_dominant_method":         None,
    }

    try:
        from src.analytics.final_third import analyse_final_third
        result = analyse_final_third(match_csv, opponent_name)
        m = result.get("metrics", {})

        corridor_counts = m.get("corridor_counts", {})
        corridor_pcts   = m.get("corridor_pcts", {})
        zone_reach      = m.get("zone_reach", {})
        outcomes        = m.get("outcomes", {})
        method_counts   = m.get("method_counts", {})

        # Dominant method
        dominant_method: str | None = None
        if method_counts:
            dominant_method = max(method_counts, key=lambda k: method_counts[k])

        return {
            "opp_ft_entries_total":        m.get("total_ft_entries", 0),
            "opp_ft_entry_left_count":     corridor_counts.get("L", 0),
            "opp_ft_entry_centre_count":   corridor_counts.get("C", 0),
            "opp_ft_entry_right_count":    corridor_counts.get("R", 0),
            "opp_ft_entry_left_pct":       corridor_pcts.get("L", 0.0),
            "opp_ft_entry_centre_pct":     corridor_pcts.get("C", 0.0),
            "opp_ft_entry_right_pct":      corridor_pcts.get("R", 0.0),
            "opp_method_counts":           method_counts,
            "opp_method_pcts":             m.get("method_pcts", {}),
            "opp_z14_count":               zone_reach.get("z14", {}).get("count", 0),
            "opp_z14_pct":                 zone_reach.get("z14", {}).get("pct",   0.0),
            "opp_flanks_count":            zone_reach.get("flanks", {}).get("count", 0),
            "opp_flanks_pct":              zone_reach.get("flanks", {}).get("pct",   0.0),
            "opp_positive_count":          outcomes.get("positive", {}).get("count", 0),
            "opp_negative_count":          outcomes.get("negative", {}).get("count", 0),
            "opp_positive_pct":            outcomes.get("positive", {}).get("pct",   0.0),
            "opp_avg_passes_before_ft":    m.get("avg_passes_before_entry", 0.0),
            "opp_avg_seconds_to_ft":       m.get("avg_seconds_to_entry",    0.0),
            "opp_possession_pct":          m.get("possession_pct",          0.0),
            "opp_dominant_method":         dominant_method,
        }

    except Exception:
        log.exception("compute_structural_mirror failed for opponent=%s", opponent_name)
        return _opp_empty





# ═══════════════════════════════════════════════════════════════════════════════
# EMPTY RESULT FALLBACK
# ═══════════════════════════════════════════════════════════════════════════════

def _empty_result() -> dict[str, Any]:
    return {
        # Transitions
        "total_transitions":         0,
        "qualified_transitions":     0,
        "transition_rate":           0.0,
        "immediate_press_rate":      0.0,
        "drop_back_rate":            0.0,
        "avg_reaction_time_sec":     0.0,
        "avg_reaction_time_by_zone": {"high": 0.0, "mid": 0.0, "low": 0.0},
        "avg_transition_depth_dx":   0.0,
        "outcome_distribution":      {"N1": 0, "N2": 0, "N3": 0},
        "outcomes_by_zone": {
            "high": {"N1": 0, "N2": 0, "N3": 0},
            "mid":  {"N1": 0, "N2": 0, "N3": 0},
            "low":  {"N1": 0, "N2": 0, "N3": 0},
        },
        "outcomes_by_corridor": {
            "L": {"N1": 0, "N2": 0, "N3": 0},
            "C": {"N1": 0, "N2": 0, "N3": 0},
            "R": {"N1": 0, "N2": 0, "N3": 0},
        },
        "transition_origins":        [],
        # Offside (unchanged)
        "offside_line_median":        None,
        "offside_line_variance":      None,
        "offside_count":              0,
        "offside_line_first_half":    None,
        "offside_line_second_half":   None,
        "offside_events_detail":      [],
        "offsides_provoked":          0,
        "offside_corridor_distribution": {"L": 0, "C": 0, "R": 0},
        "offside_corridor_pcts":      {"L": 0.0, "C": 0.0, "R": 0.0},
        "offside_zone_distribution":  {z: 0 for z in range(1, 19)},
        "offside_clustering_index":   0.0,
        "offside_height_zone_distribution": {"high": 0, "mid": 0, "low": 0},
        # Mirror (unchanged)
        "opp_ft_entries_total":       0,
        "opp_ft_entry_left_count":    0,
        "opp_ft_entry_centre_count":  0,
        "opp_ft_entry_right_count":   0,
        "opp_ft_entry_left_pct":      0.0,
        "opp_ft_entry_centre_pct":    0.0,
        "opp_ft_entry_right_pct":     0.0,
        "opp_method_counts":          {},
        "opp_method_pcts":            {},
        "opp_z14_count":              0,
        "opp_z14_pct":                0.0,
        "opp_flanks_count":           0,
        "opp_flanks_pct":             0.0,
        "opp_positive_count":         0,
        "opp_negative_count":         0,
        "opp_positive_pct":           0.0,
        "opp_avg_passes_before_ft":   0.0,
        "opp_avg_seconds_to_ft":      0.0,
        "opp_possession_pct":         0.0,
        "opp_dominant_method":        None,
        # Injected by analysis_callbacks.py after the call
        "pressing_line_median":       None,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def analyse_defensive_structure(match_csv: Path, team: str) -> dict[str, Any]:
    """
    Run the full D2 analysis for *team* in the given match CSV.
    Returns a flat dict consumed by defensive_structure_cards.py.
    On any error returns _empty_result().
    """
    try:
        team_lower = canonical_name(str(team)).lower()

        df = _load_match_events(match_csv)
        if df.empty:
            return _empty_result()

        # Ensure numeric type_id
        if "type_id" in df.columns:
            df["type_id"] = pd.to_numeric(df["type_id"], errors="coerce")

        # Ensure _match_sec exists
        if "_match_sec" not in df.columns:
            df["_match_sec"] = (
                df["minute"].fillna(0).astype(float) * 60.0
                + df["second"].fillna(0).astype(float)
            )

        # Build possession chains
        df = build_possessions(df)

        # Resolve opponent
        opponent_name: str | None = None
        all_teams = df["team_name"].dropna().unique()
        for t in all_teams:
            if canonical_name(str(t)).lower() != team_lower:
                opponent_name = str(t)
                break

        # Split team / opponent
        team_mask = df["team_name"].apply(
            lambda t: canonical_name(str(t).strip()).lower() == team_lower
        )
        team_df = df[team_mask].copy()
        opp_df  = df[~team_mask].copy()

        # Sub-analyses (each wrapped individually)
        try:
            transitions = compute_defensive_transitions(team_df, opp_df, df, team_lower)
        except Exception:
            log.exception("transitions failed")
            transitions = _empty_transitions()

        try:
            offside_line = compute_offside_line(team_df, opp_df, df, team_lower)
        except Exception:
            log.exception("offside_line failed")
            offside_line = {
                "offside_line_median": None, "offside_line_variance": None,
                "offside_count": 0, "offside_line_first_half": None,
                "offside_line_second_half": None, "offside_events_detail": [],
            }

        try:
            offside_trap = compute_offside_trap(team_df, opp_df, df, team_lower)
        except Exception:
            log.exception("offside_trap failed")
            offside_trap = {
                "offsides_provoked": 0,
                "offside_corridor_distribution": {"L": 0, "C": 0, "R": 0},
                "offside_corridor_pcts": {"L": 0.0, "C": 0.0, "R": 0.0},
                "offside_zone_distribution": {z: 0 for z in range(1, 19)},
                "offside_clustering_index": 0.0,
                "offside_height_zone_distribution": {"high": 0, "mid": 0, "low": 0},
            }

        try:
            mirror = (
                compute_structural_mirror(match_csv, opponent_name)
                if opponent_name else {}
            )
        except Exception:
            log.exception("structural_mirror failed")
            mirror = {}

        return {
            **transitions,
            **offside_line,
            **offside_trap,
            **mirror,
        }

    except Exception:
        log.exception("analyse_defensive_structure failed for team=%s", team)
        return _empty_result()
