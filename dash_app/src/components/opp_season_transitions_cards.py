"""
Opponent Analysis — Transitions Overview Season Aggregate (Offensive + Defensive)
=================================================================================
Season-aggregate Transitions Overview for Opponent Analysis.

Unlike Pressing / Castle / Chances Conceded (three distinct concepts, three
files), Offensive and Defensive Transitions are the SAME concept mirrored, so
this single module is parametrised by ``side``:

    side = "offensive"  → P1/P2/P3 outcomes, green lights map,
                          zone groups mid / mid_low / low,
                          component IDs  opp-season-trans-off-*
    side = "defensive"  → N1/N2/N3 outcomes, red lights map,
                          zone groups high / mid / low,
                          + two extra KPIs (immediate press / drop back),
                          component IDs  opp-season-trans-def-*

Data source: transitions_summary_{season}.parquet (one row per team), built by
precompute_season_transitions(). Columns are off_ / def_ prefixed.

Pattern mirrors opp_season_castle_cards.py exactly:
  · _load_transitions_parquet() → cache_get/cache_set → pd.read_parquet
  · _filter_team() via canonical_name(...).lower()
  · compute_season_transitions(season, team, side) → flat dict
  · _modal_kpi + _league_table league-comparison modals for headline KPIs
  · build_unified_modal() chrome for all modals; new single-team body for the
    zone / corridor outcome breakdowns
  · _build_transitions_lights() 18-zone density map (theme-aware — Phase 4)
"""

from __future__ import annotations

import json
from typing import Literal

import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
from dash import dcc, html

from src.config import READY_DATA_DIR
from src.team_mapping import canonical_name
from src.styling.theme import COLORS_DARK, SEMANTIC_COLORS
from src.styling.plotly_template import apply_chart_theme
from src.styling.pitch_utils import draw_pitch
from src.styling.ui_components import build_unified_modal, ds_header
from src.utils.caching import cache_get, cache_set
from src.utils.logging import log

Side = Literal["offensive", "defensive"]

# ══════════════════════════════════════════════════════════════════════════════
# PER-SIDE CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

PRIMARY    = COLORS_DARK["accent"]                  # "#8a1f33"
_HIGHLIGHT = COLORS_DARK["accent"]

CORRIDOR_COLORS = {
    "L": SEMANTIC_COLORS["corridor_left"],
    "C": SEMANTIC_COLORS["corridor_centre"],
    "R": SEMANTIC_COLORS["corridor_right"],
}
CORRIDOR_LABELS = {"L": "Left", "C": "Centre", "R": "Right"}
_CORRIDOR_ICONS = {"L": "bi-arrow-left", "C": "bi-arrows-expand-vertical", "R": "bi-arrow-right"}

