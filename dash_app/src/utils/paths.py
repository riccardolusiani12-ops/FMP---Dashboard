"""
Path utilities – build paths to raw data & artifacts consistently.
"""

from pathlib import Path
from typing import Optional

from src.config import RAW_DATA_DIR, OUTPUTS_DIR


def season_events_dir(season: str) -> Path:
    """Return the events directory for a given season string like '2024_2025'."""
    return RAW_DATA_DIR / f"serie_a_{season}" / "events"


def list_match_files(season: str) -> list[Path]:
    """Return sorted list of match CSV paths for a season."""
    d = season_events_dir(season)
    if not d.exists():
        return []
    return sorted(d.glob("*.csv"))


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
