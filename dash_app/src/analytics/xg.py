"""
Expected Goals (xG) Analytics Module — v2
==========================================
Opta-inspired xG model using logistic regression trained on Serie A
event data (2021–2026, ~46k shots).

Methodology
-----------
This model follows verified Opta / Stats Perform principles adapted
to the features available in Opta event-level CSV data (no freeze-
frame, no tracking data, no goalkeeper position).

A logistic regression is fitted on the full historical shot dataset
to predict goal probability from 18 engineered features:

  ┌───────────────────────────────┬──────────────────────────────────┐
  │ FEATURE                       │ SOURCE / DERIVATION              │
  ├───────────────────────────────┼──────────────────────────────────┤
  │ 1. distance_to_goal           │ sqrt((100−x)² + (50−y)²) scaled │
  │ 2. angle_to_goal              │ arctan subtended by goalposts    │
  │ 3. is_header                  │ "Head" qualifier                 │
  │ 4. is_right_foot              │ "Right footed" qualifier         │
  │ 5. is_volley                  │ "Volley" qualifier               │
  │ 6. is_big_chance              │ "Big Chance" qualifier           │
  │ 7. is_one_on_one              │ "1 on 1" qualifier               │
  │ 8. is_fast_break              │ "Fast break" qualifier           │
  │ 9. is_from_corner             │ "From corner" qualifier          │
  │ 10. is_set_piece              │ "Set piece" qualifier            │
  │ 11. is_free_kick              │ "Free kick" pattern on shot      │
  │ 12. is_individual_play        │ "Individual Play" qualifier      │
  │ 13. is_rebound                │ inferred from event sequence     │
  │ 14. assist_is_cross           │ "Cross" on related pass event    │
  │ 15. assist_is_through_ball    │ "Through ball" on related pass   │
  │ 16. assist_is_pull_back       │ "Pull Back" on related pass      │
  │ 17. assist_is_long_ball       │ "Long ball" on related pass      │
  │ 18. is_unassisted             │ no Related event ID              │
  └───────────────────────────────┴──────────────────────────────────┘

Penalties are excluded from the model and assigned a fixed xG of 0.79,
aligned with public Opta references.

The model is trained once at first use and cached in memory.

What CANNOT be replicated from Opta (requires unavailable data):
  - Goalkeeper positioning / distance from goal line
  - Number / position of defenders between shooter and goal
  - Clarity of goalmouth (freeze-frame required)
  - Detailed defender pressure metric
  - Shot speed / trajectory curvature
  - Game state (score differential at time of shot)

Reference:
  - Opta / Stats Perform "What are Expected Goals (xG)?" explainer
  - Public Opta xG descriptions referencing logistic regression + XGBoost
  - Penalty xG ≈ 0.79 from Opta public documentation

Data source: Opta match-event CSVs (type_id 13=miss, 14=post, 15=saved, 16=goal)
"""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from src.config import RAW_DATA_DIR, CACHE_DIR
from src.team_mapping import canonical_name


# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

# Shot type_ids in Opta data
SHOT_TYPE_IDS = [13, 14, 15, 16]  # Miss, Post, Saved, Goal

# Opta pitch: x 0–100, y 0–100; actual pitch ≈ 105 m × 68 m
GOAL_X = 100.0
GOAL_Y = 50.0            # centre of goal (y-axis)
X_SCALE = 1.05            # metres per Opta x-unit
Y_SCALE = 0.68            # metres per Opta y-unit
GOAL_WIDTH = 7.32          # goal width in metres

# Penalty xG — aligned with Opta public reference (was 0.76 in v1)
PENALTY_XG = 0.79

# Rebound detection: max seconds between consecutive same-team shots
REBOUND_MAX_SECONDS = 6

# Feature column list (order matters — must match training and prediction)
FEATURE_COLS = [
    "distance_to_goal",
    "angle_to_goal",
    "is_header",
    "is_right_foot",
    "is_volley",
    "is_big_chance",
    "is_one_on_one",
    "is_fast_break",
    "is_from_corner",
    "is_set_piece",
    "is_free_kick",
    "is_individual_play",
    "is_rebound",
    "assist_is_cross",
    "assist_is_through_ball",
    "assist_is_pull_back",
    "assist_is_long_ball",
    "is_unassisted",
]


