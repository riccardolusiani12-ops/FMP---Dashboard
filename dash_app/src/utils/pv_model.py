"""
Possession Value Model — ML-based loader
=========================================
Singleton wrapper around the pre-trained ML model (``pv_model_serie_a.pkl``).
Trained on Opta Serie A event data from 2008-2009 to 2025-2026
(8.6 M events, 24 features).

The model predicts **P(goal | game_state)** for every on-ball event in a
possession chain.  This replaces the old xT grid (lookup table of zone →
probability) with a supervised classifier that incorporates both spatial
and contextual features.

Possession Value Added (PVA) of an action:
    PVA(t) = score(event_t) − score(event_{t−1})

Positive PVA: action increased P(goal) — e.g. a through-ball into the box.
Negative PVA: action decreased P(goal) — e.g. a back-pass under pressure.

Public API
----------
    pv = PossessionValueModel.get_instance()

    pv.score(x, y, type_id, outcome, **kwargs)    → float  [0, 1]
    pv.delta(x_from, y_from, x_to, y_to, ...)     → float  [−1, 1]
    pv.score_sequence(events)                      → list[float]
    pv.pva_sequence(events)                        → list[float]

    # Backward-compatible aliases (used by high_regains.py, etc.)
    pv.get_xT(x, y)                               → float
    pv.get_gpa(x, y)                              → float
    pv.get_chain_pv_from_raw_events(df, ...)      → float

All methods are safe with None / NaN inputs (return 0.0).

Coordinate system (Opta standard):
    x: 0 → 100  (own goal → opponent goal)
    y: 0 → 100  (right touchline → left touchline)
    Final Third: x ≥ 66.67
    Penalty Box: x ≥ 83.33 AND 21.1 ≤ y ≤ 78.9
"""

from __future__ import annotations

import logging
import math
import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

log = logging.getLogger("dashboard.pv_model_util")

# Default model path — relative to this file's location:
#   utils/ → src/ → models/pv_model_serie_a.pkl
_DEFAULT_MODEL_PATH = (
    Path(__file__).parent.parent / "models" / "pv_model_serie_a.pkl"
)

# Opta constants
_GOAL_X        = 100.0
_GOAL_Y        = 50.0
_HALF_GOAL_OPT = 3.66   # 7.32 m goal ≈ 3.66 Opta units

# Feature column names — must match the order used at training time
FEATURE_COLS = [
    # Spatial
    "x", "y", "x2", "y2", "xy",
    "dist_to_goal", "angle_to_goal",
    "in_box", "in_final_third", "central_corridor", "dist_to_center_y",
    # Event
    "type_id", "outcome",
    "is_pass", "is_carry_touch", "is_recovery", "is_tackle", "is_interception",
    "through_ball", "cross", "head", "aerial",
    # Possession context
    "poss_event_index", "x_max_in_poss_so_far",
]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _safe_float(v: Any) -> Optional[float]:
    """Return float(v) or None if v is None / NaN."""
    if v is None:
        return None
    try:
        f = float(v)
        return None if (f != f) else f   # NaN check without numpy
    except (TypeError, ValueError):
        return None


def _dist_to_goal(x: float, y: float) -> float:
    return math.sqrt((_GOAL_X - x) ** 2 + (_GOAL_Y - y) ** 2)


def _angle_to_goal(x: float, y: float) -> float:
    """Angle (degrees) subtended by the goal posts at (x, y)."""
    dx = _GOAL_X - x
    dy_sq = (y - _GOAL_Y) ** 2
    numerator   = 2.0 * _HALF_GOAL_OPT * dx
    denominator = dx ** 2 + dy_sq - _HALF_GOAL_OPT ** 2
    angle_rad   = math.atan2(numerator, denominator)
    if angle_rad < 0:
        angle_rad += math.pi
    return math.degrees(angle_rad)


# ─── Main class ───────────────────────────────────────────────────────────────

