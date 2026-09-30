"""
Elenco partite della stagione → pipeline/_work/<stagione>/matches_<stagione>.csv

Metodo principale: API PerformFeeds `soccerdata/match?tmcl=<stagione>`
(una sola richiesta, niente browser; restituisce anche stato e giornata).

Ripiego: scraping della pagina risultati Scoresway con Selenium 4,
logica di `2_match url scraping.ipynb` (lettura di #Opta_0 + BeautifulSoup).

Colonne in uscita: quelle dello script 2 (date, match_id, url_match, home,
away, home_score, away_score) + week, status, source.
"""

from __future__ import annotations

import logging
import time

import pandas as pd

from config import Season
from opta_client import OptaClient

log = logging.getLogger("pipeline")

COLUMNS = ["date", "match_id", "url_match", "home", "away",
           "home_score", "away_score", "week", "status", "source"]
PAGE_SIZE = 400  # una stagione di Serie A = 380 partite


# ═════════════════════════════════════════════════════════════════════════════
# METODO PRINCIPALE — API
# ═════════════════════════════════════════════════════════════════════════════

def fetch_via_api(season: Season, client: OptaClient) -> pd.DataFrame:
    _, payload = client.get_json("match", tmcl=season.tournament_calendar_id, _pgSz=PAGE_SIZE)
    matches = payload.get("match", []) or []
    if len(matches) >= PAGE_SIZE:
        raise RuntimeError(f"API match: {len(matches)} partite, possibile paginazione incompleta")

    rows = []
    for m in matches:
        mi = m.get("matchInfo", {}) or {}
        md = (m.get("liveData", {}) or {}).get("matchDetails", {}) or {}
        if (mi.get("tournamentCalendar", {}) or {}).get("id") != season.tournament_calendar_id:
            continue
        contestants = {c.get("position"): c.get("name", "") for c in mi.get("contestant", []) or []}
        total = (md.get("scores", {}) or {}).get("total", {}) or {}
        rows.append({
            "date": mi.get("date", ""),
            "match_id": mi.get("id", ""),
            "url_match": f"{season.match_url_base}/match/view/{mi.get('id', '')}",
            "home": contestants.get("home", ""),
            "away": contestants.get("away", ""),
            "home_score": total.get("home", ""),
            "away_score": total.get("away", ""),
            "week": mi.get("week", ""),
            "status": md.get("matchStatus", ""),
            "source": "api",
        })
    return pd.DataFrame(rows, columns=COLUMNS)


# ═════════════════════════════════════════════════════════════════════════════
# RIPIEGO — pagina risultati Scoresway (script 2)
# ═════════════════════════════════════════════════════════════════════════════

TIMEOUT = 60


def try_click_cookies(driver, timeout=3):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    candidates = [
        "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accept')]",
        "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'agree')]",
        "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'consent')]",
        "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZÁÉÍÓÚÜ', 'abcdefghijklmnopqrstuvwxyzáéíóúü'), 'aceptar')]",
        "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZÁÉÍÓÚÜ', 'abcdefghijklmnopqrstuvwxyzáéíóúü'), 'permitir')]",
    ]
    for xp in candidates:
        try:
            el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((By.XPATH, xp)))
            el.click()
            time.sleep(1)
            return True
        except Exception:
            pass
    return False


def warmup_scroll(driver):
    # Triggers lazy-load for the Opta widget
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(0.4)
    for frac in (0.25, 0.55, 0.85, 1.0):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight * arguments[0]);", frac)
        time.sleep(0.9)


def wait_opta_ready(driver, timeout=TIMEOUT):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    # Wait until Opta_0 exists and contains match links (Match page)
    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.ID, "Opta_0"))
    )
    WebDriverWait(driver, timeout).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, "#Opta_0 a.Opta-MatchLink")) > 0
    )


