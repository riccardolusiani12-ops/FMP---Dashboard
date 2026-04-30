"""
High Regains Analysis — Chance-Creation Integration
=====================================================
Extracts ball recoveries, interceptions, and successful tackles
in the attacking third (x ≥ 66.7, open play) and links them to
subsequent chance-creation events within a configurable time window.

This module is the **dashboard-ready** port of the logic originally
developed in ``notebooks/01_high_regains.ipynb``.  It is consumed
**exclusively** by the Chance Creation section (Phase 3).

Definitions
-----------
- **High Regain**: a successful recovery-type event in the attacking
  third during open play.
- **Linked chance**: a shot (or key pass) occurring within
  ``WINDOW_SEC`` seconds of a high regain by the *same team* in
  the *same match*.

Coordinate system (Opta)
------------------------
x: 0 → 100  (own goal → opponent goal)
y: 0 → 100  (right → left)
Attacking third:  x ≥ 66.67

References
----------
Ian Graham "Goal Probability Added" model — the PV layer provides
the value-added metric for each linked chain.

Notebook: ``notebooks/01_high_regains.ipynb`` (canonical prototype).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.analytics.possession_value import (
    NON_PLAY_EVENTS,
    FT_X_THRESHOLD,
    SHOT_TYPE_IDS,
    PossessionValueModel,
    get_pv_model,
    get_xt_zone,
)
from src.analytics.general_buildup import build_possessions
from src.team_mapping import canonical_name

log = logging.getLogger("dashboard.high_regains")

# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

#: Minimum x-coordinate for a regain to be considered "high" (attacking third)
HIGH_REGAIN_X_MIN: float = 66.7

#: Event types that qualify as ball recovery actions
HIGH_REGAIN_TYPES: frozenset = frozenset({
    "ball recovery",
    "interception",
    "tackle",
})

#: Maximum time (seconds) between a high regain and a subsequent shot/chance
#: for the regain to be considered "linked to chance creation".
WINDOW_SEC: int = 15

#: Shot event type_ids from the Opta schema
SHOT_TYPE_IDS_SET: frozenset = frozenset(SHOT_TYPE_IDS)

#: Shot event names (lowercase) for text-based matching
SHOT_TYPE_NAMES: frozenset = frozenset({
    "goal", "saved shot", "miss", "post",
    "attempt saved", "shot on post",
})

# Set-piece qualifier columns (same as chance_creation.py)
_SET_PIECE_QUAL_COLS: tuple = (
    "Corner taken", "corner_taken",
    "Free kick taken", "free_kick_taken",
    "Throw In", "throw_in",
    "Throw In set piece",
    "Penalty", "penalty",
    "Goal Kick", "goal_kick",
    "Gk kick from hands", "gk_kick_from_hands",
)


# ═══════════════════════════════════════════════════════════════════════════════
# INTERNAL HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _match_sec(row: pd.Series) -> float:
    """Compute absolute match-second from a row."""
    m = row.get("time_min", row.get("minute", 0)) or 0
    s = row.get("time_sec", row.get("second", 0)) or 0
    p = row.get("period_id", row.get("period", 1)) or 1
    return (float(p) - 1) * 45 * 60 + float(m) * 60 + float(s)


def _is_open_play(row: pd.Series) -> bool:
    """
    Determine whether an event occurred during open play.

    Checks qualifier columns for set-piece markers.  If none are
    found the event is deemed open play.
    """
    for col in _SET_PIECE_QUAL_COLS:
        val = str(row.get(col, "")).strip().lower()
        if val in ("si", "yes", "1", "true"):
            return False

    # Also check the event name itself
    et = str(row.get("event", row.get("event_type", ""))).strip().lower()
    if et in ("corner awarded", "free kick", "throw in", "goal kick",
              "penalty"):
        return False

    return True


def _is_shot_event(row: pd.Series) -> bool:
    """Check if the row is a shot event."""
    type_id = row.get("type_id")
    if pd.notna(type_id):
        try:
            return int(type_id) in SHOT_TYPE_IDS_SET
        except (ValueError, TypeError):
            pass
    et = str(row.get("event", row.get("event_type", ""))).strip().lower()
    return et in SHOT_TYPE_NAMES


def _is_goal_event(row: pd.Series) -> bool:
    """Check if the row is a goal event."""
    type_id = row.get("type_id")
    if pd.notna(type_id):
        try:
            return int(type_id) == 16
        except (ValueError, TypeError):
            pass
    et = str(row.get("event", row.get("event_type", ""))).strip().lower()
    return et == "goal"


def _is_successful_tackle(row: pd.Series) -> bool:
    """A tackle is successful when outcome == 1."""
    et = str(row.get("event", row.get("event_type", ""))).strip().lower()
    if et != "tackle":
        return True  # Not a tackle — no filter
    outcome = row.get("outcome")
    if pd.isna(outcome):
        return False
    return int(outcome) == 1


def _prepare_events(df: pd.DataFrame) -> pd.DataFrame:
    """
    Standardise column names and ensure numeric types,
    matching the approach in chance_creation.py.
    """
    df = df.copy()

    # Rename if needed
    renames = {
        "event": "event_type",
        "time_min": "minute",
        "time_sec": "second",
        "period_id": "period",
    }
    for orig, new in renames.items():
        if orig in df.columns and new not in df.columns:
            df[new] = df[orig]

    # Ensure numeric
    for col in ("x", "y", "minute", "second", "event_id", "period",
                "outcome", "type_id"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Sort
    sort_cols = [c for c in ["period", "minute", "second", "event_id"]
                 if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols).reset_index(drop=True)

    # Match seconds (include period offset for 2nd half etc.)
    period_col = df.get("period", pd.Series(1, index=df.index)).fillna(1)
    minute_col = df.get("minute", pd.Series(0, index=df.index)).fillna(0)
    second_col = df.get("second", pd.Series(0, index=df.index)).fillna(0)
    df["_match_sec"] = (period_col - 1) * 45 * 60 + minute_col * 60 + second_col

    return df


# ═══════════════════════════════════════════════════════════════════════════════
# CORE — High Regains Detection
# ═══════════════════════════════════════════════════════════════════════════════

def detect_high_regains(
    match_df: pd.DataFrame,
    team: str,
    *,
    x_min: float = HIGH_REGAIN_X_MIN,
    open_play_only: bool = True,
) -> pd.DataFrame:
    """
    Detect all high-regain events for *team* in a single match.

    Parameters
    ----------
    match_df : pd.DataFrame
        Full match events (raw CSV rows).
    team : str
        Team to analyse (matched via ``canonical_name``).
    x_min : float
        Minimum x-coordinate threshold (default 66.7).
    open_play_only : bool
        If True, exclude regains that occur from set-piece restarts.

    Returns
    -------
    pd.DataFrame
        Subset of *match_df* rows that qualify as high regains.
        Adds column ``_match_sec`` with absolute match time.
    """
    df = _prepare_events(match_df)
    team_lower = canonical_name(team).lower()

    # Team filter
    team_col = "team_name" if "team_name" in df.columns else "team"
    team_mask = df[team_col].apply(
        lambda t: canonical_name(str(t).strip()).lower() == team_lower
        if pd.notna(t) else False
    )

    # Event type filter (recovery / interception / tackle)
    et_col = "event_type" if "event_type" in df.columns else "event"
    type_mask = df[et_col].astype(str).str.strip().str.lower().isin(HIGH_REGAIN_TYPES)

    # Location filter
    x_mask = df["x"] >= x_min

    combined = team_mask & type_mask & x_mask
    hr_df = df[combined].copy()

    # Tackle success filter
    if not hr_df.empty:
        tackle_mask = hr_df[et_col].astype(str).str.strip().str.lower() == "tackle"
        outcome_ok = hr_df["outcome"] == 1
        hr_df = hr_df[~tackle_mask | outcome_ok].copy()

    # Open play filter
    if open_play_only and not hr_df.empty:
        open_mask = hr_df.apply(_is_open_play, axis=1)
        hr_df = hr_df[open_mask].copy()

    log.debug("High regains for %s: %d events (x >= %.1f, open_play=%s)",
              team, len(hr_df), x_min, open_play_only)

    return hr_df


# ═══════════════════════════════════════════════════════════════════════════════
# CORE — Link High Regains to Shots / Chances
# ═══════════════════════════════════════════════════════════════════════════════

def link_regains_to_shots(
    match_df: pd.DataFrame,
    high_regains: pd.DataFrame,
    team: str,
    *,
    window_sec: int = WINDOW_SEC,
) -> pd.DataFrame:
    """
    For each high regain, find the **first shot** by the same team
    within *window_sec* seconds.

    Parameters
    ----------
    match_df : pd.DataFrame
        Full match events (raw, before _prepare_events — will be
        prepared internally).
    high_regains : pd.DataFrame
        Output of ``detect_high_regains()``.
    team : str
        Team to analyse.
    window_sec : int
        Maximum elapsed seconds for the regain→shot link.

    Returns
    -------
    pd.DataFrame
        One row per linked regain with columns:
        - All original high-regain columns
        - ``shot_idx``, ``shot_minute``, ``shot_second``, ``shot_type``,
          ``shot_player``, ``shot_x``, ``shot_y``, ``shot_is_goal``,
          ``dt_to_shot_sec``
    """
    if high_regains.empty:
        return _empty_linked_df()

    df = _prepare_events(match_df)
    team_lower = canonical_name(team).lower()

    team_col = "team_name" if "team_name" in df.columns else "team"

    # All shots by the same team
    team_mask = df[team_col].apply(
        lambda t: canonical_name(str(t).strip()).lower() == team_lower
        if pd.notna(t) else False
    )
    shot_mask = df.apply(_is_shot_event, axis=1)
    shots_df = df[team_mask & shot_mask].copy()

    if shots_df.empty:
        return _empty_linked_df()

    shot_times = shots_df["_match_sec"].to_numpy()
    shot_indices = shots_df.index.to_numpy()

    linked_rows: list[dict] = []

    for _, hr_row in high_regains.iterrows():
        hr_time = hr_row.get("_match_sec", _match_sec(hr_row))

        # Binary search for the first shot after hr_time
        pos = np.searchsorted(shot_times, hr_time, side="right")
        if pos >= len(shot_times):
            continue

        dt = shot_times[pos] - hr_time
        if dt > window_sec or dt < 0:
            continue

        shot_row = df.loc[shot_indices[pos]]

        linked_rows.append({
            # Regain info
            "regain_idx": hr_row.name if hasattr(hr_row, "name") else -1,
            "regain_type": str(hr_row.get("event_type", hr_row.get("event", ""))).strip(),
            "regain_player": str(hr_row.get("player_name", hr_row.get("player", ""))).strip(),
            "regain_x": float(hr_row.get("x", 0)),
            "regain_y": float(hr_row.get("y", 0)),
            "regain_minute": int(hr_row.get("minute", hr_row.get("time_min", 0)) or 0),
            "regain_second": int(hr_row.get("second", hr_row.get("time_sec", 0)) or 0),
            "regain_match_sec": float(hr_time),
            # Shot info
            "shot_idx": int(shot_indices[pos]),
            "shot_type": str(shot_row.get("event_type", shot_row.get("event", ""))).strip(),
            "shot_player": str(shot_row.get("player_name", shot_row.get("player", ""))).strip(),
            "shot_x": float(shot_row.get("x", 0)),
            "shot_y": float(shot_row.get("y", 0)),
            "shot_minute": int(shot_row.get("minute", shot_row.get("time_min", 0)) or 0),
            "shot_second": int(shot_row.get("second", shot_row.get("time_sec", 0)) or 0),
            "shot_is_goal": _is_goal_event(shot_row),
            "dt_to_shot_sec": round(dt, 1),
        })

    if not linked_rows:
        return _empty_linked_df()

    result = pd.DataFrame(linked_rows)
    log.info("Linked %d / %d high regains to shots (window=%ds) for %s",
             len(result), len(high_regains), window_sec, team)
    return result


def _empty_linked_df() -> pd.DataFrame:
    """Return an empty DataFrame with the expected linked-regain schema."""
    return pd.DataFrame(columns=[
        "regain_idx", "regain_type", "regain_player",
        "regain_x", "regain_y", "regain_minute", "regain_second",
        "regain_match_sec",
        "shot_idx", "shot_type", "shot_player",
        "shot_x", "shot_y", "shot_minute", "shot_second",
        "shot_is_goal", "dt_to_shot_sec",
    ])


# ═══════════════════════════════════════════════════════════════════════════════
# CORE — Compute High-Regain KPIs for Chance Creation
# ═══════════════════════════════════════════════════════════════════════════════

def compute_high_regain_kpis(
    match_df: pd.DataFrame,
    team: str,
    *,
    pv_model: Optional[PossessionValueModel] = None,
    window_sec: int = WINDOW_SEC,
    x_min: float = HIGH_REGAIN_X_MIN,
) -> dict:
    """
    Compute the full set of high-regain KPIs for a team in one match.

    This is the main entry point consumed by ``chance_creation.py``.

    Parameters
    ----------
    match_df : pd.DataFrame
        Full match events DataFrame.
    team : str
        Team to analyse.
    pv_model : PossessionValueModel, optional
        Pre-built PV model for value-added computation.
    window_sec : int
        Time window for regain→shot linkage.
    x_min : float
        Minimum x for "high" regain.

    Returns
    -------
    dict
        ``high_regain_kpis`` structure with keys:

        - ``total_high_regains``: int — count of qualifying regains
        - ``linked_to_shot``: int — regains followed by shot within window
        - ``linked_to_goal``: int — regains followed by goal within window
        - ``shot_conversion_rate``: float — linked_to_shot / total (0–1)
        - ``goal_conversion_rate``: float — linked_to_goal / total (0–1)
        - ``avg_time_to_shot_sec``: float — mean Δt for linked regains
        - ``total_pv_from_regains``: float — sum PV of linked chains
        - ``avg_pv_per_regain``: float — mean PV per linked chain
        - ``top_regain_zones``: list[dict] — top 3 zones by regain count
        - ``regain_types_breakdown``: dict — count per regain type
        - ``linked_details``: list[dict] — per-regain detail rows
        - ``window_sec``: int — the window used
    """
    # 1. Detect high regains
    high_regains = detect_high_regains(
        match_df, team, x_min=x_min, open_play_only=True,
    )

    total = len(high_regains)
    if total == 0:
        return _empty_kpis(window_sec)

    # 2. Link to shots
    linked = link_regains_to_shots(
        match_df, high_regains, team, window_sec=window_sec,
    )

    linked_to_shot = len(linked)
    linked_to_goal = int(linked["shot_is_goal"].sum()) if not linked.empty else 0

    # 3. Time to shot
    avg_dt = float(linked["dt_to_shot_sec"].mean()) if linked_to_shot > 0 else 0.0

    # 4. PV computation for linked chains
    total_pv = 0.0
    if pv_model is not None and linked_to_shot > 0:
        total_pv = _compute_pv_for_linked(match_df, linked, team, pv_model)

    avg_pv = total_pv / linked_to_shot if linked_to_shot > 0 else 0.0

    # 5. Zone breakdown (discretise into 3×3 grid of the attacking third)
    top_zones = _compute_top_zones(high_regains)

    # 6. Regain type breakdown
    et_col = "event_type" if "event_type" in high_regains.columns else "event"
    type_counts = (
        high_regains[et_col]
        .astype(str).str.strip().str.lower()
        .value_counts()
        .to_dict()
    )

    # 7. Detail rows
    detail_rows = linked.to_dict(orient="records") if not linked.empty else []

    kpis = {
        "total_high_regains": total,
        "linked_to_shot": linked_to_shot,
        "linked_to_goal": linked_to_goal,
        "shot_conversion_rate": round(linked_to_shot / total, 4) if total > 0 else 0.0,
        "goal_conversion_rate": round(linked_to_goal / total, 4) if total > 0 else 0.0,
        "avg_time_to_shot_sec": round(avg_dt, 1),
        "total_pv_from_regains": round(total_pv, 4),
        "avg_pv_per_regain": round(avg_pv, 4),
        "top_regain_zones": top_zones,
        "regain_types_breakdown": type_counts,
        "linked_details": detail_rows,
        "window_sec": window_sec,
    }

    log.info(
        "High regain KPIs for %s: %d total, %d→shot (%.0f%%), "
        "%d→goal, avg Δt=%.1fs, total PV=%.3f",
        team, total, linked_to_shot,
        kpis["shot_conversion_rate"] * 100,
        linked_to_goal, avg_dt, total_pv,
    )

    return kpis


def _empty_kpis(window_sec: int) -> dict:
    """Return zeroed-out KPI dict."""
    return {
        "total_high_regains": 0,
        "linked_to_shot": 0,
        "linked_to_goal": 0,
        "shot_conversion_rate": 0.0,
        "goal_conversion_rate": 0.0,
        "avg_time_to_shot_sec": 0.0,
        "total_pv_from_regains": 0.0,
        "avg_pv_per_regain": 0.0,
        "top_regain_zones": [],
        "regain_types_breakdown": {},
        "linked_details": [],
        "window_sec": window_sec,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# PV Computation for Linked Chains
# ═══════════════════════════════════════════════════════════════════════════════

def _compute_pv_for_linked(
    match_df: pd.DataFrame,
    linked: pd.DataFrame,
    team: str,
    pv_model: PossessionValueModel,
) -> float:
    """
    Sum PV across all linked regain→shot chains.

    For each linked regain, the PV is computed as the xT value at the
    regain location (where value was created by winning the ball high).
    This reflects the "Goal Probability Added" by the regain action.
    """
    total_pv = 0.0

    for _, row in linked.iterrows():
        # PV = xT at regain location (value of the zone where ball was won)
        regain_x = float(row.get("regain_x", 0))
        regain_y = float(row.get("regain_y", 50))
        pv_regain = pv_model.get_xT(regain_x, regain_y)

        # If there's a shot, also add the xT gain from regain→shot zone
        shot_x = float(row.get("shot_x", 0))
        shot_y = float(row.get("shot_y", 50))
        pv_shot = pv_model.get_xT(shot_x, shot_y)

        # PV for this chain = max(xT_shot, xT_regain) as the chain
        # produced value by getting the ball high AND converting it.
        # We use the shot zone value as the realised value of the chain.
        total_pv += pv_shot

    return total_pv


# ═══════════════════════════════════════════════════════════════════════════════
# Zone Analysis
# ═══════════════════════════════════════════════════════════════════════════════

def _compute_top_zones(
    high_regains: pd.DataFrame,
    n_top: int = 5,
) -> list[dict]:
    """
    Discretise regain locations into a zone grid within the attacking
    third and return the top *n_top* zones by count.

    Zone grid: 3 columns (x) × 3 rows (y) within x ∈ [66.7, 100],
    y ∈ [0, 100].
    """
    if high_regains.empty:
        return []

    # Discretise into 3×3 grid of the attacking third
    x_bins = [66.7, 77.8, 88.9, 100.0]
    y_bins = [0.0, 33.3, 66.7, 100.0]
    x_labels = ["deep", "mid", "advanced"]
    y_labels = ["right", "centre", "left"]

    df = high_regains.copy()
    df["zone_x"] = pd.cut(
        df["x"].clip(66.7, 100.0),
        bins=x_bins,
        labels=x_labels,
        include_lowest=True,
    )
    df["zone_y"] = pd.cut(
        df["y"].clip(0, 100),
        bins=y_bins,
        labels=y_labels,
        include_lowest=True,
    )

    zone_counts = (
        df.groupby(["zone_x", "zone_y"], observed=True)
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
        .head(n_top)
    )

    return [
        {
            "zone_x": str(row["zone_x"]),
            "zone_y": str(row["zone_y"]),
            "count": int(row["count"]),
        }
        for _, row in zone_counts.iterrows()
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# League Table (multi-team, multi-match)
# ═══════════════════════════════════════════════════════════════════════════════

def build_league_table(
    match_csvs: List[Path],
    *,
    x_min: float = HIGH_REGAIN_X_MIN,
    window_sec: int = WINDOW_SEC,
) -> pd.DataFrame:
    """
    Build a league-wide high-regains table across multiple matches.

    Parameters
    ----------
    match_csvs : list[Path]
        Paths to all match CSV files for the season.
    x_min : float
        Minimum x for high regain.
    window_sec : int
        Time window for regain→shot linkage.

    Returns
    -------
    pd.DataFrame
        One row per team with columns:
        ``team``, ``high_regains``, ``linked_to_shot``,
        ``linked_to_goal``, ``shot_rate``, ``avg_dt_sec``.
    """
    team_stats: Dict[str, Dict] = {}

    for csv_path in match_csvs:
        try:
            df = pd.read_csv(csv_path, low_memory=False)
        except Exception as exc:
            log.warning("Failed to read %s: %s", csv_path, exc)
            continue

        if df.empty:
            continue

        # Get all unique teams in the match
        team_col = "team_name" if "team_name" in df.columns else "team"
        if team_col not in df.columns:
            continue

        teams = df[team_col].dropna().unique()

        for t in teams:
            t_name = canonical_name(str(t).strip())
            hr_df = detect_high_regains(df, t_name, x_min=x_min)
            linked = link_regains_to_shots(df, hr_df, t_name, window_sec=window_sec)

            if t_name not in team_stats:
                team_stats[t_name] = {
                    "high_regains": 0,
                    "linked_to_shot": 0,
                    "linked_to_goal": 0,
                    "dt_sum": 0.0,
                }

            stats = team_stats[t_name]
            stats["high_regains"] += len(hr_df)
            stats["linked_to_shot"] += len(linked)
            if not linked.empty:
                stats["linked_to_goal"] += int(linked["shot_is_goal"].sum())
                stats["dt_sum"] += float(linked["dt_to_shot_sec"].sum())

    if not team_stats:
        return pd.DataFrame(columns=[
            "team", "high_regains", "linked_to_shot",
            "linked_to_goal", "shot_rate", "avg_dt_sec",
        ])

    rows = []
    for t_name, stats in team_stats.items():
        total = stats["high_regains"]
        linked = stats["linked_to_shot"]
        rows.append({
            "team": t_name,
            "high_regains": total,
            "linked_to_shot": linked,
            "linked_to_goal": stats["linked_to_goal"],
            "shot_rate": round(linked / total, 4) if total > 0 else 0.0,
            "avg_dt_sec": round(stats["dt_sum"] / linked, 1) if linked > 0 else 0.0,
        })

    result = (
        pd.DataFrame(rows)
        .sort_values("high_regains", ascending=False)
        .reset_index(drop=True)
    )
    result.index += 1  # 1-based ranking

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC ENTRY POINT (match-level)
# ═══════════════════════════════════════════════════════════════════════════════

def analyse_high_regains(
    match_csv: Path,
    team_name: str,
    *,
    pv_model: Optional[PossessionValueModel] = None,
    window_sec: int = WINDOW_SEC,
) -> dict:
    """
    Run the full high-regain analysis for one team in one match.

    Parameters
    ----------
    match_csv : Path
        Path to the match CSV file.
    team_name : str
        Team name to analyse.
    pv_model : PossessionValueModel, optional
        Pre-built PV model. If None, will be loaded/built automatically.
    window_sec : int
        Time window (seconds) for regain→shot linkage.

    Returns
    -------
    dict — the ``high_regain_kpis`` structure.
    """
    df = pd.read_csv(match_csv, low_memory=False)
    if df.empty:
        log.warning("Empty match data for %s", match_csv)
        return _empty_kpis(window_sec)

    if pv_model is None:
        try:
            pv_model = get_pv_model()
        except Exception:
            log.warning("PV model unavailable — PV metrics will be zero.")
            pv_model = None

    return compute_high_regain_kpis(
        df, team_name,
        pv_model=pv_model,
        window_sec=window_sec,
    )
