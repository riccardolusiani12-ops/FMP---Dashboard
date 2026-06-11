"""
Formation Analytics Module
===========================
Analyses match-event CSVs to extract team formations (starting + in-match changes).

Provides:
  - extract_team_formations()          → per-match formation list for a team
  - compute_formation_counts()         → aggregated formation usage for a season
  - extract_formation_lineup_stats()   → per-slot player stats for a specific formation
  - build_formation_pitch_figure()     → Plotly pitch visualisation of a formation

Data source: Opta match-event CSVs under data/raw/serie_a_*/events/
Formation data columns:
  - type_id 34: "Team setup" — contains starting formation
  - type_id 40: "Formation change" — in-match formation change
  - 'formation' column: numeric code (e.g. 433 → 4-3-3)
  - 'Team Formation': Opta internal formation ID
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from src.config import RAW_DATA_DIR
from src.team_mapping import canonical_name


# ═══════════════════════════════════════════════════════════════════════════════
# FORMATION CODE → DISPLAY STRING
# ═══════════════════════════════════════════════════════════════════════════════

def formation_display(code: int) -> str:
    """
    Convert a numeric formation code to a human-readable string.
    E.g. 433 → '4-3-3', 4231 → '4-2-3-1', 41212 → '4-1-2-1-2'
    """
    s = str(int(code))
    return "-".join(list(s))


# ═══════════════════════════════════════════════════════════════════════════════
# FORMATION POSITION TEMPLATES
# ═══════════════════════════════════════════════════════════════════════════════
# Each formation maps to 11 player (x, y) positions on a 0–100 pitch.
# x = pitch length (0 = own goal, 100 = opponent goal)
# y = pitch width (0 = left, 100 = right)
# GK is always at (5, 50).
# Positions are approximate and meant for visual display purposes.

_FORMATION_POSITIONS: dict[str, list[tuple[float, float]]] = {
    "4-4-2": [
        (5, 50),                                          # GK
        (22, 15), (22, 38), (22, 62), (22, 85),         # DEF
        (48, 15), (48, 38), (48, 62), (48, 85),         # MID
        (72, 35), (72, 65),                              # FWD
    ],
    "4-3-3": [
        (5, 50),
        (22, 15), (22, 38), (22, 62), (22, 85),
        (45, 30), (45, 50), (45, 70),
        (72, 20), (72, 50), (72, 80),
    ],
    "4-2-3-1": [
        (5, 50),
        (22, 15), (22, 38), (22, 62), (22, 85),
        (40, 35), (40, 65),
        (58, 20), (58, 50), (58, 80),
        (75, 50),
    ],
    "3-5-2": [
        (5, 50),
        (22, 25), (22, 50), (22, 75),
        (42, 10), (42, 30), (42, 50), (42, 70), (42, 90),
        (72, 35), (72, 65),
    ],
    "3-4-2-1": [
        (5, 50),
        (22, 25), (22, 50), (22, 75),
        (42, 15), (42, 38), (42, 62), (42, 85),
        (60, 35), (60, 65),
        (75, 50),
    ],
    "4-1-2-1-2": [
        (5, 50),
        (22, 15), (22, 38), (22, 62), (22, 85),
        (38, 50),
        (50, 30), (50, 70),
        (60, 50),
        (72, 35), (72, 65),
    ],
    "5-3-2": [
        (5, 50),
        (22, 10), (22, 30), (22, 50), (22, 70), (22, 90),
        (45, 30), (45, 50), (45, 70),
        (72, 35), (72, 65),
    ],
    "5-4-1": [
        (5, 50),
        (22, 10), (22, 30), (22, 50), (22, 70), (22, 90),
        (48, 15), (48, 38), (48, 62), (48, 85),
        (72, 50),
    ],
    "4-5-1": [
        (5, 50),
        (22, 15), (22, 38), (22, 62), (22, 85),
        (45, 10), (45, 30), (45, 50), (45, 70), (45, 90),
        (72, 50),
    ],
    "4-4-1-1": [
        (5, 50),
        (22, 15), (22, 38), (22, 62), (22, 85),
        (42, 15), (42, 38), (42, 62), (42, 85),
        (60, 50),
        (75, 50),
    ],
    "4-1-4-1": [
        (5, 50),
        (22, 15), (22, 38), (22, 62), (22, 85),
        (36, 50),
        (52, 15), (52, 38), (52, 62), (52, 85),
        (72, 50),
    ],
    "4-3-2-1": [
        (5, 50),
        (22, 15), (22, 38), (22, 62), (22, 85),
        (42, 25), (42, 50), (42, 75),
        (60, 35), (60, 65),
        (75, 50),
    ],
    "4-2-2-2": [
        (5, 50),
        (22, 15), (22, 38), (22, 62), (22, 85),
        (42, 35), (42, 65),
        (58, 35), (58, 65),
        (72, 35), (72, 65),
    ],
    "3-4-3": [
        (5, 50),
        (22, 25), (22, 50), (22, 75),
        (42, 15), (42, 38), (42, 62), (42, 85),
        (72, 20), (72, 50), (72, 80),
    ],
    "3-5-1-1": [
        (5, 50),
        (22, 25), (22, 50), (22, 75),
        (42, 10), (42, 30), (42, 50), (42, 70), (42, 90),
        (60, 50),
        (75, 50),
    ],
    "3-4-1-2": [
        (5, 50),
        (22, 25), (22, 50), (22, 75),
        (40, 15), (40, 38), (40, 62), (40, 85),
        (58, 50),
        (72, 35), (72, 65),
    ],
    "3-1-4-2": [
        (5, 50),
        (22, 25), (22, 50), (22, 75),
        (35, 50),
        (50, 15), (50, 38), (50, 62), (50, 85),
        (72, 35), (72, 65),
    ],
    "4-1-3-2": [
        (5, 50),
        (22, 15), (22, 38), (22, 62), (22, 85),
        (38, 50),
        (52, 25), (52, 50), (52, 75),
        (72, 35), (72, 65),
    ],
    "4-3-1-2": [
        (5, 50),
        (22, 15), (22, 38), (22, 62), (22, 85),
        (40, 25), (40, 50), (40, 75),
        (58, 50),
        (72, 35), (72, 65),
    ],
    "4-4-2-0": [
        # Fallback identical to 4-4-2 for numeric codes ending in 0
        (5, 50),
        (22, 15), (22, 38), (22, 62), (22, 85),
        (48, 15), (48, 38), (48, 62), (48, 85),
        (72, 35), (72, 65),
    ],
}


def _get_positions(formation_str: str) -> list[tuple[float, float]]:
    """Return player positions for a formation string, or a fallback layout."""
    if formation_str in _FORMATION_POSITIONS:
        return _FORMATION_POSITIONS[formation_str]
    # Fallback: generic 11 dots spread on the pitch
    return [
        (5, 50),
        (22, 20), (22, 40), (22, 60), (22, 80),
        (45, 20), (45, 40), (45, 60), (45, 80),
        (70, 35), (70, 65),
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1 — EXTRACT FORMATIONS FROM CSV FILES
# ═══════════════════════════════════════════════════════════════════════════════

def extract_team_formations(season: str, team: str) -> pd.DataFrame:
    """
    Extract all formations used by a team across a season.

    For each match, captures:
      - Starting formation (from type_id 34 "Team setup")
      - In-match formation changes (from type_id 40 "Formation change")

    Parameters
    ----------
    season : str
        Season key like '2025_2026'
    team : str
        Canonical team name (e.g. 'Bologna')

    Returns
    -------
    pd.DataFrame with columns:
        match_file, team, formation_code, formation_str, is_starting, minute
    """
    events_dir = RAW_DATA_DIR / f"serie_a_{season}" / "events"
    if not events_dir.exists():
        return pd.DataFrame()

    csv_files = sorted(events_dir.glob("*.csv"))
    records: list[dict] = []

    for fp in csv_files:
        try:
            df = pd.read_csv(
                fp,
                usecols=["type_id", "team_name", "team_position", "formation",
                         "Team Formation", "time_min", "period_id"],
                low_memory=False,
            )
        except Exception:
            continue

        # Check if this team played in this match
        # Resolve team name from CSV (Opta long-form → canonical)
        team_names_in_match = df["team_name"].dropna().unique()
        canonical_names = {canonical_name(n): n for n in team_names_in_match}

        if team not in canonical_names:
            continue

        opta_name = canonical_names[team]

        # --- Starting formation (type_id 34, one per team per match) ---
        setup = df[(df["type_id"] == 34) & (df["team_name"] == opta_name)]
        if not setup.empty:
            form_code = setup.iloc[0]["formation"]
            if pd.notna(form_code):
                records.append({
                    "match_file": fp.name,
                    "team": team,
                    "formation_code": int(form_code),
                    "formation_str": formation_display(int(form_code)),
                    "is_starting": True,
                    "minute": 0,
                })

        # --- In-match formation changes (type_id 40) ---
        changes = df[(df["type_id"] == 40) & (df["team_name"] == opta_name)]
        for _, row in changes.iterrows():
            form_code = row["formation"]
            minute = row.get("time_min", 0)
            if pd.notna(form_code):
                form_code_int = int(form_code)
                records.append({
                    "match_file": fp.name,
                    "team": team,
                    "formation_code": form_code_int,
                    "formation_str": formation_display(form_code_int),
                    "is_starting": False,
                    "minute": int(minute) if pd.notna(minute) else 0,
                })

    return pd.DataFrame(records)


def compute_formation_counts(
    season: str,
    team: str,
    min_count: int = 3,
) -> pd.DataFrame:
    """
    Compute formation usage counts for a team in a season.

    Counts each formation every time it appears — either as a starting
    formation or as an in-match change. This means a single match can
    contribute at most 1 starting formation + N change formations.

    Only formations used >= min_count times are returned.

    Parameters
    ----------
    season : str
        Season key like '2025_2026'
    team : str
        Canonical team name
    min_count : int
        Minimum number of times a formation must appear to be included.

    Returns
    -------
    pd.DataFrame with columns: formation_str, count, pct
        Sorted by count descending, limited to top 3 qualifying formations.
    """
    formations_df = extract_team_formations(season, team)
    if formations_df.empty:
        return pd.DataFrame(columns=["formation_str", "count", "pct"])

    # Count occurrences of each formation string
    counts = (
        formations_df
        .groupby("formation_str")
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
        .reset_index(drop=True)
    )

    # Apply threshold
    counts = counts[counts["count"] >= min_count].reset_index(drop=True)

    # Percentage of total formations
    total = counts["count"].sum()
    counts["pct"] = (counts["count"] / total * 100).round(1) if total > 0 else 0.0

    # Return top 3
    return counts.head(3).reset_index(drop=True)


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2 — FORMATION LINEUP STATS (per-slot player aggregates)
# ═══════════════════════════════════════════════════════════════════════════════

# Opta Player Position codes
_POS_LABEL = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


def _parse_qualifiers(qual_str: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for part in str(qual_str).split(";"):
        part = part.strip()
        if ":" in part:
            key, val = part.split(":", 1)
            result[key.strip()] = [x.strip() for x in val.strip().split(",")]
    return result


def extract_formation_lineup_stats(
    season: str,
    team: str,
    formation_str: str,
) -> pd.DataFrame:
    """
    For every match in which *team* started in *formation_str*, collect per-player
    stats aggregated across the full season.

    Only players who started (formation slot 1–11) in that formation are included.
    When multiple players shared the same slot across different matches the top
    contributor per slot (most starts) is the primary entry; all are returned so
    the caller can show depth.

    Returns
    -------
    pd.DataFrame with columns:
        slot, player_id, name, jersey, pos_code, pos_label,
        starts, total_mins, avg_mins_per_start
    Sorted by slot asc, starts desc.
    """
    # Convert "3-5-2" → 352 for matching against the numeric formation column
    try:
        form_code = int(formation_str.replace("-", ""))
    except ValueError:
        return pd.DataFrame()

    events_dir = RAW_DATA_DIR / f"serie_a_{season}" / "events"
    if not events_dir.exists():
        return pd.DataFrame()

    csv_files = sorted(events_dir.glob("*.csv"))

    # Accumulate: player_id → aggregate dict
    from collections import defaultdict
    agg: dict[str, dict] = defaultdict(lambda: {
        "name": "?", "jersey": "?", "pos_code": 0, "slot": 0,
        "starts": 0, "total_mins": 0,
    })

    for fp in csv_files:
        try:
            df = pd.read_csv(fp, low_memory=False)
        except Exception:
            continue

        # Resolve team name
        team_names_in_match = df["team_name"].dropna().unique()
        canonical_map = {canonical_name(n): n for n in team_names_in_match}
        if team not in canonical_map:
            continue
        opta_name = canonical_map[team]

        # Check starting formation
        setup_rows = df[(df["type_id"] == 34) & (df["team_name"] == opta_name)]
        if setup_rows.empty:
            continue
        setup_row = setup_rows.iloc[0]
        match_form = setup_row.get("formation", None)
        if pd.isna(match_form) or int(match_form) != form_code:
            continue

        # Build player_id → name from regular events
        player_map = (
            df[["player_id", "player_name"]]
            .dropna()
            .drop_duplicates()
            .set_index("player_id")["player_name"]
            .to_dict()
        )

        # Match total minutes
        p2_end = df[(df["type_id"] == 30) & (df["period_id"] == 2)]["time_min"].max()
        total_match_mins = int(p2_end) if pd.notna(p2_end) else 90

        quals = _parse_qualifiers(setup_row["represented_qualifiers"])
        involved = quals.get("Involved", [])
        jerseys = quals.get("Jersey Number", [])
        pos_codes = quals.get("Player Position", [])
        slots = quals.get("Team Player Formation", [])

        subs_off = df[(df["type_id"] == 18) & (df["team_name"] == opta_name)]

        for pid, jn, pos, slot_str in zip(involved, jerseys, pos_codes, slots):
            try:
                slot = int(slot_str)
            except ValueError:
                continue
            if slot == 0:
                continue  # bench player in this match

            # Minutes: started at 0, subbed off at minute_out
            sub_off_row = subs_off[subs_off["player_id"] == pid]
            minute_out = (
                int(sub_off_row.iloc[0]["time_min"])
                if not sub_off_row.empty
                else total_match_mins
            )

            entry = agg[pid]
            entry["name"] = player_map.get(pid, entry["name"])
            entry["jersey"] = jn
            try:
                entry["pos_code"] = int(pos)
            except (ValueError, TypeError):
                pass
            entry["slot"] = slot
            entry["starts"] += 1
            entry["total_mins"] += minute_out

    if not agg:
        return pd.DataFrame()

    rows = []
    for pid, d in agg.items():
        rows.append({
            "slot": d["slot"],
            "player_id": pid,
            "name": d["name"],
            "jersey": d["jersey"],
            "pos_code": d["pos_code"],
            "pos_label": _POS_LABEL.get(d["pos_code"], ""),
            "starts": d["starts"],
            "total_mins": d["total_mins"],
            "avg_mins_per_start": round(d["total_mins"] / d["starts"], 1) if d["starts"] else 0,
        })

    result = (
        pd.DataFrame(rows)
        .sort_values(["slot", "starts"], ascending=[True, False])
        .reset_index(drop=True)
    )
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 3 — PLAYER-TO-DOT ASSIGNMENT
# ═══════════════════════════════════════════════════════════════════════════════

def _hungarian_assign(cost: np.ndarray) -> np.ndarray:
    """
    Solve the linear assignment problem (minimise total cost).
    Returns an array `assignment` where assignment[i] = j means player i
    is assigned to dot j.  Pure numpy — no scipy dependency.
    Uses the O(n³) Kuhn-Munkres algorithm.
    """
    n = cost.shape[0]
    INF = 1e18
    u = np.zeros(n + 1)
    v = np.zeros(n + 1)
    p = np.zeros(n + 1, dtype=int)   # p[j] = row (player) assigned to col j
    way = np.zeros(n + 1, dtype=int)

    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = np.full(n + 1, INF)
        used = np.zeros(n + 1, dtype=bool)
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], INF, -1
            for j in range(1, n + 1):
                if not used[j]:
                    cur = cost[i0 - 1, j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j] = cur
                        way[j] = j0
                    if minv[j] < delta:
                        delta = minv[j]
                        j1 = j
            for j in range(n + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while j0:
            p[j0] = p[way[j0]]
            j0 = way[j0]

    # p[j] = player (1-indexed) assigned to col j (1-indexed dot)
    assignment = np.zeros(n, dtype=int)
    for j in range(1, n + 1):
        if p[j] > 0:
            assignment[p[j] - 1] = j - 1   # player → dot index (0-based)
    return assignment


def assign_players_to_dots(
    formation_str: str,
    lineup_df: "pd.DataFrame",
    positions_df: "pd.DataFrame",
) -> list[dict]:
    """
    Assign the top player per slot to the closest template dot using the
    Hungarian (optimal linear assignment) algorithm.

    Template dot positions are FIXED — dots never move.  Only the hover label
    on each dot changes to reflect the best-matching player.

    Rules applied before the cost matrix is built:
    - GK (pos_code == 1) is always assigned to dot index 0 (the GK dot at x=5).
    - All other players are matched to the remaining 10 outfield dots.
    - Cost metric: squared Euclidean distance between the player's season-median
      (x, y) and the dot's template (x, y).

    Parameters
    ----------
    formation_str : str
    lineup_df : DataFrame with columns slot, player_id, name, jersey, pos_code,
                pos_label, starts, total_mins, avg_mins_per_start.
                One row per (slot, player) — top player per slot is used.
    positions_df : DataFrame with columns player_id, median_x, median_y.

    Returns
    -------
    List of 11 dicts (one per template dot, index 0 = GK dot), each with:
        player_id, name, jersey, pos_label, pos_code, starts, total_mins,
        avg_mins_per_start
    A dict will be empty ({}) for dots where no player could be matched.
    """
    template = _get_positions(formation_str)   # 11 (x, y) pairs

    # Build player lookup maps from lineup (top player per slot)
    top = lineup_df.drop_duplicates("slot")
    pid_to_pos = positions_df.set_index("player_id")[["median_x", "median_y"]].to_dict("index")

    # Separate GK(s) from outfield players
    gk_rows    = top[top["pos_code"] == 1]
    field_rows = top[top["pos_code"] != 1]

    # ── Assign GK to dot 0 ────────────────────────────────────────────────────
    result: list[dict] = [{} for _ in range(11)]

    if not gk_rows.empty:
        gk = gk_rows.iloc[0]
        result[0] = gk.to_dict()

    # ── Build cost matrix for outfield players vs outfield dots ───────────────
    outfield_dots = template[1:]          # 10 dots
    field_list = field_rows.to_dict("records")

    # We need exactly 10 players for 10 dots.
    # If fewer players have position data, fill missing with template positions.
    n_dots = len(outfield_dots)
    n_players = len(field_list)

    if n_players == 0:
        return result

    # Pad with dummy rows if fewer than 10 real players (edge cases / data gaps)
    padded = field_list + [None] * (n_dots - n_players)

    cost = np.zeros((n_dots, n_dots))
    LARGE = 1e9  # cost for a dummy/unpositioned player — assigned last

    for i, player in enumerate(padded):
        if player is None:
            cost[i, :] = LARGE
            continue
        pid = player["player_id"]
        xy = pid_to_pos.get(pid)
        if xy is None:
            # No position data — large cost so this player is assigned to a
            # leftover dot and won't displace a positioned player
            cost[i, :] = LARGE
        else:
            px, py = xy["median_x"], xy["median_y"]
            for j, (dx, dy) in enumerate(outfield_dots):
                cost[i, j] = (px - dx) ** 2 + (py - dy) ** 2

    assignment = _hungarian_assign(cost)   # player i → dot index assignment[i]

    for i, player in enumerate(padded):
        dot_idx = assignment[i] + 1        # +1 because dot 0 is GK
        if player is not None and cost[i, assignment[i]] < LARGE:
            result[dot_idx] = player

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 4 — PLOTLY PITCH FIGURE
# ═══════════════════════════════════════════════════════════════════════════════

# Visual palette — sourced from the shared design system (theme.py).
# Pitch markings/background now come from pitch_utils.draw_pitch(style="formation").
from src.styling.theme import COLORS_DARK, SEMANTIC_COLORS
from src.styling.pitch_utils import draw_pitch

_DOT_RED        = COLORS_DARK["accent"]            # "#8a1f33" — outfield players
_DOT_GK         = SEMANTIC_COLORS["gk_marker"]     # "#3cb371" — goalkeeper
_GLOW_RED       = "rgba(230, 57, 70, 0.22)"        # soft glow behind outfield dots
_GLOW_GK        = "rgba(60, 179, 113, 0.22)"       # soft glow behind GK dot


def build_formation_pitch_figure(
    formation_str: str,
    count: int = 0,
    pct: float = 0.0,
    lineup_df: "pd.DataFrame | None" = None,
    positions_df: "pd.DataFrame | None" = None,
) -> go.Figure:
    """
    Build a Plotly figure showing a formation on a simplified football pitch.

    Dot positions are always fixed to the formation template — they never move.
    When lineup_df + positions_df are provided, each dot is labelled with the
    player whose season-average position is closest to that dot, using the
    optimal Hungarian assignment.  GK is always assigned to the GK dot.

    Parameters
    ----------
    formation_str : str
    count, pct    : unused, kept for API compatibility
    lineup_df     : per-slot player stats (columns: slot, player_id, name,
                    jersey, pos_code, pos_label, starts, total_mins,
                    avg_mins_per_start).
    positions_df  : player season-average positions (columns: player_id,
                    median_x, median_y, n_events).
    """
    template_positions = _get_positions(formation_str)   # always 11 fixed dots

    # ── Resolve per-dot player label via Hungarian assignment ─────────────────
    # dot_players[i] is the player dict assigned to template dot i (0-based).
    # Empty dict means no data for that dot.
    dot_players: list[dict] = [{} for _ in range(11)]

    if (
        lineup_df is not None and not lineup_df.empty
        and positions_df is not None and not positions_df.empty
    ):
        dot_players = assign_players_to_dots(formation_str, lineup_df, positions_df)
    elif lineup_df is not None and not lineup_df.empty:
        # No position data — fall back to slot-order assignment (dot i → slot i+1)
        top = lineup_df.drop_duplicates("slot").sort_values("slot")
        for i, (_, row) in enumerate(top.iterrows()):
            if i < 11:
                dot_players[i] = row.to_dict()

    def _hover_text(dot_idx: int) -> str:
        d = dot_players[dot_idx]
        if not d:
            return "<extra></extra>"
        return (
            f"<b>#{d.get('jersey','?')}  {d.get('name','')}</b><br>"
            f"<span style='color:#aaa'>{d.get('pos_label','')}</span><br>"
            f"──────────────<br>"
            f"Starts:  <b>{int(d.get('starts', 0))}</b><br>"
            f"Minutes: <b>{int(d.get('total_mins', 0))}</b><br>"
            f"Avg min: <b>{float(d.get('avg_mins_per_start', 0.0)):.1f}</b>"
            "<extra></extra>"
        )

    has_hover = any(dot_players)

    fig = go.Figure()

    # ── Pitch markings + square seamless layout (shared design system) ──
    # First adopter of pitch_utils.draw_pitch (style="formation").
    # The formation pitch intentionally stays DARK in both themes — the
    # client-side theme observer skips ".formation-pitch" containers and the
    # CSS keeps the dark card look in light mode (.pitch-dark convention).
    draw_pitch(fig, theme="dark", style="formation", height=300, width=300)

    # ── Player markers — fixed template dots, hover label from assignment ──────
    gk_pos   = template_positions[0]
    outfield = template_positions[1:]

    # Glow batch traces (no hover — performance)
    fig.add_trace(go.Scatter(
        x=[gk_pos[0]], y=[gk_pos[1]],
        mode="markers",
        marker=dict(size=26, color=_GLOW_GK, line=dict(width=0)),
        showlegend=False, hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=[p[0] for p in outfield],
        y=[p[1] for p in outfield],
        mode="markers",
        marker=dict(size=24, color=_GLOW_RED, line=dict(width=0)),
        showlegend=False, hoverinfo="skip",
    ))

    # Individual dot traces — one per dot so each gets its own hovertemplate
    # dot index 0 = GK dot, dots 1-10 = outfield
    for dot_idx, (x, y) in enumerate(template_positions):
        is_gk = dot_idx == 0
        fig.add_trace(go.Scatter(
            x=[x], y=[y],
            mode="markers",
            marker=dict(
                size=14 if is_gk else 13,
                color=_DOT_GK if is_gk else _DOT_RED,
                line=dict(width=2, color="rgba(255,255,255,0.8)"),
            ),
            showlegend=False,
            hovertemplate=_hover_text(dot_idx) if has_hover else None,
            hoverinfo="skip" if not has_hover else None,
        ))

    # ── Layout ────────────────────────────────────────────────
    # Square 300×300 seamless layout already applied by draw_pitch()
    # (style="formation"). Only the hover styling is chart-specific.
    if has_hover:
        fig.update_layout(
            hoverlabel=dict(
                bgcolor="#0d1b2a",
                bordercolor="rgba(255,255,255,0.15)",
                font=dict(family="Inter, system-ui, sans-serif", size=12, color="#e8eaf0"),
                align="left",
            ),
            hovermode="closest",
        )

    return fig
