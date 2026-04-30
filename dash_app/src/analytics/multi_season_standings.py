"""
Multi-Season Standings Analytics Module
========================================
Refactored from notebook: 08_multi_season_standings.ipynb

Provides:
  - load_season_matches()   → load match results from event CSVs
  - compute_standings()     → build league table from match data
  - compute_points_progression() → cumulative points per matchday
  - build_standings_figure() → interactive Plotly chart (Season/Team view)

Data source: Opta match-event CSVs under data/raw/serie_a_*/events/
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from src.config import RAW_DATA_DIR
from src.team_mapping import canonical_name


# ── SEASONS LIST ──────────────────────────────────────────────────────────────
SEASONS_LIST = ["2021/2022", "2022/2023", "2023/2024", "2024/2025", "2025/2026"]

# ── COLOUR PALETTE ───────────────────────────────────────────────────────────
PALETTE = [
    "#636EFA", "#EF553B", "#00CC96", "#AB63FA", "#FFA15A",
    "#19D3F3", "#FF6692", "#B6E880", "#FF97FF", "#FECB52",
    "#1F77B4", "#FF7F0E", "#2CA02C", "#D62728", "#9467BD",
    "#8C564B", "#E377C2", "#7F7F7F", "#BCBD22", "#17BECF",
]


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — MATCH LOADING (from CSV event files)
# ─────────────────────────────────────────────────────────────────────────────

def _parse_match_csv(fp: Path, season_label: str) -> Optional[dict]:
    """
    Extract match-level result from a single event CSV.

    Uses the filename pattern: ``{week}_{Home}_{Away}_{matchId}.csv``
    and reads goal events from the CSV to determine the score.

    Own-goal handling
    -----------------
    A goal event with ``own goal == 'Si'`` was scored by the listed player
    but is credited to the **opposing** side:
      * home-player OG → away goal
      * away-player OG → home goal
    """
    try:
        stem = fp.stem
        parts = stem.split("_")
        if len(parts) < 4:
            return None

        raw_week = parts[0]
        home_csv = parts[1]
        away_csv = parts[2]

        home = canonical_name(home_csv)
        away = canonical_name(away_csv)

        df = pd.read_csv(fp, low_memory=False)

        # ── Matchday resolution ──
        try:
            week = int(raw_week)
        except ValueError:
            if "week" in df.columns and df["week"].notna().any():
                week = int(df["week"].dropna().iloc[0])
            else:
                week = 0

        # ── Match date (for replay deduplication) ──
        match_date = ""
        if "local_date" in df.columns and df["local_date"].notna().any():
            match_date = str(df["local_date"].dropna().iloc[0])

        # ── Goal counting with own-goal correction ──
        goals = df[df["type_id"] == 16]

        hg = 0
        ag = 0

        if not goals.empty and "team_position" in goals.columns:
            has_og_col = "own goal" in goals.columns
            for _, g in goals.iterrows():
                pos = g["team_position"]
                is_og = False
                if has_og_col:
                    og_val = g["own goal"]
                    is_og = pd.notna(og_val) and str(og_val).strip() == "Si"

                if is_og:
                    # OG: credit goal to opposing side
                    if pos == "home":
                        ag += 1
                    else:
                        hg += 1
                else:
                    if pos == "home":
                        hg += 1
                    else:
                        ag += 1

        return {
            "Season": season_label,
            "Matchday": week,
            "Home": home,
            "Away": away,
            "HG": hg,
            "AG": ag,
            "Date": match_date,
            "File": fp.name,
        }

    except Exception:
        return None


def _dedup_replayed_matches(df: pd.DataFrame) -> pd.DataFrame:
    """Remove voided fixtures when a replay exists.

    If the same (Home, Away) pair appears more than once in a season,
    keep only the row with the latest Date (the official replay).
    """
    if df.empty:
        return df

    fixture_key = df["Home"] + "_" + df["Away"]
    dup_mask = fixture_key.duplicated(keep=False)

    if not dup_mask.any():
        return df

    clean = df[~dup_mask]
    dups = df[dup_mask].copy()
    kept = dups.sort_values("Date").groupby(["Home", "Away"], as_index=False).last()

    result = pd.concat([clean, kept], ignore_index=True)
    return result.sort_values(["Matchday", "Home"]).reset_index(drop=True)


def load_season_matches(season: str) -> pd.DataFrame:
    """
    Load all match results for a season from event CSVs.

    Parameters
    ----------
    season : str
        Season identifier like '2024_2025'

    Returns
    -------
    pd.DataFrame with columns: Season, Matchday, Home, Away, HG, AG, Date, File
    """
    events_dir = RAW_DATA_DIR / f"serie_a_{season}" / "events"
    if not events_dir.exists():
        return pd.DataFrame()

    season_label = season.replace("_", "/")
    csv_files = sorted(events_dir.glob("*.csv"))

    records = []
    for fp in csv_files:
        row = _parse_match_csv(fp, season_label)
        if row is not None:
            records.append(row)

    df = pd.DataFrame(records)
    if not df.empty:
        df = _dedup_replayed_matches(df)
        df = df.sort_values(["Matchday", "Home"]).reset_index(drop=True)

    return df


def load_all_seasons() -> pd.DataFrame:
    """Auto-discover and load all available seasons."""
    season_dirs = sorted(RAW_DATA_DIR.glob("serie_a_*"))
    frames = []
    for sd in season_dirs:
        if sd.is_dir() and (sd / "events").is_dir():
            season_key = sd.name.replace("serie_a_", "")
            df = load_season_matches(season_key)
            if not df.empty:
                frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — STANDINGS COMPUTATION
# ─────────────────────────────────────────────────────────────────────────────

def compute_standings(matches_df: pd.DataFrame) -> pd.DataFrame:
    """Compute league standings per Season from match-level data."""
    if matches_df.empty:
        return pd.DataFrame()

    home = matches_df.assign(Team=matches_df["Home"], GF=matches_df["HG"], GA=matches_df["AG"])
    away = matches_df.assign(Team=matches_df["Away"], GF=matches_df["AG"], GA=matches_df["HG"])
    expanded = pd.concat([home, away], ignore_index=True)

    expanded["W"] = (expanded["GF"] > expanded["GA"]).astype(int)
    expanded["D"] = (expanded["GF"] == expanded["GA"]).astype(int)
    expanded["L"] = (expanded["GF"] < expanded["GA"]).astype(int)
    expanded["Points"] = expanded["W"] * 3 + expanded["D"]

    standings = (
        expanded
        .groupby(["Season", "Team"], as_index=False)
        .agg(
            MP=("W", "count"),
            W=("W", "sum"),
            D=("D", "sum"),
            L=("L", "sum"),
            GF=("GF", "sum"),
            GA=("GA", "sum"),
            Points=("Points", "sum"),
        )
    )
    standings["GD"] = standings["GF"] - standings["GA"]
    standings = standings[
        ["Season", "Team", "MP", "W", "D", "L", "GF", "GA", "GD", "Points"]
    ]
    standings = (
        standings
        .sort_values(
            ["Season", "Points", "GD", "GF"],
            ascending=[True, False, False, False],
        )
        .reset_index(drop=True)
    )
    return standings


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — CUMULATIVE POINTS PROGRESSION
# ─────────────────────────────────────────────────────────────────────────────

def compute_points_progression(matches_df: pd.DataFrame) -> pd.DataFrame:
    """Compute per-team cumulative points across matchdays.

    Returns DataFrame with match detail columns for hover tooltips.
    """
    if matches_df.empty:
        return pd.DataFrame()

    home = matches_df[["Season", "Matchday", "Home", "Away", "HG", "AG"]].copy()
    home = home.rename(columns={"Home": "Team"})
    home["GF"] = home["HG"]
    home["GA"] = home["AG"]
    home["MatchLabel"] = home["Team"] + "-" + home["Away"] + " " + home["HG"].astype(str) + "-" + home["AG"].astype(str)
    home = home[["Season", "Matchday", "Team", "GF", "GA", "MatchLabel"]]

    away = matches_df[["Season", "Matchday", "Home", "Away", "HG", "AG"]].copy()
    away = away.rename(columns={"Away": "Team"})
    away["GF"] = away["AG"]
    away["GA"] = away["HG"]
    away["MatchLabel"] = away["Home"] + "-" + away["Team"] + " " + away["HG"].astype(str) + "-" + away["AG"].astype(str)
    away = away[["Season", "Matchday", "Team", "GF", "GA", "MatchLabel"]]

    rows = pd.concat([home, away], ignore_index=True)

    rows["MatchPoints"] = np.where(
        rows["GF"] > rows["GA"], 3,
        np.where(rows["GF"] == rows["GA"], 1, 0),
    )

    # Result letter for form display
    rows["Result"] = np.where(
        rows["GF"] > rows["GA"], "W",
        np.where(rows["GF"] == rows["GA"], "D", "L"),
    )

    rows = rows.sort_values(["Season", "Team", "Matchday"]).reset_index(drop=True)
    rows["CumulativePoints"] = rows.groupby(["Season", "Team"])["MatchPoints"].cumsum()

    return rows[["Season", "Matchday", "Team", "GF", "GA", "MatchPoints", "CumulativePoints", "MatchLabel", "Result"]]


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — PLOTLY FIGURE BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def build_standings_figure(
    progression_df: pd.DataFrame,
    team: str,
    highlight_season: Optional[str] = None,
) -> go.Figure:
    """
    Build the interactive points-progression Plotly figure for a single
    team across all available seasons.

    No in-chart dropdowns — the team is fixed and the season is
    controlled externally via the page header.

    Parameters
    ----------
    progression_df : pd.DataFrame
        Output of compute_points_progression()  (includes MatchLabel)
    team : str
        Canonical team name — only this team is shown.
    highlight_season : str, optional
        Season label (e.g. "2025/2026") to render with a bolder line.

    Returns
    -------
    go.Figure — ready to embed in a dcc.Graph
    """
    if progression_df.empty or not team:
        fig = go.Figure()
        fig.update_layout(
            template="plotly_dark",
            title="No data available",
            paper_bgcolor="#1b2838",
            plot_bgcolor="#1b2838",
        )
        return fig

    tdf = progression_df[progression_df["Team"] == team]
    if tdf.empty:
        fig = go.Figure()
        fig.update_layout(
            template="plotly_dark",
            title=f"No data for {team}",
            paper_bgcolor="#1b2838",
            plot_bgcolor="#1b2838",
        )
        return fig

    seasons_for_team = sorted(tdf["Season"].unique())
    fig = go.Figure()

    for j, season in enumerate(seasons_for_team):
        sdf = tdf[tdf["Season"] == season].sort_values("Matchday")
        is_hl = (highlight_season and season == highlight_season)

        # Build per-point custom hover text
        hover_texts = []
        for _, row in sdf.iterrows():
            match_label = row.get("MatchLabel", "")
            ht = (
                f"<b>{team} — {season}</b><br>"
                f"Points: {int(row['CumulativePoints'])}<br>"
                f"Match: {match_label}"
                f"<extra></extra>"
            )
            hover_texts.append(ht)

        fig.add_trace(go.Scatter(
            x=sdf["Matchday"],
            y=sdf["CumulativePoints"],
            mode="lines+markers",
            name=season,
            line=dict(
                color="#8a1f33" if is_hl else PALETTE[j % len(PALETTE)],
                width=3.5 if is_hl else 2,
            ),
            marker=dict(size=7 if is_hl else 4),
            hovertemplate="%{text}",
            text=hover_texts,
            visible=True,
        ))

    # ── Benchmark lines (median final-season cutoffs, 2021/22 – 2025/26) ──
    # UCL: 1st–4th (direct), UEL: 5th (direct), UECL: 6th (playoff)
    # Relegation: 17th place = last safe spot (median 33 pts across 5 seasons)
    BENCHMARKS = [
        {"y": 70, "color": "#0E1E5B", "label": "UCL (Top 4) — ~70 pts"},
        {"y": 68, "color": "#F47E01", "label": "UEL (Top 5) — ~68 pts"},
        {"y": 63, "color": "#00CC44", "label": "UECL playoff (Top 6) — ~63 pts"},
        {"y": 33, "color": "#FF1A1A", "label": "Relegation zone — ~33 pts"},
    ]

    max_matchday = int(progression_df["Matchday"].max()) if not progression_df.empty else 38

    for bm in BENCHMARKS:
        fig.add_shape(
            type="line",
            x0=1,
            x1=max_matchday,
            y0=bm["y"],
            y1=bm["y"],
            line=dict(color=bm["color"], width=1.8, dash="dash"),
        )
        fig.add_annotation(
            x=1,
            y=bm["y"],
            text=bm["label"],
            showarrow=False,
            xanchor="left",
            yanchor="bottom",
            font=dict(size=10, color=bm["color"]),
            bgcolor="rgba(27,40,56,0.0)",
        )

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text=f"Points Progression — {team}",
            font=dict(size=18, color="white"),
        ),
        xaxis=dict(
            title="Matchday",
            dtick=1,
            gridcolor="rgba(255,255,255,0.06)",
        ),
        yaxis=dict(
            title="Cumulative Points",
            gridcolor="rgba(255,255,255,0.06)",
        ),
        legend=dict(
            font=dict(size=11),
            bgcolor="rgba(0,0,0,0.45)",
            bordercolor="rgba(255,255,255,0.2)",
            borderwidth=1,
            tracegroupgap=4,
        ),
        paper_bgcolor="#1b2838",
        plot_bgcolor="#1b2838",
        height=620,
        margin=dict(t=80, l=60, r=30, b=50),
        hovermode="closest",
    )

    return fig
