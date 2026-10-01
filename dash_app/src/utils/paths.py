"""
Path utilities – build paths to raw data & artifacts consistently.
"""

from pathlib import Path
from typing import Optional

from src.config import AVAILABLE_SEASONS, MATCH_EVENTS_DIR, RAW_DATA_DIR, OUTPUTS_DIR


def season_events_dir(season: str) -> Path:
    """Return the events directory for a given season string like '2024_2025'."""
    return RAW_DATA_DIR / f"serie_a_{season}" / "events"


def list_match_files(season: str) -> list[Path]:
    """Return sorted list of match CSV paths for a season."""
    d = season_events_dir(season)
    if not d.exists():
        return []
    return sorted(d.glob("*.csv"))


# ── Match Analysis sources ────────────────────────────────────────────────────
# Locally the Match Analysis lists the raw CSVs, as above. Without data/raw/
# (git-based deploy, Render) it falls back to the per-match parquets published
# in data/match_events/<season>/ (same file stems) — see src/utils/match_events.py.
# list_match_files() itself is unchanged: season-level analytics also use it.

def published_match_files(season: str) -> list[Path]:
    """Return sorted published per-match parquet paths for a season."""
    d = MATCH_EVENTS_DIR / season
    if not d.exists():
        return []
    return sorted(d.glob("*.parquet"))


def match_analysis_files(season: str) -> list[Path]:
    """Match files for the Match Analysis: raw CSVs if present, else published parquets."""
    if season_events_dir(season).exists():
        return list_match_files(season)
    return published_match_files(season)


def match_analysis_seasons() -> list[str]:
    """Seasons the Match Analysis can open (all of them when data/raw/ is present)."""
    return [s for s in AVAILABLE_SEASONS if match_analysis_files(s)]


def parse_match_filename(path: Path) -> dict:
    """
    Parse a match CSV filename into components.
    Pattern: {week}_{HomeTeam}_{AwayTeam}_{matchId}.csv
    Returns dict with keys: week, home, away, match_id, label
    """
    stem = path.stem
    parts = stem.split("_")
    if len(parts) < 4:
        return {"week": "?", "home": "?", "away": "?", "match_id": stem, "label": stem}
    week = parts[0]
    home = parts[1]
    away = parts[2]
    match_id = "_".join(parts[3:])
    label = f"GW{week} {home}–{away}"
    return {
        "week": week,
        "home": home,
        "away": away,
        "match_id": match_id,
        "label": label,
    }


def artifact_path(
    season: str,
    analysis: str,
    team: Optional[str] = None,
    match_id: Optional[str] = None,
    filename: str = "",
) -> Path:
    """
    Build a standardised artifact path.
    outputs/{season}/{analysis}/{team}/{match_id}/{filename}
    or simpler subsets when team/match_id are omitted.
    """
    p = OUTPUTS_DIR / season / analysis
    if team:
        p = p / team
    if match_id:
        p = p / match_id
    if filename:
        p = p / filename
    return p
