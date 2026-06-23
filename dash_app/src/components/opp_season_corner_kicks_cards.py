"""
Opponent Analysis — Set Pieces Overview — Corner Kicks (Season Aggregate)
=========================================================================
Season-aggregate Corner Kicks block for Opponent Analysis, the 4th top-level
overview (Set Pieces). Scope: Corner Kicks only — Direct FK / FK will be added
later as their own files.

Data source: corner_kicks_summary_{season}.parquet (one row per team), built by
precompute_season_corner_kicks(). Mirrors opp_season_transitions_cards.py:
  · _load_corner_kicks_parquet() → cache_get/cache_set → pd.read_parquet
  · _filter_team() via canonical_name(...).lower()
  · compute_season_corner_kicks(season, team) → flat dict (JSON cols parsed)
  · _modal_kpi + _league_table league-comparison modals for headline KPIs
  · build_unified_modal() chrome for all modals
  · _build_corner_lights() 9-zone density map (theme-aware) — built fresh, the
    per-match dot map is not reused; geometry reuses _zones_for_side() from
    set_piece_cards.py for visual consistency.

Component IDs: opp-season-sp-*
"""

from __future__ import annotations

import json

import dash_bootstrap_components as dbc
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import dcc, html

from src.config import READY_DATA_DIR
from src.team_mapping import canonical_name
from src.styling.theme import COLORS_DARK, SEMANTIC_COLORS
from src.styling.plotly_template import apply_chart_theme
from src.styling.ui_components import build_unified_modal, ds_header
from src.utils.caching import cache_get, cache_set
from src.utils.logging import log

# Reuse the per-match zone geometry + pitch constants (read-only import) so the
# season delivery maps line up exactly with the Match Analysis corner card.
from src.components.set_piece_cards import (
    _zones_for_side,
    DELIVERY_COLORS,
    OUTCOME_COLORS,
    GOAL_LINE, GOAL_DEPTH, GOAL_L, GOAL_R,
    PENALTY_LINE, SIX_YARD_LINE,
    PEN_AREA_L, PEN_AREA_R, SIX_YARD_L, SIX_YARD_R,
    PEN_SPOT_X, PEN_SPOT_Y, FT_LINE, CA_LINE,
    FIG_Y_MIN, FIG_Y_MAX,
    D_ARC_RX, D_ARC_RY, CORNER_ARC_RX, CORNER_ARC_RY,
)

CID = "opp-season-sp"
STORE = "opp-season-sp-store"

PRIMARY    = COLORS_DARK["accent"]   # "#8a1f33"
_HIGHLIGHT = COLORS_DARK["accent"]

GOAL_CLR  = SEMANTIC_COLORS["sp_goal"]              # green
SOT_CLR   = SEMANTIC_COLORS["sp_shot_on_target"]    # blue
SOFF_CLR  = SEMANTIC_COLORS["sp_shot_off_target"]   # orange
CLEAR_CLR = SEMANTIC_COLORS["sp_cleared"]           # grey
SP_CLR    = SEMANTIC_COLORS["sp_second_phase"]      # violet

# Delivery types and outcome columns — verbatim from corner_kicks.py
_DELIVERY_ORDER = ["Inswinger", "Outswinger", "Straight", "Short", "Unknown"]
_OUTCOME_COLS = ["Goal", "Own Goal", "Shot on Target", "Shot off Target",
                 "Cleared", "Second Phase Attack"]

# Zones that participate in the lights map (in-box taxonomy, Unknown excluded)
_LIGHT_ZONES = ["GA1", "GA2", "GA3", "CA1", "CA2", "CA3", "Front", "Back", "Edge"]
# "Positive" outcomes that tint a zone green
_GREEN_OUTCOMES = {"Goal", "Shot on Target"}


# ══════════════════════════════════════════════════════════════════════════════
# DATA LAYER
# ══════════════════════════════════════════════════════════════════════════════

