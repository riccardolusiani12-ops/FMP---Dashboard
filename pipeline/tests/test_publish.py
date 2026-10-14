"""
Test della pubblicazione tramite worktree (pipeline/publish.py).

Ogni test lavora su repo git temporanei: un remote bare locale e un clone di
"sviluppo" con la stessa struttura data/ del repo vero. Nessuna rete, nessuna
credenziale. Uso: dash_app/.venv/bin/python -m pytest -q pipeline/tests
"""
import subprocess
import sys
from pathlib import Path

import pytest

PIPELINE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE_DIR))

import publish  # noqa: E402
from config import GIT_BIN  # noqa: E402
from publish import (  # noqa: E402
    PublishBlocked, SEASON_FAMILIES, XG_CACHE, align_local_main, classify_push_error,
    local_data_divergence, season_whitelist, unknown_season_outputs, validate_path,
)

KEY = "2026_2027"
GITIGNORE = (PIPELINE_DIR.parent / ".gitignore").read_text()


def g(cwd: Path, *args: str) -> str:
    r = subprocess.run([str(GIT_BIN), *args], cwd=cwd, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def write(path: Path, content: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    (path.write_bytes if isinstance(content, bytes) else path.write_text)(content)


@pytest.fixture
def env(tmp_path):
    """remote bare + clone di sviluppo con data/ completo, sincronizzato."""
    remote = tmp_path / "remote.git"
    g(tmp_path, "init", "--quiet", "--bare", "-b", "main", str(remote))
    dev = tmp_path / "dev"
    g(tmp_path, "clone", "--quiet", str(remote), str(dev))
    for k, v in (("user.name", "test"), ("user.email", "t@example.com"), ("commit.gpgsign", "false")):
        g(dev, "config", k, v)
    write(dev / ".gitignore", GITIGNORE)
    write(dev / "src.py", "print('v1')\n")
    for fam in SEASON_FAMILIES:
        write(dev / f"data/ready/{fam}_{KEY}.parquet", f"{fam} v1")
    write(dev / "data/ready/league_summary.parquet", "league v1")
    write(dev / "data/ready/points_progression_all.parquet", "pp v1")
    write(dev / f"data/ready/.csv_count_{KEY}", "1")
    write(dev / f"data/processed/matches_{KEY}.parquet", "matches v1")
    write(dev / XG_CACHE, b"\x80model v1")
    write(dev / f"data/match_events/{KEY}/1_A_B_m1.parquet", "m1")
    write(dev / f"data/raw/serie_a_{KEY}/events/1_A_B_m1.csv", "raw,csv\n")
    write(dev / f"data/ready/player_season_{KEY}_k_table.json", "{}")
    g(dev, "add", ".")
    g(dev, "add", "-f", f"data/ready/.csv_count_{KEY}", XG_CACHE)
    g(dev, "commit", "--quiet", "-m", "init")
    g(dev, "push", "--quiet", "origin", "main")
    return {"remote": remote, "dev": dev, "wt": dev / "pipeline" / "_work" / "publish", "tmp": tmp_path}


def whitelist(dev: Path) -> list[str]:
    return season_whitelist(KEY, dev / f"data/raw/serie_a_{KEY}/events", [KEY])


def add_matchday(dev: Path, n: int = 2) -> None:
    """Simula il precompute di una nuova giornata nel working tree di sviluppo."""
    write(dev / f"data/raw/serie_a_{KEY}/events/{n}_C_D_m{n}.csv", "raw,csv\n")
    write(dev / f"data/match_events/{KEY}/{n}_C_D_m{n}.parquet", f"m{n}")
    write(dev / f"data/ready/standings_{KEY}.parquet", f"standings v{n}")
    write(dev / f"data/ready/.csv_count_{KEY}", str(n))


def remote_log(env) -> list[str]:
    return g(env["remote"], "log", "--format=%s", "main").splitlines()


def remote_files(env, rev="main") -> list[str]:
    return g(env["remote"], "ls-tree", "-r", "--name-only", rev).splitlines()


# ─── whitelist ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("rel", [
    f"data/raw/serie_a_{KEY}/events/1_A_B.csv",
    f"data/raw/serie_a_{KEY}/x.parquet",
    "data/ready/foo.csv",
    f"data/ready/player_season_{KEY}_k_table.json",
    "data/cache/pv_model.pkl",
    "src.py",
    "../data/ready/xg_2026_2027.parquet",
    "data/serie_a_pv_labelled.parquet",
])
def test_validate_path_rejects(rel):
    with pytest.raises(PublishBlocked):
        validate_path(rel)