class PossessionValueModel:
    """
    Singleton ML-based Possession Value model.

    Loaded from ``pv_model_serie_a.pkl`` — a dict containing:
        model        : fitted sklearn / xgboost estimator
        model_type   : "logistic_regression" | "xgboost"
        scaler       : StandardScaler or None
        feature_cols : list[str]  (defines column order)

    Falls back to a legacy xT grid if the pkl contains the old format.

    Parameters
    ----------
    model_path : Path, optional
        Override the default pkl path.  Useful in tests.

    Usage
    -----
    >>> pv = PossessionValueModel.get_instance()
    >>> pv.score(85.0, 50.0, type_id=1)     # P(goal) near penalty spot
    >>> pv.delta(70.0, 50.0, 85.0, 50.0)    # P(goal) added by a run
    """

    _instance: Optional["PossessionValueModel"] = None

    # ── Singleton constructor ──────────────────────────────────────────────

    def __init__(self, model_path: Optional[Path] = None) -> None:
        path = Path(model_path) if model_path else _DEFAULT_MODEL_PATH
        self._model:        Any            = None
        self._model_type:   str            = "unknown"
        self._scaler:       Any            = None
        self._feature_cols: List[str]      = FEATURE_COLS
        self._meta:         Dict[str, Any] = {}
        self._loaded:       bool           = False
        self._load(path)

    @classmethod
    def get_instance(
        cls, model_path: Optional[Path] = None
    ) -> "PossessionValueModel":
        """Return the singleton instance, creating it on first call."""
        if cls._instance is None:
            cls._instance = cls(model_path)
        return cls._instance

    # ── Private loader ─────────────────────────────────────────────────────

    def _load(self, path: Path) -> None:
        if not path.exists():
            log.warning(
                "PV model not found at %s — all scores will be 0.0", path
            )
            return
        try:
            with open(path, "rb") as fh:
                data = pickle.load(fh)

            # ── New ML model format ───────────────────────────────────────
            if "model" in data and "feature_cols" in data:
                self._model        = data["model"]
                self._model_type   = data.get("model_type", "unknown")
                self._scaler       = data.get("scaler")
                self._feature_cols = data["feature_cols"]
                self._meta         = {
                    k: v for k, v in data.items()
                    if k not in ("model", "scaler")
                }
                self._loaded = True
                log.info(
                    "PV model (ML) loaded: %s | type=%s | roc_auc_val=%.4f"
                    " | trained_on=%s | seasons=%s",
                    path.name,
                    self._model_type,
                    data.get("roc_auc_val", float("nan")),
                    data.get("trained_on", "?"),
                    data.get("train_seasons", "?"),
                )

            # ── Legacy xT grid format ─────────────────────────────────────
            elif "xT_grid" in data:
                self._xT_grid    = np.array(data["xT_grid"], dtype=np.float64)
                self._model_type = "xt_grid_legacy"
                self._meta       = {k: v for k, v in data.items()
                                    if k not in ("xT_grid", "p_shot_grid",
                                                 "cell_stats")}
                self._loaded = True
                log.warning(
                    "PV model: loaded legacy xT grid from %s. "
                    "Run train_pv_model.py to upgrade to ML model.",
                    path.name,
                )

            else:
                log.error("Unknown model format in %s", path)

        except Exception as exc:
            log.error(
                "Failed to load PV model from %s: %s. "
                "Install scikit-learn: pip install scikit-learn",
                path, exc
            )

    # ── Feature builder ────────────────────────────────────────────────────

    def _build_features(
        self,
        x: float,
        y: float,
        type_id: int = 1,
        outcome: int = 1,
        through_ball: int = 0,
        cross: int = 0,
        head: int = 0,
        aerial: int = 0,
        poss_event_index: int = 0,
        x_max_in_poss: Optional[float] = None,
        distance_to_goal: Optional[float] = None,
        angle_to_goal_deg: Optional[float] = None,
    ) -> np.ndarray:
        """
        Construct the feature vector for a single event.

        Returns a 1-D float32 numpy array in the exact order of
        ``self._feature_cols``.  Missing optional values default to 0.
        """
        x2   = x ** 2
        y2   = y ** 2
        xy   = x * y
        dtg  = distance_to_goal if distance_to_goal is not None \
               else _dist_to_goal(x, y)
        atg  = angle_to_goal_deg if angle_to_goal_deg is not None \
               else _angle_to_goal(x, y)
        in_box           = int(x >= 83.33 and 21.1 <= y <= 78.9)
        in_final_third   = int(x >= 66.67)
        central_corridor = int(33.3 <= y <= 66.7)
        dtcy             = abs(y - 50.0)
        is_pass         = int(type_id == 1)
        is_carry_touch  = int(type_id == 44)
        is_recovery     = int(type_id == 49)
        is_tackle       = int(type_id == 7)
        is_interception = int(type_id == 8)
        x_max = x_max_in_poss if x_max_in_poss is not None else x

        feature_map = {
            "x":                    x,
            "y":                    y,
            "x2":                   x2,
            "y2":                   y2,
            "xy":                   xy,
            "dist_to_goal":         dtg,
            "angle_to_goal":        atg,
            "in_box":               in_box,
            "in_final_third":       in_final_third,
            "central_corridor":     central_corridor,
            "dist_to_center_y":     dtcy,
            "type_id":              type_id,
            "outcome":              outcome,
            "is_pass":              is_pass,
            "is_carry_touch":       is_carry_touch,
            "is_recovery":          is_recovery,
            "is_tackle":            is_tackle,
            "is_interception":      is_interception,
            "through_ball":         through_ball,
            "cross":                cross,
            "head":                 head,
            "aerial":               aerial,
            "poss_event_index":     poss_event_index,
            "x_max_in_poss_so_far": x_max,
        }
        return np.array(
            [feature_map.get(c, 0.0) for c in self._feature_cols],
            dtype=np.float32,
        )

    # ── Public API ─────────────────────────────────────────────────────────

    def score(
        self,
        x,
        y,
        type_id: int = 1,
        outcome: int = 1,
        **kwargs,
    ) -> float:
        """
        Return P(goal | game_state) for a single event.

        Parameters
        ----------
        x, y : float or None
            Opta coordinates (0-100 each).
        type_id : int
            Opta event type ID (default 1 = pass).
        outcome : int
            1 = successful, 0 = unsuccessful.
        **kwargs
            Optional: through_ball, cross, head, aerial,
            poss_event_index, x_max_in_poss, distance_to_goal,
            angle_to_goal_deg.

        Returns
        -------
        float
            P(goal) ∈ [0, 1].  Returns 0.0 for None / NaN inputs.
        """
        xf = _safe_float(x)
        yf = _safe_float(y)
        if xf is None or yf is None:
            return 0.0

        if self._model_type == "xt_grid_legacy":
            return self._xt_grid_score(xf, yf)

        if self._model is None:
            return 0.0

        try:
            feats = self._build_features(
                x=xf, y=yf,
                type_id=int(type_id or 1),
                outcome=int(outcome or 0),
                through_ball=int(kwargs.get("through_ball", 0) or 0),
                cross=int(kwargs.get("cross", 0) or 0),
                head=int(kwargs.get("head", 0) or 0),
                aerial=int(kwargs.get("aerial", 0) or 0),
                poss_event_index=int(kwargs.get("poss_event_index", 0) or 0),
                x_max_in_poss=_safe_float(kwargs.get("x_max_in_poss")),
                distance_to_goal=_safe_float(kwargs.get("distance_to_goal")),
                angle_to_goal_deg=_safe_float(kwargs.get("angle_to_goal_deg")),
            )
            X = feats.reshape(1, -1)
            if self._scaler is not None:
                X = self._scaler.transform(X)
            return float(self._model.predict_proba(X)[0, 1])
        except Exception as exc:
            log.debug("PV score error at (%.1f, %.1f): %s", xf, yf, exc)
            return 0.0

    def delta(
        self,
        x_from,
        y_from,
        x_to,
        y_to,
        type_id_from: int = 1,
        type_id_to: int = 1,
        **kwargs,
    ) -> float:
        """
        Return PVA = P(goal | state_to) − P(goal | state_from).

        Positive: action increased goal probability.
        Negative: action decreased goal probability (e.g. back-pass).

        Parameters
        ----------
        x_from, y_from : float
            Start location (before the action).
        x_to, y_to : float
            End location (after the action).
        type_id_from, type_id_to : int
            Opta type IDs for origin and destination events.

        Returns
        -------
        float
            score(to) − score(from).  Returns 0.0 if any coord is None/NaN.
        """
        return (
            self.score(x_to, y_to, type_id=type_id_to)
            - self.score(x_from, y_from, type_id=type_id_from)
        )

    def score_sequence(self, events: List[Dict]) -> List[float]:
        """
        Return P(goal) for each event in a possession chain.

        Parameters
        ----------
        events : list[dict]
            Each dict must contain ``"x"`` and ``"y"`` keys.
            Optional: type_id, outcome, through_ball, cross, head, aerial.
            poss_event_index is computed automatically.

        Returns
        -------
        list[float]
            P(goal) per event, in input order.
        """
        if not events:
            return []
        scores = []
        x_max_so_far = 0.0
        for idx, ev in enumerate(events):
            xv = _safe_float(ev.get("x")) or 0.0
            yv = _safe_float(ev.get("y")) or 0.0
            x_max_so_far = max(x_max_so_far, xv)
            s = self.score(
                xv, yv,
                type_id=int(ev.get("type_id", 1) or 1),
                outcome=int(ev.get("outcome", 1) or 1),
                through_ball=int(ev.get("through_ball", 0) or 0),
                cross=int(ev.get("cross", 0) or 0),
                head=int(ev.get("head", 0) or 0),
                aerial=int(ev.get("aerial", 0) or 0),
                poss_event_index=idx,
                x_max_in_poss=x_max_so_far,
            )
            scores.append(s)
        return scores

    def pva_sequence(self, events: List[Dict]) -> List[float]:
        """
        Return Possession Value Added for each event in a chain.

        PVA[0] = score(events[0])                    (first event)
        PVA[i] = score(events[i]) − score(events[i−1])  for i > 0

        Returns
        -------
        list[float]  — same length as events.
        """
        scores = self.score_sequence(events)
        if not scores:
            return []
        pva = [scores[0]]
        for i in range(1, len(scores)):
            pva.append(scores[i] - scores[i - 1])
        return pva

    # ── Backward-compatibility aliases ─────────────────────────────────────

    def get_xT(self, x, y) -> float:
        """Alias for ``score(x, y, type_id=1)`` — backward compatible."""
        return self.score(x, y, type_id=1)

    def get_gpa(self, x, y) -> float:
        """Alias for ``get_xT`` — Goal Probability at (x, y)."""
        return self.get_xT(x, y)

    def get_chain_pv_from_raw_events(
        self,
        poss_events,           # pd.DataFrame
        ft_entry_time: float = 0.0,
        shot_time: float = 0.0,
    ) -> float:
        """
        Backward-compatible: compute PV delta from FT entry to shot.

        Used by legacy callers that still pass a raw events DataFrame.
        Locates the FT-entry event and the shot event by match second,
        then delegates to ``delta()``.
        """
        try:
            if poss_events is None or len(poss_events) == 0:
                return 0.0

            def _sec(row):
                return (float(row.get("minute", 0) or 0) * 60
                        + float(row.get("second", 0) or 0))

            ft_event = None
            for i in range(len(poss_events)):
                row = poss_events.iloc[i]
                if _sec(row) >= ft_entry_time:
                    ft_event = row
                    break

            shot_event = None
            for i in range(len(poss_events) - 1, -1, -1):
                row = poss_events.iloc[i]
                if _sec(row) <= shot_time:
                    shot_event = row
                    break

            if ft_event is None or shot_event is None:
                return 0.0

            return self.delta(
                x_from=float(ft_event.get("x", 0) or 0),
                y_from=float(ft_event.get("y", 50) or 50),
                x_to=float(shot_event.get("x", 0) or 0),
                y_to=float(shot_event.get("y", 50) or 50),
                type_id_from=int(ft_event.get("type_id", 1) or 1),
                type_id_to=int(shot_event.get("type_id", 16) or 16),
            )
        except Exception as exc:
            log.debug("get_chain_pv_from_raw_events error: %s", exc)
            return 0.0

    # ── Legacy xT grid fallback ────────────────────────────────────────────

    def _xt_grid_score(self, x: float, y: float) -> float:
        """Score using the legacy 16×12 xT grid (if loaded from old pkl)."""
        if not hasattr(self, "_xT_grid"):
            return 0.0
        grid = self._xT_grid
        n_x, n_y = grid.shape
        col = max(0, min(int(x / (100.0 / n_x)), n_x - 1))
        row = max(0, min(int(y / (100.0 / n_y)), n_y - 1))
        return float(grid[col, row])

    # ── Diagnostics / repr ─────────────────────────────────────────────────

    @property
    def loaded(self) -> bool:
        """True if the model pkl was successfully loaded."""
        return self._loaded

    @property
    def meta(self) -> Dict:
        """Model metadata (seasons, roc_auc, etc.)."""
        return dict(self._meta)

    def __repr__(self) -> str:  # pragma: no cover
        status = "loaded" if self._loaded else "fallback"
        return (
            f"PossessionValueModel({status}, "
            f"type={self._model_type}, "
            f"n_features={len(self._feature_cols)})"
        )