def _load_corner_kicks_parquet(season: str) -> pd.DataFrame | None:
    cache_key = f"opp_corner_kicks_summary_{season}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    path = READY_DATA_DIR / f"corner_kicks_summary_{season}.parquet"
    if not path.exists():
        log.warning("Corner kicks parquet missing: %s — run "
                    "precompute_season_corner_kicks()", path.name)
        return None
    try:
        df = pd.read_parquet(path)
    except Exception as exc:
        log.error("Failed to read %s: %s", path.name, exc)
        return None

    cache_set(cache_key, df)
    return df


def _filter_team(df: pd.DataFrame | None, team_name: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    target = canonical_name(team_name).lower()
    mask = df["team"].apply(lambda t: canonical_name(str(t)).lower() == target)
    return df[mask].reset_index(drop=True)


def load_league_corner_kicks_summary(season: str) -> pd.DataFrame | None:
    """Return the full corner_kicks_summary_{season}.parquet (all teams)."""
    return _load_corner_kicks_parquet(season)


def compute_season_corner_kicks(season: str, team_name: str) -> dict:
    """Return all corner-kicks season-aggregate data for one team."""
    df = _load_corner_kicks_parquet(season)
    row_df = _filter_team(df, team_name)

    if row_df.empty:
        return _empty_result(season, team_name)

    row = row_df.iloc[0]

    def _f(col, default=0.0):
        v = row.get(col, default)
        return default if (v != v) else float(v)

    def _i(col, default=0):
        v = row.get(col, default)
        try:
            return int(v) if v == v else default
        except (TypeError, ValueError):
            return default

    def _json_col(col, default):
        try:
            return json.loads(str(row.get(col, default)))
        except (ValueError, TypeError):
            return json.loads(default)

    return {
        "season":         str(row.get("season", season)),
        "team":           team_name,
        "matches_played": _i("matches_played", 1),
        "total_corners":   _i("total_corners"),
        "total_per_match": _f("total_per_match"),
        "goals":           _i("goals"),
        "goals_per_match": _f("goals_per_match"),
        "shot_on_target":  _i("shot_on_target"),
        "sot_per_match":   _f("sot_per_match"),
        "shot_off_target": _i("shot_off_target"),
        "soff_per_match":  _f("soff_per_match"),
        "cleared":         _i("cleared"),
        "cleared_per_match": _f("cleared_per_match"),
        "second_phase":    _i("second_phase"),
        "second_phase_per_match": _f("second_phase_per_match"),
        "conversion_rate": _f("conversion_rate"),
        "delivery_counts":   _json_col("delivery_counts_json", "{}"),
        "delivery_outcomes": _json_col("delivery_outcomes_json", "{}"),
        "zone_counts":       _json_col("zone_counts_json", "{}"),
        "corners":           _json_col("corners_json", "[]"),
    }


def _empty_result(season: str, team_name: str) -> dict:
    return {
        "season": season, "team": team_name, "matches_played": 0,
        "total_corners": 0, "total_per_match": 0.0,
        "goals": 0, "goals_per_match": 0.0,
        "shot_on_target": 0, "sot_per_match": 0.0,
        "shot_off_target": 0, "soff_per_match": 0.0,
        "cleared": 0, "cleared_per_match": 0.0,
        "second_phase": 0, "second_phase_per_match": 0.0,
        "conversion_rate": 0.0,
        "delivery_counts": {}, "delivery_outcomes": {},
        "zone_counts": {}, "corners": [],
    }


# ══════════════════════════════════════════════════════════════════════════════
# SHARED UI HELPERS  (mirror opp_season_transitions_cards.py)
# ══════════════════════════════════════════════════════════════════════════════

def _expand_icon() -> html.I:
    return html.I(
        className="bi bi-box-arrow-up-right",
        style={"fontSize": "0.65rem", "color": "var(--text-muted)",
               "position": "absolute", "top": "6px", "right": "8px"},
    )


def _modal_kpi(label: str, value, subtitle: str, color: str, icon: str,
               click_id: str) -> html.Div:
    return html.Div(
        [
            html.Div(
                html.I(className=f"bi {icon}",
                       style={"color": color, "fontSize": "1.3rem"}),
                className="kpi-icon",
            ),
            html.Div(
                [
                    html.Span(label, className="kpi-label"),
                    html.Span(str(value), className="kpi-value"),
                    html.Span(subtitle, className="kpi-subtitle",
                              style={"color": color}),
                ],
                className="kpi-text",
            ),
            _expand_icon(),
        ],
        className="kpi-card",
        id=click_id,
        n_clicks=0,
        style={"cursor": "pointer", "position": "relative"},
    )


# ══════════════════════════════════════════════════════════════════════════════
# LEAGUE-COMPARISON TABLE  (identical format to the completed blocks)
# ══════════════════════════════════════════════════════════════════════════════

def _league_table(
    summary_df: pd.DataFrame | None,
    metric_col: str,
    metric_label: str,
    highlight_team: str,
    ascending: bool = False,
    fmt: str = ".1f",
    suffix: str = "",
) -> html.Div:
    if summary_df is None or summary_df.empty:
        return html.P("No league data available.", style={"color": "#8899aa"})
    if metric_col not in summary_df.columns:
        return html.P(f"Column '{metric_col}' not found.", style={"color": "#8899aa"})

    df = summary_df.copy().dropna(subset=[metric_col])
    df = df.sort_values(metric_col, ascending=ascending).reset_index(drop=True)
    df["rank"] = range(1, len(df) + 1)

    hl_lower = canonical_name(highlight_team).lower()

    header = html.Div(
        [
            html.Span("#", style={"width": "2rem", "color": "#8899aa",
                                  "fontSize": "0.75rem", "flexShrink": "0"}),
            html.Span("Team", style={"flex": "1", "color": "#8899aa",
                                     "fontSize": "0.75rem"}),
            html.Span(metric_label, style={"color": "#8899aa", "fontSize": "0.75rem",
                                           "minWidth": "4rem", "textAlign": "right"}),
        ],
        style={"display": "flex", "padding": "6px 10px",
               "borderBottom": "1px solid rgba(255,255,255,0.15)", "marginBottom": "2px"},
    )

    rows = []
    for _, row in df.iterrows():
        team    = str(row.get("team", ""))
        val     = row[metric_col]
        rank    = int(row["rank"])
        is_hl   = canonical_name(team).lower() == hl_lower
        val_str = f"{format(float(val), fmt)}{suffix}"

        row_style: dict = {
            "display": "flex", "padding": "6px 10px",
            "borderBottom": "1px solid rgba(255,255,255,0.05)",
            "alignItems": "center",
        }
        if is_hl:
            row_style.update({
                "background": f"{_HIGHLIGHT}22",
                "borderLeft": f"3px solid {_HIGHLIGHT}",
            })
        rows.append(
            html.Div(
                [
                    html.Span(str(rank), style={"width": "2rem", "color": "#8899aa",
                                                "fontSize": "0.8rem", "flexShrink": "0"}),
                    html.Span(team, style={
                        "flex": "1",
                        "fontWeight": "700" if is_hl else "400",
                        "color": _HIGHLIGHT if is_hl else "var(--text-primary)",
                        "fontSize": "0.88rem",
                    }),
                    html.Span(val_str, style={
                        "fontWeight": "700" if is_hl else "400",
                        "color": _HIGHLIGHT if is_hl else "var(--text-secondary)",
                        "fontSize": "0.9rem", "minWidth": "4rem", "textAlign": "right",
                    }),
                ],
                style=row_style,
            )
        )

    return html.Div(
        [header, *rows],
        style={
            "maxHeight": "460px", "overflowY": "auto",
            "borderRadius": "6px",
            "border": "1px solid rgba(255,255,255,0.07)",
        },
    )


# ══════════════════════════════════════════════════════════════════════════════
# SECTION A — Volume & Outcomes KPI row  (clickable league-comparison cards)
# ══════════════════════════════════════════════════════════════════════════════

def _section_volume_outcomes(d: dict) -> html.Div:
    total_pm = d.get("total_per_match", 0.0)
    total_n  = d.get("total_corners", 0)
    conv     = d.get("conversion_rate", 0.0)

    cards = [
        _modal_kpi(
            "Corners / Match", f"{total_pm:.1f}",
            f"Total: {total_n}  ·  {conv:.1f}% conv.",
            PRIMARY, "bi-flag-fill",
            f"{CID}-kpi-total",
        ),
        _modal_kpi(
            "Goals / Match", f"{d.get('goals_per_match', 0.0):.1f}",
            f"Total: {d.get('goals', 0)}  ·  {conv:.1f}% conv.",
            GOAL_CLR, "bi-trophy-fill",
            f"{CID}-kpi-goals",
        ),
        _modal_kpi(
            "Shots on Target / Match", f"{d.get('sot_per_match', 0.0):.1f}",
            f"Total: {d.get('shot_on_target', 0)}",
            SOT_CLR, "bi-bullseye",
            f"{CID}-kpi-sot",
        ),
        _modal_kpi(
            "Shots off Target / Match", f"{d.get('soff_per_match', 0.0):.1f}",
            f"Total: {d.get('shot_off_target', 0)}",
            SOFF_CLR, "bi-x-circle",
            f"{CID}-kpi-soff",
        ),
        _modal_kpi(
            "Cleared / Match", f"{d.get('cleared_per_match', 0.0):.1f}",
            f"Total: {d.get('cleared', 0)}",
            CLEAR_CLR, "bi-shield",
            f"{CID}-kpi-cleared",
        ),
        _modal_kpi(
            "2nd Phase / Match", f"{d.get('second_phase_per_match', 0.0):.1f}",
            f"Total: {d.get('second_phase', 0)}",
            SP_CLR, "bi-arrow-repeat",
            f"{CID}-kpi-sp",
        ),
    ]

    return html.Div(
        [
            html.H6("Volume & Outcomes", className="buildup-subsection-title"),
            html.P(
                "Headline = season average per match  ·  conversion rate = "
                "goals ÷ corners (season ratio). Click any card for the league "
                "ranking.",
                className="kpi-subtitle", style={"marginBottom": "0.5rem"},
            ),
            html.Div(cards, className="team-kpi-row"),
        ],
    )


# ══════════════════════════════════════════════════════════════════════════════
# SECTION B — Delivery Type season matrix (bar + table, summed across season)
# ══════════════════════════════════════════════════════════════════════════════

def _delivery_bar(delivery_counts: dict, theme: str) -> go.Figure:
    counts = [int(delivery_counts.get(d, 0) or 0) for d in _DELIVERY_ORDER]
    colors = [DELIVERY_COLORS[d] for d in _DELIVERY_ORDER]
    text_color = "#e2e8f0" if theme != "light" else "#1a1a2e"

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=_DELIVERY_ORDER,
        x=counts,
        orientation="h",
        marker=dict(color=colors, opacity=0.85),
        text=[str(c) if c else "" for c in counts],
        textposition="outside",
        textfont=dict(size=11, color=text_color),
        hovertemplate="%{y}: %{x}<extra></extra>",
    ))
    apply_chart_theme(fig, theme)
    fig.update_layout(
        margin=dict(l=10, r=30, t=10, b=10),
        height=180,
        xaxis=dict(zeroline=False, tickfont=dict(size=10)),
        yaxis=dict(tickfont=dict(size=11)),
        showlegend=False,
    )
    return fig


