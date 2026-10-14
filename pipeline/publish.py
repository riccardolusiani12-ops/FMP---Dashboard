"""
Pubblicazione dei dati su origin/main tramite un worktree dedicato.

Il working tree di sviluppo non viene mai usato per committare né per pushare:
  1. fetch di origin/main;
  2. worktree detached in pipeline/_work/publish riallineato a origin/main
     (ricreato da zero se manca o è corrotto);
  3. copia dei SOLI file della whitelist (path esatti, nessun wildcard su data/);
  4. commit `data: add Serie A <stagione> <GW>` e `push origin HEAD:main`;
     se origin/main è avanzato: fetch + rebase del solo commit di dati, mai
     force-push;
  5. allineamento facoltativo del main locale (fast-forward senza toccare i
     file su disco), solo se è sicuro.

Ogni condizione che rende la pubblicazione non sicura solleva PublishBlocked:
il chiamante non pusha nulla e riporta il motivo ("bloccato").

Nessuna credenziale passa da qui: il push usa l'helper osxkeychain di GIT_BIN e
GIT_TERMINAL_PROMPT=0 impedisce qualunque richiesta interattiva.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from config import GIT_BIN

log = logging.getLogger("pipeline")

REMOTE = "origin"
BRANCH = "main"
UPSTREAM = f"{REMOTE}/{BRANCH}"
DATA_PATHS = ["data/ready", "data/processed", "data/match_events"]
# Il modello xG in cache viene riaddestrato dal precompute quando cambia il
# numero di CSV raw (comportamento esistente della dash, src/analytics/xg.py).
XG_CACHE = "data/cache/xg_model.pkl"
COMMIT_PREFIX = "data: add Serie A"

# Famiglie data/ready/<famiglia>_<stagione>.parquet scritte dal precompute.
# Elenco esplicito: una famiglia nuova blocca la pubblicazione finché non viene
# aggiunta qui (vedi unknown_season_outputs).
SEASON_FAMILIES = (
    "castle_summary",
    "chances_conceded_summary",
    "corner_kicks_summary",
    "formation_lineups",
    "formations",
    "ft_entries",
    "gk_events",
    "goal_distribution",
    "matches",
    "offensive_summary",
    "player_season",
    "playing_style_league",
    "points_progression",
    "ppda",
    "pressing_actions",
    "pressing_summary",
    "season_teams",
    "shots",
    "standings",
    "team_overview",
    "transitions_summary",
    "xg",
)
# Presenti in data/ready ma non più generate da nessun codice del repo.
NOT_PRODUCED_BY_PRECOMPUTE = {"formation_positions"}
# Parquet di lega riscritti dal precompute di qualunque stagione.
LEAGUE_FILES = ("data/ready/league_summary.parquet", "data/ready/points_progression_all.parquet")

# Unici path pubblicabili. Tutto il resto (CSV, JSON, data/raw/, …) è rifiutato.
_ALLOWED = [re.compile(p) for p in (
    r"data/ready/[a-z_]+_\d{4}_\d{4}\.parquet",
    r"data/ready/(league_summary|points_progression_all)\.parquet",
    r"data/ready/\.csv_count_\d{4}_\d{4}",
    r"data/processed/matches_\d{4}_\d{4}\.parquet",
    r"data/match_events/\d{4}_\d{4}/[^/]+\.parquet",
    re.escape(XG_CACHE),
)]
MAX_FILE_BYTES = 25 * 1024 ** 2     # GitHub avverte a 50 MB e rifiuta a 100 MB
MAX_COMMIT_BYTES = 60 * 1024 ** 2   # una giornata ≈ 3 MB, una stagione intera ≈ 45 MB
MAX_PUSH_ATTEMPTS = 3


class PublishBlocked(Exception):
    """La pubblicazione non può procedere in sicurezza: niente push."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass
class PublishResult:
    status: str                       # "pushed" | "nothing" | "committed" | "dry-run"
    files: list[str] = field(default_factory=list)
    base_sha: str | None = None       # origin/main su cui è stato creato il commit
    commit_sha: str | None = None     # commit di dati come creato la prima volta
    pushed_sha: str | None = None     # commit su origin/main dopo il push (≠ se rebase)
    stat: str = ""
    alignment: str = ""


# ═════════════════════════════════════════════════════════════════════════════
# GIT
# ═════════════════════════════════════════════════════════════════════════════

def redact(text: str) -> str:
    """Maschera eventuali credenziali (https://user:token@host, token GitHub)."""
    text = re.sub(r"(https?://)[^/@\s]+@", r"\1***@", text)
    return re.sub(r"\b(gh[opusr]_|github_pat_)[A-Za-z0-9_]+", r"\1***", text)


