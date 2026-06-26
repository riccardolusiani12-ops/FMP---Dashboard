"""
dash_app/src/components/playing_style_evolution_cards.py
=========================================================
Style Evolution section for the Team Overview page.

12 small-multiple area+line charts — one per playing-style KPI — each showing
the selected team's within-Serie-A percentile rank for that KPI across all 5
available seasons (2021/22 through 2025/26). Placed immediately below the
Playing Style Wheel section.

Phase colours are imported from playing_style_cards — do not redefine them.
Theme helper _theme_dict is replicated here (same logic, different context).
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import dash_bootstrap_components as dbc
from dash import dcc, html

from src.styling.theme import FONT_FAMILY
from src.components.playing_style_cards import (
    DEFENCE_COLOR,
    POSSESSION_COLOR,
    PROGRESSION_COLOR,
    ATTACK_COLOR,
)


# ── KPI metadata ─────────────────────────────────────────────────────────────

KPI_LABELS = {
    "D1_pct": "Chance Prevention",
    "D2_pct": "Intensity",
    "D3_pct": "High Line",
    "P1_pct": "Deep Build-up",
    "P2_pct": "Press Resistance",
    "P3_pct": "Possession",
    "G1_pct": "Central Progression",
    "G2_pct": "Circulate",
    "G3_pct": "Field Tilt",
    "A1_pct": "Patient Attack",
    "A2_pct": "Shot Quality",
    "A3_pct": "Chance Creation",
}

KPI_ORDER = [
    "D1_pct", "D2_pct", "D3_pct",
    "P1_pct", "P2_pct", "P3_pct",
    "G1_pct", "G2_pct", "G3_pct",
    "A1_pct", "A2_pct", "A3_pct",
]

KPI_PHASE = {
    "D1_pct": "defence",    "D2_pct": "defence",    "D3_pct": "defence",
    "P1_pct": "possession", "P2_pct": "possession", "P3_pct": "possession",
    "G1_pct": "progression","G2_pct": "progression","G3_pct": "progression",
    "A1_pct": "attack",     "A2_pct": "attack",     "A3_pct": "attack",
}

_PHASE_COLOR = {
    "defence":    DEFENCE_COLOR,
    "possession": POSSESSION_COLOR,
    "progression":PROGRESSION_COLOR,
    "attack":     ATTACK_COLOR,
}


# ── Theme ─────────────────────────────────────────────────────────────────────

def _theme_dict(theme: str) -> dict:
    if theme == "light":
        return {
            "font":     "#1a1a2e",
            "muted":    "#718096",
            "grid":     "rgba(0,0,0,0.10)",
            "paper_bg": "#ffffff",
            "plot_bg":  "#ffffff",
        }
    return {
        "font":     "#f0f0f0",
        "muted":    "#8899aa",
        "grid":     "rgba(255,255,255,0.12)",
        "paper_bg": "rgba(0,0,0,0)",
        "plot_bg":  "rgba(0,0,0,0)",
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _short_season(season_str: str) -> str:
    """'2021/2022' → '21/22'."""
    parts = season_str.replace("-", "/").split("/")
    return f"{parts[0][2:]}/{parts[1][2:]}"


# ── Figure builder ────────────────────────────────────────────────────────────

def _build_evolution_figure(team: str, df_all: pd.DataFrame,
                             theme: str) -> go.Figure:
    """Build the 4×3 small-multiple subplot figure."""
    t = _theme_dict(theme)

    seasons = df_all["season"].tolist()
    x_labels = [_short_season(s) for s in seasons]

    fig = make_subplots(
        rows=4, cols=3,
        subplot_titles=[KPI_LABELS[k] for k in KPI_ORDER],
        shared_xaxes=False,
        shared_yaxes=False,
        vertical_spacing=0.10,
        horizontal_spacing=0.08,
    )

    for idx, kpi in enumerate(KPI_ORDER):
        row = idx // 3 + 1
        col = idx % 3 + 1
        phase = KPI_PHASE[kpi]
        color = _PHASE_COLOR[phase]
        fill_color = _hex_to_rgba(color, 0.25)

        y_vals = df_all[kpi].tolist() if kpi in df_all.columns else [0] * len(seasons)

        # Filled area background
        fig.add_trace(
            go.Scatter(
                x=x_labels,
                y=y_vals,
                mode="none",
                fill="tozeroy",
                fillcolor=fill_color,
                showlegend=False,
                hoverinfo="skip",
            ),
            row=row, col=col,
        )

        # Line with labelled markers
        fig.add_trace(
            go.Scatter(
                x=x_labels,
                y=y_vals,
                mode="lines+markers+text",
                line=dict(color=color, width=2),
                marker=dict(
                    symbol="circle",
                    size=24,
                    color=color,
                    line=dict(color=color, width=0),
                ),
                text=[str(int(round(v))) if v is not None else "" for v in y_vals],
                textposition="middle center",
                textfont=dict(color="white", size=10, family=FONT_FAMILY),
                showlegend=False,
                hovertemplate="%{x}: %{y:.0f}<extra></extra>",
            ),
            row=row, col=col,
        )

    # Apply axis styling to every subplot
    for idx in range(len(KPI_ORDER)):
        axis_num = "" if idx == 0 else str(idx + 1)
        fig.update_layout(**{
            f"xaxis{axis_num}": dict(
                tickmode="array",
                tickvals=x_labels,
                ticktext=x_labels,
                tickfont=dict(size=9, color=t["muted"]),
                showgrid=False,
                fixedrange=True,
            ),
            f"yaxis{axis_num}": dict(
                range=[0, 99],
                tickvals=[0, 25, 50, 75, 99],
                ticktext=["0", "25", "50", "75", "99"],
                tickfont=dict(size=9, color=t["muted"]),
                gridcolor=t["grid"],
                showgrid=True,
                zeroline=False,
                fixedrange=True,
            ),
        })

    # Style subplot title annotations
    for ann in fig.layout.annotations:
        ann.font.size = 11
        ann.font.color = t["font"]

    fig.update_layout(
        height=900,
        paper_bgcolor=t["paper_bg"],
        plot_bgcolor=t["plot_bg"],
        font=dict(family=FONT_FAMILY, color=t["font"]),
        margin=dict(l=40, r=20, t=60, b=20),
        showlegend=False,
    )

    return fig


# ── Public card ───────────────────────────────────────────────────────────────

def style_evolution_card(team: str, df_all: pd.DataFrame,
                          theme: str = "dark") -> html.Div:
    """
    Full Style Evolution section card.
    df_all: output of load_playing_style_all_seasons(team) —
            one row per season, columns season + 12 _pct columns.
    """
    fig = _build_evolution_figure(team, df_all, theme)

    header = html.Div(
        [
            html.Div(
                [html.I(className="bi bi-graph-up"), html.Span("STYLE PROFILE")],
                className="ds-eyebrow",
            ),
            html.H4("Style Evolution", className="ds-title"),
            html.P(
                "Percentile rank per season across all five Serie A seasons — "
                "within-league comparison",
                className="ds-sub",
            ),
        ],
        className="ds-header",
    )

    return html.Div(
        [
            header,
            dcc.Graph(
                figure=fig,
                config={"displayModeBar": False, "responsive": True},
                style={"width": "100%"},
            ),
        ],
        className="chart-section",
    )