def _section_delivery_type(d: dict, theme: str) -> html.Div:
    delivery_counts   = d.get("delivery_counts", {})
    delivery_outcomes = d.get("delivery_outcomes", {})

    bar_fig = _delivery_bar(delivery_counts, theme)

    header_cells = [html.Th("Type", style={"padding": "0.4rem 0.6rem",
                                            "color": "var(--text-secondary)",
                                            "fontSize": "0.75rem"})]
    for oc in _OUTCOME_COLS:
        header_cells.append(
            html.Th(oc, style={
                "padding": "0.4rem 0.5rem",
                "color": OUTCOME_COLORS.get(oc, "#94a3b8"),
                "fontSize": "0.75rem",
                "textAlign": "center",
            })
        )

    body_rows = []
    for d_type in _DELIVERY_ORDER:
        cnt = int(delivery_counts.get(d_type, 0) or 0)
        if cnt == 0:
            continue
        do = delivery_outcomes.get(d_type, {})
        cells = [
            html.Td(
                html.Span([
                    html.Span("●", style={"color": DELIVERY_COLORS[d_type],
                                          "marginRight": "5px"}),
                    d_type,
                ]),
                style={"padding": "0.35rem 0.6rem", "fontSize": "0.85rem",
                       "color": "var(--text-primary)", "fontWeight": "600"},
            )
        ]
        for oc in _OUTCOME_COLS:
            v = int(do.get(oc, 0) or 0)
            pct = f"({v/cnt*100:.0f}%)" if cnt and v else ""
            cells.append(
                html.Td(
                    f"{v} {pct}".strip(),
                    style={
                        "padding": "0.35rem 0.5rem",
                        "textAlign": "center",
                        "fontSize": "0.82rem",
                        "color": OUTCOME_COLORS.get(oc, "#94a3b8") if v else "var(--text-muted)",
                        "fontWeight": "600" if v else "400",
                    },
                )
            )
        body_rows.append(html.Tr(cells))

    if not body_rows:
        body_rows = [html.Tr(html.Td("No data", colSpan=len(_OUTCOME_COLS) + 1,
                                     style={"padding": "0.5rem",
                                            "color": "var(--text-muted)"}))]

    table = html.Table(
        [html.Thead(html.Tr(header_cells)), html.Tbody(body_rows)],
        style={"width": "100%", "borderCollapse": "separate", "borderSpacing": "2px"},
    )

    return html.Div(
        [
            html.H6("Delivery Type", className="buildup-subsection-title"),
            html.P(
                "Season totals by delivery type. Table cells show count and that "
                "outcome's share of corners of that delivery type.",
                className="kpi-subtitle", style={"marginBottom": "0.5rem"},
            ),
            html.Div(
                [
                    html.Div(
                        dcc.Graph(id=f"{CID}-delivery-bar", figure=bar_fig,
                                  config={"displayModeBar": False, "responsive": True}),
                        style={"flex": "1", "minWidth": "220px"},
                    ),
                    html.Div(
                        table,
                        style={"flex": "2", "minWidth": "0", "overflowX": "auto"},
                    ),
                ],
                style={"display": "flex", "gap": "1.5rem",
                       "alignItems": "flex-start", "flexWrap": "wrap"},
            ),
        ]
    )


