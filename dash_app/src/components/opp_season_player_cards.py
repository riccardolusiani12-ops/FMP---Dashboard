"""
Opponent Analysis — Season View: Player Analysis (season aggregate)
===================================================================
Season-aggregate Player Analysis for ONE selected team, reading the precomputed
``player_season_{season}.parquet`` (built by analytics/season_player_analysis.py).

Same underlying KPIs as the match-level Player Analysis (analytics/player_analysis.py),
aggregated across every match the team played, for the full squad.

CONTEXT (confirmed STOP-AND-ASK answers, all schema-backed):
  • Per-90 is the PRIMARY ranked number for every counting KPI; raw season total
    is shown on hover.  PVA uses per-90 too (off / def / total, kept separate).
  • Players with < 450' are DIMMED (never dropped) — `low_minutes` flag.
  • Each player carries a granular season `role_group` (GK/CB/FB/DM/CM/WM/AM/W/CF,
    or UNCL).  The position-ADJUSTED score is a within-role league percentile,
    shown alongside the per-90 number (computed here from the all-teams parquet).
  • Partial-season players carry a flag (featured < 50% of matchdays).
  • PVA consistency (σ of per-match PVA) available per player.

Component ID prefix: opp-season-player-  (verified no collision).
IDs introduced:
  opp-season-player-store
  opp-season-player-pos-filter            (role-group dropdown, applies to KPI grids)
  opp-season-player-kpi-card  {type, section, index}   (pattern-matching, clickable)
  opp-season-player-modal / -title / -body             (shared breakdown modal)
  opp-season-player-pva-{off,def,total}                (leaderboard graphs)
"""

from __future__ import annotations

import json
from typing import Any

import dash_bootstrap_components as dbc
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import dcc, html

from src.config import READY_DATA_DIR
from src.team_mapping import canonical_name
from src.styling.theme import COLORS_DARK
from src.styling.ui_components import build_unified_modal, ds_header
from src.utils.caching import cache_get, cache_set
from src.utils.logging import log

from src.analytics.player_analysis import KPI_DEFINITIONS
from src.analytics.season_player_analysis import (
    ROLE_GROUP_ORDER, UNCLASSIFIED, MIN_MINUTES_DIM, COUNT_KPIS, PCT_KPIS,
)

PREFIX = "opp-season-player"
BAR_COLOR = "#22c55e"
DIM_COLOR = "rgba(34,197,94,0.30)"
_HIGHLIGHT = COLORS_DARK["accent"]

ROLE_LABELS = {
    "GK": "Goalkeepers", "CB": "Centre-Backs", "FB": "Full-Backs",
    "DM": "Defensive Mids", "CM": "Central Mids", "WM": "Wide Mids",
    "AM": "Attacking Mids", "W": "Wingers", "CF": "Forwards",
    UNCLASSIFIED: "Unclassified",
}

# Per-KPI card config — same KPI scope as match-level, per-90 primary.
# (metric base column, card label).  The actual ranked value is the *_p90 column.
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
_PCT_SET = {c for c, _, _ in PCT_KPIS}

KPI_MODAL_COMPANIONS = {
    "passes_completed": ["passes_attempted", "pass_completion_pct"],
    "pass_completion_pct": ["passes_attempted", "passes_completed"],
    "line_breaks_completed": ["line_breaks_attempted", "line_break_pct"],
    "crosses_completed": ["crosses_attempted"],
    "tackles_won": ["tackles_made"],
    "aerial_duels_won": ["aerial_duels_total"],
}


# ═══════════════════════════════════════════════════════════════════════════════
# DATA LAYER
# ═══════════════════════════════════════════════════════════════════════════════

