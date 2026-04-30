"""
Serie A Data Loader — Fast access to precomputed ready tables.
===============================================================
Provides clean functions for callbacks to load precomputed data
instead of scanning raw CSV files.

All functions return DataFrames loaded from Parquet.
If a ready table is missing, falls back to computing on the fly
and caches the result for subsequent calls.

Functions:
  - load_season_teams(season)          → list of team names
  - load_standings(season)             → standings table
  - load_team_overview(team, season)   → team KPI row
  - load_points_progression(season)    → per-team cumulative points
  - load_all_points_progression()      → all-season points progression
  - load_ppda_summary(season)          → PPDA + regain metrics
  - load_league_summary()             → all-season standings
  - load_formation_counts(team, season) → top formations for a team
  - load_xg_summary(season)           → xG/xGC per team for a season
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

import pandas as pd

from src.config import READY_DATA_DIR, PROCESSED_DATA_DIR, AVAILABLE_SEASONS
from src.utils.logging import log


# ═══════════════════════════════════════════════════════════════════════════════
# LOW-LEVEL PARQUET READER (cached)
# ═══════════════════════════════════════════════════════════════════════════════

@lru_cache(maxsize=64)
def _read_parquet(path_str: str) -> Optional[pd.DataFrame]:
    """
    Read a Parquet file and cache the result in memory.
    Returns None if the file doesn't exist or is corrupted/unreadable.
    Uses path as string for lru_cache hashability.
    """
    p = Path(path_str)
    if not p.exists():
        return None
    try:
        return pd.read_parquet(p)
    except Exception as exc:
        log.error("Failed to read Parquet %s: %s", path_str, exc)
        return None


def _is_readable_parquet(path: Path) -> bool:
    """
    Return True only if the Parquet file exists **and** can be opened by
    pyarrow without error.  Catches corrupted files (e.g. histogram size
    mismatch) that pass a simple ``path.exists()`` check.
    """
    if not path.exists():
        return False
    try:
        pd.read_parquet(path, columns=[])  # schema-only read — fast
        return True
    except Exception:
        log.warning("Corrupted Parquet detected — will regenerate: %s", path)
        return False


def invalidate_cache() -> None:
    """Clear the in-memory Parquet cache (e.g. after re-preprocessing)."""
    _read_parquet.cache_clear()


# ═══════════════════════════════════════════════════════════════════════════════
# SEASON TEAMS
# ═══════════════════════════════════════════════════════════════════════════════

def load_season_teams(season: str) -> list[str]:
    """
    Return sorted list of canonical team names for a season.
    Loads from ready table; falls back to standings table.
    """
    # Try ready table first
    df = _read_parquet(str(READY_DATA_DIR / f"season_teams_{season}.parquet"))
    if df is not None and not df.empty:
        return sorted(df["Team"].tolist())

    # Fallback: extract from standings
    df = _read_parquet(str(READY_DATA_DIR / f"standings_{season}.parquet"))
    if df is not None and not df.empty:
        return sorted(df["Team"].unique().tolist())

    # Final fallback: scan raw files (slow path)
    log.warning("No ready table for season teams %s — falling back to raw scan", season)
    from src.team_mapping import teams_for_season as _raw_teams_for_season
    return _raw_teams_for_season(season)


# ═══════════════════════════════════════════════════════════════════════════════
# STANDINGS
# ═══════════════════════════════════════════════════════════════════════════════

def load_standings(season: str) -> pd.DataFrame:
    """
    Load the league standings table for a season.
    Columns: Season, Team, MP, W, D, L, GF, GA, GD, Points, Rank
    """
    df = _read_parquet(str(READY_DATA_DIR / f"standings_{season}.parquet"))
    if df is not None:
        return df

    # Fallback: compute from raw
    log.warning("No ready standings for %s — computing from raw", season)
    from src.analytics.multi_season_standings import load_season_matches, compute_standings
    matches = load_season_matches(season)
    if matches.empty:
        return pd.DataFrame()
    standings = compute_standings(matches)
    standings["Rank"] = standings.groupby("Season").cumcount() + 1
    return standings


def load_season_matches_cached(season: str) -> pd.DataFrame:
    """
    Load all match results for a season with caching.
    Tries precomputed Parquet first, then falls back to computing from raw CSVs.
    
    Returns
    -------
    pd.DataFrame with columns: Season, Matchday, Home, Away, HG, AG, Date, File
    
    Optimization: Uses points_progression Parquet when available, as it contains
    match-level data and is much faster to load than raw CSV parsing.
    """
    # First try: dedicated matches Parquet (if it exists)
    matches_path = str(READY_DATA_DIR / f"matches_{season}.parquet")
    df = _read_parquet(matches_path)
    if df is not None:
        return df
    
    # Second try: extract from points_progression Parquet (fastest path)
    # Points progression contains one row per team per match, with MatchLabel containing scores
    pp_path = str(READY_DATA_DIR / f"points_progression_{season}.parquet")
    pp_df = _read_parquet(pp_path)
    if pp_df is not None and not pp_df.empty:
        # Extract unique matches from points_progression
        matches = []
        seen = set()
        
        for _, row in pp_df.iterrows():
            try:
                # MatchLabel format: "Home-Away score" e.g., "Lecce-Atalanta 0-4"
                label = str(row.get("MatchLabel", ""))
                if not label or " " not in label:
                    continue
                
                # Split into teams and score
                teams_part, score_part = label.rsplit(" ", 1)
                if "-" not in score_part or "-" not in teams_part:
                    continue
                
                # Parse score
                try:
                    hg, ag = map(int, score_part.split("-"))
                except (ValueError, TypeError):
                    continue
                
                # Find team split (last dash before score)
                # We need to find where the team names end and score begins
                # The format is "Home-Away score" but team names might have special chars
                # Use the fact that score is digits-digits pattern
                parts = teams_part.split("-")
                if len(parts) < 2:
                    continue
                
                # Reconstruct: last part is away team, rest is home
                away = parts[-1].strip()
                home = "-".join(parts[:-1]).strip()
                
                matchday = int(row["Matchday"])
                match_key = (matchday, home, away)
                
                if match_key not in seen:
                    seen.add(match_key)
                    matches.append({
                        "Season": row["Season"],
                        "Matchday": matchday,
                        "Home": home,
                        "Away": away,
                        "HG": hg,
                        "AG": ag,
                        "Date": "",
                        "File": "",
                    })
            except Exception:
                continue
        
        if matches:
            result_df = pd.DataFrame(matches)
            return result_df.sort_values(["Matchday", "Home"]).reset_index(drop=True)
    
    # Fallback: compute from raw event CSVs (slow path)
    log.warning("No cached match data for %s — computing from raw", season)
    from src.analytics.multi_season_standings import load_season_matches
    return load_season_matches(season)


# ═══════════════════════════════════════════════════════════════════════════════
# TEAM OVERVIEW (KPIs)
# ═══════════════════════════════════════════════════════════════════════════════

def load_team_overview(team: str, season: str) -> Optional[pd.Series]:
    """
    Load KPI overview for a specific team in a season.
    Returns a single row (pd.Series) or None if not found.
    """
    df = _read_parquet(str(READY_DATA_DIR / f"team_overview_{season}.parquet"))
    if df is not None and not df.empty:
        row = df[df["Team"] == team]
        if not row.empty:
            return row.iloc[0]

    # Fallback: derive from standings
    standings = load_standings(season)
    if standings.empty:
        return None
    row = standings[standings["Team"] == team]
    if row.empty:
        return None
    return row.iloc[0]


# ═══════════════════════════════════════════════════════════════════════════════
# POINTS PROGRESSION
# ═══════════════════════════════════════════════════════════════════════════════

def load_points_progression(season: str) -> pd.DataFrame:
    """
    Load per-team cumulative points progression for a season.
    Columns: Season, Matchday, Team, GF, GA, MatchPoints,
             CumulativePoints, MatchLabel, Result
    """
    df = _read_parquet(str(READY_DATA_DIR / f"points_progression_{season}.parquet"))
    if df is not None:
        return df

    # Fallback
    log.warning("No ready points progression for %s — computing from raw", season)
    from src.analytics.multi_season_standings import load_season_matches, compute_points_progression
    matches = load_season_matches(season)
    if matches.empty:
        return pd.DataFrame()
    return compute_points_progression(matches)


def load_all_points_progression() -> pd.DataFrame:
    """
    Load points progression across all seasons.
    Uses the combined file if available; otherwise merges per-season files.
    """
    # Try combined file first
    df = _read_parquet(str(READY_DATA_DIR / "points_progression_all.parquet"))
    if df is not None:
        return df

    # Merge per-season files
    frames = []
    for season in AVAILABLE_SEASONS:
        sdf = load_points_progression(season)
        if not sdf.empty:
            frames.append(sdf)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


# ═══════════════════════════════════════════════════════════════════════════════
# PPDA
# ═══════════════════════════════════════════════════════════════════════════════

def load_ppda_summary(season: str) -> pd.DataFrame:
    """
    Load the PPDA + regain metrics table for a season.
    Columns: team, team_short, PPDA, passes_allowed, ball_recoveries,
             matches, ppda_std, n_regains, mean_seconds, median_seconds,
             rank, Season
    """
    df = _read_parquet(str(READY_DATA_DIR / f"ppda_{season}.parquet"))
    if df is not None:
        return df

    # Fallback: compute from raw (slow)
    log.warning("No ready PPDA table for %s — computing from raw", season)
    from src.analytics.ppda import build_ppda_table
    ppda_df = build_ppda_table(season)
    if not ppda_df.empty:
        ppda_df["Season"] = season.replace("_", "/")
    return ppda_df


# ═══════════════════════════════════════════════════════════════════════════════
# LEAGUE SUMMARY (cross-season)
# ═══════════════════════════════════════════════════════════════════════════════

def load_league_summary() -> pd.DataFrame:
    """
    Load standings across all seasons.
    Uses the combined file if available; otherwise merges per-season files.
    """
    df = _read_parquet(str(READY_DATA_DIR / "league_summary.parquet"))
    if df is not None:
        return df

    # Merge per-season files
    frames = []
    for season in AVAILABLE_SEASONS:
        sdf = load_standings(season)
        if not sdf.empty:
            frames.append(sdf)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


# ═══════════════════════════════════════════════════════════════════════════════
# READINESS CHECK
# ═══════════════════════════════════════════════════════════════════════════════

def check_ready_data(season: str) -> dict[str, bool]:
    """
    Check which ready tables exist **and are readable** for a given season.
    Returns a dict of table name → readable boolean.
    Corrupted Parquets that fail to open are treated as missing.
    """
    tables = {
        "standings": READY_DATA_DIR / f"standings_{season}.parquet",
        "points_progression": READY_DATA_DIR / f"points_progression_{season}.parquet",
        "team_overview": READY_DATA_DIR / f"team_overview_{season}.parquet",
        "ppda": READY_DATA_DIR / f"ppda_{season}.parquet",
        "season_teams": READY_DATA_DIR / f"season_teams_{season}.parquet",
    }
    return {name: _is_readable_parquet(path) for name, path in tables.items()}


def _raw_data_is_newer(season: str) -> bool:
    """
    Return True if the raw event CSVs for a season have changed since the
    precomputed standings Parquet was last generated.

    Checks three signals:
      1. Whether the reference Parquet is corrupted / unreadable
      2. Whether the newest CSV file is more recent than the Parquet file
      3. Whether the CSV file count changed (handles files copied with old mtimes)

    A lightweight fingerprint file (.csv_count) is stored next to each
    season's Parquet to track the last-known CSV count.
    """
    from src.config import RAW_DATA_DIR

    events_dir = RAW_DATA_DIR / f"serie_a_{season}" / "events"
    parquet_ref = READY_DATA_DIR / f"standings_{season}.parquet"

    if not events_dir.exists():
        return False

    # If the reference Parquet is missing or corrupted → must refresh
    if not _is_readable_parquet(parquet_ref):
        return True

    csv_files = list(events_dir.glob("*.csv"))
    if not csv_files:
        return False

    # Signal 1: mtime comparison
    newest_csv_mtime = max(f.stat().st_mtime for f in csv_files)
    parquet_mtime = parquet_ref.stat().st_mtime
    if newest_csv_mtime > parquet_mtime:
        return True

    # Signal 2: CSV count comparison
    count_file = READY_DATA_DIR / f".csv_count_{season}"
    current_count = len(csv_files)
    if count_file.exists():
        try:
            stored_count = int(count_file.read_text().strip())
            if current_count != stored_count:
                return True
        except (ValueError, OSError):
            return True  # corrupted → safer to refresh
    else:
        # First time: store count, no refresh needed (parquet exists)
        try:
            count_file.write_text(str(current_count))
        except OSError:
            pass

    return False


def ensure_ready_data(season: str) -> bool:
    """
    Ensure precomputed tables for a season are present **and fresh**.

    Triggers recomputation if:
      - any key Parquet table is missing, OR
      - the raw event CSVs are newer than the existing Parquets
        (i.e. new matchday files were uploaded since last precompute)

    Returns True if recomputation was triggered, False otherwise.
    """
    status = check_ready_data(season)
    missing = [k for k, v in status.items() if not v]

    stale = False
    if not missing:
        stale = _raw_data_is_newer(season)

    if missing:
        log.info("Missing ready tables for %s: %s — running preprocessing", season, missing)
    elif stale:
        log.info("Raw data is newer than precomputed tables for %s — refreshing", season)
    else:
        log.debug("Ready data for %s is up-to-date", season)
        return False

    from src.analytics.precompute_serie_a import precompute_season
    precompute_season(season)
    # Clear the in-memory Parquet cache so next reads pick up fresh data
    invalidate_cache()

    # Update the CSV count fingerprint
    from src.config import RAW_DATA_DIR
    events_dir = RAW_DATA_DIR / f"serie_a_{season}" / "events"
    if events_dir.exists():
        csv_count = len(list(events_dir.glob("*.csv")))
        count_file = READY_DATA_DIR / f".csv_count_{season}"
        try:
            count_file.write_text(str(csv_count))
        except OSError:
            pass

    return True


# ═══════════════════════════════════════════════════════════════════════════════
# FORMATIONS
# ═══════════════════════════════════════════════════════════════════════════════

def load_formation_counts(team: str, season: str, min_count: int = 3) -> pd.DataFrame:
    """
    Load formation usage counts for a team in a season.

    Tries precomputed Parquet first; falls back to computing from raw CSVs.
    Returns DataFrame with columns: formation_str, count, pct
    (top 3 formations with >= min_count uses).
    """
    # Try precomputed table
    parquet_path = READY_DATA_DIR / f"formations_{season}.parquet"
    df = _read_parquet(str(parquet_path))
    if df is not None and not df.empty and "team" in df.columns:
        team_df = df[df["team"] == team].copy()
        if not team_df.empty:
            # Apply threshold and return top 3
            team_df = team_df[team_df["count"] >= min_count]
            team_df = team_df.sort_values("count", ascending=False).head(3)
            return team_df[["formation_str", "count", "pct"]].reset_index(drop=True)

    # Fallback: compute from raw
    log.warning("No precomputed formations for %s/%s — computing from raw", team, season)
    from src.analytics.formations import compute_formation_counts
    return compute_formation_counts(season, team, min_count=min_count)


# ═══════════════════════════════════════════════════════════════════════════════
# xG SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════

def load_xg_summary(season: str) -> pd.DataFrame:
    """
    Load xG summary for all teams in a season.

    Tries precomputed Parquet first; falls back to computing from raw CSVs.
    Returns DataFrame with columns: Team, Season, GF, GA, xG, xGC, xG_diff, Shots, ShotsAgainst
    """
    parquet_path = READY_DATA_DIR / f"xg_{season}.parquet"
    df = _read_parquet(str(parquet_path))
    if df is not None and not df.empty:
        return df

    # Fallback: compute from raw
    log.warning("No precomputed xG for %s — computing from raw", season)
    from src.analytics.xg import compute_team_xg_summary
    return compute_team_xg_summary(season)


# ═══════════════════════════════════════════════════════════════════════════════
# GOAL DISTRIBUTION (15-minute bins)
# ═══════════════════════════════════════════════════════════════════════════════

def load_goal_distribution(team: str, season: str) -> pd.DataFrame:
    """
    Load goal distribution per 15-minute window for a team in a season.

    Tries precomputed Parquet first; falls back to computing from raw CSVs.
    Returns DataFrame with columns: bin, scored, conceded
    (always 6 rows, one per 15-minute window).
    """
    # Try precomputed table
    parquet_path = READY_DATA_DIR / f"goal_distribution_{season}.parquet"
    df = _read_parquet(str(parquet_path))
    if df is not None and not df.empty and "team" in df.columns:
        team_df = df[df["team"] == team].copy()
        if not team_df.empty:
            return team_df[["bin", "scored", "conceded"]].reset_index(drop=True)

    # Fallback: compute from raw
    log.info("Computing goal distribution for %s/%s from raw events", team, season)
    from src.analytics.goal_distribution import compute_goal_distribution
    result = compute_goal_distribution(season, team)
    if result is not None:
        return result
    return pd.DataFrame(columns=["bin", "scored", "conceded"])


# ═══════════════════════════════════════════════════════════════════════════════
# AVERAGE AGE (from Transfermarkt scrape)
# ═══════════════════════════════════════════════════════════════════════════════

@lru_cache(maxsize=1)
def _load_avg_age_csv() -> Optional[pd.DataFrame]:
    """
    Load average age CSV (scraped from Transfermarkt).
    Cached in memory. Returns None if file doesn't exist.
    """
    # data_loader.py is at: dash_app/src/analytics/data_loader.py
    # CSV is at: data/external/avg_age_serie_a.csv (project root)
    # So we need to go: dash_app/src/analytics → ../../.. → project root → data/external
    csv_path = Path(__file__).resolve().parents[3] / "data" / "external" / "avg_age_serie_a.csv"
    
    if not csv_path.exists():
        return None
    
    try:
        return pd.read_csv(csv_path)
    except Exception as exc:
        log.warning("Failed to load average age CSV: %s", exc)
        return None


def load_team_average_age(team: str, season: str) -> Optional[float]:
    """
    Load the average age for a specific team in a season.
    
    Parameters
    ----------
    team : str
        Canonical team name (e.g. 'Bologna')
    season : str
        Season key like '2024_2025'
    
    Returns
    -------
    float or None
        Average age, or None if not found
    """
    df = _load_avg_age_csv()
    if df is None or df.empty:
        return None
    
    # Convert season_key format (2024_2025 → 2024/2025)
    season_label = season.replace("_", "/") if season else ""
    
    # The CSV has columns: team, season, avg_age
    # Team names in CSV differ from canonical names, so we need to map
    # Mapping from canonical → CSV names
    canonical_to_csv = {
        "Atalanta": "Atalanta",
        "Bologna": "Bologna FC",
        "Cagliari": "Cagliari Calcio",
        "Como": "Como 1907",
        "Cremonese": "US Cremonese",
        "Empoli": "Empoli FC",
        "Fiorentina": "ACF Fiorentina",
        "Frosinone": "Frosinone Calcio",
        "Genoa": "Genoa CFC",
        "Hellas Verona": "Hellas Verona",
        "Inter": "Inter",
        "Juventus": "Juventus FC",
        "Lazio": "SS Lazio",
        "Lecce": "US Lecce",
        "Milan": "AC Milan",
        "Monza": "AC Monza",
        "Napoli": "SSC Napoli",
        "Parma": "Parma Calcio",
        "Pisa": "Pisa Sporting Club",
        "Roma": "AS Roma",
        "Salernitana": "US Salernitana",
        "Sampdoria": "UC Sampdoria",
        "Sassuolo": "US Sassuolo",
        "Spezia": "Spezia Calcio",
        "Torino": "Torino FC",
        "Udinese": "Udinese Calcio",
        "Venezia": "Venezia FC",
    }
    
    # Get CSV team name
    csv_team = canonical_to_csv.get(team)
    if csv_team is None:
        log.warning("Team mapping not found for canonical name: %s", team)
        return None
    
    # Find the row
    match = df[
        (df["season"] == season_label) &
        (df["team"] == csv_team)
    ]
    
    if not match.empty:
        return float(match.iloc[0]["avg_age"])
    
    return None

