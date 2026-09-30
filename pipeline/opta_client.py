"""
Client HTTP per api.performfeeds.com (stesso stile del widget Scoresway).

Header, parametri JSONP e token di callback sono quelli di
`4_direct download try.ipynb`. Scraping rispettoso: una richiesta alla volta
(nessun parallelismo) e pausa casuale 0.5–1.5 s tra una richiesta e l'altra.
"""

from __future__ import annotations

import json
import logging
import random
import time

import requests

log = logging.getLogger("pipeline")

API_BASE = "https://api.performfeeds.com/soccerdata"
REQUEST_TIMEOUT = 30
SLEEP_MIN = 0.5
SLEEP_MAX = 1.5
MAX_ATTEMPTS = 3

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-GB,en;q=0.9",
    "Referer": "https://www.scoresway.com/",
    "Origin": "https://www.scoresway.com",
    "Connection": "keep-alive",
}

DEFAULT_PARAMS = {
    "_rt": "c",
    "_lcl": "en",
    "_fmt": "jsonp",
    "sps": "widgets",
}


def make_callback_token(prefix: str = "W", n_hex: int = 40) -> str:
    # Stesso stile del widget: W + 40 caratteri esadecimali
    hexchars = "0123456789abcdef"
    return prefix + "".join(random.choice(hexchars) for _ in range(n_hex))


def extract_inner_json_str_from_raw(raw: str) -> str:
    """
    Restituisce la sottostringa JSON ({...} o [...]) contenuta in raw (JSON o JSONP).
    Identica a `3_json download large scale.ipynb`.
    """
    raw = raw.strip()
    if not raw:
        raise ValueError("Empty raw body")

    first = next((ch for ch in raw if not ch.isspace()), "")
    if first in ("{", "["):
        return raw

    start_obj = raw.find("{")
    start_arr = raw.find("[")
    candidates = [pos for pos in (start_obj, start_arr) if pos != -1]
    if not candidates:
        raise ValueError("No JSON object/array found inside raw")

    start = min(candidates)
    opening = raw[start]
    closing = "}" if opening == "{" else "]"
    end = raw.rfind(closing)
    if end == -1 or end <= start:
        raise ValueError("No valid closing bracket found")

    return raw[start : end + 1]


class OptaClient:
    """Sessione requests con pausa di cortesia tra richieste consecutive."""

    def __init__(self, outlet_key: str):
        self.outlet_key = outlet_key
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self._last_request: float | None = None

    def _polite_pause(self) -> None:
        if self._last_request is not None:
            time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))

    def get_raw(self, endpoint: str, path_id: str | None = None, **params) -> str:
        """
        GET {API_BASE}/{endpoint}/{outlet}[/{path_id}] in formato JSONP.
        Ritorna il testo grezzo; solleva RuntimeError dopo MAX_ATTEMPTS fallimenti.
        """
        url = f"{API_BASE}/{endpoint}/{self.outlet_key}"
        if path_id:
            url += f"/{path_id}"

        last_error = ""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            self._polite_pause()
            query = dict(DEFAULT_PARAMS, **params)
            query["_clbk"] = make_callback_token()
            try:
                r = self.session.get(url, params=query, timeout=REQUEST_TIMEOUT)
                self._last_request = time.time()
                text = r.text or ""
                if r.status_code == 200 and text.strip() and not text.lstrip().startswith("<"):
                    log.debug("GET %s → HTTP 200, %d bytes", url, len(r.content))
                    return text
                last_error = f"HTTP {r.status_code}, {len(r.content)} bytes"
            except requests.RequestException as e:
                self._last_request = time.time()
                last_error = f"{type(e).__name__}: {e}"
            log.warning("  tentativo %d/%d fallito per %s: %s", attempt, MAX_ATTEMPTS, url, last_error)
            time.sleep(2 * attempt)

        raise RuntimeError(f"{url}: {last_error}")

    def get_json(self, endpoint: str, path_id: str | None = None, **params):
        raw = self.get_raw(endpoint, path_id, **params)
        return raw, json.loads(extract_inner_json_str_from_raw(raw))
