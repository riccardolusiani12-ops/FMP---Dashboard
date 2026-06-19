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
from src.analytics.formations import extract_team_formations, formation_display, _parse_qualifiers
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
    _save_parquet(matches, READY_DATA_DIR / f"matches_{season}.parquet", "Matches (ready)")
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

    # ── 9. Formation lineups (per-slot player stats) ─────────────────
    precompute_formation_lineups(season)

    # ── 10. Offensive Phase (GK / FT / Chance Creation event tables) ──
    precompute_season_offensive(season)

    # ── 11. Defensive Pressing season aggregate ────────────────────────
    precompute_season_pressing(season)

    # ── 12. Defensive Castle season aggregate ──────────────────────────
    precompute_season_castle(season)

    # ── 13. Chances Conceded season aggregate ──────────────────────────
    precompute_season_chances_conceded(season)

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

def precompute_season_offensive(season: str) -> None:
    """
    Precompute season-level offensive phase tables for ALL teams in a season.

    Iterates every match CSV, runs the three offensive analytics modules
    (GK build-up, final-third entries, chance creation) and saves four
    Parquet files to data/ready/:

        gk_events_{season}.parquet        — one row per GK possession event
        ft_entries_{season}.parquet       — one row per FT entry event
        shots_{season}.parquet            — one row per shot / chance event
        offensive_summary_{season}.parquet — one row per team with all KPI
                                            aggregates (totals, rates, per-match)

    These replace the expensive CSV-scanning in the callbacks: the callbacks
    read and filter the ready Parquets instead.

    Bottleneck profile (2025/2026, Juventus):
        GK buildup  ~0.5s/match × 38 = ~19s
        FT entries  ~1.0s/match × 38 = ~40s  ← possession chain is the cost
        Chance crtn ~0.2s/match × 38 = ~8s
    Running once at precompute time eliminates this cost at callback time.
    """
    from src.analytics.goalkeeper_buildup import analyse_goalkeeper_buildup
    from src.analytics.final_third import analyse_final_third
    from src.analytics.chance_creation import analyse_chance_creation, get_pv_model
    from src.utils.paths import list_match_files, parse_match_filename

    season_label = season.replace("_", "/")
    print(f"\n  — Offensive Phase precompute: {season_label}")
    t0 = time.time()

    # Load PV model once; pass it into every chance_creation call
    pv_model = get_pv_model()

    files = list_match_files(season)
    if not files:
        print(f"  ⚠ No match files found for {season_label}")
        return

    gk_rows:   list[dict] = []
    ft_rows:   list[dict] = []
    shot_rows: list[dict] = []
    # Per-match KPIs collected for averaging into the summary
    # {team: {"possession_pct": [float,...], "box_touches": [int,...], "passes_per_minute": [float,...]}}
    ft_match_kpis: dict[str, dict] = {}

    for f in files:
        info = parse_match_filename(f)
        home = canonical_name(info["home"])
        away = canonical_name(info["away"])
        gw   = info.get("week", "?")

        for team in (home, away):
            # ── GK build-up ──────────────────────────────────────────────
            try:
                gk = analyse_goalkeeper_buildup(f, team)
                for ev in gk.get("events", []):
                    gk_rows.append({
                        "season":    season_label,
                        "team":      team,
                        "gw":        gw,
                        "home":      home,
                        "away":      away,
                        "minute":    ev.get("minute", 0),
                        "pass_type": ev.get("pass_type", "short"),
                        "outcome":   ev.get("outcome", "negative"),
                        "granular":  ev.get("granular_outcome", "N1"),
                        "recv_zone": ev.get("recv_zone", 0),
                        "recv_x":    ev.get("recv_x"),
                        "recv_y":    ev.get("recv_y"),
                        "gk_x":      ev.get("gk_x"),
                        "gk_y":      ev.get("gk_y"),
                    })
            except Exception as exc:
                print(f"    ⚠ GK {team} {f.name}: {exc}")

            # ── Final third entries ───────────────────────────────────────
            try:
                ft = analyse_final_third(f, team)
                for ev in ft.get("entries", []):
                    ft_rows.append({
                        "season":      season_label,
                        "team":        team,
                        "gw":          gw,
                        "home":        home,
                        "away":        away,
                        "method":      ev.get("method", "short_pass"),
                        "outcome":     ev.get("outcome", "negative"),
                        "corridor":    ev.get("corridor", "C"),
                        "entry_x":     ev.get("entry_x"),
                        "entry_y":     ev.get("entry_y"),
                        "minute":      ev.get("minute", 0),
                        "player":      ev.get("player", ""),
                        "elapsed_sec": ev.get("elapsed_sec", 0.0),
                        "passes_before": ev.get("passes_before_count", 0),
                    })
                # Collect per-match KPIs for averaging
                m = ft.get("metrics", {})
                if team not in ft_match_kpis:
                    ft_match_kpis[team] = {"possession_pct": [], "box_touches": [], "passes_per_minute": []}
                pct = m.get("possession_pct", 0.0)
                bt  = m.get("box_touches", 0)
                ppm = m.get("passes_per_minute", 0.0)
                ft_match_kpis[team]["possession_pct"].append(float(pct))
                ft_match_kpis[team]["box_touches"].append(int(bt))
                ft_match_kpis[team]["passes_per_minute"].append(float(ppm))
            except Exception as exc:
                print(f"    ⚠ FT {team} {f.name}: {exc}")

            # ── Chance creation ───────────────────────────────────────────
            try:
                cc = analyse_chance_creation(f, team, pv_model=pv_model)
                for sh in cc.get("shots_detail", []):
                    shot_rows.append({
                        "season":        season_label,
                        "team":          team,
                        "gw":            gw,
                        "home":          home,
                        "away":          away,
                        "origin":        sh.get("origin", "Combination"),
                        "x":             sh.get("x", 0.0),
                        "y":             sh.get("y", 50.0),
                        "xG":            sh.get("xG", 0.0),
                        "on_target":     bool(sh.get("on_target", False)),
                        "is_goal":       bool(sh.get("is_goal", False)),
                        "in_box":        bool(sh.get("in_box", False)),
                        "quality_tier":  int(sh.get("quality_tier", 0)),
                        "minute":        sh.get("minute", 0),
                        "player":        sh.get("player", ""),
                    })
            except Exception as exc:
                print(f"    ⚠ CC {team} {f.name}: {exc}")

    # ── Save event-level parquets ─────────────────────────────────────────────
    if gk_rows:
        _save_parquet(
            pd.DataFrame(gk_rows),
            READY_DATA_DIR / f"gk_events_{season}.parquet",
            "GK build-up events",
        )
    if ft_rows:
        _save_parquet(
            pd.DataFrame(ft_rows),
            READY_DATA_DIR / f"ft_entries_{season}.parquet",
            "FT entry events",
        )
    if shot_rows:
        _save_parquet(
            pd.DataFrame(shot_rows),
            READY_DATA_DIR / f"shots_{season}.parquet",
            "Shot / chance events",
        )

    # ── Build per-team summary (offensive_summary_{season}.parquet) ──────────
    all_teams = sorted({r["team"] for r in gk_rows + ft_rows + shot_rows})
    # Number of matches each team played (home or away appearances)
    match_counts: dict[str, int] = {}
    for f in files:
        info = parse_match_filename(f)
        for team in (canonical_name(info["home"]), canonical_name(info["away"])):
            match_counts[team] = match_counts.get(team, 0) + 1

    summary_rows: list[dict] = []
    for team in all_teams:
        mp = max(match_counts.get(team, 1), 1)

        # GK
        tgk = [r for r in gk_rows if r["team"] == team]
        gk_total   = len(tgk)
        gk_short   = sum(1 for r in tgk if r["pass_type"] == "short")
        gk_long    = gk_total - gk_short
        gk_pos     = sum(1 for r in tgk if r["outcome"] == "positive")
        short_evts = [r for r in tgk if r["pass_type"] == "short"]
        long_evts  = [r for r in tgk if r["pass_type"] == "long"]
        gk_short_pos = sum(1 for r in short_evts if r["outcome"] == "positive")
        gk_long_pos  = sum(1 for r in long_evts  if r["outcome"] == "positive")

        # FT
        tft = [r for r in ft_rows if r["team"] == team]
        ft_total = len(tft)
        ft_pos   = sum(1 for r in tft if r["outcome"] == "positive")
        from collections import Counter
        ft_methods   = Counter(r["method"]   for r in tft)
        ft_corridors = Counter(r["corridor"] for r in tft)
        top_ft_method = ft_methods.most_common(1)[0][0] if ft_methods else "short_pass"

        # Shots
        tsh = [r for r in shot_rows if r["team"] == team]
        sh_total  = len(tsh)
        sh_goals  = sum(1 for r in tsh if r["is_goal"])
        sh_target = sum(1 for r in tsh if r["on_target"])
        xg_total  = sum(r["xG"] for r in tsh)
        sh_origins = Counter(r["origin"] for r in tsh)
        top_origin = sh_origins.most_common(1)[0][0] if sh_origins else "Combination"

        safe_gk = max(gk_total, 1)
        safe_ft = max(ft_total, 1)
        safe_sh = max(sh_total, 1)

        # Per-match FT KPI averages
        kpis = ft_match_kpis.get(team, {})
        pct_vals = kpis.get("possession_pct", [])
        bt_vals  = kpis.get("box_touches", [])
        ppm_vals = kpis.get("passes_per_minute", [])
        avg_possession_pct    = round(sum(pct_vals) / len(pct_vals), 1) if pct_vals else 0.0
        avg_box_touches       = round(sum(bt_vals)  / len(bt_vals),  1) if bt_vals  else 0.0
        avg_passes_per_minute = round(sum(ppm_vals) / len(ppm_vals), 2) if ppm_vals else 0.0

        summary_rows.append({
            "season":                season_label,
            "team":                  team,
            "matches_played":        mp,
            # GK
            "gk_total":              gk_total,
            "gk_short_count":        gk_short,
            "gk_long_count":         gk_long,
            "gk_short_pct":          round(gk_short / safe_gk * 100, 1),
            "gk_long_pct":           round(gk_long  / safe_gk * 100, 1),
            "gk_positive_pct":       round(gk_pos   / safe_gk * 100, 1),
            "gk_short_success_rate": round(gk_short_pos / max(len(short_evts), 1) * 100, 1),
            "gk_long_success_rate":  round(gk_long_pos  / max(len(long_evts),  1) * 100, 1),
            "gk_avg_per_match":      round(gk_total / mp, 1),
            # FT
            "ft_total":              ft_total,
            "ft_per_match":          round(ft_total / mp, 1),
            "ft_success_rate":       round(ft_pos / safe_ft * 100, 1),
            "ft_top_method":         top_ft_method,
            "ft_left_pct":           round(ft_corridors.get("L", 0) / safe_ft * 100, 1),
            "ft_centre_pct":         round(ft_corridors.get("C", 0) / safe_ft * 100, 1),
            "ft_right_pct":          round(ft_corridors.get("R", 0) / safe_ft * 100, 1),
            "ft_possession_pct":     avg_possession_pct,
            "ft_box_touches_per_match": avg_box_touches,
            "ft_passes_per_minute":  avg_passes_per_minute,
            # Shots / xG
            "shots_total":           sh_total,
            "shots_per_match":       round(sh_total / mp, 1),
            "goals":                 sh_goals,
            "on_target":             sh_target,
            "sot_pct":               round(sh_target / safe_sh * 100, 1),
            "xg_total":              round(xg_total, 2),
            "xg_per_match":          round(xg_total / mp, 2),
            "top_origin":            top_origin,
        })

    if summary_rows:
        _save_parquet(
            pd.DataFrame(summary_rows),
            READY_DATA_DIR / f"offensive_summary_{season}.parquet",
            "Offensive phase summary",
        )

    print(f"  ✓ Offensive Phase precompute done in {time.time()-t0:.1f}s")


