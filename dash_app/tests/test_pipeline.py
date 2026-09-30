"""
Tests for the weekly data pipeline (repo-root pipeline/).

Pure helpers only — no network, no browser, no writes outside tmp_path.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

PIPELINE_DIR = Path(__file__).resolve().parents[2] / "pipeline"
sys.path.insert(0, str(PIPELINE_DIR))

from config import load_season, normalize_season_key  # noqa: E402
from convert import build_output_filename, normalize_team_name  # noqa: E402
from quality import QualityError, check_csvs  # noqa: E402
from run_weekly import committable, fallback_note, gw_label  # noqa: E402


@pytest.mark.parametrize("value", ["2026/27", "2026/2027", "2026-27", "2026_2027"])
def test_normalize_season_key(value):
    assert normalize_season_key(value) == "2026_2027"


def test_current_season_config():
    s = load_season()
    assert s.key == "2026_2027"
    assert s.raw_events_dir.parts[-3:] == ("raw", "serie_a_2026_2027", "events")
    assert s.tournament_calendar_id in s.results_url
    assert "_work" in s.work_dir.parts


def test_gw_label():
    assert gw_label(["6"] * 10) == "GW6"
    assert gw_label(["1", "5", "3"]) == "GW1-5"


def test_committable_files():
    s = load_season("2026/27")
    assert committable("data/ready/xg_2026_2027.parquet", s)
    assert committable("data/ready/.csv_count_2026_2027", s)
    assert committable("data/cache/xg_model.pkl", s)
    assert not committable("data/ready/.csv_count_2025_2026", s)
    assert not committable("data/raw/serie_a_2026_2027/events/1_A_B_x.csv", s)
    assert not committable("data/ready/player_season_2026_2027_k_table.json", s)


def test_fallback_note():
    assert fallback_note([]) == ""
    assert "ripiego browser (elenco partite, download di 2 partite)" in fallback_note(
        ["elenco partite", "download di 2 partite"]
    )


def test_output_filename_normalizes_inter_and_verona():
    mi = {"matchInfo": {"week": "3", "id": "abc", "description": "Internazionale vs Hellas Verona"}}
    assert build_output_filename(mi) == "3_Inter_Verona_abc.csv"
    assert normalize_team_name("FC Internazionale Milano") == "Inter"


def _write_csv(path: Path, columns: list[str], week="6", match_id="m1", team="Atalanta Bergamasca Calcio"):
    row = {c: "N/A" for c in columns}
    row.update({"week": week, "match_id": match_id, "team_name": team})
    pd.DataFrame([row], columns=columns).to_csv(path, index=False, encoding="utf-8-sig")


def test_quality_checks(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    cols = ["event", "team_name", "match_id", "week"]
    _write_csv(raw / "1_Atalanta_Milan_old.csv", cols, week="1", match_id="old")

    good = tmp_path / "6_Atalanta_Inter_m1.csv"
    _write_csv(good, cols)
    check_csvs([good], {"m1"}, raw)

    bad_team = tmp_path / "6_Atalanta_Nowhere_m2.csv"
    _write_csv(bad_team, cols, match_id="m2")
    with pytest.raises(QualityError, match="Nowhere"):
        check_csvs([bad_team], {"m2"}, raw)

    bad_cols = tmp_path / "6_Atalanta_Inter_m3.csv"
    _write_csv(bad_cols, cols + ["extra"], match_id="m3")
    with pytest.raises(QualityError, match="colonne"):
        check_csvs([bad_cols], {"m3"}, raw)

    dup = tmp_path / "1_Atalanta_Milan_old.csv"
    _write_csv(dup, cols, week="1", match_id="old")
    with pytest.raises(QualityError, match="già presenti"):
        check_csvs([dup], {"old"}, raw)