# ═══════════════════════════════════════════════════════════════════════════════
# GEOMETRY HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _distance_to_goal(x: float, y: float) -> float:
    """Euclidean distance in metres from (x, y) to goal centre."""
    dx = (GOAL_X - x) * X_SCALE
    dy = (GOAL_Y - y) * Y_SCALE
    return np.sqrt(dx * dx + dy * dy)


def _angle_to_goal(x: float, y: float) -> float:
    """
    Visible angle of goal (degrees) from the shot location.

    Computed as the angle subtended by the two goalposts from the
    shooter's position:
        θ = |arctan2(dy_left, dx) − arctan2(dy_right, dx)|
    """
    dx = (GOAL_X - x) * X_SCALE
    if dx <= 0:
        return 0.0
    half_goal_m = GOAL_WIDTH / 2.0
    dy_centre = (GOAL_Y - y) * Y_SCALE
    angle_left = np.arctan2(dy_centre + half_goal_m, dx)
    angle_right = np.arctan2(dy_centre - half_goal_m, dx)
    return np.degrees(abs(angle_left - angle_right))


# Vectorised versions for batch DataFrame processing
def _vec_distance(x: pd.Series, y: pd.Series) -> pd.Series:
    dx = (GOAL_X - x) * X_SCALE
    dy = (GOAL_Y - y) * Y_SCALE
    return np.sqrt(dx**2 + dy**2)


def _vec_angle(x: pd.Series, y: pd.Series) -> pd.Series:
    dx = (GOAL_X - x) * X_SCALE
    dy_centre = (GOAL_Y - y) * Y_SCALE
    half_goal_m = GOAL_WIDTH / 2.0
    angle_left = np.arctan2(dy_centre + half_goal_m, dx)
    angle_right = np.arctan2(dy_centre - half_goal_m, dx)
    return np.degrees(np.abs(angle_left - angle_right))


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE ENGINEERING
# ═══════════════════════════════════════════════════════════════════════════════

def _flag(series: pd.Series) -> pd.Series:
    """Convert Opta qualifier column (NaN / 'Si') to 0/1 int."""
    return series.notna().astype(int)


def _enrich_rebound_flag(df: pd.DataFrame) -> pd.Series:
    """
    Detect rebound shots from event sequence.

    A shot is marked as a rebound if there is a preceding shot by the
    SAME team in the SAME period within REBOUND_MAX_SECONDS seconds.
    """
    rebound = pd.Series(0, index=df.index, dtype=int)
    if df.empty or "period_id" not in df.columns:
        return rebound

    for _match_file, mdf in df.groupby("_match_file", sort=False):
        mdf_sorted = mdf.sort_values(["period_id", "time_min", "time_sec"])
        shot_mask = mdf_sorted["type_id"].isin(SHOT_TYPE_IDS)
        shot_rows = mdf_sorted[shot_mask]
        prev_time: dict = {}
        for idx in shot_rows.index:
            row = mdf_sorted.loc[idx]
            team = row.get("team_name", "")
            period = row.get("period_id", 0)
            t = row["time_min"] * 60 + row["time_sec"]
            key = (team, period)
            if key in prev_time:
                diff = t - prev_time[key]
                if 0 < diff <= REBOUND_MAX_SECONDS:
                    rebound.loc[idx] = 1
            prev_time[key] = t

    return rebound


