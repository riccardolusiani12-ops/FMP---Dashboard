"""
Tests for the published per-match events (src/utils/match_events.py) used by
the Match Analysis when data/raw/ is absent (Render).
"""
import ast
from pathlib import Path

import pandas as pd
import pytest

import src.utils.match_events as me
import src.utils.paths as paths
from src.config import MATCH_EVENTS_DIR, RAW_DATA_DIR
from src.utils.match_event_columns import MATCH_EVENT_COLUMNS, OPTA_EVENT_COLUMNS

SRC_ROOT = Path(__file__).resolve().parents[1]          # dash_app/

# Match Analysis entry points: match list + module views, Player Analysis callbacks.
ENTRY_MODULES = [
    "src.components.analysis_cards",
    "src.components.player_analysis_cards",
    "src.callbacks.player_analysis_callbacks",
]
# Reached only through lazy imports inside src.analytics.data_loader (season
# precompute / season tables); they never read a single match CSV.
SEASON_ONLY_MODULES = {
    "src.analytics.formations",
    "src.analytics.goal_distribution",
    "src.analytics.multi_season_standings",
    "src.analytics.playing_style",
    "src.analytics.ppda",
    "src.analytics.precompute_serie_a",
    "src.analytics.season_player_analysis",
}


def _module_file(name: str):
    p = SRC_ROOT.joinpath(*name.split("."))
    for cand in (p.with_suffix(".py"), p / "__init__.py"):
        if cand.exists():
            return cand
    return None


def _import_closure(entries: list[str]) -> set[str]:
    """src.* modules statically reachable from *entries*, function-level imports included."""
    seen, todo = set(), list(entries)
    while todo:
        name = todo.pop()
        if name in seen or name in SEASON_ONLY_MODULES or _module_file(name) is None:
            continue
        seen.add(name)
        for node in ast.walk(ast.parse(_module_file(name).read_text())):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("src"):
                todo.append(node.module)
                todo += [f"{node.module}.{a.name}" for a in node.names]
            elif isinstance(node, ast.Import):
                todo += [a.name for a in node.names if a.name.startswith("src")]
    return seen


def _raw_csvs() -> list[Path]:
    return [next(iter(sorted(d.glob("*.csv"))), None) for d in sorted(RAW_DATA_DIR.glob("serie_a_*/events"))]


# ── Column lists ───────────────────────────────────────────────────────────────

def test_match_columns_are_ordered_subset_of_opta_header():
    assert len(OPTA_EVENT_COLUMNS) == len(set(OPTA_EVENT_COLUMNS)) == 248
    assert set(MATCH_EVENT_COLUMNS) <= set(OPTA_EVENT_COLUMNS)
    assert list(MATCH_EVENT_COLUMNS) == [c for c in OPTA_EVENT_COLUMNS if c in MATCH_EVENT_COLUMNS]


def test_match_columns_cover_every_column_used_by_match_analysis():
    """Guard: a column referenced by a Match Analysis module must be published."""
    modules = _import_closure(ENTRY_MODULES)
    assert "src.analytics.chance_creation" in modules and "src.analytics.player_analysis" in modules
    modules.discard("src.utils.match_event_columns")   # the column lists themselves
    literals = set()
    for name in modules:
        for node in ast.walk(ast.parse(_module_file(name).read_text())):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                literals.add(node.value)
    missing = sorted((literals & set(OPTA_EVENT_COLUMNS)) - set(MATCH_EVENT_COLUMNS))
    assert not missing, f"add to MATCH_EVENT_COLUMNS and re-export: {missing}"


@pytest.mark.skipif(not any(_raw_csvs()), reason="data/raw/ not available")
def test_opta_header_matches_raw_csvs():
    for csv in filter(None, _raw_csvs()):
        assert tuple(pd.read_csv(csv, nrows=0).columns) == OPTA_EVENT_COLUMNS, csv.parent.parent.name


# ── Export / materialise ───────────────────────────────────────────────────────

@pytest.fixture
def cache_dirs(tmp_path, monkeypatch):
    events, cache = tmp_path / "match_events", tmp_path / "csv_cache"
    monkeypatch.setattr(me, "MATCH_EVENTS_DIR", events)
    monkeypatch.setattr(me, "MATCH_CSV_CACHE_DIR", cache)
    return events, cache


def _synthetic_csv(path: Path, week="6") -> Path:
    """A match CSV with the dtype traps of real files: ints, floats, empty
    columns, the "NA" week of the play-off, text with commas and quotes."""
    rows = []
    for i in range(4):
        row = {c: "" for c in OPTA_EVENT_COLUMNS}
        row.update({
            "event_id": str(i + 1), "event": "Pass", "type_id": "1", "period_id": "1",
            "time_min": str(i), "time_sec": "5", "x": f"{10.5 + i}", "y": "50.0",
            "outcome": "1" if i % 2 else "0", "team_name": 'Hellas Verona, "FC"',
            "week": week, "Pass End X": "" if i == 0 else "71.2", "Length": "12.3",
            "player_name": "Riccardo Orsolini", "timeStamp": f"2026-08-24T18:4{i}:05.123Z",
        })
        rows.append(row)
    pd.DataFrame(rows, columns=OPTA_EVENT_COLUMNS).to_csv(path, index=False, encoding="utf-8-sig")
    return path


def test_rebuilt_csv_reads_exactly_like_the_raw_one(tmp_path, cache_dirs):
    events, _ = cache_dirs
    raw = _synthetic_csv(tmp_path / "NA_Spezia_Verona_abc.csv", week="NA")
    pq_path = me.export_match(raw, events / "2022_2023" / f"{raw.stem}.parquet")
    rebuilt = me.materialize_match_csv(pq_path)
    assert rebuilt.name == raw.name
    expected = pd.read_csv(raw, low_memory=False)[list(MATCH_EVENT_COLUMNS)]
    pd.testing.assert_frame_equal(pd.read_csv(rebuilt, low_memory=False), expected)


