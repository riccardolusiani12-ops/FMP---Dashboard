"""
Scrape Serie A average squad age from Transfermarkt.
=====================================================
Source : https://www.transfermarkt.it/serie-a/altersschnitt/wettbewerb/IT1
Seasons: 2021/2022 → 2025/2026

The "Età media" (average age) is calculated by Transfermarkt based on
minutes played — it's the weighted-average age of players who appeared
on the pitch during the season.

Output → data/external/avg_age_serie_a.csv
  Columns: team, season, avg_age
"""

from __future__ import annotations

import time
import random
import logging
from pathlib import Path

import requests
from bs4 import BeautifulSoup
import pandas as pd

# ── Settings ─────────────────────────────────────────────────────────────────
BASE_URL = (
    "https://www.transfermarkt.it/serie-a/altersschnitt/"
    "wettbewerb/IT1/saison_id/{year}"
)

SEASONS = {
    2021: "2021/2022",
    2022: "2022/2023",
    2023: "2023/2024",
    2024: "2024/2025",
    2025: "2025/2026",
}

# Transfermarkt blocks requests without a browser-like User-Agent
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.transfermarkt.it/",
}

OUTPUT_PATH = Path(__file__).resolve().parents[2] / "data" / "external" / "avg_age_serie_a.csv"

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
log = logging.getLogger(__name__)


# ── Scraper ──────────────────────────────────────────────────────────────────

def _fetch_page(url: str) -> BeautifulSoup:
    """GET a page with retry logic and return a BeautifulSoup object."""
    for attempt in range(1, 4):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "lxml")
        except requests.RequestException as exc:
            log.warning("Attempt %d failed for %s: %s", attempt, url, exc)
            time.sleep(3 * attempt)
    raise RuntimeError(f"Failed to fetch {url} after 3 attempts")


def scrape_season(year: int) -> list[dict]:
    """
    Scrape the average-age table for one season.

    Returns a list of dicts: {team, season, avg_age}
    """
    url = BASE_URL.format(year=year)
    season_label = SEASONS[year]
    log.info("Scraping %s  →  %s", season_label, url)

    soup = _fetch_page(url)

    # The age table is inside <table class="items"> on Transfermarkt
    table = soup.find("table", class_="items")
    if table is None:
        log.error("Could not find the age table for season %s", season_label)
        return []

    rows: list[dict] = []
    tbody = table.find("tbody")
    if tbody is None:
        log.error("No <tbody> in the age table for season %s", season_label)
        return []

    for tr in tbody.find_all("tr", recursive=False):
        cells = tr.find_all("td")
        if len(cells) < 5:
            continue

        # Team name — inside the first <a> with class "vereinprofil_tooltip"
        # or in the cell with class "hauptlink"
        team_link = tr.find("a", class_="vereinprofil_tooltip")
        if team_link is None:
            # Fallback: take text from the hauptlink cell
            hauptlink = tr.find("td", class_="hauptlink")
            team_name = hauptlink.get_text(strip=True) if hauptlink else None
        else:
            team_name = team_link.get_text(strip=True)

        if not team_name:
            continue

        # Average age is in the last <td> of each row
        # In compact view the columns are:
        #   [rank] | logo | team | players_used | squad_size | avg_age
        age_text = cells[-1].get_text(strip=True)

        # Transfermarkt uses comma as decimal separator (e.g. "26,3")
        try:
            avg_age = float(age_text.replace(",", "."))
        except ValueError:
            log.warning("Could not parse age '%s' for %s", age_text, team_name)
            continue

        rows.append({
            "team": team_name,
            "season": season_label,
            "avg_age": avg_age,
        })

    log.info("  → Found %d teams for %s", len(rows), season_label)
    return rows


def main() -> None:
    all_rows: list[dict] = []

    for year in sorted(SEASONS):
        rows = scrape_season(year)
        all_rows.extend(rows)
        # Polite delay between requests (2-4 s random)
        pause = round(random.uniform(2.0, 4.0), 1)
        log.info("  Sleeping %.1f s …", pause)
        time.sleep(pause)

    if not all_rows:
        log.error("No data scraped — exiting without writing CSV.")
        return

    df = pd.DataFrame(all_rows)

    # Sort nicely: season ascending, team alphabetically
    df = df.sort_values(["season", "team"]).reset_index(drop=True)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)
    log.info("Saved %d rows → %s", len(df), OUTPUT_PATH)

    # Quick preview
    print("\n" + "=" * 60)
    print(df.to_string(index=False))
    print("=" * 60)


if __name__ == "__main__":
    main()
