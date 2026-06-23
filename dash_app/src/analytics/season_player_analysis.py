"""
Season-Aggregate Player Analysis — Precompute
=============================================
Aggregates the MATCH-LEVEL Player Analysis (analytics/player_analysis.py) across
every match a team played in a season, for every player who featured, producing a
single parquet per season keyed by (season, team, player).

ISOLATION (Phase 1 step 1): this module is fully self-contained.  It is *called
from* precompute_serie_a.precompute_season() as an additive hook, but its internals
touch no other season artifact and can be run/disabled/debugged independently via
``precompute_season_players(season)``.

REUSE (Phase 1 step 2): per-match values come straight from
``analyse_player_analysis(match_csv)`` — the exact same cached bundle the Match
Analysis UI consumes.  No KPI or PV logic is reimplemented here; this module only
AGGREGATES.  Because we read the bundle unmodified (never re-scoping it), the
Match Analysis output is provably unchanged (no refactor of player_analysis.py).

AGGREGATION RULES (Phase 0E — confirmed):
  • Counting KPIs (passes_completed, tackles_won, …) sum directly across matches.
  • Percentage KPIs (pass_completion_pct, line_break_pct) are recomputed as
    sum(numerator) / sum(denominator) — NEVER a mean of per-match percentages.
    To make this exact we sum the underlying *_attempted / *_completed counters
    and divide once at the end.
  • PVA (off/def/total) sums directly across matches; per-90 is applied to the
    season TOTAL, not per match then averaged.
  • Every counting KPI is stored as BOTH a raw season total AND a per-90 value
    (per90 = season_sum / season_minutes * 90).
  • Minutes sum across matches where the player featured (minutes > 0).
    Appearances = count of such matches.  Starts = matches where started is True.

CONTEXT (STOP AND ASK answers):
  • Minutes dim cutoff 450' (kept, never dropped) — flag stored, UI dims.
  • Per-90 is the primary number for every counting KPI; raw total kept for hover.
  • Granular role (collapsed from the raw per-event ``position`` column to ~8
    groups) is the season role, assigned minutes-weighted-most-frequent over the
    matches the player STARTED.  Players with no role in any match → "UNCL".
  • Per-match PVA series stored (JSON) so the UI can compute PVA consistency (σ).
  • Partial-season flag: featured in < 50% of the team's matchdays.
  • All teams written to one parquet so the UI can compute league within-role
    percentiles for the position-adjusted score.

Output: data/ready/player_season_{season}.parquet
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from typing import Any, Dict

import numpy as np
import pandas as pd

from src.config import READY_DATA_DIR
from src.team_mapping import canonical_name
from src.utils.logging import log

# ── Role collapse: raw Opta per-event position codes → 8 role groups ──────────
# Raw vocabulary seen league-wide:
#   GK, CB, LB, RB, LWB, RWB, CDM, MC, CM, LM, RM, CAM, SS, LW, RW, CF
ROLE_GROUP_MAP: Dict[str, str] = {
    "GK": "GK",
    "CB": "CB",
    "LB": "FB", "RB": "FB", "LWB": "FB", "RWB": "FB",
    "CDM": "DM",
    "MC": "CM", "CM": "CM",
    "LM": "WM", "RM": "WM",
    "CAM": "AM", "SS": "AM",
    "LW": "W", "RW": "W",
    "CF": "CF",
}
ROLE_GROUP_ORDER = ["GK", "CB", "FB", "DM", "CM", "WM", "AM", "W", "CF", "UNCL"]
UNCLASSIFIED = "UNCL"

MIN_MINUTES_DIM = 450.0          # STOP-AND-ASK Q1: dim below ~5 full matches
PARTIAL_SEASON_THRESHOLD = 0.50  # featured in < 50% of matchdays → partial flag

# Counting KPIs that carry BOTH a raw season total and a per-90 value.
# (player_analysis column name → output base name)
IN_COUNT_KPIS = [
    "passes_attempted", "passes_completed",
    "switches_of_play", "crosses_attempted", "crosses_completed",
    "line_breaks_attempted", "line_breaks_completed",
    "ball_progressions", "take_ons", "attempts_at_goal", "goals",
]
OUT_COUNT_KPIS = [
    "tackles_made", "tackles_won", "blocks", "interceptions",
    "clearances", "aerial_duels_won", "aerial_duels_total",
    "possession_regains",
]
# Percentage KPIs: (output col, numerator col, denominator col)
PCT_KPIS = [
    ("pass_completion_pct", "passes_completed", "passes_attempted"),
    ("line_break_pct", "line_breaks_completed", "line_breaks_attempted"),
]
COUNT_KPIS = IN_COUNT_KPIS + OUT_COUNT_KPIS
PVA_COLS = ["off_pva", "def_pva", "total_pva"]

# Every per-90 metric subject to minutes-weighted shrinkage (Phase 1).
# (base column name → its raw per-90 column).  Counting KPIs + PVA per-90.
PER90_METRICS = [f"{c}_p90" for c in COUNT_KPIS] + [f"{c}_p90" for c in PVA_COLS]

# ── Empirical-Bayes shrinkage (credibility weighting) ─────────────────────────
#   adjusted_per90 = w * observed_per90 + (1 - w) * role_avg_per90,
#   w = minutes / (minutes + K)
# K (in minutes) is estimated PER per-90 metric from split-half reliability and
# falls back to a variance-based heuristic when the split-half sample is too thin.
MIN_MATCHES_FOR_SPLITHALF = 8     # a player needs ≥8 matches to split odd/even
MIN_PLAYERS_FOR_SPLITHALF = 8     # a role needs ≥8 such players for a stable r
K_FLOOR = 200.0                   # ~2 full matches — never trust below this
K_CEIL = 3000.0                   # cap pathological heuristics (~33 matches)
HEURISTIC_K_SCALE = 600.0         # base minutes for the CV²-scaled heuristic K


def _match_started_roles(bundle_df: pd.DataFrame, started: set[str]) -> Dict[str, str]:
    """
    For each player who STARTED this match, the granular role group they played,
    derived from the raw per-event ``position`` column (most-frequent code over
    that player's events, mapped to a role group).  Players with no usable
    position code are omitted (caller treats them as unclassified for this match).
    """
    out: Dict[str, str] = {}
    if bundle_df is None or bundle_df.empty or "position" not in bundle_df.columns:
        return out
    sub = bundle_df[bundle_df["player_name"].notna() & bundle_df["position"].notna()]
    for name, grp in sub.groupby("player_name"):
        if str(name) not in started:
            continue
        codes = grp["position"].astype(str).str.upper()
        top = codes.value_counts()
        if top.empty:
            continue
        raw = top.index[0]
        out[str(name)] = ROLE_GROUP_MAP.get(raw, UNCLASSIFIED)
    return out


def _filter_team(df: pd.DataFrame, team_canon: str) -> pd.DataFrame:
    if df is None or df.empty or "team_name" not in df.columns:
        return pd.DataFrame()
    mask = df["team_name"].map(lambda t: canonical_name(str(t)) == team_canon)
    return df[mask]


def aggregate_team_season(
    season_label: str,
    team_canon: str,
    match_bundles: list[tuple[str, Dict[str, Any]]],
) -> list[dict]:
    """
    Aggregate one team's season from a list of (matchday, per-match bundle) pairs.

    Returns one row dict per player who featured for the team.  Pure function —
    no I/O — so it is unit-testable and re-runnable in isolation.
    """
    n_matchdays = len(match_bundles)

    # Per-player accumulators
    minutes = defaultdict(float)
    appearances = defaultdict(int)
    starts = defaultdict(int)
    counts: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    pva_sum: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    pva_series: Dict[str, list[float]] = defaultdict(list)   # per-match total_pva (for σ)
    # Per-match (minute, count) tuples per player per KPI — fuels the empirical
    # split-half K estimation (per-90 in each half = sum(count)/sum(min)*90).
    # Stored as JSON in the parquet so K can be (re)derived without re-precompute.
    match_series: Dict[str, Dict[str, list[tuple[int, float, float]]]] = defaultdict(
        lambda: defaultdict(list)
    )  # name -> kpi -> [(matchday_int, minutes, count), ...]
    # role votes: player → {role_group: minutes_started_in_that_role}
    role_votes: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    matchdays_seen: Dict[str, set] = defaultdict(set)
    player_team: Dict[str, str] = {}

    for md, bundle in match_bundles:
        mins_map = bundle.get("minutes", {})
        bundle_df = bundle.get("df")
        # Team's own players who featured this match (minutes > 0).
        team_players = {
            name: info for name, info in mins_map.items()
            if canonical_name(str(info.get("team", ""))) == team_canon
            and float(info.get("minutes", 0) or 0) > 0
        }
        if not team_players:
            continue

        started_set = {n for n, info in team_players.items() if info.get("started")}
        roles_this_match = _match_started_roles(bundle_df, started_set)

        # KPI / PVA frames scoped to the team's own players.
        in_df = _filter_team(bundle.get("in_possession"), team_canon).set_index("player_name") \
            if not _filter_team(bundle.get("in_possession"), team_canon).empty else pd.DataFrame()
        out_df = _filter_team(bundle.get("out_possession"), team_canon).set_index("player_name") \
            if not _filter_team(bundle.get("out_possession"), team_canon).empty else pd.DataFrame()
        pva_df = _filter_team(bundle.get("pva"), team_canon).set_index("player_name") \
            if not _filter_team(bundle.get("pva"), team_canon).empty else pd.DataFrame()

        for name, info in team_players.items():
            m = float(info.get("minutes", 0) or 0)
            minutes[name] += m
            appearances[name] += 1
            matchdays_seen[name].add(md)
            player_team.setdefault(name, team_canon)
            if info.get("started"):
                starts[name] += 1
                role = roles_this_match.get(name)
                if role:
                    role_votes[name][role] += m

            try:
                md_int = int(md)
            except (TypeError, ValueError):
                md_int = len(matchdays_seen[name])

            for col in IN_COUNT_KPIS:
                if not in_df.empty and name in in_df.index and col in in_df.columns:
                    c = float(in_df.at[name, col] or 0)
                    counts[name][col] += c
                    match_series[name][col].append((md_int, m, c))
            for col in OUT_COUNT_KPIS:
                if not out_df.empty and name in out_df.index and col in out_df.columns:
                    c = float(out_df.at[name, col] or 0)
                    counts[name][col] += c
                    match_series[name][col].append((md_int, m, c))

            if not pva_df.empty and name in pva_df.index:
                for pc in PVA_COLS:
                    v = float(pva_df.at[name, pc] or 0)
                    pva_sum[name][pc] += v
                    match_series[name][pc].append((md_int, m, v))
                pva_series[name].append(round(float(pva_df.at[name, "total_pva"] or 0), 4))
            else:
                pva_series[name].append(0.0)

    rows: list[dict] = []
    for name in minutes:
        mins = round(minutes[name], 1)
        apps = appearances[name]
        nstarts = starts[name]

        # Season role: minutes-weighted most-frequent STARTED role; else UNCL.
        votes = role_votes.get(name, {})
        if votes:
            role = max(votes.items(), key=lambda kv: kv[1])[0]
        else:
            role = UNCLASSIFIED

        per90_factor = (90.0 / mins) if mins > 0 else 0.0

        row: dict = {
            "season": season_label,
            "team": team_canon,
            "player": name,
            "minutes": mins,
            "appearances": apps,
            "starts": nstarts,
            "matchdays_played": len(matchdays_seen[name]),
            "n_matchdays": n_matchdays,
            "minutes_share": round(mins / (n_matchdays * 90.0) * 100, 1) if n_matchdays else 0.0,
            "role_group": role,
            "low_minutes": mins < MIN_MINUTES_DIM,
            "partial_season": (len(matchdays_seen[name]) / n_matchdays < PARTIAL_SEASON_THRESHOLD)
                              if n_matchdays else False,
        }

        # Counting KPIs: raw total + per-90.
        for col in COUNT_KPIS:
            total = round(counts[name].get(col, 0.0), 2)
            row[col] = total
            row[f"{col}_p90"] = round(total * per90_factor, 3)

        # Percentage KPIs: sum(num)/sum(den) — exact, never mean-of-%.
        for out_col, num_col, den_col in PCT_KPIS:
            num = counts[name].get(num_col, 0.0)
            den = counts[name].get(den_col, 0.0)
            row[out_col] = round(num / den * 100, 1) if den > 0 else 0.0

        # PVA: season sum + per-90 (per-90 on the season total).
        for pc in PVA_COLS:
            tot = round(pva_sum[name].get(pc, 0.0), 4)
            row[pc] = tot
            row[f"{pc}_p90"] = round(tot * per90_factor, 4)

        # PVA consistency: std-dev of per-match total_pva (form steadiness).
        series = pva_series.get(name, [])
        row["pva_per_match_json"] = json.dumps([round(v, 3) for v in series])
        row["pva_consistency"] = round(float(np.std(series)), 4) if len(series) > 1 else 0.0

        # Per-match (matchday, minutes, count) series per per-90 metric — drives
        # the empirical split-half K estimation downstream.  Compact JSON.
        ms = {
            kpi: [(md_i, round(mn, 1), round(c, 4)) for md_i, mn, c in lst]
            for kpi, lst in match_series.get(name, {}).items()
        }
        row["match_series_json"] = json.dumps(ms)

        rows.append(row)

    return rows


# ═══════════════════════════════════════════════════════════════════════════════
# EMPIRICAL-BAYES SHRINKAGE  (Phase 1 — minutes-weighted credibility)
# ═══════════════════════════════════════════════════════════════════════════════

def _split_half_reliability(df: pd.DataFrame, metric: str) -> tuple[float | None, int, float]:
    """
    Split-half reliability for one per-90 *metric* within a single role group.

    For every player with ≥ MIN_MATCHES_FOR_SPLITHALF matches, split their matches
    by odd/even matchday, compute per-90 in each half (sum(count)/sum(min)*90), and
    Pearson-correlate the two halves across players.  The raw split-half r measures
    HALF-season reliability; we adjust to a FULL-season-equivalent r via the
    Spearman-Brown prophecy formula (two halves → whole), which is the value that
    maps cleanly onto K.

    Returns (r_full, n_players_used, mean_player_minutes).  r_full is None when the
    sample is too thin to be trustworthy.
    """
    base = metric[:-4] if metric.endswith("_p90") else metric  # strip "_p90"
    h1, h2, mins_used = [], [], []
    for _, row in df.iterrows():
        try:
            ms = json.loads(row.get("match_series_json") or "{}")
        except (ValueError, TypeError):
            continue
        seq = ms.get(base) or ms.get(metric)
        if not seq or len(seq) < MIN_MATCHES_FOR_SPLITHALF:
            continue
        odd_c = odd_m = even_c = even_m = 0.0
        for md_i, mn, c in seq:
            if int(md_i) % 2:
                odd_c += c; odd_m += mn
            else:
                even_c += c; even_m += mn
        if odd_m <= 0 or even_m <= 0:
            continue
        h1.append(odd_c / odd_m * 90.0)
        h2.append(even_c / even_m * 90.0)
        mins_used.append(float(row.get("minutes", 0) or 0))

    n = len(h1)
    if n < MIN_PLAYERS_FOR_SPLITHALF:
        return None, n, float(np.mean(mins_used)) if mins_used else 0.0
    a, b = np.array(h1), np.array(h2)
    if a.std() == 0 or b.std() == 0:
        return None, n, float(np.mean(mins_used))
    r_half = float(np.corrcoef(a, b)[0, 1])
    if not np.isfinite(r_half) or r_half <= 0:
        return None, n, float(np.mean(mins_used))
    # Spearman-Brown: full-test reliability from two equal halves.
    r_full = (2 * r_half) / (1 + r_half)
    r_full = min(max(r_full, 1e-3), 0.999)
    return r_full, n, float(np.mean(mins_used))


def _heuristic_k(df: pd.DataFrame, metric: str) -> float:
    """
    Variance-based fallback K for one per-90 *metric* within a role group.

    K scales with the squared coefficient of variation (CV² = (σ/μ)²) of the raw
    per-90 across qualifying players: noisier / rarer KPIs (high CV²) get a larger
    K (shrink harder), frequent stable KPIs (low CV²) get a smaller K.  This avoids
    a single flat K across KPIs that do not stabilise at the same sample size.
    """
    vals = df[df["minutes"] >= MIN_MINUTES_DIM][metric].astype(float)
    vals = vals[vals > 0]
    if len(vals) < 3 or vals.mean() <= 0:
        return HEURISTIC_K_SCALE
    cv2 = (vals.std() / vals.mean()) ** 2
    k = HEURISTIC_K_SCALE * (0.5 + cv2)
    return float(min(max(k, K_FLOOR), K_CEIL))


def estimate_k_per_metric(df: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
    """
    Estimate a shrinkage constant K (minutes) for every per-90 metric, role group
    by role group, from the all-teams season frame.

    Method per (role, metric): split-half reliability r_full → K = mean_minutes *
    (1 - r_full) / r_full  (the minutes at which the observed rate is trusted half-
    way — classic credibility half-life).  When the split-half sample is too thin
    (< MIN_PLAYERS_FOR_SPLITHALF players with ≥ MIN_MATCHES_FOR_SPLITHALF matches),
    fall back to the CV²-based heuristic for that (role, metric).

    Returns {metric: {role: {"K": float, "method": str, "r": float|None,
                             "n": int, "role_avg": float}}}.
    """
    classified = df[df["role_group"] != UNCLASSIFIED]
    out: Dict[str, Dict[str, Any]] = {}
    for metric in PER90_METRICS:
        out[metric] = {}
        for role, g in classified.groupby("role_group"):
            qual = g[g["minutes"] >= MIN_MINUTES_DIM]
            role_avg = float(qual[metric].astype(float).mean()) if not qual.empty else \
                float(g[metric].astype(float).mean() or 0.0)
            r_full, n, mean_min = _split_half_reliability(g, metric)
            if r_full is not None:
                k = mean_min * (1 - r_full) / r_full
                k = float(min(max(k, K_FLOOR), K_CEIL))
                method = "splithalf"
            else:
                k = _heuristic_k(g, metric)
                method = "heuristic"
            out[metric][role] = {
                "K": round(k, 1), "method": method,
                "r": round(r_full, 3) if r_full is not None else None,
                "n": n, "role_avg": round(role_avg, 4),
            }
    return out


def apply_shrinkage(df: pd.DataFrame, k_table: Dict[str, Dict[str, Any]]) -> pd.DataFrame:
    """
    Add an ``{metric}_adj`` column for every per-90 metric (Empirical-Bayes
    shrinkage toward the within-role mean).  Raw ``{metric}`` columns are kept
    untouched (additive).  Unclassified players get adj == raw (no role prior).
    """
    out = df.copy()
    for metric in PER90_METRICS:
        adj_col = f"{metric}_adj"
        out[adj_col] = out[metric].astype(float)  # default: unchanged (UNCL)
        for role, params in k_table.get(metric, {}).items():
            K = params["K"]; role_avg = params["role_avg"]
            mask = out["role_group"] == role
            if not mask.any():
                continue
            mins = out.loc[mask, "minutes"].astype(float)
            obs = out.loc[mask, metric].astype(float)
            w = mins / (mins + K)
            out.loc[mask, adj_col] = (w * obs + (1 - w) * role_avg).round(4)
    return out


def precompute_season_players(season: str) -> pd.DataFrame:
    """
    Build the season-aggregate player table for ALL teams in a season and save it
    to data/ready/player_season_{season}.parquet.

    Returns the combined DataFrame (also for inspection/testing).
    """
    from src.utils.paths import list_match_files, parse_match_filename
    from src.analytics.player_analysis import analyse_player_analysis

    season_label = season.replace("_", "/")
    print(f"\n  — Season Player Analysis precompute: {season_label}")
    t0 = time.time()

    files = list_match_files(season)
    if not files:
        print(f"  ⚠ No match files found for {season_label}")
        return pd.DataFrame()

    # Compute each match bundle ONCE (it covers both teams), then route it to both
    # teams' accumulators.  This avoids recomputing the expensive PV bundle twice.
    team_matches: Dict[str, list[tuple[str, dict]]] = defaultdict(list)

    for f in files:
        info = parse_match_filename(f)
        md = info.get("week", "?")
        home = canonical_name(info["home"])
        away = canonical_name(info["away"])
        try:
            bundle = analyse_player_analysis(f)
        except Exception as exc:
            print(f"    ⚠ Player bundle {f.name}: {exc}")
            continue
        team_matches[home].append((md, bundle))
        team_matches[away].append((md, bundle))

    all_rows: list[dict] = []
    for team_canon, bundles in team_matches.items():
        all_rows.extend(aggregate_team_season(season_label, team_canon, bundles))

    if not all_rows:
        print(f"  ⚠ No player rows produced for {season_label}")
        return pd.DataFrame()

    out = pd.DataFrame(all_rows)

    # ── Second pass: league-wide minutes-weighted shrinkage (Phase 1) ─────────
    # Needs every team's rows present so role-group means + split-half K can be
    # estimated across the whole league, then folded back per player.
    k_table = estimate_k_per_metric(out)
    out = apply_shrinkage(out, k_table)

    out = out.sort_values(["team", "total_pva_p90_adj"], ascending=[True, False]).reset_index(drop=True)

    path = READY_DATA_DIR / f"player_season_{season}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(path, index=False, engine="pyarrow")

    # Persist the K-table sidecar (documentation / thesis methodology).
    try:
        k_path = READY_DATA_DIR / f"player_season_{season}_k_table.json"
        k_path.write_text(json.dumps(k_table, indent=2))
        print(f"  ✓ K-table written → {k_path.name}")
    except OSError as exc:
        log.warning("Could not write K-table sidecar: %s", exc)
    print(f"  ✓ Season Player Analysis: {len(out)} player-rows "
          f"({out['team'].nunique()} teams) → {path.name}")
    print(f"  ✓ Season Player Analysis precompute done in {time.time()-t0:.1f}s")
    log.info("player_season_%s.parquet written: %d rows", season, len(out))
    return out


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
    seasons = sys.argv[1:] or ["2024_2025"]
    for s in seasons:
        precompute_season_players(s)
