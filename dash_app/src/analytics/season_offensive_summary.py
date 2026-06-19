"""
Season-level Offensive Phase Aggregation
==========================================
Reads precomputed Parquet files produced by precompute_season_offensive()
instead of scanning raw match CSVs.  Callbacks call these functions; they
never touch CSVs directly.

Performance profile (root cause of the original 50s load):
  - GK buildup  ~0.5s × 38 matches = ~19s  \
  - FT entries  ~1.0s × 38 matches = ~40s   } serial CSV scan in callbacks
  - Chance crtn ~0.2s × 38 matches = ~8s   /
  Total serial: ~67s  (all inside the Dash callback thread)

Fix — three layers:
  Layer 1: precompute_season_offensive() writes four parquets at pipeline time.
  Layer 2: these functions read + filter those parquets (milliseconds per call).
  Layer 3: TTL in-memory cache keeps each season-parquet hot after first read.

Public API (unchanged — callbacks use these names):
    compute_season_gk_buildup(season, team_name)
    compute_season_ft_entries(season, team_name)
    compute_season_chance_creation(season, team_name)
    compute_league_offensive_benchmarks(season)
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from src.config import READY_DATA_DIR
from src.team_mapping import canonical_name
from src.utils.caching import cache_get, cache_set
from src.utils.logging import log


# ═══════════════════════════════════════════════════════════════════════════════
# INTERNAL — parquet loader with in-memory cache (season-level granularity)
# ═══════════════════════════════════════════════════════════════════════════════

def _load_offensive_parquet(data_type: str, season: str) -> Optional[pd.DataFrame]:
    """
    Load a season offensive parquet with in-memory TTL cache.

    Cache key is season-level (not team-level) — one disk read per season
    per app session, regardless of how many teams the user views.

    Parameters
    ----------
    data_type : str
        One of: ``"gk_events"``, ``"ft_entries"``, ``"shots"``,
        ``"offensive_summary"``.
    season : str
        Season key, e.g. ``"2025_2026"``.
    """
    cache_key = f"opp_offensive_{data_type}_{season}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    path = READY_DATA_DIR / f"{data_type}_{season}.parquet"
    if not path.exists():
        log.warning("Offensive parquet missing: %s — run precompute_season_offensive()", path.name)
        return None

    try:
        df = pd.read_parquet(path)
    except Exception as exc:
        log.error("Failed to read %s: %s", path.name, exc)
        return None

    cache_set(cache_key, df)
    return df


def _filter_team(df: pd.DataFrame, team_name: str) -> pd.DataFrame:
    """Filter a season-level DataFrame to a single canonical team."""
    if df is None or df.empty:
        return pd.DataFrame()
    target = canonical_name(team_name).lower()
    mask = df["team"].apply(lambda t: canonical_name(str(t)).lower() == target)
    return df[mask].reset_index(drop=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 1 — GK BUILD-UP
# ═══════════════════════════════════════════════════════════════════════════════

def compute_season_gk_buildup(season: str, team_name: str) -> dict:
    """
    Return season-aggregate GK build-up data for one team.

    Reads from ``gk_events_{season}.parquet`` (precomputed).

    Returns
    -------
    dict with keys:
        metrics  dict — season-level KPIs
        events   list[dict] — per-event records for pitch scatter
        matches  int — number of matches represented
    """
    df_full = _load_offensive_parquet("gk_events", season)
    summary = _load_offensive_parquet("offensive_summary", season)

    df = _filter_team(df_full, team_name)

    if df.empty:
        return _empty_gk_result()

    total      = len(df)
    short_count = int((df["pass_type"] == "short").sum())
    long_count  = total - short_count
    pos_count   = int((df["outcome"] == "positive").sum())
    safe_total  = max(total, 1)

    short_df   = df[df["pass_type"] == "short"]
    long_df    = df[df["pass_type"] == "long"]
    short_pos  = int((short_df["outcome"] == "positive").sum())
    long_pos   = int((long_df["outcome"] == "positive").sum())

    # matches_played from summary parquet if available
    mp = 0
    if summary is not None and not summary.empty:
        row = _filter_team(summary, team_name)
        if not row.empty:
            mp = int(row.iloc[0].get("matches_played", 0))
    if mp == 0:
        mp = int(df["gw"].nunique()) or 1

    metrics = {
        "total":              total,
        "short_count":        short_count,
        "long_count":         long_count,
        "short_pct":          round(short_count / safe_total * 100, 1),
        "long_pct":           round(long_count  / safe_total * 100, 1),
        "positive_pct":       round(pos_count   / safe_total * 100, 1),
        "short_success_rate": round(short_pos / max(len(short_df), 1) * 100, 1),
        "long_success_rate":  round(long_pos  / max(len(long_df),  1) * 100, 1),
        "avg_per_match":      round(total / mp, 1),
        "granular_counts":    {
            k: int((df["granular"] == k).sum())
            for k in ("P1", "P2", "P3", "N1", "N2", "N3")
        },
        "short_granular_counts": {
            k: int((short_df["granular"] == k).sum())
            for k in ("P1", "P2", "P3", "N1", "N2", "N3")
        },
        "long_granular_counts": {
            k: int((long_df["granular"] == k).sum())
            for k in ("P1", "P2", "P3", "N1", "N2", "N3")
        },
    }

    events = df.to_dict(orient="records")
    return {"metrics": metrics, "events": events, "matches": mp}


def _empty_gk_result() -> dict:
    _zero_gc = {"P1": 0, "P2": 0, "P3": 0, "N1": 0, "N2": 0, "N3": 0}
    return {
        "metrics": {
            "total": 0, "short_count": 0, "long_count": 0,
            "short_pct": 0.0, "long_pct": 0.0, "positive_pct": 0.0,
            "short_success_rate": 0.0, "long_success_rate": 0.0,
            "avg_per_match": 0.0,
            "granular_counts":       dict(_zero_gc),
            "short_granular_counts": dict(_zero_gc),
            "long_granular_counts":  dict(_zero_gc),
        },
        "events": [], "matches": 0,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 2 — FINAL THIRD ENTRIES
# ═══════════════════════════════════════════════════════════════════════════════

def compute_season_ft_entries(season: str, team_name: str) -> dict:
    """
    Return season-aggregate FT-entry data for one team.

    Reads from ``ft_entries_{season}.parquet`` (precomputed).

    Returns
    -------
    dict with keys:
        metrics  dict — season-level KPIs
        entries  list[dict] — per-entry records for pitch scatter
        matches  int — number of matches represented
    """
    df_full = _load_offensive_parquet("ft_entries", season)
    summary = _load_offensive_parquet("offensive_summary", season)

    df = _filter_team(df_full, team_name)

    if df.empty:
        return _empty_ft_result()

    total    = len(df)
    pos      = int((df["outcome"] == "positive").sum())
    safe_n   = max(total, 1)

    corr_counts = df["corridor"].value_counts().to_dict()
    method_counts = df["method"].value_counts().to_dict()
    top_method = df["method"].mode()[0] if not df.empty else "short_pass"

    mp = 0
    if summary is not None and not summary.empty:
        row = _filter_team(summary, team_name)
        if not row.empty:
            mp = int(row.iloc[0].get("matches_played", 0))
    if mp == 0:
        mp = int(df["gw"].nunique()) or 1

    # Method frequency % (for dropdown) — all methods sorted descending by count
    _all_method_keys = (
        "transition_recovery", "through_ball", "switch_of_play", "set_piece",
        "long_ball", "cross_delivery", "individual_carry", "short_pass",
    )
    method_counts_full = {k: int(method_counts.get(k, 0)) for k in _all_method_keys}
    method_pcts = {
        k: round(method_counts_full[k] / safe_n * 100, 1) for k in _all_method_keys
    }
    # Top method excluding short_pass
    excl_short = {k: v for k, v in method_counts_full.items() if k != "short_pass" and v > 0}
    sorted_excl = sorted(excl_short.items(), key=lambda x: x[1], reverse=True)
    top_method_excl_short = sorted_excl[1][0] if len(sorted_excl) >= 2 else (sorted_excl[0][0] if sorted_excl else "individual_carry")

    # Per-match averaged KPIs from offensive_summary (new fields added by precompute)
    possession_pct    = 0.0
    box_touches_avg   = 0.0
    passes_per_minute = 0.0
    if summary is not None and not summary.empty:
        row = _filter_team(summary, team_name)
        if not row.empty:
            possession_pct    = float(row.iloc[0].get("ft_possession_pct", 0.0))
            box_touches_avg   = float(row.iloc[0].get("ft_box_touches_per_match", 0.0))
            passes_per_minute = float(row.iloc[0].get("ft_passes_per_minute", 0.0))

    metrics = {
        "total_ft_entries":    total,
        "entries_per_match":   round(total / mp, 1),
        "top_method":          top_method,
        "top_method_excl_short": top_method_excl_short,
        "success_rate":        round(pos / safe_n * 100, 1),
        "positive_count":      pos,
        "negative_count":      total - pos,
        "corridor_counts":     {k: int(corr_counts.get(k, 0)) for k in ("L", "C", "R")},
        "corridor_pcts":       {
            k: round(corr_counts.get(k, 0) / safe_n * 100, 1)
            for k in ("L", "C", "R")
        },
        "method_counts":       method_counts_full,
        "method_pcts":         method_pcts,
        "possession_pct":      possession_pct,
        "box_touches_per_match": box_touches_avg,
        "passes_per_minute":   passes_per_minute,
    }

    entries = df.to_dict(orient="records")
    return {"metrics": metrics, "entries": entries, "matches": mp}


def _empty_ft_result() -> dict:
    _mk = ("transition_recovery", "through_ball", "switch_of_play", "set_piece",
           "long_ball", "cross_delivery", "individual_carry", "short_pass")
    return {
        "metrics": {
            "total_ft_entries": 0, "entries_per_match": 0.0,
            "top_method": "short_pass", "top_method_excl_short": "individual_carry",
            "success_rate": 0.0,
            "positive_count": 0, "negative_count": 0,
            "corridor_counts": {"L": 0, "C": 0, "R": 0},
            "corridor_pcts":   {"L": 0.0, "C": 0.0, "R": 0.0},
            "method_counts":   {k: 0 for k in _mk},
            "method_pcts":     {k: 0.0 for k in _mk},
            "possession_pct":  0.0,
            "box_touches_per_match": 0.0,
            "passes_per_minute": 0.0,
        },
        "entries": [], "matches": 0,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 3 — CHANCE CREATION
# ═══════════════════════════════════════════════════════════════════════════════

def compute_season_chance_creation(season: str, team_name: str) -> dict:
    """
    Return season-aggregate chance-creation data for one team.

    Reads from ``shots_{season}.parquet`` (precomputed).

    Returns
    -------
    dict with keys:
        metrics  dict — season-level KPIs
        shots    list[dict] — per-shot records for pitch scatter
        matches  int — number of matches represented
    """
    df_full = _load_offensive_parquet("shots", season)
    summary = _load_offensive_parquet("offensive_summary", season)

    df = _filter_team(df_full, team_name)

    if df.empty:
        return _empty_cc_result()

    total    = len(df)
    goals    = int(df["is_goal"].sum())
    on_tgt   = int(df["on_target"].sum())
    xg_total = float(df["xG"].sum())
    top_origin = df["origin"].mode()[0] if not df.empty else "Combination"
    origin_counts = df["origin"].value_counts().to_dict()

    # Goals and conversion rate per origin (derived from shot-level data)
    from src.analytics.chance_creation import ORIGIN_LABELS as _ORIGIN_LABELS
    origin_goals: dict[str, int] = {o: 0 for o in _ORIGIN_LABELS}
    for _, s in df.iterrows():
        o = s.get("origin", "Combination")
        if o in origin_goals and s.get("is_goal"):
            origin_goals[o] += 1

    origin_data: dict[str, dict] = {}
    for o in _ORIGIN_LABELS:
        cnt  = int(origin_counts.get(o, 0))
        g    = origin_goals.get(o, 0)
        origin_data[o] = {
            "total":          cnt,
            "per_match":      0.0,   # filled below after mp is known
            "goals_total":    g,
            "conversion_pct": round(g / cnt * 100, 1) if cnt > 0 else None,
        }

    mp = 0
    if summary is not None and not summary.empty:
        row = _filter_team(summary, team_name)
        if not row.empty:
            mp = int(row.iloc[0].get("matches_played", 0))
    if mp == 0:
        mp = int(df["gw"].nunique()) or 1

    safe_mp = max(mp, 1)
    for o in _ORIGIN_LABELS:
        origin_data[o]["per_match"] = round(origin_data[o]["total"] / safe_mp, 1)

    metrics = {
        "total_shots":      total,
        "shots_per_match":  round(total / safe_mp, 1),
        "goals":            goals,
        "on_target":        on_tgt,
        "sot_pct":          round(on_tgt / max(total, 1) * 100, 1),
        "xg_total":         round(xg_total, 2),
        "xg_per_match":     round(xg_total / safe_mp, 2),
        "top_origin":       top_origin,
        "origin_counts":    {k: int(v) for k, v in origin_counts.items()},
        "origin_data":      origin_data,
    }

    shots = df.to_dict(orient="records")
    return {"metrics": metrics, "shots": shots, "matches": mp}


def _empty_cc_result() -> dict:
    from src.analytics.chance_creation import ORIGIN_LABELS as _ORIGIN_LABELS
    return {
        "metrics": {
            "total_shots": 0, "shots_per_match": 0.0, "goals": 0,
            "on_target": 0, "sot_pct": 0.0,
            "xg_total": 0.0, "xg_per_match": 0.0,
            "top_origin": "Combination", "origin_counts": {},
            "origin_data": {
                o: {"total": 0, "per_match": 0.0, "goals_total": 0, "conversion_pct": None}
                for o in _ORIGIN_LABELS
            },
        },
        "shots": [], "matches": 0,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 4 — LEAGUE BENCHMARKS (from precomputed offensive_summary parquet)
# ═══════════════════════════════════════════════════════════════════════════════

def compute_league_offensive_benchmarks(season: str) -> dict[str, Any]:
    """
    Return season-level offensive benchmarks for ALL teams from the
    precomputed ``offensive_summary_{season}.parquet``.

    Falls back to the xg/ppda parquets when the offensive summary is not
    yet available (e.g. first run before precompute).

    Returns a dict keyed by canonical team name:
        {
            "xg_per_match":          float
            "shots_per_match":       float
            "ft_per_match":          float
            "gk_short_success_rate": float
        }
    """
    cache_key = f"opp_offensive_benchmarks_{season}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    summary = _load_offensive_parquet("offensive_summary", season)

    benchmarks: dict[str, Any] = {}

    if summary is not None and not summary.empty:
        for _, row in summary.iterrows():
            team = canonical_name(str(row.get("team", "")))
            benchmarks[team] = {
                "xg_per_match":              float(row.get("xg_per_match", 0.0)),
                "shots_per_match":           float(row.get("shots_per_match", 0.0)),
                "ft_per_match":              float(row.get("ft_per_match", 0.0)),
                "gk_short_success_rate":     float(row.get("gk_short_success_rate", 0.0)),
                "gk_long_success_rate":      float(row.get("gk_long_success_rate", 0.0)),
                "ft_box_touches_per_match":  float(row.get("ft_box_touches_per_match", 0.0)),
            }
    else:
        # Fallback: use fast xg/ppda parquets (no FT/GK benchmark available)
        log.warning("offensive_summary_%s.parquet missing — using xG fallback", season)
        from src.analytics.data_loader import load_xg_summary, load_ppda_summary
        from src.team_mapping import canonical_name as _canon

        xg_df   = load_xg_summary(season)
        ppda_df = load_ppda_summary(season)
        matches_map: dict[str, int] = {}
        if ppda_df is not None and not ppda_df.empty and "matches" in ppda_df.columns:
            for _, row in ppda_df.iterrows():
                t = _canon(str(row.get("team", "") or row.get("team_short", "")))
                matches_map[t.lower()] = max(int(row.get("matches", 1)), 1)

        if xg_df is not None and not xg_df.empty:
            for _, row in xg_df.iterrows():
                team = _canon(str(row.get("Team", "")))
                xg_total = float(row.get("xG", 0.0))
                shots    = int(row.get("Shots", 0))
                mp       = matches_map.get(team.lower(), 38)
                benchmarks[team] = {
                    "xg_per_match":          round(xg_total / mp, 2),
                    "shots_per_match":       round(shots / mp, 1),
                    "ft_per_match":          0.0,
                    "gk_short_success_rate": 0.0,
                    "gk_long_success_rate":  0.0,
                }

    cache_set(cache_key, benchmarks)
    return benchmarks
