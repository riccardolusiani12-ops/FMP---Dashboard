"""
Orchestratore settimanale: Opta → CSV → precompute → pubblicazione dati.

Passi (arresto al primo errore):
   0. verifiche preliminari: git (/usr/bin/git), dati locali coerenti con
      origin/main (a parte i dati della pipeline non ancora pubblicati)
   1. elenco partite giocate della stagione
   2. confronto con i CSV già presenti nella cartella raw della dash
   3. nessuna mancante → ritenta la pubblicazione di eventuali dati in sospeso,
      notifica "nessuna nuova partita" e fine
   4. download dei JSON mancanti
   5. conversione in CSV
   6. controlli di qualità
   7. copia dei CSV nella cartella raw della dash
   8. precompute della sola stagione corrente + parquet di partita della Match
      Analysis online (data/match_events/, solo se la stagione è in
      match_analysis_seasons di seasons.toml)
   9. pytest -q
  10. pubblicazione dei soli file della whitelist tramite il worktree dedicato
      pipeline/_work/publish (publish.py): commit di dati + push su origin main.
      Il working tree di sviluppo non viene usato né per il commit né per il push.
  11. notifica macOS con l'esito

Esiti (notifica e codice di uscita):
  ✅ nuove partite caricate e pubblicate                            → 0
  ⚠️ nuove partite caricate in locale, pubblicazione bloccata       → 2
  ℹ️ nessuna nuova partita                                          → 0
  ❌ errore al passo N                                              → 1

Se un passo tra 7 e 9 fallisce, i CSV copiati e i file della whitelist
rigenerati vengono ripristinati. Se la pubblicazione è bloccata, i dati restano
caricati in locale (registrati in _work/.pending_publish.json) e la
pubblicazione viene ritentata alla prossima esecuzione.

Uso (dalla root del repo):
    dash_app/.venv/bin/python pipeline/run_weekly.py [--dry-run] [--no-push] [--publish-only] [--season 2026/27]
"""

from __future__ import annotations

import argparse
import fcntl
import logging
import os
import shutil
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import (  # noqa: E402
    DASH_DIR, DASH_PYTHON, GIT_BIN, LOGS_DIR, PUBLISH_WORKTREE, REPO_ROOT, Season,
    load_match_analysis_seasons, load_season,
)
from convert import convert_file  # noqa: E402
from download import download_matches  # noqa: E402
from fetch_matches import fetch_matches, played_matches  # noqa: E402
from notify import notify  # noqa: E402
from opta_client import OptaClient  # noqa: E402
from publish import (  # noqa: E402
    COMMIT_PREFIX, DATA_PATHS, NOT_PRODUCED_BY_PRECOMPUTE, UPSTREAM, XG_CACHE, PublishBlocked,
    PublishResult, align_local_main, check_git_bin, clear_pending, fetch, load_pending,
    local_data_divergence, prepare_local_pull, publish, redact, run_git, save_pending, season_whitelist,
    unknown_season_outputs,
)
from quality import check_csvs, match_id_from_csv_name  # noqa: E402

log = logging.getLogger("pipeline")

STAMP_FILE = REPO_ROOT / "pipeline" / "_work" / ".last_success"
PENDING_FILE = REPO_ROOT / "pipeline" / "_work" / ".pending_publish.json"
READY_DIR = REPO_ROOT / "data" / "ready"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
MATCH_EVENTS_DIR = REPO_ROOT / "data" / "match_events"

# Soglie oltre le quali un passo viene segnalato come lento (minuti).
STEP_WARN_MINUTES = {"precompute": 60, "download": 30, "pytest": 10, "pubblicazione": 10}
DEFAULT_WARN_MINUTES = 30

EXIT_OK, EXIT_ERROR, EXIT_BLOCKED = 0, 1, 2


class StepError(Exception):
    def __init__(self, step: int, reason: str):
        super().__init__(f"passo {step}: {reason}")
        self.step = step
        self.reason = reason


@dataclass
class RunState:
    started: float = field(default_factory=time.time)
    outcome: str = "?"
    steps: list[tuple[str, float]] = field(default_factory=list)
    slow: list[str] = field(default_factory=list)
    commit_sha: str | None = None
    pushed_sha: str | None = None


STATE = RunState()


# ═════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═════════════════════════════════════════════════════════════════════════════

def setup_logging() -> Path:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"run_{datetime.now():%Y%m%d_%H%M%S}.log"
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")
    log.setLevel(logging.INFO)
    for h in (logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler(sys.stdout)):
        h.setFormatter(fmt)
        log.addHandler(h)
    return log_path


