"""
PPDA Analytics Module
======================
Refactored from notebook: 05_ppda.ipynb

Provides:
  - load_season_events()          → load & clean event data for a season
  - compute_ppda()                → compute PPDA per team (league-wide)
  - compute_mean_seconds_to_regain() → pressing speed metric
  - build_ppda_bar_figure()       → ranked horizontal bar chart
  - build_ppda_scatter_figure()   → PPDA vs regain seconds scatter

Data source: Opta match-event CSVs under data/raw/serie_a_*/events/
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from src.config import RAW_DATA_DIR, PRIMARY_COLOR, LOGOS_DIR
from src.team_mapping import canonical_name, TEAM_LOGO_MAP


# ── PPDA Constants ────────────────────────────────────────────────────────────
PPDA_ZONE_UPPER = 60       # passer's x_from_own_goal ≤ 60
PRESSING_ZONE_MIN = 100 - PPDA_ZONE_UPPER  # = 40
PASS_EVENT = "pass"
REGAIN_EVENT = "ball recovery"

# ── Dashboard colour palette ─────────────────────────────────────────────────
from src.styling.theme import SEMANTIC_COLORS, get_colors
from src.styling.plotly_template import apply_chart_theme

NEUTRAL_COLOR = SEMANTIC_COLORS["opponent"]    # "#4a6274"
HIGHLIGHT_COLOR = SEMANTIC_COLORS["team"]      # "#8a1f33" (== PRIMARY_COLOR)
ELITE_GREEN = SEMANTIC_COLORS["outcome_positive"]   # was #00CC96 — harmonised green
WARN_RED = SEMANTIC_COLORS["outcome_negative"]      # was #EF553B — harmonised red


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1 — EVENT LOADING
# ═══════════════════════════════════════════════════════════════════════════════

def _short_name(opta_name: str) -> str:
    """Map an Opta long-form team name to a dashboard-canonical short name."""
    return canonical_name(opta_name)


def load_season_events(season: str) -> pd.DataFrame:
    """
    Load all match-event CSVs for a season and prepare the columns
    needed for PPDA computation.

    Returns a DataFrame with columns:
        event_id, event, period_id, time_min, time_sec, team_name,
        team_position, x, y, outcome, match_id,
        is_success, t_sec, is_pass, is_regain, opponent,
        own_goal_x, x_from_own_goal, team_short
    """
    events_dir = RAW_DATA_DIR / f"serie_a_{season}" / "events"
    if not events_dir.exists():
        return pd.DataFrame()

    cols = [
        "event_id", "event", "period_id", "time_min", "time_sec",
        "team_name", "team_position", "x", "y", "outcome", "match_id",
    ]

    csv_files = sorted(events_dir.glob("*.csv"))
    if not csv_files:
        return pd.DataFrame()

    frames = []
    for f in csv_files:
        try:
            df = pd.read_csv(f, usecols=cols, low_memory=False)
            frames.append(df)
        except Exception:
            continue

    if not frames:
        return pd.DataFrame()

    events = pd.concat(frames, ignore_index=True)

    # ── Numeric coercions ────────────────────────────────────
    for col in ["period_id", "time_min", "time_sec", "x", "y"]:
        events[col] = pd.to_numeric(events[col], errors="coerce")

    # ── Drop rows missing essentials ─────────────────────────
    events = events.dropna(
        subset=["match_id", "team_name", "team_position", "period_id",
                "time_min", "time_sec", "x"]
    )

    # ── Outcome → boolean ───────────────────────────────────
    events["is_success"] = events["outcome"].apply(
        lambda v: int(v) == 1
        if pd.notna(v) and isinstance(v, (int, float, np.integer, np.floating))
        else False
    )

    # ── Timestamp in seconds ─────────────────────────────────
    events["t_sec"] = events["time_min"] * 60 + events["time_sec"]

    # ── Event flags ──────────────────────────────────────────
    events["is_pass"] = events["event"].str.strip().str.lower().eq(PASS_EVENT)
    events["is_regain"] = events["event"].str.strip().str.lower().eq(REGAIN_EVENT)

    # ── Opponent mapping ─────────────────────────────────────
    teams_by_match = (
        events[["match_id", "team_name", "team_position"]]
        .drop_duplicates()
        .pivot_table(index="match_id", columns="team_position",
                     values="team_name", aggfunc="first")
    )
    teams_by_match.columns = [str(c).strip().lower() for c in teams_by_match.columns]

    if not {"home", "away"}.issubset(teams_by_match.columns):
        return pd.DataFrame()

    match_home = teams_by_match["home"].to_dict()
    match_away = teams_by_match["away"].to_dict()

    def _get_opponent(match_id, team_name):
        h, a = match_home.get(match_id), match_away.get(match_id)
        if team_name == h:
            return a
        if team_name == a:
            return h
        return np.nan

    events["opponent"] = [
        _get_opponent(mid, tn)
        for mid, tn in zip(events["match_id"], events["team_name"])
    ]
    events = events.dropna(subset=["opponent"])

    # ── Compute x_from_own_goal ──────────────────────────────
    def _own_goal_x(team_position: str, period_id: int) -> int:
        tp = str(team_position).strip().lower()
        p = int(period_id)
        if p == 1:
            return 0 if tp == "home" else 100
        else:
            return 100 if tp == "home" else 0

    events["own_goal_x"] = [
        _own_goal_x(tp, p)
        for tp, p in zip(events["team_position"], events["period_id"])
    ]
    events["x_from_own_goal"] = np.where(
        events["own_goal_x"] == 0, events["x"], 100 - events["x"]
    )

    # ── Add short display names ──────────────────────────────
    events["team_short"] = events["team_name"].map(_short_name)

    return events


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2 — PPDA COMPUTATION
# ═══════════════════════════════════════════════════════════════════════════════

def compute_ppda(events: pd.DataFrame) -> pd.DataFrame:
    """
    Compute season-level PPDA for every team.

    Returns DataFrame with columns:
        team_short, passes_allowed, ball_recoveries, PPDA, matches, ppda_std
    Sorted ascending by PPDA (most intense first).
    """
    if events.empty:
        return pd.DataFrame()

    # ── 1) Opponent passes in their own defensive zone ───────
    passes_in_zone = events[
        events["is_pass"]
        & (events["x_from_own_goal"] <= PPDA_ZONE_UPPER)
    ].copy()
    passes_in_zone["pressing_team"] = passes_in_zone["opponent"]

    passes_allowed = (
        passes_in_zone.groupby("pressing_team")
        .size()
        .rename("passes_allowed")
    )

    # ── 2) Pressing team's ball recoveries in same zone ──────
    regains_in_zone = events[
        events["is_regain"]
        & (events["x_from_own_goal"] >= PRESSING_ZONE_MIN)
    ]

    ball_recoveries = (
        regains_in_zone.groupby("team_name")
        .size()
        .rename("ball_recoveries")
    )

    # ── 3) Combine → PPDA ───────────────────────────────────
    ppda = pd.concat([passes_allowed, ball_recoveries], axis=1).fillna(0)
    ppda = ppda[ppda["ball_recoveries"] > 0].copy()
    ppda["PPDA"] = (ppda["passes_allowed"] / ppda["ball_recoveries"]).round(2)

    # ── 4) Per-match PPDA (for std dev) ──────────────────────
    pa_match = (
        passes_in_zone.groupby(["pressing_team", "match_id"])
        .size()
        .rename("passes_allowed")
        .reset_index()
    )
    br_match = (
        regains_in_zone.groupby(["team_name", "match_id"])
        .size()
        .rename("ball_recoveries")
        .reset_index()
        .rename(columns={"team_name": "pressing_team"})
    )
    ppda_match = pa_match.merge(
        br_match, on=["pressing_team", "match_id"], how="outer"
    ).fillna(0)
    ppda_match["ppda_match"] = np.where(
        ppda_match["ball_recoveries"] > 0,
        ppda_match["passes_allowed"] / ppda_match["ball_recoveries"],
        np.nan,
    )

    ppda_stats = (
        ppda_match.groupby("pressing_team")["ppda_match"]
        .agg(matches="count", ppda_std="std")
        .round(2)
    )
    ppda = ppda.join(ppda_stats)

    # ── Sort & label ─────────────────────────────────────────
    ppda = ppda.sort_values("PPDA", ascending=True)
    ppda.index.name = "team"
    ppda["team_short"] = ppda.index.map(_short_name)

    return ppda.reset_index()


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 3 — MEAN SECONDS TO REGAIN (DEPRECATED — use Field Tilt instead)
# ═══════════════════════════════════════════════════════════════════════════════

###
### def compute_mean_seconds_to_regain(events: pd.DataFrame) -> pd.DataFrame:
###     """
###     Compute mean seconds to regain possession per team in the pressing zone.
###
###     Returns DataFrame with columns:
###         team, n_regains, mean_seconds, median_seconds
###     """
###