# ══════════════════════════════════════════════════════════════════════════════
# SECTION C — Delivery Maps (two panels, 9-zone density "lights")
# ══════════════════════════════════════════════════════════════════════════════

def _line_color(theme: str, alpha: float) -> str:
    base = "255,255,255" if theme != "light" else "26,26,46"
    return f"rgba({base},{alpha})"


def _zone_light_fill(positive: int, total: int, intensity: float, theme: str) -> str:
    """
    Single fill per zone. Green when the majority of corners landing there end
    Goal / Shot on Target, red otherwise. ``intensity`` in [0, 1] drives both
    the saturation toward the target hue and the alpha (volume = brighter).
    """
    if total <= 0:
        return "rgba(120,130,146,0.06)" if theme != "light" else "rgba(120,130,146,0.05)"

    is_green = positive * 2 >= total  # majority (ties → green)
    base = (90, 100, 116)             # neutral slate
    target = (34, 197, 94) if is_green else (239, 68, 68)
    r = int(base[0] + (target[0] - base[0]) * intensity)
    g = int(base[1] + (target[1] - base[1]) * intensity)
    b = int(base[2] + (target[2] - base[2]) * intensity)
    a = 0.20 + 0.60 * intensity
    return f"rgba({r},{g},{b},{a:.2f})"