def _enrich_assist_features(shots_df: pd.DataFrame,
                            all_events_by_match: dict) -> pd.DataFrame:
    """
    Look up the Related event ID for each shot to extract assist-type
    qualifiers (Cross, Through ball, Pull Back, Long ball) from the
    preceding pass / action.
    """
    for col in ["assist_is_cross", "assist_is_through_ball",
                "assist_is_pull_back", "assist_is_long_ball"]:
        shots_df[col] = 0

    rel_mask = shots_df["Related event ID"].notna()
    if not rel_mask.any():
        return shots_df

    for idx in shots_df.index[rel_mask]:
        rel_id = int(shots_df.at[idx, "Related event ID"])
        match_file = shots_df.at[idx, "_match_file"]
        match_events = all_events_by_match.get(match_file)
        if match_events is None:
            continue
        assist_row = match_events.loc[match_events["event_id"] == rel_id]
        if assist_row.empty:
            continue
        ar = assist_row.iloc[0]

        if "Cross" in ar.index and pd.notna(ar.get("Cross")):
            shots_df.at[idx, "assist_is_cross"] = 1
        if "Through ball" in ar.index and pd.notna(ar.get("Through ball")):
            shots_df.at[idx, "assist_is_through_ball"] = 1
        if "Pull Back" in ar.index and pd.notna(ar.get("Pull Back")):
            shots_df.at[idx, "assist_is_pull_back"] = 1
        if "Long ball" in ar.index and pd.notna(ar.get("Long ball")):
            shots_df.at[idx, "assist_is_long_ball"] = 1

    return shots_df


def engineer_features(shots_df: pd.DataFrame,
                      all_events_by_match: Optional[dict] = None) -> pd.DataFrame:
    """
    Build the full feature matrix for xG prediction.

    Parameters
    ----------
    shots_df : DataFrame of shot events (type_id in [13,14,15,16])
    all_events_by_match : dict  {match_file → full match DataFrame}
        Needed for assist-type and rebound features.
        If None, those features are set to 0.

    Returns
    -------
    shots_df with all FEATURE_COLS added.
    """
    df = shots_df.copy()

    # ── Geometry ──────────────────────────────────────────────
    df["distance_to_goal"] = _vec_distance(df["x"], df["y"])
    df["angle_to_goal"] = _vec_angle(df["x"], df["y"])

    # ── Body part ─────────────────────────────────────────────
    df["is_header"] = _flag(df.get("Head", pd.Series(dtype="object")))
    df["is_right_foot"] = _flag(df.get("Right footed", pd.Series(dtype="object")))

    # ── Shot technique ────────────────────────────────────────
    df["is_volley"] = _flag(df.get("Volley", pd.Series(dtype="object")))

    # ── Chance quality ────────────────────────────────────────
    df["is_big_chance"] = _flag(df.get("Big Chance", pd.Series(dtype="object")))
    df["is_one_on_one"] = _flag(df.get("1 on 1", pd.Series(dtype="object")))

    # ── Pattern of play ───────────────────────────────────────
    df["is_fast_break"] = _flag(df.get("Fast break", pd.Series(dtype="object")))
    df["is_from_corner"] = _flag(df.get("From corner", pd.Series(dtype="object")))
    df["is_set_piece"] = _flag(df.get("Set piece", pd.Series(dtype="object")))
    df["is_free_kick"] = _flag(df.get("Free kick", pd.Series(dtype="object")))
    df["is_individual_play"] = _flag(df.get("Individual Play", pd.Series(dtype="object")))

    # ── Rebound ───────────────────────────────────────────────
    if all_events_by_match is not None and "_match_file" in df.columns:
        df["is_rebound"] = _enrich_rebound_flag(df)
    else:
        df["is_rebound"] = 0

    # ── Assist type ───────────────────────────────────────────
    if all_events_by_match is not None and "Related event ID" in df.columns:
        df = _enrich_assist_features(df, all_events_by_match)
    else:
        for col in ["assist_is_cross", "assist_is_through_ball",
                     "assist_is_pull_back", "assist_is_long_ball"]:
            df[col] = 0

    # ── Unassisted ────────────────────────────────────────────
    if "Related event ID" in df.columns:
        df["is_unassisted"] = df["Related event ID"].isna().astype(int)
    else:
        df["is_unassisted"] = 1

    return df


# ═══════════════════════════════════════════════════════════════════════════════
# MODEL — LOGISTIC REGRESSION
# ═══════════════════════════════════════════════════════════════════════════════

