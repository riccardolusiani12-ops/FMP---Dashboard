"""
Tests for the penalty-box x threshold used by N2 "Inside box" classification
in ``src.analytics.defensive_structure`` — Fase 2c sanity-check follow-up.

OPP_BOX_X_MIN (previously 83.5, a dead constant never read by the
classification logic) was removed; the real threshold used by the "cross
into the box" branch of ``compute_defensive_transitions()`` is ``BOX_X``
(83.33, Opta-normalised). These tests pin that value and confirm the
boundary behaviour with a minimal synthetic transition.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.analytics.defensive_structure import (
    BOX_X,
    OPP_BOX_Y_MAX,
    OPP_BOX_Y_MIN,
    compute_defensive_transitions,
)


def _make_event(
    event_id: int,
    team_name: str,
    type_id: int,
    x: float,
    y: float,
    time_min: int,
    time_sec: int,
    period: int = 1,
    outcome: int = 1,
    poss_id: int = 1,
    poss_origin: str = "open_play",
    **extra,
) -> dict:
    row = {
        "event_id": event_id,
        "team_name": team_name,
        "type_id": type_id,
        "x": x,
        "y": y,
        "minute": time_min,
        "second": time_sec,
        "period": period,
        "outcome": outcome,
        "poss_id": poss_id,
        "poss_origin": poss_origin,
        "_match_sec": time_min * 60 + time_sec,
    }
    row.update(extra)
    return row


def _build_transition_df(cross_pass_end_x: float) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Minimal two-event transition: our team is Dispossessed (type_id=50) in
    the opponent's offensive half (trigger, Group B), then — inside the
    25s transition window — the opponent completes a cross whose
    Pass End X is the value under test. This exercises the "N2: cross into
    the box" branch (Pass End X >= BOX_X and cross qualifier present).
    """
    events = [
        _make_event(
            1, "Bologna", type_id=50, x=60.0, y=50.0,
            time_min=10, time_sec=0,
        ),
        _make_event(
            2, "Roma", type_id=1, x=70.0, y=50.0,
            time_min=10, time_sec=5,
            Cross="Yes", **{"Pass End X": cross_pass_end_x, "Pass End Y": 50.0},
        ),
    ]
    full_df = pd.DataFrame(events)
    team_df = full_df[full_df["team_name"] == "Bologna"].copy()
    opp_df = full_df[full_df["team_name"] == "Roma"].copy()
    return team_df, opp_df, full_df


class TestBoxThresholdConstant:
    """OPP_BOX_X_MIN was removed; BOX_X is the single source of truth."""

    def test_box_x_is_canonical_opta_value(self):
        assert BOX_X == pytest.approx(83.33)

    def test_opp_box_x_min_no_longer_defined(self):
        import src.analytics.defensive_structure as ds
        assert not hasattr(ds, "OPP_BOX_X_MIN")


class TestInsideBoxClassificationBoundary:
    """x = 83.4 is Inside box; x = 83.3 is not (BOX_X = 83.33 boundary)."""

    def test_cross_at_83_4_is_inside_box_n2(self):
        team_df, opp_df, full_df = _build_transition_df(cross_pass_end_x=83.4)
        result = compute_defensive_transitions(team_df, opp_df, full_df, "bologna")
        assert result["qualified_transitions"] == 1
        assert result["outcome_distribution"] == {"N1": 0, "N2": 1, "N3": 0}

    def test_cross_at_83_3_is_not_inside_box(self):
        team_df, opp_df, full_df = _build_transition_df(cross_pass_end_x=83.3)
        result = compute_defensive_transitions(team_df, opp_df, full_df, "bologna")
        assert result["qualified_transitions"] == 1
        assert result["outcome_distribution"]["N2"] == 0
