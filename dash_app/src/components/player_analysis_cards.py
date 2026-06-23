"""
Player Analysis — Component / Layout Layer
===========================================
Renders the three sections of the Player Analysis module (inside Match Analysis):

  1. Possession Value   (PV overview KPIs, full-pitch event map, possession
                          sequence viewer, per-90 leaderboards)
  2. In Possession       (highlight cards + sortable/filterable KPI table + info modals)
  3. Out of Possession   (highlight cards + sortable/filterable KPI table + info modals)

Scoped to ONE match, BOTH teams.  Component ID prefix: "mp-" (Match Player) — verified
non-colliding with "ma-", "opponent", "opp-season-", "player-analysis-" (old tab).

Visual conventions reused: draw_pitch() (pitch_utils), kpi_card() (kpis),
create_datatable() (tables), build_unified_modal() (ui_components), and the chain
node/connector pattern from buildup_cards (_chain_event_node/_chain_connector) as the
basis for the sequence viewer.
"""

from __future__ import annotations

from typing import Any, Dict, List

import dash_bootstrap_components as dbc
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import dcc, html

from src.analytics.player_analysis import (
    KPI_DEFINITIONS,
    MIN_MINUTES_FOR_PER90,
    build_possession_sequence,
)
from src.components.buildup_cards import _chain_connector, _chain_event_node
from src.styling.pitch_utils import draw_pitch
from src.styling.ui_components import build_unified_modal, ds_header
from src.team_mapping import canonical_name, logo_url
from src.utils.pv_model import PossessionValueModel

PREFIX = "mp"

# Team colour assignment — first team green-ish, second team orange-ish; logos carry
# the real identity, colours just separate the two teams on charts.
TEAM_COLORS = ["#22c55e", "#f59e0b"]

POS_COLOR = "#22c55e"   # value added
NEG_COLOR = "#ef4444"   # value lost


# ═══════════════════════════════════════════════════════════════════════════════
# SHARED HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _team_badge(team: str) -> html.Span:
    return html.Span(
        [
            html.Img(src=logo_url(canonical_name(team)),
                     style={"height": "18px", "marginRight": "6px",
                            "verticalAlign": "middle"}),
            html.Span(canonical_name(team), style={"verticalAlign": "middle"}),
        ],
    )


def _empty_section(msg: str) -> html.Div:
    return html.P(msg, className="text-muted",
                  style={"padding": "2rem", "textAlign": "center"})


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — POSSESSION VALUE
# ═══════════════════════════════════════════════════════════════════════════════

def _pv_overview_cards(pva: pd.DataFrame, team: str) -> dbc.Row:
    """Total Offensive + Defensive PVA for the SELECTED team (two numbers)."""
    off = pva["off_pva"].sum() if pva is not None and not pva.empty else 0.0
    deff = pva["def_pva"].sum() if pva is not None and not pva.empty else 0.0
    return dbc.Row([
        dbc.Col(
            dbc.Card(dbc.CardBody([
                html.Div(_team_badge(team), className="mb-2",
                         style={"fontSize": "0.9rem", "fontWeight": "600",
                                "color": "var(--text-primary)"}),
                html.Div([
                    html.Div([
                        html.Div("Offensive PVA", className="text-muted",
                                 style={"fontSize": "0.72rem"}),
                        html.H3(f"{off:+.2f}", className="mb-0 text-success fw-bold"),
                    ], style={"flex": "1"}),
                    html.Div([
                        html.Div("Defensive PVA", className="text-muted",
                                 style={"fontSize": "0.72rem"}),
                        html.H3(f"{deff:+.2f}", className="mb-0 fw-bold",
                                style={"color": "var(--primary-light)"}),
                    ], style={"flex": "1"}),
                ], className="d-flex"),
            ]), className="border-0 h-100",
                style={"backgroundColor": "rgba(44,62,80,0.5)"}),
            xs=12, md=8, lg=6, className="mb-3",
        ),
    ], className="g-3")