def check_git_bin() -> None:
    if not (GIT_BIN.is_file() and os.access(GIT_BIN, os.X_OK)):
        raise PublishBlocked(f"git non trovato o non eseguibile: {GIT_BIN} (variabile PIPELINE_GIT)")


def run_git(cwd: Path, *args: str, check: bool = True, stdin: str | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", LC_ALL="C")
    r = subprocess.run([str(GIT_BIN), *args], cwd=cwd, capture_output=True, text=True, env=env, input=stdin)
    if check and r.returncode != 0:
        raise RuntimeError(redact(f"git {' '.join(args)}: {(r.stderr or r.stdout).strip()}"))
    return r


def git_out(cwd: Path, *args: str) -> str:
    return run_git(cwd, *args).stdout.strip()


def fetch(repo: Path) -> None:
    r = run_git(repo, "fetch", "--quiet", REMOTE, BRANCH, check=False)
    if r.returncode != 0:
        raise PublishBlocked(f"fetch di {UPSTREAM} fallito: {_first_line(r)}")


def _first_line(r: subprocess.CompletedProcess) -> str:
    lines = [l for l in redact((r.stderr or "") + (r.stdout or "")).splitlines() if l.strip()]
    return lines[-1].strip() if lines else f"codice {r.returncode}"


def blob_shas(repo: Path, paths: list[str]) -> dict[str, str]:
    """SHA blob git dei file su disco (stesso hash che userebbe un commit)."""
    existing = [p for p in paths if (repo / p).is_file()]
    if not existing:
        return {}
    out = run_git(repo, "hash-object", "--no-filters", "--stdin-paths", stdin="\n".join(existing) + "\n").stdout
    return dict(zip(existing, out.split()))


def tree_blobs(repo: Path, ref: str, paths: list[str]) -> dict[str, str]:
    """{path: sha blob} dei file sotto `paths` nel commit `ref`."""
    out = run_git(repo, "ls-tree", "-r", "-z", ref, "--", *paths).stdout
    blobs = {}
    for entry in filter(None, out.split("\0")):
        meta, path = entry.split("\t", 1)
        _mode, kind, sha = meta.split()
        if kind == "blob":
            blobs[path] = sha
    return blobs


# ═════════════════════════════════════════════════════════════════════════════
# WHITELIST
# ═════════════════════════════════════════════════════════════════════════════

def validate_path(rel: str) -> None:
    p = Path(rel)
    if p.is_absolute() or ".." in p.parts or "raw" in p.parts:
        raise PublishBlocked(f"path non pubblicabile: {rel}")
    if p.suffix.lower() in (".csv", ".json"):
        raise PublishBlocked(f"CSV/JSON non pubblicabili: {rel}")
    if not any(rx.fullmatch(rel) for rx in _ALLOWED):
        raise PublishBlocked(f"path fuori whitelist: {rel}")


def season_whitelist(season_key: str, raw_events_dir: Path, match_analysis_seasons: list[str]) -> list[str]:
    """Path esatti pubblicabili per una stagione."""
    paths = [f"data/ready/{fam}_{season_key}.parquet" for fam in SEASON_FAMILIES]
    paths += [
        f"data/processed/matches_{season_key}.parquet",
        *LEAGUE_FILES,
        f"data/ready/.csv_count_{season_key}",
        XG_CACHE,
    ]
    if season_key in match_analysis_seasons and raw_events_dir.exists():
        paths += sorted(f"data/match_events/{season_key}/{p.stem}.parquet"
                        for p in raw_events_dir.glob("*.csv"))
    for rel in paths:
        validate_path(rel)
    return paths


def unknown_season_outputs(repo: Path, season_key: str) -> list[str]:
    """Parquet di stagione presenti su disco ma non previsti dalla whitelist."""
    suffix = f"_{season_key}.parquet"
    found = {p.name[: -len(suffix)] for p in (repo / "data" / "ready").glob(f"*{suffix}")}
    return sorted(found - set(SEASON_FAMILIES) - NOT_PRODUCED_BY_PRECOMPUTE)


def check_sources(repo: Path, paths: list[str]) -> None:
    missing = [p for p in paths if not (repo / p).is_file()]
    if missing:
        raise PublishBlocked(f"{len(missing)} file della whitelist mancanti (es. {missing[0]})")
    big = [p for p in paths if (repo / p).stat().st_size > MAX_FILE_BYTES]
    if big:
        raise PublishBlocked(f"file oltre {MAX_FILE_BYTES // 1024 ** 2} MB: {', '.join(big)}")


# ═════════════════════════════════════════════════════════════════════════════
# COERENZA DEI DATI LOCALI (preflight)
# ═════════════════════════════════════════════════════════════════════════════

def local_data_divergence(repo: Path, pending: dict[str, str], ref: str = UPSTREAM) -> list[str]:
    """
    File dati tracciati in `ref` il cui contenuto su disco è diverso da `ref`,
    esclusi quelli prodotti dalla pipeline e non ancora pubblicati (`pending`,
    con lo stesso hash). Una lista non vuota vuol dire che i dati locali non
    sono quelli di origin/main: un precompute ricalcolerebbe file di lega e
    li pubblicherebbe partendo da dati diversi.
    """
    expected = tree_blobs(repo, ref, [*DATA_PATHS, XG_CACHE])
    actual = blob_shas(repo, list(expected))
    return sorted(p for p, sha in expected.items()
                  if actual.get(p) != sha and pending.get(p, "missing") != actual.get(p))


# ═════════════════════════════════════════════════════════════════════════════
# MANIFEST DEI DATI IN SOSPESO
# ═════════════════════════════════════════════════════════════════════════════

def load_pending(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) and isinstance(data.get("files"), dict) else {}
    except (OSError, ValueError):
        return {}


def save_pending(path: Path, repo: Path, season_key: str, weeks: list[str], paths: list[str]) -> dict:
    """Registra i file prodotti da un run riuscito e non ancora pubblicati."""
    prev = load_pending(path)
    files = dict(prev.get("files", {}))
    files.update(blob_shas(repo, paths))
    data = {
        "season": season_key,
        "weeks": sorted({*prev.get("weeks", []), *map(str, weeks)}, key=lambda w: int(w) if w.isdigit() else 0),
        "files": files,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1))
    return data