def _corner_pitch_shapes(is_left: bool, theme: str) -> list:
    """Theme-aware portrait final-third pitch furniture (lines only, no zones)."""
    lc = _line_color(theme, 0.50)
    lw = 1.5
    shapes = []

    # Touchlines
    for xv in (0.0, 100.0):
        shapes.append(dict(type="line", x0=xv, x1=xv, y0=FIG_Y_MIN, y1=GOAL_LINE,
                           line=dict(color=lc, width=lw), layer="below"))
    # Final third line (bottom)
    shapes.append(dict(type="line", x0=0, x1=100, y0=FT_LINE, y1=FT_LINE,
                       line=dict(color=_line_color(theme, 0.30), width=1, dash="dot")))
    # Goal line (bold)
    shapes.append(dict(type="line", x0=0, x1=100, y0=GOAL_LINE, y1=GOAL_LINE,
                       line=dict(color=_line_color(theme, 0.80), width=2.5)))
    # Goal box
    shapes.append(dict(type="rect", x0=GOAL_L, x1=GOAL_R, y0=GOAL_LINE, y1=GOAL_LINE + GOAL_DEPTH,
                       line=dict(color=_line_color(theme, 0.75), width=2),
                       fillcolor=_line_color(theme, 0.04), layer="below"))
    # Penalty area
    shapes.append(dict(type="rect", x0=PEN_AREA_L, x1=PEN_AREA_R, y0=PENALTY_LINE, y1=GOAL_LINE,
                       line=dict(color=lc, width=lw), fillcolor="rgba(0,0,0,0)", layer="below"))
    # 6-yard box
    shapes.append(dict(type="rect", x0=SIX_YARD_L, x1=SIX_YARD_R, y0=SIX_YARD_LINE, y1=GOAL_LINE,
                       line=dict(color=lc, width=lw), fillcolor="rgba(0,0,0,0)", layer="below"))

    # D-arc (portion below penalty line)
    t_arc = np.linspace(-2.51, -0.63, 50)
    ax = PEN_SPOT_Y + D_ARC_RX * np.cos(t_arc)
    ay = PEN_SPOT_X + D_ARC_RY * np.sin(t_arc)
    mask = (ay < PENALTY_LINE) & (ax >= 0) & (ax <= 100)
    ax, ay = ax[mask], ay[mask]
    if len(ax) >= 2:
        path = "M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in zip(ax, ay))
        shapes.append(dict(type="path", path=path,
                           line=dict(color=_line_color(theme, 0.45), width=1.2),
                           fillcolor="rgba(0,0,0,0)", layer="below"))

    # Corner arcs
    t_cl = np.linspace(-np.pi / 2, 0, 25)
    shapes.append(dict(type="path",
                       path="M " + " L ".join(
                           f"{CORNER_ARC_RX * np.cos(t):.3f},{100 + CORNER_ARC_RY * np.sin(t):.3f}"
                           for t in t_cl),
                       line=dict(color=_line_color(theme, 0.50), width=1.2),
                       fillcolor="rgba(0,0,0,0)", layer="below"))
    t_cr = np.linspace(-np.pi, -np.pi / 2, 25)
    shapes.append(dict(type="path",
                       path="M " + " L ".join(
                           f"{100 + CORNER_ARC_RX * np.cos(t):.3f},{100 + CORNER_ARC_RY * np.sin(t):.3f}"
                           for t in t_cr),
                       line=dict(color=_line_color(theme, 0.50), width=1.2),
                       fillcolor="rgba(0,0,0,0)", layer="below"))

    return shapes


