"""
Offensive Transitions — Analytics
===================================
Analyses what the selected team does AFTER winning the ball:
how quickly they transition forward, how far they get, and
whether they create a dangerous situation.

This is the mirror image of ``defensive_structure.py``
``compute_defensive_transitions()``.  Here:
  • TRIGGER  = the team wins the ball (ball recovery / tackle / interception)
  • WINDOW   = 25 s of the TEAM's own play scanned forward
  • OUTCOMES = P1 / P2 / P3  (replacing N1 / N2 / N3)

Outcome definitions
-------------------
  P1 — Sustained : team held possession ≥ 15 s OR entered the opponent's
                   final third (x ≥ 66.67 in team coords).
  P2 — Threatening : team won a corner / free kick in the attacking third,
                     OR delivered a cross targeting the box.
  P3 — Dangerous  : team generated a shot, penalty or goal.

Origin filtering
----------------
Only transitions that begin in the TEAM's OWN HALF (x ≤ 50) are
kept as "qualified" and plotted on the pitch map.  This mirrors the
defensive side's x ≥ 33.33 filter and ensures the map shows genuine
counter-attacking sequences (ball won in defensive or middle third).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.analytics.general_buildup import build_possessions
from src.team_mapping import canonical_name
from src.utils.logging import log

# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

# Spatial thresholds (all in Opta 0-100 coordinate system, left-to-right)
OWN_HALF_MAX:       float = 50.0    # origin must be ≤ this (ball won in own half)
ATT_THIRD_MIN:      float = 66.67   # x at which team enters opponent's final third
BOX_X:              float = 83.33   # penalty-area front edge
OPP_BOX_Y_MIN:      float = 21.0
OPP_BOX_Y_MAX:      float = 79.0

LEFT_Y_MIN:  float = 66.67
RIGHT_Y_MAX: float = 33.33

# Temporal thresholds
TRANSITION_WINDOW_SEC: float = 25.0   # seconds to scan after ball won
DEDUP_WINDOW_SEC:      float = 8.0    # ignore new trigger if last one < 8 s ago
FOUL_GUARD_SEC:        float = 3.0    # ignore if TEAM fouled opp in last 3 s

# ── Event type IDs ────────────────────────────────────────────────────────────
# Group A  — TEAM events that represent the team winning the ball
BALL_WIN_TEAM_IDS: frozenset[int] = frozenset({
    49,   # Ball Recovery (team wins loose ball)
    8,    # Interception
})
# type_id 7 (Tackle) with outcome==1 also counts

# Group B  — OPPONENT events that confirm the team gained possession
BALL_WIN_OPP_IDS: frozenset[int] = frozenset({
    50,   # Dispossessed (opponent's player lost the ball to our team)
    51,   # Error
})
# type_id 61 (Ball Touch) outcome==0 from opponent also counts

# Excluded origins (contested duels / shots / dead-ball restarts)
DEFENSIVE_LOSS_TYPE_IDS: frozenset[int] = frozenset({44, 45})
SHOT_TYPE_IDS:           frozenset[int] = frozenset({13, 14, 15, 16})
FOUL_TYPE_ID:            int = 4
CORNER_TYPE_ID:          int = 6
PASS_TYPE_ID:            int = 1

SET_PIECE_ORIGINS: frozenset[str] = frozenset({
    "corner", "free_kick", "throw_in", "goal_kick", "penalty", "gk_hands",
})


# ══════════════════════════════════════════════════════════════════════════════
# COORDINATE HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _x_to_zone_group(x: float) -> str:
    """Classify origin x-coordinate into high / mid / low relative to OWN half."""
    if x <= 16.67:
        return "low"     # deep own third (GK area)
    if x <= 33.33:
        return "mid_low" # own defensive third
    return "mid"         # own midfield (the most common origin zone)


def _y_to_corridor(y: float) -> str:
    if y > LEFT_Y_MIN:
        return "L"
    if y < RIGHT_Y_MAX:
        return "R"
    return "C"


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


# ══════════════════════════════════════════════════════════════════════════════
# DATA LOADER (mirrors defensive_structure.py)
# ══════════════════════════════════════════════════════════════════════════════

def _load_match_events(match_csv: Path) -> pd.DataFrame:
    try:
        df = pd.read_csv(match_csv, low_memory=False)
        rename_map = {
            "type_id":   "type_id",
            "period_id": "period",
            "time_min":  "minute",
            "time_sec":  "second",
        }
        for old, new in rename_map.items():
            if old in df.columns and new not in df.columns:
                df.rename(columns={old: new}, inplace=True)
        return df
    except Exception:
        log.exception("Failed to load match CSV: %s", match_csv)
        return pd.DataFrame()


# ══════════════════════════════════════════════════════════════════════════════
# MAIN COMPUTATION
# ══════════════════════════════════════════════════════════════════════════════

def compute_offensive_transitions(
    team_df: pd.DataFrame,
    opp_df: pd.DataFrame,
    full_df: pd.DataFrame,
    team_lower: str,
) -> dict:
    """
    Detect and analyse offensive transitions for the selected team.

    Logic is the exact inverse of ``compute_defensive_transitions()``:

    Triggers
    --------
    Group A — Team's own events (team just won the ball):
      • type_id=49  Ball Recovery (team gains possession of loose ball)
      • type_id=8   Interception  (team cuts off opponent pass)
      • type_id=7   Tackle, outcome==1 (team won the tackle)

    Group B — Opponent events (opponent just lost the ball):
      • type_id=50  Dispossessed (opponent player tackled by our team)
      • type_id=51  Error
      • type_id=61  Ball Touch, outcome==0

    Origin coordinates
    ------------------
    Group A: use the trigger event's own x, y (team's player position).
    Group B: scan forward to find the team's first play-event and use
             those coordinates.

    Qualification filter
    --------------------
    Only origins with x ≤ OWN_HALF_MAX (50) are included in the
    ``transition_origins`` list (the pitch map).  This keeps the map
    focused on genuine counter-attacks from the defensive/midfield zone.
    All 39 triggers (before dedup) count for ``total_transitions``.

    Outcome scan
    ------------
    Within TRANSITION_WINDOW_SEC after the trigger, scan the TEAM's events:
      P3: team shot / penalty conceded foul in the box
      P2: team won a corner, free kick in attacking third, or cross into box
      P1: team's own x reached ≥ ATT_THIRD_MIN, OR held ball ≥ 15 s
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
            return _empty_offensive_transitions()

        # total_transitions = team's own Ball Recovery count (raw)
        team_ball_recoveries = team_df[
            pd.to_numeric(team_df["type_id"], errors="coerce") == 49
        ]
        total_transitions = len(team_ball_recoveries)

        # Pre-compute lookup columns
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

        # poss_id → poss_origin lookup
        poss_origin_map: dict[int, str] = {}
        if "poss_origin" in full_sorted.columns:
            for pid, origin in (
                full_sorted.dropna(subset=["poss_id"])
                .groupby("poss_id")["poss_origin"]
                .first()
                .items()
            ):
                poss_origin_map[int(pid)] = str(origin or "open_play")

        n_rows = len(full_sorted)
        transitions: list[dict] = []
        last_trigger_sec: float = -9999.0

        NON_PLAY_EVENTS = {"period", "start", "end", "deleted", ""}

        for idx in range(n_rows):
            row     = full_sorted.iloc[idx]
            w_team  = row["_tl"]
            is_team = (w_team == team_lower)
            is_opp  = (not is_team) and (w_team != "")

            if not is_team and not is_opp:
                continue

            tid     = int(row["_tid"])
            out_val = int(row["_out"])

            # ── identify trigger group ─────────────────────────────────────────
            group = ""
            if is_team:
                if tid in BALL_WIN_TEAM_IDS:
                    group = "A"
                elif tid == 7 and out_val == 1:   # Tackle won
                    group = "A"
            elif is_opp:
                if tid in BALL_WIN_OPP_IDS:
                    group = "B"
                elif tid == 61 and out_val == 0:  # Opponent failed ball touch
                    group = "B"

            if not group:
                continue

            trigger_sec = float(row.get("_match_sec", 0) or 0)
            period      = row.get("period")

            # ── set-piece exclusion: check if TEAM's next possession
            # starts from a set piece (meaning the ball win was actually a
            # restart, not an open-play transition) ───────────────────────────
            own_poss_origin = "open_play"
            if group == "A":
                pid_raw = row.get("poss_id")
                try:
                    pid = int(float(pid_raw)) if pd.notna(pid_raw) else None
                except (ValueError, TypeError):
                    pid = None
                if pid is not None:
                    own_poss_origin = poss_origin_map.get(pid, "open_play")
            else:
                # Group B: scan forward for team's next possession
                for fwd in range(idx + 1, min(idx + 50, n_rows)):
                    fwd_row = full_sorted.iloc[fwd]
                    if fwd_row["_tl"] == team_lower:
                        fwd_pid_raw = fwd_row.get("poss_id")
                        try:
                            fwd_pid = int(float(fwd_pid_raw)) if pd.notna(fwd_pid_raw) else None
                        except (ValueError, TypeError):
                            fwd_pid = None
                        if fwd_pid is not None:
                            own_poss_origin = poss_origin_map.get(fwd_pid, "open_play")
                        break

            if own_poss_origin in SET_PIECE_ORIGINS:
                continue

            # ── resolve origin coordinates ─────────────────────────────────────
            # Group A: use trigger event's own x,y (team's player position)
            # Group B: scan forward to first team play event
            if group == "A":
                ox_raw   = row.get("x")
                oy_raw   = row.get("y")
                origin_x = float(ox_raw) if pd.notna(ox_raw) else None
                origin_y = float(oy_raw) if pd.notna(oy_raw) else None
                origin_tid = tid
            else:
                origin_x = origin_y = None
                origin_tid = -1
                for fwd in range(idx + 1, min(idx + 300, n_rows)):
                    fwd_row = full_sorted.iloc[fwd]
                    if fwd_row.get("period") != period:
                        break
                    if fwd_row["_tl"] != team_lower:
                        continue
                    evt_type = str(fwd_row.get("event_type", "")).strip().lower()
                    if evt_type in NON_PLAY_EVENTS or evt_type == "":
                        continue
                    ox_raw   = fwd_row.get("x")
                    oy_raw   = fwd_row.get("y")
                    origin_x = float(ox_raw) if pd.notna(ox_raw) else None
                    origin_y = float(oy_raw) if pd.notna(oy_raw) else None
                    origin_tid = int(fwd_row["_tid"])
                    break

            if origin_x is None:
                continue

            # ── exclude contested duels / shots as origin ──────────────────────
            if origin_tid in DEFENSIVE_LOSS_TYPE_IDS:
                continue
            if origin_tid in SHOT_TYPE_IDS:
                continue

            _oy = float(origin_y or 50.0)
            if not (0.0 <= origin_x <= 100.0 and 0.0 <= _oy <= 100.0):
                continue

            # ── foul guard: team fouled opponent just before trigger ───────────
            foul_guard_mask = (
                (full_sorted["period"] == period)
                & (full_sorted["_match_sec"] >= trigger_sec - FOUL_GUARD_SEC)
                & (full_sorted["_match_sec"] <= trigger_sec + 1.0)
                & (full_sorted["_tl"] == team_lower)
                & (full_sorted["_tid"] == FOUL_TYPE_ID)
            )
            if foul_guard_mask.any():
                continue

            # ── deduplication ─────────────────────────────────────────────────
            if trigger_sec - last_trigger_sec < DEDUP_WINDOW_SEC:
                continue

            last_trigger_sec = trigger_sec
            corridor = _y_to_corridor(_oy)

            # ── scan transition window (TEAM's events forward) ────────────────
            win_mask = (
                (full_sorted["period"] == period)
                & (full_sorted["_match_sec"] >= trigger_sec)
                & (full_sorted["_match_sec"] <= trigger_sec + TRANSITION_WINDOW_SEC)
                & (full_sorted["_tl"] == team_lower)
            )
            window = full_sorted[win_mask]

            p3_shot_flag:    bool = False
            p3_penalty_flag: bool = False
            p2_corner_flag:  bool = False
            p2_foul_flag:    bool = False
            p2_cross_flag:   bool = False
            p1_depth_flag:   bool = False
            p1_time_flag:    bool = False
            reaction_time_raw: float | None = None

            for _, w_row in window.iterrows():
                w_tid = int(w_row["_tid"])
                w_out = int(w_row["_out"])
                w_x_raw = w_row.get("x")
                w_y_raw = w_row.get("y")
                w_x   = float(w_x_raw) if pd.notna(w_x_raw) else None
                w_y   = float(w_y_raw) if pd.notna(w_y_raw) else 50.0
                w_sec = float(w_row.get("_match_sec", trigger_sec))

                if w_x is None:
                    continue

                # P3: team shot
                if w_tid in SHOT_TYPE_IDS:
                    p3_shot_flag = True
                    if reaction_time_raw is None:
                        reaction_time_raw = w_sec - trigger_sec

                # P3: team won a penalty (foul by opponent in box counts via
                # the foul event logged against the opponent — we check team's
                # free-kick won signal via type_id=4 outcome=0 with penalty qual)
                if w_tid == FOUL_TYPE_ID and w_out == 0:
                    if _has_penalty_qualifier(w_row) or (
                        w_x >= BOX_X and OPP_BOX_Y_MIN <= w_y <= OPP_BOX_Y_MAX
                    ):
                        p3_penalty_flag = True
                        if reaction_time_raw is None:
                            reaction_time_raw = w_sec - trigger_sec

                # P2: team won a corner in the attacking third
                if w_tid == CORNER_TYPE_ID and w_x >= ATT_THIRD_MIN:
                    p2_corner_flag = True
                    if reaction_time_raw is None:
                        reaction_time_raw = w_sec - trigger_sec

                # P2: team delivered a cross targeting the box
                if (
                    w_tid == PASS_TYPE_ID
                    and _has_cross_qualifier(w_row)
                    and _pass_end_x(w_row) >= BOX_X
                ):
                    p2_cross_flag = True
                    if reaction_time_raw is None:
                        reaction_time_raw = w_sec - trigger_sec

                # P2: team won a free kick in the attacking third
                # (type_id=4, outcome=0, logged for the OPPONENT — we are
                #  scanning only team events here, so we check via the
                #  free-kick-taken event type_id=62 or type_id=4 on opp side.
                #  Approximate: if x >= ATT_THIRD_MIN and it is a foul-won
                #  signal from the team itself — handled via opp foul below)

                # P1: team reaches opponent's final third
                if w_x >= ATT_THIRD_MIN:
                    p1_depth_flag = True
                    if reaction_time_raw is None:
                        reaction_time_raw = w_sec - trigger_sec

                # P1: team holds ball ≥ 15 s
                if w_sec - trigger_sec >= 15.0:
                    p1_time_flag = True

            # Also scan opponent window for fouls in attacking third
            # (free kick won by team = foul by opponent)
            opp_win_mask = (
                (full_sorted["period"] == period)
                & (full_sorted["_match_sec"] >= trigger_sec)
                & (full_sorted["_match_sec"] <= trigger_sec + TRANSITION_WINDOW_SEC)
                & (full_sorted["_tl"] != team_lower)
                & (full_sorted["_tl"] != "")
            )
            opp_window = full_sorted[opp_win_mask]
            for _, w_row in opp_window.iterrows():
                w_tid = int(w_row["_tid"])
                w_out = int(w_row["_out"])
                w_x_raw = w_row.get("x")
                w_y_raw = w_row.get("y")
                w_x   = float(w_x_raw) if pd.notna(w_x_raw) else None
                w_y   = float(w_y_raw) if pd.notna(w_y_raw) else 50.0
                w_sec = float(w_row.get("_match_sec", trigger_sec))
                if w_x is None:
                    continue
                # Foul committed by opponent: corresponds to team winning a FK
                # Convert opponent x to team attacking frame: 100 - w_x
                team_frame_x = 100.0 - w_x
                if w_tid == FOUL_TYPE_ID and w_out == 0:
                    if _has_penalty_qualifier(w_row) or (
                        team_frame_x >= BOX_X
                        and OPP_BOX_Y_MIN <= w_y <= OPP_BOX_Y_MAX
                    ):
                        p3_penalty_flag = True
                        if reaction_time_raw is None:
                            reaction_time_raw = w_sec - trigger_sec
                    elif team_frame_x >= ATT_THIRD_MIN:
                        p2_foul_flag = True
                        if reaction_time_raw is None:
                            reaction_time_raw = w_sec - trigger_sec

            # Classify outcome
            if p3_shot_flag or p3_penalty_flag:
                outcome: str | None = "P3"
            elif p2_corner_flag or p2_foul_flag or p2_cross_flag:
                outcome = "P2"
            elif p1_depth_flag or p1_time_flag:
                outcome = "P1"
            else:
                outcome = None  # non-qualified

            reaction_time = (
                round(reaction_time_raw, 2)
                if reaction_time_raw is not None
                else TRANSITION_WINDOW_SEC
            )

            transitions.append({
                "x":             origin_x,
                "y":             _oy,
                "zone_group":    _x_to_zone_group(origin_x),
                "corridor":      corridor,
                "outcome":       outcome,
                "reaction_time": reaction_time,
                "match_sec":     trigger_sec,
            })

        # ── Aggregate ──────────────────────────────────────────────────────────
        qualified = [t for t in transitions if t["outcome"] is not None]
        q  = len(qualified)
        p1 = sum(1 for t in qualified if t["outcome"] == "P1")
        p2 = sum(1 for t in qualified if t["outcome"] == "P2")
        p3 = sum(1 for t in qualified if t["outcome"] == "P3")

        transition_rate = round(q / total_transitions * 100, 1) if total_transitions else 0.0

        react_times = [t["reaction_time"] for t in qualified]
        avg_reaction = round(float(np.mean(react_times)), 2) if react_times else 0.0

        avg_react_by_zone: dict[str, float] = {"mid": 0.0, "mid_low": 0.0, "low": 0.0}
        for zg in ("mid", "mid_low", "low"):
            zt = [t["reaction_time"] for t in qualified if t["zone_group"] == zg]
            if zt:
                avg_react_by_zone[zg] = round(float(np.mean(zt)), 2)

        outcomes_by_zone: dict[str, dict[str, int]] = {
            zg: {"P1": 0, "P2": 0, "P3": 0}
            for zg in ("mid", "mid_low", "low")
        }
        for t in qualified:
            outcomes_by_zone[t["zone_group"]][t["outcome"]] += 1

        outcomes_by_corridor: dict[str, dict[str, int]] = {
            c: {"P1": 0, "P2": 0, "P3": 0}
            for c in ("L", "C", "R")
        }
        for t in qualified:
            outcomes_by_corridor[t["corridor"]][t["outcome"]] += 1

        # Origins: only those that started in the team's own half (x <= OWN_HALF_MAX)
        origins = [
            {
                "x":             t["x"],
                "y":             t["y"],
                "zone_group":    t["zone_group"],
                "corridor":      t["corridor"],
                "outcome":       t["outcome"],
                "reaction_time": t["reaction_time"],
            }
            for t in qualified
            if t["x"] <= OWN_HALF_MAX
        ]

        return {
            "total_transitions":         total_transitions,
            "qualified_transitions":     q,
            "transition_rate":           transition_rate,
            "avg_reaction_time_sec":     avg_reaction,
            "avg_reaction_time_by_zone": avg_react_by_zone,
            "outcome_distribution":      {"P1": p1, "P2": p2, "P3": p3},
            "outcomes_by_zone":          outcomes_by_zone,
            "outcomes_by_corridor":      outcomes_by_corridor,
            "transition_origins":        origins,
        }

    except Exception:
        log.exception("compute_offensive_transitions failed")
        return _empty_offensive_transitions()


