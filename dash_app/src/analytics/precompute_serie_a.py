"""
Serie A Data Preprocessing Pipeline
=====================================
Reads raw CSV match-event files and generates fast intermediate tables
in Parquet format under data/processed/ and data/ready/.

Reuses existing analytics modules:
  - multi_season_standings  → matches, standings, points progression
  - ppda                    → PPDA + regain metrics

Output structure:
  data/processed/
      matches_{season}.parquet        — match results per season
  data/ready/
      standings_{season}.parquet      — league table per season
      points_progression_{season}.parquet — cumulative points per team
      team_overview_{season}.parquet  — team KPI summary per season
      ppda_{season}.parquet           — PPDA + regain metrics per season
      season_teams_{season}.parquet   — team list per season
      league_summary.parquet          — all-season standings combined

Usage:
    python -m src.analytics.precompute_serie_a           # all seasons
    python -m src.analytics.precompute_serie_a 2025_2026 # single season
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# Ensure src is importable when run as __main__
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.config import (
    RAW_DATA_DIR,
    PROCESSED_DATA_DIR,
    READY_DATA_DIR,
    AVAILABLE_SEASONS,
)
from src.analytics.multi_season_standings import (
    load_season_matches,
    compute_standings,
    compute_points_progression,
)
from src.analytics.ppda import (
    build_ppda_table,
)
from src.analytics.formations import extract_team_formations, formation_display
from src.analytics.xg import compute_team_xg_summary
from src.team_mapping import canonical_name


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _save_parquet(df: pd.DataFrame, path: Path, label: str) -> None:
    """Save a DataFrame to Parquet, creating parent dirs if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False, engine="pyarrow")
    print(f"  ✓ {label}: {len(df)} rows → {path.name}")


# ═══════════════════════════════════════════════════════════════════════════════
# PER-SEASON PREPROCESSING
# ═══════════════════════════════════════════════════════════════════════════════

def precompute_season(season: str) -> dict[str, pd.DataFrame]:
    """
    Run the full preprocessing pipeline for a single season.
    Returns a dict of DataFrames for inspection/testing.
    """
    season_label = season.replace("_", "/")
    print(f"\n{'='*60}")
    print(f"Processing season: {season_label}")
    print(f"{'='*60}")

    results: dict[str, pd.DataFrame] = {}

    # ── 1. Match results ─────────────────────────────────────
    t0 = time.time()
    matches = load_season_matches(season)
    print(f"  Loaded {len(matches)} matches in {time.time()-t0:.1f}s")

    if matches.empty:
        print(f"  ⚠ No matches found for {season_label} — skipping")
        return results

    _save_parquet(matches, PROCESSED_DATA_DIR / f"matches_{season}.parquet", "Matches")
    results["matches"] = matches

    # ── 2. Standings ─────────────────────────────────────────
    standings = compute_standings(matches)
    if not standings.empty:
        # Add rank column
        standings = standings.reset_index(drop=True)
        standings["Rank"] = standings.groupby("Season").cumcount() + 1
        _save_parquet(standings, READY_DATA_DIR / f"standings_{season}.parquet", "Standings")
        results["standings"] = standings

    # ── 3. Points progression ────────────────────────────────
    progression = compute_points_progression(matches)
    if not progression.empty:
        _save_parquet(progression, READY_DATA_DIR / f"points_progression_{season}.parquet", "Points Progression")
        results["points_progression"] = progression

    # ── 4. Season teams list ─────────────────────────────────
    if not standings.empty:
        teams_df = pd.DataFrame({
            "Team": standings["Team"].unique(),
            "Season": season_label,
        }).sort_values("Team").reset_index(drop=True)
        _save_parquet(teams_df, READY_DATA_DIR / f"season_teams_{season}.parquet", "Season Teams")
        results["season_teams"] = teams_df

    # ── 5. Team overview KPIs ────────────────────────────────
    if not standings.empty and not progression.empty:
        overview = _build_team_overview(standings, progression, season_label)
        if not overview.empty:
            _save_parquet(overview, READY_DATA_DIR / f"team_overview_{season}.parquet", "Team Overview")
            results["team_overview"] = overview

    # ── 6. PPDA (with field tilt) ────────────────────────────
    t0 = time.time()
    ppda_df = build_ppda_table(season)
    elapsed = time.time() - t0
    print(f"  Built PPDA table in {elapsed:.1f}s")

    if not ppda_df.empty:
        ppda_df["Season"] = season_label
        _save_parquet(ppda_df, READY_DATA_DIR / f"ppda_{season}.parquet", "PPDA + Field Tilt")
        results["ppda"] = ppda_df

    # ── 7. Formations ────────────────────────────────────────
    t0 = time.time()
    teams_list = sorted(standings["Team"].unique()) if not standings.empty else []
    if teams_list:
        all_formations = []
        for team in teams_list:
            formations_df = extract_team_formations(season, team)
            if formations_df.empty:
                continue
            # Compute counts per formation for this team
            counts = (
                formations_df
                .groupby("formation_str")
                .size()
                .reset_index(name="count")
                .sort_values("count", ascending=False)
                .reset_index(drop=True)
            )
            total = counts["count"].sum()
            counts["pct"] = (counts["count"] / total * 100).round(1) if total > 0 else 0.0
            counts["team"] = team
            counts["season"] = season_label
            all_formations.append(counts)

        if all_formations:
            formations_combined = pd.concat(all_formations, ignore_index=True)
            _save_parquet(
                formations_combined,
                READY_DATA_DIR / f"formations_{season}.parquet",
                "Formations",
            )
            results["formations"] = formations_combined

        print(f"  Formations computed in {time.time()-t0:.1f}s")

    # ── 8. xG Summary ───────────────────────────────────────
    t0 = time.time()
    xg_summary = compute_team_xg_summary(season)
    if not xg_summary.empty:
        _save_parquet(xg_summary, READY_DATA_DIR / f"xg_{season}.parquet", "xG Summary")
        results["xg"] = xg_summary
    print(f"  xG computed in {time.time()-t0:.1f}s")

    return results


