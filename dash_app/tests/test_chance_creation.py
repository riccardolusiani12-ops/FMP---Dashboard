"""
Tests for src/analytics/chance_creation.py and src/analytics/possession_value.py

Covers:
  - classify_attack_origin() with mocked event sequences (one per origin)
  - PossessionValueModel.get_chain_pv() with a known simple chain
  - PossessionValueModel.build() with synthetic data
  - ChanceCreationAnalyzer integration with a mini match DataFrame
  - Shot quality tier classification
  - Shot metrics computation
  - PV model save/load roundtrip
"""

import numpy as np
import pandas as pd
import pytest

from src.analytics.chance_creation import (
    classify_attack_origin,
    classify_shot_quality,
    ChanceCreationAnalyzer,
    _is_in_penalty_box,
    ORIGIN_LABELS,
)
from src.analytics.possession_value import (
    PossessionValueModel,
    get_xt_zone,
    X_ZONES,
    Y_ZONES,
    _fallback_xt_grid,
)


# ═══════════════════════════════════════════════════════════════════════════════
# FIXTURES & HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _make_pv_model_with_known_grid() -> PossessionValueModel:
    """
    Create a PV model with a hand-crafted xT grid for predictable testing.

    The grid has linearly increasing values along the x-axis:
        xT[col][row] = col / 15 * 0.40  → ranges from 0.0 to 0.40
    """
    model = PossessionValueModel()
    model.xT = np.zeros((X_ZONES, Y_ZONES), dtype=np.float64)
    for col in range(X_ZONES):
        for row in range(Y_ZONES):
            model.xT[col, row] = col / 15.0 * 0.40
    model.P_shot = np.full((X_ZONES, Y_ZONES), 0.05)
    model.P_goal = np.full((X_ZONES, Y_ZONES), 0.01)
    model._built = True
    return model


def _event_row(**kwargs) -> dict:
    """Build a minimal event row dict with defaults."""
    defaults = {
        "event": "Pass",
        "event_type": "pass",
        "type_id": 1,
        "x": 50.0,
        "y": 50.0,
        "time_min": 10,
        "time_sec": 0,
        "minute": 10,
        "second": 0,
        "period": 1,
        "period_id": 1,
        "team_name": "Test FC",
        "team_id": "t1",
        "player_name": "Player A",
        "outcome": 1,
        "Pass End X": None,
        "Pass End Y": None,
        "Through ball": None,
        "Cross": None,
        "Long ball": None,
        "Corner taken": None,
        "Free kick taken": None,
        "Throw In": None,
        "Penalty": None,
        "Goal Kick": None,
        "Gk kick from hands": None,
        "poss_id": 1,
        "poss_origin": "open_play",
        "_match_sec": 600,
        "poss_team_name": "Test FC",
        "Related event ID": None,
        "Head": None,
        "Right footed": None,
        "Volley": None,
        "Big Chance": None,
        "1 on 1": None,
        "Fast break": None,
        "From corner": None,
        "Set piece": None,
        "Free kick": None,
        "Individual Play": None,
        "own goal": None,
    }
    defaults.update(kwargs)
    return defaults


def _shot_row(**kwargs) -> dict:
    """Build a minimal shot event row."""
    defaults = _event_row(
        event="Saved Shot",
        event_type="saved shot",
        type_id=15,
        x=90.0,
        y=50.0,
        time_min=12,
        time_sec=30,
        minute=12,
        second=30,
        _match_sec=750,
    )
    defaults.update(kwargs)
    return defaults


def _make_poss_df(events: list[dict]) -> pd.DataFrame:
    """Build a possession events DataFrame from a list of event dicts."""
    df = pd.DataFrame(events)
    if "_match_sec" not in df.columns:
        df["_match_sec"] = df.get("minute", 0) * 60 + df.get("second", 0)
    return df


# ═══════════════════════════════════════════════════════════════════════════════
# xT ZONE HELPER TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestXtZone:
    def test_origin(self):
        assert get_xt_zone(0, 0) == (0, 0)

    def test_centre(self):
        col, row = get_xt_zone(50, 50)
        assert col == 8  # 50 / 6.25 = 8
        assert row == 6  # 50 / 8.33 ≈ 6

    def test_far_corner(self):
        col, row = get_xt_zone(100, 100)
        assert col == 15
        assert row == 11

    def test_penalty_spot_zone(self):
        # Penalty spot ≈ x=88.5, y=50
        col, row = get_xt_zone(88.5, 50.0)
        assert col == 14  # 88.5 / 6.25 = 14.16 → 14
        assert row == 6   # 50 / 8.33 ≈ 6


# ═══════════════════════════════════════════════════════════════════════════════
# PENALTY BOX HELPER
# ═══════════════════════════════════════════════════════════════════════════════

class TestPenaltyBox:
    def test_centre_of_box(self):
        assert _is_in_penalty_box(90.0, 50.0) is True

    def test_outside_x(self):
        assert _is_in_penalty_box(80.0, 50.0) is False

    def test_outside_y_low(self):
        assert _is_in_penalty_box(90.0, 15.0) is False

    def test_outside_y_high(self):
        assert _is_in_penalty_box(90.0, 85.0) is False

    def test_edge_of_box(self):
        assert _is_in_penalty_box(83.33, 21.1) is True


# ═══════════════════════════════════════════════════════════════════════════════
# ATTACK ORIGIN CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════════