# Everything that branches on side lives in this single config dict.
_SIDE_CONFIG: dict[str, dict] = {
    "offensive": {
        "id":        "opp-season-trans-off",
        "prefix":    "off_",
        "store":     "opp-season-trans-off-store",
        "label":     "Offensive Transitions",
        "icon":      "bi-lightning-charge-fill",
        "blurb":     "What the team does after winning the ball — outcomes, "
                     "zones and recovery origins, season aggregate",
        "tiers":     ("P1", "P2", "P3"),
        "tier_cols": {"P1": "p1_total", "P2": "p2_total", "P3": "p3_total"},
        "tier_colors": {
            "P1": SEMANTIC_COLORS["transition_p1"],
            "P2": SEMANTIC_COLORS["transition_p2"],
            "P3": SEMANTIC_COLORS["transition_p3"],
        },
        "tier_labels": {
            "P1": "P1 — Sustained (15s+ or reached final third)",
            "P2": "P2 — Threatening (corner / free kick / cross in final third)",
            "P3": "P3 — Dangerous (shot / goal / penalty)",
        },
        "zone_keys":   ("mid", "mid_low", "low"),
        "zone_labels": {"mid": "Mid", "mid_low": "Def. Third", "low": "Own Box"},
        "lights_color": "green",
        "lights_title": "Threatening Transition Origins (P2 / P3)",
        "lights_blurb": "Season-aggregate density of transitions reaching a "
                        "Threatening (P2) or Dangerous (P3) outcome — brighter "
                        "green = more high-value counter-attacks from that zone",
        "extra_kpis":  False,
    },
    "defensive": {
        "id":        "opp-season-trans-def",
        "prefix":    "def_",
        "store":     "opp-season-trans-def-store",
        "label":     "Defensive Transitions",
        "icon":      "bi-shield-shaded",
        "blurb":     "What happens after the team loses the ball — opponent "
                     "outcomes, zones and loss origins, season aggregate",
        "tiers":     ("N1", "N2", "N3"),
        "tier_cols": {"N1": "n1_total", "N2": "n2_total", "N3": "n3_total"},
        "tier_colors": {
            "N1": SEMANTIC_COLORS["transition_n1"],
            "N2": SEMANTIC_COLORS["transition_n2"],
            "N3": SEMANTIC_COLORS["transition_n3"],
        },
        "tier_labels": {
            "N1": "N1 — Sustained (opp held 15s+ or reached final third)",
            "N2": "N2 — Threatening (opp corner / free kick / cross in final third)",
            "N3": "N3 — Dangerous (opp shot / goal / penalty)",
        },
        "zone_keys":   ("high", "mid", "low"),
        "zone_labels": {"high": "Att. Third", "mid": "Middle", "low": "Def. Third"},
        "lights_color": "red",
        "lights_title": "Dangerous Transition Origins (N2 / N3)",
        "lights_blurb": "Season-aggregate density of transitions the opponent "
                        "turned Threatening (N2) or Dangerous (N3) — brighter "
                        "red = more high-value opponent counters from that zone",
        "extra_kpis":  True,
    },
}


def _cfg(side: Side) -> dict:
    return _SIDE_CONFIG[side]


# 18-zone grid edges (shared taxonomy — see pitch_zones.py / goalkeeper_buildup.xy_to_zone)
_X_EDGES = [0, 16.67, 33.33, 50.0, 66.67, 83.33, 100.0]
_Y_EDGES = [0, 33.33, 66.67, 100.0]


# ══════════════════════════════════════════════════════════════════════════════
# DATA LAYER
# ══════════════════════════════════════════════════════════════════════════════

def _load_transitions_parquet(season: str) -> pd.DataFrame | None:
    cache_key = f"opp_transitions_summary_{season}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    path = READY_DATA_DIR / f"transitions_summary_{season}.parquet"
    if not path.exists():
        log.warning("Transitions parquet missing: %s — run precompute_season_transitions()", path.name)
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


def load_league_transitions_summary(season: str) -> pd.DataFrame | None:
    """Return the full transitions_summary_{season}.parquet (all teams)."""
    return _load_transitions_parquet(season)


def compute_season_transitions(season: str, team_name: str, side: Side) -> dict:
    """Return all transitions season-aggregate data for one team and side."""
    cfg = _cfg(side)
    p = cfg["prefix"]
    t1, t2, t3 = cfg["tiers"]

    df = _load_transitions_parquet(season)
    row_df = _filter_team(df, team_name)

    if row_df.empty:
        return _empty_result(season, team_name, side)

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

    outcomes_by_zone     = _json_col(f"{p}outcomes_by_zone_json", "{}")
    outcomes_by_corridor = _json_col(f"{p}outcomes_by_corridor_json", "{}")
    _raw_lights = _json_col(f"{p}zone_lights_json", "{}")
    zone_lights = {}
    for k, v in _raw_lights.items():
        try:
            zone_lights[int(k)] = int(v)
        except (TypeError, ValueError):
            pass

    result = {
        "total_total":         _i(f"{p}total_total"),
        "total_per_match":     _f(f"{p}total_per_match"),
        "qualified_total":     _i(f"{p}qualified_total"),
        "qualified_per_match": _f(f"{p}qualified_per_match"),
        "transition_rate":     _f(f"{p}transition_rate"),
        "outcome_distribution": {
            t1: _i(f"{p}{cfg['tier_cols'][t1]}"),
            t2: _i(f"{p}{cfg['tier_cols'][t2]}"),
            t3: _i(f"{p}{cfg['tier_cols'][t3]}"),
        },
        "outcomes_by_zone":     outcomes_by_zone,
        "outcomes_by_corridor": outcomes_by_corridor,
        "zone_lights":          zone_lights,
        "season":         str(row.get("season", season)),
        "team":           team_name,
        "matches_played": _i("matches_played", 1),
        "side":           side,
    }

    if cfg["extra_kpis"]:
        result["immediate_press_rate"] = _f(f"{p}immediate_press_rate")
        result["drop_back_rate"]       = _f(f"{p}drop_back_rate")

    return result