def test_materialize_is_deterministic_atomic_and_bounded(tmp_path, cache_dirs, monkeypatch):
    events, cache = cache_dirs
    monkeypatch.setattr(me, "MATCH_CSV_CACHE_MAX", 3)
    parquets = [me.export_match(_synthetic_csv(tmp_path / f"{i}_Bologna_Lazio_m{i}.csv"),
                                events / "2026_2027" / f"{i}_Bologna_Lazio_m{i}.parquet")
                for i in range(1, 6)]
    first = me.materialize_match_csv(parquets[0])
    assert first == cache / "2026_2027" / "1_Bologna_Lazio_m1.csv"
    assert me.materialize_match_csv(parquets[0]) == first
    for p in parquets[1:]:
        me.materialize_match_csv(p)
    left = sorted(f.name for f in cache.rglob("*") if f.is_file())
    assert len(left) == 3 and all(n.endswith(".csv") for n in left)   # no temp leftovers
    assert "5_Bologna_Lazio_m5.csv" in left and "1_Bologna_Lazio_m1.csv" not in left


def test_ensure_match_csv_rebuilds_an_evicted_file(tmp_path, cache_dirs):
    events, _ = cache_dirs
    raw = _synthetic_csv(tmp_path / "3_Bologna_Sassuolo_x.csv")
    rebuilt = me.materialize_match_csv(me.export_match(raw, events / "2026_2027" / f"{raw.stem}.parquet"))
    rebuilt.unlink()
    assert me.ensure_match_csv(rebuilt) == rebuilt and rebuilt.exists()
    assert me.ensure_match_csv(raw) == raw                  # raw CSVs pass through


def test_export_season_is_incremental_and_prune(tmp_path, cache_dirs):
    events, _ = cache_dirs
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    _synthetic_csv(raw_dir / "1_Bologna_Lazio_a.csv")
    assert me.export_season("2026_2027", raw_dir) == (1, 0)
    _synthetic_csv(raw_dir / "2_Lazio_Bologna_b.csv")
    assert me.export_season("2026_2027", raw_dir) == (1, 1)
    (events / "2024_2025").mkdir()
    assert me.prune(["2026_2027"]) == ["2024_2025"]
    assert sorted(p.name for p in events.iterdir()) == ["2026_2027"]


# ── Match Analysis sources (paths.py) ──────────────────────────────────────────

def test_match_analysis_files_prefers_raw_then_published(tmp_path, monkeypatch):
    raw, pub = tmp_path / "raw", tmp_path / "match_events"
    monkeypatch.setattr(paths, "RAW_DATA_DIR", raw)
    monkeypatch.setattr(paths, "MATCH_EVENTS_DIR", pub)
    monkeypatch.setattr(paths, "AVAILABLE_SEASONS", ["2024_2025", "2025_2026", "2026_2027"])
    (raw / "serie_a_2024_2025" / "events").mkdir(parents=True)
    (raw / "serie_a_2024_2025" / "events" / "1_A_B_x.csv").touch()
    (pub / "2024_2025").mkdir(parents=True)
    (pub / "2024_2025" / "1_A_B_x.parquet").touch()
    (pub / "2026_2027").mkdir()
    (pub / "2026_2027" / "2_C_D_y.parquet").touch()

    assert [p.suffix for p in paths.match_analysis_files("2024_2025")] == [".csv"]
    assert [p.name for p in paths.match_analysis_files("2026_2027")] == ["2_C_D_y.parquet"]
    assert paths.match_analysis_files("2025_2026") == []
    assert paths.match_analysis_seasons() == ["2024_2025", "2026_2027"]


def test_match_list_unpublished_season_and_playoff_week(monkeypatch):
    import src.components.analysis_cards as ac
    monkeypatch.setattr(ac, "_score_lookup", lambda season: {})
    monkeypatch.setattr(ac, "match_analysis_files", lambda season: [])
    text = str(ac._match_list_layout("2021_2022", "Bologna", "ma").to_plotly_json())
    assert "not available online" in text and "No matches found" not in text

    files = [Path("NA_Spezia_Verona_p.csv"), Path("25_Spezia_Verona_r.csv"), Path("3_Verona_Spezia_s.csv")]
    monkeypatch.setattr(ac, "match_analysis_files", lambda season: files)
    grid = ac._match_list_layout("2022_2023", "Spezia", "ma").children[1]
    assert [c.id["index"] for c in grid.children] == ["s", "r", "p"]
    assert "Play-off" in str(grid.children[-1].to_plotly_json())


# ── Real data (skipped when not available) ─────────────────────────────────────

@pytest.mark.skipif(not any(MATCH_EVENTS_DIR.glob("*/*.parquet")) or not RAW_DATA_DIR.exists(),
                    reason="needs data/raw/ and data/match_events/")
def test_published_match_matches_raw(cache_dirs):
    pq_path = sorted(MATCH_EVENTS_DIR.glob("*/*.parquet"))[0]
    raw = RAW_DATA_DIR / f"serie_a_{pq_path.parent.name}" / "events" / f"{pq_path.stem}.csv"
    rebuilt = me.materialize_match_csv(pq_path)
    expected = pd.read_csv(raw, low_memory=False)[list(MATCH_EVENT_COLUMNS)]
    pd.testing.assert_frame_equal(pd.read_csv(rebuilt, low_memory=False), expected)
