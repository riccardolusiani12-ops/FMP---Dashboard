"""
Calcio Italiano — Application-wide configuration.
All paths are relative to the project root (dash_app/).
"""

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
AVAILABLE_SEASONS: list[str] = sorted(
    [
        d.name.replace("serie_a_", "")
        for d in RAW_DATA_DIR.glob("serie_a_*")
        if d.is_dir()
    ]
)

# ── UI constants ──────────────────────────────────────────────────────────────
APP_TITLE: Final[str] = "Calcio Italiano"
APP_SUBTITLE: Final[str] = "Serie A Analytics Dashboard"
PRIMARY_COLOR: Final[str] = "#8a1f33"  # Deep red
SECONDARY_COLOR: Final[str] = "#1b2838"  # Dark navy

# ── Debug ─────────────────────────────────────────────────────────────────────
import os
DEBUG: Final[bool] = os.getenv("DEBUG", "false").lower() in ("1", "true", "yes")