def _empty_result(season: str, team_name: str, side: Side) -> dict:
    cfg = _cfg(side)
    t1, t2, t3 = cfg["tiers"]
    res = {
        "total_total": 0, "total_per_match": 0.0,
        "qualified_total": 0, "qualified_per_match": 0.0,
        "transition_rate": 0.0,
        "outcome_distribution": {t1: 0, t2: 0, t3: 0},
        "outcomes_by_zone": {}, "outcomes_by_corridor": {},
        "zone_lights": {},
        "season": season, "team": team_name, "matches_played": 0,
        "side": side,
    }
    if cfg["extra_kpis"]:
        res["immediate_press_rate"] = 0.0
        res["drop_back_rate"] = 0.0
    return res


# ══════════════════════════════════════════════════════════════════════════════
# SHARED UI HELPERS  (mirrors opp_season_castle_cards.py)
# ══════════════════════════════════════════════════════════════════════════════

def _expand_icon() -> html.I:
    return html.I(
        className="bi bi-box-arrow-up-right",
        style={"fontSize": "0.65rem", "color": "rgba(255,255,255,0.25)",
               "position": "absolute", "top": "6px", "right": "8px"},
    )


def _modal_kpi(label: str, value, subtitle: str, color: str, icon: str,
               click_id: str) -> html.Div:
    """KPI card with expand icon — clickable, opens a modal."""
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


def _mini_kpi(label: str, value, subtitle: str, color: str, icon: str) -> html.Div:
    """Non-clickable KPI card."""
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
        ],
        className="kpi-card",
    )