def precompute_formation_lineups(season: str) -> None:
    """
    Single-pass over all match CSVs for a season: emit per-player stats for
    every (team, formation) starting combination and save as a Parquet table.

    Output: data/ready/formation_lineups_{season}.parquet
    Columns: team, formation_str, slot, player_id, name, jersey,
             pos_code, pos_label, starts, total_mins, avg_mins_per_start
    """
    from collections import defaultdict

    _POS_LABEL = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}

    events_dir = RAW_DATA_DIR / f"serie_a_{season}" / "events"
    if not events_dir.exists():
        print(f"  ⚠ No events dir for {season} — skipping formation lineups")
        return

    USECOLS = [
        "type_id", "team_name", "player_id", "player_name",
        "formation", "time_min", "period_id", "represented_qualifiers",
    ]
    csv_files = sorted(events_dir.glob("*.csv"))
    t0 = time.time()
    print(f"  — Formation lineups precompute: {season.replace('_','/')} ({len(csv_files)} files)")

    # (canonical_team, formation_str) → {player_id → stats dict}
    all_agg: dict[tuple[str, str], dict] = defaultdict(
        lambda: defaultdict(lambda: {
            "name": "?", "jersey": "?", "pos_code": 0, "slot": 0,
            "starts": 0, "total_mins": 0,
        })
    )

    for fp in csv_files:
        try:
            df = pd.read_csv(fp, low_memory=False, usecols=USECOLS)
        except Exception:
            continue

        player_map = (
            df[["player_id", "player_name"]].dropna()
            .drop_duplicates().set_index("player_id")["player_name"].to_dict()
        )
        p2_end = df[(df["type_id"] == 30) & (df["period_id"] == 2)]["time_min"].max()
        total_match_mins = int(p2_end) if pd.notna(p2_end) else 90

        for _, setup_row in df[df["type_id"] == 34].iterrows():
            team_opta = setup_row["team_name"]
            form_code = setup_row.get("formation", None)
            if pd.isna(form_code):
                continue

            team_can = canonical_name(str(team_opta))
            form_str = "-".join(list(str(int(form_code))))
            key = (team_can, form_str)

            quals = _parse_qualifiers(str(setup_row["represented_qualifiers"]))
            involved = quals.get("Involved", [])
            jerseys = quals.get("Jersey Number", [])
            pos_codes = quals.get("Player Position", [])
            slots = quals.get("Team Player Formation", [])

            subs_off = df[(df["type_id"] == 18) & (df["team_name"] == team_opta)]

            for pid, jn, pos, slot_str in zip(involved, jerseys, pos_codes, slots):
                try:
                    slot = int(slot_str)
                except (ValueError, TypeError):
                    continue
                if slot == 0:
                    continue

                sub_off_row = subs_off[subs_off["player_id"] == pid]
                minute_out = (
                    int(sub_off_row.iloc[0]["time_min"])
                    if not sub_off_row.empty
                    else total_match_mins
                )

                entry = all_agg[key][pid]
                entry["name"] = player_map.get(pid, entry["name"])
                entry["jersey"] = jn
                try:
                    entry["pos_code"] = int(pos)
                except (ValueError, TypeError):
                    pass
                entry["slot"] = slot
                entry["starts"] += 1
                entry["total_mins"] += minute_out

    if not all_agg:
        print(f"  ⚠ No formation lineup data found for {season}")
        return

    rows = []
    for (team, form_str), player_dict in all_agg.items():
        for pid, d in player_dict.items():
            rows.append({
                "team": team,
                "formation_str": form_str,
                "slot": d["slot"],
                "player_id": pid,
                "name": d["name"],
                "jersey": d["jersey"],
                "pos_code": d["pos_code"],
                "pos_label": _POS_LABEL.get(d["pos_code"], ""),
                "starts": d["starts"],
                "total_mins": d["total_mins"],
                "avg_mins_per_start": round(d["total_mins"] / d["starts"], 1) if d["starts"] else 0.0,
            })

    out = pd.DataFrame(rows).sort_values(
        ["team", "formation_str", "slot", "starts"],
        ascending=[True, True, True, False],
    ).reset_index(drop=True)

    _save_parquet(
        out,
        READY_DATA_DIR / f"formation_lineups_{season}.parquet",
        f"Formation Lineups ({season.replace('_','/')})",
    )
    print(f"  ✓ Formation lineups done in {time.time()-t0:.1f}s")


