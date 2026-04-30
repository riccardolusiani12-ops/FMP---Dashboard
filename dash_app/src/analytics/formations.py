"""
Formation Analytics Module
===========================
Analyses match-event CSVs to extract team formations (starting + in-match changes).

Provides:
  - extract_team_formations()       → per-match formation list for a team
  - compute_formation_counts()      → aggregated formation usage for a season
  - build_formation_pitch_figure()  → Plotly pitch visualisation of a formation

Data source: Opta match-event CSVs under data/raw/serie_a_*/events/
Formation data columns:
  - type_id 34: "Team setup" — contains starting formation
  - type_id 40: "Formation change" — in-match formation change
  - 'formation' column: numeric code (e.g. 433 → 4-3-3)
  - 'Team Formation': Opta internal formation ID
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from src.config import RAW_DATA_DIR
from src.team_mapping import canonical_name


# ═══════════════════════════════════════════════════════════════════════════════
# FORMATION CODE → DISPLAY STRING
# ═══════════════════════════════════════════════════════════════════════════════

def formation_display(code: int) -> str:
    """
    Convert a numeric formation code to a human-readable string.
    E.g. 433 → '4-3-3', 4231 → '4-2-3-1', 41212 → '4-1-2-1-2'
    """
    s = str(int(code))
    return "-".join(list(s))


# ═══════════════════════════════════════════════════════════════════════════════
# FORMATION POSITION TEMPLATES
# ═══════════════════════════════════════════════════════════════════════════════
# Each formation maps to 11 player (x, y) positions on a 0–100 pitch.
# x = pitch length (0 = own goal, 100 = opponent goal)
# y = pitch width (0 = left, 100 = right)
# GK is always at (5, 50).
# Positions are approximate and meant for visual display purposes.

_FORMATION_POSITIONS: dict[str, list[tuple[float, float]]] = {
    "4-4-2": [
        (5, 50),                                          # GK
        (22, 15), (22, 38), (22, 62), (22, 85),         # DEF
        (48, 15), (48, 38), (48, 62), (48, 85),         # MID
        (72, 35), (72, 65),                              # FWD
    ],
    "4-3-3": [
        (5, 50),
        (22, 15), (22, 38), (22, 62), (22, 85),
        (45, 30), (45, 50), (45, 70),
        (72, 20), (72, 50), (72, 80),
    ],
    "4-2-3-1": [
        (5, 50),
        (22, 15), (22, 38), (22, 62), (22, 85),
        (40, 35), (40, 65),
        (58, 20), (58, 50), (58, 80),
        (75, 50),
    ],
    "3-5-2": [
        (5, 50),
        (22, 25), (22, 50), (22, 75),
        (42, 10), (42, 30), (42, 50), (42, 70), (42, 90),
        (72, 35), (72, 65),
    ],
    "3-4-2-1": [
        (5, 50),
        (22, 25), (22, 50), (22, 75),
        (42, 15), (42, 38), (42, 62), (42, 85),
        (60, 35), (60, 65),
        (75, 50),
    ],
    "4-1-2-1-2": [
        (5, 50),
        (22, 15), (22, 38), (22, 62), (22, 85),
        (38, 50),
        (50, 30), (50, 70),
        (60, 50),
        (72, 35), (72, 65),
    ],
    "5-3-2": [
        (5, 50),
        (22, 10), (22, 30), (22, 50), (22, 70), (22, 90),
        (45, 30), (45, 50), (45, 70),
        (72, 35), (72, 65),
    ],
    "5-4-1": [
        (5, 50),
        (22, 10), (22, 30), (22, 50), (22, 70), (22, 90),
        (48, 15), (48, 38), (48, 62), (48, 85),
        (72, 50),
    ],
    "4-5-1": [
        (5, 50),
        (22, 15), (22, 38), (22, 62), (22, 85),
        (45, 10), (45, 30), (45, 50), (45, 70), (45, 90),
        (72, 50),
    ],
    "4-4-1-1": [
        (5, 50),
        (22, 15), (22, 38), (22, 62), (22, 85),
        (42, 15), (42, 38), (42, 62), (42, 85),
        (60, 50),
        (75, 50),
    ],
    "4-1-4-1": [
        (5, 50),
        (22, 15), (22, 38), (22, 62), (22, 85),
        (36, 50),
        (52, 15), (52, 38), (52, 62), (52, 85),
        (72, 50),
    ],
    "4-3-2-1": [
        (5, 50),
        (22, 15), (22, 38), (22, 62), (22, 85),
        (42, 25), (42, 50), (42, 75),
        (60, 35), (60, 65),
        (75, 50),
    ],
    "4-2-2-2": [
        (5, 50),
        (22, 15), (22, 38), (22, 62), (22, 85),
        (42, 35), (42, 65),
        (58, 35), (58, 65),
        (72, 35), (72, 65),
    ],
    "3-4-3": [
        (5, 50),
        (22, 25), (22, 50), (22, 75),
        (42, 15), (42, 38), (42, 62), (42, 85),
        (72, 20), (72, 50), (72, 80),
    ],
    "3-5-1-1": [
        (5, 50),
        (22, 25), (22, 50), (22, 75),
        (42, 10), (42, 30), (42, 50), (42, 70), (42, 90),
        (60, 50),
        (75, 50),
    ],
    "3-4-1-2": [
        (5, 50),
        (22, 25), (22, 50), (22, 75),
        (40, 15), (40, 38), (40, 62), (40, 85),
        (58, 50),
        (72, 35), (72, 65),
    ],
    "3-1-4-2": [
        (5, 50),
        (22, 25), (22, 50), (22, 75),
        (35, 50),
        (50, 15), (50, 38), (50, 62), (50, 85),
        (72, 35), (72, 65),
    ],
    "4-1-3-2": [
        (5, 50),
        (22, 15), (22, 38), (22, 62), (22, 85),
        (38, 50),
        (52, 25), (52, 50), (52, 75),
        (72, 35), (72, 65),
    ],
    "4-3-1-2": [
        (5, 50),
        (22, 15), (22, 38), (22, 62), (22, 85),
        (40, 25), (40, 50), (40, 75),
        (58, 50),
        (72, 35), (72, 65),
    ],
    "4-4-2-0": [
        # Fallback identical to 4-4-2 for numeric codes ending in 0
        (5, 50),
        (22, 15), (22, 38), (22, 62), (22, 85),
        (48, 15), (48, 38), (48, 62), (48, 85),
        (72, 35), (72, 65),
    ],
}


def _get_positions(formation_str: str) -> list[tuple[float, float]]:
    """Return player positions for a formation string, or a fallback layout."""
    if formation_str in _FORMATION_POSITIONS:
        return _FORMATION_POSITIONS[formation_str]
    # Fallback: generic 11 dots spread on the pitch
    return [
        (5, 50),
        (22, 20), (22, 40), (22, 60), (22, 80),
        (45, 20), (45, 40), (45, 60), (45, 80),
        (70, 35), (70, 65),
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1 — EXTRACT FORMATIONS FROM CSV FILES
# ═══════════════════════════════════════════════════════════════════════════════

def extract_team_formations(season: str, team: str) -> pd.DataFrame:
    """
    Extract all formations used by a team across a season.

    For each match, captures:
      - Starting formation (from type_id 34 "Team setup")
      - In-match formation changes (from type_id 40 "Formation change")

    Parameters
    ----------
    season : str
        Season key like '2025_2026'
    team : str
        Canonical team name (e.g. 'Bologna')

    Returns
    -------
    pd.DataFrame with columns:
        match_file, team, formation_code, formation_str, is_starting, minute
    """
    events_dir = RAW_DATA_DIR / f"serie_a_{season}" / "events"
    if not events_dir.exists():
        return pd.DataFrame()

    csv_files = sorted(events_dir.glob("*.csv"))
    records: list[dict] = []

    for fp in csv_files:
        try:
            df = pd.read_csv(
                fp,
                usecols=["type_id", "team_name", "team_position", "formation",
                         "Team Formation", "time_min", "period_id"],
                low_memory=False,
            )
        except Exception:
            continue

        # Check if this team played in this match
        # Resolve team name from CSV (Opta long-form → canonical)
        team_names_in_match = df["team_name"].dropna().unique()
        canonical_names = {canonical_name(n): n for n in team_names_in_match}

        if team not in canonical_names:
            continue

        opta_name = canonical_names[team]

        # --- Starting formation (type_id 34, one per team per match) ---
        setup = df[(df["type_id"] == 34) & (df["team_name"] == opta_name)]
        if not setup.empty:
            form_code = setup.iloc[0]["formation"]
            if pd.notna(form_code):
                records.append({
                    "match_file": fp.name,
                    "team": team,
                    "formation_code": int(form_code),
                    "formation_str": formation_display(int(form_code)),
                    "is_starting": True,
                    "minute": 0,
                })

        # --- In-match formation changes (type_id 40) ---
        changes = df[(df["type_id"] == 40) & (df["team_name"] == opta_name)]
        for _, row in changes.iterrows():
            form_code = row["formation"]
            minute = row.get("time_min", 0)
            if pd.notna(form_code):
                form_code_int = int(form_code)
                records.append({
                    "match_file": fp.name,
                    "team": team,
                    "formation_code": form_code_int,
                    "formation_str": formation_display(form_code_int),
                    "is_starting": False,
                    "minute": int(minute) if pd.notna(minute) else 0,
                })

    return pd.DataFrame(records)


def compute_formation_counts(
    season: str,
    team: str,
    min_count: int = 3,
) -> pd.DataFrame:
    """
    Compute formation usage counts for a team in a season.

    Counts each formation every time it appears — either as a starting
    formation or as an in-match change. This means a single match can
    contribute at most 1 starting formation + N change formations.

    Only formations used >= min_count times are returned.

    Parameters
    ----------
    season : str
        Season key like '2025_2026'
    team : str
        Canonical team name
    min_count : int
        Minimum number of times a formation must appear to be included.

    Returns
    -------
    pd.DataFrame with columns: formation_str, count, pct
        Sorted by count descending, limited to top 3 qualifying formations.
    """
    formations_df = extract_team_formations(season, team)
    if formations_df.empty:
        return pd.DataFrame(columns=["formation_str", "count", "pct"])

    # Count occurrences of each formation string
    counts = (
        formations_df
        .groupby("formation_str")
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
        .reset_index(drop=True)
    )

    # Apply threshold
    counts = counts[counts["count"] >= min_count].reset_index(drop=True)

    # Percentage of total formations
    total = counts["count"].sum()
    counts["pct"] = (counts["count"] / total * 100).round(1) if total > 0 else 0.0

    # Return top 3
    return counts.head(3).reset_index(drop=True)


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2 — PLOTLY PITCH FIGURE
# ═══════════════════════════════════════════════════════════════════════════════

# Visual palette
_PITCH_BG       = "#1b2838"
_LINE_COLOR     = "rgba(255, 255, 255, 0.15)"
_LINE_WIDTH     = 1.2
_DOT_RED        = "#8a1f33"          # bright red for outfield
_DOT_GK         = "#3cb371"          # green for goalkeeper
_GLOW_RED       = "rgba(230, 57, 70, 0.22)"
_GLOW_GK        = "rgba(60, 179, 113, 0.22)"


def build_formation_pitch_figure(
    formation_str: str,
    count: int = 0,
    pct: float = 0.0,
) -> go.Figure:
    """
    Build a Plotly figure showing a formation on a simplified football pitch.

    Key design decisions for reliable rendering in Dash:
      • ALL shapes use layer="below" so traces are always visible
      • No scaleanchor / scaleratio — avoids plot-area collapse in flex containers
      • Explicit width + height for predictable sizing
      • Simple scatter traces with high-contrast colours

    Parameters
    ----------
    formation_str : str   e.g. '4-3-3'
    count : int           usage count (unused in figure itself)
    pct : float           usage percentage (unused in figure itself)

    Returns
    -------
    go.Figure
    """
    positions = _get_positions(formation_str)
    BELOW = "below"                       # constant for every shape

    fig = go.Figure()

    # ── Pitch markings (all layer="below" so they never cover traces) ──

    # Outer boundary
    fig.add_shape(type="rect", x0=0, y0=0, x1=100, y1=100,
                  line=dict(color=_LINE_COLOR, width=_LINE_WIDTH),
                  fillcolor=_PITCH_BG, layer=BELOW)

    # Centre line
    fig.add_shape(type="line", x0=50, y0=0, x1=50, y1=100,
                  line=dict(color=_LINE_COLOR, width=_LINE_WIDTH),
                  layer=BELOW)

    # Centre circle
    fig.add_shape(type="circle", x0=42, y0=42, x1=58, y1=58,
                  line=dict(color=_LINE_COLOR, width=_LINE_WIDTH),
                  layer=BELOW)

    # Centre spot
    fig.add_shape(type="circle", x0=49.3, y0=49.3, x1=50.7, y1=50.7,
                  fillcolor=_LINE_COLOR, line=dict(width=0),
                  layer=BELOW)

    # Penalty areas
    fig.add_shape(type="rect", x0=0, y0=22, x1=16.5, y1=78,
                  line=dict(color=_LINE_COLOR, width=_LINE_WIDTH),
                  layer=BELOW)
    fig.add_shape(type="rect", x0=83.5, y0=22, x1=100, y1=78,
                  line=dict(color=_LINE_COLOR, width=_LINE_WIDTH),
                  layer=BELOW)

    # 6-yard boxes
    fig.add_shape(type="rect", x0=0, y0=36, x1=5.5, y1=64,
                  line=dict(color=_LINE_COLOR, width=_LINE_WIDTH),
                  layer=BELOW)
    fig.add_shape(type="rect", x0=94.5, y0=36, x1=100, y1=64,
                  line=dict(color=_LINE_COLOR, width=_LINE_WIDTH),
                  layer=BELOW)

    # Penalty spots
    fig.add_shape(type="circle", x0=11.2, y0=49.3, x1=12.4, y1=50.7,
                  fillcolor=_LINE_COLOR, line=dict(width=0),
                  layer=BELOW)
    fig.add_shape(type="circle", x0=87.6, y0=49.3, x1=88.8, y1=50.7,
                  fillcolor=_LINE_COLOR, line=dict(width=0),
                  layer=BELOW)

    # Goal mouths
    fig.add_shape(type="rect", x0=-2.5, y0=44, x1=0, y1=56,
                  line=dict(color="rgba(255,255,255,0.20)", width=1.5),
                  fillcolor="rgba(255,255,255,0.04)",
                  layer=BELOW)
    fig.add_shape(type="rect", x0=100, y0=44, x1=102.5, y1=56,
                  line=dict(color="rgba(255,255,255,0.20)", width=1.5),
                  fillcolor="rgba(255,255,255,0.04)",
                  layer=BELOW)

    # ── Player markers ────────────────────────────────────────
    gk_pos = positions[0]
    outfield = positions[1:]

    # Glow layers (soft halo behind each dot)
    fig.add_trace(go.Scatter(
        x=[gk_pos[0]], y=[gk_pos[1]],
        mode="markers",
        marker=dict(size=26, color=_GLOW_GK, line=dict(width=0)),
        showlegend=False, hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=[p[0] for p in outfield],
        y=[p[1] for p in outfield],
        mode="markers",
        marker=dict(size=24, color=_GLOW_RED, line=dict(width=0)),
        showlegend=False, hoverinfo="skip",
    ))

    # Main dots — GK (green) and outfield (red)
    fig.add_trace(go.Scatter(
        x=[gk_pos[0]], y=[gk_pos[1]],
        mode="markers",
        marker=dict(
            size=14, color=_DOT_GK,
            line=dict(width=2, color="rgba(255,255,255,0.8)"),
        ),
        showlegend=False, hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=[p[0] for p in outfield],
        y=[p[1] for p in outfield],
        mode="markers",
        marker=dict(
            size=13, color=_DOT_RED,
            line=dict(width=2, color="rgba(255,255,255,0.8)"),
        ),
        showlegend=False, hoverinfo="skip",
    ))

    # ── Layout ────────────────────────────────────────────────
    # Square figure (300×300) with zero margins so the 110×110 data range
    # maps to equal pixels on both axes.  The pitch rect (0→100) then has
    # exactly 13.6 px of symmetrical padding on every side.
    # paper_bgcolor == plot_bgcolor == pitch-shape fill → seamless dark rect.
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=_PITCH_BG,
        plot_bgcolor=_PITCH_BG,
        xaxis=dict(
            range=[-5, 105],
            showgrid=False, zeroline=False,
            showticklabels=False, fixedrange=True,
            visible=False,
        ),
        yaxis=dict(
            range=[-5, 105],
            showgrid=False, zeroline=False,
            showticklabels=False, fixedrange=True,
            visible=False,
        ),
        width=300,
        height=300,
        autosize=False,
        margin=dict(l=0, r=0, t=0, b=0),
        dragmode=False,
    )

    return fig
