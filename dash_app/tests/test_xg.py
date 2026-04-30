"""
Tests for src/analytics/xg.py

Covers:
  - Geometry helpers (_distance_to_goal, _angle_to_goal)
  - XGModel: fit, predict, save/load roundtrip
  - compute_batch_xg: penalty fixed at 0.79, own goal fixed at 0.0
  - No raw CSV files or model training triggered from disk.
"""
import numpy as np
import pandas as pd
import pytest

from src.analytics.xg import (
    _distance_to_goal,
    _angle_to_goal,
    XGModel,
    FEATURE_COLS,
    PENALTY_XG,
    compute_batch_xg,
)


# ── Geometry ──────────────────────────────────────────────────────────────────

def test_distance_to_goal_at_goal_mouth():
    """A shot from the centre of the goal mouth is (almost) zero."""
    assert _distance_to_goal(100.0, 50.0) < 0.01


def test_distance_to_goal_increases_with_distance():
    close = _distance_to_goal(90.0, 50.0)
    far = _distance_to_goal(50.0, 50.0)
    assert close < far


def test_distance_to_goal_penalty_spot():
    # Opta penalty spot ~ x=88.5, y=50; real distance ~11.5 m
    d = _distance_to_goal(88.5, 50.0)
    assert 10.0 < d < 14.0


def test_angle_to_goal_is_zero_behind_goal():
    # x > 100 → dx ≤ 0 → angle should be 0
    assert _angle_to_goal(105.0, 50.0) == 0.0


def test_angle_to_goal_increases_closer():
    far_angle = _angle_to_goal(60.0, 50.0)
    close_angle = _angle_to_goal(90.0, 50.0)
    assert close_angle > far_angle


def test_angle_to_goal_symmetric_about_centreline():
    # Equal y-offset above/below centre should give the same angle
    above = _angle_to_goal(85.0, 60.0)
    below = _angle_to_goal(85.0, 40.0)
    assert abs(above - below) < 0.01


# ── XGModel: fit & predict ────────────────────────────────────────────────────

def _make_synthetic_training_data(n=200, seed=0):
    """
    Minimal synthetic training set: goals scored from close range,
    misses from far range.  Gives the model a learnable signal.
    """
    rng = np.random.default_rng(seed)
    n_half = n // 2

    # Close shots → goals (label 1)
    close = np.zeros((n_half, len(FEATURE_COLS)))
    close[:, FEATURE_COLS.index("distance_to_goal")] = rng.uniform(3, 8, n_half)
    close[:, FEATURE_COLS.index("angle_to_goal")] = rng.uniform(25, 50, n_half)

    # Far shots → misses (label 0)
    far = np.zeros((n_half, len(FEATURE_COLS)))
    far[:, FEATURE_COLS.index("distance_to_goal")] = rng.uniform(25, 40, n_half)
    far[:, FEATURE_COLS.index("angle_to_goal")] = rng.uniform(2, 10, n_half)

    X = np.vstack([close, far])
    y = np.array([1] * n_half + [0] * n_half, dtype=float)
    return X, y


def test_xgmodel_predictions_in_valid_range():
    X, y = _make_synthetic_training_data()
    model = XGModel()
    model.fit(X, y, lr=0.05, n_iter=500)
    preds = model.predict_proba(X)
    assert preds.min() >= 0.01
    assert preds.max() <= 0.99


def test_xgmodel_closer_shot_higher_xg():
    """After training, a point-blank shot should score higher than a long-range effort."""
    X, y = _make_synthetic_training_data()
    model = XGModel()
    model.fit(X, y, lr=0.05, n_iter=1000)

    close_features = {c: 0.0 for c in FEATURE_COLS}
    close_features["distance_to_goal"] = 5.0
    close_features["angle_to_goal"] = 40.0

    far_features = {c: 0.0 for c in FEATURE_COLS}
    far_features["distance_to_goal"] = 35.0
    far_features["angle_to_goal"] = 4.0

    assert model.predict_single(close_features) > model.predict_single(far_features)


def test_xgmodel_save_load_roundtrip(tmp_path):
    """Serialised model should produce identical predictions after reload."""
    X, y = _make_synthetic_training_data()
    model = XGModel()
    model.fit(X, y, lr=0.05, n_iter=500)

    cache_file = tmp_path / "xg_model_test.pkl"
    model.save(cache_file, csv_count=42)

    result = XGModel.load(cache_file)
    assert result is not None
    loaded_model, csv_count = result

    assert csv_count == 42

    preds_original = model.predict_proba(X)
    preds_loaded = loaded_model.predict_proba(X)
    np.testing.assert_array_almost_equal(preds_original, preds_loaded)


def test_xgmodel_load_returns_none_for_missing_file(tmp_path):
    result = XGModel.load(tmp_path / "does_not_exist.pkl")
    assert result is None


# ── compute_batch_xg: special cases ──────────────────────────────────────────

def _shot_row(**kwargs) -> dict:
    """Build a minimal shot-event row with defaults."""
    defaults = {
        "type_id": 15,  # saved (non-goal)
        "x": 85.0,
        "y": 50.0,
    }
    defaults.update(kwargs)
    return defaults


def test_penalty_xg_is_fixed():
    """Rows with a Penalty qualifier must receive exactly PENALTY_XG."""
    df = pd.DataFrame([_shot_row(Penalty="Si"), _shot_row(Penalty="Si")])
    xg = compute_batch_xg(df)
    assert (xg == PENALTY_XG).all()


def test_own_goal_xg_is_zero():
    """Rows flagged as own goals must receive xG = 0.0."""
    df = pd.DataFrame([_shot_row(**{"own goal": "Si"})])
    xg = compute_batch_xg(df)
    assert (xg == 0.0).all()


def test_penalty_and_own_goal_do_not_trigger_model():
    """
    If every shot is either a penalty or own goal, _get_model() is never
    called — no CSV scan, no training.  This should complete instantly.
    """
    df = pd.DataFrame([
        _shot_row(Penalty="Si"),
        _shot_row(**{"own goal": "Si"}),
    ])
    xg = compute_batch_xg(df)
    assert len(xg) == 2