def clear_pending(path: Path) -> None:
    path.unlink(missing_ok=True)


# ═════════════════════════════════════════════════════════════════════════════
# WORKTREE
# ═════════════════════════════════════════════════════════════════════════════

def _registered_worktrees(repo: Path) -> set[Path]:
    out = run_git(repo, "worktree", "list", "--porcelain").stdout
    return {Path(l[len("worktree "):]).resolve() for l in out.splitlines() if l.startswith("worktree ")}


def _remove_worktree_dir(repo: Path, wt: Path) -> None:
    # Protezione: si cancella solo una cartella "publish" dentro pipeline/_work.
    wt = wt.resolve()
    if wt.name != "publish" or wt.parent.name != "_work" or repo.resolve() not in wt.parents:
        raise PublishBlocked(f"rifiuto di cancellare {wt}: non è il worktree di pubblicazione")
    shutil.rmtree(wt)


def prepare_worktree(repo: Path, wt: Path, base: str) -> None:
    """Worktree detached esattamente su `base`, senza file estranei."""
    healthy = False
    if (wt / ".git").exists() and wt.resolve() in _registered_worktrees(repo):
        r = run_git(wt, "rev-parse", "--show-toplevel", check=False)
        healthy = r.returncode == 0 and Path(r.stdout.strip()).resolve() == wt.resolve()
    if healthy:
        for state in ("rebase-merge", "rebase-apply"):
            if (wt / git_out(wt, "rev-parse", "--git-path", state)).exists():
                run_git(wt, "rebase", "--abort", check=False)
        run_git(wt, "checkout", "--quiet", "--detach", "--force", base)
        run_git(wt, "reset", "--quiet", "--hard", base)
        run_git(wt, "clean", "-ffdxq")
    else:
        if wt.exists():
            log.warning("[10] worktree di pubblicazione non valido: lo ricreo")
            _remove_worktree_dir(repo, wt)
        run_git(repo, "worktree", "prune")
        wt.parent.mkdir(parents=True, exist_ok=True)
        run_git(repo, "worktree", "add", "--quiet", "--detach", str(wt), base)
    if git_out(wt, "rev-parse", "HEAD") != base:
        raise PublishBlocked("worktree di pubblicazione non allineato a origin/main")


# ═════════════════════════════════════════════════════════════════════════════
# PUSH
# ═════════════════════════════════════════════════════════════════════════════

_NON_FF = ("non-fast-forward", "fetch first", "[rejected]")
_AUTH = ("could not read username", "authentication failed", "-25320", "terminal prompts disabled",
         "permission denied", "error: 403")
_NETWORK = ("could not resolve host", "failed to connect", "unable to access", "timed out")


