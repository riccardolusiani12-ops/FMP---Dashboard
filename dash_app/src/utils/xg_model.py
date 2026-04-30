"""
Fallback xG Logistic Regression Model
========================================
Simple positional xG model for when Opta xG is not available
in the CSV.  Uses a logistic regression trained on shot events.

This module wraps the existing ``src.analytics.xg.XGModel`` and
provides a simpler interface for the Chance Creation module.

The primary xG source should be the existing ``xg.py`` module;
this module is a thin adapter that provides the same interface
expected by ``chance_creation.py``.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

log = logging.getLogger("dashboard.xg_fallback")


# ═══════════════════════════════════════════════════════════════════════════════
# xG ESTIMATION — delegates to existing model
# ═══════════════════════════════════════════════════════════════════════════════

def compute_xg_for_shot(row: pd.Series) -> float:
    """
    Compute xG for a single shot row.

    Delegates to ``src.analytics.xg.compute_shot_xg()``.
    """
    from src.analytics.xg import compute_shot_xg
    return compute_shot_xg(row)


def compute_batch_xg_values(shots_df: pd.DataFrame,
                            all_events_by_match: Optional[dict] = None) -> pd.Series:
    """
    Compute xG for a DataFrame of shots (batch).

    Delegates to ``src.analytics.xg.compute_batch_xg()``.
    """
    from src.analytics.xg import compute_batch_xg
    return compute_batch_xg(shots_df, all_events_by_match)


# ═══════════════════════════════════════════════════════════════════════════════
# xGOT ESTIMATION (FALLBACK)
# ═══════════════════════════════════════════════════════════════════════════════

def estimate_xgot(xg: float, y: float, on_target: bool) -> float:
    """
    Estimate xGOT from xG and shot location.

    **This is a simplified approximation.** Only applies to on-target shots.

    Parameters
    ----------
    xg : float
        The expected goals value for the shot.
    y : float
        The y-coordinate of the shot (0–100 scale).
    on_target : bool
        Whether the shot was on target (saved or goal).

    Returns
    -------
    float — estimated xGOT.  Returns 0.0 if not on target.

    NOTE: This is a rough estimation — Opta xGOT accounts for
    shot placement, speed, and GK positioning which are not
    available in our data.
    """
    if not on_target:
        return 0.0

    # Placement bonus based on y-coordinate offset from centre
    y_offset = abs(y - 50.0)
    if y_offset > 25.0:
        placement_bonus = 0.15  # near/far post quadrant
    else:
        placement_bonus = 0.05  # central shot

    xgot = xg * (1.0 + placement_bonus)
    return round(min(xgot, 0.99), 4)