def _build_corner_lights(corners: list, is_left: bool, title: str,
                         theme: str = "dark") -> go.Figure:
    """
    Portrait final-third 9-zone density map for corners from one side.

    Each named zone (GA1–3, CA1–3, Front, Back, Edge) is filled green when the
    majority of corners landing there end Goal / Shot on Target, red otherwise;
    fill intensity scales with corner volume in that zone (volume / max).
    """
    side_corners = [c for c in corners if bool(c.get("is_left", True)) == is_left]

    # Tally per zone: total + positive (Goal / Shot on Target)
    zone_total: dict[str, int] = {z: 0 for z in _LIGHT_ZONES}
    zone_pos: dict[str, int] = {z: 0 for z in _LIGHT_ZONES}
    for c in side_corners:
        z = c.get("zone", "Unknown")
        if z not in zone_total:
            continue
        zone_total[z] += 1
        if c.get("outcome") in _GREEN_OUTCOMES:
            zone_pos[z] += 1

    max_vol = max(zone_total.values(), default=1) or 1

    fig = go.Figure()

    # Pitch furniture
    for shape in _corner_pitch_shapes(is_left, theme):
        fig.add_shape(**shape)

    # Penalty spot
    fig.add_trace(go.Scatter(
        x=[100 - PEN_SPOT_Y], y=[PEN_SPOT_X], mode="markers",
        marker=dict(size=7, color=_line_color(theme, 0.60), symbol="circle"),
        showlegend=False, hoverinfo="skip",
    ))

    # Zone fills (lights) + count annotations
    text_base = "255,255,255" if theme != "light" else "26,26,46"
    annotations = []
    for x0, x1, y0, y1, label, _default_fill in _zones_for_side(is_left):
        zkey = label.replace("\n", "").replace("Zone", "")  # "Front\nZone"→"Front"
        zkey = zkey.strip()
        total = zone_total.get(zkey, 0)
        pos   = zone_pos.get(zkey, 0)
        intensity = total / max_vol if total > 0 else 0.0
        fill = _zone_light_fill(pos, total, intensity, theme)

        fig.add_shape(type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
                      line=dict(color=_line_color(theme, 0.18), width=0.8),
                      fillcolor=fill, layer="below")

        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        label_txt = label.replace("\n", "<br>")
        if total > 0:
            text_a = 0.55 + 0.45 * intensity
            annotations.append(dict(
                x=cx, y=cy,
                text=f"{label_txt}<br><b>{total}</b>",
                showarrow=False,
                font=dict(size=9, color=f"rgba({text_base},{text_a:.2f})"),
                xanchor="center", yanchor="middle",
            ))
        else:
            annotations.append(dict(
                x=cx, y=cy, text=label_txt, showarrow=False,
                font=dict(size=8, color=f"rgba({text_base},0.35)"),
                xanchor="center", yanchor="middle",
            ))

    # GOAL + Final Third Line annotations
    annotations += [
        dict(x=50, y=GOAL_LINE + GOAL_DEPTH / 2 + 0.3, text="GOAL", showarrow=False,
             font=dict(size=9, color=f"rgba({text_base},0.75)"), xanchor="center"),
        dict(x=50, y=FT_LINE - 0.8, text="Final Third Line", showarrow=False,
             font=dict(size=7, color=f"rgba({text_base},0.30)"), xanchor="center"),
    ]

    apply_chart_theme(fig, theme)
    fig.update_layout(
        title=dict(text=title, font=dict(size=11), x=0.5, xanchor="center"),
        margin=dict(l=15, r=15, t=30, b=20),
        height=480,
        xaxis=dict(range=[-5, 105], showgrid=False, zeroline=False,
                   showticklabels=False, fixedrange=True),
        yaxis=dict(range=[FIG_Y_MIN - 1, FIG_Y_MAX + 0.5], showgrid=False,
                   zeroline=False, showticklabels=False, fixedrange=True),
        showlegend=False,
        annotations=annotations,
    )
    return fig


