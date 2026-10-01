"""
Orchestratore settimanale: Opta → CSV → precompute → commit/push.

Passi (arresto al primo errore; in quel caso niente commit né push):
   1. elenco partite giocate della stagione
   2. confronto con i CSV già presenti nella cartella raw della dash
   3. nessuna mancante → notifica "nessuna nuova partita" e fine
   4. download dei JSON mancanti
   5. conversione in CSV
   6. controlli di qualità                    (--dry-run si ferma qui)
   7. copia dei CSV nella cartella raw della dash
   8. precompute della sola stagione corrente + parquet di partita della Match
      Analysis online (data/match_events/, solo se la stagione è in
      match_analysis_seasons di seasons.toml)
   9. pytest -q
  10. commit dei soli parquet cambiati + push su origin main (salvo --no-push)
  11. notifica macOS con l'esito

Se un passo tra 7 e 10 (prima del commit) fallisce, i CSV copiati e i parquet
rigenerati vengono ripristinati, così l'esecuzione successiva riparte pulita.

Uso (dalla root del repo):
    dash_app/.venv/bin/python pipeline/run_weekly.py [--dry-run] [--no-push] [--season 2026/27]
"""

from __future__ import annotations

import argparse
import fcntl
import logging
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import (  # noqa: E402
    DASH_DIR, DASH_PYTHON, LOGS_DIR, REPO_ROOT, Season, load_match_analysis_seasons, load_season,
)
from convert import convert_file  # noqa: E402
from download import download_matches  # noqa: E402
from fetch_matches import fetch_matches, played_matches  # noqa: E402
from notify import notify  # noqa: E402
from opta_client import OptaClient  # noqa: E402
from quality import check_csvs, match_id_from_csv_name  # noqa: E402

log = logging.getLogger("pipeline")

STAMP_FILE = REPO_ROOT / "pipeline" / "_work" / ".last_success"
READY_DIR = REPO_ROOT / "data" / "ready"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
MATCH_EVENTS_DIR = REPO_ROOT / "data" / "match_events"
DATA_PATHS = ["data/ready", "data/processed", "data/match_events"]
# Il modello xG in cache viene riaddestrato dal precompute quando cambia il
# numero di CSV raw (comportamento esistente della dash, src/analytics/xg.py).
XG_CACHE = "data/cache/xg_model.pkl"
# Famiglie di parquet presenti in data/ready ma che nessun codice del repo
# genera più (non prodotte da precompute_serie_a): escluse dal controllo.
NOT_PRODUCED_BY_PRECOMPUTE = {"formation_positions"}
COMMIT_PREFIX = "data: add Serie A"


class StepError(Exception):
    def __init__(self, step: int, reason: str):
        super().__init__(f"passo {step}: {reason}")
        self.step = step
        self.reason = reason


# ═════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═════════════════════════════════════════════════════════════════════════════

def setup_logging() -> Path:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"run_{datetime.now():%Y%m%d_%H%M%S}.log"
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S")
    log.setLevel(logging.INFO)
    for h in (logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler(sys.stdout)):
        h.setFormatter(fmt)
        log.addHandler(h)
    return log_path


def redact(text: str) -> str:
    """Maschera eventuali credenziali negli URL (https://user:token@host)."""
    return re.sub(r"(https?://)[^/@\s]+@", r"\1***@", text)


def git(*args: str, check: bool = True) -> str:
    r = subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(redact(f"git {' '.join(args)}: {r.stderr.strip() or r.stdout.strip()}"))
    return r.stdout


def run_logged(cmd: list[str], cwd: Path) -> int:
    """Esegue un comando riversando stdout/stderr nel log, riga per riga."""
    log.info("$ %s", " ".join(cmd))
    env = dict(os.environ, PYTHONUNBUFFERED="1")
    proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1, env=env)
    assert proc.stdout is not None
    for line in proc.stdout:
        log.info("  │ %s", line.rstrip())
    return proc.wait()