def _pv_event_map(event_map: pd.DataFrame, team: str) -> dcc.Graph:
    """Full-pitch scatter of the SELECTED team's scored events, by PV delta."""
    fig = go.Figure()
    draw_pitch(fig, theme="dark", half=None, height=460,
               title=f"Event Map — {canonical_name(team)} Possession Value Added",
               show_legend=False)

    if event_map is None or event_map.empty:
        return dcc.Graph(figure=fig, config={"displayModeBar": False})

    em = event_map.copy()
    mag = em["pv_delta"].abs()
    max_mag = float(mag.max()) or 1.0
    sizes = 6 + (mag / max_mag) * 22
    colors = [POS_COLOR if d >= 0 else NEG_COLOR for d in em["pv_delta"]]

    fig.add_trace(go.Scatter(
        x=em["x"], y=em["y"], mode="markers",
        marker=dict(
            size=sizes, color=colors,
            line=dict(width=1.2, color="rgba(255,255,255,0.55)"),
            opacity=0.78,
        ),
        customdata=np.stack([
            em["player_name"], em["minute"], em["event_type"], em["pv_delta"],
        ], axis=-1),
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Min %{customdata[1]} · %{customdata[2]}<br>"
            "PV Δ: %{customdata[3]:+.4f}<extra></extra>"
        ),
        showlegend=False,
    ))

    # Legend proxy for positive/negative.
    for label, col in (("Value added", POS_COLOR), ("Value lost", NEG_COLOR)):
        fig.add_trace(go.Scatter(
            x=[None], y=[None], mode="markers",
            marker=dict(size=10, color=col), name=label, showlegend=True,
        ))
    fig.update_layout(showlegend=True,
                      legend=dict(orientation="h", y=-0.04, x=0.5, xanchor="center"))
    return dcc.Graph(figure=fig, config={"displayModeBar": False})


def _swing_chips(swings: pd.DataFrame) -> html.Div:
    """Top-5 highest-swing possession quick-select chips."""
    chips = []
    top5 = swings.head(5)
    for i, (_, r) in enumerate(top5.iterrows()):
        chips.append(html.Button(
            [
                html.Span(f"#{i+1}", style={"fontWeight": "700", "marginRight": "5px"}),
                f"{canonical_name(r['team_name'])} {r['start_min']}' · Δ{r['swing']:.2f}",
            ],
            id={"type": f"{PREFIX}-swing-chip", "index": int(r["poss_id"])},
            n_clicks=0,
            className="btn btn-sm me-2 mb-2",
            style={"background": "rgba(138,31,51,0.18)", "color": "var(--text-primary)",
                   "border": "1px solid var(--primary-light)", "fontSize": "0.72rem"},
        ))
    return html.Div(chips, className="d-flex flex-wrap")


def _sequence_dropdown(swings: pd.DataFrame) -> dcc.Dropdown:
    opts = [
        {"label": f"{canonical_name(r['team_name'])} — {r['start_min']}' "
                  f"({r['n_events']} events, swing {r['swing']:.2f})",
         "value": int(r["poss_id"])}
        for _, r in swings.iterrows()
    ]
    default = int(swings.iloc[0]["poss_id"]) if not swings.empty else None
    return dcc.Dropdown(
        id=f"{PREFIX}-sequence-dropdown", options=opts, value=default,
        clearable=False, className="dash-dropdown-dark",
        style={"maxWidth": "520px"},
    )