def _section_delivery_maps(d: dict, theme: str) -> html.Div:
    corners = d.get("corners", [])

    nl = sum(1 for c in corners if bool(c.get("is_left", True)))
    nr = sum(1 for c in corners if not bool(c.get("is_left", True)))

    fig_left  = _build_corner_lights(corners, True,  f"Left-Side Corners ({nl})", theme)
    fig_right = _build_corner_lights(corners, False, f"Right-Side Corners ({nr})", theme)

    def _pitch_col(graph_id, fig, n):
        subtitle = f"{n} corner{'s' if n != 1 else ''}" if n else "No corners from this side"
        return html.Div(
            [
                html.P(subtitle, className="kpi-subtitle",
                       style={"textAlign": "center", "marginBottom": "0.4rem"}),
                html.Div(
                    dcc.Graph(id=graph_id, figure=fig,
                              config={"displayModeBar": False, "responsive": True}),
                    className="pitch-transitions-lights",
                ),
            ],
            style={"flex": "1", "minWidth": "280px"},
        )

    return html.Div(
        [
            html.H6("Delivery Maps", className="buildup-subsection-title"),
            html.P(
                "Zone shading = corner volume landing there (brighter = more)  ·  "
                "green = majority end as goal / shot on target  ·  red = majority "
                "cleared, off target or second phase. Zones are relative to the "
                "corner side taken.",
                className="kpi-subtitle", style={"marginBottom": "0.8rem"},
            ),
            html.Div(
                [_pitch_col(f"{CID}-map-left", fig_left, nl),
                 _pitch_col(f"{CID}-map-right", fig_right, nr)],
                style={"display": "flex", "gap": "1.5rem", "flexWrap": "wrap"},
            ),
        ]
    )