def gw_label(weeks: list[str]) -> str:
    nums = sorted({int(w) for w in weeks if str(w).isdigit()})
    if not nums:
        return "GW?"
    return f"GW{nums[0]}" if len(nums) == 1 else f"GW{nums[0]}-{nums[-1]}"


def wait_for_network(host: str = "api.performfeeds.com", timeout: int = 180) -> None:
    """Al risveglio/accensione la rete può non essere ancora pronta."""
    deadline = time.time() + timeout
    while True:
        try:
            socket.create_connection((host, 443), timeout=5).close()
            return
        except OSError:
            if time.time() > deadline:
                raise
            time.sleep(10)


def last_weekly_slot(now: datetime) -> datetime:
    """Ultimo martedì alle 09:00 (orario del LaunchAgent) non successivo a now."""
    slot = (now - timedelta(days=(now.weekday() - 1) % 7)).replace(hour=9, minute=0, second=0, microsecond=0)
    return slot - timedelta(days=7) if slot > now else slot


def weekly_slot_done(now: datetime) -> bool:
    if not STAMP_FILE.exists():
        return False
    return datetime.fromtimestamp(STAMP_FILE.stat().st_mtime) >= last_weekly_slot(now)


def fallback_note(fallbacks: list[str]) -> str:
    return f" — ⚠️ API non disponibile, usato ripiego browser ({', '.join(fallbacks)})" if fallbacks else ""


def pending_pipeline_commits() -> list[str]:
    """Commit locali della pipeline non ancora pushati (es. push fallito la volta prima)."""
    git("fetch", "--quiet", "origin", "main", check=False)
    out = git("log", "--format=%s", "origin/main..HEAD", check=False).strip()
    subjects = [s for s in out.splitlines() if s]
    if subjects and all(s.startswith(COMMIT_PREFIX) for s in subjects):
        return subjects
    return []


# ═════════════════════════════════════════════════════════════════════════════
# PASSI
# ═════════════════════════════════════════════════════════════════════════════

def preflight(args) -> None:
    if not DASH_PYTHON.exists():
        raise StepError(0, f"Python della dash non trovato: {DASH_PYTHON}")
    if args.dry_run:
        return
    branch = git("rev-parse", "--abbrev-ref", "HEAD").strip()
    if branch != "main":
        raise StepError(0, f"branch corrente '{branch}', attesa 'main'")
    if git("diff", "--cached", "--name-only").strip():
        raise StepError(0, "ci sono file già in staging: la pipeline committa solo i propri parquet")
    dirty = [l for l in git("status", "--porcelain", "--", *DATA_PATHS, XG_CACHE).splitlines()
             if not l.startswith("??")]
    if dirty:
        raise StepError(0, f"modifiche non committate in {', '.join(DATA_PATHS)} o {XG_CACHE} ({len(dirty)} file)")


def step_missing(season: Season, client: OptaClient, fallbacks: list[str]):
    try:
        df = fetch_matches(season, client)
    except Exception as e:
        raise StepError(1, f"elenco partite non disponibile ({e})")
    if (df["source"] == "results_page").any():
        fallbacks.append("elenco partite")
    played = played_matches(df)
    log.info("[1] %s: %d partite in calendario, %d giocate", season.label, len(df), len(played))

    existing = set()
    if season.raw_events_dir.exists():
        existing = {match_id_from_csv_name(p) for p in season.raw_events_dir.glob("*.csv")}
    missing = played[~played["match_id"].isin(existing)].reset_index(drop=True)
    log.info("[2] già nella dash: %d — mancanti: %d", len(existing), len(missing))
    for _, r in missing.iterrows():
        log.info("      GW%-2s %s – %s (%s)", r["week"], r["home"], r["away"], r["match_id"])
    return missing