class TestClassifyAttackOrigin:
    """One test per origin type, verifying priority rules."""

    def test_set_piece_from_corner(self):
        """Shot after a corner kick → Set Piece."""
        events = [
            _event_row(event_type="pass", **{"Corner taken": "Si"},
                       _match_sec=600, minute=10, second=0),
            _event_row(event_type="pass", x=85.0, y=30.0,
                       _match_sec=604, minute=10, second=4,
                       **{"Pass End X": 90.0, "Pass End Y": 45.0}),
            _shot_row(_match_sec=607, minute=10, second=7),
        ]
        poss_df = _make_poss_df(events)
        shot = pd.Series(events[-1])
        result = classify_attack_origin(shot, poss_df, "corner", 600.0)
        assert result == "Set Piece"

    def test_set_piece_from_penalty(self):
        """Penalty kick → Set Piece."""
        shot = pd.Series(_shot_row(Penalty="Si", _match_sec=700))
        poss_df = _make_poss_df([_shot_row(Penalty="Si", _match_sec=700)])
        result = classify_attack_origin(shot, poss_df, "penalty", 700.0)
        assert result == "Set Piece"

    def test_counter_attack_now_combination(self):
        """Recovery in middle third + shot within 8s → Combination (Counter removed)."""
        events = [
            _event_row(event_type="ball recovery", x=40.0, y=50.0,
                       _match_sec=600, minute=10, second=0),
            _event_row(event_type="pass", x=60.0, y=50.0,
                       _match_sec=603, minute=10, second=3,
                       **{"Pass End X": 85.0, "Pass End Y": 50.0}),
            _shot_row(x=90.0, y=50.0, _match_sec=607, minute=10, second=7),
        ]
        poss_df = _make_poss_df(events)
        shot = pd.Series(events[-1])
        result = classify_attack_origin(shot, poss_df, "open_play", 600.0)
        assert result == "Combination"

    def test_high_regain(self):
        """Recovery in attacking final third (x >= 66.67) + shot within 8s → High Regain."""
        events = [
            _event_row(event_type="ball recovery", x=80.0, y=33.0,
                       _match_sec=600, minute=10, second=0),
            _event_row(event_type="pass", x=79.0, y=32.0,
                       _match_sec=601, minute=10, second=1,
                       **{"Pass End X": 92.0, "Pass End Y": 34.0}),
            _shot_row(x=92.0, y=34.0, _match_sec=603, minute=10, second=3),
        ]
        poss_df = _make_poss_df(events)
        shot = pd.Series(events[-1])
        result = classify_attack_origin(shot, poss_df, "open_play", 600.0)
        assert result == "High Regain"

    def test_high_regain_not_counter_when_in_final_third(self):
        """Recovery at x=70 (final third) should be High Regain."""
        events = [
            _event_row(event_type="interception", x=70.0, y=50.0,
                       _match_sec=600, minute=10, second=0),
            _event_row(event_type="pass", x=75.0, y=45.0,
                       _match_sec=602, minute=10, second=2,
                       **{"Pass End X": 90.0, "Pass End Y": 50.0}),
            _shot_row(x=90.0, y=50.0, _match_sec=605, minute=10, second=5),
        ]
        poss_df = _make_poss_df(events)
        shot = pd.Series(events[-1])
        result = classify_attack_origin(shot, poss_df, "open_play", 600.0)
        assert result == "High Regain"

    def test_recovery_in_middle_third_is_combination(self):
        """Recovery at x=40 (middle third) + fast shot → Combination (Counter removed)."""
        events = [
            _event_row(event_type="tackle", x=40.0, y=50.0,
                       _match_sec=600, minute=10, second=0),
            _event_row(event_type="pass", x=60.0, y=50.0,
                       _match_sec=603, minute=10, second=3,
                       **{"Pass End X": 85.0, "Pass End Y": 50.0}),
            _shot_row(x=90.0, y=50.0, _match_sec=607, minute=10, second=7),
        ]
        poss_df = _make_poss_df(events)
        shot = pd.Series(events[-1])
        result = classify_attack_origin(shot, poss_df, "open_play", 600.0)
        assert result == "Combination"

    def test_high_regain_direct_score_from_opponent_error(self):
        """Goal scored directly from opponent error in final third → High Regain.

        Case B: the shot/goal is the ONLY play event in its possession;
        the previous possession (opponent) ends with an error at their
        own end (low x), which flips to the attacker's final third.
        Mirrors the real Lautaro Martínez goal (Inter-Torino 51').
        """
        # Previous possession: opponent passes ending in error at x=12.8
        opp_events = [
            _event_row(event_type="pass", x=22.4, y=71.4,
                       _match_sec=3057, minute=50, second=57,
                       team_name="Opponent FC"),
            _event_row(event_type="pass", x=14.0, y=82.4,
                       _match_sec=3058, minute=50, second=58,
                       outcome=0, team_name="Opponent FC"),
            _event_row(event_type="error", x=12.8, y=81.2,
                       _match_sec=3059, minute=50, second=59,
                       team_name="Opponent FC"),
        ]
        # Current possession: attacker scores directly (no recovery event)
        goal_event = _shot_row(
            event_type="goal", type_id=16,
            x=93.7, y=33.0,
            _match_sec=3060, minute=51, second=0,
            team_name="My Team FC",
        )

        # Build full match_df with poss_id assignments
        for evt in opp_events:
            evt["poss_id"] = 282
        goal_event["poss_id"] = 283

        match_df = pd.DataFrame(opp_events + [goal_event])
        match_df["_match_sec"] = match_df.get("_match_sec",
                                               match_df["minute"] * 60 + match_df["second"])

        poss_df = match_df[match_df["poss_id"] == 283].copy()
        shot = pd.Series(goal_event)

        result = classify_attack_origin(
            shot, poss_df, "open_play", 3060.0, match_df=match_df,
        )
        assert result == "High Regain"

    def test_direct_score_from_opponent_own_half_is_not_high_regain(self):
        """Opponent error in own half (our x < 66.67) → NOT High Regain."""
        opp_events = [
            _event_row(event_type="error", x=60.0, y=50.0,
                       _match_sec=600, minute=10, second=0,
                       team_name="Opponent FC"),
        ]
        goal_event = _shot_row(
            event_type="goal", type_id=16,
            x=55.0, y=50.0,
            _match_sec=602, minute=10, second=2,
            team_name="My Team FC",
        )
        for evt in opp_events:
            evt["poss_id"] = 10
        goal_event["poss_id"] = 11

        match_df = pd.DataFrame(opp_events + [goal_event])
        match_df["_match_sec"] = match_df["minute"] * 60 + match_df["second"]

        poss_df = match_df[match_df["poss_id"] == 11].copy()
        shot = pd.Series(goal_event)

        result = classify_attack_origin(
            shot, poss_df, "open_play", 602.0, match_df=match_df,
        )
        assert result != "High Regain"

    def test_counter_too_slow_becomes_combination(self):
        """Recovery but shot after 8s → Combination (no Counter category)."""
        events = [
            _event_row(event_type="ball recovery", x=40.0, y=50.0,
                       _match_sec=600, minute=10, second=0),
            _event_row(event_type="pass", x=60.0, y=50.0,
                       _match_sec=606, minute=10, second=6,
                       **{"Pass End X": 85.0, "Pass End Y": 50.0}),
            _shot_row(x=90.0, y=50.0, _match_sec=610, minute=10, second=10),
        ]
        poss_df = _make_poss_df(events)
        shot = pd.Series(events[-1])
        result = classify_attack_origin(shot, poss_df, "open_play", 600.0)
        assert result == "Combination"

    def test_through_ball(self):
        """Pass with Through ball qualifier → Through Ball."""
        events = [
            _event_row(event_type="pass", x=60.0, y=50.0,
                       _match_sec=600, minute=10, second=0,
                       **{"Pass End X": 85.0, "Pass End Y": 50.0}),
            _event_row(event_type="pass", x=70.0, y=50.0,
                       _match_sec=605, minute=10, second=5,
                       **{"Through ball": "Si",
                          "Pass End X": 92.0, "Pass End Y": 45.0}),
            _shot_row(x=92.0, y=45.0, _match_sec=607, minute=10, second=7),
        ]
        poss_df = _make_poss_df(events)
        shot = pd.Series(events[-1])
        result = classify_attack_origin(shot, poss_df, "open_play", 600.0)
        assert result == "Through Ball"

    def test_cross(self):
        """Pass with Cross qualifier → Cross."""
        events = [
            _event_row(event_type="pass", x=70.0, y=50.0,
                       _match_sec=600, minute=10, second=0,
                       **{"Pass End X": 80.0, "Pass End Y": 20.0}),
            _event_row(event_type="pass", x=80.0, y=15.0,
                       _match_sec=605, minute=10, second=5,
                       **{"Cross": "Si",
                          "Pass End X": 92.0, "Pass End Y": 50.0}),
            _shot_row(x=92.0, y=50.0, _match_sec=607, minute=10, second=7),
        ]
        poss_df = _make_poss_df(events)
        shot = pd.Series(events[-1])
        result = classify_attack_origin(shot, poss_df, "open_play", 600.0)
        assert result == "Cross"

    def test_cross_from_wide_zone(self):
        """Pass from wide final-third zone (y<25, x≥66.67) → Cross."""
        events = [
            _event_row(event_type="pass", x=75.0, y=10.0,
                       _match_sec=605, minute=10, second=5,
                       **{"Pass End X": 90.0, "Pass End Y": 50.0}),
            _shot_row(x=90.0, y=50.0, _match_sec=607, minute=10, second=7),
        ]
        poss_df = _make_poss_df(events)
        shot = pd.Series(events[-1])
        result = classify_attack_origin(shot, poss_df, "open_play", 600.0)
        assert result == "Cross"

    def test_out_box_shot_becomes_combination(self):
        """Shot from outside the penalty box with no special qualifiers → Combination.

        'Out Box' has been removed as an origin dimension.  Shot location
        (in-box vs out-of-box) is tracked as a separate dimension in
        shot_metrics; the attack-origin column now uses Combination as the
        default for all patient-build-up shots regardless of distance.
        """
        events = [
            _event_row(event_type="pass", x=50.0, y=50.0,
                       _match_sec=600, minute=10, second=0,
                       **{"Pass End X": 75.0, "Pass End Y": 50.0}),
            _shot_row(x=75.0, y=50.0, _match_sec=607, minute=10, second=7),
        ]
        poss_df = _make_poss_df(events)
        shot = pd.Series(events[-1])
        result = classify_attack_origin(shot, poss_df, "open_play", 600.0)
        assert result == "Combination"

    def test_default_combination_play(self):
        """In-box shot with no special qualifiers → Combination (default)."""
        events = [
            _event_row(event_type="pass", x=70.0, y=50.0,
                       _match_sec=600, minute=10, second=0,
                       **{"Pass End X": 85.0, "Pass End Y": 50.0}),
            _event_row(event_type="pass", x=85.0, y=50.0,
                       _match_sec=605, minute=10, second=5,
                       **{"Pass End X": 90.0, "Pass End Y": 50.0}),
            _shot_row(x=90.0, y=50.0, _match_sec=607, minute=10, second=7),
        ]
        poss_df = _make_poss_df(events)
        shot = pd.Series(events[-1])
        result = classify_attack_origin(shot, poss_df, "open_play", 600.0)
        assert result == "Combination"

    def test_set_piece_takes_priority_over_combination(self):
        """Free-kick possession + fast shot within pass limit → Set Piece."""
        events = [
            _event_row(event_type="ball recovery", x=40.0, y=50.0,
                       _match_sec=600, minute=10, second=0,
                       **{"Free kick taken": "Si"}),
            _shot_row(x=90.0, y=50.0, _match_sec=605, minute=10, second=5),
        ]
        poss_df = _make_poss_df(events)
        shot = pd.Series(events[-1])
        result = classify_attack_origin(shot, poss_df, "free_kick", 600.0)
        assert result == "Set Piece"

    def test_through_ball_beats_cross_when_both_qualifiers(self):
        """
        Through Ball takes priority over Cross when both qualifiers are present.
        Through Ball is highest priority because the data qualifier is authoritative.
        """
        events = [
            _event_row(event_type="pass", x=73.5, y=85.2,
                       _match_sec=918, minute=15, second=18,
                       outcome=1,
                       **{"Cross": "1", "Through ball": "1"}),
            _shot_row(x=90.1, y=85.2, _match_sec=922, minute=15, second=22),
        ]
        poss_df = _make_poss_df(events)
        shot = pd.Series(events[-1])

        result = classify_attack_origin(shot, poss_df, "open_play", 918.0)
        assert result == "Through Ball", (
            f"Expected 'Through Ball' (highest priority) but got '{result}'. "
            "Through Ball qualifier is authoritative and overrides Cross."
        )

    def test_set_piece_lookback_into_previous_possession(self):
        """Corner in poss N → aerial split → shot in poss N+2 → Set Piece via lookback.

        Regression for Bastoni (min 24): corner kick was in a previous
        possession (possession boundary at the aerial duel), so the shot
        possession has poss_origin='open_play'.  The lookback must find
        the corner in the prior possession and classify as Set Piece.
        """
        corner = {**_event_row(event_type="pass", x=99.0, y=90.0,
                               _match_sec=1440, minute=24, second=0),
                  "poss_id": 50, "poss_origin": "corner",
                  "Corner taken": "Si"}
        aerial_opp = {**_event_row(event_type="aerial", x=90.0, y=45.0,
                                   _match_sec=1442, minute=24, second=2,
                                   team_name="Opponent FC"),
                      "poss_id": 51, "poss_origin": "open_play"}
        shot_event = {**_shot_row(x=91.0, y=44.0,
                                  _match_sec=1444, minute=24, second=4),
                      "poss_id": 52, "poss_origin": "open_play"}

        match_df = pd.DataFrame([corner, aerial_opp, shot_event])
        poss_df = match_df[match_df["poss_id"] == 52].copy()
        shot = pd.Series(shot_event)

        result = classify_attack_origin(
            shot, poss_df, "open_play", 1444.0, match_df=match_df,
        )
        assert result == "Set Piece", (
            f"Expected 'Set Piece' via lookback but got '{result}'. "
            "Corner in prior possession must be found when possession splits at aerial."
        )

    def test_set_piece_with_many_passes_becomes_open_play(self):
        """Set piece + > 5 passes in own half → Combination (default), NOT Set Piece.

        Regression for the Zielinski goal: Inter free kick in own third
        is played short and built up through many passes before the shot.
        The origin should be Combination, not Set Piece.
        """
        events = [
            _event_row(event_type="pass", x=20.0, y=50.0,
                       _match_sec=600, minute=10, second=0,
                       **{"Free kick taken": "Si"}),
            _event_row(event_type="pass", x=25.0, y=45.0,
                       _match_sec=603, minute=10, second=3),
            _event_row(event_type="pass", x=35.0, y=40.0,
                       _match_sec=608, minute=10, second=8),
            _event_row(event_type="pass", x=50.0, y=42.0,
                       _match_sec=614, minute=10, second=14),
            _event_row(event_type="pass", x=62.0, y=38.0,
                       _match_sec=620, minute=10, second=20),
            _event_row(event_type="pass", x=75.0, y=42.0,
                       _match_sec=627, minute=10, second=27),
            _event_row(event_type="pass", x=82.0, y=48.0,
                       _match_sec=633, minute=10, second=33),
            _shot_row(x=90.0, y=50.0, _match_sec=636, minute=10, second=36),
        ]
        poss_df = _make_poss_df(events)
        shot = pd.Series(events[-1])
        # poss_origin is free_kick but 6 passes were played → Combination
        result = classify_attack_origin(shot, poss_df, "free_kick", 600.0)
        assert result != "Set Piece", (
            f"Expected NOT 'Set Piece' (too many passes) but got '{result}'."
        )
        assert result == "Combination"

    def test_through_ball_beats_set_piece_lookback(self):
        """Through ball qualifier in a prior possession overrides set-piece detection.

        Regression for Barella shot (Inter-Como GW14, min 2'):
        Chain: free_kick possession (with through-ball pass) →
               opponent save possession → Inter shot possession.
        The through-ball pass is in poss N, the shot is in poss N+2.
        Even though poss N has a free_kick origin (within 15 s), the explicit
        through-ball qualifier must win because it is authoritative data.
        """
        # Poss N (Inter, free_kick): two passes, last one is a through ball
        prev_events = [
            {**_event_row(event_type="pass", x=45.9, y=50.0,
                          _match_sec=163, minute=2, second=43,
                          team_name="My Team FC"),
             "poss_id": 21, "poss_origin": "free_kick"},
            {**_event_row(event_type="pass", x=62.9, y=50.0,
                          _match_sec=172, minute=2, second=52,
                          team_name="My Team FC",
                          **{"Through ball": "Si",
                             "Intentional Assist": "Si",
                             "Pass End X": 76.8, "Pass End Y": 45.6}),
             "poss_id": 21, "poss_origin": "free_kick"},
        ]
        # Poss N+1 (opponent): goalkeeper save
        save_event = {
            **_event_row(event_type="save", x=11.0, y=50.0,
                         _match_sec=175, minute=2, second=55,
                         team_name="Opponent FC"),
            "poss_id": 22, "poss_origin": "open_play",
        }
        # Poss N+2 (Inter): shot
        shot_event = {
            **_shot_row(x=84.9, y=45.6, _match_sec=175,
                        minute=2, second=55,
                        team_name="My Team FC"),
            "poss_id": 23, "poss_origin": "open_play",
        }

        match_df = pd.DataFrame(prev_events + [save_event, shot_event])
        poss_df = match_df[match_df["poss_id"] == 23].copy()
        shot = pd.Series(shot_event)

        result = classify_attack_origin(
            shot, poss_df, "open_play", 175.0, match_df=match_df,
        )
        assert result == "Through Ball", (
            f"Expected 'Through Ball' but got '{result}'. "
            "Through Ball in prior possession must be detected via cross-possession lookback."
        )

    def test_cut_back(self):
        """Pass with Pull Back qualifier → Cut Back."""
        events = [
            _event_row(event_type="pass", x=88.0, y=5.0,
                       _match_sec=600, minute=10, second=0,
                       **{"Pass End X": 88.0, "Pass End Y": 30.0}),
            _event_row(event_type="pass", x=97.0, y=5.0,
                       _match_sec=605, minute=10, second=5,
                       **{"Pull Back": "Si",
                          "Pass End X": 90.0, "Pass End Y": 50.0}),
            _shot_row(x=90.0, y=50.0, _match_sec=607, minute=10, second=7),
        ]
        poss_df = _make_poss_df(events)
        shot = pd.Series(events[-1])
        result = classify_attack_origin(shot, poss_df, "open_play", 600.0)
        assert result == "Cut Back"


        """Cross → aerial duel (new poss) → goal should still be Cross.

        Mirrors real-world pattern (e.g. Thuram 61:40 in Inter-Torino):
          Poss N   (Inter): Bastoni cross at x=73.5, y=85.2, Cross=Si
          Poss N+1 (Torino): Biraghi aerial (lost)
          Poss N+2 (Inter): Thuram aerial (won) → Goal

        The cross lives in a different possession than the goal because
        the aerial duel triggers a possession break.
        """
        # Possession 100: same-team build-up ending with a cross
        prev_poss_events = [
            _event_row(event_type="pass", x=64.7, y=83.4,
                       _match_sec=3691, minute=61, second=31,
                       team_name="Inter", poss_id=100),
            _event_row(event_type="pass", x=83.0, y=93.2,
                       _match_sec=3694, minute=61, second=34,
                       team_name="Inter", poss_id=100),
            _event_row(event_type="pass", x=73.5, y=85.2,
                       _match_sec=3697, minute=61, second=37,
                       team_name="Inter", poss_id=100,
                       **{"Cross": "Si",
                          "Pass End X": 95.7, "Pass End Y": 40.7}),
        ]
        # Possession 101: opponent aerial (lost)
        opp_aerial = [
            _event_row(event_type="aerial", x=4.6, y=57.9,
                       _match_sec=3699, minute=61, second=39,
                       team_name="Torino", poss_id=101, outcome=0),
        ]
        # Possession 102: our aerial (won) + goal
        goal_poss_events = [
            _event_row(event_type="aerial", x=95.4, y=42.1,
                       _match_sec=3699, minute=61, second=39,
                       team_name="Inter", poss_id=102, outcome=1),
            _shot_row(event_type="goal", type_id=16,
                      x=95.0, y=43.5,
                      _match_sec=3700, minute=61, second=40,
                      team_name="Inter", poss_id=102),
        ]

        all_events = prev_poss_events + opp_aerial + goal_poss_events
        match_df = pd.DataFrame(all_events)
        match_df["_match_sec"] = match_df["minute"] * 60 + match_df["second"]

        poss_df = match_df[match_df["poss_id"] == 102].copy()
        shot = pd.Series(goal_poss_events[-1])

        result = classify_attack_origin(
            shot, poss_df, "open_play", 3699.0, match_df=match_df,
        )
        assert result == "Cross", (
            f"Expected 'Cross' but got '{result}'. "
            "Cross-to-header goals across aerial possession splits "
            "should be detected by looking back at the previous possession."
        )

    def test_cross_to_header_not_triggered_without_cross(self):
        """Aerial-start possession without a cross in the previous poss.

        If the previous same-team possession ended with a normal pass
        (no Cross qualifier, not from a wide zone), the cross-to-header
        fallback should NOT fire.
        """
        prev_poss_events = [
            _event_row(event_type="pass", x=50.0, y=50.0,
                       _match_sec=3690, minute=61, second=30,
                       team_name="Inter", poss_id=100),
        ]
        opp_aerial = [
            _event_row(event_type="aerial", x=50.0, y=50.0,
                       _match_sec=3695, minute=61, second=35,
                       team_name="Torino", poss_id=101, outcome=0),
        ]
        goal_poss_events = [
            _event_row(event_type="aerial", x=90.0, y=50.0,
                       _match_sec=3695, minute=61, second=35,
                       team_name="Inter", poss_id=102, outcome=1),
            _shot_row(x=90.0, y=50.0,
                      _match_sec=3697, minute=61, second=37,
                      team_name="Inter", poss_id=102),
        ]

        all_events = prev_poss_events + opp_aerial + goal_poss_events
        match_df = pd.DataFrame(all_events)
        match_df["_match_sec"] = match_df["minute"] * 60 + match_df["second"]

        poss_df = match_df[match_df["poss_id"] == 102].copy()
        shot = pd.Series(goal_poss_events[-1])

        result = classify_attack_origin(
            shot, poss_df, "open_play", 3695.0, match_df=match_df,
        )
        assert result != "Cross", (
            f"Got 'Cross' but previous possession had no cross. "
            "Should fall through to Combination (default)."
        )
        assert result == "Combination"