# ══════════════════════════════════════════════════════════════════════════════
# MODALS
# ══════════════════════════════════════════════════════════════════════════════

# (slug, metric_col, label, ascending, fmt, suffix, modal title)
KPI_MODALS = [
    ("total",   "total_per_match", "Corners/M", False, ".1f", "",  "Corners / Match — League Comparison"),
    ("goals",   "goals_per_match", "Goals/M",   False, ".1f", "",  "Corner Goals / Match — League Comparison"),
    ("sot",     "sot_per_match",   "SoT/M",     False, ".1f", "",  "Shots on Target / Match — League Comparison"),
    ("soff",    "soff_per_match",  "Soff/M",    False, ".1f", "",  "Shots off Target / Match — League Comparison"),
    ("cleared", "cleared_per_match", "Cleared/M", False, ".1f", "", "Cleared / Match — League Comparison"),
    ("sp",      "second_phase_per_match", "2nd Phase/M", False, ".1f", "", "2nd Phase / Match — League Comparison"),
]


def _build_all_modals() -> list:
    modals = []
    for slug, _col, _lbl, _asc, _fmt, _suf, title in KPI_MODALS:
        modals.append(build_unified_modal(
            modal_id=f"{CID}-modal-{slug}",
            title_id=f"{CID}-modal-{slug}-title",
            body_id =f"{CID}-modal-{slug}-body",
            title   =title,
            size    ="md",
        ))
    return modals


# ══════════════════════════════════════════════════════════════════════════════
# STORE
# ══════════════════════════════════════════════════════════════════════════════

def _store(d: dict) -> dcc.Store:
    return dcc.Store(id=STORE, data={
        "season": d.get("season", ""),
        "team":   d.get("team", ""),
        "corners": d.get("corners", []),
        "delivery_counts": d.get("delivery_counts", {}),
    })


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def build_corner_kicks_section(season: str, team_name: str,
                               theme: str = "dark") -> html.Div:
    """
    Build the full season-aggregate Corner Kicks section.
    Called lazily by the opp-section-sp loader callback.
    """
    season_label = season.replace("_", "/")
    d = compute_season_corner_kicks(season, team_name)

    no_data_banner = None
    if d["total_corners"] == 0:
        no_data_banner = dbc.Alert(
            [
                html.I(className="bi bi-exclamation-triangle-fill me-2"),
                f"No corner kicks data found for {team_name} ({season_label}). "
                "Run precompute_season_corner_kicks() to generate the parquet.",
            ],
            color="warning", className="mb-3",
        )

    _hr = html.Hr(style={"borderColor": "var(--border-light)", "margin": "1.5rem 0"})

    return html.Div(
        [
            ds_header(
                "Opponent Analysis — Season View",
                "bi-flag-fill",
                f"Set Pieces — Corner Kicks — {team_name}  ({season_label})",
                "Volume, delivery types and zone-by-zone delivery maps, season "
                "aggregate",
            ),
            _store(d),
            *_build_all_modals(),
            *([] if no_data_banner is None else [no_data_banner]),

            # A — Volume & Outcomes
            html.Div(_section_volume_outcomes(d), style={"marginBottom": "1.5rem"}),

            _hr,

            # B — Delivery Type matrix
            html.Div(_section_delivery_type(d, theme), style={"marginBottom": "1.5rem"}),

            _hr,

            # C — Delivery maps (two panels, theme-aware lights)
            html.Div(_section_delivery_maps(d, theme), style={"marginBottom": "1.5rem"}),
        ],
        className="analysis-section buildup-card ma-card",
        style={"marginBottom": "2rem", "padding": "1.5rem"},
    )