def _compute_mean_seconds_to_regain_deprecated(events: pd.DataFrame) -> pd.DataFrame:
    """
    DEPRECATED: Use Field Tilt instead.
    Compute mean seconds to regain possession per team in the pressing zone.

    Returns DataFrame with columns:
        team, n_regains, mean_seconds, median_seconds
    """
    if events.empty:
        return pd.DataFrame()

    events_zone = events[events["x_from_own_goal"] >= PRESSING_ZONE_MIN].copy()

    ez = events_zone.sort_values(
        ["match_id", "period_id", "t_sec", "event_id"], kind="mergesort"
    ).reset_index(drop=True)

    # ── Possession proxy ─────────────────────────────────────
    ez["pos_team"] = pd.array([pd.NA] * len(ez), dtype=pd.StringDtype())
    mask_control = (ez["is_pass"] & ez["is_success"]) | ez["is_regain"]
    ez.loc[mask_control, "pos_team"] = ez.loc[mask_control, "team_name"].astype(pd.StringDtype())
    ez["pos_team"] = ez.groupby("match_id")["pos_team"].ffill()

    # ── Detect possession changes ────────────────────────────
    ez["prev_pos_team"] = ez.groupby("match_id")["pos_team"].shift(1)
    ez["pos_change"] = (
        (ez["pos_team"] != ez["prev_pos_team"]) & ez["prev_pos_team"].notna()
    )

    # ── Build loss → regain windows ──────────────────────────
    loss_events = ez[ez["pos_change"]].copy()
    loss_events["lost_team"] = loss_events["prev_pos_team"]
    loss_events["loss_t"] = loss_events["t_sec"]
    loss_events["loss_period"] = loss_events["period_id"]

    da_events = ez[ez["is_regain"]][
        ["match_id", "period_id", "t_sec", "team_name"]
    ].copy()
    da_events = da_events.rename(
        columns={"t_sec": "regain_t", "team_name": "regain_team"}
    )

    windows = []
    for _, loss in loss_events.iterrows():
        mid = loss["match_id"]
        team = loss["lost_team"]
        t0 = loss["loss_t"]
        pid = loss["loss_period"]
        candidates = da_events[
            (da_events["match_id"] == mid)
            & (da_events["regain_team"] == team)
            & (da_events["period_id"] == pid)
            & (da_events["regain_t"] > t0)
        ]
        if candidates.empty:
            continue
        windows.append({
            "match_id": mid,
            "team": team,
            "loss_t": t0,
            "regain_t": candidates["regain_t"].iloc[0],
            "seconds_to_regain": candidates["regain_t"].iloc[0] - t0,
        })

    if not windows:
        return pd.DataFrame()

    regain_df = pd.DataFrame(windows)

    regain_team = (
        regain_df.groupby("team")["seconds_to_regain"]
        .agg(n_regains="count", mean_seconds="mean", median_seconds="median")
        .round(2)
        .sort_values("mean_seconds")
    )

    return regain_team.reset_index()


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 3b — FIELD TILT COMPUTATION
# ═══════════════════════════════════════════════════════════════════════════════