# ═══════════════════════════════════════════════════════════════════════════════
# POSSESSION VALUE MODEL
# ═══════════════════════════════════════════════════════════════════════════════

class TestPossessionValueModel:

    def test_get_xt_returns_float(self):
        model = _make_pv_model_with_known_grid()
        val = model.get_xT(50.0, 50.0)
        assert isinstance(val, float)
        assert val > 0

    def test_xt_increases_toward_goal(self):
        model = _make_pv_model_with_known_grid()
        val_own = model.get_xT(10.0, 50.0)
        val_mid = model.get_xT(50.0, 50.0)
        val_att = model.get_xT(90.0, 50.0)
        assert val_own < val_mid < val_att

    def test_get_chain_pv_simple_chain(self):
        """
        Three passes, each adding ~0.05 xT.

        In the test grid: xT = col/15 * 0.40
        Pass 1: x=50→60: col 8→9, xT 0.2133→0.24 = +0.0267
        Pass 2: x=60→70: col 9→11, xT 0.24→0.2933 = +0.0533
        Pass 3: x=70→80: col 11→12, xT 0.2933→0.32 = +0.0267

        Total PV > 0 (exact value depends on zone boundaries).
        """
        model = _make_pv_model_with_known_grid()
        events = [
            {"event_type": "pass", "x": 50.0, "y": 50.0,
             "pass_end_x": 60.0, "pass_end_y": 50.0, "match_sec": 600,
             "player_name": "A"},
            {"event_type": "pass", "x": 60.0, "y": 50.0,
             "pass_end_x": 70.0, "pass_end_y": 50.0, "match_sec": 603,
             "player_name": "B"},
            {"event_type": "pass", "x": 70.0, "y": 50.0,
             "pass_end_x": 80.0, "pass_end_y": 50.0, "match_sec": 606,
             "player_name": "C"},
        ]
        pv = model.get_chain_pv(events, ft_entry_time=None)
        assert pv > 0.0
        assert pv < 0.50  # sanity upper bound

    def test_get_chain_pv_backward_pass_zero(self):
        """A backward pass should contribute 0 PV (clamped)."""
        model = _make_pv_model_with_known_grid()
        events = [
            {"event_type": "pass", "x": 80.0, "y": 50.0,
             "pass_end_x": 60.0, "pass_end_y": 50.0, "match_sec": 600,
             "player_name": "A"},
        ]
        pv = model.get_chain_pv(events, ft_entry_time=None)
        assert pv == 0.0

    def test_export_heatmap_shape(self):
        model = _make_pv_model_with_known_grid()
        hm = model.export_heatmap()
        assert hm.shape == (X_ZONES, Y_ZONES)

    def test_save_load_roundtrip(self, tmp_path):
        model = _make_pv_model_with_known_grid()
        cache_path = tmp_path / "pv_test.pkl"
        model.save(cache_path)

        loaded = PossessionValueModel()
        loaded.load(cache_path)

        np.testing.assert_array_equal(model.xT, loaded.xT)
        np.testing.assert_array_equal(model.P_shot, loaded.P_shot)

    def test_load_missing_file_raises(self, tmp_path):
        model = PossessionValueModel()
        with pytest.raises(FileNotFoundError):
            model.load(tmp_path / "nonexistent.pkl")

    def test_fallback_grid_shape(self):
        grid = _fallback_xt_grid()
        assert grid.shape == (X_ZONES, Y_ZONES)
        assert grid.min() >= 0
        assert grid.max() <= 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# PV MODEL BUILD WITH SYNTHETIC DATA
