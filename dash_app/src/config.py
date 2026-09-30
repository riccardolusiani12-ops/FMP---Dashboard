"""
Calcio Italiano — Application-wide configuration.
All paths are relative to the project root (dash_app/).
"""

import re
from pathlib import Path
from typing import Final

# ── Paths ──────────────────────────────────────────────────────────────────────
PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent.parent  # dash_app/
REPO_ROOT: Final[Path] = PROJECT_ROOT.parent  # FMP_SerieA_Dashboard/

DATA_DIR: Final[Path] = REPO_ROOT / "data"
RAW_DATA_DIR: Final[Path] = DATA_DIR / "raw"
PROCESSED_DATA_DIR: Final[Path] = DATA_DIR / "processed"
READY_DATA_DIR: Final[Path] = DATA_DIR / "ready"
CACHE_DIR: Final[Path] = DATA_DIR / "cache"
EXTERNAL_DATA_DIR: Final[Path] = DATA_DIR / "external"

OUTPUTS_DIR: Final[Path] = REPO_ROOT / "outputs"
MANIFEST_PATH: Final[Path] = OUTPUTS_DIR / "manifest.json"
FIGURES_DIR: Final[Path] = OUTPUTS_DIR / "figures"
REPORTS_DIR: Final[Path] = OUTPUTS_DIR / "reports"

LOGOS_SRC_DIR: Final[Path] = REPO_ROOT / "docs" / "logos" / "seriea"
LOGOS_DIR: Final[Path] = PROJECT_ROOT / "assets" / "logos"

LOGS_DIR: Final[Path] = PROJECT_ROOT / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE: Final[Path] = LOGS_DIR / "app.log"

ASSETS_DIR: Final[Path] = PROJECT_ROOT / "assets"

# ── Defaults ───────────────────────────────────────────────────────────────────
DEFAULT_TEAM: Final[str] = "Bologna"
DEFAULT_SEASON: Final[str] = "2024_2025"
DEFAULT_COMPETITION: Final[str] = "Serie A"

# ── Cache ─────────────────────────────────────────────────────────────────────
CACHE_TTL: Final[int] = 3600  # seconds — 1 hour

# ── Available seasons (folder names under data/raw/) ──────────────────────────
def discover_seasons(raw_dir: Path, ready_dir: Path) -> list[str]:
    """
    Season keys ("2025_2026"), chronological.

    Locally they come from the raw folders data/raw/serie_a_*. On a git-based
    deploy (Render) data/raw/ is not versioned, so fall back to the seasons that
    have a precomputed standings_<season>.parquet in data/ready/.
    """
    raw = sorted(
        d.name.replace("serie_a_", "")
        for d in raw_dir.glob("serie_a_*")
        if d.is_dir()
    )
    if raw:
        return raw
    return sorted(
        p.stem.replace("standings_", "")
        for p in ready_dir.glob("standings_*.parquet")
        if re.fullmatch(r"\d{4}_\d{4}", p.stem.replace("standings_", ""))
    )


AVAILABLE_SEASONS: list[str] = discover_seasons(RAW_DATA_DIR, READY_DATA_DIR)

# ── UI constants ──────────────────────────────────────────────────────────────
APP_TITLE: Final[str] = "Calcio Italiano"
APP_SUBTITLE: Final[str] = "Serie A Analytics Dashboard"
PRIMARY_COLOR: Final[str] = "#8a1f33"  # Deep red
SECONDARY_COLOR: Final[str] = "#1b2838"  # Dark navy

# ── Debug ─────────────────────────────────────────────────────────────────────
import os
DEBUG: Final[bool] = os.getenv("DEBUG", "false").lower() in ("1", "true", "yes")