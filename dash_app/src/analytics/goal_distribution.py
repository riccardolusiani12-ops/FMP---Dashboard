"""
Goal Distribution Analytics Module
====================================
Aggregates goals scored and conceded by a team across a season
into 15-minute match windows.

Data source: Opta match-event CSVs under data/raw/serie_a_*/events/
Goal event: type_id == 16
Own-goal:   "own goal" column == "Si"

Time windows:
  0'–15'  | 15'–30' | 30'–45' | 45'–60' | 60'–75' | 75'–90'
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from src.config import RAW_DATA_DIR
from src.team_mapping import canonical_name
from src.utils.logging import log


# ── Bin definitions ──────────────────────────────────────────────────────────
BINS = [
    ("0'–15'",  0,  15),
    ("15'–30'", 15, 30),
    ("30'–45'", 30, 45),
    ("45'–60'", 45, 60),
    ("60'–75'", 60, 75),
    ("75'–90'", 75, None),   # None = no upper bound
]

BIN_LABELS = [b[0] for b in BINS]


def _minute_to_bin(minute: int) -> str:
    """Map a goal minute to the corresponding 15-minute bin label.

    Stoppage time logic:
    - first-half stoppage (period_id 1, minute >= 45) -> '30'–45''
    - second-half stoppage (period_id 2, minute >= 90) -> '75'–90''
    These are handled naturally by the bin ranges since 45+ falls into
    the 45–60 bin only if period_id is 2, but for simplicity we use
    minute-based binning which already works:
    - minute 45 with period_id=1 is first-half stoppage → we remap to 44
      externally before calling this function.
    """
    for label, lo, hi in BINS:
        if hi is None:
            if minute >= lo:
                return label
        else:
            if lo <= minute < hi:
                return label
    # Fallback: last bin
    return BINS[-1][0]


def _effective_minute(row: pd.Series) -> int:
    """Return the effective minute for bin assignment.

    Handles stoppage time: if period_id == 1 and minute >= 45,
    cap at 44 so it falls into the '30'–45'' bin.
    If period_id == 2 and minute >= 90, leave as-is (falls into '75'–90'').
    """
    minute = int(row["time_min"])
    period = row.get("period_id", None)

    if period is not None:
        try:
            period = int(period)
        except (ValueError, TypeError):
            period = None

    # First-half stoppage time: minute >= 45 in period 1
    if period == 1 and minute >= 45:
        return 44  # maps to 30'–45'

    return minute


def compute_goal_distribution(
    season: str,
    team: str,
) -> Optional[pd.DataFrame]:
    """Aggregate goals scored and conceded per 15-minute window for a team.

    Parameters
    ----------
    season : str
        Season key like '2025_2026'.
    team : str
        Canonical team name (e.g. 'Bologna').

    Returns
    -------
    pd.DataFrame with columns: bin, scored, conceded
        One row per 15-minute bin (always 6 rows).
        Returns None if no event files found.
    """
    events_dir = RAW_DATA_DIR / f"serie_a_{season}" / "events"
    if not events_dir.exists():
        log.warning("No events directory for season %s", season)
        return None

    csv_files = sorted(events_dir.glob("*.csv"))
    if not csv_files:
        log.warning("No event CSVs for season %s", season)
        return None

    # Initialise counts
    scored = {label: 0 for label in BIN_LABELS}
    conceded = {label: 0 for label in BIN_LABELS}

    for fp in csv_files:
        try:
            _process_match_file(fp, team, scored, conceded)
        except Exception as exc:
            log.debug("Skipping %s: %s", fp.name, exc)
            continue

    # Build result DataFrame — always 6 rows in order
    result = pd.DataFrame({
        "bin": BIN_LABELS,
        "scored": [scored[b] for b in BIN_LABELS],
        "conceded": [conceded[b] for b in BIN_LABELS],
    })
    return result


def _process_match_file(
    fp: Path,
    team: str,
    scored: dict[str, int],
    conceded: dict[str, int],
) -> None:
    """Process a single match CSV and update scored/conceded dicts.

    Determines whether the team played in this match, then for each goal:
    - If the team scored it (accounting for own goals) → increment scored
    - If the team conceded it → increment conceded
    """
    # Quick check from filename: does this team feature?
    stem = fp.stem
    parts = stem.split("_")
    if len(parts) < 4:
        return

    home_csv = parts[1]
    away_csv = parts[2]
    home_canonical = canonical_name(home_csv)
    away_canonical = canonical_name(away_csv)

    if team != home_canonical and team != away_canonical:
        return  # Team not in this match

    team_is_home = (team == home_canonical)

    # Read only the columns we need
    try:
        df = pd.read_csv(
            fp,
            usecols=["type_id", "time_min", "period_id", "team_position", "own goal"],
            low_memory=False,
        )
    except (ValueError, KeyError):
        # Fallback: read all columns if usecols fails
        df = pd.read_csv(fp, low_memory=False)

    # Filter goal events
    goals = df[df["type_id"] == 16].copy()
    if goals.empty:
        return

    has_og_col = "own goal" in goals.columns
    has_position_col = "team_position" in goals.columns

    if not has_position_col:
        return  # Cannot determine home/away without team_position

    for _, g in goals.iterrows():
        try:
            minute = _effective_minute(g)
        except (ValueError, TypeError):
            continue

        bin_label = _minute_to_bin(minute)
        pos = str(g["team_position"]).strip().lower()

        # Determine if this is an own goal
        is_og = False
        if has_og_col:
            og_val = g["own goal"]
            is_og = pd.notna(og_val) and str(og_val).strip() == "Si"

        # Determine if the selected team scored or conceded this goal
        goal_by_home_side = (pos == "home")

        if is_og:
            # Own goal: credited to the opposing side
            if goal_by_home_side:
                # Home player scored own goal → away team benefits
                if team_is_home:
                    conceded[bin_label] += 1  # Team conceded
                else:
                    scored[bin_label] += 1    # Team scored (via OG)
            else:
                # Away player scored own goal → home team benefits
                if team_is_home:
                    scored[bin_label] += 1    # Team scored (via OG)
                else:
                    conceded[bin_label] += 1  # Team conceded
        else:
            # Normal goal
            if goal_by_home_side:
                if team_is_home:
                    scored[bin_label] += 1
                else:
                    conceded[bin_label] += 1
            else:
                if team_is_home:
                    conceded[bin_label] += 1
                else:
                    scored[bin_label] += 1