def step_precompute(season: Season, started: float) -> None:
    # Solo la stagione corrente: altrimenti il parquet giocatori non verrebbe
    # rigenerato (precompute_season_players_if_needed lo salta se esiste).
    player_parquet = READY_DIR / f"player_season_{season.key}.parquet"
    if player_parquet.exists():
        log.info("[8] rimuovo %s per forzarne la rigenerazione", player_parquet.name)
        player_parquet.unlink()

    rc = run_logged([str(DASH_PYTHON), "-m", "src.analytics.precompute_serie_a", season.key], DASH_DIR)
    if rc != 0:
        raise StepError(8, f"precompute terminato con codice {rc}")

    # Ogni famiglia di parquet presente per le altre stagioni deve essere stata
    # (ri)scritta per questa stagione durante questo run.
    families = set()
    for p in READY_DIR.glob("*_20[0-9][0-9]_20[0-9][0-9].parquet"):
        families.add(p.name[: -len("_2025_2026.parquet")])
    families -= NOT_PRODUCED_BY_PRECOMPUTE
    expected = [READY_DIR / f"{f}_{season.key}.parquet" for f in sorted(families)]
    expected.append(PROCESSED_DIR / f"matches_{season.key}.parquet")
    stale = [p.name for p in expected if not p.exists() or p.stat().st_mtime < started]
    if stale:
        raise StepError(8, f"parquet non rigenerati: {', '.join(stale)}")
    log.info("[8] precompute OK: %d parquet rigenerati", len(expected))

    # Fingerprint del meccanismo "stale data" dell'app, solo dopo un precompute riuscito.
    n = len(list(season.raw_events_dir.glob("*.csv")))
    (READY_DIR / f".csv_count_{season.key}").write_text(str(n))
    log.info("[8] .csv_count_%s = %d", season.key, n)


def step_match_events(season: Season, started: float) -> None:
    """Parquet di partita per la Match Analysis online, solo per la stagione corrente."""
    if season.key not in load_match_analysis_seasons():
        log.info("[8] %s non è in match_analysis_seasons: nessun parquet di partita", season.label)
        return
    rc = run_logged([str(DASH_PYTHON), "-m", "src.utils.match_events", "export", "--season", season.key],
                    DASH_DIR)
    if rc != 0:
        raise StepError(8, f"export dei parquet di partita terminato con codice {rc}")
    out_dir = MATCH_EVENTS_DIR / season.key
    published = {p.stem for p in out_dir.glob("*.parquet")}
    missing = [p.name for p in season.raw_events_dir.glob("*.csv") if p.stem not in published]
    if missing:
        raise StepError(8, f"parquet di partita mancanti: {', '.join(sorted(missing))}")
    new = sum(1 for p in out_dir.glob("*.parquet") if p.stat().st_mtime >= started)
    log.info("[8] match events %s: %d nuovi parquet (%d pubblicati)", season.key, new, len(published))


def rollback(season: Season, copied: list[Path], created_raw_dir: bool, started: float,
             csv_count_backup, xg_cache_clean: bool) -> None:
    log.warning("↩️  Ripristino dello stato precedente …")
    for p in copied:
        p.unlink(missing_ok=True)
    if created_raw_dir:
        # Una cartella raw vuota farebbe comparire la stagione nell'app.
        for d in (season.raw_events_dir, season.raw_events_dir.parent):
            if d.exists() and not any(d.iterdir()):
                d.rmdir()
    # parquet tracciati → versione committata; non tracciati creati in questo run → rimossi
    for rel in DATA_PATHS:  # uno per volta: un percorso non tracciato non blocca gli altri
        git("checkout", "--", rel, check=False)
    if xg_cache_clean:
        git("checkout", "--", XG_CACHE, check=False)
    # file non tracciati creati in questo run (parquet, sidecar k_table.json)
    for rel in git("ls-files", "--others", "--", *DATA_PATHS, check=False).splitlines():
        p = REPO_ROOT / rel
        if p.is_file() and p.stat().st_mtime >= started and not p.name.startswith(".csv_count_"):
            p.unlink()
    path, content = csv_count_backup
    if content is None:
        path.unlink(missing_ok=True)
    else:
        path.write_text(content)


def committable(rel: str, season: Season) -> bool:
    """Parquet, fingerprint .csv_count della stagione e modello xG in cache."""
    return rel.endswith(".parquet") or rel in (f"data/ready/.csv_count_{season.key}", XG_CACHE)


