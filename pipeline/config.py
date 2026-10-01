"""
Loader di seasons.toml → oggetto Season con tutti i percorsi risolti.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PIPELINE_DIR.parent
DASH_DIR = REPO_ROOT / "dash_app"
DASH_PYTHON = DASH_DIR / ".venv" / "bin" / "python"
LOOKUPS_DIR = PIPELINE_DIR / "opta_lookups"
LOGS_DIR = PIPELINE_DIR / "logs"
SEASONS_FILE = PIPELINE_DIR / "seasons.toml"


@dataclass(frozen=True)
class Season:
    key: str                     # "2026_2027" — stesso formato di data/raw/serie_a_<key>
    label: str                   # "2026/27"
    tournament_calendar_id: str
    results_url: str
    outlet_key: str
    competition_id: str
    raw_events_dir: Path         # cartella raw della dash
    work_dir: Path               # pipeline/_work/<key>/
    browser_headless: bool       # ripieghi Selenium: headless o finestra visibile

    @property
    def json_dir(self) -> Path:
        return self.work_dir / "json"

    @property
    def csv_dir(self) -> Path:
        return self.work_dir / "csv"

    @property
    def matches_csv(self) -> Path:
        return self.work_dir / f"matches_{self.key}.csv"

    @property
    def match_url_base(self) -> str:
        """Base degli URL partita Scoresway, es. .../serie-a-2026-2027/<tmcl>"""
        return self.results_url.rsplit("/results", 1)[0]


def normalize_season_key(value: str) -> str:
    """'2026/27', '2026/2027', '2026-27', '2026_2027' → '2026_2027'."""
    v = value.strip().replace("/", "_").replace("-", "_")
    start, _, end = v.partition("_")
    if not (start.isdigit() and end.isdigit() and len(start) == 4):
        raise ValueError(f"Stagione non valida: {value!r}")
    if len(end) == 2:
        end = start[:2] + end
    return f"{start}_{end}"


def load_match_analysis_seasons() -> list[str]:
    """Stagioni con la Match Analysis pubblicata online (match_analysis_seasons)."""
    with open(SEASONS_FILE, "rb") as f:
        cfg = tomllib.load(f)
    return [normalize_season_key(s) for s in cfg["defaults"].get("match_analysis_seasons", [])]


def load_season(season: str | None = None) -> Season:
    with open(SEASONS_FILE, "rb") as f:
        cfg = tomllib.load(f)
    defaults = cfg["defaults"]
    key = normalize_season_key(season or defaults["current_season"])
    seasons = cfg.get("seasons", {})
    if key not in seasons:
        raise KeyError(
            f"Stagione {key} non configurata in {SEASONS_FILE.name} "
            f"(disponibili: {', '.join(sorted(seasons)) or 'nessuna'})"
        )
    s = seasons[key]
    return Season(
        key=key,
        label=s["label"],
        tournament_calendar_id=s["tournament_calendar_id"],
        results_url=s["results_url"],
        outlet_key=s.get("outlet_key", defaults["outlet_key"]),
        competition_id=s.get("competition_id", defaults["competition_id"]),
        raw_events_dir=REPO_ROOT / s["raw_events_dir"],
        work_dir=REPO_ROOT / defaults["work_dir"] / key,
        browser_headless=bool(defaults.get("browser_headless", False)),
    )
