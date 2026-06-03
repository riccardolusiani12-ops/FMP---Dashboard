"""
Defensive Phase — D4: Chances Conceded
=======================================
Analyses shots conceded by *team* — i.e. every shot taken **by the
opponent** — and classifies how each shot was created, where it came
from on the pitch, and how dangerous it was.

This module is the defensive mirror of ``chance_creation.py``.
It re-uses the exact same ``analyse_chance_creation`` engine applied to
the **opponent** team, then:

  1. Flips the Opta coordinates (x → 100−x, y → 100−y) so every shot
     location is expressed from the **analysed team's** defensive
     reference frame (own penalty area near x = 0).
  2. Renames a handful of keys to make the defensive context clear
     (e.g. ``chain_to_goal_matrix`` → ``chain_to_concede_matrix``,
     row ``GS`` → ``GC``).
  3. Adds ``opponent`` (str) to the output for display.

Relevant Opta event types considered (via chance_creation engine)
──────────────────────────────────────────────────────────────────
  13  Miss            — shot wide/over; off target
  14  Post            — shot hits woodwork
  15  Saved Shot      — shot saved (on target)
  16  Goal            — goal scored (goal conceded by analysed team)

Key qualifiers leveraged by the origin classifier
──────────────────────────────────────────────────
  Q2   Cross           — shot preceded by cross
  Q4   Through Ball    — shot set up by through-ball pass
  Q5   Free kick taken — dead-ball restart
  Q6   Corner taken    — corner restart
  Q9   Penalty         — penalty kick
  Q22  Regular play    — open-play shot
  Q23  Fast break      — transition shot
  Q24  Set piece (crossed FK)
  Q25  From corner     — shot directly from corner situation
  Q26  Free kick (direct)
  Q107 Throw In        — throw-in restart
  Q124 Goal Kick       — GK distribution restart (excluded from Set Piece)
  Q133 Deflection      — deflected shot
  Q154 Intentional Assist
  Q210 Assist          — preceding pass was an assist
  Q214 Big Chance      — clear-cut scoring opportunity
  Q215 Individual Play — solo effort, no assist

Attack Origin taxonomy (same as offensive phase)
─────────────────────────────────────────────────
  Priority 1 — Through Ball (qualifier 4 on preceding pass — highest priority)
  Priority 2 — Set Piece    (corner / free kick / throw-in / penalty)
  Priority 3 — High Regain  (opponent recovery in their own final third → fast shot)
  Priority 4 — Cross        (cross qualifier or wide-zone pass)
  Priority 5 — Cut Back     (pull-back qualifier Q195 from the by-line)
  Default    — Combination  (patient build-up)

Coordinate system (after flip — analysed team's frame)
───────────────────────────────────────────────────────
  x : 0 = own goal-line   → 100 = opponent goal-line
  y : 0 = right touchline → 100 = left touchline
  Own penalty area: x ∈ [0, 16.5], y ∈ [21, 79]
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from src.analytics.goalkeeper_buildup import _load_match_events
from src.analytics.chance_creation import analyse_chance_creation, ORIGIN_LABELS
from src.team_mapping import canonical_name

log = logging.getLogger("dashboard.chance_conceded")


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _find_opponent(df: pd.DataFrame, team_lower: str) -> Optional[str]:
    """Return the first team name that is NOT *team_lower* (canonical)."""
    for t in df["team_name"].dropna().unique():
        if canonical_name(str(t)).lower() != team_lower:
            return str(t)
    return None


def _flip_coords(shots: list[dict]) -> None:
    """Flip x and y in-place so shots are in the defending team's frame."""
    for s in shots:
        s["x"] = round(100.0 - float(s.get("x", 50)), 4)
        s["y"] = round(100.0 - float(s.get("y", 50)), 4)


