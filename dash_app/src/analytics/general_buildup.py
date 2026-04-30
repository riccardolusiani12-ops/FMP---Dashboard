"""
General Build-up Analysis  (Open Play Only)  — v2
===================================================
How does a team progress the ball from deep into the Final Third during
open play?

Design principles:
  • Simple & measurable — every metric maps to a clear on-pitch event
  • 5 progression categories derived from Opta qualifiers
  • 3 clean post-Z3 metrics (Z14 control, wide play, box entries)
  • 2 extra metrics (avg passes before entry, avg seconds to reach FT)

This is the SECOND of three offensive phases:
  1. Build-up from GK  (goalkeeper_buildup.py)
  2. General Build-up   (THIS MODULE)
  3. Chance Creation    (future)

Uses the same 18-zone pitch model as the GK build-up analysis.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import numpy as np

from src.utils.logging import log
from src.team_mapping import canonical_name

# Re-use the 18-zone grid helpers from GK build-up
from src.analytics.goalkeeper_buildup import (
    xy_to_zone,
    ROW_WIDTH,
    COL_WIDTH,
    NON_PLAY_EVENTS,
    _load_match_events,
    _elapsed_seconds,
    _is_same_team,
    _is_play_event,
)

# ═══════════════════════════════════════════════════════════════════════════════
# THRESHOLDS
# ═══════════════════════════════════════════════════════════════════════════════

Z3_X_THRESHOLD: float = 100.0 / 6 * 4        # ≈ 66.67  (Final Third)

# Short-passing sequence: min passes before Z3 entry
SHORT_PASS_MIN: int = 5

# Long pass distance (Opta Length units ≈ metres on 100×100 grid)
LONG_PASS_DISTANCE: float = 30.0

# Recovery → quick progression window (seconds)
RECOVERY_QUICK_SEC: float = 8.0

# Post-Z3 analysis window (seconds)
POST_Z3_WINDOW_SEC: float = 10.0

# Zone definitions
Z14_ZONES: frozenset = frozenset({14})                  # central danger zone
BOX_ZONES: frozenset = frozenset({16, 17, 18})          # penalty-area row
LEFT_Y_MAX:  float = 33.33
RIGHT_Y_MIN: float = 66.67

# Set-piece detection columns (both renamed and original names)
SET_PIECE_COLS = (
    "corner_taken", "Corner taken",
    "free_kick_taken", "Free kick taken",
    "throw_in", "Throw In",
    "penalty", "Penalty",
    "goal_kick", "Goal Kick",
    "gk_kick_from_hands", "Gk kick from hands",
)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. BUILD POSSESSION CHAINS
# ═══════════════════════════════════════════════════════════════════════════════

def build_possessions(df: pd.DataFrame) -> pd.DataFrame:
    """
    Assign a ``poss_id`` to every row.

    A new possession starts when:
      – team changes
      – period changes
      – a goal is scored
      – a set-piece restart occurs
    """
    n = len(df)
    poss_ids    = np.zeros(n, dtype=np.int64)
    poss_teams  = [""] * n
    poss_names  = [""] * n
    poss_origin = [""] * n

    cur_poss   = 0
    cur_team   = None
    cur_period = None

    for i in range(n):
        row = df.iloc[i]
        et    = str(row.get("event_type", "")).strip().lower()
        tid   = str(row.get("team_id", "")).strip()
        per   = row.get("period")
        tname = str(row.get("team_name", "")).strip()

        # Non-play events inherit previous possession
        if et in NON_PLAY_EVENTS or et == "":
            poss_ids[i]    = cur_poss
            poss_teams[i]  = cur_team or ""
            poss_names[i]  = poss_names[i - 1] if i > 0 else ""
            poss_origin[i] = poss_origin[i - 1] if i > 0 else ""
            continue

        new_poss = False

        if per != cur_period and cur_period is not None:
            new_poss = True
        elif tid != cur_team and cur_team is not None and tid != "":
            new_poss = True
        elif et == "goal":
            poss_ids[i]    = cur_poss
            poss_teams[i]  = tid
            poss_names[i]  = tname
            poss_origin[i] = poss_origin[i - 1] if i > 0 else "open_play"
            cur_team   = None
            cur_period = per
            continue

        if _is_set_piece(row):
            new_poss = True

        if new_poss or cur_poss == 0:
            cur_poss   += 1
            cur_team   = tid
            cur_period = per
        elif tid != "" and tid != cur_team:
            cur_poss   += 1
            cur_team   = tid
            cur_period = per

        poss_ids[i]    = cur_poss
        poss_teams[i]  = cur_team or ""
        poss_names[i]  = tname
        poss_origin[i] = _detect_origin(row)

    df = df.copy()
    df["poss_id"]        = poss_ids
    df["poss_team_id"]   = poss_teams
    df["poss_team_name"] = poss_names

    origin_s = pd.Series(poss_origin, index=df.index)
    first_origins = (
        df.assign(_origin=origin_s)
        .groupby("poss_id")["_origin"]
        .first()
    )
    df["poss_origin"] = df["poss_id"].map(first_origins).fillna("open_play")

    df["_match_sec"]     = df["minute"].fillna(0) * 60 + df["second"].fillna(0)
    df["poss_start_sec"] = df.groupby("poss_id")["_match_sec"].transform("first")

    return df


def _is_set_piece(row: pd.Series) -> bool:
    """Check if event is a set-piece restart via qualifier columns."""
    for col in SET_PIECE_COLS:
        val = str(row.get(col, "")).strip().lower()
        if val in ("si", "yes", "1", "true"):
            return True
    return False


def _detect_origin(row: pd.Series) -> str:
    """Determine possession origin from the first event."""
    for cols, label in (
        (("corner_taken", "Corner taken"), "corner"),
        (("free_kick_taken", "Free kick taken"), "free_kick"),
        (("throw_in", "Throw In"), "throw_in"),
        (("penalty", "Penalty"), "penalty"),
        (("goal_kick", "Goal Kick"), "goal_kick"),
        (("gk_kick_from_hands", "Gk kick from hands"), "gk_hands"),
    ):
        for col in cols:
            val = str(row.get(col, "")).strip().lower()
            if val in ("si", "yes", "1", "true"):
                return label
    return "open_play"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. FILTER OPEN-PLAY POSSESSIONS
# ═══════════════════════════════════════════════════════════════════════════════

def filter_open_play(df: pd.DataFrame, team_lower: str) -> pd.DataFrame:
    """Keep only open-play possessions belonging to *team_lower*.

    Uses canonical-name resolution so that e.g. 'milan' matches only
    'AC Milan' and not 'FC Internazionale Milano'.
    """
    team_mask   = df["poss_team_name"].apply(
        lambda t: canonical_name(str(t).strip()).lower() == team_lower
    )
    origin_mask = df["poss_origin"] == "open_play"
    return df[team_mask & origin_mask].copy()


# ═══════════════════════════════════════════════════════════════════════════════
# 3. DETECT FINAL-THIRD ENTRIES
# ═══════════════════════════════════════════════════════════════════════════════

def detect_entries(df: pd.DataFrame) -> list[dict]:
    """
    Detect when the ball crosses into the Final Third (x >= Z3_X_THRESHOLD).

    Only considers possessions whose FIRST event starts *outside* the FT.
    Tracks per-entry:
      • passes_before  (list of pass dicts for classification)
      • first_event_type (event_type of the very first action in the poss.)
      • entry_row details (player, coords, timing, Opta qualifiers)
    """
    entries: list[dict] = []

    for poss_id, grp in df.groupby("poss_id"):
        play = grp[grp["event_type"].str.strip().str.lower().apply(
            lambda e: e not in NON_PLAY_EVENTS and e != ""
        )]
        if play.empty:
            continue

        first = play.iloc[0]
        first_x = first.get("x")
        if pd.isna(first_x) or float(first_x) >= Z3_X_THRESHOLD:
            continue  # possession already in FT

        poss_start_sec  = first.get("_match_sec", 0) or 0
        first_event_type = str(first.get("event_type", "")).strip().lower()

        passes: list[dict] = []
        prev_x      = float(first_x)
        prev_player = str(first.get("player_name", "")).strip()

        for idx in range(len(play)):
            row = play.iloc[idx]
            et     = str(row.get("event_type", "")).strip().lower()
            x      = row.get("x")
            y      = row.get("y")
            player = str(row.get("player_name", "")).strip()

            if pd.isna(x):
                continue
            x = float(x)
            y = float(y) if pd.notna(y) else 50.0

            # Track passes for classification
            if et == "pass":
                passes.append({
                    "x": x, "y": y,
                    "end_x": row.get("pass_end_x"),
                    "end_y": row.get("pass_end_y"),
                    "length": row.get("length"),
                    "long_ball": str(row.get("long_ball", "")).strip().lower(),
                    "through_ball": str(row.get("through_ball", "")).strip().lower(),
                    "outcome": row.get("outcome"),
                })

            # ── Entry via pass ──
            if et in ("pass", "offside pass", "blocked pass"):
                end_x = row.get("pass_end_x")
                has_through = str(row.get("through_ball", "")).strip().lower() in (
                    "si", "yes", "1", "true"
                )
                if pd.notna(end_x) and float(end_x) != 0:
                    end_x = float(end_x)
                    end_y = (float(row.get("pass_end_y", 50))
                             if pd.notna(row.get("pass_end_y")) else 50.0)
                    if x < Z3_X_THRESHOLD and end_x >= Z3_X_THRESHOLD:
                        elapsed = (row.get("_match_sec", 0) or 0) - poss_start_sec
                        entries.append(_make_entry(
                            poss_id, "pass", end_x, end_y, x, y,
                            player, elapsed, list(passes), row,
                            first_event_type,
                        ))
                # Through balls often lack end coordinates in Opta —
                # infer FT entry from the NEXT event's position
                elif has_through and x < Z3_X_THRESHOLD:
                    if idx + 1 < len(play):
                        nxt = play.iloc[idx + 1]
                        nx = nxt.get("x")
                        if pd.notna(nx) and float(nx) >= Z3_X_THRESHOLD:
                            nx = float(nx)
                            ny = float(nxt.get("y", 50)) if pd.notna(nxt.get("y")) else 50.0
                            elapsed = (row.get("_match_sec", 0) or 0) - poss_start_sec
                            entries.append(_make_entry(
                                poss_id, "pass", nx, ny, x, y,
                                player, elapsed, list(passes), row,
                                first_event_type,
                            ))

            # ── Entry via carry ──
            elif et in ("ball touch", "take on", "ball recovery",
                        "dispossessed", "clearance"):
                if (prev_x < Z3_X_THRESHOLD and x >= Z3_X_THRESHOLD
                        and player == prev_player and player != ""):
                    elapsed = (row.get("_match_sec", 0) or 0) - poss_start_sec
                    entries.append(_make_entry(
                        poss_id, "carry", x, y, prev_x, y,
                        player, elapsed, list(passes), row,
                        first_event_type,
                    ))

            prev_x      = x
            prev_player = player

    return entries


def _make_entry(
    poss_id, entry_type, entry_x, entry_y, origin_x, origin_y,
    player, elapsed_sec, passes_before, row, first_event_type,
) -> dict:
    """Build one entry record."""
    long_flag = str(row.get("long_ball", "")).strip().lower() in (
        "si", "yes", "1", "true"
    )
    through_flag = str(row.get("through_ball", "")).strip().lower() in (
        "si", "yes", "1", "true"
    )
    entry_len = row.get("length")
    entry_len = float(entry_len) if pd.notna(entry_len) else None

    return {
        "poss_id":              poss_id,
        "entry_type":           entry_type,       # "pass" or "carry"
        "entry_x":              entry_x,
        "entry_y":              entry_y,
        "origin_x":             origin_x,
        "origin_y":             origin_y,
        "origin_zone":          xy_to_zone(origin_x, origin_y),
        "entry_zone":           xy_to_zone(entry_x, entry_y),
        "player":               player,
        "elapsed_sec":          elapsed_sec,
        "passes_before_count":  len(passes_before),
        "passes_before":        passes_before,
        "first_event_type":     first_event_type,
        # Opta qualifiers on the entry event
        "long_ball_flag":       long_flag,
        "through_ball_flag":    through_flag,
        "entry_length":         entry_len,
        # Timing
        "minute":               row.get("minute", 0),
        "second":               row.get("second", 0),
        "period":               row.get("period", 1),
        "match_sec":            row.get("_match_sec", 0),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 4. CLASSIFY PROGRESSION TYPE
# ═══════════════════════════════════════════════════════════════════════════════
#
# Exactly 5 categories, checked in priority order:
#
#   1. Through Ball         – the entry pass has the Opta "Through ball" flag
#   2. Long Ball / Direct   – entry pass has "Long ball" flag OR Length >= 30
#   3. Recovery + Quick     – possession starts from ball recovery / interception
#                             / tackle AND Z3 reached within RECOVERY_QUICK_SEC
#   4. Individual Carry     – the entry itself is a carry (same player)
#   5. Short Passing        – >= SHORT_PASS_MIN passes before Z3 entry
#
#   If none match -> "other"
# ═══════════════════════════════════════════════════════════════════════════════

PROG_KEYS = [
    "through_ball",
    "long_ball",
    "recovery_fast",
    "individual_carry",
    "short_passing",
    "other",
]


def classify_entries(entries: list[dict]) -> list[dict]:
    """Tag each entry with ``progression_type``."""
    for e in entries:
        e["progression_type"] = _classify_one(e)
    return entries


def _classify_one(e: dict) -> str:
    # 1. Through Ball
    if e["through_ball_flag"]:
        return "through_ball"
    # Also check last pass in the chain
    if e["passes_before"]:
        last_p = e["passes_before"][-1]
        if last_p.get("through_ball") in ("si", "yes", "1", "true"):
            return "through_ball"

    # 2. Long Ball / Direct Play
    if e["long_ball_flag"]:
        return "long_ball"
    if e["entry_length"] is not None and e["entry_length"] >= LONG_PASS_DISTANCE:
        return "long_ball"
    if e["passes_before"]:
        last_p = e["passes_before"][-1]
        if last_p.get("long_ball") in ("si", "yes", "1", "true"):
            return "long_ball"
        lp_len = last_p.get("length")
        if lp_len is not None and pd.notna(lp_len) and float(lp_len) >= LONG_PASS_DISTANCE:
            return "long_ball"

    # 3. Recovery + Quick Progression
    if (e["first_event_type"] in ("ball recovery", "interception", "tackle")
            and e["elapsed_sec"] <= RECOVERY_QUICK_SEC):
        return "recovery_fast"

    # 4. Individual Carry
    if e["entry_type"] == "carry":
        return "individual_carry"

    # 5. Short Passing Sequence
    if e["passes_before_count"] >= SHORT_PASS_MIN:
        return "short_passing"

    return "other"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. POST-Z3 ANALYSIS  (What happens after reaching the Final Third)
# ═══════════════════════════════════════════════════════════════════════════════
#
# For each entry we check the next POST_Z3_WINDOW_SEC seconds:
#   • z14_touch    – did the ball touch Z14?
#   • wide_play    – did the ball go wide (y < 33.33 or y > 66.67)?
#   • box_entry    – did the ball enter the penalty area (Z16/17/18)?
# ═══════════════════════════════════════════════════════════════════════════════

def analyse_post_z3(entries: list[dict], df: pd.DataFrame) -> list[dict]:
    """Enrich each entry with post-Z3 booleans."""
    for e in entries:
        sec_start = e["match_sec"]
        sec_end   = sec_start + POST_Z3_WINDOW_SEC
        pid       = e["poss_id"]

        window = df[
            (df["_match_sec"] >= sec_start)
            & (df["_match_sec"] <= sec_end)
            & (df["poss_id"] == pid)
        ]

        z14  = False
        wide = False
        box  = False

        for _, row in window.iterrows():
            x, y = row.get("x"), row.get("y")
            if pd.notna(x) and pd.notna(y):
                zone = xy_to_zone(float(x), float(y))
                if zone in Z14_ZONES:
                    z14 = True
                if zone in BOX_ZONES:
                    box = True
                yf = float(y)
                if yf < LEFT_Y_MAX or yf > RIGHT_Y_MIN:
                    wide = True

            # Also check pass endpoints
            ex, ey = row.get("pass_end_x"), row.get("pass_end_y")
            if pd.notna(ex) and pd.notna(ey):
                zone = xy_to_zone(float(ex), float(ey))
                if zone in Z14_ZONES:
                    z14 = True
                if zone in BOX_ZONES:
                    box = True
                eyf = float(ey)
                if eyf < LEFT_Y_MAX or eyf > RIGHT_Y_MIN:
                    wide = True

        e["z14_touch"] = z14
        e["wide_play"] = wide
        e["box_entry"] = box

    return entries


# ═══════════════════════════════════════════════════════════════════════════════
# 6. AGGREGATE METRICS
# ═══════════════════════════════════════════════════════════════════════════════

def compute_metrics(
    entries: list[dict],
    total_open_poss: int,
    total_outside_z3: int,
) -> dict:
    """Build a flat metrics dictionary consumed by the UI layer."""
    n = len(entries)
    if n == 0:
        return _empty_metrics(total_open_poss)

    safe_n       = n or 1
    safe_outside = total_outside_z3 or 1

    # ── Section A: Frequency ──
    z3_pct = round(n / safe_outside * 100, 1)

    # ── Section B: Origin (L / C / R) ──
    origin_left   = sum(1 for e in entries if e["origin_y"] < LEFT_Y_MAX)
    origin_right  = sum(1 for e in entries if e["origin_y"] > RIGHT_Y_MIN)
    origin_centre = n - origin_left - origin_right

    # ── Section C: Progression types ──
    prog: dict[str, int] = {k: 0 for k in PROG_KEYS}
    for e in entries:
        pt = e.get("progression_type", "other")
        prog[pt] = prog.get(pt, 0) + 1

    # ── Section D: Post-Z3 ──
    z14_count  = sum(1 for e in entries if e.get("z14_touch"))
    wide_count = sum(1 for e in entries if e.get("wide_play"))
    box_count  = sum(1 for e in entries if e.get("box_entry"))

    # ── Extra metrics ──
    avg_passes  = round(np.mean([e["passes_before_count"] for e in entries]), 1)
    avg_seconds = round(np.mean([e["elapsed_sec"] for e in entries]), 1)

    return {
        # A — frequency
        "total_z3_entries":            n,
        "total_open_possessions":      total_open_poss,
        "total_starting_outside_z3":   total_outside_z3,
        "z3_entry_pct":                z3_pct,

        # B — origin
        "origin_left":       origin_left,
        "origin_centre":     origin_centre,
        "origin_right":      origin_right,
        "origin_left_pct":   round(origin_left   / safe_n * 100, 1),
        "origin_centre_pct": round(origin_centre / safe_n * 100, 1),
        "origin_right_pct":  round(origin_right  / safe_n * 100, 1),

        # C — progression types
        "progression_types": prog,

        # D — post-Z3
        "z14_count":  z14_count,
        "z14_pct":    round(z14_count / safe_n * 100, 1),
        "wide_count": wide_count,
        "wide_pct":   round(wide_count / safe_n * 100, 1),
        "box_count":  box_count,
        "box_pct":    round(box_count / safe_n * 100, 1),

        # Extra
        "avg_passes_before_entry": avg_passes,
        "avg_seconds_to_entry":    avg_seconds,
    }


def _empty_metrics(total_open: int = 0) -> dict:
    """Return a zeroed-out metrics dict."""
    return {
        "total_z3_entries":          0,
        "total_open_possessions":    total_open,
        "total_starting_outside_z3": 0,
        "z3_entry_pct":              0.0,
        "origin_left": 0, "origin_centre": 0, "origin_right": 0,
        "origin_left_pct": 0.0, "origin_centre_pct": 0.0, "origin_right_pct": 0.0,
        "progression_types":         {k: 0 for k in PROG_KEYS},
        "z14_count": 0, "z14_pct": 0.0,
        "wide_count": 0, "wide_pct": 0.0,
        "box_count": 0, "box_pct": 0.0,
        "avg_passes_before_entry":   0.0,
        "avg_seconds_to_entry":      0.0,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def analyse_general_buildup(
    match_csv: Path,
    team_name: str,
) -> dict:
    """
    Run the full open-play build-up analysis for one team in one match.

    Returns
    -------
    dict with keys ``metrics``, ``entries``, ``debug_events``.
    """
    df = _load_match_events(match_csv)
    if df.empty:
        log.warning("Empty match data for %s", match_csv)
        return {"metrics": _empty_metrics(), "entries": [], "debug_events": []}

    # Ensure qualifier columns exist under both naming conventions
    renames = {
        "Corner taken": "corner_taken",
        "Free kick taken": "free_kick_taken",
        "Throw In": "throw_in",
        "Penalty": "penalty",
        "Gk kick from hands": "gk_kick_from_hands",
        "Through ball": "through_ball",
        "Long ball": "long_ball",
    }
    for orig, new in renames.items():
        if orig in df.columns and new not in df.columns:
            df[new] = df[orig]

    team_lower = team_name.strip().lower()

    # 1. Build possession chains
    df = build_possessions(df)

    # 2. Filter to open play for this team
    open_df = filter_open_play(df, team_lower)
    total_open = open_df["poss_id"].nunique()

    poss_first_x     = open_df.groupby("poss_id")["x"].first().dropna()
    starting_outside = int((poss_first_x < Z3_X_THRESHOLD).sum())

    # 3. Detect FT entries
    entries = detect_entries(open_df)

    # 4. Classify progression type
    entries = classify_entries(entries)

    # 5. Post-Z3 analysis (needs full df for window events)
    entries = analyse_post_z3(entries, df)

    # 6. Aggregate
    metrics = compute_metrics(entries, total_open, starting_outside)

    # Debug trace
    debug = []
    for e in entries:
        debug.append({
            "min":   f"{int(e.get('minute', 0))}:{int(e.get('second', 0)):02d}",
            "period": e.get("period"),
            "player": e.get("player"),
            "type":   e.get("progression_type"),
            "entry":  e.get("entry_type"),
            "origin": f"Z{e.get('origin_zone')}",
            "target": f"Z{e.get('entry_zone')}",
            "elapsed": f"{e.get('elapsed_sec', 0):.0f}s",
            "passes":  e.get("passes_before_count"),
            "z14":     e.get("z14_touch"),
            "wide":    e.get("wide_play"),
            "box":     e.get("box_entry"),
        })

    return {
        "metrics":      metrics,
        "entries":      entries,
        "debug_events": debug,
    }
