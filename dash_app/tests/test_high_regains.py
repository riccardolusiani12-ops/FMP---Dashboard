"""
Tests for High Regains Analysis — ``src.analytics.high_regains``
=================================================================
Validates detection, linkage, KPI computation, and edge-case handling.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.analytics.high_regains import (
    HIGH_REGAIN_TYPES,
    HIGH_REGAIN_X_MIN,
    WINDOW_SEC,
    _empty_linked_df,
    _match_sec,
    compute_high_regain_kpis,
    detect_high_regains,
    link_regains_to_shots,
)


# ═══════════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════

def _make_event(
    event: str = "Pass",
    type_id: int = 1,
    x: float = 50.0,
    y: float = 50.0,
    time_min: int = 10,
    time_sec: int = 0,
    period_id: int = 1,
    outcome: int = 1,
    team_name: str = "Inter",
    player_name: str = "Player A",
    event_id: int = 1,
    **extra,
) -> dict:
    """Create a single event row as a dict."""
    row = {
        "event": event,
        "type_id": type_id,
        "x": x,
        "y": y,
        "time_min": time_min,
        "time_sec": time_sec,
        "period_id": period_id,
        "outcome": outcome,
        "team_name": team_name,
        "player_name": player_name,
        "event_id": event_id,
    }
    row.update(extra)
    return row


def _make_match_df(events: list[dict]) -> pd.DataFrame:
    """Build a DataFrame from a list of event dicts."""
    return pd.DataFrame(events)


@pytest.fixture
def basic_match():
    """
    A minimal match with:
    - 2 high regains for Inter (ball recovery at x=70, interception at x=80)
    - 1 shot by Inter within 10s of the first regain (Goal at x=92)
    - 1 shot by Inter 60s after the second regain (too late to link)
    """
    events = [
        # Ball recovery in attacking third → high regain #1
        _make_event("Ball recovery", 49, x=70, y=40, time_min=10, time_sec=0,
                     team_name="Inter", player_name="Barella", event_id=1),
        # Pass after recovery
        _make_event("Pass", 1, x=75, y=45, time_min=10, time_sec=3,
                     team_name="Inter", player_name="Calhanoglu", event_id=2),
        # Shot (Goal) within 10s → should link to regain #1
        _make_event("Goal", 16, x=92, y=50, time_min=10, time_sec=8,
                     team_name="Inter", player_name="Lautaro", event_id=3),

        # Interception in attacking third → high regain #2
        _make_event("Interception", 74, x=80, y=60, time_min=30, time_sec=0,
                     team_name="Inter", player_name="Bastoni", event_id=4),
        # Pass
        _make_event("Pass", 1, x=82, y=55, time_min=30, time_sec=5,
                     team_name="Inter", player_name="Mkhitaryan", event_id=5),
        # Shot 60s later (too far) → should NOT link
        _make_event("Miss", 13, x=88, y=48, time_min=31, time_sec=0,
                     team_name="Inter", player_name="Thuram", event_id=6),

        # Opponent events (should be ignored)
        _make_event("Ball recovery", 49, x=75, y=30, time_min=15, time_sec=0,
                     team_name="Milan", player_name="Tonali", event_id=7),
        _make_event("Pass", 1, x=50, y=50, time_min=15, time_sec=5,
                     team_name="Milan", player_name="Leao", event_id=8),
    ]
    return _make_match_df(events)


@pytest.fixture
def match_with_tackle():
    """Match with successful and failed tackles."""
    events = [
        # Successful tackle in attacking third
        _make_event("Tackle", 4, x=72, y=35, time_min=5, time_sec=0,
                     team_name="Inter", outcome=1, event_id=1),
        # Failed tackle in attacking third (should be filtered)
        _make_event("Tackle", 4, x=75, y=45, time_min=6, time_sec=0,
                     team_name="Inter", outcome=0, event_id=2),
        # Shot within window
        _make_event("Saved Shot", 15, x=90, y=50, time_min=5, time_sec=10,
                     team_name="Inter", event_id=3),
    ]
    return _make_match_df(events)


@pytest.fixture
def match_with_set_piece():
    """High regain that comes from a set piece (should be filtered in open play mode)."""
    events = [
        # Ball recovery from a corner
        _make_event("Ball recovery", 49, x=85, y=60, time_min=20, time_sec=0,
                     team_name="Inter", event_id=1,
                     **{"Corner taken": "Si"}),
        # Shot
        _make_event("Goal", 16, x=95, y=50, time_min=20, time_sec=5,
                     team_name="Inter", event_id=2),
    ]
    return _make_match_df(events)


@pytest.fixture
def match_no_regains():
    """Match with no recovery events at all."""
    events = [
        _make_event("Pass", 1, x=50, y=50, time_min=10, time_sec=0,
                     team_name="Inter", event_id=1),
        _make_event("Miss", 13, x=85, y=50, time_min=10, time_sec=5,
                     team_name="Inter", event_id=2),
    ]
    return _make_match_df(events)


@pytest.fixture
def match_deep_regain():
    """Ball recovery in own half (x=30) — should NOT be high regain."""
    events = [
        _make_event("Ball recovery", 49, x=30, y=50, time_min=10, time_sec=0,
                     team_name="Inter", event_id=1),
        _make_event("Goal", 16, x=92, y=50, time_min=10, time_sec=10,
                     team_name="Inter", event_id=2),
    ]
    return _make_match_df(events)


# ═══════════════════════════════════════════════════════════════════════════════
# TESTS — detect_high_regains
# ═══════════════════════════════════════════════════════════════════════════════


class TestDetectHighRegains:

    def test_detects_correct_count(self, basic_match):
        hr = detect_high_regains(basic_match, "Inter")
        assert len(hr) == 2  # Ball recovery + Interception

    def test_filters_opponent_events(self, basic_match):
        hr = detect_high_regains(basic_match, "Inter")
        # Milan's ball recovery should not be included
        assert all(
            "inter" in str(row.get("team_name", "")).lower()
            or "inter" in str(row.get("team", "")).lower()
            for _, row in hr.iterrows()
        )

    def test_filters_deep_regains(self, match_deep_regain):
        hr = detect_high_regains(match_deep_regain, "Inter")
        assert len(hr) == 0

    def test_filters_failed_tackles(self, match_with_tackle):
        hr = detect_high_regains(match_with_tackle, "Inter")
        assert len(hr) == 1  # Only the successful tackle

    def test_filters_set_piece_regains(self, match_with_set_piece):
        hr = detect_high_regains(match_with_set_piece, "Inter", open_play_only=True)
        assert len(hr) == 0

    def test_includes_set_piece_when_disabled(self, match_with_set_piece):
        hr = detect_high_regains(match_with_set_piece, "Inter", open_play_only=False)
        assert len(hr) == 1

    def test_custom_x_threshold(self, basic_match):
        # Higher threshold: only the interception at x=80 should pass
        hr = detect_high_regains(basic_match, "Inter", x_min=75.0)
        assert len(hr) == 1
        assert hr.iloc[0]["x"] >= 75.0

    def test_no_regains_for_unknown_team(self, basic_match):
        hr = detect_high_regains(basic_match, "Juventus")
        assert len(hr) == 0

    def test_empty_df(self):
        empty = pd.DataFrame(columns=["event", "type_id", "x", "y",
                                       "time_min", "time_sec", "period_id",
                                       "outcome", "team_name"])
        hr = detect_high_regains(empty, "Inter")
        assert len(hr) == 0

    def test_adds_match_sec_column(self, basic_match):
        hr = detect_high_regains(basic_match, "Inter")
        assert "_match_sec" in hr.columns
        # First regain at 10:00 → 600s
        assert hr.iloc[0]["_match_sec"] == pytest.approx(600.0)


# ═══════════════════════════════════════════════════════════════════════════════
# TESTS — link_regains_to_shots
# ═══════════════════════════════════════════════════════════════════════════════

class TestLinkRegainsToShots:

    def test_links_within_window(self, basic_match):
        hr = detect_high_regains(basic_match, "Inter")
        linked = link_regains_to_shots(basic_match, hr, "Inter", window_sec=15)
        assert len(linked) == 1  # Only 1st regain links (2nd is 60s away)

    def test_correct_dt(self, basic_match):
        hr = detect_high_regains(basic_match, "Inter")
        linked = link_regains_to_shots(basic_match, hr, "Inter", window_sec=15)
        assert len(linked) == 1
        # Regain at 10:00, shot at 10:08 → dt=8s
        assert linked.iloc[0]["dt_to_shot_sec"] == pytest.approx(8.0)

    def test_shot_is_goal_flag(self, basic_match):
        hr = detect_high_regains(basic_match, "Inter")
        linked = link_regains_to_shots(basic_match, hr, "Inter", window_sec=15)
        assert linked.iloc[0]["shot_is_goal"] == True  # noqa: E712 — numpy bool

    def test_wider_window_links_more(self, basic_match):
        hr = detect_high_regains(basic_match, "Inter")
        linked = link_regains_to_shots(basic_match, hr, "Inter", window_sec=120)
        assert len(linked) == 2  # Both regains now link

    def test_empty_regains(self, basic_match):
        empty_hr = pd.DataFrame()
        linked = link_regains_to_shots(basic_match, empty_hr, "Inter")
        assert len(linked) == 0
        assert isinstance(linked, pd.DataFrame)

    def test_no_shots_in_match(self, match_no_regains):
        # Create a match with regains but no shots
        events = [
            _make_event("Ball recovery", 49, x=75, y=50, time_min=10,
                         time_sec=0, team_name="Inter", event_id=1),
            _make_event("Pass", 1, x=80, y=50, time_min=10, time_sec=5,
                         team_name="Inter", event_id=2),
        ]
        df = _make_match_df(events)
        hr = detect_high_regains(df, "Inter")
        linked = link_regains_to_shots(df, hr, "Inter")
        assert len(linked) == 0

    def test_linked_df_schema(self, basic_match):
        hr = detect_high_regains(basic_match, "Inter")
        linked = link_regains_to_shots(basic_match, hr, "Inter", window_sec=15)
        expected_cols = {
            "regain_idx", "regain_type", "regain_player",
            "regain_x", "regain_y", "regain_minute", "regain_second",
            "regain_match_sec",
            "shot_idx", "shot_type", "shot_player",
            "shot_x", "shot_y", "shot_minute", "shot_second",
            "shot_is_goal", "dt_to_shot_sec",
        }
        assert expected_cols.issubset(set(linked.columns))


# ═══════════════════════════════════════════════════════════════════════════════
# TESTS — compute_high_regain_kpis
# ═══════════════════════════════════════════════════════════════════════════════

class TestComputeHighRegainKpis:

    def test_basic_kpis(self, basic_match):
        kpis = compute_high_regain_kpis(basic_match, "Inter", window_sec=15)
        assert kpis["total_high_regains"] == 2
        assert kpis["linked_to_shot"] == 1
        assert kpis["linked_to_goal"] == 1
        assert 0.0 <= kpis["shot_conversion_rate"] <= 1.0
        assert kpis["shot_conversion_rate"] == pytest.approx(0.5)
        assert kpis["goal_conversion_rate"] == pytest.approx(0.5)
        assert kpis["avg_time_to_shot_sec"] == pytest.approx(8.0)

    def test_no_regains(self, match_no_regains):
        kpis = compute_high_regain_kpis(match_no_regains, "Inter")
        assert kpis["total_high_regains"] == 0
        assert kpis["linked_to_shot"] == 0
        assert kpis["shot_conversion_rate"] == 0.0

    def test_type_breakdown(self, basic_match):
        kpis = compute_high_regain_kpis(basic_match, "Inter")
        breakdown = kpis["regain_types_breakdown"]
        assert "ball recovery" in breakdown
        assert "interception" in breakdown
        assert breakdown["ball recovery"] == 1
        assert breakdown["interception"] == 1

    def test_kpi_keys_complete(self, basic_match):
        kpis = compute_high_regain_kpis(basic_match, "Inter")
        expected_keys = {
            "total_high_regains", "linked_to_shot", "linked_to_goal",
            "shot_conversion_rate", "goal_conversion_rate",
            "avg_time_to_shot_sec", "total_pv_from_regains",
            "avg_pv_per_regain", "top_regain_zones",
            "regain_types_breakdown", "linked_details", "window_sec",
        }
        assert expected_keys == set(kpis.keys())

    def test_empty_match(self):
        empty = pd.DataFrame(columns=["event", "type_id", "x", "y",
                                       "time_min", "time_sec", "period_id",
                                       "outcome", "team_name"])
        kpis = compute_high_regain_kpis(empty, "Inter")
        assert kpis["total_high_regains"] == 0

    def test_zone_breakdown(self, basic_match):
        kpis = compute_high_regain_kpis(basic_match, "Inter")
        zones = kpis["top_regain_zones"]
        assert isinstance(zones, list)
        for z in zones:
            assert "zone_x" in z
            assert "zone_y" in z
            assert "count" in z


# ═══════════════════════════════════════════════════════════════════════════════
# TESTS — edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:

    def test_regain_exactly_at_threshold(self):
        """Ball recovery at x=66.7 exactly should qualify."""
        events = [
            _make_event("Ball recovery", 49, x=66.7, y=50, time_min=10,
                         time_sec=0, team_name="Inter", event_id=1),
        ]
        df = _make_match_df(events)
        hr = detect_high_regains(df, "Inter")
        assert len(hr) == 1

    def test_regain_just_below_threshold(self):
        """Ball recovery at x=66.6 should NOT qualify."""
        events = [
            _make_event("Ball recovery", 49, x=66.6, y=50, time_min=10,
                         time_sec=0, team_name="Inter", event_id=1),
        ]
        df = _make_match_df(events)
        hr = detect_high_regains(df, "Inter")
        assert len(hr) == 0

    def test_near_simultaneous_regain_and_shot(self):
        """Regain and shot 1s apart → dt=1, should link."""
        events = [
            _make_event("Ball recovery", 49, x=80, y=50, time_min=20,
                         time_sec=0, team_name="Inter", event_id=1),
            _make_event("Goal", 16, x=92, y=50, time_min=20,
                         time_sec=1, team_name="Inter", event_id=2),
        ]
        df = _make_match_df(events)
        hr = detect_high_regains(df, "Inter")
        linked = link_regains_to_shots(df, hr, "Inter", window_sec=15)
        assert len(linked) == 1
        assert linked.iloc[0]["dt_to_shot_sec"] == pytest.approx(1.0)

    def test_multiple_regains_same_shot(self):
        """Multiple regains before the same shot — each should link independently."""
        events = [
            _make_event("Ball recovery", 49, x=70, y=40, time_min=10,
                         time_sec=0, team_name="Inter", event_id=1),
            _make_event("Interception", 74, x=75, y=45, time_min=10,
                         time_sec=3, team_name="Inter", event_id=2),
            _make_event("Goal", 16, x=92, y=50, time_min=10,
                         time_sec=8, team_name="Inter", event_id=3),
        ]
        df = _make_match_df(events)
        hr = detect_high_regains(df, "Inter")
        assert len(hr) == 2
        linked = link_regains_to_shots(df, hr, "Inter", window_sec=15)
        assert len(linked) == 2

    def test_second_half_timing(self):
        """Verify match_sec computation for second half events."""
        events = [
            _make_event("Ball recovery", 49, x=75, y=50, time_min=50,
                         time_sec=30, period_id=2, team_name="Inter",
                         event_id=1),
            _make_event("Goal", 16, x=92, y=50, time_min=50,
                         time_sec=40, period_id=2, team_name="Inter",
                         event_id=2),
        ]
        df = _make_match_df(events)
        hr = detect_high_regains(df, "Inter")
        assert len(hr) == 1
        # 2nd half: (2-1)*45*60 + 50*60 + 30 = 2700 + 3000 + 30 = 5730
        assert hr.iloc[0]["_match_sec"] == pytest.approx(5730.0)

    def test_empty_linked_df_schema(self):
        """The empty linked DataFrame should have all expected columns."""
        df = _empty_linked_df()
        assert len(df) == 0
        expected = {
            "regain_idx", "regain_type", "regain_player",
            "regain_x", "regain_y", "regain_minute", "regain_second",
            "regain_match_sec",
            "shot_idx", "shot_type", "shot_player",
            "shot_x", "shot_y", "shot_minute", "shot_second",
            "shot_is_goal", "dt_to_shot_sec",
        }
        assert expected == set(df.columns)