class XGModel:
    """
    Lightweight logistic-regression xG model.

    Trained on historical Serie A shot data using 18 engineered features.
    Penalties are handled separately (fixed xG = 0.79).

    Uses a custom gradient-descent solver (no sklearn dependency needed).
    """

    def __init__(self):
        self.coef_: Optional[np.ndarray] = None
        self.intercept_: float = 0.0
        self.feature_names: list[str] = FEATURE_COLS
        self.n_train: int = 0
        self._fitted = False
        self._mean: np.ndarray = np.zeros(len(FEATURE_COLS))
        self._std: np.ndarray = np.ones(len(FEATURE_COLS))

    @staticmethod
    def _sigmoid(z: np.ndarray) -> np.ndarray:
        """Numerically stable sigmoid function."""
        return np.where(
            z >= 0,
            1.0 / (1.0 + np.exp(-z)),
            np.exp(z) / (1.0 + np.exp(z)),
        )

    def fit(self, X: np.ndarray, y: np.ndarray,
            lr: float = 0.05, n_iter: int = 3000,
            reg_lambda: float = 0.005) -> "XGModel":
        """
        Fit via gradient descent with L2 regularisation.

        Custom solver avoids sklearn dependency and keeps the project
        lightweight.  Convergence is fast with 18 features.
        """
        n, d = X.shape
        self.coef_ = np.zeros(d, dtype=np.float64)
        self.intercept_ = 0.0

        # Standardise features for gradient convergence
        self._mean = np.zeros(d)
        self._std = np.ones(d)
        for j in range(d):
            col_std = X[:, j].std()
            if col_std > 1e-8:
                self._mean[j] = X[:, j].mean()
                self._std[j] = col_std
        X_std = (X - self._mean) / self._std

        for _ in range(n_iter):
            z = X_std @ self.coef_ + self.intercept_
            p = self._sigmoid(z)
            error = p - y
            grad_w = (X_std.T @ error) / n + reg_lambda * self.coef_
            grad_b = error.mean()
            self.coef_ -= lr * grad_w
            self.intercept_ -= lr * grad_b

        self.n_train = n
        self._fitted = True
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Return P(goal) for each row."""
        if not self._fitted:
            raise RuntimeError("XGModel not fitted yet.")
        X_std = (X - self._mean) / self._std
        z = X_std @ self.coef_ + self.intercept_
        p = self._sigmoid(z)
        return np.clip(p, 0.01, 0.99)

    def predict_single(self, features: dict) -> float:
        """Predict xG for a single shot given a feature dict."""
        x = np.array([[features.get(c, 0.0) for c in self.feature_names]])
        return float(self.predict_proba(x)[0])

    def summary(self) -> pd.DataFrame:
        """Return a readable summary of model coefficients."""
        if not self._fitted:
            return pd.DataFrame()
        raw_coef = self.coef_ / self._std
        return pd.DataFrame({
            "feature": self.feature_names,
            "coefficient": raw_coef,
            "std_coefficient": self.coef_,
        }).sort_values("std_coefficient", ascending=False, key=abs)

    def save(self, path: Path, csv_count: int) -> None:
        """Persist model weights and the CSV fingerprint used for training."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({"model": self, "csv_count": csv_count}, f)

    @staticmethod
    def load(path: Path) -> "tuple[XGModel, int] | None":
        """Load model from disk. Returns (model, csv_count) or None on failure."""
        try:
            with open(path, "rb") as f:
                data = pickle.load(f)
            return data["model"], data["csv_count"]
        except Exception:
            return None


# ═══════════════════════════════════════════════════════════════════════════════
# TRAINING PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════

def _load_all_shots_for_training() -> tuple[pd.DataFrame, dict]:
    """Load every shot across every available season for model training."""
    season_dirs = sorted(RAW_DATA_DIR.glob("serie_a_*"))
    frames = []
    all_events_by_match: dict[str, pd.DataFrame] = {}

    for season_dir in season_dirs:
        events_dir = season_dir / "events"
        if not events_dir.exists():
            continue
        for fp in sorted(events_dir.glob("*.csv")):
            try:
                df = pd.read_csv(fp, low_memory=False)
                all_events_by_match[fp.name] = df
                shots = df[df["type_id"].isin(SHOT_TYPE_IDS)].copy()
                if shots.empty:
                    continue
                shots["_match_file"] = fp.name
                parts = fp.stem.split("_")
                if len(parts) >= 3:
                    shots["_home_csv"] = canonical_name(parts[1])
                    shots["_away_csv"] = canonical_name(parts[2])
                frames.append(shots)
            except Exception:
                continue

    if not frames:
        return pd.DataFrame(), {}
    return pd.concat(frames, ignore_index=True), all_events_by_match