def precompute_season_pressing(season: str) -> None:
    """
    Precompute season-level defensive pressing tables for ALL teams in a season.

    Iterates every match CSV, calls analyse_defensive_pressing() for each
    (team, match) and saves two Parquet files to data/ready/:

        pressing_actions_{season}.parquet  — one row per defensive action
            cols: season, team, gw, home, away, x, y, action, zone_group,
                  corridor, success, minute, player

        pressing_summary_{season}.parquet  — one row per team with KPI aggregates
            cols: season, team, matches_played,
                  total_def_actions, actions_per_match,
                  ppda_num_overall, ppda_den_overall, ppda_overall,
                  ppda_num_high, ppda_den_high, ppda_high,
                  ppda_num_mid, ppda_den_mid, ppda_mid,
                  pressing_line_median,
                  high_press_count, high_press_pct,
                  mid_press_count,  mid_press_pct,
                  low_block_count,  low_block_pct,
                  pressing_left_pct, pressing_centre_pct, pressing_right_pct,
                  press_success_rate,
                  press_success_by_zone_high_{total,success,rate},
                  press_success_by_zone_mid_{total,success,rate},
                  press_success_by_zone_low_{total,success,rate},
                  zone_heatmap_1 … zone_heatmap_18
    """
    from src.analytics.defensive_pressing import analyse_defensive_pressing
    from src.analytics.goalkeeper_buildup import xy_to_zone as _xy_to_zone
    from src.utils.paths import list_match_files, parse_match_filename

    season_label = season.replace("_", "/")
    print(f"\n  — Defensive Pressing precompute: {season_label}")
    t0 = time.time()

    files = list_match_files(season)
    if not files:
        print(f"  ⚠ No match files found for {season_label}")
        return

    # Accumulate per-match results keyed by team
    # {team: [per_match_result_dict, ...]}
    per_match: dict[str, list[dict]] = {}
    action_rows: list[dict] = []

    for f in files:
        info = parse_match_filename(f)
        home = canonical_name(info["home"])
        away = canonical_name(info["away"])
        gw   = info.get("week", "?")

        for team in (home, away):
            try:
                res = analyse_defensive_pressing(f, team)
            except Exception as exc:
                print(f"    ⚠ Pressing {team} {f.name}: {exc}")
                continue

            if team not in per_match:
                per_match[team] = []
            per_match[team].append(res)

            # Flatten press_actions_detail into one row per action
            for act in res.get("press_actions_detail", []):
                action_rows.append({
                    "season":     season_label,
                    "team":       team,
                    "gw":         gw,
                    "home":       home,
                    "away":       away,
                    "x":          act.get("x"),
                    "y":          act.get("y"),
                    "action":     act.get("action", ""),
                    "zone_group": act.get("zone_group", ""),
                    "corridor":   act.get("corridor", ""),
                    "success":    bool(act.get("success", False)),
                    "minute":     int(act.get("minute", 0)),
                    "player":     str(act.get("player", "")),
                })

    # ── Save action-level parquet ────────────────────────────────────────────────
    if action_rows:
        _save_parquet(
            pd.DataFrame(action_rows),
            READY_DATA_DIR / f"pressing_actions_{season}.parquet",
            "Defensive pressing actions",
        )

    # ── Build per-team summary ───────────────────────────────────────────────────
    # Match counts: each file is one match for both teams
    match_counts: dict[str, int] = {}
    for f in files:
        info = parse_match_filename(f)
        for team in (canonical_name(info["home"]), canonical_name(info["away"])):
            match_counts[team] = match_counts.get(team, 0) + 1

    summary_rows: list[dict] = []
    for team, results in per_match.items():
        mp = max(match_counts.get(team, 1), 1)

        total_actions = sum(r["total_def_actions"] for r in results)

        # PPDA: aggregate numerators and denominators then compute ratio once
        ppda_num_o = sum(r["ppda_num_overall"] for r in results)
        ppda_den_o = sum(r["ppda_den_overall"] for r in results)
        ppda_num_h = sum(r["ppda_num_high"]    for r in results)
        ppda_den_h = sum(r["ppda_den_high"]    for r in results)
        ppda_num_m = sum(r["ppda_num_mid"]     for r in results)
        ppda_den_m = sum(r["ppda_den_mid"]     for r in results)

        def _ppda(num: int, den: int) -> float | None:
            return round(num / den, 2) if den > 0 else None

        ppda_overall = _ppda(ppda_num_o, ppda_den_o)
        ppda_high    = _ppda(ppda_num_h, ppda_den_h)
        ppda_mid     = _ppda(ppda_num_m, ppda_den_m)

        # Pressing height — average the medians; aggregate zone counts
        line_medians = [r["pressing_line_median"] for r in results if r["pressing_line_median"] is not None]
        median_pressing_line = round(float(np.median(line_medians)), 1) if line_medians else None

        high_count = sum(r["high_press_count"] for r in results)
        mid_count  = sum(r["mid_press_count"]  for r in results)
        low_count  = sum(r["low_block_count"]  for r in results)
        total_height = max(high_count + mid_count + low_count, 1)

        # Direction — aggregate raw counts
        left_count   = sum(r["pressing_left_count"]   for r in results)
        centre_count = sum(r["pressing_centre_count"] for r in results)
        right_count  = sum(r["pressing_right_count"]  for r in results)
        total_dir    = max(left_count + centre_count + right_count, 1)

        # Press success — aggregate total / successful counts by zone
        ps_total     = sum(r["press_success_total"]      for r in results)
        ps_success   = sum(r["press_success_successful"] for r in results)
        ps_rate      = round(ps_success / max(ps_total, 1) * 100, 1)

        def _zone_agg(zone_key: str) -> tuple[int, int, float]:
            tot = sum(r["press_success_by_zone"][zone_key]["total"]   for r in results)
            suc = sum(r["press_success_by_zone"][zone_key]["success"] for r in results)
            rate = round(suc / max(tot, 1) * 100, 1)
            return tot, suc, rate

        zh_tot, zh_suc, zh_rate = _zone_agg("high")
        zm_tot, zm_suc, zm_rate = _zone_agg("mid")
        zl_tot, zl_suc, zl_rate = _zone_agg("low")

        # Per-zone (Z1–Z18) press success counts derived from action-level detail
        zone18_total:   dict[int, int] = {z: 0 for z in range(1, 19)}
        zone18_success: dict[int, int] = {z: 0 for z in range(1, 19)}
        for r in results:
            for act in r.get("press_actions_detail", []):
                ax = act.get("x")
                ay = act.get("y")
                if ax is None or ay is None:
                    continue
                try:
                    z = _xy_to_zone(float(ax), float(ay))
                except (TypeError, ValueError):
                    continue
                zone18_total[z]   += 1
                if act.get("success", False):
                    zone18_success[z] += 1

        # 18-zone heatmap — sum across all matches
        heatmap: dict[int, int] = {z: 0 for z in range(1, 19)}
        for r in results:
            for z, cnt in r.get("zone_heatmap", {}).items():
                heatmap[int(z)] = heatmap.get(int(z), 0) + cnt

        row: dict = {
            "season":               season_label,
            "team":                 team,
            "matches_played":       mp,
            "total_def_actions":    total_actions,
            "actions_per_match":    round(total_actions / mp, 1),
            # PPDA raw counts + ratios
            "ppda_num_overall":     ppda_num_o,
            "ppda_den_overall":     ppda_den_o,
            "ppda_overall":         ppda_overall,
            "ppda_num_high":        ppda_num_h,
            "ppda_den_high":        ppda_den_h,
            "ppda_high":            ppda_high,
            "ppda_num_mid":         ppda_num_m,
            "ppda_den_mid":         ppda_den_m,
            "ppda_mid":             ppda_mid,
            # Pressing height
            "pressing_line_median": median_pressing_line,
            "high_press_count":     high_count,
            "high_press_pct":       round(high_count  / total_height * 100, 1),
            "mid_press_count":      mid_count,
            "mid_press_pct":        round(mid_count   / total_height * 100, 1),
            "low_block_count":      low_count,
            "low_block_pct":        round(low_count   / total_height * 100, 1),
            # Pressing direction
            "pressing_left_count":   left_count,
            "pressing_left_pct":     round(left_count   / total_dir * 100, 1),
            "pressing_centre_count": centre_count,
            "pressing_centre_pct":   round(centre_count / total_dir * 100, 1),
            "pressing_right_count":  right_count,
            "pressing_right_pct":    round(right_count  / total_dir * 100, 1),
            # Press success overall
            "press_success_total":       ps_total,
            "press_success_successful":  ps_success,
            "press_success_rate":        ps_rate,
            # Press success by zone
            "press_success_high_total":  zh_tot,
            "press_success_high_success": zh_suc,
            "press_success_high_rate":   zh_rate,
            "press_success_mid_total":   zm_tot,
            "press_success_mid_success": zm_suc,
            "press_success_mid_rate":    zm_rate,
            "press_success_low_total":   zl_tot,
            "press_success_low_success": zl_suc,
            "press_success_low_rate":    zl_rate,
        }
        # Flatten 18-zone heatmap into columns
        for z in range(1, 19):
            row[f"zone_heatmap_{z}"] = heatmap.get(z, 0)

        # Flatten per-zone (Z1–Z18) press outcome counts into columns
        for z in range(1, 19):
            row[f"press_zone_{z}_total"]   = zone18_total.get(z, 0)
            row[f"press_zone_{z}_success"] = zone18_success.get(z, 0)

        summary_rows.append(row)

    if summary_rows:
        _save_parquet(
            pd.DataFrame(summary_rows),
            READY_DATA_DIR / f"pressing_summary_{season}.parquet",
            "Defensive pressing summary",
        )

    print(f"  ✓ Defensive Pressing precompute done in {time.time()-t0:.1f}s")


