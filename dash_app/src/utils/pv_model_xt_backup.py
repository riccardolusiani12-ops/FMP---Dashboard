"""
Possession Value Model — lightweight loader
===========================================
Singleton wrapper around the pre-trained xT-style grid model
(``pv_model_serie_a.pkl``).  Trained on Opta Serie A event data
from 2008-2009 to 2025-2026 (8.6 M events, 16×12 pitch grid).

Smoothing: gaussian_filter(sigma=0.8) — applied to reduce artefacts
in low-density lateral zones while preserving the central-zone gradient.

Public API
----------
    pv = PossessionValueModel.get_instance()

    pv.score(x, y)                            → float
    pv.delta(x_from, y_from, x_to, y_to)     → float
    pv.score_sequence(events)                 → list[float]

All methods are safe with None / NaN inputs (return 0.0).

Coordinate system (Opta standard):
    x: 0 → 100  (own goal → opponent goal)
    y: 0 → 100  (right touchline → left touchline)
"""

from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

log = logging.getLogger("dashboard.pv_model_util")

# Default model path — relative to this file's location:
#   utils/ → src/ → models/pv_model_serie_a.pkl
_DEFAULT_MODEL_PATH = (
    Path(__file__).parent.parent / "models" / "pv_model_serie_a.pkl"
)

# Grid constants (must match trained model)
_N_X = 16
_N_Y = 12
_X_STEP = 100.0 / _N_X   # 6.25 units per cell
_Y_STEP = 100.0 / _N_Y   # ~8.33 units per cell


def _xy_to_cell(x: float, y: float) -> tuple[int, int]:
    """Convert Opta (x, y) to grid (col, row), clamped to valid range."""
    col = min(int(x / _X_STEP), _N_X - 1)
    row = min(int(y / _Y_STEP), _N_Y - 1)
    return max(col, 0), max(row, 0)


def _safe_float(v) -> Optional[float]:
    """Return float(v) or None if v is None / NaN."""
    if v is None:
        return None
    try:
        f = float(v)
        return None if np.isnan(f) else f
    except (TypeError, ValueError):
        return None


class PossessionValueModel:
    """Singleton xT-grid model loaded from ``pv_model_serie_a.pkl``.

    Parameters
    ----------
    model_path : Path, optional
        Override the default pkl path.  Useful in tests.

    Usage
    -----
    >>> pv = PossessionValueModel.get_instance()
    >>> pv.score(85.0, 50.0)          # xT at the penalty spot
    >>> pv.delta(70.0, 50.0, 85.0, 50.0)   # value added by a run
    """

    _instance: Optional["PossessionValueModel"] = None

    # ──────────────────────────────────────────────────────────────────
    # Singleton constructor
    # ──────────────────────────────────────────────────────────────────

    def __init__(self, model_path: Optional[Path] = None) -> None:
        path = Path(model_path) if model_path else _DEFAULT_MODEL_PATH
        self._xT_grid:     np.ndarray = np.zeros((_N_X, _N_Y), dtype=np.float64)
        self._p_shot_grid: np.ndarray = np.zeros((_N_X, _N_Y), dtype=np.float64)
        self._meta: Dict   = {}
        self._loaded: bool = False
        self._load(path)

    @classmethod
    def get_instance(cls, model_path: Optional[Path] = None) -> "PossessionValueModel":
        """Return the singleton instance, creating it on first call."""
        if cls._instance is None:
            cls._instance = cls(model_path)
        return cls._instance

    # ──────────────────────────────────────────────────────────────────
    # Private loader
    # ──────────────────────────────────────────────────────────────────

    def _load(self, path: Path) -> None:
        if not path.exists():
            log.warning("PV model not found at %s — all scores will be 0.0", path)
            return
        try:
            with open(path, "rb") as fh:
                data = pickle.load(fh)
            self._xT_grid     = np.array(data["xT_grid"],     dtype=np.float64)
            self._p_shot_grid = np.array(data["p_shot_grid"], dtype=np.float64)
            self._meta        = {k: v for k, v in data.items()
                                 if k not in ("xT_grid", "p_shot_grid", "cell_stats")}
            self._loaded = True
            log.info(
                "PV model loaded: %s | xT max=%.4f | trained_on=%s | seasons=%s",
                path.name,
                self._xT_grid.max(),
                data.get("trained_on", "?"),
                data.get("seasons", "?"),
            )
        except Exception as exc:
            log.error("Failed to load PV model from %s: %s", path, exc)

    # ──────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────

    def score(self, x, y) -> float:
        """Return the absolute xT value at pitch location (x, y).

        Parameters
        ----------
        x, y : float or None
            Opta coordinates (0-100 each).

        Returns
        -------
        float
            xT ∈ [0, xT_max].  Returns 0.0 for None / NaN inputs or if
            the model was not loaded.
        """
        xf = _safe_float(x)
        yf = _safe_float(y)
        if xf is None or yf is None:
            return 0.0
        col, row = _xy_to_cell(xf, yf)
        return float(self._xT_grid[col, row])

    def delta(self, x_from, y_from, x_to, y_to) -> float:
        """Return the xT delta between two pitch locations.

        Positive values indicate the destination is more dangerous.
        Negative values mean the ball moved to a less dangerous zone
        (e.g. sideways pass out of the box).

        Parameters
        ----------
        x_from, y_from, x_to, y_to : float or None
            Opta coordinates for origin and destination.

        Returns
        -------
        float
            score(x_to, y_to) − score(x_from, y_from).
            Returns 0.0 if any coordinate is None / NaN.
        """
        return self.score(x_to, y_to) - self.score(x_from, y_from)

    def score_sequence(self, events: List[Dict]) -> List[float]:
        """Return xT scores for a list of event dicts.

        Each dict must have ``"x"`` and ``"y"`` keys (Opta coordinates).
        Missing / None / NaN values produce 0.0 for that event.

        Parameters
        ----------
        events : list[dict]
            List of event dicts, typically a possession chain.

        Returns
        -------
        list[float]
            xT score for each event, in the same order as *events*.

        Example
        -------
        >>> chain = [{"x": 70, "y": 50}, {"x": 85, "y": 48}]
        >>> pv.score_sequence(chain)
        [0.023, 0.041]
        """
        if not events:
            return []
        return [self.score(ev.get("x"), ev.get("y")) for ev in events]

    # ──────────────────────────────────────────────────────────────────
    # Diagnostics / repr
    # ──────────────────────────────────────────────────────────────────

    @property
    def loaded(self) -> bool:
        """True if the model pkl was successfully loaded."""
        return self._loaded

    @property
    def meta(self) -> Dict:
        """Model metadata (seasons, total_events, smoothing, etc.)."""
        return dict(self._meta)

    def __repr__(self) -> str:  # pragma: no cover
        status = "loaded" if self._loaded else "fallback"
        return (
            f"PossessionValueModel({status}, "
            f"grid={_N_X}×{_N_Y}, "
            f"xT_max={self._xT_grid.max():.4f})"
        )