# ═══════════════════════════════════════════════════════════════════════════════

class TestPossessionValueModelBuild:
    """Test the model build with a tiny synthetic match."""

    def _make_synthetic_match(self) -> pd.DataFrame:
        """Create a minimal synthetic match DataFrame."""
        rows = []
        eid = 1
        # Home team passes progressing up the pitch
        for i in range(50):
            x_start = 10 + i * 1.5
            x_end = x_start + 5
            rows.append({
                "event_id": eid, "event": "Pass", "type_id": 1,
                "period_id": 1, "time_min": i, "time_sec": 0,
                "team_name": "Home FC", "player_name": "Player A",
                "x": min(x_start, 99), "y": 50,
                "outcome": 1,
                "Pass End X": min(x_end, 99), "Pass End Y": 50,
            })
            eid += 1

        # A few shots
        for sx, sy, tid in [(90, 50, 15), (92, 45, 16), (70, 50, 13)]:
            rows.append({
                "event_id": eid, "event": "Shot" if tid != 16 else "Goal",
                "type_id": tid,
                "period_id": 1, "time_min": 80, "time_sec": eid,
                "team_name": "Home FC", "player_name": "Player B",
                "x": sx, "y": sy, "outcome": 1,
            })
            eid += 1

        return pd.DataFrame(rows)

    def test_build_completes(self):
        df = self._make_synthetic_match()
        model = PossessionValueModel([df])
        model.build()
        assert model.xT is not None
        assert model.xT.shape == (X_ZONES, Y_ZONES)

    def test_build_xt_non_negative(self):
        df = self._make_synthetic_match()
        model = PossessionValueModel([df])
        model.build()
        assert (model.xT >= 0).all()

    def test_build_xt_penalty_zone_high(self):
        """Penalty zone should have non-trivial xT after build."""
        df = self._make_synthetic_match()
        model = PossessionValueModel([df])
        model.build()
        # Col 14, row 6 (penalty spot area)
        val = model.xT[14, 6]
        assert val > 0  # should be positive even with tiny data