def compute_field_tilt(events: pd.DataFrame) -> pd.DataFrame:
    """
    Compute Field Tilt for every team.
    
    Field Tilt (%) = (Team's Final Third Passes ÷ Total Final Third Passes) × 100
    Final Third = attacking third (x_from_own_goal > 66.67)

    Returns DataFrame with columns:
        team, final_third_passes, field_tilt
    """
    if events.empty:
        return pd.DataFrame()

    # ── 1) Filter passes in final third (attacking third) ─────
    final_third_threshold = 66.67
    passes_final_third = events[
        events["is_pass"]
        & (events["x_from_own_goal"] > final_third_threshold)
    ].copy()

    if passes_final_third.empty:
        return pd.DataFrame()

    # ── 2) Count final third passes per team ──────────────────
    team_final_third_passes = (
        passes_final_third.groupby("team_name")
        .size()
        .rename("final_third_passes")
    )

    # ── 3) Total final third passes per match ────────────────
    # This is needed to normalize per match
    match_final_third_total = (
        passes_final_third.groupby("match_id")
        .size()
        .rename("match_total")
    )

    # ── 4) Per-match field tilt ──────────────────────────────
    passes_final_third_match = (
        passes_final_third.groupby(["team_name", "match_id"])
        .size()
        .rename("match_passes")
        .reset_index()
    )

    match_totals_df = (
        passes_final_third.groupby("match_id")
        .size()
        .reset_index(name="match_total")
    )

    field_tilt_match = passes_final_third_match.merge(
        match_totals_df, on="match_id"
    )
    field_tilt_match["match_field_tilt"] = (
        (field_tilt_match["match_passes"] / field_tilt_match["match_total"]) * 100
    ).round(2)

    # ── 5) Average field tilt across season ──────────────────
    field_tilt_season = (
        field_tilt_match.groupby("team_name")["match_field_tilt"]
        .agg(field_tilt="mean")
        .round(2)
    )

    # ── 6) Add total final third passes ──────────────────────
    result = team_final_third_passes.to_frame().join(field_tilt_season)
    result.index.name = "team"

    return result.reset_index()


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 4 — MERGED PPDA TABLE (for KPIs and charts)
# ═══════════════════════════════════════════════════════════════════════════════