def precompute_season_castle(season: str) -> None:
    """
    Precompute season-level Defensive Castle (D3) tables for ALL teams in a season.

    Iterates every match CSV, calls analyse_defensive_castle() for each
    (team, match) and saves one Parquet file to data/ready/:

        castle_summary_{season}.parquet  — one row per team with KPI aggregates
            cols: season, team, matches_played,
                  total_actions, actions_per_match,
                  in_own_box_total, in_own_box_per_match,
                  wide_flanks_total, wide_flanks_per_match,
                  def_third_edge_total, def_third_edge_per_match,
                  actions_by_type_json,
                  corridor_L_n, corridor_C_n, corridor_R_n,
                  corridor_L_pct, corridor_C_pct, corridor_R_pct
    """
    import json
    from src.analytics.defensive_castle import analyse_defensive_castle
    from src.utils.paths import list_match_files, parse_match_filename

    season_label = season.replace("_", "/")
    print(f"\n  — Defensive Castle precompute: {season_label}")
    t0 = time.time()

    files = list_match_files(season)
    if not files:
        print(f"  ⚠ No match files found for {season_label}")
        return

    # {team: [per_match_result_dict, ...]}
    per_match: dict[str, list[dict]] = {}

    for f in files:
        info = parse_match_filename(f)
        home = canonical_name(info["home"])
        away = canonical_name(info["away"])

        for team in (home, away):
            try:
                res = analyse_defensive_castle(f, team)
            except Exception as exc:
                print(f"    ⚠ Castle {team} {f.name}: {exc}")
                continue
            if team not in per_match:
                per_match[team] = []
            per_match[team].append(res)

    # Match counts
    match_counts: dict[str, int] = {}
    for f in files:
        info = parse_match_filename(f)
        for team in (canonical_name(info["home"]), canonical_name(info["away"])):
            match_counts[team] = match_counts.get(team, 0) + 1

    summary_rows: list[dict] = []
    for team, results in per_match.items():
        mp = max(match_counts.get(team, 1), 1)

        total_actions = sum(r["total_actions"] for r in results)

        # Sub-zone counts from by_subzone
        in_own_box_total    = sum(r.get("by_subzone", {}).get("box", 0)            for r in results)
        wide_flanks_total   = sum(r.get("by_subzone", {}).get("deep_flank", 0)     for r in results)
        def_third_edge_total= sum(r.get("by_subzone", {}).get("def_third_edge", 0) for r in results)

        # Actions by type — accumulate cross-match totals
        by_type_agg: dict[str, int] = {}
        for r in results:
            for action, count in r.get("by_type", {}).items():
                by_type_agg[action] = by_type_agg.get(action, 0) + count
        # Sort descending by count
        by_type_sorted = sorted(by_type_agg.items(), key=lambda kv: -kv[1])

        # Corridors — accumulate raw counts; compute pct from cross-match totals
        corr_counts = {"L": 0, "C": 0, "R": 0}
        for r in results:
            for k in ("L", "C", "R"):
                corr_counts[k] += r.get("by_corridor", {}).get(k, 0)
        corr_total = max(sum(corr_counts.values()), 1)
        corr_pcts = {k: round(v / corr_total * 100, 1) for k, v in corr_counts.items()}

        # Zone counts — accumulate zone_counts (zones 1-6, defensive third) across matches
        zone_counts_agg: dict[int, int] = {}
        for r in results:
            for z, cnt in r.get("zone_counts", {}).items():
                zone_counts_agg[z] = zone_counts_agg.get(z, 0) + cnt

        summary_rows.append({
            "season":               season_label,
            "team":                 team,
            "matches_played":       mp,
            "total_actions":        total_actions,
            "actions_per_match":    round(total_actions / mp, 1),
            "in_own_box_total":     in_own_box_total,
            "in_own_box_per_match": round(in_own_box_total / mp, 1),
            "wide_flanks_total":    wide_flanks_total,
            "wide_flanks_per_match":round(wide_flanks_total / mp, 1),
            "def_third_edge_total": def_third_edge_total,
            "def_third_edge_per_match": round(def_third_edge_total / mp, 1),
            # JSON-serialised ranked action type list: [[action, count], ...]
            "actions_by_type_json": json.dumps(by_type_sorted),
            # Corridor absolute counts
            "corridor_L_n":   corr_counts["L"],
            "corridor_C_n":   corr_counts["C"],
            "corridor_R_n":   corr_counts["R"],
            # Corridor percentages (computed from cross-match totals)
            "corridor_L_pct": corr_pcts["L"],
            "corridor_C_pct": corr_pcts["C"],
            "corridor_R_pct": corr_pcts["R"],
            # Zone action counts JSON: {"1": n, "2": n, ...} (zones 1-6, defensive third)
            "zone_action_counts_json": json.dumps(
                {str(k): v for k, v in zone_counts_agg.items()}
            ),
        })

    if summary_rows:
        _save_parquet(
            pd.DataFrame(summary_rows),
            READY_DATA_DIR / f"castle_summary_{season}.parquet",
            "Defensive Castle summary",
        )

    print(f"  ✓ Defensive Castle precompute done in {time.time()-t0:.1f}s")