# ══════════════════════════════════════════════════════════════════════════════
# LEAGUE-COMPARISON TABLE BUILDER  (identical format to the completed blocks)
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
    """Ranked table of all teams by a single metric, selected team highlighted."""
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
            html.Span("#",          style={"width": "2rem", "color": "#8899aa",
                                           "fontSize": "0.75rem", "flexShrink": "0"}),
            html.Span("Team",       style={"flex": "1", "color": "#8899aa",
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
# SECTION A — Overview KPI Row  (clickable league-comparison cards)
# ══════════════════════════════════════════════════════════════════════════════

def _section_overview(d: dict, side: Side) -> html.Div:
    cfg = _cfg(side)
    cid = cfg["id"]

    total_pm = d.get("total_per_match", 0.0)
    total_n  = d.get("total_total", 0)
    qual_pm  = d.get("qualified_per_match", 0.0)
    qual_n   = d.get("qualified_total", 0)
    rate     = d.get("transition_rate", 0.0)

    cards = [
        _modal_kpi(
            "Transitions / Match", f"{total_pm:.1f}",
            f"Total: {total_n}",
            PRIMARY, "bi-arrow-repeat",
            f"{cid}-kpi-total",
        ),
        _modal_kpi(
            "Qualifying / Match", f"{qual_pm:.1f}",
            f"Total: {qual_n}",
            SEMANTIC_COLORS["outcome_positive"] if side == "offensive"
            else SEMANTIC_COLORS["outcome_negative"],
            "bi-funnel-fill",
            f"{cid}-kpi-qualified",
        ),
        _modal_kpi(
            "Qualifying Rate", f"{rate:.1f}%",
            "qualified ÷ total transitions",
            PRIMARY, "bi-percent",
            f"{cid}-kpi-rate",
        ),
    ]

    if cfg["extra_kpis"]:
        cards.append(
            _modal_kpi(
                "Immediate Press", f"{d.get('immediate_press_rate', 0.0):.1f}%",
                "counter-press ≤ 5s after loss",
                SEMANTIC_COLORS["press_mid"], "bi-stopwatch-fill",
                f"{cid}-kpi-press",
            )
        )
        cards.append(
            _modal_kpi(
                "Organised Drop", f"{d.get('drop_back_rate', 0.0):.1f}%",
                "no press / drop back > 10s",
                SEMANTIC_COLORS["press_low"], "bi-arrow-down-square-fill",
                f"{cid}-kpi-drop",
            )
        )

    return html.Div(
        [
            html.H6("Season Overview", className="buildup-subsection-title"),
            html.Div(cards, className="team-kpi-row"),
        ],
    )


# ══════════════════════════════════════════════════════════════════════════════
# SECTION B — Outcome distribution donut  +  zone / corridor modal triggers
# ══════════════════════════════════════════════════════════════════════════════

def _outcome_donut(d: dict, side: Side) -> go.Figure:
    """Donut of the tier distribution (P1/P2/P3 or N1/N2/N3), GK-donut style."""
    cfg = _cfg(side)
    tiers  = cfg["tiers"]
    colors = cfg["tier_colors"]
    labels = cfg["tier_labels"]
    od     = d.get("outcome_distribution", {})

    counts = [od.get(t, 0) for t in tiers]
    total  = sum(counts) or 1

    seg_text = [f"{v / total * 100:.0f}%" if v / total >= 0.03 else "" for v in counts]
    custom   = [f"{labels[t]}<br>n={v}<br>{v / total * 100:.1f}%"
                for t, v in zip(tiers, counts)]

    def _short_label(t: str) -> str:
        parts = labels[t].split("—", 1)
        desc = parts[1].strip() if len(parts) > 1 else labels[t]
        return f"{t} — {desc}"

    fig = go.Figure(
        go.Pie(
            labels=[_short_label(t) for t in tiers],
            values=counts,
            text=seg_text,
            customdata=custom,
            marker=dict(
                colors=[colors[t] for t in tiers],
                line=dict(color="rgba(255,255,255,0.18)", width=1.5),
            ),
            textinfo="text",
            textposition="outside",
            textfont=dict(size=12),
            hole=0.60,
            hovertemplate="%{customdata}<extra></extra>",
            sort=False,
            direction="clockwise",
            showlegend=True,
        )
    )
    apply_chart_theme(fig, "dark")
    fig.add_annotation(
        text=f"<b>{d.get('qualified_total', 0)}</b><br><span style='font-size:10px'>qualifying</span>",
        x=0.5, y=0.5, showarrow=False, font=dict(size=18),
    )
    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10), height=260,
        showlegend=True,
        legend=dict(orientation="v", yanchor="middle", y=0.5, xanchor="left", x=1.02,
                    font=dict(size=10)),
    )
    return fig


def _section_outcomes(d: dict, side: Side) -> html.Div:
    cfg = _cfg(side)
    cid = cfg["id"]
    return html.Div(
        [
            html.H6("Outcome Distribution", className="buildup-subsection-title"),
            html.P(
                "Share of qualifying transitions by outcome tier "
                f"({' · '.join(cfg['tiers'])}).",
                className="kpi-subtitle", style={"marginBottom": "0.5rem"},
            ),
            html.Div(
                dcc.Graph(
                    id=f"{cid}-outcome-donut",
                    figure=_outcome_donut(d, side),
                    config={"displayModeBar": False},
                ),
            ),
            html.Div(
                [
                    _modal_kpi(
                        "Outcomes by Zone", "›",
                        "tier split per pitch zone",
                        PRIMARY, "bi-grid-3x3-gap-fill",
                        f"{cid}-kpi-by-zone",
                    ),
                    _modal_kpi(
                        "Outcomes by Corridor", "›",
                        "tier split per corridor",
                        PRIMARY, "bi-distribute-vertical",
                        f"{cid}-kpi-by-corridor",
                    ),
                ],
                className="team-kpi-row", style={"marginTop": "0.75rem"},
            ),
        ],
    )


