"""
Playing Style Wheel — 12-KPI season-aggregate analytics.
=========================================================
Computes a team's playing-style fingerprint across 4 phases of play
(Defence, Possession, Progression, Attack), each phase holding 3 KPIs,
expressed as within-Serie-A season percentiles (0–99).

Design (audited 2026-06): most KPIs are sourced from the season parquets
already written by precompute_serie_a.py, so this module only re-parses raw
match CSVs for the handful of event-level KPIs that have no precomputed home.
The raw pass is single-pass-per-match (both teams at once), mirroring the
existing ``precompute_season_*`` jobs.

Reused (no raw re-parse):
    chances_conceded_summary_{season}.parquet → D1 (xg_conceded_per_match)
    pressing_summary_{season}.parquet         → D2 (ppda_num/den_overall)
    offensive_summary_{season}.parquet        → P1 (gk_long_pct), P3 (ft_possession_pct)
    shots_{season}.parquet                    → A1, A2(shots), A3 (xG, is_penalty)

Raw event parse (single pass / match):
    D3 (high line), P2 (press resistance), G1 (crosses), G2 (circulate),
    G3 (field tilt), A2 (final-third touches denominator)

Coordinate note: Opta x/y in these CSVs are already team-relative — every
team attacks left→right (x: 0 own goal → 100 opp goal) in both periods, so
zone thresholds apply directly without per-period flipping.

KPI keys: D1 D2 D3 P1 P2 P3 G1 G2 G3 A1 A2 A3 (raw + _pct percentile).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from src.config import READY_DATA_DIR
from src.team_mapping import canonical_name
from src.utils.logging import log
from src.utils.paths import list_match_files, parse_match_filename


# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS — pitch zones (team-relative x: 0 own goal → 100 opp goal)
# ═══════════════════════════════════════════════════════════════════════════════

ATT_TWO_THIRDS_X: float = 100.0 / 3        # ≈ 33.33 — attacking two-thirds start
OWN_TWO_THIRDS_X: float = 100.0 / 3 * 2    # ≈ 66.67 — own two-thirds end
FINAL_THIRD_X: float = 100.0 / 3 * 2       # ≈ 66.67 — final third start
GK_SWEEPER_X: float = 100.0 / 6 * 5        # ≈ 83.33 — outside-box marker (opp goal end)

# Opta type_ids
PASS = 1
OFFSIDE_PROVOKED = 55       # defending team caused the offside
TACKLE, INTERCEPTION = 7, 8

# The 12 KPIs and whether a *lower* raw value is better (inverted for percentile).
KPI_IDS: list[str] = [
    "D1", "D2", "D3", "P1", "P2", "P3",
    "G1", "G2", "G3", "A1", "A2", "A3",
]
LOWER_IS_BETTER: set[str] = {"D1", "D2", "A2"}


# ═══════════════════════════════════════════════════════════════════════════════
# RAW-PASS HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _is_si(series: pd.Series) -> pd.Series:
    """Opta wide-format qualifier truthiness: column holds 'Si' when present."""
    return series.astype(str).str.strip().str.lower().eq("si")


def _raw_counters_for_match(csv_path: Path) -> dict[str, dict[str, float]]:
    """
    Single pass over one match CSV → per-team raw counters for the event-level
    KPIs that have no precomputed source.

    Returns ``{team_canonical: {counter: value, ...}}`` with counters:
        crosses, total_passes, ft_passes, prog_dist, total_dist,
        own23_touches, ft_touches,
        offsides_provoked, throughballs_conceded, gk_sweeper,
        opp_ft_passes, opp_def_actions_own23
    The "conceded / opp" counters are stored under the *defending* team's entry.
    """
    try:
        df = pd.read_csv(csv_path, low_memory=False)
    except Exception as exc:
        log.warning("playing_style: failed to read %s: %s", csv_path.name, exc)
        return {}

    if "team_name" not in df.columns or "type_id" not in df.columns:
        return {}

    df["_team"] = df["team_name"].map(lambda t: canonical_name(str(t)))
    teams = [t for t in df["_team"].dropna().unique() if t]
    if len(teams) != 2:
        return {}

    for col in ("x", "y", "Pass End X", "Pass End Y"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    cross_si = _is_si(df["Cross"]) if "Cross" in df.columns else pd.Series(False, index=df.index)
    tb_si = _is_si(df["Through ball"]) if "Through ball" in df.columns else pd.Series(False, index=df.index)

    out: dict[str, dict[str, float]] = {}
    for team in teams:
        opp = teams[0] if teams[1] == team else teams[1]
        tmask = df["_team"] == team
        omask = df["_team"] == opp

        passes = df[tmask & (df["type_id"] == PASS)]
        total_passes = len(passes)
        crosses = int(cross_si[passes.index].sum()) if total_passes else 0
        ft_passes = int((passes["x"] >= FINAL_THIRD_X).sum()) if "x" in passes else 0

        # Directness: progressive x-distance vs total pass travel distance.
        prog_dist = total_dist = 0.0
        if {"x", "Pass End X", "Pass End Y", "y"}.issubset(passes.columns):
            ex, ey = passes["Pass End X"], passes["Pass End Y"]
            sx, sy = passes["x"], passes["y"]
            valid = ex.notna() & ey.notna() & sx.notna() & sy.notna()
            dx = (ex - sx)[valid]
            dist = np.hypot(dx, (ey - sy)[valid])
            prog_dist = float(dx.clip(lower=0).sum())
            total_dist = float(dist.sum())

        # Touch zones (any event by the team with a valid x).
        tev = df[tmask]
        tx = pd.to_numeric(tev["x"], errors="coerce") if "x" in tev else pd.Series(dtype=float)
        own23_touches = int((tx <= OWN_TWO_THIRDS_X).sum())
        ft_touches = int((tx >= FINAL_THIRD_X).sum())

        # High line (defensive): events the team produced while defending.
        offsides_provoked = int((tev["type_id"] == OFFSIDE_PROVOKED).sum())
        gk_sweeper = 0
        gk_rows = tev[(tev.get("type_id").isin([TACKLE, INTERCEPTION, 12]))] if "type_id" in tev else tev.iloc[0:0]
        if "x" in gk_rows:
            gk_sweeper = int((pd.to_numeric(gk_rows["x"], errors="coerce") <= (100.0 - GK_SWEEPER_X)).sum())

        # Opponent-derived "conceded" counters (stored on defending team).
        opp_passes = df[omask & (df["type_id"] == PASS)]
        # Opponent final-third passes are in the opponent's frame (x>=66.67 = our def third)
        opp_ft_passes = int((pd.to_numeric(opp_passes["x"], errors="coerce") >= FINAL_THIRD_X).sum()) if "x" in opp_passes else 0
        throughballs_conceded = int(tb_si[opp_passes.index].sum()) if len(opp_passes) else 0
        # Opp defensive actions (tackle/interception) in our own two-thirds:
        # in the opponent's frame those occur at x >= 33.33 (their attacking 2/3).
        opp_def = df[omask & (df["type_id"].isin([TACKLE, INTERCEPTION]))]
        opp_def_own23 = int((pd.to_numeric(opp_def["x"], errors="coerce") >= ATT_TWO_THIRDS_X).sum()) if "x" in opp_def else 0

        out[team] = {
            "crosses": crosses,
            "total_passes": total_passes,
            "ft_passes": ft_passes,
            "prog_dist": prog_dist,
            "total_dist": total_dist,
            "own23_touches": own23_touches,
            "ft_touches": ft_touches,
            "offsides_provoked": offsides_provoked,
            "throughballs_conceded": throughballs_conceded,
            "gk_sweeper": gk_sweeper,
            "opp_ft_passes": opp_ft_passes,
            "opp_def_actions_own23": opp_def_own23,
        }
    return out


def _aggregate_raw(season: str) -> dict[str, dict[str, float]]:
    """Sum the per-match raw counters across the whole season, per team."""
    files = list_match_files(season)
    agg: dict[str, dict[str, float]] = {}
    for f in files:
        for team, counters in _raw_counters_for_match(Path(f)).items():
            bucket = agg.setdefault(team, {})
            for k, v in counters.items():
                bucket[k] = bucket.get(k, 0.0) + v
    return agg


# ═══════════════════════════════════════════════════════════════════════════════
# PRECOMPUTED-PARQUET HELPERS (reuse, no raw parse)
# ═══════════════════════════════════════════════════════════════════════════════

def _read_ready(name: str) -> Optional[pd.DataFrame]:
    p = READY_DATA_DIR / name
    if not p.exists():
        return None
    try:
        return pd.read_parquet(p)
    except Exception as exc:
        log.warning("playing_style: failed to read %s: %s", name, exc)
        return None


def _team_matches(season: str) -> dict[str, int]:
    """Matches played per team (for /90 and per-match normalisation)."""
    counts: dict[str, int] = {}
    for f in list_match_files(season):
        info = parse_match_filename(Path(f))
        for t in (canonical_name(info["home"]), canonical_name(info["away"])):
            counts[t] = counts.get(t, 0) + 1
    return counts


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════

def compute_playing_style_kpis(team: str, season: str,
                               raw_agg: dict | None = None,
                               parquets: dict | None = None) -> dict:
    """
    Compute the 12 raw playing-style KPIs for one team in one season.

    Returns a dict with keys D1_raw … A3_raw. ``raw_agg`` and ``parquets`` may
    be passed in to avoid re-reading on every team (used by the league builder);
    when omitted they are loaded here for standalone/test use.
    """
    if raw_agg is None:
        raw_agg = _aggregate_raw(season)
    if parquets is None:
        parquets = {
            "chances_conceded": _read_ready(f"chances_conceded_summary_{season}.parquet"),
            "pressing": _read_ready(f"pressing_summary_{season}.parquet"),
            "offensive": _read_ready(f"offensive_summary_{season}.parquet"),
            "shots": _read_ready(f"shots_{season}.parquet"),
            "matches": _team_matches(season),
        }

    r = raw_agg.get(team, {})
    mp = max(parquets["matches"].get(team, 1), 1)

    def _prow(df: Optional[pd.DataFrame]) -> Optional[pd.Series]:
        if df is None or df.empty or "team" not in df.columns:
            return None
        sub = df[df["team"] == team]
        return sub.iloc[0] if not sub.empty else None

    cc = _prow(parquets["chances_conceded"])
    pp = _prow(parquets["pressing"])
    of = _prow(parquets["offensive"])
    shots = parquets["shots"]

    # ── DEFENCE ───────────────────────────────────────────────────────────────
    # D1 — non-pen xGA per 90 (lower better). xg_conceded already excludes pens.
    d1 = float(cc["xg_conceded_per_match"]) if cc is not None else np.nan

    # D2 — opp passes per team defensive action (att 2/3) = PPDA overall (lower better)
    if pp is not None and pp.get("ppda_den_overall", 0):
        d2 = float(pp["ppda_num_overall"]) / float(pp["ppda_den_overall"])
    else:
        d2 = np.nan

    # D3 — (offsides provoked + through-balls conceded + GK sweeper) per 100 opp FT passes
    opp_ft = r.get("opp_ft_passes", 0)
    high_line_events = r.get("offsides_provoked", 0) + r.get("throughballs_conceded", 0) + r.get("gk_sweeper", 0)
    d3 = (high_line_events / opp_ft * 100) if opp_ft else 0.0

    # ── POSSESSION ────────────────────────────────────────────────────────────
    # P1 — deep build-up = 1 − GK launch rate (higher = more short GK passes)
    p1 = (1.0 - float(of["gk_long_pct"]) / 100.0) if of is not None else np.nan

    # P2 — own-2/3 touches per opp defensive action in that zone (higher better)
    opp_def = r.get("opp_def_actions_own23", 0)
    p2 = (r.get("own23_touches", 0) / opp_def) if opp_def else np.nan

    # P3 — possession share (reuse precomputed open-play possession)
    p3 = float(of["ft_possession_pct"]) if of is not None else np.nan

    # ── PROGRESSION ───────────────────────────────────────────────────────────
    tp = r.get("total_passes", 0)
    # G1 — central progression = 1 − crosses per 100 passes (higher = fewer crosses)
    g1 = (1.0 - (r.get("crosses", 0) / tp * 100)) if tp else np.nan
    # G2 — circulate = 1 − directness (higher = less direct)
    td = r.get("total_dist", 0.0)
    g2 = (1.0 - (r.get("prog_dist", 0.0) / td)) if td else np.nan
    # G3 — field tilt = team FT passes / (team + opp FT passes) × 100
    ft_total = r.get("ft_passes", 0) + opp_ft
    g3 = (r.get("ft_passes", 0) / ft_total * 100) if ft_total else np.nan

    # ── ATTACK ────────────────────────────────────────────────────────────────
    # Non-penalty shots for this team
    npxg = np_shots = np.nan
    if shots is not None and not shots.empty:
        tshots = shots[shots["team"] == team]
        # Exclude penalties when the column is present; older parquets omit it.
        if "is_penalty" in tshots.columns:
            tshots = tshots[~tshots["is_penalty"].astype(bool)]
        np_shots = len(tshots)
        npxg = float(tshots["xG"].sum())

    # A1 — non-pen xG per 90 (higher better)
    a1 = (npxg / mp) if (mp and not np.isnan(npxg)) else np.nan
    # A2 — shots per 100 FT touches (lower = more patient)
    ftt = r.get("ft_touches", 0)
    a2 = (np_shots / ftt * 100) if (ftt and not np.isnan(np_shots)) else np.nan
    # A3 — non-pen xG per shot (higher better)
    a3 = (npxg / np_shots) if (np_shots and not np.isnan(npxg)) else np.nan

    return {
        "D1_raw": d1, "D2_raw": d2, "D3_raw": d3,
        "P1_raw": p1, "P2_raw": p2, "P3_raw": p3,
        "G1_raw": g1, "G2_raw": g2, "G3_raw": g3,
        "A1_raw": a1, "A2_raw": a2, "A3_raw": a3,
    }


def compute_league_playing_style(season: str) -> pd.DataFrame:
    """
    Compute raw KPIs for every team in *season*, then within-season percentiles.

    Returns a DataFrame: team, season, D1_raw, D1_pct, …, A3_raw, A3_pct.
    Percentiles use rank-based percentileofscore scaled to 0–99; lower-is-better
    KPIs are inverted (100 − pct) so a higher percentile is always "better".
    """
    from scipy.stats import percentileofscore

    season_label = season.replace("_", "/")
    matches = _team_matches(season)
    teams = sorted(matches.keys())
    if not teams:
        return pd.DataFrame()

    parquets = {
        "chances_conceded": _read_ready(f"chances_conceded_summary_{season}.parquet"),
        "pressing": _read_ready(f"pressing_summary_{season}.parquet"),
        "offensive": _read_ready(f"offensive_summary_{season}.parquet"),
        "shots": _read_ready(f"shots_{season}.parquet"),
        "matches": matches,
    }
    raw_agg = _aggregate_raw(season)

    rows: list[dict] = []
    for team in teams:
        kpis = compute_playing_style_kpis(team, season, raw_agg=raw_agg, parquets=parquets)
        kpis["team"] = team
        kpis["season"] = season_label
        rows.append(kpis)

    df = pd.DataFrame(rows)

    # Within-season percentile per KPI (rank-based, 0–99).
    for kid in KPI_IDS:
        raw_col = f"{kid}_raw"
        vals = df[raw_col].astype(float)
        finite = vals.dropna()
        pct_vals = []
        for v in vals:
            if pd.isna(v) or finite.empty:
                pct_vals.append(np.nan)
                continue
            p = percentileofscore(finite.values, v, kind="rank")
            if kid in LOWER_IS_BETTER:
                p = 100.0 - p
            pct_vals.append(round(min(max(p, 0.0), 99.0), 1))
        df[f"{kid}_pct"] = pct_vals

    # Order columns: team, season, then D1_raw, D1_pct, …
    ordered = ["team", "season"]
    for kid in KPI_IDS:
        ordered += [f"{kid}_raw", f"{kid}_pct"]
    return df[ordered].reset_index(drop=True)