def _empty_offensive_transitions() -> dict:
    return {
        "total_transitions":         0,
        "qualified_transitions":     0,
        "transition_rate":           0.0,
        "avg_reaction_time_sec":     0.0,
        "avg_reaction_time_by_zone": {"mid": 0.0, "mid_low": 0.0, "low": 0.0},
        "outcome_distribution":      {"P1": 0, "P2": 0, "P3": 0},
        "outcomes_by_zone": {
            "mid":     {"P1": 0, "P2": 0, "P3": 0},
            "mid_low": {"P1": 0, "P2": 0, "P3": 0},
            "low":     {"P1": 0, "P2": 0, "P3": 0},
        },
        "outcomes_by_corridor": {
            "L": {"P1": 0, "P2": 0, "P3": 0},
            "C": {"P1": 0, "P2": 0, "P3": 0},
            "R": {"P1": 0, "P2": 0, "P3": 0},
        },
        "transition_origins": [],
    }


# ══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def analyse_offensive_transitions(match_csv: Path, team: str) -> dict[str, Any]:
    """
    Run the full offensive-transition analysis for *team* in *match_csv*.
    Returns a flat dict consumed by ``offensive_transition_cards.py``.
    """
    try:
        team_lower = canonical_name(str(team)).lower()

        df = _load_match_events(match_csv)
        if df.empty:
            return _empty_offensive_transitions()

        if "type_id" in df.columns:
            df["type_id"] = pd.to_numeric(df["type_id"], errors="coerce")

        if "_match_sec" not in df.columns:
            df["_match_sec"] = (
                df["minute"].fillna(0).astype(float) * 60.0
                + df["second"].fillna(0).astype(float)
            )

        df = build_possessions(df)

        team_mask = df["team_name"].apply(
            lambda t: canonical_name(str(t).strip()).lower() == team_lower
        )
        team_df = df[team_mask].copy()
        opp_df  = df[~team_mask].copy()

        return compute_offensive_transitions(team_df, opp_df, df, team_lower)

    except Exception:
        log.exception("analyse_offensive_transitions failed for team=%s", team)
        return _empty_offensive_transitions()