def test_whitelist_is_explicit(env):
    paths = whitelist(env["dev"])
    assert len(paths) == len(SEASON_FAMILIES) + 5 + 1   # famiglie + lega/processed/count/xg + 1 partita
    assert f"data/match_events/{KEY}/1_A_B_m1.parquet" in paths
    assert not any(p.endswith((".csv", ".json")) or "/raw/" in p for p in paths)
    # stagione non pubblicata online → niente parquet di partita
    assert not any("match_events" in p for p in season_whitelist(KEY, env["dev"] / "nope", []))


def test_unknown_family_detected(env):
    write(env["dev"] / f"data/ready/brand_new_{KEY}.parquet", "x")
    assert unknown_season_outputs(env["dev"], KEY) == ["brand_new"]


# ─── publish ──────────────────────────────────────────────────────────────────

def test_publish_pushes_only_data_and_aligns_main(env):
    dev = env["dev"]
    add_matchday(dev)
    res = publish.publish(dev, env["wt"], whitelist(dev), "data: add Serie A 2026/27 GW2")
    assert res.status == "pushed" and res.pushed_sha == res.commit_sha
    assert remote_log(env) == ["data: add Serie A 2026/27 GW2", "init"]
    changed = g(env["remote"], "diff-tree", "--no-commit-id", "--name-only", "-r", "main").splitlines()
    assert sorted(changed) == sorted([f"data/match_events/{KEY}/2_C_D_m2.parquet",
                                      f"data/ready/.csv_count_{KEY}", f"data/ready/standings_{KEY}.parquet"])
    assert not any(f.endswith((".csv", ".json")) for f in remote_files(env))

    msg = align_local_main(dev, res.pushed_sha)
    assert "allineato" in msg
    assert g(dev, "rev-parse", "HEAD") == res.pushed_sha
    assert g(dev, "status", "--porcelain", "--untracked-files=no") == ""


def test_idempotent_second_run(env):
    dev = env["dev"]
    add_matchday(dev)
    publish.publish(dev, env["wt"], whitelist(dev), "data: GW2")
    res = publish.publish(dev, env["wt"], whitelist(dev), "data: GW2 again")
    assert res.status == "nothing" and res.commit_sha is None
    assert remote_log(env) == ["data: GW2", "init"]


def test_case_a_unrelated_local_commits_and_dirty_tree(env):
    dev = env["dev"]
    write(dev / "src.py", "print('local code commit')\n")
    g(dev, "commit", "--quiet", "-am", "wip: local code")
    write(dev / "src.py", "print('uncommitted edit')\n")
    write(dev / "notes.md", "untracked")
    g(dev, "add", "notes.md")                       # anche qualcosa in staging
    local_head = g(dev, "rev-parse", "HEAD")
    add_matchday(dev)

    res = publish.publish(dev, env["wt"], whitelist(dev), "data: GW2")
    assert res.status == "pushed"
    assert remote_log(env) == ["data: GW2", "init"]          # il commit di codice resta locale
    assert g(env["remote"], "show", "main:src.py") == "print('v1')"
    assert "notes.md" not in remote_files(env)

    msg = align_local_main(dev, res.pushed_sha)
    assert "non allineato" in msg
    assert g(dev, "rev-parse", "HEAD") == local_head          # main locale intatto
    assert (dev / "src.py").read_text() == "print('uncommitted edit')\n"


def test_case_a_other_branch_untouched(env):
    dev = env["dev"]
    g(dev, "checkout", "--quiet", "-b", "feature/x")
    write(dev / "src.py", "print('feature')\n")
    g(dev, "commit", "--quiet", "-am", "feature work")
    feature_head = g(dev, "rev-parse", "HEAD")
    add_matchday(dev)

    res = publish.publish(dev, env["wt"], whitelist(dev), "data: GW2")
    assert res.status == "pushed" and remote_log(env) == ["data: GW2", "init"]
    msg = align_local_main(dev, res.pushed_sha)
    assert "feature/x" in msg
    assert g(dev, "rev-parse", "HEAD") == feature_head
    assert g(dev, "rev-parse", "main") != res.pushed_sha      # main locale non toccato