def build_ppda_table(season: str) -> pd.DataFrame:
    """
    Full PPDA analytics table for a season, merging PPDA and field tilt metrics.

    Returns DataFrame with columns:
        team, team_short, PPDA, passes_allowed, ball_recoveries,
        matches, ppda_std, final_third_passes, field_tilt, rank
    """
    events = load_season_events(season)
    if events.empty:
        return pd.DataFrame()

    ppda_df = compute_ppda(events)
    if ppda_df.empty:
        return pd.DataFrame()

    field_tilt_df = compute_field_tilt(events)

    if not field_tilt_df.empty:
        merged = ppda_df.merge(field_tilt_df, on="team", how="left")
    else:
        merged = ppda_df.copy()
        merged["final_third_passes"] = np.nan
        merged["field_tilt"] = np.nan

    # Sort by PPDA ascending (most intense first) and assign rank
    merged = merged.sort_values("PPDA", ascending=True).reset_index(drop=True)
    merged["rank"] = range(1, len(merged) + 1)

    return merged


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 5 — PLOTLY FIGURE BUILDERS
# ═══════════════════════════════════════════════════════════════════════════════

def build_ppda_bar_figure(
    ppda_table: pd.DataFrame,
    highlight_team: str = "",
) -> go.Figure:
    """
    Build a horizontal bar chart ranking teams by PPDA.
    Lower PPDA = more intense pressing → shown at top.

    Parameters
    ----------
    ppda_table : pd.DataFrame
        Output of build_ppda_table()
    highlight_team : str
        Team to highlight in a different color
    """
    if ppda_table.empty:
        fig = go.Figure()
        fig.update_layout(title="No PPDA data available")
        return apply_chart_theme(fig, "dark")

    df = ppda_table.sort_values("PPDA", ascending=True).copy()

    # ── Build colors array ───────────────────────────────────
    colors = []
    for _, row in df.iterrows():
        if row["team_short"] == highlight_team:
            colors.append(HIGHLIGHT_COLOR)
        else:
            colors.append(NEUTRAL_COLOR)

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=df["PPDA"],
        y=df["team_short"],
        orientation="h",
        marker=dict(
            color=colors,
            line=dict(width=0),
        ),
        text=df["PPDA"].apply(lambda v: f"{v:.2f}"),
        textposition="outside",
        textfont=dict(size=11, color=get_colors("dark")["text_secondary"]),
        hovertemplate=(
            "<b>%{y}</b><br>"
            "PPDA: %{x:.2f}<br>"
            "<extra></extra>"
        ),
    ))

    # Shared design-system theming first, chart-specific layout on top.
    # Built dark; the client-side theme observer re-patches colours on toggle.
    apply_chart_theme(fig, "dark")
    fig.update_layout(
        title=dict(text="PPDA Ranking — Pressing Intensity"),
        xaxis=dict(
            title="PPDA (lower = more intense)",
            zeroline=False,
        ),
        yaxis=dict(
            title="",
            autorange="reversed",
            tickfont=dict(size=11),
            showgrid=False,
        ),
        height=max(450, len(df) * 32),
        margin=dict(l=110, r=60, t=50, b=40),
        showlegend=False,
        bargap=0.25,
    )

    return fig


