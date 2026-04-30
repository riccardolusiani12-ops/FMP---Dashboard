"""
Final Third Entry Analysis
===========================
Analyses how a team progresses the ball into the final third.

Definitions:
- Possession: >= 10 seconds continuous sequence for one team
- Final third: x >= 66.67 (Opta 0-100 scale, 66.67 = 70m on 105m pitch)
- Corridors: Left (y>66.67), Centre (33.33-66.67), Right (y<33.33)
  (Opta y=0 right touchline, y=100 left touchline — high y = Left)

Entry methods (priority order):
1. through_ball      — Through ball qualifier (F3 #4)
2. switch_of_play    — Switch of play qualifier (F3 #196)
3. cross             — Cross qualifier (F3 #2) — ball from wide into box
4. set_piece         — Possession from set-piece + entry within 12s
5. long_ball         — Long ball qualifier (F3 #1) OR Length >= 32
6. transition_recovery — Recovery/interception possession + entry within 8s
7. individual_carry  — Player dribbles/carries across FT line
8. short_pass        — Default (patient build-up, incl. combination play patterns)

Outcome thresholds (binary — no neutral):
- Positive: >=5s retention OR shot attempt OR foul vs team OR corner/throw-in
             for team OR penalty OR goal
- Negative: everything else (uses _who_has_possession_next look-ahead to avoid
             false losses on contested/aerial events)
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import numpy as np

from src.utils.logging import log
from src.team_mapping import canonical_name

from src.analytics.goalkeeper_buildup import (
    xy_to_zone,
    ROW_WIDTH,
    COL_WIDTH,
    NON_PLAY_EVENTS,
    _load_match_events,
    _elapsed_seconds,
    _is_same_team,
    _is_play_event,
    _who_has_possession_next,
)

from src.analytics.general_buildup import (
    build_possessions,
    _is_set_piece,
    _detect_origin,
)


# ═══════════════════════════════════════════════════════════════════════════════
# THRESHOLDS
# ═══════════════════════════════════════════════════════════════════════════════

FT_X_THRESHOLD: float = 100.0 / 6 * 4          # ≈ 66.67  (Final Third)

# Minimum possession duration to count as "qualifying"
MIN_POSS_SEC: float = 10.0

# Long-pass distance threshold (Opta Length units)
LONG_PASS_DISTANCE: float = 32.0

# Set-piece → entry window
SET_PIECE_ENTRY_SEC: float = 12.0

# Transition/recovery → quick entry window
RECOVERY_ENTRY_SEC: float = 8.0

# Post-entry analysis window
POST_FT_WINDOW_SEC: float = 10.0

# Outcome classification thresholds
OUTCOME_POSITIVE_SEC: float = 5.0
OUTCOME_NEGATIVE_SEC: float = 3.0

# Zone constants
# Opta y-axis: y=0 right touchline, y=100 left touchline (broadcast view).
# From the attacking team's perspective: Left = high y, Right = low y.
Z14_ZONES:    frozenset = frozenset({14})
FLANK_ZONES:  frozenset = frozenset({13, 15, 16, 18})   # wide channels in FT
BOX_ZONES:    frozenset = frozenset({17})                 # central penalty area
# Corridor thresholds (Left = y>66.67, Right = y<33.33)
LEFT_Y_MIN:  float = 66.67
RIGHT_Y_MAX: float = 33.33

# Entry method keys (priority order)
METHOD_KEYS = [
    "high_regain",          # special: ball won back already inside the FT
    "transition_recovery",
    "through_ball",
    "switch_of_play",
    "set_piece",
    "long_ball",
    "individual_carry",
    "short_pass",
]

# Event types that qualify as High Regain (mirrors high_regains.py)
# Tackles are included only when outcome == 1 (successful).
HIGH_REGAIN_RECOVERY_TYPES: frozenset = frozenset({
    "ball recovery",
    "interception",
    "tackle",
})

# Shot event types (attacking team) → immediate positive
SHOT_EVENTS: frozenset[str] = frozenset({
    "saved shot", "miss", "post", "goal",
})

# Qualifier column renames applied once at load time.
# Maps original Opta column names → snake_case names used in code.
# Source: F3_opta_qualifier_types (qualifier IDs noted in comments).
_QUALIFIER_RENAMES = {
    # ── Set-piece identifiers ──
    "Corner taken":       "corner_taken",        # F3 #6
    "Free kick taken":    "free_kick_taken",      # F3 #5
    "Throw In":           "throw_in",             # F3 #107
    "Penalty":            "penalty",              # F3 #9
    "Goal Kick":          "goal_kick",            # F3 #124
    # ── GK distribution qualifiers ──
    "Gk kick from hands": "gk_kick_from_hands",   # F3 #199
    "GK hoof":            "gk_hoof",              # F3 #198
    # ── Pass type qualifiers ──
    "Through ball":       "through_ball",          # F3 #4
    "Long ball":          "long_ball",             # F3 #1  — pass over 32 m
    "Switch of play":     "switch_of_play",        # F3 #196 — cross-field > 60 y
    "Cross":              "cross",                 # F3 #2  — ball into the box from wide
    "Chipped":            "chipped",               # F3 #155 — airborne / lofted pass
    "Lay-off":            "lay_off",               # F3 #156 — laid into teammate's run
    "Launch":             "launch",                # F3 #157 — long pass aimed at a zone
    "Flick-on":           "flick_on",              # F3 #168 — headed flick forward
    "Pull Back":          "pull_back",             # F3 #195 — cut-back from by-line
    "Head pass":          "head_pass",             # F3 #3  — pass with the head
    "Attacking Pass":     "attacking_pass",        # F3 #106 — pass in opponent's half
    # ── Pass geometry ──
    "Pass End X":         "pass_end_x",            # F3 #140
    "Pass End Y":         "pass_end_y",            # F3 #141
    "Length":             "length",                # F3 #212 — estimated metres
    "Angle":              "angle",                 # F3 #213 — radians
    # ── Shot-context qualifiers (used in outcome classification) ──
    "Fast break":         "fast_break",            # F3 #23
    "Big Chance":         "big_chance",            # F3 #214
    "Individual Play":    "individual_play",       # F3 #215
    "Assist":             "assist",                # F3 #210
}


# ═══════════════════════════════════════════════════════════════════════════════
# 1. POSSESSION STATISTICS
# ═══════════════════════════════════════════════════════════════════════════════

def build_possession_stats(df: pd.DataFrame, team_lower: str) -> dict:
    """
    Compute possession summary stats for the analysed team.

    Returns dict with:
        possession_pct       — team's share of total match possession time
        total_team_poss      — all possessions belonging to the team
        qualifying_poss      — team possessions lasting >= MIN_POSS_SEC
        qualifying_poss_ids  — set of qualifying possession IDs
        all_team_poss_ids    — set of all team possession IDs
    """
    # Use only play events for duration to avoid non-play events (stoppages,
    # cards, subs) inflating the possession time of the last active possession.
    play_df = df[df["event_type"].str.strip().str.lower().apply(
        lambda e: e not in NON_PLAY_EVENTS and e != ""
    )]

    poss_info = play_df.groupby("poss_id").agg(
        team=("poss_team_name", "first"),
        start_sec=("_match_sec", "min"),
        end_sec=("_match_sec", "max"),
    ).reset_index()
    poss_info["duration"] = (poss_info["end_sec"] - poss_info["start_sec"]).clip(lower=0)

    team_mask = poss_info["team"].apply(
        lambda t: canonical_name(str(t).strip()).lower() == team_lower
    )
    team_poss = poss_info[team_mask]
    all_poss  = poss_info

    total_match_time = all_poss["duration"].sum()
    total_team_time  = team_poss["duration"].sum()

    possession_pct = (
        round(float(total_team_time) / float(total_match_time) * 100, 1)
        if total_match_time > 0 else 0.0
    )

    qualifying = team_poss[team_poss["duration"] >= MIN_POSS_SEC]

    return {
        "possession_pct":      possession_pct,
        "total_team_poss":     int(len(team_poss)),
        "qualifying_poss":     int(len(qualifying)),
        "qualifying_poss_ids": set(qualifying["poss_id"].tolist()),
        "all_team_poss_ids":   set(team_poss["poss_id"].tolist()),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 2. DETECT FINAL-THIRD ENTRIES
# ═══════════════════════════════════════════════════════════════════════════════

def detect_ft_entries(
    open_df: pd.DataFrame,
    full_df: pd.DataFrame,
    team_lower: str,
) -> list[dict]:
    """
    Detect all events where the ball crosses into the Final Third
    (x < FT_X_THRESHOLD → x >= FT_X_THRESHOLD) for qualifying possessions.

    Parameters
    ----------
    open_df   : team's possessions only (already built_possessions, play filtered)
    full_df   : complete match DataFrame (both teams, for outcome lookup)
    team_lower: lower-cased team name fragment

    Returns list of entry dicts.
    """
    entries: list[dict] = []

    for poss_id, grp in open_df.groupby("poss_id"):
        play = grp[grp["event_type"].str.strip().str.lower().apply(
            lambda e: e not in NON_PLAY_EVENTS and e != ""
        )]
        if play.empty:
            continue

        first = play.iloc[0]
        first_x = first.get("x")
        if pd.isna(first_x) or float(first_x) >= FT_X_THRESHOLD:
            continue   # possession already entirely in FT

        poss_start_sec   = float(first.get("_match_sec", 0) or 0)
        poss_origin      = str(grp["poss_origin"].iloc[0])
        poss_origin_evt  = str(first.get("event_type", "")).strip().lower()

        # Pass chain tracking (for method classification)
        passes_before_detail: list[dict] = []
        last_pass_chain_idx: int | None  = None
        prev_x      = float(first_x)
        prev_player = str(first.get("player_name", "")).strip()

        play_rows = list(play.itertuples(index=False))  # fast iteration
        play_idx_list = list(play.index)                # integer positions in full_df

        for seq_idx, row_tuple in enumerate(play_rows):
            # Re-fetch as a proper Series with column access
            row = play.iloc[seq_idx]

            et     = str(row.get("event_type", "")).strip().lower()
            x      = row.get("x")
            y      = row.get("y")
            player = str(row.get("player_name", "")).strip()

            if pd.isna(x):
                continue
            x = float(x)
            y = float(y) if pd.notna(y) else 50.0

            # ── Track pass chains with passer+receiver names ──
            if et in ("pass", "offside pass"):
                # Determine receiver from the NEXT event in the same possession
                receiver_name = "?"
                if seq_idx + 1 < len(play_rows):
                    nxt = play.iloc[seq_idx + 1]
                    nxt_et = str(nxt.get("event_type", "")).strip().lower()
                    if nxt_et not in NON_PLAY_EVENTS and nxt_et != "":
                        receiver_name = str(nxt.get("player_name", "?")).strip()

                passes_before_detail.append({
                    "passer":   player,
                    "receiver": receiver_name,
                    "x":        x,
                    "y":        y,
                    "end_x":    row.get("pass_end_x"),
                    "end_y":    row.get("pass_end_y"),
                    "length":   row.get("length"),
                    "long_ball":      str(row.get("long_ball", "")).strip().lower(),
                    "through_ball":   str(row.get("through_ball", "")).strip().lower(),
                    "switch_of_play": str(row.get("switch_of_play", "")).strip().lower(),
                    "cross":          str(row.get("cross", "")).strip().lower(),
                    "chipped":        str(row.get("chipped", "")).strip().lower(),
                    "launch":         str(row.get("launch", "")).strip().lower(),
                    "lay_off":        str(row.get("lay_off", "")).strip().lower(),
                    "flick_on":       str(row.get("flick_on", "")).strip().lower(),
                    "pull_back":      str(row.get("pull_back", "")).strip().lower(),
                    "head_pass":      str(row.get("head_pass", "")).strip().lower(),
                })
                last_pass_chain_idx = seq_idx

            # ── Detect crossing the FT line via pass endpoint ──
            if et in ("pass", "offside pass", "blocked pass"):
                end_x = row.get("pass_end_x")
                end_y = row.get("pass_end_y")

                # Handle through-ball inference (sometimes missing endpoints)
                has_through = str(row.get("through_ball", "")).strip().lower() in (
                    "si", "yes", "1", "true"
                )

                if pd.notna(end_x) and float(end_x) != 0:
                    end_xf = float(end_x)
                    end_yf = float(end_y) if pd.notna(end_y) else 50.0
                    if x < FT_X_THRESHOLD and end_xf >= FT_X_THRESHOLD:
                        elapsed = (float(row.get("_match_sec", 0) or 0)
                                   - poss_start_sec)
                        # iloc in full_df
                        full_iloc = _find_full_iloc(play_idx_list[seq_idx], full_df)
                        entry = _make_ft_entry(
                            poss_id, "pass", end_xf, end_yf, x, y,
                            player, elapsed, list(passes_before_detail), row,
                            poss_origin, poss_origin_evt, full_iloc,
                            float(first_x),
                        )
                        entries.append(entry)

                elif has_through and x < FT_X_THRESHOLD:
                    # Infer from next event
                    if seq_idx + 1 < len(play_rows):
                        nxt = play.iloc[seq_idx + 1]
                        nx = nxt.get("x")
                        if pd.notna(nx) and float(nx) >= FT_X_THRESHOLD:
                            nxf = float(nx)
                            nyf = float(nxt.get("y", 50)) if pd.notna(nxt.get("y")) else 50.0
                            elapsed = (float(row.get("_match_sec", 0) or 0)
                                       - poss_start_sec)
                            full_iloc = _find_full_iloc(play_idx_list[seq_idx], full_df)
                            entry = _make_ft_entry(
                                poss_id, "pass", nxf, nyf, x, y,
                                player, elapsed, list(passes_before_detail), row,
                                poss_origin, poss_origin_evt, full_iloc,
                                float(first_x),
                            )
                            entries.append(entry)

            # ── Detect crossing via carry (same player, x crosses threshold) ──
            elif et in ("ball touch", "take on"):
                if (prev_x < FT_X_THRESHOLD and x >= FT_X_THRESHOLD
                        and player == prev_player and player != ""):
                    elapsed = (float(row.get("_match_sec", 0) or 0)
                               - poss_start_sec)
                    full_iloc = _find_full_iloc(play_idx_list[seq_idx], full_df)
                    entry = _make_ft_entry(
                        poss_id, "carry", x, y, prev_x, y,
                        player, elapsed, list(passes_before_detail), row,
                        poss_origin, poss_origin_evt, full_iloc,
                        float(first_x),
                    )
                    entries.append(entry)

            prev_x      = x
            prev_player = player

    return entries


def _find_full_iloc(df_index_val: int, full_df: pd.DataFrame) -> int:
    """
    Return the integer iloc position in full_df for a given DataFrame index value.
    Falls back to 0 if not found.
    """
    try:
        return full_df.index.get_loc(df_index_val)
    except KeyError:
        return 0


def _flag(row: pd.Series, col: str) -> bool:
    """Return True when an Opta qualifier column has a truthy 'Si'/'Yes'/'1' value."""
    return str(row.get(col, "")).strip().lower() in ("si", "yes", "1", "true")


def _make_ft_entry(
    poss_id,
    entry_type: str,
    entry_x: float,
    entry_y: float,
    origin_x: float,
    origin_y: float,
    player: str,
    elapsed_sec: float,
    passes_before_detail: list[dict],
    row: pd.Series,
    poss_origin: str,
    poss_origin_evt: str,
    full_iloc: int,
    poss_start_x: float = 50.0,
) -> dict:
    """Build a single FT-entry record."""
    # Corridor at entry point
    # Opta: y=0 right touchline, y=100 left touchline (broadcast view).
    # Left corridor = high y (>66.67); Right corridor = low y (<33.33).
    if entry_y > LEFT_Y_MIN:
        corridor = "L"
    elif entry_y < RIGHT_Y_MAX:
        corridor = "R"
    else:
        corridor = "C"

    return {
        "poss_id":              poss_id,
        "entry_type":           entry_type,
        "entry_x":              entry_x,
        "entry_y":              entry_y,
        "corridor":             corridor,
        "origin_x":             origin_x,
        "origin_y":             origin_y,
        "poss_start_x":         poss_start_x,   # x of the first event in the possession
        "player":               player,
        "elapsed_sec":          elapsed_sec,
        "passes_before_count":  len(passes_before_detail),
        "passes_before_detail": passes_before_detail,
        "poss_origin":          poss_origin,
        "poss_origin_event":    poss_origin_evt,
        # Opta qualifiers on the entry event (see F3 definitions)
        "long_ball_flag":       _flag(row, "long_ball"),
        "through_ball_flag":    _flag(row, "through_ball"),
        "switch_of_play_flag":  _flag(row, "switch_of_play"),
        "cross_flag":           _flag(row, "cross"),          # F3 #2
        "chipped_flag":         _flag(row, "chipped"),         # F3 #155
        "launch_flag":          _flag(row, "launch"),          # F3 #157
        "lay_off_flag":         _flag(row, "lay_off"),         # F3 #156
        "flick_on_flag":        _flag(row, "flick_on"),        # F3 #168
        "pull_back_flag":       _flag(row, "pull_back"),       # F3 #195
        "head_pass_flag":       _flag(row, "head_pass"),       # F3 #3
        "attacking_pass_flag":  _flag(row, "attacking_pass"),  # F3 #106
        "entry_length":         (float(row.get("length")) if pd.notna(row.get("length")) else None),
        # Timing
        "minute":               row.get("minute", 0),
        "second":               row.get("second", 0),
        "period":               row.get("period", 1),
        "match_sec":            float(row.get("_match_sec", 0) or 0),
        # Index in full_df for outcome lookup
        "entry_iloc":           full_iloc,
        # Filled in later
        "method":               "short_pass",
        "outcome":              "negative",
        "z14_touch":            False,
        "wide_play":            False,
        "box_entry":            False,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 2b. DETECT HIGH-REGAIN FT ENTRIES
# ═══════════════════════════════════════════════════════════════════════════════

def detect_high_regain_ft_entries(
    team_df: pd.DataFrame,
    full_df: pd.DataFrame,
) -> list[dict]:
    """
    Detect High Regain entries: ball won back (ball recovery / interception /
    successful tackle) with the event ALREADY inside the Final Third
    (x ≥ FT_X_THRESHOLD ≈ 66.67), during open play.

    These are the 'exception' entry method — the ball is not crossing the FT
    line but is recovered directly within it.  One entry is created per
    qualifying possession whose first play event is such a regain.

    Logic mirrors ``notebooks/01_high_regains.ipynb`` and
    ``src/analytics/high_regains.py``:
    - Event types: ball recovery, interception, tackle (outcome == 1 only)
    - x ≥ 66.67  (attacking third)
    - Open play only (set-piece possession origins excluded)

    Parameters
    ----------
    team_df  : team-only possession DataFrame (already filtered to qualifying
               possessions if caller wants qualifying-only results)
    full_df  : full match DataFrame (both teams, for outcome look-ahead)
    """
    _SET_PIECE_ORIGINS = frozenset({
        "corner", "free_kick", "throw_in", "penalty", "goal_kick", "gk_hands"
    })
    entries: list[dict] = []

    for poss_id, grp in team_df.groupby("poss_id"):
        play = grp[grp["event_type"].str.strip().str.lower().apply(
            lambda e: e not in NON_PLAY_EVENTS and e != ""
        )]
        if play.empty:
            continue

        poss_origin = str(grp["poss_origin"].iloc[0])

        # Skip set-piece-origin possessions (high regain is open play only)
        if poss_origin in _SET_PIECE_ORIGINS:
            continue

        # Only look at the FIRST play event of the possession.
        # If the team's possession starts inside the FT via a regain, that is
        # the high-regain event.  detect_ft_entries() skips these possessions
        # (first_x >= FT_X_THRESHOLD) so there is no double-counting.
        first = play.iloc[0]
        et = str(first.get("event_type", "")).strip().lower()

        if et not in HIGH_REGAIN_RECOVERY_TYPES:
            continue

        # Tackle: only successful (outcome == 1)
        if et == "tackle":
            outcome_val = first.get("outcome")
            if pd.isna(outcome_val):
                continue
            try:
                if int(outcome_val) != 1:
                    continue
            except (ValueError, TypeError):
                continue

        first_x = first.get("x")
        if pd.isna(first_x) or float(first_x) < FT_X_THRESHOLD:
            continue

        x = float(first_x)
        y_raw = first.get("y")
        y = float(y_raw) if pd.notna(y_raw) else 50.0
        player = str(first.get("player_name", "")).strip()
        poss_start_sec = float(first.get("_match_sec", 0) or 0)

        play_idx_list = list(play.index)
        full_iloc = _find_full_iloc(play_idx_list[0], full_df)

        entry = _make_ft_entry(
            poss_id, "high_regain", x, y, x, y,
            player, 0.0, [], first,
            poss_origin, et, full_iloc,
            x,   # poss_start_x == entry x (starts inside FT)
        )
        # Method is fixed — bypass _classify_ft_method entirely
        entry["method"] = "high_regain"
        entries.append(entry)

    return entries


# ═══════════════════════════════════════════════════════════════════════════════
# 3. CLASSIFY ENTRY METHOD
# ═══════════════════════════════════════════════════════════════════════════════

def _classify_ft_method(entry: dict) -> str:
    """
    Classify how the ball entered the Final Third.

    Priority order (first match wins):
    1. transition_recovery — Ball recovered in own 1st third (poss_start_x <= 33.33)
                             AND FT reached within RECOVERY_ENTRY_SEC (8 s).
                             Wins regardless of how the ball was progressed
                             (long ball, short passes, carry, etc.).
    2. through_ball        — F3 #4 Through ball qualifier
    3. switch_of_play      — F3 #196 Switch of play qualifier
    4. set_piece           — Set-piece restart played directly into the FT:
                             passes_before_count == 0 (the restart itself crosses
                             the FT line — no intermediate passes in own half).
    5. long_ball           — F3 #1 Long ball qualifier OR Length >= 32
                             OR F3 #2 cross qualifier (a cross from outside the FT
                             is effectively a long/direct ball into the FT).
    6. individual_carry    — Same player carries/dribbles across FT line
    7. short_pass          — Default (patient build-up, incl. one-two patterns)
    """
    detail = entry["passes_before_detail"]

    # 0. High Regain — ball recovered already inside the FT (set at detection time)
    if entry.get("entry_type") == "high_regain":
        return "high_regain"

    # 1. Transition / recovery — ball won back in OWN 1st third, FT reached fast
    if (entry["poss_origin_event"] in ("ball recovery", "interception", "tackle")
            and entry.get("poss_start_x", 100.0) <= 33.33
            and entry["elapsed_sec"] <= RECOVERY_ENTRY_SEC):
        return "transition_recovery"

    # 2. Through ball qualifier on the entry pass (F3 #4)
    if entry["through_ball_flag"]:
        return "through_ball"
    if detail:
        last_p = detail[-1]
        if last_p.get("through_ball", "") in ("si", "yes", "1", "true"):
            return "through_ball"

    # 3. Switch of play qualifier (F3 #196)
    if entry["switch_of_play_flag"]:
        return "switch_of_play"
    if detail:
        last_p = detail[-1]
        if last_p.get("switch_of_play", "") in ("si", "yes", "1", "true"):
            return "switch_of_play"

    # 4. Set-piece origin — ONLY when played directly into the FT
    #    (passes_before_count == 0: the restart pass itself is the entry).
    if (entry["poss_origin"] in ("corner", "free_kick", "throw_in",
                                  "penalty", "goal_kick", "gk_hands")
            and entry["passes_before_count"] == 0):
        return "set_piece"

    # 5. Long ball qualifier, distance >= LONG_PASS_DISTANCE, OR cross qualifier
    #    A cross from outside the FT is a direct/aerial ball into the FT.
    if entry["long_ball_flag"] or entry.get("cross_flag"):
        return "long_ball"
    if entry["entry_length"] is not None and entry["entry_length"] >= LONG_PASS_DISTANCE:
        return "long_ball"
    if detail:
        last_p = detail[-1]
        if last_p.get("long_ball", "") in ("si", "yes", "1", "true"):
            return "long_ball"
        if last_p.get("cross", "") in ("si", "yes", "1", "true"):
            return "long_ball"
        lp_len = last_p.get("length")
        if lp_len is not None and pd.notna(lp_len) and float(lp_len) >= LONG_PASS_DISTANCE:
            return "long_ball"

    # 6. Individual carry (same player crossed the line)
    if entry["entry_type"] == "carry":
        return "individual_carry"

    # 7. Default — patient build-up (includes combination/one-two patterns)
    return "short_pass"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. CLASSIFY OUTCOME
# ═══════════════════════════════════════════════════════════════════════════════

def _classify_outcome(
    entry_iloc: int,
    team_lower: str,
    df: pd.DataFrame,
    entry_match_sec: float,
    poss_id: int = None,
) -> str:
    """
    Scan forward from entry_iloc in the FULL match df and classify the outcome
    as **'positive' or 'negative' only** (no neutral).

    Mirrors the GK build-up outcome logic for consistency:
      - Positive triggers are checked FIRST (shot, goal, corner, foul by opp,
        penalty, retention >= OUTCOME_POSITIVE_SEC)
      - Opponent events are passed through _who_has_possession_next() so that
        contested / aerial / clearance events do not count as a possession loss
        when the team immediately wins the ball back.
      - No poss_id boundary shortcut — this prevented shot events being seen
        when Opta assigned a new poss_id on the receiving touch.

    Positive:
      - Shot by attacking team (saved shot, miss, post, goal)
      - Corner awarded
      - Foul by defending team
      - Penalty qualifier on a team event
      - Team retains ball >= OUTCOME_POSITIVE_SEC (5 s)

    Negative:
      - Foul committed by attacking team
      - Genuine possession loss (opponent confirmed by look-ahead)
        before OUTCOME_POSITIVE_SEC has elapsed
    """
    ref_row = df.iloc[entry_iloc]
    last_team_elapsed: float = 0.0

    for j in range(entry_iloc + 1, len(df)):
        row = df.iloc[j]

        # Compute elapsed time from the entry event
        ref_ts = ref_row.get("timestamp")
        row_ts = row.get("timestamp")
        if pd.notna(ref_ts) and pd.notna(row_ts):
            elapsed = (row_ts - ref_ts).total_seconds()
        else:
            elapsed = float(row.get("_match_sec", 0) or 0) - entry_match_sec

        # Stop at period boundary to avoid cross-period contamination
        if row.get("period") != ref_row.get("period") and elapsed > 30:
            break

        if not _is_play_event(row):
            continue

        et = str(row.get("event_type", "")).strip().lower()
        is_team = _is_same_team(row, team_lower)

        # ── IMMEDIATE POSITIVE TRIGGERS (checked before any elapsed logic) ──

        # Shot by attacking team → immediate positive
        if is_team and et in SHOT_EVENTS:
            return "positive"

        # Corner awarded → positive
        if et == "corner awarded":
            return "positive"

        # Penalty qualifier
        pen_val = str(row.get("penalty", "")).strip().lower()
        if pen_val in ("si", "yes", "1", "true") and is_team:
            return "positive"

        # Foul event — Opta records each foul as TWO rows (one per team).
        # outcome 0 = committed the foul, 1 = won the foul.
        if et == "foul":
            foul_outcome = row.get("outcome")
            if pd.notna(foul_outcome):
                committed = int(foul_outcome) == 0
                if is_team and committed:
                    return "negative"   # attacking team committed foul
                elif not is_team and committed:
                    return "positive"   # defending team committed foul
            continue  # skip the paired foul row

        # ── TEAM ACTION ──
        if is_team:
            last_team_elapsed = elapsed
            if elapsed >= OUTCOME_POSITIVE_SEC:
                return "positive"

        # ── OPPONENT ACTION — use look-ahead before declaring possession lost ──
        else:
            real_owner = _who_has_possession_next(j, team_lower, df)

            if real_owner == "team":
                # Contested event but team wins the ball back — keep scanning.
                continue

            if real_owner == "set_piece_team":
                # Ball out of play, team gets the restart — keep scanning.
                continue

            # Genuine possession loss
            if last_team_elapsed >= OUTCOME_POSITIVE_SEC:
                return "positive"
            return "negative"

    # End of match data
    if last_team_elapsed >= OUTCOME_POSITIVE_SEC:
        return "positive"
    return "negative"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. POST-FT ZONE ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════════

def analyse_post_ft_zones(entries: list[dict], df: pd.DataFrame) -> list[dict]:
    """
    For each entry, scan the next POST_FT_WINDOW_SEC of the same possession
    to detect:
      - z14_touch : ball touched Z14 (central danger zone)
      - wide_play : ball used flank (y < 33.33 or y > 66.67) in FT
      - box_entry : ball entered penalty area (Z16-Z18)
    """
    for entry in entries:
        sec_start = entry["match_sec"]
        sec_end   = sec_start + POST_FT_WINDOW_SEC
        pid       = entry["poss_id"]

        window = df[
            (df["_match_sec"] >= sec_start)
            & (df["_match_sec"] <= sec_end)
            & (df["poss_id"] == pid)
        ]

        z14  = False
        wide = False
        box  = False

        for _, row in window.iterrows():
            for xk, yk in (("x", "y"), ("pass_end_x", "pass_end_y")):
                xv = row.get(xk)
                yv = row.get(yk)
                if pd.notna(xv) and pd.notna(yv):
                    xf = float(xv)
                    yf = float(yv)
                    # Only count positions inside the FT
                    if xf >= FT_X_THRESHOLD:
                        zone = xy_to_zone(xf, yf)
                        if zone in Z14_ZONES:
                            z14 = True
                        if zone in BOX_ZONES:
                            box = True
                        # Wide = outside centre corridor (y < 33.33 or y > 66.67)
                        if yf < RIGHT_Y_MAX or yf > LEFT_Y_MIN:
                            wide = True

        entry["z14_touch"] = z14
        entry["wide_play"] = wide
        entry["box_entry"] = box

    return entries


# ═══════════════════════════════════════════════════════════════════════════════
# 5b. OPPOSITION BOX TOUCHES
# ═══════════════════════════════════════════════════════════════════════════════

# Opposition box x-threshold: last sixth of pitch (x >= 83.33)
_OPP_BOX_X: float = 100.0 / 6 * 5  # ≈ 83.33

# Event types explicitly excluded from box-touch count.
# Duels (ground/aerial) and fouls are NOT considered a "touch in the box".
_BOX_TOUCH_EXCLUDED: frozenset = frozenset({
    "aerial",
    "tackle",
    "foul",
    "card",
    "offside provoked",
    "shield ball opp",
    # Ball-position / referee markers — not player touches
    "out",
    "corner awarded",
    "offside",
    # Administrative / non-play
    "deleted event", "team setp up", "start", "end",
    "player off", "player on", "resume", "unknown",
    "start delay", "end delay", "formation change",
    "collection end", "early end",
    "injury time announcement",
    "contentious referee decision",
})


def count_box_touches(team_df: pd.DataFrame, team_lower: str = "") -> int:
    """
    Count touches in the opposition penalty area (x >= 83.33, 21 <= y <= 79)
    by the analysed team only.

    Included: passes received, dribbles, carries, ball touches, shots,
              take-ons, clearances, interceptions, goal-kicks received.
    Excluded: duels (aerial/ground), tackles, fouls, cards, and all
              non-play events.

    Each individual action is counted separately even if part of the
    same uninterrupted attack.

    Parameters
    ----------
    team_df    : pd.DataFrame — already filtered to the team's POSSESSION windows
                 (poss_team_name == team), but may still contain opponent rows
                 within those windows.
    team_lower : str — lower-cased canonical team name; used to restrict counting
                 to rows belonging to the team itself (not opponent events that
                 fall inside the team's possession windows).

    Returns
    -------
    int  Total qualifying touches inside the opposition box.
    """
    if team_df.empty:
        return 0

    # ── Filter to the team's own rows ──────────────────────────────────────────
    # poss_team_name marks possession ownership but during those possessions
    # opponent events (clearances, tackles, etc.) also carry the same poss tag.
    # We must restrict to rows where team_name == team to avoid double-counting.
    if team_lower:
        own_mask = team_df["team_name"].apply(
            lambda t: canonical_name(str(t).strip()).lower() == team_lower
        )
        df_own = team_df[own_mask]
    else:
        df_own = team_df

    if df_own.empty:
        return 0

    et = df_own["event_type"].astype(str).str.strip().str.lower()
    touch_mask = (~et.isin(_BOX_TOUCH_EXCLUDED)) & (et != "")
    x_mask = df_own["x"].ge(_OPP_BOX_X)
    y_mask = df_own["y"].between(21, 79)

    return int((touch_mask & x_mask & y_mask).sum())


# ═══════════════════════════════════════════════════════════════════════════════
# 6. AGGREGATE METRICS
# ═══════════════════════════════════════════════════════════════════════════════

def compute_ft_metrics(entries: list[dict], poss_stats: dict, box_touches: int = 0, all_ft_entries: int = 0) -> dict:
    """
    Aggregate all per-entry data into a flat metrics dictionary.
    """
    qualifying_ids  = poss_stats["qualifying_poss_ids"]
    qualifying_poss = poss_stats["qualifying_poss"]

    # Only count entries from qualifying possessions
    qual_entries = [e for e in entries if e["poss_id"] in qualifying_ids]
    n = len(qual_entries)
    safe_n = n or 1

    # Unique possessions with at least one FT entry
    poss_with_entry = len({e["poss_id"] for e in qual_entries})

    ft_entry_pct = round(poss_with_entry / qualifying_poss * 100, 1) if qualifying_poss else 0.0

    # ── Corridors ──
    corridor_counts = {"L": 0, "C": 0, "R": 0}
    for e in qual_entries:
        corridor_counts[e["corridor"]] += 1
    corridor_pcts = {
        k: round(v / safe_n * 100, 1) for k, v in corridor_counts.items()
    }

    # ── Methods ──
    method_counts: dict[str, int] = {k: 0 for k in METHOD_KEYS}
    for e in qual_entries:
        method_counts[e["method"]] = method_counts.get(e["method"], 0) + 1
    method_pcts = {
        k: round(v / safe_n * 100, 1) for k, v in method_counts.items()
    }

    # ── Post-entry zone reach (by entry zone, matching heatmap) ──
    z14_count  = 0
    wide_count = 0
    box_count  = 0
    for e in qual_entries:
        ex = e.get("entry_x")
        ey = e.get("entry_y", 50)
        if ex is None:
            continue
        entry_zone = xy_to_zone(float(ex), float(ey))
        if entry_zone in Z14_ZONES:
            z14_count += 1
        if entry_zone in FLANK_ZONES:
            wide_count += 1
        if entry_zone in BOX_ZONES:
            box_count += 1
    zone_reach = {
        "z14":    {"count": z14_count,  "pct": round(z14_count  / safe_n * 100, 1)},
        "flanks": {"count": wide_count, "pct": round(wide_count / safe_n * 100, 1)},
        "box":    {"count": box_count,  "pct": round(box_count  / safe_n * 100, 1)},
    }

    # ── Outcomes ──
    outcome_counts: dict[str, int] = {"positive": 0, "negative": 0}
    for e in qual_entries:
        oc = e.get("outcome", "negative")
        outcome_counts[oc] = outcome_counts.get(oc, 0) + 1
    outcomes = {
        k: {"count": v, "pct": round(v / safe_n * 100, 1)}
        for k, v in outcome_counts.items()
    }

    # ── Outcome by corridor ──
    outcome_by_corridor: dict[str, dict] = {
        c: {"positive": 0, "negative": 0} for c in ("L", "C", "R")
    }
    for e in qual_entries:
        c  = e["corridor"]
        oc = e.get("outcome", "negative")
        outcome_by_corridor[c][oc] += 1

    # ── Outcome by method ──
    outcome_by_method: dict[str, dict] = {
        k: {"positive": 0, "negative": 0} for k in METHOD_KEYS
    }
    for e in qual_entries:
        m  = e["method"]
        oc = e.get("outcome", "negative")
        outcome_by_method[m][oc] += 1

    # ── Build-up tempo metrics ──
    avg_passes  = round(float(np.mean([e["passes_before_count"] for e in qual_entries])), 1) if qual_entries else 0.0
    avg_seconds = round(float(np.mean([e["elapsed_sec"] for e in qual_entries])), 1) if qual_entries else 0.0

    return {
        "possession_pct":          poss_stats["possession_pct"],
        "total_team_poss":         poss_stats["total_team_poss"],
        "qualifying_poss":         qualifying_poss,
        "possessions_with_ft_entry": poss_with_entry,
        "all_ft_entries":          all_ft_entries,
        "total_ft_entries":        n,
        "ft_entry_pct":            ft_entry_pct,
        "corridor_counts":         corridor_counts,
        "corridor_pcts":           corridor_pcts,
        "method_counts":           method_counts,
        "method_pcts":             method_pcts,
        "zone_reach":              zone_reach,
        "outcomes":                outcomes,
        "outcome_by_corridor":     outcome_by_corridor,
        "outcome_by_method":       outcome_by_method,
        "avg_passes_before_entry": avg_passes,
        "avg_seconds_to_entry":    avg_seconds,
        "box_touches":             box_touches,
    }


def _empty_metrics() -> dict:
    return {
        "possession_pct":            0.0,
        "total_team_poss":           0,
        "qualifying_poss":           0,
        "possessions_with_ft_entry": 0,
        "all_ft_entries":            0,
        "total_ft_entries":          0,
        "ft_entry_pct":              0.0,
        "corridor_counts":           {"L": 0, "C": 0, "R": 0},
        "corridor_pcts":             {"L": 0.0, "C": 0.0, "R": 0.0},
        "method_counts":             {k: 0 for k in METHOD_KEYS},
        "method_pcts":               {k: 0.0 for k in METHOD_KEYS},
        "zone_reach": {
            "z14":    {"count": 0, "pct": 0.0},
            "flanks": {"count": 0, "pct": 0.0},
            "box":    {"count": 0, "pct": 0.0},
        },
        "outcomes": {
            "positive": {"count": 0, "pct": 0.0},
            "negative": {"count": 0, "pct": 0.0},
        },
        "outcome_by_corridor": {
            "L": {"positive": 0, "negative": 0},
            "C": {"positive": 0, "negative": 0},
            "R": {"positive": 0, "negative": 0},
        },
        "outcome_by_method": {
            k: {"positive": 0, "negative": 0} for k in METHOD_KEYS
        },
        "avg_passes_before_entry": 0.0,
        "avg_seconds_to_entry":    0.0,
        "box_touches":             0,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def analyse_final_third(
    match_csv: Path,
    team_name: str,
) -> dict:
    """
    Run the full Final Third Entry analysis for one team in one match.

    Returns
    -------
    dict with keys:
        metrics      — flat dict of aggregated metrics
        entries      — list of per-entry dicts
        debug_events — list of lightweight debug records
    """
    df = _load_match_events(match_csv)
    if df.empty:
        log.warning("Empty match data for %s", match_csv)
        return {"metrics": _empty_metrics(), "entries": [], "debug_events": []}

    # ── Apply qualifier renames (only if not already renamed) ──
    for orig, new in _QUALIFIER_RENAMES.items():
        if orig in df.columns and new not in df.columns:
            df[new] = df[orig]

    team_lower = team_name.strip().lower()

    # 1. Build possession chains (adds poss_id, poss_origin, _match_sec, etc.)
    df = build_possessions(df)

    # 2. Filter to this team's possessions (all origins — we filter by method later)
    team_mask = df["poss_team_name"].apply(
        lambda t: canonical_name(str(t).strip()).lower() == team_lower
    )
    team_df = df[team_mask].copy()

    # 3. Possession statistics
    poss_stats = build_possession_stats(df, team_lower)

    # 4a. Detect FT entries from ALL team possessions (total count)
    all_entries = detect_ft_entries(team_df, df, team_lower)
    all_entries += detect_high_regain_ft_entries(team_df, df)
    all_ft_entries_count = len(all_entries)

    # 4b. Detect FT entries from qualifying possessions only
    qual_ids = poss_stats["qualifying_poss_ids"]
    qual_team_df = team_df[team_df["poss_id"].isin(qual_ids)].copy()

    entries = detect_ft_entries(qual_team_df, df, team_lower)
    entries += detect_high_regain_ft_entries(qual_team_df, df)

    # 5. Classify entry method (high_regain entries already pre-classified)
    for entry in entries:
        if entry.get("method") != "high_regain":
            entry["method"] = _classify_ft_method(entry)

    # 6. Classify outcome (uses full df for look-ahead)
    for entry in entries:
        entry["outcome"] = _classify_outcome(
            entry["entry_iloc"], team_lower, df, entry["match_sec"], entry.get("poss_id")
        )

    # 7. Post-FT zone analysis (uses full df for window)
    entries = analyse_post_ft_zones(entries, df)

    # 7b. Count all touches in the opposition box
    bt = count_box_touches(team_df, team_lower)

    # 8. Aggregate metrics
    metrics = compute_ft_metrics(entries, poss_stats, box_touches=bt,
                                 all_ft_entries=all_ft_entries_count)

    # 9. Debug trace
    debug: list[dict] = []
    for e in entries:
        debug.append({
            "min":     f"{int(e.get('minute', 0))}:{int(e.get('second', 0)):02d}",
            "period":  e.get("period"),
            "player":  e.get("player"),
            "method":  e.get("method"),
            "entry":   e.get("entry_type"),
            "corridor": e.get("corridor"),
            "entry_xy": f"({e.get('entry_x', 0):.1f},{e.get('entry_y', 0):.1f})",
            "elapsed": f"{e.get('elapsed_sec', 0):.0f}s",
            "passes":  e.get("passes_before_count"),
            "outcome": e.get("outcome"),
            "z14":     e.get("z14_touch"),
            "wide":    e.get("wide_play"),
            "box":     e.get("box_entry"),
        })

    return {
        "metrics":      metrics,
        "entries":      entries,
        "debug_events": debug,
    }