def render_sequence_view(df: pd.DataFrame, poss_id: int, pv) -> html.Div:
    """Chain (nodes/connectors) on the left + cumulative-PV step chart on the right."""
    seq = build_possession_sequence(df, poss_id, pv)
    nodes = seq.get("nodes", [])
    if not nodes:
        return _empty_section("No scored on-ball events in this possession.")

    # ── Chain row (node + connector + node + …) ──
    chain_children: List[Any] = []
    for i, n in enumerate(nodes):
        evt = {"is_team": n["is_team"], "event_type": n["event_type"], "player": n["player"]}
        node = _chain_event_node(evt, i, len(nodes))
        # PVA badge under each node (signed, colour-coded).
        pva_badge = html.Div(
            f"{n['pva']:+.3f}",
            style={"fontSize": "0.6rem", "fontWeight": "700", "textAlign": "center",
                   "color": POS_COLOR if n["pva"] >= 0 else NEG_COLOR},
        )
        chain_children.append(html.Div([node, pva_badge],
                                       style={"display": "flex",
                                              "flexDirection": "column",
                                              "alignItems": "center"}))
        if i < len(nodes) - 1:
            chain_children.append(_chain_connector(
                {"event_type": nodes[i + 1]["event_type"]}))

    chain = html.Div(
        chain_children,
        style={"display": "flex", "alignItems": "flex-start", "overflowX": "auto",
               "padding": "0.75rem 0.5rem", "gap": "2px"},
    )

    # ── Cumulative-PV step chart ──
    cum = [n["cum"] for n in nodes]
    labels = [f"{i+1}. {n['player']}" for i, n in enumerate(nodes)]
    step = go.Figure()
    step.add_trace(go.Scatter(
        x=list(range(1, len(cum) + 1)), y=cum, mode="lines+markers",
        line=dict(shape="hv", color="var(--primary-light)", width=2),
        marker=dict(size=6, color=["#22c55e" if c >= 0 else "#ef4444" for c in cum]),
        customdata=labels,
        hovertemplate="%{customdata}<br>Cumulative PV: %{y:.4f}<extra></extra>",
    ))
    step.add_hline(y=0, line=dict(color="rgba(255,255,255,0.2)", dash="dot"))
    step.update_layout(
        height=300, template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=40, r=20, t=30, b=30),
        title=dict(text="Cumulative Possession Value", font=dict(size=13)),
        xaxis=dict(title="Action #", showgrid=False),
        yaxis=dict(title="Cumulative PV", showgrid=True,
                   gridcolor="rgba(255,255,255,0.06)"),
    )

    # ── Pitch trace of the possession path ──
    pitch = go.Figure()
    draw_pitch(pitch, theme="dark", half=None, height=300, show_legend=False,
               title=f"Possession Path — {canonical_name(seq.get('team_name',''))}")
    xs = [n["x"] for n in nodes]
    ys = [n["y"] for n in nodes]
    pitch.add_trace(go.Scatter(
        x=xs, y=ys, mode="lines+markers+text",
        line=dict(color="var(--primary-light)", width=2),
        marker=dict(size=12, color=["#22c55e" if n["pva"] >= 0 else "#ef4444" for n in nodes],
                    line=dict(width=1, color="#fff")),
        text=[str(i + 1) for i in range(len(nodes))],
        textposition="middle center", textfont=dict(size=8, color="#fff"),
        customdata=np.stack([[n["player"] for n in nodes],
                             [n["event_type"] for n in nodes],
                             [n["pva"] for n in nodes]], axis=-1),
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<br>"
                      "PV Δ %{customdata[2]:+.4f}<extra></extra>",
    ))

    return html.Div([
        html.Div(chain, className="mb-3",
                 style={"background": "rgba(15,25,35,0.4)", "borderRadius": "8px"}),
        dbc.Row([
            dbc.Col(dcc.Graph(figure=pitch, config={"displayModeBar": False}),
                    xs=12, lg=6),
            dbc.Col(dcc.Graph(figure=step, config={"displayModeBar": False}),
                    xs=12, lg=6),
        ]),
    ])