# ══════════════════════════════════════════════════════════════════════════════
# SINGLE-TEAM ZONE / CORRIDOR OUTCOME BREAKDOWN  (new modal bodies — Decision 4)
# ══════════════════════════════════════════════════════════════════════════════

def _grouped_outcome_bar(
    by_group: dict, group_keys: tuple[str, ...], group_labels: dict,
    side: Side, x_title: str,
) -> go.Figure:
    """Grouped bar — one cluster per zone/corridor, one bar per outcome tier."""
    cfg = _cfg(side)
    tiers  = cfg["tiers"]
    colors = cfg["tier_colors"]
    labels = cfg["tier_labels"]
    cats   = [group_labels[k] for k in group_keys]

    fig = go.Figure()
    for t in tiers:
        fig.add_trace(go.Bar(
            name=t,
            x=cats,
            y=[by_group.get(k, {}).get(t, 0) for k in group_keys],
            marker_color=colors[t],
            hovertemplate=f"{labels[t]}<br>%{{x}}: %{{y}}<extra></extra>",
        ))
    apply_chart_theme(fig, "dark")
    fig.update_layout(
        barmode="group",
        margin=dict(l=40, r=10, t=20, b=40), height=320,
        xaxis=dict(title=x_title, showgrid=False, fixedrange=True,
                   tickfont=dict(size=11)),
        yaxis=dict(title="Transitions", showgrid=True,
                   gridcolor="rgba(255,255,255,0.06)", fixedrange=True,
                   tickfont=dict(size=10)),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1,
                    font=dict(size=11)),
    )
    return fig


def _zone_breakdown_body(d: dict, side: Side) -> html.Div:
    cfg = _cfg(side)
    by_zone = d.get("outcomes_by_zone", {})
    return html.Div(
        [
            html.P(
                f"{cfg['label']} outcomes ({' / '.join(cfg['tiers'])}) by pitch zone, "
                f"season aggregate — {d.get('team', '')}.",
                className="kpi-subtitle", style={"marginBottom": "0.6rem"},
            ),
            dcc.Graph(
                figure=_grouped_outcome_bar(
                    by_zone, cfg["zone_keys"], cfg["zone_labels"], side, "Zone",
                ),
                config={"displayModeBar": False},
            ),
        ],
        style={"padding": "0.5rem"},
    )


def _corridor_breakdown_body(d: dict, side: Side) -> html.Div:
    cfg = _cfg(side)
    by_corr = d.get("outcomes_by_corridor", {})
    return html.Div(
        [
            html.P(
                f"{cfg['label']} outcomes ({' / '.join(cfg['tiers'])}) by corridor, "
                f"season aggregate — {d.get('team', '')}.",
                className="kpi-subtitle", style={"marginBottom": "0.6rem"},
            ),
            dcc.Graph(
                figure=_grouped_outcome_bar(
                    by_corr, ("L", "C", "R"), CORRIDOR_LABELS, side, "Corridor",
                ),
                config={"displayModeBar": False},
            ),
        ],
        style={"padding": "0.5rem"},
    )


# ══════════════════════════════════════════════════════════════════════════════
# SECTION C — Corridor distribution tiles
# ══════════════════════════════════════════════════════════════════════════════

def _section_corridors(d: dict, side: Side) -> html.Div:
    """Static corridor tiles using QUALIFIED transition totals per corridor."""
    by_corr = d.get("outcomes_by_corridor", {})
    tiers = _cfg(side)["tiers"]

    counts = {
        c: sum(by_corr.get(c, {}).get(t, 0) for t in tiers)
        for c in ("L", "C", "R")
    }
    grand = max(sum(counts.values()), 1)
    pcts = {c: round(counts[c] / grand * 100, 1) for c in ("L", "C", "R")}

    kpis = [
        _mini_kpi(
            CORRIDOR_LABELS[k], counts[k], f"{pcts[k]:.1f}%",
            CORRIDOR_COLORS[k], _CORRIDOR_ICONS[k],
        )
        for k in ("L", "C", "R")
    ]

    return html.Div(
        [
            html.H6("Qualifying Transitions by Corridor",
                    className="buildup-subsection-title"),
            html.Div(kpis, className="team-kpi-row",
                     style={"flexDirection": "row", "gap": "0.5rem"}),
        ],
    )


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 4 — ORIGINS DENSITY "LIGHTS" MAP  (theme-aware)
# ══════════════════════════════════════════════════════════════════════════════

