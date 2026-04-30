"""
Goal Kick Build-up Analysis  (v3 — Goal Kicks only)
====================================================
Analyses **only goal kicks** (detected via the Opta ``Goal Kick`` column)
and classifies each one by:

* **Type**: short (first receiver in zones 1–6) vs long (zones 7–18)
* **First-receiver zone**: which of the 18 pitch zones the first
  teammate to touch the ball occupies
* **Outcome**: positive (possession kept ≥15 s from first reception)
  vs negative (possession lost within 15 s)

Zone attribution is based on the **first receiver's** position, not
the pass end-point.  Only rows where ``Goal Kick == "Si"`` are
considered; all other distributions are excluded.

Goal kicks can be taken by the goalkeeper or by defenders (CB, LB, RB)
from the goal area, depending on team tactics and preference.

Configurable thresholds are at the top of the file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np

from src.utils.logging import log
from src.team_mapping import canonical_name

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURABLE THRESHOLDS
# ═══════════════════════════════════════════════════════════════════════════════

# Possession-retention window (seconds) after first reception
POSSESSION_WINDOW_SEC: float = 15.0

# Zones considered "short" receiving (defensive third: rows 1-2)
SHORT_ZONES: set[int] = set(range(1, 7))   # Z1–Z6
LONG_ZONES:  set[int] = set(range(7, 19))  # Z7–Z18

# Events that are never "real play" and should be skipped when looking
# for the first receiver or tracking possession.
NON_PLAY_EVENTS: frozenset[str] = frozenset({
    "deleted event", "team setp up", "start", "end",
    "player off", "player on", "resume", "unknown",
    "start delay", "end delay", "formation change",
    "collection end", "early end",
    "injury time announcement", "card",
    "contentious referee decision",
})

# Events that count as a shot attempt
SHOT_EVENTS: frozenset[str] = frozenset({
    "miss", "saved shot", "goal", "save",
})

# Final-third x threshold (zones 13–18, row 5–6)
FINAL_THIRD_X: float = 100.0 / 6 * 4     # ≈ 66.67

# Penalty-area x threshold (zones 16–18, row 6)
BOX_X: float = 100.0 / 6 * 5             # ≈ 83.33

# Enable / disable debug trace (list of per-distribution records).
# When True the returned dict includes a 'debug_events' key with
# a list of dicts that can be printed or exported for validation.
DEBUG_TRACE: bool = True


# ═══════════════════════════════════════════════════════════════════════════════
# 18-ZONE PITCH GRID
# ═══════════════════════════════════════════════════════════════════════════════
#
# Coordinate system (Opta standard, per-team):
#   x: 0 = own goal-line,  100 = opponent goal-line
#   y: 0 = right touchline (from broadcast view), 100 = left touchline
#
# Our 18-zone layout (analysed team attacks left → right):
#
#   Row 6 (x 83.3–100):  Z16  Z17  Z18     ← opponent box area
#   Row 5 (x 66.7–83.3): Z13  Z14  Z15
#   Row 4 (x 50–66.7):   Z10  Z11  Z12
#   Row 3 (x 33.3–50):   Z7   Z8   Z9
#   Row 2 (x 16.7–33.3): Z4   Z5   Z6
#   Row 1 (x 0–16.7):    Z1   Z2   Z3      ← own box area
#
#   Columns: Left (y 0–33.3) | Centre (y 33.3–66.7) | Right (y 66.7–100)
#

ROW_WIDTH = 100.0 / 6          # ≈ 16.67
COL_WIDTH = 100.0 / 3          # ≈ 33.33


def xy_to_zone(x: float, y: float) -> int:
    """
    Convert (x, y) pitch coordinates → zone number 1–18.

    x = progression axis  (0 own goal → 100 opponent goal)
    y = width axis        (0 → 100, touchline to touchline)
    """
    x = max(0.0, min(100.0, float(x)))
    y = max(0.0, min(100.0, float(y)))
    row = min(int(x / ROW_WIDTH), 5)       # 0-based row  (0 = own goal end)
    col = min(int(y / COL_WIDTH), 2)       # 0-based col  (0 = left)
    return row * 3 + col + 1


def zone_label(zone: int) -> str:
    return f"Z{zone}"


# ═══════════════════════════════════════════════════════════════════════════════
# RAW EVENT LOADER
# ═══════════════════════════════════════════════════════════════════════════════

def _load_match_events(match_csv: Path) -> pd.DataFrame:
    """Load raw Opta event CSV → cleaned DataFrame."""
    try:
        df = pd.read_csv(match_csv, low_memory=False)
    except Exception as exc:
        log.error("Failed to load match CSV %s: %s", match_csv, exc)
        return pd.DataFrame()

    col_map = {
        "event_id": "event_id",
        "event": "event_type",
        "type_id": "type_id",
        "period_id": "period",
        "time_min": "minute",
        "time_sec": "second",
        "contestant_id": "team_id",
        "team_name": "team_name",
        "player_name": "player_name",
        "x": "x",
        "y": "y",
        "outcome": "outcome",
        "Pass End X": "pass_end_x",
        "Pass End Y": "pass_end_y",
        "Length": "length",
        "Long ball": "long_ball",
        "Goal Kick": "goal_kick",
        "GK hoof": "gk_hoof",
        "Gk kick from hands": "gk_kick_from_hands",
        "position": "position",
        "timeStamp": "timestamp",
    }
    existing = {k: v for k, v in col_map.items() if k in df.columns}
    df = df.rename(columns=existing)

    for col in ("x", "y", "pass_end_x", "pass_end_y", "length",
                "minute", "second", "event_id", "period", "outcome"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)

    df = df.sort_values(["period", "minute", "second", "event_id"]).reset_index(drop=True)
    return df


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER: timestamp-based elapsed seconds (with fallback)
# ═══════════════════════════════════════════════════════════════════════════════

def _elapsed_seconds(ref_row: pd.Series, row: pd.Series) -> float:
    """Return seconds elapsed between two event rows."""
    ref_ts = ref_row.get("timestamp")
    row_ts = row.get("timestamp")
    if pd.notna(ref_ts) and pd.notna(row_ts):
        return (row_ts - ref_ts).total_seconds()
    # Fallback: minute / second fields (unreliable across periods)
    if row.get("period") != ref_row.get("period"):
        return POSSESSION_WINDOW_SEC + 1          # treat period break as window end
    ref_t = (ref_row.get("minute", 0) or 0) * 60 + (ref_row.get("second", 0) or 0)
    row_t = (row.get("minute", 0) or 0) * 60 + (row.get("second", 0) or 0)
    return row_t - ref_t


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER: team-matching and play-event checks
# ═══════════════════════════════════════════════════════════════════════════════

def _is_same_team(row: pd.Series, team_lower: str) -> bool:
    """Canonical-name match — resolves Opta long names to short canonical form."""
    raw = str(row.get("team_name", "")).strip()
    return canonical_name(raw).lower() == team_lower


def _is_play_event(row: pd.Series) -> bool:
    """Return True if the event is a real on-pitch action."""
    et = str(row.get("event_type", "")).strip().lower()
    return et not in NON_PLAY_EVENTS and et != ""


# ═══════════════════════════════════════════════════════════════════════════════
# IDENTIFY GOAL KICKS
# ═══════════════════════════════════════════════════════════════════════════════

def _is_goal_kick(
    iloc_idx: int,
    df: pd.DataFrame,
    team_lower: str,
) -> bool:
    """
    Return True if the event at *iloc_idx* is a goal kick by the
    analysed team.

    Detection relies **exclusively** on the Opta ``Goal Kick`` column
    (value ``"Si"``).  All other distributions are ignored.

    Additionally requires:
      1. Event is a Pass (type_id == 1)
      2. Belongs to the analysed team
      3. Flagged as Goal Kick in Opta data

    Note: Goal kicks are taken from the goal-area by the goalkeeper
    or, more commonly in modern football, by a defender (CB, LB, RB).
    Position is NOT used as a filter since defenders frequently take goal kicks.
    """
    row = df.iloc[iloc_idx]

    # Must be flagged as a Goal Kick in Opta data
    gk_flag = str(row.get("goal_kick", "")).strip().lower()
    if gk_flag not in ("si", "yes", "1", "true"):
        return False

    # Must be a pass event
    et = str(row.get("event_type", "")).strip().lower()
    tid = row.get("type_id")
    if et != "pass" and tid != 1:
        return False

    # Must be the analysed team
    if not _is_same_team(row, team_lower):
        return False

    return True


# ═══════════════════════════════════════════════════════════════════════════════
# FIND FIRST RECEIVER
# ═══════════════════════════════════════════════════════════════════════════════

def _find_first_receiver(
    gk_iloc: int,
    df: pd.DataFrame,
    team_lower: str,
) -> Optional[dict]:
    """
    After a GK distribution at *gk_iloc*, find the first teammate who
    touches the ball.

    Returns a dict with:
        iloc       – integer position in df
        player     – player name
        x, y       – coordinates of the receiving action
        zone       – 18-zone number
        event_type – event type string

    Returns None if no teammate touch is found (opponent intercepted).
    """
    for j in range(gk_iloc + 1, min(gk_iloc + 20, len(df))):
        row = df.iloc[j]
        if not _is_play_event(row):
            continue
        if _is_same_team(row, team_lower):
            rx = row.get("x")
            ry = row.get("y")
            if pd.notna(rx) and pd.notna(ry):
                zone = xy_to_zone(float(rx), float(ry))
            else:
                zone = 0
            return {
                "iloc": j,
                "player": str(row.get("player_name", "?")),
                "x": rx,
                "y": ry,
                "zone": zone,
                "event_type": str(row.get("event_type", "")),
            }
        else:
            # Opponent touched the ball before any teammate → interception.
            return None
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# EVENT CHAIN EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════

def _event_record(row: pd.Series, team_lower: str) -> dict:
    """Build a chain-event dict from a DataFrame row."""
    et = str(row.get("event_type", "")).strip()
    return {
        "player": str(row.get("player_name", "?")),
        "event_type": et,
        "x": float(row["x"]) if pd.notna(row.get("x")) else None,
        "y": float(row["y"]) if pd.notna(row.get("y")) else None,
        "minute": int(row.get("minute", 0)),
        "second": int(row.get("second", 0)),
        "is_team": _is_same_team(row, team_lower),
        "outcome": row.get("outcome"),
    }


def _extract_chain_and_outcome(
    gk_iloc: int,
    recv_iloc: int | None,
    team_lower: str,
    df: pd.DataFrame,
) -> tuple[list[dict], str, str]:
    """
    Extract the full event chain starting from the goal kick and classify
    a granular outcome.

    Key principle: an opponent touch does NOT automatically mean possession
    is lost.  After any opponent action we look ahead to determine who
    actually controls the ball next:
      • If the analysed team's next play event is a constructive action
        (pass, ball touch, take on, shot, clearance, corner awarded,
        keeper pick-up …), possession was never truly lost.
      • If the opponent's next play event is constructive, OR the team's
        next event is a "lost" event (dispossessed, error), then
        possession has genuinely changed.
      • "Out" / "Corner Awarded" events are resolved by checking which
        team has the restart.

    The 15 s window is always measured from the first receiver's touch.

    Returns
    -------
    (chain, outcome, granular_outcome)
    """
    chain: list[dict] = []
    gk_row = df.iloc[gk_iloc]
    chain.append(_event_record(gk_row, team_lower))

    # ── If no receiver (intercepted immediately) ──
    if recv_iloc is None:
        opp_start = None
        for j in range(gk_iloc + 1, min(gk_iloc + 30, len(df))):
            row = df.iloc[j]
            if not _is_play_event(row):
                continue
            chain.append(_event_record(row, team_lower))
            if not _is_same_team(row, team_lower):
                opp_start = j
                break
            break

        if opp_start is not None:
            neg_level, opp_chain = _track_opponent_possession(opp_start, team_lower, df)
            chain.extend(opp_chain)
            return chain, "negative", neg_level
        return chain, "negative", "N1"

    # ── Build the team's possession chain (within the 15 s window) ──
    ref_row = df.iloc[recv_iloc]
    if recv_iloc != gk_iloc:
        chain.append(_event_record(ref_row, team_lower))

    reached_final_third = False
    created_shot = False

    # Check the receiver's position for final-third entry
    rx = ref_row.get("x")
    if pd.notna(rx) and float(rx) >= FINAL_THIRD_X:
        reached_final_third = True

    j = recv_iloc + 1
    while j < len(df):
        row = df.iloc[j]
        elapsed = _elapsed_seconds(ref_row, row)

        if not _is_play_event(row):
            j += 1
            continue

        is_team = _is_same_team(row, team_lower)
        et = str(row.get("event_type", "")).strip().lower()

        # ── Team action ──
        if is_team:
            chain.append(_event_record(row, team_lower))

            # Shot by the team → P3
            if et in SHOT_EVENTS:
                return chain, "positive", "P3"

            # Check for final-third entry
            ex = row.get("x")
            if pd.notna(ex) and float(ex) >= FINAL_THIRD_X:
                reached_final_third = True

            # Corner awarded to the team → positive (team keeps restart)
            if et == "corner awarded":
                ex2 = row.get("x")
                if pd.notna(ex2) and float(ex2) >= FINAL_THIRD_X:
                    reached_final_third = True

            # 15 s window check
            if elapsed >= POSSESSION_WINDOW_SEC:
                if reached_final_third:
                    return chain, "positive", "P2"
                return chain, "positive", "P1"
            j += 1
            continue

        # ── Opponent action — determine if possession truly changed ──
        chain.append(_event_record(row, team_lower))

        # Foul by opponent → team keeps the restart
        if et == "foul":
            if reached_final_third:
                return chain, "positive", "P2"
            return chain, "positive", "P1"

        # For any other opponent action (aerial, tackle, interception,
        # ball recovery, out, clearance …), look ahead to see who
        # actually has the ball next.
        real_owner = _who_has_possession_next(j, team_lower, df)

        if real_owner == "team":
            # Team still has the ball — continue the possession chain.
            # The look-ahead already told us the ball comes back,
            # so advance j and keep going.
            j += 1
            continue

        if real_owner == "set_piece_team":
            # Ball went out of play but the team gets the restart
            # (throw-in, corner, free kick). Continue possession.
            # Advance past the dead-ball events.
            j += 1
            continue

        # ── Genuine possession loss → track opponent possession ──
        neg_level, opp_chain = _track_opponent_possession(j, team_lower, df)
        chain.extend(opp_chain)
        return chain, "negative", neg_level

    # Reached end of data with team in possession
    if created_shot:
        return chain, "positive", "P3"
    if reached_final_third:
        return chain, "positive", "P2"
    return chain, "positive", "P1"


# ── Contested-event helpers ───────────────────────────────────────────────────

# Events where the opponent wins a duel but the team may still keep the ball
_CONTESTED_EVENTS = frozenset({
    "aerial", "tackle", "interception", "ball recovery",
    "clearance", "blocked pass", "out", "corner awarded",
    "shield ball opp", "challenge",
})

# Events by the team that indicate THEY lost the ball (not constructive)
_TEAM_LOSS_EVENTS = frozenset({
    "dispossessed", "error", "offside pass",
})

# Events by the team that confirm they still control the ball
_TEAM_CONSTRUCTIVE = frozenset({
    "pass", "ball touch", "take on", "aerial", "clearance",
    "miss", "saved shot", "goal", "corner awarded",
    "keeper pick-up", "claim", "punch",
})


def _who_has_possession_next(
    contested_iloc: int,
    team_lower: str,
    df: pd.DataFrame,
) -> str:
    """
    After a contested / opponent event at *contested_iloc*, determine
    who actually ends up with the ball.

    Returns
    -------
    "team"           – analysed team keeps / regains the ball
    "set_piece_team" – ball went out but team gets the restart
    "opponent"       – opponent genuinely has possession
    """
    # Look at the next few real play events after the contested event
    for k in range(contested_iloc + 1, min(contested_iloc + 8, len(df))):
        nxt = df.iloc[k]
        if not _is_play_event(nxt):
            continue
        net = str(nxt.get("event_type", "")).strip().lower()
        nxt_is_team = _is_same_team(nxt, team_lower)

        if nxt_is_team:
            # Team touches the ball next
            if net in _TEAM_LOSS_EVENTS:
                # e.g. "Dispossessed" means the team player had the ball
                # but immediately lost it — this is still opponent possession
                return "opponent"
            if net in _TEAM_CONSTRUCTIVE or net not in _CONTESTED_EVENTS:
                return "team"
            # Another contested event by the team (e.g. aerial) — keep looking
            continue

        # Opponent touches next
        if net == "out" or net == "corner awarded":
            # Ball went out — check who gets the restart
            restart_owner = _restart_owner(k, team_lower, df)
            return restart_owner
        if net in SHOT_EVENTS:
            return "opponent"
        if net in _TEAM_CONSTRUCTIVE or net == "pass":
            return "opponent"
        # Another contested event — keep looking
        continue

    return "opponent"


def _restart_owner(
    out_iloc: int,
    team_lower: str,
    df: pd.DataFrame,
) -> str:
    """
    After an 'Out' or 'Corner Awarded' event, determine which team gets
    the restart by looking at the next pass / set-piece event.
    """
    for k in range(out_iloc + 1, min(out_iloc + 10, len(df))):
        nxt = df.iloc[k]
        if not _is_play_event(nxt):
            continue
        net = str(nxt.get("event_type", "")).strip().lower()
        # Skip duplicate "out" / "corner awarded" mirror events
        if net in ("out", "corner awarded"):
            continue
        if _is_same_team(nxt, team_lower):
            return "set_piece_team"
        return "opponent"
    return "opponent"


def _track_opponent_possession(
    start_iloc: int,
    team_lower: str,
    df: pd.DataFrame,
) -> tuple[str, list[dict]]:
    """
    Follow the opponent's possession from *start_iloc* until they
    genuinely lose the ball (or the phase ends).  Determine the worst
    consequence.

    Key rule: a team event like ``Dispossessed`` or ``Error`` means the
    team player had the ball momentarily but lost it — the opponent still
    has possession.  Only a constructive team action (pass, ball touch,
    take on, clearance …) signals the opponent lost the ball.

    Returns
    -------
    (neg_level, chain_events)
        neg_level    : "N1", "N2", or "N3"
        chain_events : list of event-record dicts (excluding the first,
                       which was already added by the caller)
    """
    extra_chain: list[dict] = []
    entered_box = False
    shot_conceded = False

    for j in range(start_iloc + 1, min(start_iloc + 80, len(df))):
        row = df.iloc[j]
        if not _is_play_event(row):
            continue

        is_team = _is_same_team(row, team_lower)
        et = str(row.get("event_type", "")).strip().lower()

        if not is_team:
            # Still opponent possession
            extra_chain.append(_event_record(row, team_lower))

            # Check for shot
            if et in SHOT_EVENTS:
                shot_conceded = True
                break

            # Check for box entry (opponent x ≥ 83.3)
            ox = row.get("x")
            if pd.notna(ox) and float(ox) >= BOX_X:
                entered_box = True

            continue

        # ── Team event during opponent possession ──
        extra_chain.append(_event_record(row, team_lower))

        # "Dispossessed" / "Error" = team player had the ball briefly
        # but lost it — opponent still has possession. Keep tracking.
        if et in _TEAM_LOSS_EVENTS:
            continue

        # "Out" / "Corner Awarded" — check who gets the restart
        if et in ("out", "corner awarded"):
            restart = _restart_owner(j, team_lower, df)
            if restart == "opponent":
                continue   # opponent keeps possession
            # Team gets restart → opponent lost possession
            break

        # Constructive team action → opponent lost possession
        break

    if shot_conceded:
        return "N3", extra_chain
    if entered_box:
        return "N2", extra_chain
    return "N1", extra_chain


# ═══════════════════════════════════════════════════════════════════════════════
# LEGACY WRAPPER  (kept for backwards compatibility)
# ═══════════════════════════════════════════════════════════════════════════════

def _classify_outcome(
    ref_iloc: int,
    team_lower: str,
    df: pd.DataFrame,
) -> str:
    """
    Legacy wrapper — returns just "positive" / "negative".
    Uses the new chain extraction under the hood.
    """
    _, outcome, _ = _extract_chain_and_outcome(ref_iloc, ref_iloc, team_lower, df)
    return outcome


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ANALYSIS FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════

def analyse_goalkeeper_buildup(
    match_csv: Path,
    team_name: str,
) -> dict:
    """
    Run the goal-kick build-up analysis for one team in one match.

    Only events with ``Goal Kick == "Si"`` are counted.

    Returns
    -------
    dict with keys:
        total            int — goal kicks found
        short_count      int
        long_count       int
        short_pct        float (0–100)
        long_pct         float (0–100)
        zone_counts      dict[int, int]   — {zone: count}  (first-receiver zone)
        zone_outcomes    dict[int, dict]   — {zone: {"positive": n, "negative": n}}
        outcome_counts   dict[str, int]
        events           list[dict]        — per-distribution records
        debug_events     list[dict] | None — detailed trace (if DEBUG_TRACE)
    """
    df = _load_match_events(match_csv)
    if df.empty:
        return _empty_result()

    team_lower = canonical_name(team_name).lower()
    distributions: list[dict] = []
    debug_rows: list[dict] = []

    for iloc_idx in range(len(df)):
        if not _is_goal_kick(iloc_idx, df, team_lower):
            continue

        gk_row = df.iloc[iloc_idx]

        # ── Find first receiver ──
        receiver = _find_first_receiver(iloc_idx, df, team_lower)

        if receiver is not None and receiver["zone"] > 0:
            recv_zone = receiver["zone"]
            recv_iloc = receiver["iloc"]
            recv_player = receiver["player"]
            recv_x = receiver["x"]
            recv_y = receiver["y"]
        else:
            # Pass was intercepted or no valid receiver found.
            end_x = gk_row.get("pass_end_x")
            end_y = gk_row.get("pass_end_y")
            if pd.notna(end_x) and pd.notna(end_y):
                recv_zone = xy_to_zone(float(end_x), float(end_y))
            else:
                recv_zone = 0
            recv_iloc = None
            recv_player = "(intercepted)"
            recv_x = end_x
            recv_y = end_y

        # ── Extract full event chain + granular outcome ──
        chain, outcome, granular = _extract_chain_and_outcome(
            iloc_idx, recv_iloc, team_lower, df,
        )

        # ── Short / Long based on receiving zone ──
        if recv_zone in SHORT_ZONES:
            pass_type = "short"
        elif recv_zone in LONG_ZONES:
            pass_type = "long"
        else:
            length = gk_row.get("length")
            pass_type = "long" if pd.notna(length) and float(length) > 32.0 else "short"

        rec = {
            "minute": gk_row.get("minute", 0),
            "second": gk_row.get("second", 0),
            "period": gk_row.get("period", 1),
            "gk_player": str(gk_row.get("player_name", "GK")),
            "gk_x": gk_row.get("x"),
            "gk_y": gk_row.get("y"),
            "pass_end_x": gk_row.get("pass_end_x"),
            "pass_end_y": gk_row.get("pass_end_y"),
            "receiver": recv_player,
            "recv_x": recv_x,
            "recv_y": recv_y,
            "recv_zone": recv_zone,
            "pass_type": pass_type,
            "outcome": outcome,
            "granular_outcome": granular,
            "chain": chain,
            "goal_kick": str(gk_row.get("goal_kick", "")),
        }
        distributions.append(rec)

        if DEBUG_TRACE:
            debug_rows.append({
                "min": f"{int(rec['minute'])}:{int(rec['second']):02d}",
                "period": rec["period"],
                "gk": rec["gk_player"],
                "from": f"({rec['gk_x']:.1f},{rec['gk_y']:.1f})" if pd.notna(rec["gk_x"]) else "?",
                "receiver": recv_player,
                "recv_pos": f"({float(recv_x):.1f},{float(recv_y):.1f})" if pd.notna(recv_x) else "?",
                "recv_zone": f"Z{recv_zone}" if recv_zone else "?",
                "short_long": pass_type,
                "outcome": outcome,
                "granular": granular,
                "chain_len": len(chain),
                "goal_kick": rec["goal_kick"],
            })

    if not distributions:
        return _empty_result()

    # ── Aggregates ──
    total = len(distributions)
    short_count = sum(1 for d in distributions if d["pass_type"] == "short")
    long_count  = total - short_count
    short_pct = round(short_count / total * 100, 1) if total else 0.0
    long_pct  = round(long_count / total * 100, 1) if total else 0.0

    zone_counts: dict[int, int] = {}
    zone_outcomes: dict[int, dict] = {}
    outcome_counts: dict[str, int] = {"positive": 0, "negative": 0}
    granular_counts: dict[str, int] = {
        "P1": 0, "P2": 0, "P3": 0,
        "N1": 0, "N2": 0, "N3": 0,
    }

    for d in distributions:
        z = d["recv_zone"]
        zone_counts[z] = zone_counts.get(z, 0) + 1
        if z not in zone_outcomes:
            zone_outcomes[z] = {"positive": 0, "negative": 0}
        zone_outcomes[z][d["outcome"]] += 1
        outcome_counts[d["outcome"]] += 1
        granular_counts[d["granular_outcome"]] = granular_counts.get(d["granular_outcome"], 0) + 1

    result = {
        "total": total,
        "short_count": short_count,
        "long_count": long_count,
        "short_pct": short_pct,
        "long_pct": long_pct,
        "zone_counts": zone_counts,
        "zone_outcomes": zone_outcomes,
        "outcome_counts": outcome_counts,
        "granular_counts": granular_counts,
        "events": distributions,
    }

    if DEBUG_TRACE:
        result["debug_events"] = debug_rows

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _empty_result() -> dict:
    return {
        "total": 0,
        "short_count": 0,
        "long_count": 0,
        "short_pct": 0.0,
        "long_pct": 0.0,
        "zone_counts": {},
        "zone_outcomes": {},
        "outcome_counts": {"positive": 0, "negative": 0},
        "granular_counts": {"P1": 0, "P2": 0, "P3": 0, "N1": 0, "N2": 0, "N3": 0},
        "events": [],
        "debug_events": [] if DEBUG_TRACE else None,
    }