# ═══════════════════════════════════════════════════════════════════════════════
# SHOT QUALITY TIERS
# ═══════════════════════════════════════════════════════════════════════════════

class TestShotQualityTiers:
    def test_goal_is_level_3(self):
        assert classify_shot_quality(16, 0.05, True, True) == 3

    def test_saved_is_level_2(self):
        assert classify_shot_quality(15, 0.10, True, False) == 2

    def test_high_xg_miss_is_level_2(self):
        assert classify_shot_quality(13, 0.25, False, False) == 2

    def test_moderate_xg_miss_is_level_1(self):
        assert classify_shot_quality(13, 0.15, False, False) == 1

    def test_low_xg_miss_is_level_0(self):
        assert classify_shot_quality(13, 0.05, False, False) == 0

    def test_blocked_is_level_0(self):
        """Blocked shot (type_id not in 13,14) with low xG → level 0."""
        assert classify_shot_quality(12, 0.05, False, False) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# CHANCE CREATION ANALYZER — INTEGRATION
# ═══════════════════════════════════════════════════════════════════════════════

class TestChanceCreationAnalyzer:
    """Integration tests with a mini match DataFrame."""

    def _make_mini_match(self) -> pd.DataFrame:
        """
        Build a minimal match with known possessions and shots.

        Possession 1: Home FC open play → shot (saved, in box)
        Possession 2: Home FC corner → shot (goal, in box)
        Possession 3: Away FC → shot (miss, out box)
        """
        events = []
        eid = 1

        # Possession 1: open-play build-up → shot
        for sec_offset in range(5):
            events.append({
                "event_id": eid, "event": "Pass", "type_id": 1,
                "period_id": 1, "time_min": 10, "time_sec": sec_offset * 3,
                "contestant_id": "t1", "team_name": "Test FC",
                "player_name": "Player A",
                "x": 50 + sec_offset * 8, "y": 50,
                "outcome": 1,
                "Pass End X": 58 + sec_offset * 8,
                "Pass End Y": 50,
                "Through ball": None, "Cross": None,
                "Long ball": None, "Corner taken": None,
                "Free kick taken": None, "Throw In": None,
                "Penalty": None, "Goal Kick": None,
                "Gk kick from hands": None,
                "Head": None, "Right footed": "Si",
                "Volley": None, "Big Chance": None,
                "1 on 1": None, "Fast break": None,
                "From corner": None, "Set piece": None,
                "Free kick": None, "Individual Play": None,
                "own goal": None, "Related event ID": None,
            })
            eid += 1

        # Shot 1: saved, in box
        events.append({
            "event_id": eid, "event": "Saved Shot", "type_id": 15,
            "period_id": 1, "time_min": 10, "time_sec": 20,
            "contestant_id": "t1", "team_name": "Test FC",
            "player_name": "Player B",
            "x": 90.0, "y": 50.0, "outcome": 1,
            "Pass End X": None, "Pass End Y": None,
            "Through ball": None, "Cross": None,
            "Long ball": None, "Corner taken": None,
            "Free kick taken": None, "Throw In": None,
            "Penalty": None, "Goal Kick": None,
            "Gk kick from hands": None,
            "Head": None, "Right footed": "Si",
            "Volley": None, "Big Chance": None,
            "1 on 1": None, "Fast break": None,
            "From corner": None, "Set piece": None,
            "Free kick": None, "Individual Play": None,
            "own goal": None, "Related event ID": None,
        })
        eid += 1

        # Possession 2: corner kick → goal
        events.append({
            "event_id": eid, "event": "Pass", "type_id": 1,
            "period_id": 1, "time_min": 25, "time_sec": 0,
            "contestant_id": "t1", "team_name": "Test FC",
            "player_name": "Player C",
            "x": 100.0, "y": 0.0, "outcome": 1,
            "Pass End X": 92.0, "Pass End Y": 50.0,
            "Through ball": None, "Cross": None,
            "Long ball": None, "Corner taken": "Si",
            "Free kick taken": None, "Throw In": None,
            "Penalty": None, "Goal Kick": None,
            "Gk kick from hands": None,
            "Head": None, "Right footed": None,
            "Volley": None, "Big Chance": None,
            "1 on 1": None, "Fast break": None,
            "From corner": None, "Set piece": None,
            "Free kick": None, "Individual Play": None,
            "own goal": None, "Related event ID": None,
        })
        eid += 1

        # Shot 2: goal, in box (from corner)
        events.append({
            "event_id": eid, "event": "Goal", "type_id": 16,
            "period_id": 1, "time_min": 25, "time_sec": 5,
            "contestant_id": "t1", "team_name": "Test FC",
            "player_name": "Player D",
            "x": 95.0, "y": 45.0, "outcome": 1,
            "Pass End X": None, "Pass End Y": None,
            "Through ball": None, "Cross": None,
            "Long ball": None, "Corner taken": None,
            "Free kick taken": None, "Throw In": None,
            "Penalty": None, "Goal Kick": None,
            "Gk kick from hands": None,
            "Head": "Si", "Right footed": None,
            "Volley": None, "Big Chance": "Si",
            "1 on 1": None, "Fast break": None,
            "From corner": "Si", "Set piece": "Si",
            "Free kick": None, "Individual Play": None,
            "own goal": None, "Related event ID": None,
        })
        eid += 1

        # Possession 3: Away team shot (miss, out box)
        events.append({
            "event_id": eid, "event": "Miss", "type_id": 13,
            "period_id": 1, "time_min": 40, "time_sec": 0,
            "contestant_id": "t2", "team_name": "Opponent FC",
            "player_name": "Opp Player",
            "x": 70.0, "y": 50.0, "outcome": 0,
            "Pass End X": None, "Pass End Y": None,
            "Through ball": None, "Cross": None,
            "Long ball": None, "Corner taken": None,
            "Free kick taken": None, "Throw In": None,
            "Penalty": None, "Goal Kick": None,
            "Gk kick from hands": None,
            "Head": None, "Right footed": "Si",
            "Volley": None, "Big Chance": None,
            "1 on 1": None, "Fast break": None,
            "From corner": None, "Set piece": None,
            "Free kick": None, "Individual Play": None,
            "own goal": None, "Related event ID": None,
        })
        eid += 1

        return pd.DataFrame(events)

    def test_analyze_returns_correct_structure(self):
        """Integration: analyze() returns all expected keys."""
        model = _make_pv_model_with_known_grid()
        analyzer = ChanceCreationAnalyzer(model)
        df = self._make_mini_match()
        result = analyzer.analyze(df, "Test FC")

        assert "chain_to_goal_matrix" in result
        assert "shot_metrics" in result
        assert "shot_quality_tiers" in result
        assert "shots_detail" in result

    def test_analyze_correct_shot_count(self):
        """Test FC should have exactly 2 shots."""
        model = _make_pv_model_with_known_grid()
        analyzer = ChanceCreationAnalyzer(model)
        df = self._make_mini_match()
        result = analyzer.analyze(df, "Test FC")

        assert result["shot_metrics"]["shots_total"] == 2

    def test_analyze_goal_count(self):
        """Test FC should have exactly 1 goal."""
        model = _make_pv_model_with_known_grid()
        analyzer = ChanceCreationAnalyzer(model)
        df = self._make_mini_match()
        result = analyzer.analyze(df, "Test FC")

        assert result["chain_to_goal_matrix"]["TOTAL"]["GS"] == 1

    def test_analyze_matrix_has_all_origins(self):
        """Matrix should have all 5 origin columns plus TOTAL."""
        model = _make_pv_model_with_known_grid()
        analyzer = ChanceCreationAnalyzer(model)
        df = self._make_mini_match()
        result = analyzer.analyze(df, "Test FC")

        matrix = result["chain_to_goal_matrix"]
        for label in ORIGIN_LABELS + ["TOTAL"]:
            assert label in matrix
            assert "N" in matrix[label]
            assert "xG" in matrix[label]
            assert "SoT%" in matrix[label]
            assert "GS" in matrix[label]

    def test_analyze_xg_positive(self):
        """Total xG should be positive."""
        model = _make_pv_model_with_known_grid()
        analyzer = ChanceCreationAnalyzer(model)
        df = self._make_mini_match()
        result = analyzer.analyze(df, "Test FC")

        assert result["chain_to_goal_matrix"]["TOTAL"]["xG"] > 0

    def test_analyze_quality_tiers_sum(self):
        """Quality tier counts should sum to total shots."""
        model = _make_pv_model_with_known_grid()
        analyzer = ChanceCreationAnalyzer(model)
        df = self._make_mini_match()
        result = analyzer.analyze(df, "Test FC")

        tiers = result["shot_quality_tiers"]
        total_from_tiers = sum(
            tiers[k]["count"] for k in tiers
        )
        assert total_from_tiers == result["shot_metrics"]["shots_total"]

    def test_analyze_empty_team(self):
        """Analysis for a team with no shots returns empty output."""
        model = _make_pv_model_with_known_grid()
        analyzer = ChanceCreationAnalyzer(model)
        df = self._make_mini_match()
        result = analyzer.analyze(df, "Nonexistent FC")

        assert result["shot_metrics"]["shots_total"] == 0
        assert result["chain_to_goal_matrix"]["TOTAL"]["GS"] == 0

    def test_opponent_shots_excluded(self):
        """Away team shots should NOT appear in Test FC's analysis."""
        model = _make_pv_model_with_known_grid()
        analyzer = ChanceCreationAnalyzer(model)
        df = self._make_mini_match()
        result = analyzer.analyze(df, "Test FC")

        # Only 2 shots for Test FC, not 3
        assert result["shot_metrics"]["shots_total"] == 2

    def test_shot_metrics_percentages(self):
        """Shot metric percentages should be 0-100."""
        model = _make_pv_model_with_known_grid()
        analyzer = ChanceCreationAnalyzer(model)
        df = self._make_mini_match()
        result = analyzer.analyze(df, "Test FC")

        metrics = result["shot_metrics"]
        assert 0 <= metrics["pct_in_box"] <= 100
        assert 0 <= metrics["sot_pct_total"] <= 100