def classify_push_error(text: str) -> str:
    low = text.lower()
    if any(s in low for s in _AUTH):
        return "auth"
    if any(s in low for s in _NON_FF):
        return "non-ff"
    if any(s in low for s in _NETWORK):
        return "network"
    return "other"


def _rebase_on_upstream(repo: Path, wt: Path, paths: set[str]) -> None:
    fetch(repo)
    r = run_git(wt, "rebase", "--quiet", UPSTREAM, check=False)
    if r.returncode != 0:
        run_git(wt, "rebase", "--abort", check=False)
        raise PublishBlocked(f"{UPSTREAM} è avanzato e il rebase del commit di dati è fallito: {_first_line(r)}")
    _assert_only_whitelisted(wt, "HEAD", paths)


def _assert_only_whitelisted(wt: Path, rev: str, paths: set[str]) -> None:
    if git_out(wt, "rev-parse", rev) == git_out(wt, "rev-parse", UPSTREAM):
        return
    touched = git_out(wt, "diff-tree", "--no-commit-id", "--name-only", "-r", rev).splitlines()
    bad = [p for p in touched if p not in paths]
    if bad:
        raise PublishBlocked(f"il commit di dati tocca file fuori whitelist: {bad[:3]}")


def publish(repo: Path, wt: Path, paths: list[str], message: str, *,
            push: bool = True, dry_run: bool = False) -> PublishResult:
    """Copia `paths` nel worktree allineato a origin/main, committa e pusha."""
    check_git_bin()
    for rel in paths:
        validate_path(rel)
    check_sources(repo, paths)
    allowed = set(paths)

    fetch(repo)
    base = git_out(repo, "rev-parse", UPSTREAM)
    try:
        prepare_worktree(repo, wt, base)
    except RuntimeError as e:
        raise PublishBlocked(f"worktree di pubblicazione: {e}")

    for rel in paths:
        dest = wt / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo / rel, dest)
    # -f: .csv_count_* e data/cache/ sono gitignorati; la lista è già validata.
    run_git(wt, "add", "-f", "--", *paths)

    staged = [p for p in run_git(wt, "diff", "--cached", "--name-only", "-z").stdout.split("\0") if p]
    stray = [l[3:] for l in run_git(wt, "status", "--porcelain", "--untracked-files=all").stdout.splitlines()
             if l[3:] not in allowed]
    bad = [p for p in staged if p not in allowed] + stray
    if bad:
        run_git(wt, "reset", "--quiet", "--hard", base, check=False)
        raise PublishBlocked(f"file fuori whitelist nel worktree: {bad[:3]}")
    if not staged:
        return PublishResult("nothing", base_sha=base)

    total = sum((wt / p).stat().st_size for p in staged)
    if total > MAX_COMMIT_BYTES:
        run_git(wt, "reset", "--quiet", "--hard", base, check=False)
        raise PublishBlocked(f"commit di dati troppo grande: {total / 1024 ** 2:.0f} MB")
    stat = run_git(wt, "diff", "--cached", "--stat=100").stdout.rstrip()
    result = PublishResult("dry-run", files=staged, base_sha=base, stat=stat)
    if dry_run:
        run_git(wt, "reset", "--quiet", "--hard", base, check=False)
        return result

    try:
        run_git(wt, "commit", "--quiet", "--no-verify", "-m", message)
    except RuntimeError as e:
        raise PublishBlocked(f"commit nel worktree non riuscito: {e}")
    result.commit_sha = git_out(wt, "rev-parse", "HEAD")
    _assert_only_whitelisted(wt, "HEAD", allowed)
    if not push:
        result.status = "committed"
        return result

    for attempt in range(1, MAX_PUSH_ATTEMPTS + 1):
        r = run_git(wt, "push", "--porcelain", REMOTE, f"HEAD:refs/heads/{BRANCH}", check=False)
        if r.returncode == 0:
            break
        err = redact((r.stderr or "") + (r.stdout or ""))
        kind = classify_push_error(err)
        if kind == "auth":
            raise PublishBlocked("credenziale GitHub non disponibile (Portachiavi) — push non eseguito")
        if kind == "network":
            raise PublishBlocked(f"GitHub non raggiungibile — push non eseguito ({_first_line(r)})")
        if kind != "non-ff":
            raise PublishBlocked(f"push rifiutato: {_first_line(r)}")
        log.warning("[10] %s è avanzato (tentativo %d/%d): fetch + rebase del commit di dati",
                    UPSTREAM, attempt, MAX_PUSH_ATTEMPTS)
        _rebase_on_upstream(repo, wt, allowed)
        if git_out(wt, "rev-parse", "HEAD") == git_out(wt, "rev-parse", UPSTREAM):
            result.status = "nothing"       # gli stessi dati sono già su origin/main
            return result
    else:
        raise PublishBlocked(f"{UPSTREAM} continua ad avanzare: push non riuscito dopo {MAX_PUSH_ATTEMPTS} tentativi")

    result.pushed_sha = git_out(wt, "rev-parse", "HEAD")
    result.base_sha = git_out(wt, "rev-parse", "HEAD^")
    result.status = "pushed"
    return result


