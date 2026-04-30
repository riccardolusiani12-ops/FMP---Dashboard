"""
Team mapping utilities.

Central registry that maps:
  - team display names  →  logo filenames
  - team CSV names      →  display names
  - season folders      →  team lists

Easy to maintain: just add new teams or aliases here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from src.config import LOGOS_DIR, RAW_DATA_DIR


# ── Master team registry ─────────────────────────────────────────────────────
# Keys   = canonical display name (title case, short)
# Values = logo filename (without extension)
TEAM_LOGO_MAP: dict[str, str] = {
    "Atalanta":     "atalanta",
    "Bologna":      "bologna",
    "Cagliari":     "cagliari",
    "Como":         "como",
    "Cremonese":    "cremonese",
    "Empoli":       "empoli",
    "Fiorentina":   "fiorentina",
    "Frosinone":    "frosinone",
    "Genoa":        "genoa",
    "Hellas Verona":"hellasverona",
    "Inter":        "inter",
    "Juventus":     "juventus",
    "Lazio":        "lazio",
    "Lecce":        "lecce",
    "Milan":        "milan",
    "Monza":        "monza",
    "Napoli":       "napoli",
    "Parma":        "parma",
    "Pisa":         "pisa",
    "Roma":         "roma",
    "Salernitana":  "salernitana",
    "Sampdoria":    "sampdoria",
    "Sassuolo":     "sassuolo",
    "Spezia":       "spezia",
    "Torino":       "torino",
    "Udinese":      "udinese",
    "Venezia":      "venezia",
}

# ── CSV name aliases ──────────────────────────────────────────────────────────
# Match-event CSVs use short names like "Verona", "Inter", etc.
# This maps CSV aliases → canonical display name.
_CSV_ALIASES: dict[str, str] = {
    "Verona":       "Hellas Verona",
    "Inter":        "Inter",
    "Milan":        "Milan",
    "Roma":         "Roma",
    "Lazio":        "Lazio",
    "Napoli":       "Napoli",
    "Juventus":     "Juventus",
    "Atalanta":     "Atalanta",
    "Fiorentina":   "Fiorentina",
    "Bologna":      "Bologna",
    "Torino":       "Torino",
    "Genoa":        "Genoa",
    "Lecce":        "Lecce",
    "Empoli":       "Empoli",
    "Udinese":      "Udinese",
    "Cagliari":     "Cagliari",
    "Monza":        "Monza",
    "Sassuolo":     "Sassuolo",
    "Salernitana":  "Salernitana",
    "Sampdoria":    "Sampdoria",
    "Frosinone":    "Frosinone",
    "Como":         "Como",
    "Parma":        "Parma",
    "Venezia":      "Venezia",
    "Cremonese":    "Cremonese",
    "Spezia":       "Spezia",
    "Pisa":         "Pisa",
    # Long-form names from Opta data
    "Bologna FC 1909":   "Bologna",
    "Udinese Calcio":    "Udinese",
    "Hellas Verona FC":  "Hellas Verona",
    "Hellas Verona":     "Hellas Verona",
    "SSC Napoli":        "Napoli",
    "AC Milan":          "Milan",
    "AS Roma":           "Roma",
    "SS Lazio":          "Lazio",
    "FC Internazionale": "Inter",
    "Internazionale":    "Inter",
    "Juventus FC":       "Juventus",
    "US Lecce":          "Lecce",
    "ACF Fiorentina":    "Fiorentina",
    "Torino FC":         "Torino",
    "Genoa CFC":         "Genoa",
    "US Salernitana 1919": "Salernitana",
    "AC Monza":          "Monza",
    "US Sassuolo Calcio": "Sassuolo",
    "Frosinone Calcio":  "Frosinone",
    "Cagliari Calcio":   "Cagliari",
    "Atalanta BC":       "Atalanta",
    "Empoli FC":         "Empoli",
    "Parma Calcio 1913": "Parma",
    "Venezia FC":        "Venezia",
    "Como 1907":         "Como",
    "US Cremonese":      "Cremonese",
    "Pisa SC":           "Pisa",
    "Spezia Calcio":     "Spezia",
    "UC Sampdoria":      "Sampdoria",
    # Additional Opta long-form names
    "FC Internazionale Milano": "Inter",
    "Pisa Sporting Club":       "Pisa",
    "Atalanta Bergamasca Calcio": "Atalanta",
    "Calcio Como 1907":         "Como",
}


def canonical_name(raw_name: str) -> str:
    """Return canonical display name for any known alias."""
    return _CSV_ALIASES.get(raw_name, raw_name)


def logo_filename(team: str) -> str:
    """Return the logo filename (e.g. 'bologna.png') for a canonical team name."""
    canon = canonical_name(team)
    slug = TEAM_LOGO_MAP.get(canon, canon.lower().replace(" ", ""))
    return f"{slug}.png"


def logo_url(team: str) -> str:
    """Return the Dash asset URL path for a team's logo."""
    return f"/assets/logos/{logo_filename(team)}"


def teams_for_season(season: str) -> list[str]:
    """
    Discover teams that played in a season by scanning match-event CSV filenames.
    Returns sorted list of canonical display names.
    """
    events_dir = RAW_DATA_DIR / f"serie_a_{season}" / "events"
    if not events_dir.exists():
        return []

    teams: set[str] = set()
    for csv_file in events_dir.glob("*.csv"):
        parts = csv_file.stem.split("_")
        if len(parts) >= 3:
            home = parts[1]
            away = parts[2]
            teams.add(canonical_name(home))
            teams.add(canonical_name(away))

    return sorted(teams)


def team_slug(team: str) -> str:
    """Return a URL-safe slug for a team name."""
    return canonical_name(team).lower().replace(" ", "-")


def team_from_slug(slug: str) -> Optional[str]:
    """Reverse-lookup: URL slug → canonical team name."""
    for name in TEAM_LOGO_MAP:
        if name.lower().replace(" ", "-") == slug:
            return name
    return None
