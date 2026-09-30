"""
Download dei JSON matchevent → pipeline/_work/<stagione>/json/

Metodo principale: chiamata diretta a PerformFeeds
(`4_direct download try.ipynb`).
Ripiego: Chrome via Selenium 4 (vedi browser_headless in seasons.toml) che apre la pagina /player-stats e
intercetta la risposta matchevent più pesante via log di rete CDP
(stessa logica "heaviest" di `3_json download large scale.ipynb`, senza
selenium-wire).

Formato salvato: come lo script 3 — wrapper JSONP rimosso, JSON indentato
(indent=4, ensure_ascii=False), nome `<week>_<Home>_<Away>_<match_id>.json`.
Le partite già presenti (qualsiasi file che termina con `_<match_id>.json`)
vengono saltate.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse

from config import Season
from opta_client import OptaClient, extract_inner_json_str_from_raw

log = logging.getLogger("pipeline")

URL_REGEX = re.compile(
    r"https://api\.performfeeds\.com/soccerdata/.*matchevent.*",
    re.IGNORECASE,
)
SCORESWAY_BASE = "https://www.scoresway.com"
TIMEOUT_SEC_PER_MATCH = 35
SLEEP_BETWEEN_MATCHES = 1.2


# ═════════════════════════════════════════════════════════════════════════════
# HELPERS (da script 3)
# ═════════════════════════════════════════════════════════════════════════════

def decode_body(body: bytes) -> str:
    return body.decode("utf-8", errors="ignore").lstrip("﻿").strip()


def match_id_from_raw(raw: str, fallback_url: str) -> str:
    try:
        inner = extract_inner_json_str_from_raw(raw)
        obj = json.loads(inner)
        mid = (obj.get("matchInfo", {}) or {}).get("id")
        if mid:
            return str(mid)
    except Exception:
        pass

    p = urlparse(fallback_url)
    parts = [x for x in p.path.split("/") if x]
    for i, part in enumerate(parts):
        if part.lower() == "matchevent" and i + 1 < len(parts):
            return parts[i + 1]
    return "unknown_match"


def match_id_from_matchevent_url(u: str) -> str:
    try:
        p = urlparse(u)
        parts = [x for x in p.path.split("/") if x]
        for i, part in enumerate(parts):
            if part.lower() == "matchevent" and i + 2 < len(parts):
                return parts[i + 2]
    except Exception:
        pass
    return ""


def normalize_scoresway_url(u: str) -> str:
    u = (u or "").strip()
    if not u:
        return ""
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("/"):
        return SCORESWAY_BASE + u
    return u


def to_player_stats_url(match_url: str) -> str:
    match_url = normalize_scoresway_url(match_url)
    if not match_url:
        return ""
    match_url = match_url.split("#")[0]
    if "?" in match_url:
        match_url = match_url.split("?")[0]
    if match_url.rstrip("/").endswith("/player-stats"):
        return match_url
    return match_url.rstrip("/") + "/player-stats"


def already_downloaded_for_match(out_dir: str | Path, match_id: str) -> bool:
    """Check if ANY file in out_dir ends with _{match_id}.json"""
    return any(
        f.endswith(f"_{match_id}.json")
        for f in os.listdir(out_dir)
        if f.endswith(".json")
    )


def build_rich_filename(raw_text: str, perform_id: str) -> str:
    """
    Build filename <week>_<Home>_<Away>_<perform_id>.json
    by parsing matchInfo from the JSON body.
    Falls back to <perform_id>.json if parsing fails.
    """
    try:
        inner = extract_inner_json_str_from_raw(raw_text)
        obj = json.loads(inner)
        mi = obj.get("matchInfo", {})

        # Week / matchday
        week = str(mi.get("week", "0")).strip()
        if not week or week.lower() == "none":
            week = "0"

        # Contestants
        contestants = {c["position"]: c["name"] for c in mi.get("contestant", [])}
        home = contestants.get("home", "UNK")
        away = contestants.get("away", "UNK")

        # Filesystem-safe names (keep only letters, numbers)
        home = re.sub(r"[^A-Za-z0-9]+", "", home) or "UNK"
        away = re.sub(r"[^A-Za-z0-9]+", "", away) or "UNK"

        return f"{week}_{home}_{away}_{perform_id}.json"
    except Exception:
        return f"{perform_id}.json"


def unique_path(path: str) -> str:
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    for k in range(2, 200):
        cand = f"{base}_{k}{ext}"
        if not os.path.exists(cand):
            return cand
    return f"{base}_{int(time.time())}{ext}"


def save_match_json(raw_text: str, expected_mid: str, out_dir: Path) -> Path:
    """
    Valida la risposta (matchInfo.id atteso, eventi presenti) e la salva nel
    formato dello script 3. Solleva ValueError se la risposta non è valida.
    """
    inner_json_str = extract_inner_json_str_from_raw(raw_text)
    json_obj = json.loads(inner_json_str)

    raw_mid = (json_obj.get("matchInfo", {}) or {}).get("id")
    if raw_mid != expected_mid:
        raise ValueError(f"matchInfo.id={raw_mid!r} diverso dall'atteso {expected_mid!r}")
    events = (json_obj.get("liveData", {}) or {}).get("event", []) or []
    if not events:
        raise ValueError("liveData.event vuoto")

    filename = build_rich_filename(raw_text, raw_mid)
    final_path = Path(unique_path(str(out_dir / filename)))
    with open(final_path, "w", encoding="utf-8") as f:
        json.dump(json_obj, f, indent=4, ensure_ascii=False)
    return final_path


# ═════════════════════════════════════════════════════════════════════════════
# METODO PRINCIPALE — download diretto
# ═════════════════════════════════════════════════════════════════════════════

def download_direct(client: OptaClient, match_id: str, out_dir: Path) -> Path:
    raw_text = client.get_raw("matchevent", match_id)
    return save_match_json(raw_text, match_id, out_dir)


# ═════════════════════════════════════════════════════════════════════════════
# RIPIEGO — Chrome (Selenium 4) + log di rete CDP
# ═════════════════════════════════════════════════════════════════════════════

def _capture_heaviest_matchevent(driver, player_stats_url: str, expected_mid: str) -> str | None:
    driver.get_log("performance")  # svuota il buffer dalle pagine precedenti
    driver.get(player_stats_url)

    # small scroll
    try:
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(0.4)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.6);")
        time.sleep(0.6)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.15);")
    except Exception:
        pass

    candidates: dict[str, str] = {}   # requestId → url
    best = {"size": -1, "body": None}
    done: set[str] = set()

    start = time.time()
    while time.time() - start < TIMEOUT_SEC_PER_MATCH:
        for entry in driver.get_log("performance"):
            msg = json.loads(entry["message"])["message"]
            method, params = msg.get("method"), msg.get("params", {})
            if method == "Network.responseReceived":
                url = params.get("response", {}).get("url", "")
                if URL_REGEX.search(url):
                    mid_in_url = match_id_from_matchevent_url(url)
                    if expected_mid and mid_in_url and mid_in_url != expected_mid:
                        continue
                    log.info("      🔗 API request: %s", url)
                    candidates[params["requestId"]] = url
            elif method == "Network.loadingFinished":
                rid = params.get("requestId")
                if rid in candidates and rid not in done:
                    done.add(rid)
                    try:
                        res = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": rid})
                    except Exception:
                        continue
                    body = res.get("body", "")
                    body_bytes = base64.b64decode(body) if res.get("base64Encoded") else body.encode("utf-8")
                    if len(body_bytes) > best["size"]:
                        best = {"size": len(body_bytes), "body": body_bytes}
        # Uscita anticipata: risposta trovata e nessuna richiesta pendente
        if best["body"] is not None and done >= set(candidates) and time.time() - start > 8:
            break
        time.sleep(0.35)

    if best["body"] is None:
        return None
    return decode_body(best["body"])


def download_via_browser(match_ids_urls: list[tuple[str, str]], out_dir: Path,
                         headless: bool = True) -> dict[str, Path | Exception]:
    from browser import create_driver

    results: dict[str, Path | Exception] = {}
    driver = create_driver(headless=headless, performance_log=True)
    try:
        for i, (mid, match_url) in enumerate(match_ids_urls, start=1):
            url = to_player_stats_url(match_url)
            log.info("  [browser %d/%d] %s", i, len(match_ids_urls), url)
            try:
                raw = _capture_heaviest_matchevent(driver, url, mid)
                if not raw:
                    raise RuntimeError("nessuna risposta matchevent intercettata")
                results[mid] = save_match_json(raw, mid, out_dir)
            except Exception as e:
                results[mid] = e
            time.sleep(SLEEP_BETWEEN_MATCHES)
    finally:
        driver.quit()
    return results


# ═════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═════════════════════════════════════════════════════════════════════════════

def download_matches(season: Season, client: OptaClient, matches: list[tuple[str, str]],
                     use_fallback: bool = True, stats: dict | None = None) -> list[Path]:
    """
    matches: lista (match_id, url_match). Ritorna i percorsi JSON di tutte le
    partite richieste (scaricate ora o già presenti). Solleva RuntimeError se
    anche il ripiego non recupera tutte le partite. Se `stats` è un dict, vi
    scrive "browser": numero di partite per cui è stato usato il ripiego.
    """
    out_dir = season.json_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    failed: list[tuple[str, str]] = []
    for i, (mid, url) in enumerate(matches, start=1):
        if already_downloaded_for_match(out_dir, mid):
            log.info("  [%d/%d] ⏭️  già scaricata: %s", i, len(matches), mid)
            continue
        try:
            path = download_direct(client, mid, out_dir)
            log.info("  [%d/%d] ✅ %s", i, len(matches), path.name)
        except Exception as e:
            log.warning("  [%d/%d] ❌ download diretto fallito per %s: %s", i, len(matches), mid, e)
            failed.append((mid, url))

    if failed and use_fallback:
        log.warning("Ripiego browser per %d partite", len(failed))
        if stats is not None:
            stats["browser"] = len(failed)
        res = download_via_browser(failed, out_dir, headless=season.browser_headless)
        still = [(mid, r) for mid, r in res.items() if isinstance(r, Exception)]
        for mid, r in res.items():
            if not isinstance(r, Exception):
                log.info("  ✅ (browser) %s", r.name)
        failed = [(mid, "") for mid, _ in still]
        for mid, err in still:
            log.error("  ❌ ripiego browser fallito per %s: %s", mid, err)

    if failed:
        raise RuntimeError(f"{len(failed)} partite non scaricate: {', '.join(m for m, _ in failed)}")

    return [find_json_for_match(out_dir, mid) for mid, _ in matches]


def find_json_for_match(out_dir: Path, match_id: str) -> Path:
    hits = sorted(p for p in out_dir.glob(f"*_{match_id}.json"))
    if not hits:
        raise FileNotFoundError(f"JSON non trovato per {match_id}")
    return hits[0]
