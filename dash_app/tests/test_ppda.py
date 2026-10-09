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


def test_compute_field_tilt_ratio_of_sums():
    """
    Season Field Tilt = Σ team FT passes ÷ Σ (team + opponent) FT passes,
    not the mean of per-match tilts.

    m1: A 9, B 1   (A tilt 90 %, denominator 10)
    m2: A 10, B 90 (A tilt 10 %, denominator 100)
    m3: no final-third passes at all → zero denominator, contributes nothing
    Mean of matches would give A 50 %; ratio of sums gives 19 / 110.
    """
    rows = (
        [{"is_pass": True, "team_name": "A", "x_from_own_goal": 80.0, "match_id": "m1"}] * 9
        + [{"is_pass": True, "team_name": "B", "x_from_own_goal": 80.0, "match_id": "m1"}] * 1
        + [{"is_pass": True, "team_name": "A", "x_from_own_goal": 80.0, "match_id": "m2"}] * 10
        + [{"is_pass": True, "team_name": "B", "x_from_own_goal": 80.0, "match_id": "m2"}] * 90
        + [{"is_pass": True, "team_name": "A", "x_from_own_goal": 30.0, "match_id": "m3"}] * 5
        + [{"is_pass": True, "team_name": "B", "x_from_own_goal": 30.0, "match_id": "m3"}] * 5
    )
    result = compute_field_tilt(_make_events(rows)).set_index("team")

    assert result.loc["A", "field_tilt"] == pytest.approx(19 / 110 * 100, abs=0.01)
    assert result.loc["B", "field_tilt"] == pytest.approx(91 / 110 * 100, abs=0.01)
    assert result.loc["A", "final_third_passes"] == 19
    assert result.loc["B", "final_third_passes"] == 91


def test_compute_field_tilt_counts_matches_with_zero_team_passes():
    """
    A match where the team has no final-third passes but the opponent does
    still adds the opponent's passes to the team's denominator.
    m1: A 5, B 5; m2: A 0, B 10 → A = 5 / 20 = 25 %.
    """
    rows = (
        [{"is_pass": True, "team_name": "A", "x_from_own_goal": 80.0, "match_id": "m1"}] * 5
        + [{"is_pass": True, "team_name": "B", "x_from_own_goal": 80.0, "match_id": "m1"}] * 5
        + [{"is_pass": True, "team_name": "A", "x_from_own_goal": 30.0, "match_id": "m2"}] * 3
        + [{"is_pass": True, "team_name": "B", "x_from_own_goal": 80.0, "match_id": "m2"}] * 10
    )
    result = compute_field_tilt(_make_events(rows)).set_index("team")

    assert result.loc["A", "field_tilt"] == pytest.approx(25.0, abs=0.01)
    assert result.loc["B", "field_tilt"] == pytest.approx(75.0, abs=0.01)


# ── load_season_events: coordinate frame ─────────────────────────────────────

def _orientation_csv(path) -> None:
    """
    One synthetic match in the raw Opta frame: every team attacks towards
    x = 100 in both halves. Each team-half has 2 shots at high x, 2 GK events
    at low x and 4 passes into the final third.
    """
    rows = []
    eid = 0
    for team, position in (("Home FC", "home"), ("Away FC", "away")):
        for period in (1, 2):
            minute = 10 if period == 1 else 60
            for event, x in (
                [("Miss", 88.0), ("Attempt Saved", 91.0)]
                + [("Save", 5.0), ("Claim", 7.0)]
                + [("Pass", 80.0)] * 4
            ):
                eid += 1
                rows.append({
                    "event_id": eid, "event": event, "period_id": period,
                    "time_min": minute, "time_sec": eid % 60,
                    "team_name": team, "team_position": position,
                    "x": x, "y": 50.0, "outcome": 1, "match_id": "orient1",
                })
    pd.DataFrame(rows).to_csv(path, index=False)


def test_load_season_events_keeps_team_relative_frame(tmp_path, monkeypatch):
    """
    Shots must stay at high x and GK events at low x after load_season_events,
    in both halves and for both home and away teams. Fails if x is flipped by
    home/away or period (the raw CSVs are already team-relative).
    """
    import src.analytics.ppda as ppda

    events_dir = tmp_path / "serie_a_test_season" / "events"
    events_dir.mkdir(parents=True)
    _orientation_csv(events_dir / "1_Home_Away_orient1.csv")
    monkeypatch.setattr(ppda, "RAW_DATA_DIR", tmp_path)

    events = ppda.load_season_events("test_season")
    assert not events.empty

    shots = events[events["event"].isin(["Miss", "Attempt Saved"])]
    gk = events[events["event"].isin(["Save", "Claim"])]
    for (team, period), grp in shots.groupby(["team_name", "period_id"]):
        assert (grp["x_from_own_goal"] > 66.67).all(), (team, period)
    for (team, period), grp in gk.groupby(["team_name", "period_id"]):
        assert (grp["x_from_own_goal"] < 33.33).all(), (team, period)
    # Every team-half is represented (2 teams × 2 halves)
    assert shots.groupby(["team_name", "period_id"]).ngroups == 4
    assert gk.groupby(["team_name", "period_id"]).ngroups == 4

    # Downstream: all 16 passes per team-pair are final-third passes → 50/50
    tilt = ppda.compute_field_tilt(events).set_index("team")
    assert tilt.loc["Home FC", "final_third_passes"] == 8
    assert tilt.loc["Away FC", "final_third_passes"] == 8
    assert tilt.loc["Home FC", "field_tilt"] == pytest.approx(50.0, abs=0.01)