def step_commit(season: Season, gw: str, push: bool) -> str:
    changed = []
    # -uall: i file di una cartella nuova (es. data/match_events/<nuova stagione>/)
    # vanno elencati uno per uno, non come cartella.
    for line in git("status", "--porcelain", "--untracked-files=all", "--", *DATA_PATHS, XG_CACHE).splitlines():
        rel = line[3:].strip()
        if committable(rel, season):
            changed.append(rel)
    if not any(r.endswith(".parquet") for r in changed):
        raise StepError(10, "nessun parquet cambiato dopo il precompute")
    try:
        # -f: xg_model.pkl è tracciato ma sta in data/cache/, cartella gitignorata;
        # la lista contiene solo file ammessi da committable().
        git("add", "-f", "--", *changed)
        staged = git("diff", "--cached", "--name-only").split()
        bad = [f for f in staged if not committable(f, season)]
        if bad:
            git("reset", "--quiet", "--", *staged, check=False)
            raise StepError(10, f"file non ammessi in staging: {bad}")
        msg = f"{COMMIT_PREFIX} {season.label} {gw}"
        git("commit", "--quiet", "-m", msg)
    except RuntimeError as e:
        git("reset", "--quiet", check=False)
        raise StepError(10, f"commit non riuscito ({e})")
    log.info("[10] commit: %s (%d file: %s)", msg, len(changed),
             ", ".join(r for r in changed if not r.endswith(".parquet")) + " + parquet")
    if push:
        git("push", "--quiet", "origin", "main")
        log.info("[10] push su origin main OK")
    return msg


# ═════════════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════════════

