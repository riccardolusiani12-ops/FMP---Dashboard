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