def _rename_gs_to_gc(matrix: dict) -> dict:
    """Return a copy of the chain matrix with row key 'GS' renamed to 'GC'."""
    out: dict = {}
    for origin, rows in matrix.items():
        out[origin] = {}
        for k, v in rows.items():
            out[origin]["GC" if k == "GS" else k] = v
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def analyse_chance_conceded(
    match_csv: Path,
    team: str,
    pv_model: Optional[Any] = None,
) -> dict[str, Any]:
    """
    Compute Chance Conceded metrics for *team* in the given match.

    Internally runs ``analyse_chance_creation`` for the **opponent** and
    re-frames the result from the defending team's perspective.

    Parameters
    ----------
    match_csv : Path
        Path to the match CSV file.
    team : str
        The analysed / defending team.
    pv_model : optional
        Pre-built PV model passed through to the chance creation engine.

    Returns
    -------
    dict consumed by ``chance_conceded_card()``.
    """
    team_lower = canonical_name(str(team)).lower()

    df = _load_match_events(match_csv)
    if df.empty:
        log.warning("Empty match data: %s", match_csv)
        return _empty_result()

    opponent = _find_opponent(df, team_lower)
    if opponent is None:
        log.warning("Could not find opponent for %s in %s", team, match_csv)
        return _empty_result()

    log.debug("Chance Conceded: analysing opponent '%s' vs '%s'", opponent, team)

    # ── Run chance creation analysis for the opponent ─────────────────────
    opp_data = analyse_chance_creation(match_csv, opponent, pv_model=pv_model)

    # ── Flip coordinates (opponent frame → defending team frame) ──────────
    shots: list[dict] = opp_data.get("shots_detail", [])
    _flip_coords(shots)

    # ── Re-map chain matrix: GS → GC ──────────────────────────────────────
    matrix = _rename_gs_to_gc(opp_data.get("chain_to_goal_matrix", {}))

    # ── Build shot metrics with defensive naming ──────────────────────────
    sm_raw = opp_data.get("shot_metrics", {})
    shot_metrics: dict[str, Any] = {
        "shots_total":    sm_raw.get("shots_total", 0),
        "shots_in_box":   sm_raw.get("shots_in_box", 0),
        "shots_out_box":  sm_raw.get("shots_out_box", 0),
        "sot_pct_total":  sm_raw.get("sot_pct_total", 0.0),
        "xg_per_shot":    sm_raw.get("xg_per_shot", 0.0),
        "shot_freq_pct":  sm_raw.get("shot_freq_pct", 0.0),
        "pct_in_box":     sm_raw.get("pct_in_box", 0.0),
        "pct_out_box":    sm_raw.get("pct_out_box", 0.0),
    }

    # ── Add convenience aggregates from shots ─────────────────────────────────────
    goals_conceded   = sum(1 for s in shots if s.get("is_goal"))
    xg_against_total = sum(s.get("xG", 0.0) for s in shots)
    # Big chances: use the quality_tier flag (set from Opta Big Chance qualifier)
    big_chances      = sum(1 for s in shots if s.get("quality_tier") == 2)

    # ── Pass shot quality tiers through (rename GS→GC key not needed here) ───
    shot_quality_tiers = opp_data.get("shot_quality_tiers", {})

    return {
        # Core data
        "chain_to_concede_matrix": matrix,
        "shot_metrics":            shot_metrics,
        "shots_detail":            shots,
        "shot_quality_tiers":      shot_quality_tiers,
        # Convenience aggregates
        "goals_conceded":          goals_conceded,
        "xg_against":              round(xg_against_total, 2),
        "big_chances_conceded":    big_chances,
        # Context
        "opponent":                canonical_name(opponent),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# EMPTY RESULT
# ═══════════════════════════════════════════════════════════════════════════════

def _empty_result() -> dict[str, Any]:
    empty_origin = {"N": 0, "xG": 0.0, "SoT%": 0.0, "GC": 0}
    return {
        "chain_to_concede_matrix": {
            label: dict(empty_origin)
            for label in ORIGIN_LABELS + ["TOTAL"]
        },
        "shot_metrics": {
            "shots_total": 0,
            "shots_in_box": 0,
            "shots_out_box": 0,
            "sot_pct_total": 0.0,
            "xg_per_shot": 0.0,
            "shot_freq_pct": 0.0,
            "pct_in_box": 0.0,
            "pct_out_box": 0.0,
        },
        "shot_quality_tiers": {
            "level_3_converted": {"count": 0, "pct": 0.0},
            "level_2_threat":    {"count": 0, "pct": 0.0},
            "level_0_low":       {"count": 0, "pct": 0.0},
        },
        "shots_detail":         [],
        "goals_conceded":       0,
        "xg_against":           0.0,
        "big_chances_conceded": 0,
        "opponent":             "Unknown",
    }