def _other_clone_pushes(env, path: str, content: str, msg: str) -> None:
    other = env["tmp"] / "other"
    if not other.exists():
        g(env["tmp"], "clone", "--quiet", str(env["remote"]), str(other))
        for k, v in (("user.name", "o"), ("user.email", "o@example.com"), ("commit.gpgsign", "false")):
            g(other, "config", k, v)
    g(other, "pull", "--quiet")
    write(other / path, content)
    g(other, "add", "-f", path)
    g(other, "commit", "--quiet", "-m", msg)
    g(other, "push", "--quiet", "origin", "main")


def _stale_first_fetch(monkeypatch):
    """Il primo fetch non vede l'avanzamento: origin/main avanza tra fetch e push."""
    real, calls = publish.fetch, []
    monkeypatch.setattr(publish, "fetch", lambda repo: calls.append(1) if len(calls) == 0 else real(repo))


def test_case_c_origin_advanced_rebases_data_commit(env, monkeypatch):
    dev = env["dev"]
    add_matchday(dev)
    _other_clone_pushes(env, "src.py", "print('remote code')\n", "remote code change")
    _stale_first_fetch(monkeypatch)

    res = publish.publish(dev, env["wt"], whitelist(dev), "data: GW2")
    assert res.status == "pushed" and res.pushed_sha != res.commit_sha
    assert remote_log(env) == ["data: GW2", "remote code change", "init"]
    assert g(env["remote"], "show", "main:src.py") == "print('remote code')"
    assert "non allineato" in align_local_main(dev, res.pushed_sha)   # main locale è indietro


def test_case_c_conflicting_advance_blocks_without_push(env, monkeypatch):
    dev = env["dev"]
    add_matchday(dev)
    _other_clone_pushes(env, f"data/ready/standings_{KEY}.parquet", "someone else", "data: manual fix")
    before = g(env["remote"], "rev-parse", "main")
    _stale_first_fetch(monkeypatch)

    with pytest.raises(PublishBlocked, match="rebase"):
        publish.publish(dev, env["wt"], whitelist(dev), "data: GW2")
    assert g(env["remote"], "rev-parse", "main") == before
    # il run successivo riparte da un worktree pulito
    monkeypatch.undo()
    res = publish.publish(dev, env["wt"], whitelist(dev), "data: GW2", dry_run=True)
    assert res.status == "dry-run"


def test_case_d_paths_outside_whitelist(env):
    dev = env["dev"]
    with pytest.raises(PublishBlocked, match="non pubblicabile"):
        publish.publish(dev, env["wt"], [f"data/raw/serie_a_{KEY}/events/1_A_B_m1.csv"], "x")
    with pytest.raises(PublishBlocked, match="CSV/JSON"):
        publish.publish(dev, env["wt"], [f"data/ready/player_season_{KEY}_k_table.json"], "x")
    # il k_table.json sul disco non finisce mai nel commit
    add_matchday(dev)
    publish.publish(dev, env["wt"], whitelist(dev), "data: GW2")
    assert not any(f.endswith(".json") for f in remote_files(env))


def test_case_e_credentials_unavailable_blocks(env, monkeypatch):
    dev = env["dev"]
    add_matchday(dev)
    before = g(env["remote"], "rev-parse", "main")
    real = publish.run_git

    def fake(cwd, *args, **kw):
        if args and args[0] == "push":
            return subprocess.CompletedProcess(args, 128, "", "fatal: failed to get: -25320\n"
                                               "fatal: could not read Username for 'https://github.com': "
                                               "terminal prompts disabled\n")
        return real(cwd, *args, **kw)

    monkeypatch.setattr(publish, "run_git", fake)
    with pytest.raises(PublishBlocked, match="credenziale"):
        publish.publish(dev, env["wt"], whitelist(dev), "data: GW2")
    assert g(env["remote"], "rev-parse", "main") == before