def _train_model() -> "XGModel":
    """
    Train the xG logistic regression model on all historical data.
    Penalties and own goals are excluded from training.
    """
    from src.utils.logging import log

    model = XGModel()
    shots, events_by_match = _load_all_shots_for_training()
    if shots.empty:
        log.warning("xG model: no shot data found — using fallback model")
        return _fallback_model()

    log.info("xG model: loaded %d shots for training", len(shots))

    # Exclude penalties (handled separately at fixed xG)
    pen_col = shots.get("Penalty", pd.Series(dtype="object"))
    non_penalty = shots[pen_col.isna()].copy()

    # Exclude own goals
    if "own goal" in non_penalty.columns:
        non_penalty = non_penalty[non_penalty["own goal"].isna()].copy()

    # Engineer features
    non_penalty = engineer_features(non_penalty, events_by_match)

    y = (non_penalty["type_id"] == 16).astype(int).values
    X = non_penalty[FEATURE_COLS].fillna(0).values.astype(np.float64)

    model.fit(X, y, lr=0.05, n_iter=3000, reg_lambda=0.005)

    # Calibration check
    pred = model.predict_proba(X)
    total_xg = pred.sum()
    total_goals = y.sum()
    log.info(
        "xG model trained: %d shots, %d goals (%.1f%%), "
        "predicted xG=%.1f, ratio=%.3f",
        len(y), total_goals, total_goals / len(y) * 100,
        total_xg, total_xg / max(total_goals, 1),
    )

    summary = model.summary()
    log.info("xG model coefficients:\n%s", summary.to_string(index=False))

    return model


def _fallback_model() -> XGModel:
    """
    Fallback model with hand-calibrated coefficients for when no
    training data is available.
    """
    model = XGModel()
    model._mean = np.zeros(len(FEATURE_COLS))
    model._std = np.ones(len(FEATURE_COLS))
    model._fitted = True
    model.n_train = 0

    coef = np.zeros(len(FEATURE_COLS))
    idx = {name: i for i, name in enumerate(FEATURE_COLS)}
    coef[idx["distance_to_goal"]] = -0.08
    coef[idx["angle_to_goal"]] = 0.04
    coef[idx["is_header"]] = -0.15
    coef[idx["is_right_foot"]] = 0.0
    coef[idx["is_volley"]] = -0.20
    coef[idx["is_big_chance"]] = 1.50
    coef[idx["is_one_on_one"]] = 1.20
    coef[idx["is_fast_break"]] = 0.40
    coef[idx["is_from_corner"]] = -0.30
    coef[idx["is_set_piece"]] = -0.15
    coef[idx["is_free_kick"]] = -0.40
    coef[idx["is_individual_play"]] = -0.30
    coef[idx["is_rebound"]] = 0.30
    coef[idx["assist_is_cross"]] = -0.10
    coef[idx["assist_is_through_ball"]] = 0.40
    coef[idx["assist_is_pull_back"]] = 0.50
    coef[idx["assist_is_long_ball"]] = -0.10
    coef[idx["is_unassisted"]] = -0.20

    model.coef_ = coef
    model.intercept_ = -2.0
    return model


# Module-level model instance (lazy-loaded)
_XG_MODEL: Optional[XGModel] = None

_MODEL_CACHE_PATH = CACHE_DIR / "xg_model.pkl"


def _count_shot_csvs() -> int:
    """Count total raw CSV files across all seasons (used as freshness fingerprint)."""
    return sum(
        1
        for season_dir in RAW_DATA_DIR.glob("serie_a_*")
        for _ in (season_dir / "events").glob("*.csv")
        if (season_dir / "events").exists()
    )