def build_ppda_scatter_figure(
    ppda_table: pd.DataFrame,
    highlight_team: str = "",
) -> go.Figure:
    """
    Build a scatter plot: PPDA vs Field Tilt.
    Shows team logos for every team, with the selected team highlighted
    via a glowing ring. Quadrant labels are placed dynamically in the
    emptiest corners to avoid overlapping logos.

    Parameters
    ----------
    ppda_table : pd.DataFrame
        Output of build_ppda_table() — must include field_tilt column
    highlight_team : str
        Team to visually emphasise with a ring
    """
    import base64
    from io import BytesIO

    df = ppda_table.dropna(subset=["field_tilt"]).copy()

    if df.empty:
        fig = go.Figure()
        fig.update_layout(title="No scatter data available")
        return apply_chart_theme(fig, "dark")

    # ── Medians for quadrant lines ───────────────────────────
    med_ppda = df["PPDA"].median()
    med_tilt = df["field_tilt"].median()

    # ── Axis ranges with padding ─────────────────────────────
    x_min, x_max = df["field_tilt"].min(), df["field_tilt"].max()
    y_min, y_max = df["PPDA"].min(), df["PPDA"].max()
    x_range = x_max - x_min
    y_range = y_max - y_min
    x_pad = x_range * 0.18
    y_pad = y_range * 0.18

    fig = go.Figure()

    # ── Invisible scatter trace for hover interactivity ──────
    fig.add_trace(go.Scatter(
        x=df["field_tilt"],
        y=df["PPDA"],
        mode="markers",
        marker=dict(size=28, opacity=0),
        hovertext=[
            f"<b>{row['team_short']}</b><br>"
            f"PPDA: {row['PPDA']:.2f}<br>"
            f"Field Tilt: {row['field_tilt']:.1f}%<br>"
            f"Final Third Passes: {int(row['final_third_passes'])}<br>"
            f"Rank: #{int(row['rank'])}"
            for _, row in df.iterrows()
        ],
        hoverinfo="text",
        showlegend=False,
    ))

    # ── Highlight ring for the selected team ─────────────────
    if highlight_team:
        hl_row = df[df["team_short"] == highlight_team]
        if not hl_row.empty:
            fig.add_trace(go.Scatter(
                x=hl_row["field_tilt"],
                y=hl_row["PPDA"],
                mode="markers",
                marker=dict(
                    size=36,
                    color="rgba(0,0,0,0)",
                    line=dict(width=3, color=HIGHLIGHT_COLOR),
                ),
                hoverinfo="skip",
                showlegend=False,
            ))

    # ── Add team logos as layout images ───────────────────────
    badge_x_size = x_range * 0.055
    badge_y_size = y_range * 0.055

    for _, row in df.iterrows():
        team_short = row["team_short"]
        logo_slug = TEAM_LOGO_MAP.get(team_short, team_short.lower().replace(" ", ""))
        logo_path = LOGOS_DIR / f"{logo_slug}.png"

        if not logo_path.exists():
            # Fallback: text annotation if logo missing
            fig.add_annotation(
                x=row["field_tilt"], y=row["PPDA"],
                text=team_short, showarrow=False,
                font=dict(size=8, color="#8899aa"),
            )
            continue

        with open(logo_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()

        fig.add_layout_image(
            source=f"data:image/png;base64,{b64}",
            x=row["field_tilt"],
            y=row["PPDA"],
            xref="x", yref="y",
            sizex=badge_x_size,
            sizey=badge_y_size,
            xanchor="center", yanchor="middle",
            layer="above",
        )

    # ── Quadrant lines (medians) ─────────────────────────────
    fig.add_hline(
        y=med_ppda,
        line=dict(dash="dash", color="rgba(255,255,255,0.18)", width=1),
    )
    fig.add_vline(
        x=med_tilt,
        line=dict(dash="dash", color="rgba(255,255,255,0.18)", width=1),
    )

    # ── Dynamic quadrant label placement ─────────────────────
    # Place labels in the emptiest part of each quadrant so they
    # don't overlap logos.  For each corner we find the point
    # farthest from all data points and anchor the label there.

    corners = {
        "bl": {"xanchor": "left",  "yanchor": "bottom",
               "color": ELITE_GREEN, "opacity": 0.8,
               "text": "<b>Elite Pressing</b><br><span style='font-size:9px;color:#8899aa'>Low PPDA · Low Tilt</span>"},
        "tr": {"xanchor": "right", "yanchor": "top",
               "color": WARN_RED, "opacity": 0.8,
               "text": "<b>Passive Pressing</b><br><span style='font-size:9px;color:#8899aa'>High PPDA · High Tilt</span>"},
        "br": {"xanchor": "right", "yanchor": "bottom",
               "color": "#FFA15A", "opacity": 0.55,
               "text": "<b>Low Pressing Activity</b><br><span style='font-size:9px;color:#8899aa'>Low PPDA · High Tilt</span>"},
        "tl": {"xanchor": "left",  "yanchor": "top",
               "color": "#19D3F3", "opacity": 0.55,
               "text": "<b>Defensive Focus</b><br><span style='font-size:9px;color:#8899aa'>High PPDA · Low Tilt</span>"},
    }

    # Quadrant bounds (data coordinates)
    q_bounds = {
        "bl": (x_min - x_pad, med_tilt, y_min - y_pad, med_ppda),
        "tr": (med_tilt, x_max + x_pad, med_ppda, y_max + y_pad),
        "br": (med_tilt, x_max + x_pad, y_min - y_pad, med_ppda),
        "tl": (x_min - x_pad, med_tilt, med_ppda, y_max + y_pad),
    }

    # Normalise data points to [0,1] within axis range for distance calc
    ax_x_min, ax_x_max = x_min - x_pad, x_max + x_pad
    ax_y_min, ax_y_max = y_min - y_pad, y_max + y_pad
    ax_x_span = ax_x_max - ax_x_min
    ax_y_span = ax_y_max - ax_y_min

    pts_norm_x = ((df["field_tilt"].values - ax_x_min) / ax_x_span) if ax_x_span else df["field_tilt"].values * 0
    pts_norm_y = ((df["PPDA"].values - ax_y_min) / ax_y_span) if ax_y_span else df["PPDA"].values * 0

    for key, info in corners.items():
        qx0, qx1, qy0, qy1 = q_bounds[key]

        # Candidate anchor point: the actual corner of the plot area
        if "left" in info["xanchor"]:
            cx = qx0
        else:
            cx = qx1
        if "bottom" in info["yanchor"]:
            cy = qy0
        else:
            cy = qy1

        # Check minimum normalised distance from anchor to any data point
        cx_n = (cx - ax_x_min) / ax_x_span if ax_x_span else 0
        cy_n = (cy - ax_y_min) / ax_y_span if ax_y_span else 0
        dists = np.sqrt((pts_norm_x - cx_n) ** 2 + (pts_norm_y - cy_n) ** 2)
        min_dist = dists.min()

        # If a logo is very close to the corner, nudge the label inward
        # along the diagonal toward the median cross-point
        if min_dist < 0.15:
            nudge = 0.10
            cx = cx + nudge * (med_tilt - cx)
            cy = cy + nudge * (med_ppda - cy)

        fig.add_annotation(
            x=cx, y=cy,
            text=info["text"],
            showarrow=False,
            font=dict(size=10, color=info["color"]),
            xanchor=info["xanchor"],
            yanchor=info["yanchor"],
            opacity=info["opacity"],
        )

    # Shared design-system theming first, chart-specific layout on top.
    # Built dark; the client-side theme observer re-patches colours on toggle.
    apply_chart_theme(fig, "dark")
    fig.update_layout(
        title=dict(text="PPDA vs Field Tilt"),
        xaxis=dict(
            title="Field Tilt % (higher = more attacking territory control)",
            range=[ax_x_min, ax_x_max],
        ),
        yaxis=dict(
            title="PPDA (lower = more intense pressing)",
            range=[ax_y_min, ax_y_max],
        ),
        height=560,
        margin=dict(l=60, r=30, t=50, b=50),
        hovermode="closest",
    )

    return fig
