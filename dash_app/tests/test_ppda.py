"""
Tests for src/analytics/ppda.py

Covers:
  - compute_ppda: formula correctness, sort order, empty-input guard
  - compute_field_tilt: percentage calculation, empty-input guard
  All tests use synthetic DataFrames — no CSV files touched.
"""
import numpy as np
import pandas as pd
import pytest

from src.analytics.ppda import compute_ppda, compute_field_tilt


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_events(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal events DataFrame with the columns compute_ppda expects."""
    defaults = {
        "is_pass": False,
        "is_regain": False,
        "x_from_own_goal": 50.0,
        "team_name": "Team A",
        "opponent": "Team B",
        "match_id": "match_1",
    }
    return pd.DataFrame([{**defaults, **r} for r in rows])


# ── compute_ppda ──────────────────────────────────────────────────────────────

def test_compute_ppda_empty_returns_empty():
    result = compute_ppda(pd.DataFrame())
    assert result.empty


def test_compute_ppda_basic_formula():
    """
    Team B presses Team A.
    Team A makes 10 passes in their own half (x_from_own_goal ≤ 60).
    Team B makes 2 ball recoveries in the pressing zone (x_from_own_goal ≥ 40).
    Expected: Team B PPDA = 10 / 2 = 5.0
    """
    rows = (
        # Team A passes in own half → Team B is the pressing team
        [{"is_pass": True, "team_name": "Team A", "opponent": "Team B",
          "x_from_own_goal": 40.0, "match_id": "m1"}] * 10
        +
        # Team B ball recoveries in pressing zone
        [{"is_regain": True, "team_name": "Team B", "opponent": "Team A",
          "x_from_own_goal": 45.0, "match_id": "m1"}] * 2
    )
    df = _make_events(rows)
    result = compute_ppda(df)

    assert not result.empty
    team_b_row = result[result["team"] == "Team B"]
    assert not team_b_row.empty
    assert team_b_row["PPDA"].iloc[0] == pytest.approx(5.0, rel=0.01)


def test_compute_ppda_excludes_passes_outside_zone():
    """
    Passes with x_from_own_goal > 60 (deep in opponent half) should NOT
    count toward the allowed-passes tally.
    """
    rows = (
        # 4 passes in zone (≤ 60) + 6 passes outside zone (> 60)
        [{"is_pass": True, "team_name": "A", "opponent": "B",
          "x_from_own_goal": 30.0, "match_id": "m1"}] * 4
        + [{"is_pass": True, "team_name": "A", "opponent": "B",
            "x_from_own_goal": 80.0, "match_id": "m1"}] * 6
        + [{"is_regain": True, "team_name": "B", "opponent": "A",
            "x_from_own_goal": 50.0, "match_id": "m1"}] * 2
    )
    df = _make_events(rows)
    result = compute_ppda(df)

    b_row = result[result["team"] == "B"]
    # Only 4 passes in zone / 2 recoveries = 2.0
    assert b_row["PPDA"].iloc[0] == pytest.approx(2.0, rel=0.01)


def test_compute_ppda_sorted_ascending():
    """Lower PPDA (more intense pressing) should appear first."""
    rows = (
        # Team B presses Team A: 10 passes / 5 recoveries = PPDA 2.0
        [{"is_pass": True, "team_name": "Team A", "opponent": "Team B",
          "x_from_own_goal": 40.0, "match_id": "m1"}] * 10
        + [{"is_regain": True, "team_name": "Team B", "opponent": "Team A",
            "x_from_own_goal": 45.0, "match_id": "m1"}] * 5
        +
        # Team A presses Team B: 10 passes / 2 recoveries = PPDA 5.0
        [{"is_pass": True, "team_name": "Team B", "opponent": "Team A",
          "x_from_own_goal": 40.0, "match_id": "m1"}] * 10
        + [{"is_regain": True, "team_name": "Team A", "opponent": "Team B",
            "x_from_own_goal": 45.0, "match_id": "m1"}] * 2
    )
    df = _make_events(rows)
    result = compute_ppda(df)

    assert result["PPDA"].iloc[0] < result["PPDA"].iloc[1]


def test_compute_ppda_no_recoveries_excluded():
    """Teams with zero ball recoveries should not appear in the output."""
    rows = [
        {"is_pass": True, "team_name": "A", "opponent": "B",
         "x_from_own_goal": 40.0, "match_id": "m1"},
    ]
    df = _make_events(rows)
    result = compute_ppda(df)
    # Team B would be pressing team but has 0 recoveries → excluded
    assert result.empty or (result["ball_recoveries"] > 0).all()


# ── compute_field_tilt ────────────────────────────────────────────────────────

def test_compute_field_tilt_empty_returns_empty():
    result = compute_field_tilt(pd.DataFrame())
    assert result.empty


def test_compute_field_tilt_basic():
    """
    Single match: Team A makes 6 final-third passes, Team B makes 4.
    Team A field tilt = 60%, Team B = 40%.
    """
    rows = (
        [{"is_pass": True, "team_name": "Team A",
          "x_from_own_goal": 75.0, "match_id": "m1"}] * 6
        + [{"is_pass": True, "team_name": "Team B",
            "x_from_own_goal": 75.0, "match_id": "m1"}] * 4
    )
    df = _make_events(rows)
    result = compute_field_tilt(df)

    a_row = result[result["team"] == "Team A"]
    b_row = result[result["team"] == "Team B"]

    assert a_row["field_tilt"].iloc[0] == pytest.approx(60.0, abs=0.1)
    assert b_row["field_tilt"].iloc[0] == pytest.approx(40.0, abs=0.1)


def test_compute_field_tilt_ignores_own_half_passes():
    """Passes with x_from_own_goal ≤ 66.67 must not count toward field tilt."""
    rows = (
        # Only these should count (x > 66.67)
        [{"is_pass": True, "team_name": "A", "x_from_own_goal": 80.0, "match_id": "m1"}] * 3
        # These should be ignored
        + [{"is_pass": True, "team_name": "A", "x_from_own_goal": 50.0, "match_id": "m1"}] * 10
    )
    df = _make_events(rows)
    result = compute_field_tilt(df)

    # Only Team A in final third → field tilt should be 100%
    a_row = result[result["team"] == "A"]
    assert a_row["field_tilt"].iloc[0] == pytest.approx(100.0, abs=0.1)