# ═════════════════════════════════════════════════════════════════════════════
# ALLINEAMENTO DEL MAIN LOCALE
# ═════════════════════════════════════════════════════════════════════════════

def align_local_main(repo: Path, pushed_sha: str) -> str:
    """
    Fast-forward del main locale sul commit di dati appena pubblicato, senza
    toccare i file su disco (sono già quelli pubblicati). Solo se:
    - il branch corrente è main (un altro branch non viene mai toccato);
    - main coincide con il genitore del commit di dati;
    - niente in staging e nessuna modifica tracciata, a parte i file del
      commit di dati con contenuto identico a quello pubblicato.
    Altrimenti non fa nulla e restituisce il motivo, da riportare nel log.
    """
    branch = run_git(repo, "symbolic-ref", "--quiet", "--short", "HEAD", check=False).stdout.strip()
    if branch != BRANCH:
        return f"main locale non toccato: il branch corrente è '{branch or 'HEAD detached'}'"
    head = git_out(repo, "rev-parse", "HEAD")
    parent = git_out(repo, "rev-parse", f"{pushed_sha}^")
    if head != parent:
        return (f"main locale non allineato: HEAD {head[:7]} ≠ base del commit di dati {parent[:7]} "
                f"(commit locali o main indietro) — i file su disco sono già quelli pubblicati; "
                f"{PULL_HINT}")
    if run_git(repo, "diff", "--cached", "--name-only").stdout.strip():
        return "main locale non allineato: ci sono file in staging"
    changed = git_out(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", pushed_sha).splitlines()
    dirty = run_git(repo, "diff", "--name-only").stdout.split()
    others = [p for p in dirty if p not in changed]
    if others:
        return (f"main locale non allineato: modifiche tracciate non correlate ({len(others)} file, "
                f"es. {others[0]}); {PULL_HINT}")
    if blob_shas(repo, changed) != tree_blobs(repo, pushed_sha, changed):
        return "main locale non allineato: i file su disco differiscono dal commit pubblicato"
    run_git(repo, "update-ref", "-m", "pipeline: fast-forward al commit di dati pubblicato",
            f"refs/heads/{BRANCH}", pushed_sha, head)
    run_git(repo, "reset", "--quiet", pushed_sha, "--", *changed)
    leftover = run_git(repo, "status", "--porcelain", "--", *changed).stdout.strip()
    if leftover:
        return f"main locale avanzato a {pushed_sha[:7]} ma {len(leftover.splitlines())} file risultano ancora modificati"
    return f"main locale allineato a {pushed_sha[:7]} (fast-forward, file su disco invariati)"


PULL_HINT = "per allineare: run_weekly.py --prepare-pull, poi git pull"


def prepare_local_pull(repo: Path, ref: str = UPSTREAM) -> list[str]:
    """
    Prepara il working tree a un normale `git pull` quando i dati pubblicati
    sono già su disco ma il branch locale non contiene ancora il commit di dati
    (altrimenti git rifiuta: "local changes / untracked files would be
    overwritten"). Tocca SOLO i file dati il cui contenuto su disco è identico
    a `ref`: li riporta alla versione di HEAD, o li rimuove se HEAD non li ha.
    Il pull li ripristina identici. Restituisce i path toccati.
    """
    fetch(repo)
    upstream = tree_blobs(repo, ref, [*DATA_PATHS, XG_CACHE])
    on_disk = blob_shas(repo, list(upstream))
    head = tree_blobs(repo, "HEAD", [*DATA_PATHS, XG_CACHE])
    touched = [p for p, sha in upstream.items() if on_disk.get(p) == sha and head.get(p) != sha]
    restore = [p for p in touched if p in head]
    if restore:
        run_git(repo, "checkout", "HEAD", "--", *restore)
    for p in touched:
        if p not in head:
            (repo / p).unlink()
            run_git(repo, "rm", "--cached", "--quiet", "--ignore-unmatch", "--", p)
    return sorted(touched)