def _build_team_overview(
    standings: pd.DataFrame,
    progression: pd.DataFrame,
    season_label: str,
) -> pd.DataFrame:
    """
    Build a per-team overview table with KPIs for the season.
    Columns: Team, Season, Rank, MP, W, D, L, GF, GA, GD, Points,
             WinRate, Last5, AvgPointsPerMatch
    """
    season_std = standings[standings["Season"] == season_label].copy()
    if season_std.empty:
        return pd.DataFrame()

    # Last 5 form per team
    season_prog = progression[progression["Season"] == season_label].copy()
    last5_map: dict[str, str] = {}
    if not season_prog.empty:
        for team in season_prog["Team"].unique():
            tdf = season_prog[season_prog["Team"] == team].sort_values("Matchday")
            results = tdf["Result"].tolist()
            last5_map[team] = ",".join(results[-5:])

    season_std["WinRate"] = (season_std["W"] / season_std["MP"].clip(lower=1) * 100).round(1)
    season_std["Last5"] = season_std["Team"].map(last5_map).fillna("")
    season_std["AvgPointsPerMatch"] = (season_std["Points"] / season_std["MP"].clip(lower=1)).round(2)

    return season_std[
        ["Team", "Season", "Rank", "MP", "W", "D", "L", "GF", "GA", "GD",
         "Points", "WinRate", "Last5", "AvgPointsPerMatch"]
    ].reset_index(drop=True)


# ═══════════════════════════════════════════════════════════════════════════════
# CROSS-SEASON AGGREGATION
# ═══════════════════════════════════════════════════════════════════════════════

def build_league_summary() -> pd.DataFrame:
    """
    Combine all per-season standings into a single league summary table.
    Also builds a combined points progression table for multi-season charts.
    """
    standings_frames = []
    progression_frames = []

    for season in AVAILABLE_SEASONS:
        std_path = READY_DATA_DIR / f"standings_{season}.parquet"
        prog_path = READY_DATA_DIR / f"points_progression_{season}.parquet"

        if std_path.exists():
            standings_frames.append(pd.read_parquet(std_path))
        if prog_path.exists():
            progression_frames.append(pd.read_parquet(prog_path))

    if standings_frames:
        league_summary = pd.concat(standings_frames, ignore_index=True)
        _save_parquet(league_summary, READY_DATA_DIR / "league_summary.parquet", "League Summary (all seasons)")
    else:
        league_summary = pd.DataFrame()

    if progression_frames:
        all_progression = pd.concat(progression_frames, ignore_index=True)
        _save_parquet(all_progression, READY_DATA_DIR / "points_progression_all.parquet", "Points Progression (all seasons)")

    return league_summary


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def precompute_all(seasons: list[str] | None = None) -> None:
    """
    Run the full preprocessing pipeline for all (or specified) seasons.
    """
    target_seasons = seasons or AVAILABLE_SEASONS

    if not target_seasons:
        print("No seasons found. Check data/raw/ for serie_a_* folders.")
        return

    print(f"\n{'#'*60}")
    print(f"  Serie A Data Preprocessing Pipeline")
    print(f"  Seasons: {', '.join(s.replace('_', '/') for s in target_seasons)}")
    print(f"{'#'*60}")

    total_t0 = time.time()

    for season in target_seasons:
        precompute_season(season)

    # Cross-season aggregation
    print(f"\n{'='*60}")
    print("Building cross-season aggregations...")
    print(f"{'='*60}")
    build_league_summary()

    elapsed = time.time() - total_t0
    print(f"\n{'#'*60}")
    print(f"  ✅ Pipeline complete in {elapsed:.1f}s")
    print(f"  Processed tables: {PROCESSED_DATA_DIR}")
    print(f"  Ready tables:     {READY_DATA_DIR}")
    print(f"{'#'*60}\n")


if __name__ == "__main__":
    # Accept optional season arguments
    args = sys.argv[1:]
    if args:
        precompute_all(seasons=args)
    else:
        precompute_all()