def precompute_season_chances_conceded(season: str) -> None:
    """
    Precompute season-level Chances Conceded (D4) tables for ALL teams in a season.

    Iterates every match CSV, calls analyse_chance_conceded() for each
    (team, match) and saves one Parquet file to data/ready/:

        chances_conceded_summary_{season}.parquet  — one row per team

    Schema (all per-match values are means; totals are sums):
      season, team, num_matches,
      -- Shots overview --
      total_shots, shots_per_match,
      on_target_total, on_target_per_match,
      goals_conceded_total, goals_conceded_per_match,
      big_chances_total, big_chances_per_match,
      xg_conceded_total, xg_conceded_per_match,
      -- Attack origin counts (per discovered origin key) --
      {origin_slug}_total, {origin_slug}_per_match, {origin_slug}_pct
      -- Shot coordinate array (JSON list of {x,y,outcome}) --
      shots_json,
      -- Zone shot counts (JSON dict {zone_id: count}) --
      zone_shot_counts_json,
      -- Shot quality tiers --
      tier_level_3_converted_total, tier_level_3_converted_per_match, tier_level_3_converted_pct,
      tier_level_2_threat_total, ..., tier_level_0_low_total, ...
    """
    import json as _json
    from src.analytics.chance_conceded import analyse_chance_conceded
    from src.analytics.chance_creation import ORIGIN_LABELS, get_pv_model
    from src.analytics.goalkeeper_buildup import xy_to_zone as _xy_to_zone
    from src.utils.paths import list_match_files, parse_match_filename

    season_label = season.replace("_", "/")
    print(f"\n  — Chances Conceded precompute: {season_label}")
    t0 = time.time()

    out_path = READY_DATA_DIR / f"chances_conceded_summary_{season}.parquet"

    files = list_match_files(season)
    if not files:
        print(f"  ⚠ No match files found for {season_label}")
        return

    pv_model = get_pv_model()

    # {team: [per_match_result_dict, ...]}
    per_match: dict[str, list[dict]] = {}

    for f in files:
        info = parse_match_filename(f)
        home = canonical_name(info["home"])
        away = canonical_name(info["away"])

        for team in (home, away):
            try:
                res = analyse_chance_conceded(f, team, pv_model=pv_model)
            except Exception as exc:
                print(f"    ⚠ CC-conceded {team} {f.name}: {exc}")
                continue
            if team not in per_match:
                per_match[team] = []
            per_match[team].append(res)

    match_counts: dict[str, int] = {}
    for f in files:
        info = parse_match_filename(f)
        for team in (canonical_name(info["home"]), canonical_name(info["away"])):
            match_counts[team] = match_counts.get(team, 0) + 1

    # Tier keys as discovered from the analytics output
    _TIER_KEYS = ["level_3_converted", "level_2_threat", "level_0_low"]

    summary_rows: list[dict] = []
    for team, results in per_match.items():
        mp = max(match_counts.get(team, 1), 1)

        # Flatten all shots across all matches
        all_shots: list[dict] = []
        for r in results:
            all_shots.extend(r.get("shots_detail", []))

        total_shots = len(all_shots)
        on_target_total      = sum(1 for s in all_shots if s.get("on_target") or s.get("is_goal"))
        goals_conceded_total = sum(1 for s in all_shots if s.get("is_goal"))
        big_chances_total    = sum(1 for s in all_shots if s.get("quality_tier") == 2)
        xg_conceded_total    = round(sum(s.get("xG", 0.0) for s in all_shots), 2)

        # Attack origin breakdown — use ORIGIN_LABELS to ensure all origins present
        origin_counts: dict[str, int] = {o: 0 for o in ORIGIN_LABELS}
        origin_goals:  dict[str, int] = {o: 0 for o in ORIGIN_LABELS}
        for s in all_shots:
            origin = s.get("origin", "Combination")
            if origin in origin_counts:
                origin_counts[origin] += 1
                if s.get("is_goal"):
                    origin_goals[origin] += 1

        safe_total = max(total_shots, 1)

        # Shot coordinate array — normalise outcome to 4 labels
        shot_coords: list[dict] = []
        for s in all_shots:
            if s.get("is_goal"):
                outcome = "goal"
            elif s.get("on_target"):
                outcome = "on_target"
            elif s.get("in_box") is not None:
                # Use quality_tier=0 as blocked proxy; otherwise miss
                # Blocked not explicitly flagged in analytics; default to miss
                outcome = "miss"
            else:
                outcome = "miss"
            shot_coords.append({
                "x": s.get("x", 50.0),
                "y": s.get("y", 50.0),
                "outcome": outcome,
            })

        # Zone shot counts for density overlay
        zone_shot_counts: dict[int, int] = {}
        for sc in shot_coords:
            try:
                z = _xy_to_zone(float(sc["x"]), float(sc["y"]))
                zone_shot_counts[z] = zone_shot_counts.get(z, 0) + 1
            except (TypeError, ValueError):
                pass

        # Shot quality tiers — accumulate cross-match totals
        tier_totals: dict[str, int] = {tk: 0 for tk in _TIER_KEYS}
        for r in results:
            for tk in _TIER_KEYS:
                tier_totals[tk] += r.get("shot_quality_tiers", {}).get(tk, {}).get("count", 0)

        row: dict = {
            "season":                     season_label,
            "team":                       team,
            "num_matches":                mp,
            # Shots overview
            "total_shots":                total_shots,
            "shots_per_match":            round(total_shots / mp, 1),
            "on_target_total":            on_target_total,
            "on_target_per_match":        round(on_target_total / mp, 1),
            "goals_conceded_total":       goals_conceded_total,
            "goals_conceded_per_match":   round(goals_conceded_total / mp, 2),
            "big_chances_total":          big_chances_total,
            "big_chances_per_match":      round(big_chances_total / mp, 1),
            "xg_conceded_total":          xg_conceded_total,
            "xg_conceded_per_match":      round(xg_conceded_total / mp, 2),
            # Shot coordinate array + zone density (JSON-serialised)
            "shots_json":                 _json.dumps(shot_coords),
            "zone_shot_counts_json":      _json.dumps({str(k): v for k, v in zone_shot_counts.items()}),
        }

        # Attack origin columns (flat, one quintuple per origin)
        for origin in ORIGIN_LABELS:
            slug  = origin.lower().replace(" ", "_")
            cnt   = origin_counts.get(origin, 0)
            goals = origin_goals.get(origin, 0)
            row[f"{slug}_total"]          = cnt
            row[f"{slug}_per_match"]      = round(cnt / mp, 1)
            row[f"{slug}_pct"]            = round(cnt / safe_total * 100, 1)
            row[f"{slug}_goals_total"]    = goals
            row[f"{slug}_conversion_pct"] = round(goals / cnt * 100, 1) if cnt > 0 else None

        # Shot quality tier columns
        for tk in _TIER_KEYS:
            cnt = tier_totals[tk]
            row[f"tier_{tk}_total"]    = cnt
            row[f"tier_{tk}_per_match"] = round(cnt / mp, 1)
            row[f"tier_{tk}_pct"]       = round(cnt / safe_total * 100, 1)

        summary_rows.append(row)

    if summary_rows:
        _save_parquet(
            pd.DataFrame(summary_rows),
            out_path,
            "Chances Conceded summary",
        )

    print(f"  ✓ Chances Conceded precompute done in {time.time()-t0:.1f}s")


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