# ═══════════════════════════════════════════════════════════════════════════════
# SHOT METRICS COMPUTATION (UNIT)
# ═══════════════════════════════════════════════════════════════════════════════

class TestComputeShotMetrics:
    def test_all_in_box(self):
        model = _make_pv_model_with_known_grid()
        analyzer = ChanceCreationAnalyzer(model)
        shots = [
            {"in_box": True, "on_target": True, "xG": 0.3, "is_goal": False},
            {"in_box": True, "on_target": False, "xG": 0.1, "is_goal": False},
        ]
        metrics = analyzer.compute_shot_metrics(shots, total_possessions=10)
        assert metrics["shots_total"] == 2
        assert metrics["shots_in_box"] == 2
        assert metrics["shots_out_box"] == 0
        assert metrics["pct_in_box"] == 100.0

    def test_xg_per_shot(self):
        model = _make_pv_model_with_known_grid()
        analyzer = ChanceCreationAnalyzer(model)
        shots = [
            {"in_box": True, "on_target": True, "xG": 0.4, "is_goal": False},
            {"in_box": False, "on_target": False, "xG": 0.2, "is_goal": False},
        ]
        metrics = analyzer.compute_shot_metrics(shots, total_possessions=20)
        assert metrics["xg_per_shot"] == 0.30

    def test_empty_shots(self):
        model = _make_pv_model_with_known_grid()
        analyzer = ChanceCreationAnalyzer(model)
        metrics = analyzer.compute_shot_metrics([], total_possessions=10)
        assert metrics["shots_total"] == 0
