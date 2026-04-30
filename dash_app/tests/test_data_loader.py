"""
Tests for src/analytics/data_loader.py

Covers:
  - _read_parquet: returns None for missing/corrupt files, caches valid reads
  - invalidate_cache: clears the in-memory cache without errors
"""
import pandas as pd
import pytest

from src.analytics.data_loader import _read_parquet, invalidate_cache


@pytest.fixture(autouse=True)
def clear_cache():
    """Ensure a clean cache state before and after every test."""
    invalidate_cache()
    yield
    invalidate_cache()


# ── _read_parquet ─────────────────────────────────────────────────────────────

def test_read_parquet_nonexistent_returns_none(tmp_path):
    result = _read_parquet(str(tmp_path / "does_not_exist.parquet"))
    assert result is None


def test_read_parquet_valid_file(tmp_path):
    df = pd.DataFrame({"Team": ["Bologna", "Milan"], "Pts": [60, 55]})
    path = tmp_path / "test_table.parquet"
    df.to_parquet(path)

    result = _read_parquet(str(path))
    assert result is not None
    assert list(result["Team"]) == ["Bologna", "Milan"]


def test_read_parquet_result_is_cached(tmp_path):
    """Reading the same path twice should return the identical object (cache hit)."""
    df = pd.DataFrame({"x": [1, 2, 3]})
    path = tmp_path / "cached.parquet"
    df.to_parquet(path)

    path_str = str(path)
    first = _read_parquet(path_str)
    second = _read_parquet(path_str)

    # Same object in memory → cache is working
    assert first is second


def test_read_parquet_corrupted_file_returns_none(tmp_path):
    bad = tmp_path / "bad.parquet"
    bad.write_bytes(b"this is not a valid parquet file")

    result = _read_parquet(str(bad))
    assert result is None


# ── invalidate_cache ──────────────────────────────────────────────────────────

def test_invalidate_cache_allows_re_read(tmp_path):
    """After invalidation, a modified file should be re-read from disk."""
    df_v1 = pd.DataFrame({"val": [1]})
    path = tmp_path / "versioned.parquet"
    df_v1.to_parquet(path)

    path_str = str(path)
    r1 = _read_parquet(path_str)
    assert r1 is not None

    invalidate_cache()

    # Overwrite the file with different data
    df_v2 = pd.DataFrame({"val": [99]})
    df_v2.to_parquet(path)

    r2 = _read_parquet(path_str)
    assert r2 is not None
    assert r2["val"].iloc[0] == 99