def run(args) -> int:
    started = time.time()
    season = load_season(args.season)
    log.info("══ Pipeline settimanale %s %s%s ══", season.label,
             "(dry-run)" if args.dry_run else "", " (no-push)" if args.no_push else "")

    if args.catch_up and weekly_slot_done(datetime.now()):
        # Avvio al login/accensione: il controllo settimanale è già stato fatto.
        log.info("Catch-up: controllo settimanale già eseguito dopo %s — niente da fare",
                 f"{last_weekly_slot(datetime.now()):%a %d/%m %H:%M}")
        notify(f"ℹ️ {season.label}: nessuna nuova partita (controllo settimanale già eseguito)")
        return 0

    preflight(args)
    if args.wait_network:
        try:
            wait_for_network()
        except OSError as e:
            raise StepError(1, f"rete non disponibile ({e})")

    client = OptaClient(season.outlet_key)
    fallbacks = args.fallbacks  # ripieghi browser usati: riportati nella notifica

    # 1–2
    missing = step_missing(season, client, fallbacks)

    # 3
    if missing.empty:
        extra = ""
        if not args.dry_run and not args.no_push:
            pending = pending_pipeline_commits()
            if pending:
                try:
                    git("push", "--quiet", "origin", "main")
                    extra = f" (pubblicati {len(pending)} commit in sospeso)"
                    log.info("[3] push dei commit in sospeso: %s", pending)
                except RuntimeError as e:
                    raise StepError(10, f"push dei commit in sospeso fallito ({e})")
        notify(f"ℹ️ {season.label}: nessuna nuova partita{extra}{fallback_note(fallbacks)}")
        return 0

    gw = gw_label(missing["week"].astype(str).tolist())

    # 4
    stats: dict = {}
    try:
        json_paths = download_matches(season, client, list(zip(missing["match_id"], missing["url_match"])),
                                      stats=stats)
        if stats.get("browser"):
            fallbacks.append(f"download di {stats['browser']} partite")
    except Exception as e:
        if stats.get("browser"):
            fallbacks.append(f"download di {stats['browser']} partite")
        raise StepError(4, f"download: {e}")
    log.info("[4] JSON pronti: %d", len(json_paths))

    # 5
    season.csv_dir.mkdir(parents=True, exist_ok=True)
    csv_paths = []
    for jp in json_paths:
        try:
            csv_paths.append(convert_file(jp, season.csv_dir))
        except Exception as e:
            raise StepError(5, f"conversione di {jp.name}: {e}")
    log.info("[5] CSV pronti: %d", len(csv_paths))

    # 6
    try:
        check_csvs(csv_paths, set(missing["match_id"]), season.raw_events_dir)
    except Exception as e:
        raise StepError(6, f"controlli qualità: {e}")
    log.info("[6] controlli qualità OK")

    if args.dry_run:
        log.info("Dry-run: %d partite (%s) verrebbero caricate. Nessuna copia, nessun commit.", len(csv_paths), gw)
        notify(f"🧪 Dry-run {season.label} {gw}: {len(csv_paths)} partite pronte da caricare{fallback_note(fallbacks)}")
        return 0

    # 7–9 con ripristino in caso di errore
    created_raw_dir = not season.raw_events_dir.exists()
    count_file = READY_DIR / f".csv_count_{season.key}"
    csv_count_backup = (count_file, count_file.read_text() if count_file.exists() else None)
    xg_cache_clean = not git("status", "--porcelain", "--", XG_CACHE).strip()
    copied: list[Path] = []
    try:
        season.raw_events_dir.mkdir(parents=True, exist_ok=True)
        for p in csv_paths:
            dest = season.raw_events_dir / p.name
            shutil.copy2(p, dest)
            copied.append(dest)
        log.info("[7] copiati %d CSV in %s", len(copied), season.raw_events_dir.relative_to(REPO_ROOT))

        step_precompute(season, started)
        step_match_events(season, started)

        rc = run_logged([str(DASH_PYTHON), "-m", "pytest", "-q"], DASH_DIR)
        if rc != 0:
            raise StepError(9, f"pytest fallito (codice {rc})")
        log.info("[9] pytest verde")
    except BaseException:
        rollback(season, copied, created_raw_dir, started, csv_count_backup, xg_cache_clean)
        raise

    # 10
    try:
        step_commit(season, gw, push=not args.no_push)
    except StepError:
        rollback(season, copied, created_raw_dir, started, csv_count_backup, xg_cache_clean)
        raise
    except RuntimeError as e:
        # commit locale riuscito ma push fallito: resta in sospeso e verrà
        # ritentato alla prossima esecuzione.
        raise StepError(10, f"push fallito, commit locale in sospeso ({e})")

    # 11
    published = "caricate" + ("" if args.no_push else " e pubblicate")
    notify(f"✅ {season.label} {gw}: {len(csv_paths)} nuove partite {published}{fallback_note(fallbacks)}")
    log.info("Fatto in %.0f s", time.time() - started)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Pipeline dati settimanale Serie A")
    ap.add_argument("--dry-run", action="store_true", help="fino ai controlli di qualità, senza copiare né committare")
    ap.add_argument("--no-push", action="store_true", help="committa ma non fa push")
    ap.add_argument("--season", help="es. 2026/27 (default: current_season in seasons.toml)")
    ap.add_argument("--wait-network", action="store_true", help="attende la rete fino a 3 minuti (uso da launchd)")
    ap.add_argument("--catch-up", action="store_true",
                    help="esegue solo se il controllo dell'ultimo martedì 09:00 non è ancora stato fatto (uso da launchd)")
    args = ap.parse_args()
    args.fallbacks = []

    log_path = setup_logging()
    lock_path = REPO_ROOT / "pipeline" / "_work" / ".run.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = open(lock_path, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log.error("Un'altra esecuzione è già in corso")
        return 1

    try:
        rc = run(args)
        if rc == 0 and not args.dry_run:
            STAMP_FILE.touch()
        return rc
    except StepError as e:
        log.error("❌ Errore al %s", e)
        notify(f"❌ Errore al passo {e.step}: {e.reason[:120]} — vedi log{fallback_note(args.fallbacks)}",
               subtitle=log_path.name)
        return 1
    except Exception as e:
        log.exception("❌ Errore inatteso")
        notify(f"❌ Errore inatteso: {str(e)[:120]} — vedi log", subtitle=log_path.name)
        return 1
    finally:
        log.info("Log: %s", log_path)
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()


if __name__ == "__main__":
    sys.exit(main())
