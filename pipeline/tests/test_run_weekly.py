"""
Test dell'orchestratore (esiti, notifiche, ripristino, tempi) senza rete né git reale.
Uso: dash_app/.venv/bin/python -m pytest -q pipeline/tests
"""
import sys
from pathlib import Path

import pytest

PIPELINE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE_DIR))

import run_weekly  # noqa: E402
from config import load_season  # noqa: E402
from publish import PublishResult  # noqa: E402


@pytest.fixture
def notes(monkeypatch):
    sent = []
    monkeypatch.setattr(run_weekly, "notify", lambda msg, subtitle=None: sent.append(msg))
    monkeypatch.setattr(run_weekly, "STATE", run_weekly.RunState())
    return sent


SEASON = load_season("2026/27")


def test_outcome_1_new_matches_pushed(notes):
    res = PublishResult("pushed", files=["a"], commit_sha="c" * 40, pushed_sha="abcdef1" + "0" * 33)
    rc = run_weekly.finish_publish(SEASON, 10, "GW6", res, None, [], dry_run=False)
    assert rc == run_weekly.EXIT_OK
    assert notes[-1].startswith("✅ 2026/27 GW6: 10 nuove partite caricate e pubblicate (abcdef1)")


def test_outcome_2_new_matches_blocked(notes):
    rc = run_weekly.finish_publish(SEASON, 10, "GW6", None, "credenziale GitHub non disponibile", [], dry_run=False)
    assert rc == run_weekly.EXIT_BLOCKED
    assert notes[-1].startswith("⚠️ 2026/27 GW6: 10 nuove partite caricate in locale, push BLOCCATO: credenziale")
    assert run_weekly.STATE.outcome == "bloccato"


def test_outcome_3_nothing_new(notes):
    rc = run_weekly.finish_publish(SEASON, 0, "", PublishResult("nothing"), None, [], dry_run=False)
    assert rc == run_weekly.EXIT_OK and notes[-1] == "ℹ️ 2026/27: nessuna nuova partita"


def test_outcome_3_pending_published(notes):
    res = PublishResult("pushed", pushed_sha="1234567" + "0" * 33)
    run_weekly.finish_publish(SEASON, 0, "", res, None, [], dry_run=False)
    assert notes[-1] == "ℹ️ 2026/27: nessuna nuova partita (pubblicati i dati in sospeso) (1234567)"


def test_outcome_3_pending_blocked(notes):
    rc = run_weekly.finish_publish(SEASON, 0, "", None, "fetch fallito", [], dry_run=False)
    assert rc == run_weekly.EXIT_BLOCKED and "in sospeso BLOCCATA: fetch fallito" in notes[-1]


def test_outcome_4_error_notifies_step(notes, monkeypatch, tmp_path):
    monkeypatch.setattr(run_weekly, "LOGS_DIR", tmp_path)
    monkeypatch.setenv("PIPELINE_NO_CAFFEINATE", "1")
    monkeypatch.setattr(sys, "argv", ["run_weekly.py"])

    def boom(args):
        raise run_weekly.StepError(8, "precompute terminato con codice 1")

    monkeypatch.setattr(run_weekly, "run", boom)
    assert run_weekly.main() == run_weekly.EXIT_ERROR
    assert notes[-1].startswith("❌ Errore al passo 8: precompute terminato")
    log_text = next(tmp_path.glob("run_*.log")).read_text()
    assert "esito: errore al passo 8" in log_text and "durata totale" in log_text


def test_slow_step_warning(notes, monkeypatch):
    monkeypatch.setitem(run_weekly.STEP_WARN_MINUTES, "precompute", -1)
    with run_weekly.timed(8, "precompute"):
        pass
    assert run_weekly.STATE.slow and run_weekly.STATE.slow[0].startswith("precompute")
    run_weekly.finish_publish(SEASON, 0, "", PublishResult("nothing"), None, [], dry_run=False)
    assert "⏱️ lento: precompute" in notes[-1]


def test_rollback_restores_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(run_weekly, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(run_weekly, "MATCH_EVENTS_DIR", tmp_path / "data" / "match_events")
    raw = tmp_path / "raw" / "events"
    raw.mkdir(parents=True)
    season = type(SEASON)(**{**SEASON.__dict__, "raw_events_dir": raw, "work_dir": tmp_path / "_work"})
    ready = tmp_path / "data" / "ready"
    ready.mkdir(parents=True)
    (ready / "standings_2026_2027.parquet").write_text("before")
    me = tmp_path / "data" / "match_events" / "2026_2027"
    me.mkdir(parents=True)
    (me / "1_A_B_m1.parquet").write_text("m1")

    snap = run_weekly.take_snapshot(season)
    # passi 7–8 simulati
    csv = raw / "2_C_D_m2.csv"
    csv.write_text("x")
    (ready / "standings_2026_2027.parquet").write_text("after")
    (ready / "xg_2026_2027.parquet").write_text("new")
    (me / "2_C_D_m2.parquet").write_text("m2")

    run_weekly.rollback(season, [csv], False, snap)
    assert (ready / "standings_2026_2027.parquet").read_text() == "before"
    assert not (ready / "xg_2026_2027.parquet").exists()
    assert sorted(p.name for p in me.iterdir()) == ["1_A_B_m1.parquet"]
    assert not csv.exists()