def git(*args: str, check: bool = True) -> str:
    """git (GIT_BIN) nel working tree di sviluppo; errori già ripuliti da credenziali."""
    return run_git(REPO_ROOT, *args, check=check).stdout


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


def fmt_duration(seconds: float) -> str:
    s = int(round(seconds))
    if s >= 3600:
        return f"{s // 3600}h{s % 3600 // 60:02d}m"
    if s >= 60:
        return f"{s // 60}m{s % 60:02d}s"
    return f"{s}s"


@contextmanager
def timed(step: int | str, name: str):
    """Registra la durata del passo e avvisa se supera la soglia."""
    t0 = time.time()
    try:
        yield
    finally:
        elapsed = time.time() - t0
        STATE.steps.append((f"[{step}] {name}", elapsed))
        limit = STEP_WARN_MINUTES.get(name, DEFAULT_WARN_MINUTES)
        if elapsed > limit * 60:
            STATE.slow.append(f"{name} {fmt_duration(elapsed)}")
            log.warning("[%s] ⏱️ %s lento: %s (soglia %d min) — Mac in stop durante il run?",
                        step, name, fmt_duration(elapsed), limit)
        else:
            log.info("[%s] %s: %s", step, name, fmt_duration(elapsed))


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


def slow_note() -> str:
    return f" — ⏱️ lento: {', '.join(STATE.slow)}" if STATE.slow else ""


def committable(rel: str, season: Season) -> bool:
    """Parquet, fingerprint .csv_count della stagione e modello xG in cache."""
    return rel.endswith(".parquet") or rel in (f"data/ready/.csv_count_{season.key}", XG_CACHE)