def _lights_ramp(intensity: float, color: str) -> str:
    """
    Single-hue zone fill ramp. ``intensity`` in [0, 1].

    color = "green" → neutral grey → vivid green
    color = "red"   → neutral grey → vivid red

    Neutral base reads on both light and dark backgrounds; the lit colour is
    fully saturated at high intensity so the brightest zones pop regardless of
    theme.
    """
    # Neutral grey base (slate) → target hue.
    base = (90, 100, 116)
    if color == "green":
        target = (34, 197, 94)     # #22c55e
    else:
        target = (239, 68, 68)     # #ef4444
    r = int(base[0] + (target[0] - base[0]) * intensity)
    g = int(base[1] + (target[1] - base[1]) * intensity)
    b = int(base[2] + (target[2] - base[2]) * intensity)
    a = 0.18 + 0.62 * intensity
    return f"rgba({r},{g},{b},{a:.2f})"


def _build_transitions_lights(
    zone_counts: dict[int, int], side: Side, theme: str = "dark",
) -> go.Figure:
    """
    Full-pitch 18-zone density map of threatening transition origins.

    Structure follows _build_castle_heatmap() (18 add_shape rects, count
    annotations, draw_pitch base) but:
      · green ramp for offensive, red ramp for defensive,
      · intensity driven by the P2/P3 (or N2/N3) count per zone,
      · zones with zero threat stay dim neutral,
      · theme-aware (Phase 4) — pass theme="dark"|"light".
    """
    cfg = _cfg(side)
    color = cfg["lights_color"]
    fig = go.Figure()

    _COLS = 3
    max_count = max(zone_counts.values(), default=1) or 1

    # Text colour adapts to theme so counts stay legible on a light pitch.
    text_base = "255,255,255" if theme != "light" else "26,26,46"

    for zone_num in range(1, 19):
        row = (zone_num - 1) // _COLS
        col = (zone_num - 1) % _COLS
        x0, x1 = _X_EDGES[row], _X_EDGES[row + 1]
        y0, y1 = _Y_EDGES[col], _Y_EDGES[col + 1]
        count = zone_counts.get(zone_num, 0)

        intensity = count / max_count if count > 0 else 0.0
        fill = _lights_ramp(intensity, color) if count > 0 else (
            "rgba(120,130,146,0.06)" if theme != "light" else "rgba(120,130,146,0.05)"
        )

        fig.add_shape(
            type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
            line=dict(color="rgba(120,130,146,0.20)", width=1),
            fillcolor=fill, layer="below",
        )

        if count > 0:
            text_a = 0.45 + 0.55 * intensity
            fig.add_annotation(
                x=(x0 + x1) / 2, y=(y0 + y1) / 2,
                text=f"<b>{count}</b>", showarrow=False,
                font=dict(size=14, color=f"rgba({text_base},{text_a:.2f})"),
            )

    apply_chart_theme(fig, theme)
    draw_pitch(fig, theme=theme, title=cfg["lights_title"],
               height=430, show_legend=False, draw_zones=True)
    return fig


# ══════════════════════════════════════════════════════════════════════════════
# MODALS
# ══════════════════════════════════════════════════════════════════════════════