def _load_player_parquet(season: str) -> pd.DataFrame | None:
    """Load the all-teams season player parquet (cached)."""
    cache_key = f"opp_player_season_{season}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    path = READY_DATA_DIR / f"player_season_{season}.parquet"
    if not path.exists():
        log.warning("Player season parquet missing: %s — run precompute_season_players()", path.name)
        return None
    try:
        df = pd.read_parquet(path)
    except Exception as exc:
        log.error("Failed to read %s: %s", path.name, exc)
        return None
    cache_set(cache_key, df)
    return df


def _ranked_value(df: pd.DataFrame, metric: str) -> str:
    """The OBSERVED column shown to the user: raw per-90 for counts, raw % for %.

    This is the unshrunk number surfaced for transparency (cards/hover/modal).
    Ranking + percentiles use _rank_col() (the shrinkage-adjusted value) instead.
    """
    if metric in _PCT_SET:
        return metric
    p90 = f"{metric}_p90"
    return p90 if p90 in df.columns else metric


def _rank_col(df: pd.DataFrame, metric: str) -> str:
    """The column used to RANK and to compute within-role percentiles.

    For counting + PVA per-90 metrics this is the Empirical-Bayes *adjusted* per-90
    (``{metric}_p90_adj``) — minutes-weighted shrinkage toward the role mean, which
    is the actual fix for small-sample percentile inflation.  Percentage KPIs are
    already sample-size robust (sum(num)/sum(den)) and rank on their raw value.
    """
    if metric in _PCT_SET:
        return metric
    adj = f"{metric}_p90_adj"
    if adj in df.columns:
        return adj
    return _ranked_value(df, metric)  # graceful fallback (pre-shrinkage parquet)


def _add_role_percentiles(league_df: pd.DataFrame, metric: str) -> pd.DataFrame:
    """
    Add a within-role league percentile for *metric*'s ranked value.

    Percentile is computed off the shrinkage-ADJUSTED per-90 (_rank_col), across
    ALL league players sharing the same role_group (UNCL excluded — no comparable
    peer group).  Only players with minutes >= MIN_MINUTES_DIM contribute to and
    receive a percentile, so a 20-minute cameo does not define the distribution.
    """
    col = _rank_col(league_df, metric)
    out = league_df.copy()
    pct_col = f"__pctl_{metric}"
    out[pct_col] = np.nan
    qualified = out[(out["minutes"] >= MIN_MINUTES_DIM) & (out["role_group"] != UNCLASSIFIED)]
    for role, grp in qualified.groupby("role_group"):
        vals = grp[col].astype(float)
        if len(vals) < 3:
            continue
        ranks = vals.rank(pct=True) * 100
        out.loc[ranks.index, pct_col] = ranks.round(0)
    return out


def compute_season_players(season: str, team_name: str) -> dict:
    """Return season player data for one team + the league frame for percentiles."""
    league = _load_player_parquet(season)
    if league is None or league.empty:
        return {"season": season, "team": team_name, "team_df": pd.DataFrame(),
                "league_df": pd.DataFrame(), "n_matchdays": 0}

    target = canonical_name(team_name).lower()
    mask = league["team"].apply(lambda t: canonical_name(str(t)).lower() == target)
    team_df = league[mask].reset_index(drop=True)

    n_md = int(team_df["n_matchdays"].iloc[0]) if not team_df.empty else 0
    return {
        "season": season.replace("_", "/"),
        "team": canonical_name(team_name),
        "team_df": team_df,
        "league_df": league,
        "n_matchdays": n_md,
    }


def load_league_player_summary(season: str) -> pd.DataFrame | None:
    return _load_player_parquet(season)


# ═══════════════════════════════════════════════════════════════════════════════
# CHART + CARD HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _fmt_val(metric: str, v: float) -> str:
    if metric in _PCT_SET:
        return f"{v:.1f}%"
    return f"{v:.0f}" if float(v).is_integer() else f"{v:.1f}"