def _get_model() -> XGModel:
    """
    Return the trained xG model.

    Load from disk cache if fresh (same CSV count as when trained).
    Train from scratch and save to cache otherwise.
    """
    global _XG_MODEL
    if _XG_MODEL is not None:
        return _XG_MODEL

    from src.utils.logging import log

    current_csv_count = _count_shot_csvs()

    # Try loading from cache
    if _MODEL_CACHE_PATH.exists():
        result = XGModel.load(_MODEL_CACHE_PATH)
        if result is not None:
            model, cached_csv_count = result
            if cached_csv_count == current_csv_count:
                log.info(
                    "xG model: loaded from cache (%d CSVs, weights intact)",
                    current_csv_count,
                )
                _XG_MODEL = model
                return _XG_MODEL
            else:
                log.info(
                    "xG model: cache stale (%d → %d CSVs) — retraining",
                    cached_csv_count,
                    current_csv_count,
                )

    # Train and persist
    _XG_MODEL = _train_model()
    try:
        _XG_MODEL.save(_MODEL_CACHE_PATH, current_csv_count)
        log.info("xG model: saved to cache at %s", _MODEL_CACHE_PATH)
    except Exception as e:
        log.warning("xG model: could not save cache — %s", e)

    return _XG_MODEL


# ═══════════════════════════════════════════════════════════════════════════════
# PER-SHOT xG CALCULATION (public API — backward-compatible)
# ═══════════════════════════════════════════════════════════════════════════════

def compute_shot_xg(row: pd.Series) -> float:
    """
    Compute xG for a single shot event (row-level API).

    Backward-compatible wrapper.  For batch use prefer compute_batch_xg().
    Note: rebound and assist features are unavailable in single-row mode.
    """
    # Penalty → fixed xG
    if "Penalty" in row.index and pd.notna(row.get("Penalty")):
        return PENALTY_XG

    # Own goal → 0
    if "own goal" in row.index and pd.notna(row.get("own goal")):
        return 0.0

    model = _get_model()
    features = {
        "distance_to_goal": _distance_to_goal(row["x"], row["y"]),
        "angle_to_goal": _angle_to_goal(row["x"], row["y"]),
        "is_header": 1 if pd.notna(row.get("Head")) else 0,
        "is_right_foot": 1 if pd.notna(row.get("Right footed")) else 0,
        "is_volley": 1 if pd.notna(row.get("Volley")) else 0,
        "is_big_chance": 1 if pd.notna(row.get("Big Chance")) else 0,
        "is_one_on_one": 1 if pd.notna(row.get("1 on 1")) else 0,
        "is_fast_break": 1 if pd.notna(row.get("Fast break")) else 0,
        "is_from_corner": 1 if pd.notna(row.get("From corner")) else 0,
        "is_set_piece": 1 if pd.notna(row.get("Set piece")) else 0,
        "is_free_kick": 1 if pd.notna(row.get("Free kick")) else 0,
        "is_individual_play": 1 if pd.notna(row.get("Individual Play")) else 0,
        "is_rebound": 0,
        "assist_is_cross": 0,
        "assist_is_through_ball": 0,
        "assist_is_pull_back": 0,
        "assist_is_long_ball": 0,
        "is_unassisted": 1 if pd.isna(row.get("Related event ID")) else 0,
    }
    return model.predict_single(features)


def compute_batch_xg(shots_df: pd.DataFrame,
                     all_events_by_match: Optional[dict] = None) -> pd.Series:
    """
    Compute xG for a DataFrame of shots (batch prediction).

    Handles penalties, own goals, rebounds, and assist features.
    This is the preferred method for season-level computation.
    """
    model = _get_model()
    xg = pd.Series(0.0, index=shots_df.index, dtype=float)

    # Penalties → fixed xG
    _no_flag = pd.Series(False, index=shots_df.index)
    pen_mask = shots_df["Penalty"].notna() if "Penalty" in shots_df.columns else _no_flag
    xg.loc[pen_mask] = PENALTY_XG

    # Own goals → 0
    og_mask = shots_df["own goal"].notna() if "own goal" in shots_df.columns else _no_flag
    xg.loc[og_mask] = 0.0

    # Non-penalty, non-own-goal shots → model prediction
    model_mask = ~pen_mask & ~og_mask
    if model_mask.any():
        model_shots = shots_df.loc[model_mask].copy()
        model_shots = engineer_features(model_shots, all_events_by_match)
        X = model_shots[FEATURE_COLS].fillna(0).values.astype(np.float64)
        xg.loc[model_mask] = model.predict_proba(X)

    return xg