def _build_all_modals(side: Side) -> list:
    cfg = _cfg(side)
    cid = cfg["id"]
    modals = []

    # League-comparison KPI modals
    kpi_modals = [
        ("total",     "Transitions / Match — League Comparison"),
        ("qualified", "Qualifying Transitions / Match — League Comparison"),
        ("rate",      "Qualifying Rate — League Comparison"),
    ]
    if cfg["extra_kpis"]:
        kpi_modals.append(("press", "Immediate Press Rate — League Comparison"))
        kpi_modals.append(("drop",  "Organised Drop Rate — League Comparison"))

    for slug, title in kpi_modals:
        modals.append(build_unified_modal(
            modal_id=f"{cid}-modal-{slug}",
            title_id=f"{cid}-modal-{slug}-title",
            body_id =f"{cid}-modal-{slug}-body",
            title   =title,
            size    ="md",
        ))

    # Single-team zone / corridor breakdown modals (new layout)
    modals.append(build_unified_modal(
        modal_id=f"{cid}-modal-by-zone",
        title_id=f"{cid}-modal-by-zone-title",
        body_id =f"{cid}-modal-by-zone-body",
        title   =f"{cfg['label']} — Outcomes by Zone",
        size    ="lg",
    ))
    modals.append(build_unified_modal(
        modal_id=f"{cid}-modal-by-corridor",
        title_id=f"{cid}-modal-by-corridor-title",
        body_id =f"{cid}-modal-by-corridor-body",
        title   =f"{cfg['label']} — Outcomes by Corridor",
        size    ="lg",
    ))

    return modals


# ══════════════════════════════════════════════════════════════════════════════
# STORE
# ══════════════════════════════════════════════════════════════════════════════

def _store(d: dict, side: Side) -> dcc.Store:
    cfg = _cfg(side)
    payload = {
        "season":               d.get("season", ""),
        "team":                 d.get("team", ""),
        "side":                 side,
        "outcomes_by_zone":     d.get("outcomes_by_zone", {}),
        "outcomes_by_corridor": d.get("outcomes_by_corridor", {}),
        "zone_lights":          d.get("zone_lights", {}),
    }
    return dcc.Store(id=cfg["store"], data=payload)


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def build_transitions_section(
    season: str, team_name: str, side: Side = "offensive",
    theme: str = "dark",
) -> html.Div:
    """
    Build the full season-aggregate Transitions section for one side.
    Called lazily by the opp-section-trans-{off,def} loader callbacks.
    """
    cfg = _cfg(side)
    cid = cfg["id"]
    season_label = season.replace("_", "/")
    d = compute_season_transitions(season, team_name, side)

    no_data_banner = None
    if d["total_total"] == 0:
        no_data_banner = dbc.Alert(
            [
                html.I(className="bi bi-exclamation-triangle-fill me-2"),
                f"No {cfg['label'].lower()} data found for {team_name} "
                f"({season_label}). Run precompute_season_transitions() to "
                "generate the parquet.",
            ],
            color="warning", className="mb-3",
        )

    _hr = html.Hr(style={"borderColor": "var(--border-light)", "margin": "1.5rem 0"})

    return html.Div(
        [
            ds_header(
                "Opponent Analysis — Season View",
                cfg["icon"],
                f"{cfg['label']} — {team_name}  ({season_label})",
                cfg["blurb"],
            ),
            _store(d, side),
            *_build_all_modals(side),
            *([] if no_data_banner is None else [no_data_banner]),

            # A — Overview KPIs (clickable league-comparison cards)
            html.Div(_section_overview(d, side), style={"marginBottom": "1.5rem"}),

            _hr,

            # B — Outcome distribution donut + zone/corridor modal triggers
            html.Div(_section_outcomes(d, side), style={"marginBottom": "1.5rem"}),

            _hr,

            # C — Corridor tiles
            html.Div(_section_corridors(d, side), style={"marginBottom": "1.5rem"}),

            _hr,

            # D — Origins density lights map (theme-aware; NOT in a
            #     pitch-dark-container so the theme toggle can repaint it via
            #     the dedicated rebuild callback)
            html.Div(
                [
                    html.H6("Pitch Map — Transition Origins Density",
                            className="buildup-subsection-title"),
                    html.P(cfg["lights_blurb"], className="kpi-subtitle",
                           style={"marginBottom": "0.5rem"}),
                    html.Div(
                        dcc.Graph(
                            id=f"{cid}-lights",
                            figure=_build_transitions_lights(
                                d.get("zone_lights", {}), side, theme,
                            ),
                            config={"displayModeBar": False},
                        ),
                        className="pitch-transitions-lights",
                    ),
                ],
                style={"marginBottom": "1.5rem"},
            ),
        ],
        className="analysis-section buildup-card ma-card",
        style={"marginBottom": "2rem", "padding": "1.5rem"},
    )