def test_classify_push_error():
    assert classify_push_error("! [rejected] HEAD -> main (fetch first)") == "non-ff"
    assert classify_push_error("fatal: could not read Username for 'https://github.com'") == "auth"
    assert classify_push_error("Could not resolve host: github.com") == "network"


def test_dry_run_changes_nothing(env):
    dev = env["dev"]
    add_matchday(dev)
    before = g(env["remote"], "rev-parse", "main")
    res = publish.publish(dev, env["wt"], whitelist(dev), "data: GW2", dry_run=True)
    assert res.status == "dry-run" and len(res.files) == 3 and res.commit_sha is None
    assert g(env["remote"], "rev-parse", "main") == before
    assert g(env["wt"], "status", "--porcelain") == ""
    assert g(dev, "rev-parse", "HEAD") == before


def test_no_push_commits_only_in_worktree(env):
    dev = env["dev"]
    add_matchday(dev)
    before = g(env["remote"], "rev-parse", "main")
    res = publish.publish(dev, env["wt"], whitelist(dev), "data: GW2", push=False)
    assert res.status == "committed" and res.commit_sha
    assert g(env["remote"], "rev-parse", "main") == before
    assert g(dev, "rev-parse", "main") == before


def test_corrupted_worktree_is_recreated(env):
    dev = env["dev"]
    publish.publish(dev, env["wt"], whitelist(dev), "noop", dry_run=True)
    (env["wt"] / ".git").unlink()                                   # worktree rotto
    add_matchday(dev)
    res = publish.publish(dev, env["wt"], whitelist(dev), "data: GW2")
    assert res.status == "pushed"


def test_file_size_limit(env, monkeypatch):
    monkeypatch.setattr(publish, "MAX_FILE_BYTES", 3)
    with pytest.raises(PublishBlocked, match="oltre"):
        publish.publish(env["dev"], env["wt"], whitelist(env["dev"]), "x")


def test_missing_whitelisted_file_blocks(env):
    (env["dev"] / f"data/ready/xg_{KEY}.parquet").unlink()
    with pytest.raises(PublishBlocked, match="mancanti"):
        publish.publish(env["dev"], env["wt"], whitelist(env["dev"]), "x")


# ─── coerenza dei dati locali (preflight) ─────────────────────────────────────

def test_local_data_divergence(env):
    dev = env["dev"]
    assert local_data_divergence(dev, {}) == []
    write(dev / f"data/ready/xg_{KEY}.parquet", "edited by hand")
    assert local_data_divergence(dev, {}) == [f"data/ready/xg_{KEY}.parquet"]
    pending = publish.blob_shas(dev, [f"data/ready/xg_{KEY}.parquet"])
    assert local_data_divergence(dev, pending) == []               # prodotto dalla pipeline
    # codice locale non correlato: nessuna divergenza sui dati
    write(dev / "src.py", "x")
    assert local_data_divergence(dev, pending) == []


def test_prepare_local_pull_then_pull_rebase(env):
    """Main locale non allineato (commit di codice locali): --prepare-pull + git pull."""
    dev = env["dev"]
    write(dev / "src.py", "print('local code commit')\n")
    g(dev, "commit", "--quiet", "-am", "wip: local code")
    add_matchday(dev)
    res = publish.publish(dev, env["wt"], whitelist(dev), "data: GW2")
    assert "non allineato" in align_local_main(dev, res.pushed_sha)

    # senza preparazione git pull rifiuta (file già su disco)
    r = subprocess.run([str(GIT_BIN), "pull", "--quiet", "--rebase"], cwd=dev, capture_output=True, text=True)
    assert r.returncode != 0
    g(dev, "rebase", "--abort") if (dev / ".git" / "rebase-merge").exists() else None

    touched = publish.prepare_local_pull(dev)
    assert f"data/match_events/{KEY}/2_C_D_m2.parquet" in touched
    g(dev, "pull", "--quiet", "--rebase")
    assert g(dev, "log", "--format=%s", "-3").splitlines() == ["wip: local code", "data: GW2", "init"]
    assert (dev / f"data/ready/standings_{KEY}.parquet").read_text() == "standings v2"
    assert (dev / "src.py").read_text() == "print('local code commit')\n"
    assert g(dev, "status", "--porcelain", "--untracked-files=no") == ""