# ═══════════════════════════════════════════════════════════════════════════════
# SEASON-LEVEL AGGREGATION
# ═══════════════════════════════════════════════════════════════════════════════

def load_season_shots(season: str) -> pd.DataFrame:
    """
    Load all shot events for a season from CSV files.

    Returns a DataFrame with one row per shot, including xG.
    Uses batch prediction with full event context (rebounds + assists).
    """
    events_dir = RAW_DATA_DIR / f"serie_a_{season}" / "events"
    if not events_dir.exists():
        return pd.DataFrame()

    csv_files = sorted(events_dir.glob("*.csv"))
    shot_frames = []
    all_events_by_match: dict[str, pd.DataFrame] = {}

    for fp in csv_files:
        try:
            df = pd.read_csv(fp, low_memory=False)
            all_events_by_match[fp.name] = df

            shots = df[df["type_id"].isin(SHOT_TYPE_IDS)].copy()
            if shots.empty:
                continue

            shots["_match_file"] = fp.name
            shots["match_file"] = fp.name

            # Parse home/away from filename
            parts = fp.stem.split("_")
            if len(parts) >= 3:
                shots["_home_csv"] = canonical_name(parts[1])
                shots["_away_csv"] = canonical_name(parts[2])

            shot_frames.append(shots)
        except Exception:
            continue

    if not shot_frames:
        return pd.DataFrame()

    all_shots = pd.concat(shot_frames, ignore_index=True).copy()

    # Compute derived columns all at once to avoid DataFrame fragmentation
    team_col = all_shots["team_name"].apply(
        lambda n: canonical_name(n) if pd.notna(n) else n
    )
    xg_col = compute_batch_xg(all_shots, all_events_by_match)
    goal_col = (all_shots["type_id"] == 16).astype(int)

    all_shots = all_shots.assign(team=team_col, xG=xg_col, is_goal=goal_col)

    return all_shots


def compute_team_xg_summary(season: str) -> pd.DataFrame:
    """
    Compute aggregated xG and goals for every team in a season.

    Returns DataFrame with columns:
        Team, Season, GF, GA, xG, xGC, xG_diff, Shots, ShotsAgainst
    """
    shots = load_season_shots(season)
    if shots.empty:
        return pd.DataFrame()

    season_label = season.replace("_", "/")

    # --- xG for (team scoring) ---
    team_xg = (
        shots
        .groupby("team")
        .agg(
            xG=("xG", "sum"),
            GF=("is_goal", "sum"),
            Shots=("xG", "count"),
        )
        .reset_index()
        .rename(columns={"team": "Team"})
    )

    # --- xG against (opponent's shots) ---
    def _get_opponent(row):
        team = row["team"]
        home = row.get("_home_csv", "")
        away = row.get("_away_csv", "")
        if team == home:
            return away
        elif team == away:
            return home
        return None

    shots = shots.copy()
    shots["opponent"] = shots.apply(_get_opponent, axis=1)
    shots_against = shots.dropna(subset=["opponent"]).copy()

    opponent_xg = (
        shots_against
        .groupby("opponent")
        .agg(
            xGC=("xG", "sum"),
            GA=("is_goal", "sum"),
            ShotsAgainst=("xG", "count"),
        )
        .reset_index()
        .rename(columns={"opponent": "Team"})
    )

    # Merge
    summary = team_xg.merge(opponent_xg, on="Team", how="outer").fillna(0)
    summary["Season"] = season_label
    summary["xG"] = summary["xG"].round(2)
    summary["xGC"] = summary["xGC"].round(2)
    summary["xG_diff"] = (summary["xG"] - summary["xGC"]).round(2)

    for col in ["GF", "GA", "Shots", "ShotsAgainst"]:
        summary[col] = summary[col].astype(int)

    return summary.sort_values("xG", ascending=False).reset_index(drop=True)