def _kpi_rank_figure(team_df: pd.DataFrame, league_df: pd.DataFrame,
                     metric: str, top_n: int = 8) -> go.Figure:
    """
    Horizontal bar chart ranking the team's players on *metric*'s per-90 value.
    Low-minutes players dimmed.  Hover shows raw season total, minutes, and the
    within-role league percentile (position-adjusted score).
    """
    fig = go.Figure()
    if team_df is None or team_df.empty:
        fig.update_layout(height=40, template="plotly_dark",
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          margin=dict(l=0, r=0, t=0, b=0))
        return fig

    rank_col = _rank_col(team_df, metric)     # adjusted per-90 (ranks the bars)
    obs_col = _ranked_value(team_df, metric)  # observed per-90 / raw % (hover)
    enriched = _add_role_percentiles(league_df, metric)
    # join percentile back onto team rows by (player) within this team
    pct_col = f"__pctl_{metric}"
    team = team_df.merge(
        enriched[["team", "player", pct_col]], on=["team", "player"], how="left",
    )

    d = team[team[rank_col].astype(float) > 0].copy()
    if d.empty:
        fig.update_layout(height=40, template="plotly_dark",
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          margin=dict(l=0, r=0, t=0, b=0))
        return fig
    d["pl"] = d["player"].map(canonical_name)
    d = d.sort_values(rank_col, ascending=False).head(top_n).sort_values(rank_col)

    is_pct = metric in _PCT_SET
    raw_total_col = metric  # raw season total
    colors = [DIM_COLOR if low else BAR_COLOR for low in d["low_minutes"]]
    text = d[rank_col].map(lambda v: _fmt_val(metric, v))
    pctl_txt = d[pct_col].map(lambda p: "—" if pd.isna(p) else f"{int(p)}th")
    role_txt = d["role_group"].map(lambda r: ROLE_LABELS.get(r, r))

    # Bars show the ADJUSTED value (what's ranked); hover exposes the raw observed
    # per-90 + minutes so the shrinkage is transparent, not hidden.
    fig.add_trace(go.Bar(
        x=d[rank_col], y=d["pl"], orientation="h",
        marker=dict(color=colors),
        text=text, textposition="auto", textfont=dict(size=10),
        customdata=np.stack([d[obs_col], d[raw_total_col], d["minutes"],
                             role_txt, pctl_txt], axis=-1),
        hovertemplate=(
            "<b>%{y}</b><br>"
            + ("Adjusted: %{x:.1f}% (season)" if is_pct
               else "Adjusted: %{x:.2f}/90 (raw: %{customdata[0]:.2f}/90)")
            + "<br>Total: %{customdata[1]:.0f} · %{customdata[2]:.0f} min<br>"
            "%{customdata[3]} · %{customdata[4]} pct in role<extra></extra>"
        ),
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


def _kpi_card(team_df: pd.DataFrame, league_df: pd.DataFrame,
              metric: str, label: str, section: str) -> dbc.Col:
    col = _rank_col(team_df, metric) if not team_df.empty else metric
    leader = "—"
    if team_df is not None and not team_df.empty and col in team_df.columns \
            and team_df[col].astype(float).max() > 0:
        top = team_df.sort_values(col, ascending=False).iloc[0]
        suffix = "" if metric in _PCT_SET else " /90"
        leader = f"{canonical_name(top['player'])} · {_fmt_val(metric, top[col])}{suffix}"

    return dbc.Col(
        html.Div(
            dbc.Card(dbc.CardBody([
                html.Div([
                    html.Span(label, style={"fontWeight": "600", "fontSize": "0.82rem",
                                            "color": "var(--text-primary)"}),
                    html.I(className="bi bi-info-circle",
                           style={"color": "var(--text-muted)", "fontSize": "0.75rem"},
                           title="Click card for definition + full breakdown"),
                ], className="d-flex align-items-center justify-content-between mb-1"),
                html.Div(leader, className="text-muted mb-2", style={"fontSize": "0.7rem"}),
                dcc.Graph(figure=_kpi_rank_figure(team_df, league_df, metric),
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


def _kpi_cards_grid(team_df: pd.DataFrame, league_df: pd.DataFrame,
                    kpi_list: list[tuple], section: str) -> html.Div:
    if team_df is None or team_df.empty:
        return html.P("No player data for this team/season.", className="text-muted",
                      style={"padding": "2rem", "textAlign": "center"})
    cards = [_kpi_card(team_df, league_df, m, lbl, section) for m, lbl in kpi_list]
    return dbc.Row(cards, className="g-3")


# ═══════════════════════════════════════════════════════════════════════════════
# PVA LEADERBOARDS (per-90, off / def / total — kept separate)
# ═══════════════════════════════════════════════════════════════════════════════

def _pva_leaderboard(team_df: pd.DataFrame, metric: str) -> go.Figure:
    fig = go.Figure()
    if team_df is None or team_df.empty:
        return fig
    obs_col = f"{metric}_p90"                     # observed per-90 (hover)
    adj_col = f"{metric}_p90_adj"                 # shrinkage-adjusted (ranked)
    rank_col = adj_col if adj_col in team_df.columns else obs_col
    d = team_df.copy()
    d["pl"] = d["player"].map(canonical_name)
    d = d.sort_values(rank_col, ascending=False).head(12).sort_values(rank_col)
    colors = [DIM_COLOR if low else BAR_COLOR for low in d["low_minutes"]]
    fig.add_trace(go.Bar(
        x=d[rank_col], y=d["pl"], orientation="h", marker=dict(color=colors),
        customdata=np.stack([d[obs_col], d[metric], d["minutes"], d["role_group"]], axis=-1),
        hovertemplate=("<b>%{y}</b><br>Adjusted: %{x:.3f}/90 (raw: %{customdata[0]:.3f}/90)<br>"
                       "Raw season %{customdata[1]:+.2f} · %{customdata[2]:.0f} min · "
                       "%{customdata[3]}<extra></extra>"),
    ))
    fig.update_layout(
        height=max(320, 26 * len(d) + 60), template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=20, t=10, b=30),
        xaxis=dict(title="PVA per 90", showgrid=True,
                   gridcolor="rgba(255,255,255,0.06)", zeroline=True,
                   zerolinecolor="rgba(255,255,255,0.2)"),
        yaxis=dict(automargin=True, tickfont=dict(size=10)),
    )
    return fig


def _pva_block(team_df: pd.DataFrame) -> html.Div:
    metrics = [("off_pva", "Offensive PVA"), ("def_pva", "Defensive PVA"),
               ("total_pva", "Total PVA")]
    cols = []
    for key, label in metrics:
        cols.append(dbc.Col([
            html.Div(label, className="mb-1",
                     style={"fontWeight": "600", "fontSize": "0.85rem",
                            "color": "var(--text-primary)"}),
            dcc.Graph(id=f"{PREFIX}-pva-{key.split('_')[0]}",
                      figure=_pva_leaderboard(team_df, key),
                      config={"displayModeBar": False}),
        ], xs=12, lg=4))
    return html.Div([
        dbc.Row(cols, className="g-3"),
        html.P(
            f"Bars show the minutes-weighted ADJUSTED PVA per 90 (Empirical-Bayes "
            f"shrinkage toward the role mean), which is what's ranked; hover shows the "
            f"raw observed per-90 + minutes. Players under {int(MIN_MINUTES_DIM)}′ are "
            f"also dimmed as a low-sample flag.",
            className="text-muted mt-2", style={"fontSize": "0.72rem"}),
    ])


# ═══════════════════════════════════════════════════════════════════════════════
# SQUAD OVERVIEW (season-only KPIs: apps / starts / minutes / consistency)
# ═══════════════════════════════════════════════════════════════════════════════

def _squad_overview(team_df: pd.DataFrame) -> html.Div:
    if team_df is None or team_df.empty:
        return html.Div()
    d = team_df.sort_values("minutes", ascending=False)

    header = html.Div(
        [html.Span("Player", style={"flex": "1", "fontSize": "0.72rem", "color": "#8899aa"})]
        + [html.Span(h, style={"minWidth": w, "textAlign": "right",
                               "fontSize": "0.72rem", "color": "#8899aa"})
           for h, w in [("Role", "4rem"), ("Apps", "3rem"), ("Starts", "3.5rem"),
                        ("Min", "4rem"), ("Min%", "3.5rem"),
                        ("Adj PVA/90", "5rem"), ("σ PVA", "4rem")]],
        style={"display": "flex", "padding": "6px 10px",
               "borderBottom": "1px solid rgba(255,255,255,0.15)"},
    )
    rows = []
    for _, r in d.iterrows():
        badges = []
        if r["low_minutes"]:
            badges.append(html.Span("low min", className="ms-2",
                          style={"fontSize": "0.6rem", "color": "#f59e0b",
                                 "border": "1px solid #f59e0b", "borderRadius": "3px",
                                 "padding": "0 4px"}))
        if r["partial_season"]:
            badges.append(html.Span("partial", className="ms-1",
                          style={"fontSize": "0.6rem", "color": "#60a5fa",
                                 "border": "1px solid #60a5fa", "borderRadius": "3px",
                                 "padding": "0 4px"}))
        rows.append(html.Div(
            [html.Span([canonical_name(r["player"]), *badges],
                       style={"flex": "1", "fontSize": "0.85rem", "color": "var(--text-primary)"})]
            + [html.Span(str(v), style={"minWidth": w, "textAlign": "right",
                                        "fontSize": "0.85rem", "color": "var(--text-secondary)"})
               for v, w in [
                   (ROLE_LABELS.get(r["role_group"], r["role_group"]).split()[0] if False else r["role_group"], "4rem"),
                   (int(r["appearances"]), "3rem"),
                   (int(r["starts"]), "3.5rem"),
                   (f"{r['minutes']:.0f}", "4rem"),
                   (f"{r['minutes_share']:.0f}%", "3.5rem"),
                   (f"{r.get('total_pva_p90_adj', r['total_pva_p90']):.2f}", "5rem"),
                   (f"{r['pva_consistency']:.2f}", "4rem"),
               ]],
            style={"display": "flex", "padding": "6px 10px", "alignItems": "center",
                   "borderBottom": "1px solid rgba(255,255,255,0.05)"},
        ))
    return html.Div([header, *rows],
                    style={"maxHeight": "460px", "overflowY": "auto", "borderRadius": "6px",
                           "border": "1px solid rgba(255,255,255,0.07)"})


# ═══════════════════════════════════════════════════════════════════════════════
# MODAL BODY (definition + ranked within-role table)
# ═══════════════════════════════════════════════════════════════════════════════

def build_kpi_breakdown_modal_body(season: str, team_name: str, metric: str) -> html.Div:
    data = compute_season_players(season.replace("/", "_"), team_name)
    team_df, league_df = data["team_df"], data["league_df"]
    meta = KPI_DEFINITIONS.get(metric, {})
    if team_df is None or team_df.empty:
        return html.Div(html.P("No data for this metric.", className="text-muted"))

    rank_col = _rank_col(team_df, metric)     # adjusted (ranks the table)
    obs_col = _ranked_value(team_df, metric)  # observed per-90 / raw %
    is_pct = metric in _PCT_SET
    enriched = _add_role_percentiles(league_df, metric)
    pct_col = f"__pctl_{metric}"
    d = team_df.merge(enriched[["team", "player", pct_col]], on=["team", "player"], how="left")
    companions = [c for c in KPI_MODAL_COMPANIONS.get(metric, []) if c in d.columns]
    d = d.sort_values(rank_col, ascending=False)

    # For counting/PVA metrics show BOTH Adjusted (ranked) and Raw/90 (observed),
    # making the shrinkage transparent.  Percentage KPIs aren't shrunk → one col.
    if is_pct:
        value_cols = [("Season %", "5rem")]
    else:
        value_cols = [("Adj /90", "5rem"), ("Raw /90", "5rem")]
    head_cols = value_cols + [(c.replace("_", " ").title(), "5rem") for c in companions] \
        + [("Role %ile", "4.5rem"), ("Min", "3.5rem")]
    header = html.Div(
        [html.Span("Player", style={"flex": "1", "fontSize": "0.72rem", "color": "#8899aa"})]
        + [html.Span(h, style={"minWidth": w, "textAlign": "right",
                               "fontSize": "0.72rem", "color": "#8899aa"}) for h, w in head_cols],
        style={"display": "flex", "padding": "6px 10px",
               "borderBottom": "1px solid rgba(255,255,255,0.15)"},
    )
    rows = []
    for _, r in d.iterrows():
        if float(r.get(rank_col, 0) or 0) == 0:
            continue
        pctl = r.get(pct_col)
        pctl_s = "—" if pd.isna(pctl) else f"{int(pctl)}th"
        comp_vals = [_fmt_val(c, r.get(c, 0)) for c in companions]
        name_style = {"flex": "1", "fontSize": "0.85rem",
                      "color": "var(--text-primary)",
                      "opacity": "0.5" if r["low_minutes"] else "1"}
        if is_pct:
            value_spans = [html.Span(_fmt_val(metric, r[rank_col]),
                           style={"minWidth": "5rem", "textAlign": "right",
                                  "fontSize": "0.85rem", "color": "var(--text-secondary)"})]
        else:
            value_spans = [
                html.Span(_fmt_val(metric, r[rank_col]),
                          style={"minWidth": "5rem", "textAlign": "right", "fontSize": "0.85rem",
                                 "color": "var(--text-primary)", "fontWeight": "600"}),
                html.Span(_fmt_val(metric, r[obs_col]),
                          style={"minWidth": "5rem", "textAlign": "right", "fontSize": "0.85rem",
                                 "color": "#8899aa"}),
            ]
        rows.append(html.Div(
            [html.Span(canonical_name(r["player"]), style=name_style)]
            + value_spans
            + [html.Span(cv, style={"minWidth": "5rem", "textAlign": "right",
                         "fontSize": "0.85rem", "color": "var(--text-secondary)"}) for cv in comp_vals]
            + [html.Span(pctl_s, style={"minWidth": "4.5rem", "textAlign": "right",
                         "fontSize": "0.85rem", "color": "var(--primary-light)"})]
            + [html.Span(f"{r['minutes']:.0f}", style={"minWidth": "3.5rem", "textAlign": "right",
                         "fontSize": "0.85rem", "color": "#8899aa"})],
            style={"display": "flex", "padding": "6px 10px", "alignItems": "center",
                   "borderBottom": "1px solid rgba(255,255,255,0.05)"},
        ))

    explain = ("Season % ranked (sample-size robust). " if is_pct else
               "Adj /90 = minutes-weighted shrinkage toward the role mean (ranked); "
               "Raw /90 = observed. ")
    return html.Div([
        html.P([html.Span(f"[{meta.get('class','')}] ",
                          style={"fontWeight": "700", "color": "var(--primary-light)"}),
                meta.get("def", "")],
               style={"fontSize": "0.8rem", "color": "var(--text-secondary)", "marginBottom": "0.5rem"}),
        html.P(explain + "Role %ile = within-role percentile (on the adjusted value) "
               "vs all qualifying Serie A players (≥450′). Low-minute players dimmed.",
               style={"fontSize": "0.72rem", "color": "var(--text-muted)", "marginBottom": "0.75rem"}),
        html.Div([header, *rows] if rows else html.P("No players recorded this metric.",
                 className="text-muted"),
                 style={"maxHeight": "440px", "overflowY": "auto", "borderRadius": "6px",
                        "border": "1px solid rgba(255,255,255,0.07)"}),
    ])


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def _store(d: dict) -> dcc.Store:
    return dcc.Store(id=f"{PREFIX}-store",
                     data={"season": d.get("season", ""), "team": d.get("team", "")})


def build_player_section(season: str, team_name: str) -> html.Div:
    season_label = season.replace("_", "/")
    d = compute_season_players(season, team_name)
    team_df, league_df = d["team_df"], d["league_df"]

    no_data = None
    if team_df is None or team_df.empty:
        no_data = dbc.Alert(
            [html.I(className="bi bi-exclamation-triangle-fill me-2"),
             f"No season player data for {canonical_name(team_name)} ({season_label}). "
             "Run precompute_season_players() to generate player_season_{season}.parquet."],
            color="warning", className="mb-3")

    sep = html.Hr(style={"borderColor": "var(--border-light)", "margin": "1.5rem 0"})

    return html.Div([
        ds_header(
            "Opponent Analysis — Season View", "bi-person-badge",
            f"Player Analysis — {canonical_name(team_name)}  ({season_label})",
            "Season-aggregate player KPIs — Possession Value, in/out of possession. "
            "Per-90 normalised with minutes-weighted shrinkage, ranked by within-role "
            "league percentiles for positional context."),
        _store(d),
        build_unified_modal(f"{PREFIX}-modal", f"{PREFIX}-modal-title",
                            f"{PREFIX}-modal-body", title="Metric Breakdown", size="lg"),
        *([] if no_data is None else [no_data]),

        # Role-classification caveat — roles come from Opta position tags and may
        # not reflect a club's tactical usage (e.g. a deep CAM used as a central
        # midfielder), which can affect within-role comparisons for such players.
        html.Div(
            [html.I(className="bi bi-info-circle me-1"),
             "Roles are derived from Opta position tags and may not match a club's "
             "tactical usage (e.g. a deep-lying playmaker tagged as an attacking "
             "mid). Within-role comparisons reflect the tagged role."],
            style={"fontSize": "0.72rem", "color": "var(--text-muted)",
                   "background": "rgba(96,165,250,0.07)", "border": "1px solid rgba(96,165,250,0.18)",
                   "borderRadius": "6px", "padding": "6px 10px", "marginBottom": "1rem"},
        ),

        # 1 — Possession Value leaderboards
        html.H6("POSSESSION VALUE (per 90)", className="buildup-subsection-title"),
        _pva_block(team_df),
        sep,

        # 2 — In Possession KPI grid
        html.H6("IN POSSESSION", className="buildup-subsection-title"),
        html.Div("Ranked by shrinkage-adjusted per-90 (minutes-weighted toward the role "
                 "mean); hover shows the raw observed per-90, minutes and within-role "
                 "percentile. Click any card for the full breakdown.",
                 style={"fontSize": "0.78rem", "color": "var(--text-muted)", "marginBottom": "0.6rem"}),
        _kpi_cards_grid(team_df, league_df, IN_POSSESSION_KPIS, "in"),
        sep,

        # 3 — Out of Possession KPI grid
        html.H6("OUT OF POSSESSION", className="buildup-subsection-title"),
        _kpi_cards_grid(team_df, league_df, OUT_POSSESSION_KPIS, "out"),
        sep,

        # 4 — Squad overview (apps / starts / minutes / consistency)
        html.H6("SQUAD OVERVIEW", className="buildup-subsection-title"),
        html.Div("Appearances, starts, minutes-share of the season, total PVA per 90, "
                 "and PVA consistency (σ of per-match PVA — lower = steadier).",
                 style={"fontSize": "0.78rem", "color": "var(--text-muted)", "marginBottom": "0.6rem"}),
        _squad_overview(team_df),
    ], className="analysis-section buildup-card ma-card",
       style={"marginBottom": "2rem", "padding": "1.5rem"})