def parse_opta0_html(opta_html: str):
    """
    Parses ALL HTML inside #Opta_0 exactly as rendered
    (without changing matchdays) and extracts the matches displayed.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(opta_html, "lxml")

    rows = []
    current_date = None

    for table in soup.select("table.Opta-Crested"):
        for tb in table.select("tbody"):
            # Date (separator block)
            title_td = tb.select_one("td.Opta-title h4 span")
            if title_td:
                current_date = title_td.get_text(strip=True)
                continue

            classes = tb.get("class", []) or []
            if "Opta-fixture" not in classes:
                continue

            # Match URL (Match page)
            a = tb.select_one("a.Opta-MatchLink")
            url = (a.get("href") or "").strip() if a else ""
            if not url:
                continue

            # Preferred match_id: data-match
            match_id = (tb.get("data-match") or "").strip()
            if not match_id:
                if "/match/view/" in url:
                    match_id = url.split("/match/view/")[-1].split("?")[0].strip()
                else:
                    match_id = url.rstrip("/").split("/")[-1]

            # Teams and score (if present)
            home = away = ""
            home_score = away_score = ""

            home_a = tb.select_one("tr.Opta-Scoreline td.Opta-Team.Opta-Home a.Opta-TeamLink")
            away_a = tb.select_one("tr.Opta-Scoreline td.Opta-Team.Opta-Away a.Opta-TeamLink")
            if home_a:
                home = home_a.get_text(strip=True)
            if away_a:
                away = away_a.get_text(strip=True)

            hs = tb.select_one("td.Opta-Score.Opta-Home span.Opta-Team-Score")
            aas = tb.select_one("td.Opta-Score.Opta-Away span.Opta-Team-Score")
            if hs:
                home_score = hs.get_text(strip=True)
            if aas:
                away_score = aas.get_text(strip=True)

            rows.append({
                "date": current_date,
                "match_id": match_id,
                "url_match": url,
                "home": home,
                "away": away,
                "home_score": home_score,
                "away_score": away_score,
            })

    return rows


def fetch_via_results_page(season: Season, headless: bool | None = None) -> pd.DataFrame:
    from selenium.webdriver.common.by import By

    from browser import create_driver

    driver = create_driver(headless=season.browser_headless if headless is None else headless)
    try:
        driver.get(season.results_url)
        try_click_cookies(driver, timeout=3)
        warmup_scroll(driver)
        wait_opta_ready(driver, timeout=TIMEOUT)
        opta_html = driver.find_element(By.ID, "Opta_0").get_attribute("innerHTML") or ""
        rows = parse_opta0_html(opta_html)
    finally:
        driver.quit()

    if not rows:
        raise RuntimeError("Nessuna partita estratta da #Opta_0")

    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["match_id"], keep="first")
    df = df.drop_duplicates(subset=["url_match"], keep="first")
    # La pagina risultati non espone giornata/stato: giocata = punteggio presente.
    df["week"] = ""
    df["status"] = [
        "Played" if str(h).strip() != "" and str(a).strip() != "" else "Unknown"
        for h, a in zip(df["home_score"], df["away_score"])
    ]
    df["source"] = "results_page"
    return df[COLUMNS]


# ═════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═════════════════════════════════════════════════════════════════════════════

def fetch_matches(season: Season, client: OptaClient, use_fallback: bool = True) -> pd.DataFrame:
    """Elenco completo della stagione, salvato in matches_<stagione>.csv."""
    try:
        df = fetch_via_api(season, client)
        if df.empty:
            raise RuntimeError("API match: nessuna partita restituita")
        log.info("Elenco partite via API: %d partite", len(df))
    except Exception as e:
        if not use_fallback:
            raise
        log.warning("API match fallita (%s) — ripiego sulla pagina risultati Scoresway", e)
        df = fetch_via_results_page(season)
        log.info("Elenco partite via pagina risultati: %d partite", len(df))

    season.work_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(season.matches_csv, index=False, encoding="utf-8")
    return df


def played_matches(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["status"] == "Played"].reset_index(drop=True)


if __name__ == "__main__":
    import argparse
    import sys

    from config import load_season

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description="Elenco partite di una stagione")
    ap.add_argument("--season")
    ap.add_argument("--method", choices=["api", "results_page"], default="api")
    args = ap.parse_args()
    s = load_season(args.season)
    if args.method == "api":
        out = fetch_matches(s, OptaClient(s.outlet_key), use_fallback=False)
    else:
        out = fetch_via_results_page(s)
    print(out.groupby("status").size().to_string())
    print(f"Giocate: {len(played_matches(out))}")
    sys.exit(0)