def keep_awake() -> subprocess.Popen | None:
    """caffeinate -i finché questo processo è vivo: evita lo stop per inattività
    durante il run (non basta a coperchio chiuso a batteria)."""
    caffeinate = Path("/usr/bin/caffeinate")
    if os.environ.get("PIPELINE_NO_CAFFEINATE") or not caffeinate.exists():
        return None
    try:
        return subprocess.Popen([str(caffeinate), "-i", "-w", str(os.getpid())],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as e:
        log.warning("caffeinate non avviato: %s", e)
        return None


# ═════════════════════════════════════════════════════════════════════════════
# PASSI
# ═════════════════════════════════════════════════════════════════════════════

def preflight() -> None:
    """Solo ciò che serve davvero: niente vincoli su branch o commit locali."""
    if not DASH_PYTHON.exists():
        raise StepError(0, f"Python della dash non trovato: {DASH_PYTHON}")
    try:
        check_git_bin()
    except PublishBlocked as e:
        raise StepError(0, e.reason)
    try:
        fetch(REPO_ROOT)  # repo pubblico: il fetch non usa credenziali
    except PublishBlocked as e:
        log.warning("[0] %s — confronto con l'ultimo %s noto", e.reason, UPSTREAM)

    branch = git("symbolic-ref", "--quiet", "--short", "HEAD", check=False).strip() or "HEAD detached"
    ahead = git("rev-list", "--count", f"{UPSTREAM}..HEAD", check=False).strip() or "?"
    behind = git("rev-list", "--count", f"HEAD..{UPSTREAM}", check=False).strip() or "?"
    log.info("[0] git %s — branch '%s', %s commit locali non su %s, %s indietro",
             GIT_BIN, branch, ahead, UPSTREAM, behind)

    pending = load_pending(PENDING_FILE).get("files", {})
    try:
        divergent = local_data_divergence(REPO_ROOT, pending)
    except RuntimeError as e:
        raise StepError(0, f"confronto dei dati locali con {UPSTREAM} non riuscito ({e})")
    if divergent:
        raise StepError(0, f"{len(divergent)} file dati locali diversi da {UPSTREAM} e non prodotti dalla "
                           f"pipeline (es. {divergent[0]}): allinea data/ e rilancia")
    if pending:
        log.info("[0] dati in sospeso da pubblicare: %d file (%s)", len(pending),
                 gw_label(load_pending(PENDING_FILE).get("weeks", [])))


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


@dataclass
class Snapshot:
    """Stato dei file della whitelist prima dei passi 7–9, per il ripristino."""
    dir: Path
    files: list[str]                 # whitelist (senza data/match_events)
    saved: set[str]                  # quelli che esistevano e sono stati copiati
    match_events: set[Path]          # parquet di partita già presenti


def take_snapshot(season: Season) -> Snapshot:
    snap_dir = season.work_dir / "rollback"
    shutil.rmtree(snap_dir, ignore_errors=True)
    files = season_whitelist(season.key, season.raw_events_dir, [])  # senza data/match_events
    saved = set()
    for rel in files:
        src = REPO_ROOT / rel
        if src.is_file():
            dest = snap_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            saved.add(rel)
    me = set((MATCH_EVENTS_DIR / season.key).glob("*.parquet"))
    return Snapshot(snap_dir, files, saved, me)


def rollback(season: Season, copied: list[Path], created_raw_dir: bool, snap: Snapshot) -> None:
    """Riporta CSV raw e file della whitelist allo stato precedente al passo 7.
    Non usa git: i dati su disco possono essere più recenti dell'indice (main
    locale non allineato) o in attesa di pubblicazione."""
    log.warning("↩️  Ripristino dello stato precedente …")
    for p in copied:
        p.unlink(missing_ok=True)
    if created_raw_dir:
        # Una cartella raw vuota farebbe comparire la stagione nell'app.
        for d in (season.raw_events_dir, season.raw_events_dir.parent):
            if d.exists() and not any(d.iterdir()):
                d.rmdir()
    for rel in snap.files:
        if rel in snap.saved:
            shutil.copy2(snap.dir / rel, REPO_ROOT / rel)
        else:
            (REPO_ROOT / rel).unlink(missing_ok=True)
    for p in (MATCH_EVENTS_DIR / season.key).glob("*.parquet"):
        if p not in snap.match_events:
            p.unlink()


def step_publish(season: Season, weeks: list[str], *, push: bool, dry_run: bool) -> tuple[PublishResult | None, str | None]:
    """Passo 10. Restituisce (esito, None) oppure (None, motivo del blocco)."""
    pending = load_pending(PENDING_FILE)
    all_weeks = sorted({*map(str, weeks), *pending.get("weeks", [])})
    try:
        paths = season_whitelist(season.key, season.raw_events_dir, load_match_analysis_seasons())
        paths += [p for p in pending.get("files", {}) if p not in paths]
        unknown = unknown_season_outputs(REPO_ROOT, season.key)
        if unknown:
            raise PublishBlocked(f"parquet non previsti dalla whitelist: {', '.join(unknown)} "
                                 f"(aggiungili a SEASON_FAMILIES in publish.py)")
        msg = f"{COMMIT_PREFIX} {season.label} {gw_label(all_weeks)}"
        log.info("[10] whitelist: %d path, worktree %s", len(paths), PUBLISH_WORKTREE.relative_to(REPO_ROOT))
        with timed(10, "pubblicazione"):
            res = publish(REPO_ROOT, PUBLISH_WORKTREE, paths, msg, push=push, dry_run=dry_run)
    except PublishBlocked as e:
        log.warning("[10] ⛔ pubblicazione BLOCCATA: %s", e.reason)
        return None, e.reason
    except RuntimeError as e:
        reason = f"errore git: {redact(str(e))[:200]}"
        log.warning("[10] ⛔ pubblicazione BLOCCATA: %s", reason)
        return None, reason

    log.info("[10] base %s: %s", UPSTREAM, res.base_sha)
    if res.status == "nothing":
        log.info("[10] nessuna differenza rispetto a %s: nessun commit, nessun push", UPSTREAM)
    else:
        log.info("[10] file nel commit di dati: %d\n%s", len(res.files), res.stat)
    if res.status == "dry-run":
        log.info("[10] dry-run: commit '%s' e push HEAD:main NON eseguiti", msg)
    if res.commit_sha:
        STATE.commit_sha = res.commit_sha
        log.info("[10] commit di dati: %s '%s'", res.commit_sha, msg)
    if res.status == "committed":
        log.info("[10] --no-push: commit lasciato nel worktree, nessun push")
    if res.status == "pushed":
        STATE.pushed_sha = res.pushed_sha
        if res.pushed_sha != res.commit_sha:
            log.info("[10] commit ribasato su %s avanzato", UPSTREAM)
        log.info("[10] push OK: %s %s..%s", UPSTREAM, res.base_sha[:7], res.pushed_sha)
        try:
            res.alignment = align_local_main(REPO_ROOT, res.pushed_sha)
        except RuntimeError as e:
            res.alignment = f"allineamento del main locale non riuscito: {e}"
        log.info("[10] %s", res.alignment)
    if res.status in ("pushed", "nothing") and not dry_run:
        clear_pending(PENDING_FILE)
    return res, None


# ═════════════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════════════

def finish_publish(season: Season, n_new: int, gw: str, res: PublishResult | None, blocked: str | None,
                   fallbacks: list[str], dry_run: bool) -> int:
    """Esito finale e notifica a partire dal risultato del passo 10."""
    tail = fallback_note(fallbacks) + slow_note()
    what = f"{season.label} {gw}: {n_new} nuove partite" if n_new else f"{season.label}: nessuna nuova partita"
    if dry_run:
        STATE.outcome = "dry-run"
        if blocked:
            detail = f"pubblicazione bloccata: {blocked[:90]}"
        elif res and res.status == "dry-run":
            detail = f"pubblicherebbe {len(res.files)} file"
        else:
            detail = "niente da pubblicare"
        notify(f"🧪 Dry-run {what} — {detail}{tail}")
        return EXIT_OK
    if blocked:
        STATE.outcome = "bloccato"
        if n_new:
            notify(f"⚠️ {what} caricate in locale, push BLOCCATO: {blocked[:100]}{tail}")
        else:
            notify(f"⚠️ {what}; pubblicazione dati in sospeso BLOCCATA: {blocked[:100]}{tail}")
        return EXIT_BLOCKED
    assert res is not None
    if res.status == "pushed":
        STATE.outcome = "pubblicato"
        prefix = f"✅ {what} caricate e pubblicate" if n_new else f"ℹ️ {what} (pubblicati i dati in sospeso)"
        notify(f"{prefix} ({res.pushed_sha[:7]}){tail}")
    elif res.status == "committed":
        STATE.outcome = "commit senza push"
        notify(f"✅ {what} caricate; commit dati {res.commit_sha[:7]} non pushato (--no-push){tail}")
    else:
        STATE.outcome = "nessuna novità" if not n_new else "caricato, niente da pubblicare"
        notify(f"ℹ️ {what}{' caricate, già allineate a origin/main' if n_new else ''}{tail}")
    return EXIT_OK


def run(args) -> int:
    started = STATE.started
    season = load_season(args.season)
    log.info("══ Pipeline settimanale %s%s%s%s ══", season.label,
             " (dry-run)" if args.dry_run else "", " (no-push)" if args.no_push else "",
             " (publish-only)" if args.publish_only else "")

    if args.catch_up and weekly_slot_done(datetime.now()):
        # Avvio al login/accensione: il controllo settimanale è già stato fatto.
        log.info("Catch-up: controllo settimanale già eseguito dopo %s — niente da fare",
                 f"{last_weekly_slot(datetime.now()):%a %d/%m %H:%M}")
        STATE.outcome = "catch-up: niente da fare"
        notify(f"ℹ️ {season.label}: nessuna nuova partita (controllo settimanale già eseguito)")
        return EXIT_OK

    if args.wait_network:
        try:
            wait_for_network()
        except OSError as e:
            raise StepError(1, f"rete non disponibile ({e})")
    with timed(0, "verifiche preliminari"):
        preflight()

    push = not args.no_push
    fallbacks = args.fallbacks  # ripieghi browser usati: riportati nella notifica

    if args.publish_only:
        res, blocked = step_publish(season, [], push=push, dry_run=args.dry_run)
        return finish_publish(season, 0, "", res, blocked, fallbacks, args.dry_run)

    client = OptaClient(season.outlet_key)

    # 1–2
    with timed("1-2", "elenco partite"):
        missing = step_missing(season, client, fallbacks)

    # 3 — nessuna novità: ritenta solo la pubblicazione (idempotente)
    if missing.empty:
        res, blocked = step_publish(season, [], push=push, dry_run=args.dry_run)
        return finish_publish(season, 0, "", res, blocked, fallbacks, args.dry_run)

    weeks = missing["week"].astype(str).tolist()
    gw = gw_label(weeks)

    # 4
    stats: dict = {}
    with timed(4, "download"):
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
    with timed(5, "conversione"):
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
        log.info("Dry-run: %d partite (%s) verrebbero caricate. Nessuna copia, nessun precompute.", len(csv_paths), gw)
        new_me = [f"data/match_events/{season.key}/{p.stem}.parquet" for p in csv_paths]
        if season.key in load_match_analysis_seasons():
            log.info("[10] dopo il precompute verrebbero pubblicati (se cambiati) i file della whitelist "
                     "di %s, più %d nuovi parquet di partita:\n  %s", season.label, len(new_me), "\n  ".join(new_me))
        # Anteprima della pubblicazione sullo stato attuale del disco (dati in sospeso).
        res, blocked = step_publish(season, weeks, push=False, dry_run=True)
        return finish_publish(season, len(csv_paths), gw, res, blocked, fallbacks, dry_run=True)

    # 7–9 con ripristino in caso di errore
    created_raw_dir = not season.raw_events_dir.exists()
    snap = take_snapshot(season)
    copied: list[Path] = []
    try:
        season.raw_events_dir.mkdir(parents=True, exist_ok=True)
        for p in csv_paths:
            dest = season.raw_events_dir / p.name
            shutil.copy2(p, dest)
            copied.append(dest)
        log.info("[7] copiati %d CSV in %s", len(copied), season.raw_events_dir.relative_to(REPO_ROOT))

        with timed(8, "precompute"):
            step_precompute(season, started)
        with timed(8, "export match events"):
            step_match_events(season, started)

        with timed(9, "pytest"):
            rc = run_logged([str(DASH_PYTHON), "-m", "pytest", "-q"], DASH_DIR)
        if rc != 0:
            raise StepError(9, f"pytest fallito (codice {rc})")
        log.info("[9] pytest verde")
    except BaseException:
        rollback(season, copied, created_raw_dir, snap)
        raise
    shutil.rmtree(snap.dir, ignore_errors=True)

    # Da qui i dati sono caricati in locale: se la pubblicazione non riesce
    # restano registrati come "in sospeso" e vengono ritentati al run successivo.
    save_pending(PENDING_FILE, REPO_ROOT, season.key, weeks,
                 season_whitelist(season.key, season.raw_events_dir, load_match_analysis_seasons()))

    # 10–11
    res, blocked = step_publish(season, weeks, push=push, dry_run=False)
    return finish_publish(season, len(csv_paths), gw, res, blocked, fallbacks, dry_run=False)


def log_summary(log_path: Path) -> None:
    log.info("── Riepilogo ──")
    log.info("esito: %s — durata totale %s", STATE.outcome, fmt_duration(time.time() - STATE.started))
    for name, secs in STATE.steps:
        log.info("  %-34s %s", name, fmt_duration(secs))
    log.info("commit di dati: %s — push: %s", STATE.commit_sha or "—", STATE.pushed_sha or "—")
    log.info("Log: %s", log_path)


def main() -> int:
    ap = argparse.ArgumentParser(description="Pipeline dati settimanale Serie A")
    ap.add_argument("--dry-run", action="store_true",
                    help="fino ai controlli di qualità + anteprima della pubblicazione, senza copiare, committare né pushare")
    ap.add_argument("--no-push", action="store_true", help="commit di dati nel worktree ma niente push")
    ap.add_argument("--publish-only", action="store_true",
                    help="salta download e precompute: pubblica solo i dati locali già pronti")
    ap.add_argument("--prepare-pull", action="store_true",
                    help="riporta a HEAD i soli file dati già identici a origin/main, così 'git pull' può allinearli")
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
        return EXIT_ERROR

    if args.prepare_pull:
        try:
            touched = prepare_local_pull(REPO_ROOT)
        except (PublishBlocked, RuntimeError) as e:
            log.error("❌ --prepare-pull non riuscito: %s", e)
            return EXIT_ERROR
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            lock.close()
        log.info("--prepare-pull: %d file dati riportati a HEAD (identici a %s su disco). Ora: git pull",
                 len(touched), UPSTREAM)
        return EXIT_OK

    awake = keep_awake()
    try:
        rc = run(args)
        # Il controllo settimanale è fatto anche se la pubblicazione è bloccata:
        # verrà ritentata al prossimo run (dati in sospeso).
        if rc in (EXIT_OK, EXIT_BLOCKED) and not args.dry_run and not args.publish_only:
            STAMP_FILE.touch()
        return rc
    except StepError as e:
        STATE.outcome = f"errore al passo {e.step}"
        log.error("❌ Errore al %s", e)
        notify(f"❌ Errore al passo {e.step}: {e.reason[:120]} — vedi log{fallback_note(args.fallbacks)}",
               subtitle=log_path.name)
        return EXIT_ERROR
    except Exception as e:
        STATE.outcome = "errore inatteso"
        log.exception("❌ Errore inatteso")
        notify(f"❌ Errore inatteso: {redact(str(e))[:120]} — vedi log", subtitle=log_path.name)
        return EXIT_ERROR
    finally:
        log_summary(log_path)
        if awake is not None:
            awake.terminate()
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()


if __name__ == "__main__":
    sys.exit(main())
