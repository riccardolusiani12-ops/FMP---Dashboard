"""
Tests for season / team discovery when data/raw/ is absent (git-based deploy).

Locally seasons and teams come from the raw CSV folders; on Render data/raw/
is not versioned, so src.config.discover_seasons() and
src.team_mapping.teams_for_season() fall back to the precomputed parquets in
data/ready/.
"""
import pandas as pd
import pytest

import src.team_mapping as team_mapping
from src.config import RAW_DATA_DIR, READY_DATA_DIR, AVAILABLE_SEASONS, discover_seasons


def _ready_seasons() -> list[str]:
    return sorted(p.stem.replace("standings_", "") for p in READY_DATA_DIR.glob("standings_????_????.parquet"))


# ── discover_seasons ──────────────────────────────────────────────────────────

def test_raw_folders_take_precedence(tmp_path):
    raw, ready = tmp_path / "raw", tmp_path / "ready"
    for s in ("2023_2024", "2021_2022"):
        (raw / f"serie_a_{s}" / "events").mkdir(parents=True)
    ready.mkdir()
    (ready / "standings_2026_2027.parquet").touch()
    assert discover_seasons(raw, ready) == ["2021_2022", "2023_2024"]


def test_without_raw_uses_ready_parquets_in_chronological_order(tmp_path):
    ready = tmp_path / "ready"
    ready.mkdir()
    for s in ("2026_2027", "2021_2022", "2024_2025"):
        (ready / f"standings_{s}.parquet").touch()
    (ready / "standings_all.parquet").touch()  # not a season
    assert discover_seasons(tmp_path / "missing_raw", ready) == ["2021_2022", "2024_2025", "2026_2027"]


def test_without_raw_matches_real_ready_dir(tmp_path):
    seasons = discover_seasons(tmp_path / "missing_raw", READY_DATA_DIR)
    assert seasons == _ready_seasons()
    assert seasons, "no standings parquet found in data/ready/"
    if RAW_DATA_DIR.exists():
        # every locally available season must also be visible from the parquets
        assert set(AVAILABLE_SEASONS) <= set(seasons)


# ── teams_for_season ──────────────────────────────────────────────────────────

def test_teams_from_ready_parquet_are_canonical(tmp_path, monkeypatch):
    ready = tmp_path / "ready"
    ready.mkdir()
    pd.DataFrame({"Team": ["Verona", "Inter", "Atalanta"], "Season": "2026/2027"}).to_parquet(
        ready / "season_teams_2026_2027.parquet", index=False
    )
    monkeypatch.setattr(team_mapping, "RAW_DATA_DIR", tmp_path / "missing_raw")
    monkeypatch.setattr(team_mapping, "READY_DATA_DIR", ready)
    assert team_mapping.teams_for_season("2026_2027") == ["Atalanta", "Hellas Verona", "Inter"]
    assert team_mapping.teams_for_season("1999_2000") == []


@pytest.mark.parametrize("season", _ready_seasons())
def test_teams_without_raw_match_raw_derived_teams(season, tmp_path, monkeypatch):
    from_raw = team_mapping.teams_for_season(season)
    monkeypatch.setattr(team_mapping, "RAW_DATA_DIR", tmp_path / "missing_raw")
    from_ready = team_mapping.teams_for_season(season)
    assert len(from_ready) == 20
    if from_raw:  # raw CSVs present locally → must be identical
        assert from_ready == from_raw