def _leaderboard_figure(pva: pd.DataFrame, minutes: Dict[str, Any],
                        metric: str, team: str, show_bottom: bool) -> go.Figure:
    """Horizontal bar chart of per-90 PVA for one metric (off/def/total).

    ``team`` is the selected team (single-team scope); used only for bar colour.
    """
    if pva is None or pva.empty:
        return go.Figure()

    df = pva.copy()
    df["minutes"] = df["player_name"].map(lambda p: minutes.get(p, {}).get("minutes", 0.0))
    # Per-90 normalisation; guard divide-by-zero.
    df["per90"] = np.where(df["minutes"] > 0,
                           df[metric] / df["minutes"] * 90.0, 0.0)
    df["low_min"] = df["minutes"] < MIN_MINUTES_FOR_PER90

    df = df.sort_values("per90", ascending=False)
    if show_bottom:
        view = pd.concat([df.head(8), df.tail(5)]).drop_duplicates("player_name")
    else:
        view = df.head(12)
    view = view.sort_values("per90")

    base_color = TEAM_COLORS[0]  # single-team scope — one consistent colour
    colors = [_dim(base_color) if r["low_min"] else base_color
              for _, r in view.iterrows()]

    fig = go.Figure(go.Bar(
        x=view["per90"], y=view["player_name"], orientation="h",
        marker=dict(color=colors),
        customdata=np.stack([view[metric], view["minutes"], view["team_name"]], axis=-1),
        hovertemplate=("<b>%{y}</b><br>Per-90: %{x:.3f}<br>"
                       "Raw %{customdata[0]:+.3f} · %{customdata[1]:.0f} min<br>"
                       "%{customdata[2]}<extra></extra>"),
    ))
    fig.update_layout(
        height=max(320, 26 * len(view) + 80), template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=20, t=20, b=40),
        xaxis=dict(title="PVA per 90", showgrid=True,
                   gridcolor="rgba(255,255,255,0.06)", zeroline=True,
                   zerolinecolor="rgba(255,255,255,0.2)"),
        yaxis=dict(automargin=True),
    )
    return fig


def _dim(hex_color: str) -> str:
    """Return an rgba string at low opacity for low-minutes flagging."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},0.35)"


def _leaderboards_block(pva: pd.DataFrame, minutes: Dict[str, Any],
                        team: str) -> html.Div:
    metrics = [("off_pva", "Offensive PVA"), ("def_pva", "Defensive PVA"),
               ("total_pva", "Total PVA")]
    cols = []
    for key, label in metrics:
        cols.append(dbc.Col([
            html.Div(label, className="mb-1",
                     style={"fontWeight": "600", "fontSize": "0.85rem",
                            "color": "var(--text-primary)"}),
            dcc.Graph(
                id=f"{PREFIX}-leaderboard-{key}",
                figure=_leaderboard_figure(pva, minutes, key, team, False),
                config={"displayModeBar": False},
            ),
        ], xs=12, lg=4))
    return html.Div([
        html.Div([
            dbc.Checklist(
                options=[{"label": " Show bottom (least valuable / most costly) players",
                          "value": "bottom"}],
                value=[], id=f"{PREFIX}-leaderboard-bottom-toggle",
                switch=True, inline=True,
                style={"fontSize": "0.8rem"},
            ),
        ], className="mb-2"),
        dbc.Row(cols, className="g-3"),
        html.P(
            f"Bars show PVA normalised per 90 minutes. Players with < "
            f"{int(MIN_MINUTES_FOR_PER90)} minutes are dimmed — per-90 extrapolation "
            f"from few minutes is unreliable. Hover any bar for raw totals + minutes.",
            className="text-muted mt-2", style={"fontSize": "0.72rem"},
        ),
    ])


def _section_possession_value(bundle: Dict[str, Any]) -> html.Div:
    team = bundle.get("selected_team", "")
    pva = bundle["pva"]
    swings = bundle["swings"]

    sep = html.Hr(style={"borderColor": "var(--border-light)", "margin": "1.5rem 0"})

    if pva is None or pva.empty:
        return html.Div([
            ds_header("Player Analysis — Possession Value", "bi-graph-up-arrow",
                      "Possession Value",
                      f"Per-player value added for {canonical_name(team)} (ML model)."),
            _empty_section(f"No scored events found for {canonical_name(team)} "
                           "in this match."),
        ])

    seq_default = (
        render_sequence_view(bundle["df"], int(swings.iloc[0]["poss_id"]),
                             PossessionValueModel.get_instance())
        if not swings.empty else _empty_section("No multi-action possessions found.")
    )

    return html.Div([
        ds_header("Player Analysis — Possession Value", "bi-graph-up-arrow",
                  "Possession Value",
                  f"Per-player value added in and out of possession for "
                  f"{canonical_name(team)} (ML model)."),

        # 1 — Match PV overview (selected team only)
        html.H6("Team PV Overview", className="text-light mb-2"),
        _pv_overview_cards(pva, team),
        _pv_event_map(bundle["event_map"], team),
        sep,

        # 2 — Possession sequence viewer (selected team's possessions only)
        html.H6("Possession Sequence Viewer", className="text-light mb-2"),
        html.P(f"{canonical_name(team)}'s highest-swing possessions "
               "(sum of |PV Δ| across the chain). Pick a chip or browse all.",
               className="text-muted", style={"fontSize": "0.75rem"}),
        _swing_chips(swings),
        html.Div(_sequence_dropdown(swings), className="mb-3"),
        dcc.Loading(html.Div(seq_default, id=f"{PREFIX}-sequence-view"),
                    type="circle", color="#8a1f33"),
        sep,

        # 3 — Leaderboards (selected team's players)
        html.H6("Player Leaderboards (per 90)", className="text-light mb-2"),
        _leaderboards_block(pva, bundle["minutes"], team),
    ], className="buildup-card ma-card")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2 + 3 — IN / OUT OF POSSESSION TABLES
# ═══════════════════════════════════════════════════════════════════════════════

# Per-KPI card config (Phase 3 redesign): (metric_key, card label).
# One card per KPI; each shows a player-ranking bar chart and opens a modal with
# the full numeric breakdown.  Order = card grid order.  KPI scope (DIRECT/REUSE/
# NEW) is unchanged from the original build — this is presentation only.
IN_POSSESSION_KPIS = [
    ("passes_completed", "Passes Completed"),
    ("pass_completion_pct", "Pass Completion %"),
    ("ball_progressions", "Ball Progressions"),
    ("line_breaks_completed", "Line Breaks"),
    ("switches_of_play", "Switches of Play"),
    ("crosses_completed", "Crosses Completed"),
    ("take_ons", "Take-Ons"),
    ("attempts_at_goal", "Attempts at Goal"),
    ("goals", "Goals"),
]

OUT_POSSESSION_KPIS = [
    ("tackles_won", "Tackles Won"),
    ("tackles_made", "Tackles Made"),
    ("interceptions", "Interceptions"),
    ("blocks", "Blocks"),
    ("clearances", "Clearances"),
    ("aerial_duels_won", "Aerial Duels Won"),
    ("possession_regains", "Possession Regains"),
]

# Companion/secondary columns shown in each KPI's breakdown modal (for context),
# keyed by the card metric.  e.g. completion % also shows attempts/completed.
KPI_MODAL_COMPANIONS = {
    "passes_completed": ["passes_attempted", "pass_completion_pct"],
    "pass_completion_pct": ["passes_attempted", "passes_completed"],
    "line_breaks_completed": ["line_breaks_attempted", "line_break_pct"],
    "crosses_completed": ["crosses_attempted"],
    "tackles_won": ["tackles_made"],
    "aerial_duels_won": ["aerial_duels_total"],
}

_COL_SHORT = {
    "passes_attempted": "Att", "passes_completed": "Cmp",
    "pass_completion_pct": "%", "line_breaks_attempted": "LB Att",
    "line_breaks_completed": "LB Cmp", "line_break_pct": "LB %",
    "crosses_attempted": "Cross Att", "crosses_completed": "Cross Cmp",
    "tackles_made": "Made", "tackles_won": "Won",
    "aerial_duels_total": "Contested", "aerial_duels_won": "Won",
}


def _highlight_cards(kpi_df: pd.DataFrame, highlights: List[tuple]) -> dbc.Row:
    """highlights: list of (metric, label, icon, color)."""
    from src.components.kpis import kpi_card
    cards = []
    for metric, label, icon, color in highlights:
        if kpi_df.empty or metric not in kpi_df.columns or kpi_df[metric].max() == 0:
            cards.append(kpi_card(label, "—", "no data", icon=icon, color=color))
            continue
        top = kpi_df.sort_values(metric, ascending=False).iloc[0]
        cards.append(kpi_card(
            label, str(int(top[metric]) if float(top[metric]).is_integer()
                       else round(float(top[metric]), 1)),
            subtitle=canonical_name(top["player_name"]), icon=icon, color=color,
        ))
    return dbc.Row(cards, className="g-3")


def _kpi_rank_figure(kpi_df: pd.DataFrame, metric: str, top_n: int = 8) -> go.Figure:
    """Horizontal bar chart ranking players on one metric (flat list, desc)."""
    fig = go.Figure()
    if kpi_df is None or kpi_df.empty or metric not in kpi_df.columns:
        fig.update_layout(height=40, template="plotly_dark",
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          margin=dict(l=0, r=0, t=0, b=0))
        return fig

    d = kpi_df[kpi_df[metric] > 0].copy()
    d["player"] = d["player_name"].map(canonical_name)
    d = d.sort_values(metric, ascending=False).head(top_n).sort_values(metric)

    is_pct = metric.endswith("_pct")
    fmt = "%{x:.1f}%" if is_pct else "%{x:.0f}"
    fig.add_trace(go.Bar(
        x=d[metric], y=d["player"], orientation="h",
        marker=dict(color=TEAM_COLORS[0]),
        text=d[metric].map(lambda v: f"{v:.1f}%" if is_pct else f"{int(v)}"),
        textposition="auto", textfont=dict(size=10),
        hovertemplate="<b>%{y}</b><br>" + fmt + "<extra></extra>",
    ))
    fig.update_layout(
        height=max(150, 24 * len(d) + 30), template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=4, r=10, t=4, b=20),
        xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.06)",
                   showticklabels=False),
        yaxis=dict(automargin=True, tickfont=dict(size=10)),
    )
    return fig


def _kpi_card(kpi_df: pd.DataFrame, metric: str, label: str,
              section: str) -> dbc.Col:
    """One KPI card: title + info-icon + ranking bar chart, clickable for modal."""
    leader = "—"
    if kpi_df is not None and not kpi_df.empty and metric in kpi_df.columns \
            and kpi_df[metric].max() > 0:
        top = kpi_df.sort_values(metric, ascending=False).iloc[0]
        is_pct = metric.endswith("_pct")
        val = f"{top[metric]:.1f}%" if is_pct else f"{int(top[metric])}"
        leader = f"{canonical_name(top['player_name'])} · {val}"

    return dbc.Col(
        html.Div(
            dbc.Card(dbc.CardBody([
                html.Div([
                    html.Span(label, style={"fontWeight": "600", "fontSize": "0.82rem",
                                            "color": "var(--text-primary)"}),
                    html.I(className="bi bi-info-circle",
                           style={"color": "var(--text-muted)", "fontSize": "0.75rem"},
                           title="Click card for definition + breakdown"),
                ], className="d-flex align-items-center justify-content-between mb-1"),
                html.Div(leader, className="text-muted mb-2",
                         style={"fontSize": "0.7rem"}),
                dcc.Graph(figure=_kpi_rank_figure(kpi_df, metric),
                          config={"displayModeBar": False}),
                html.Div(
                    [html.I(className="bi bi-table me-1"), "Full breakdown"],
                    className="text-muted",
                    style={"fontSize": "0.68rem", "marginTop": "4px",
                           "textAlign": "right", "color": "var(--primary-light)"},
                ),
            ]),
                className="border-0 h-100",
                style={"backgroundColor": "rgba(44,62,80,0.5)"}),
            id={"type": f"{PREFIX}-kpi-card", "section": section, "index": metric},
            n_clicks=0,
            style={"cursor": "pointer", "height": "100%"},
        ),
        xs=12, md=6, lg=4, className="mb-3",
    )


def _kpi_cards_grid(kpi_df: pd.DataFrame, kpi_list: List[tuple],
                    section: str) -> html.Div:
    if kpi_df is None or kpi_df.empty:
        return _empty_section("No player data for this match.")
    cards = [_kpi_card(kpi_df, m, lbl, section) for m, lbl in kpi_list]
    return dbc.Row(cards, className="g-3")


def build_kpi_breakdown_modal_body(kpi_df: pd.DataFrame, minutes: Dict[str, Any],
                                   metric: str) -> html.Div:
    """Full numeric breakdown for one KPI: definition + ranked table (all players)."""
    meta = KPI_DEFINITIONS.get(metric, {})
    if kpi_df is None or kpi_df.empty or metric not in kpi_df.columns:
        return html.Div(_empty_section("No data for this metric."))

    companions = KPI_MODAL_COMPANIONS.get(metric, [])
    cols = [metric] + [c for c in companions if c in kpi_df.columns]
    d = kpi_df.copy()
    d["player"] = d["player_name"].map(canonical_name)
    d["min"] = d["player_name"].map(lambda p: minutes.get(p, {}).get("minutes", 0.0))
    d = d.sort_values(metric, ascending=False)

    def _fmt(col, v):
        return f"{v:.1f}%" if col.endswith("_pct") else (
            f"{v:.1f}" if isinstance(v, float) and not float(v).is_integer()
            else f"{int(v)}")

    header = html.Div(
        [html.Span("Player", style={"flex": "1", "fontSize": "0.72rem",
                                    "color": "#8899aa"})]
        + [html.Span(_COL_SHORT.get(c, c.replace("_", " ").title()),
                     style={"minWidth": "4.5rem", "textAlign": "right",
                            "fontSize": "0.72rem", "color": "#8899aa"})
           for c in cols]
        + [html.Span("Min", style={"minWidth": "3.5rem", "textAlign": "right",
                                   "fontSize": "0.72rem", "color": "#8899aa"})],
        style={"display": "flex", "padding": "6px 10px",
               "borderBottom": "1px solid rgba(255,255,255,0.15)"},
    )
    rows = []
    for _, r in d.iterrows():
        if all((r.get(c, 0) or 0) == 0 for c in cols):
            continue
        rows.append(html.Div(
            [html.Span(r["player"], style={"flex": "1", "fontSize": "0.85rem",
                                           "color": "var(--text-primary)"})]
            + [html.Span(_fmt(c, r.get(c, 0)),
                         style={"minWidth": "4.5rem", "textAlign": "right",
                                "fontSize": "0.85rem", "color": "var(--text-secondary)"})
               for c in cols]
            + [html.Span(f"{r['min']:.0f}",
                         style={"minWidth": "3.5rem", "textAlign": "right",
                                "fontSize": "0.85rem", "color": "#8899aa"})],
            style={"display": "flex", "padding": "6px 10px", "alignItems": "center",
                   "borderBottom": "1px solid rgba(255,255,255,0.05)"},
        ))

    return html.Div([
        html.P([html.Span(f"[{meta.get('class','')}] ",
                          style={"fontWeight": "700",
                                 "color": "var(--primary-light)"}),
                meta.get("def", "")],
               style={"fontSize": "0.8rem", "color": "var(--text-secondary)",
                      "marginBottom": "0.75rem"}),
        html.Div([header, *rows] if rows else _empty_section("No players recorded this metric."),
                 style={"maxHeight": "440px", "overflowY": "auto",
                        "borderRadius": "6px",
                        "border": "1px solid rgba(255,255,255,0.07)"}),
    ])


def _section_in_possession(bundle: Dict[str, Any]) -> html.Div:
    kpi = bundle["in_possession"]
    highlights = [
        ("passes_completed", "Top Passer", "bi-arrow-left-right", "success"),
        ("ball_progressions", "Top Progressor", "bi-graph-up-arrow", "info"),
        ("crosses_completed", "Top Crosser", "bi-arrow-up-right", "warning"),
        ("attempts_at_goal", "Most Shots", "bi-bullseye", "danger"),
    ]
    team = bundle.get("selected_team", "")
    return html.Div([
        ds_header("Player Analysis — In Possession", "bi-arrow-left-right",
                  "In Possession",
                  f"On-ball player KPIs for {canonical_name(team)}. "
                  "One card per metric — click any card for the full breakdown."),
        _highlight_cards(kpi, highlights),
        html.Div(style={"height": "1.25rem"}),
        _kpi_cards_grid(kpi, IN_POSSESSION_KPIS, "in"),
    ], className="buildup-card ma-card")


def _section_out_possession(bundle: Dict[str, Any]) -> html.Div:
    kpi = bundle["out_possession"]
    highlights = [
        ("tackles_won", "Top Tackler", "bi-shield-fill", "success"),
        ("interceptions", "Top Interceptor", "bi-sign-stop", "info"),
        ("aerial_duels_won", "Top in Air", "bi-arrow-up", "warning"),
        ("possession_regains", "Top Regains", "bi-arrow-repeat", "danger"),
    ]
    team = bundle.get("selected_team", "")
    return html.Div([
        ds_header("Player Analysis — Out of Possession", "bi-shield-fill",
                  "Out of Possession",
                  f"Defensive player KPIs for {canonical_name(team)}. "
                  "One card per metric — click any card for the full breakdown."),
        _highlight_cards(kpi, highlights),
        html.Div(style={"height": "1.25rem"}),
        _kpi_cards_grid(kpi, OUT_POSSESSION_KPIS, "out"),
    ], className="buildup-card ma-card")


# ═══════════════════════════════════════════════════════════════════════════════
# TOP-LEVEL CARD (entry point from _analysis_view)
# ═══════════════════════════════════════════════════════════════════════════════

def _scope_to_team(bundle: Dict[str, Any], team: str) -> Dict[str, Any]:
    """
    Return a shallow copy of *bundle* with player-attribution frames filtered to
    *team* (matched canonically).  The PV computation itself is NOT re-scoped —
    every event was already scored over both teams, so the team's defensive
    actions during the opponent's possessions remain attributed here.  Only the
    final display frames are filtered.

    Scoping rules:
      • pva / event_map / in_possession / out_possession → rows for the team's
        own players (team_name matches).
      • swings → possessions OWNED by the team (poss-team == team), so the
        sequence viewer + chips never surface the opponent's attacks.
    """
    if not team:
        return bundle
    tcanon = canonical_name(team)

    def _filt(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty or "team_name" not in df.columns:
            return df
        mask = df["team_name"].map(lambda t: canonical_name(str(t)) == tcanon)
        return df[mask].reset_index(drop=True)

    scoped = dict(bundle)
    scoped["selected_team"] = tcanon
    scoped["pva"] = _filt(bundle.get("pva"))
    scoped["event_map"] = _filt(bundle.get("event_map"))
    scoped["in_possession"] = _filt(bundle.get("in_possession"))
    scoped["out_possession"] = _filt(bundle.get("out_possession"))
    scoped["swings"] = _filt(bundle.get("swings"))
    return scoped


def player_analysis_card(match_csv, team: str = "") -> html.Div:
    """Render the Player Analysis module for a single match, scoped to *team*."""
    from src.analytics.player_analysis import analyse_player_analysis

    bundle = analyse_player_analysis(match_csv)
    if not bundle.get("teams"):
        return html.Div(
            dbc.Alert("No event data available for this match.", color="warning"),
        )

    bundle = _scope_to_team(bundle, team)

    sep = html.Div(style={"height": "2rem"})
    return html.Div([
        # Carries the match CSV path + selected team so self-contained callbacks
        # can recompute and re-scope the cached bundle without re-iterating raw CSV.
        dcc.Store(id=f"{PREFIX}-match-store",
                  data={"csv": str(match_csv), "team": canonical_name(team) if team else ""}),
        _section_possession_value(bundle),
        sep,
        _section_in_possession(bundle),
        sep,
        _section_out_possession(bundle),
        # Shared KPI breakdown modal — opened by any In/Out KPI card click, filled
        # by callback with that metric's definition + ranked per-player table.
        build_unified_modal(
            f"{PREFIX}-kpi-modal", f"{PREFIX}-kpi-modal-title",
            f"{PREFIX}-kpi-modal-body", title="Metric Breakdown", size="lg",
        ),
    ])
