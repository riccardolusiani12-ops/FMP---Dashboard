"""
Opponent Analysis — Defensive Phase: Chances Conceded Season Aggregate (D4)
===========================================================================
Season-aggregate Chances Conceded section for Opponent Analysis.

# Keys from analyse_chance_conceded() (per match):
#   chain_to_concede_matrix  — {origin: {N, xG, SoT%, GC}}
#   shot_metrics             — {shots_total, shots_in_box, shots_out_box,
#                               sot_pct_total, xg_per_shot, shot_freq_pct,
#                               pct_in_box, pct_out_box}
#   shots_detail             — list of {x, y, origin, is_goal, on_target,
#                               in_box, xG, quality_tier, player, minute}
#   shot_quality_tiers       — {level_3_converted: {count, pct},
#                               level_2_threat: {count, pct},
#                               level_0_low: {count, pct}}
#   goals_conceded, xg_against, big_chances_conceded, opponent
#
# Parquet: chances_conceded_summary_{season}.parquet
# Schema: season, team, num_matches,
#   total_shots, shots_per_match,
#   on_target_total, on_target_per_match,
#   goals_conceded_total, goals_conceded_per_match,
#   big_chances_total, big_chances_per_match,
#   xg_conceded_total, xg_conceded_per_match,
#   {origin_slug}_total, {origin_slug}_per_match, {origin_slug}_pct
#     (origins: set_piece, high_regain, cross, through_ball, cut_back,
#               individual_play, combination)
#   shots_json, zone_shot_counts_json,
#   tier_level_3_converted_{total,per_match,pct},
#   tier_level_2_threat_{total,per_match,pct},
#   tier_level_0_low_{total,per_match,pct}
#
# Component ID prefix: opp-season-cc-conceded-
# IDs introduced:
#   opp-season-cc-conceded-store
#   opp-season-cc-conceded-kpi-shots-pm
#   opp-season-cc-conceded-kpi-on-target-pm
#   opp-season-cc-conceded-kpi-goals-pm
#   opp-season-cc-conceded-kpi-big-chances-pm
#   opp-season-cc-conceded-kpi-xg-pm
#   opp-season-cc-conceded-kpi-origin-{slug}   (one per origin)
#   opp-season-cc-conceded-modal-shots-pm       / -title / -body
#   opp-season-cc-conceded-modal-on-target-pm   / -title / -body
#   opp-season-cc-conceded-modal-goals-pm       / -title / -body
#   opp-season-cc-conceded-modal-big-chances-pm / -title / -body
#   opp-season-cc-conceded-modal-xg-pm          / -title / -body
#   opp-season-cc-conceded-modal-origin-{slug}  / -title / -body
#   opp-season-cc-conceded-pitch-zone-grid  (18-zone pitch map)
"""

from __future__ import annotations

import json

import dash_bootstrap_components as dbc
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

from src.analytics.chance_creation import ORIGIN_LABELS
from src.components.chance_creation_cards import TIER_META

# ── Palette ──────────────────────────────────────────────────────────────────
_HIGHLIGHT = COLORS_DARK["accent"]          # "#8a1f33"
PRIMARY    = COLORS_DARK["accent"]

ORIGIN_COLORS: dict[str, str] = {
    "Set Piece":       SEMANTIC_COLORS["origin_set_piece"],
    "High Regain":     SEMANTIC_COLORS["origin_high_regain"],
    "Cross":           SEMANTIC_COLORS["origin_cross"],
    "Through Ball":    SEMANTIC_COLORS["origin_through_ball"],
    "Cut Back":        SEMANTIC_COLORS["origin_cut_back"],
    "Individual Play": SEMANTIC_COLORS["origin_individual_play"],
    "Combination":     SEMANTIC_COLORS["origin_combination"],
}

ORIGIN_ICONS: dict[str, str] = {
    "Set Piece":       "bi-flag-fill",
    "High Regain":     "bi-shield-fill-exclamation",
    "Cross":           "bi-arrow-up-right",
    "Through Ball":    "bi-chevron-double-up",
    "Cut Back":        "bi-arrow-return-left",
    "Individual Play": "bi-person-fill-up",
    "Combination":     "bi-shuffle",
}

# Slugify origin name → parquet column prefix
def _origin_slug(origin: str) -> str:
    return origin.lower().replace(" ", "_")

# 18-zone grid edges (full pitch)
_X_EDGES = [0.0, 16.67, 33.33, 50.0, 66.67, 83.33, 100.0]
_Y_EDGES = [0.0, 33.33, 66.67, 100.0]
_N_COLS  = 3


# ═══════════════════════════════════════════════════════════════════════════════
# DATA LAYER
# ═══════════════════════════════════════════════════════════════════════════════

def _load_cc_parquet(season: str) -> pd.DataFrame | None:
    cache_key = f"opp_cc_conceded_{season}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    path = READY_DATA_DIR / f"chances_conceded_summary_{season}.parquet"
    if not path.exists():
        log.warning("Chances Conceded parquet missing: %s — run precompute_season_chances_conceded()", path.name)
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


def compute_season_cc_conceded(season: str, team_name: str) -> dict:
    """Return all chances-conceded season-aggregate data for one team."""
    df = _load_cc_parquet(season)
    row_df = _filter_team(df, team_name)

    if row_df.empty:
        return _empty_result()

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

    # Parse shot coords JSON
    try:
        shots = json.loads(str(row.get("shots_json", "[]")))
    except (ValueError, TypeError):
        shots = []

    # Parse zone shot counts JSON
    try:
        _raw_zones = json.loads(str(row.get("zone_shot_counts_json", "{}")))
        zone_shot_counts = {int(k): int(v) for k, v in _raw_zones.items()}
    except (ValueError, TypeError):
        zone_shot_counts = {}

    # Attack origin breakdown
    origin_data: dict[str, dict] = {}
    for origin in ORIGIN_LABELS:
        slug = _origin_slug(origin)
        raw_conv = row.get(f"{slug}_conversion_pct")
        origin_data[origin] = {
            "total":          _i(f"{slug}_total"),
            "per_match":      _f(f"{slug}_per_match"),
            "pct":            _f(f"{slug}_pct"),
            "goals_total":    _i(f"{slug}_goals_total"),
            "conversion_pct": None if (raw_conv is None or raw_conv != raw_conv) else float(raw_conv),
        }

    # Shot quality tiers
    tier_data: dict[str, dict] = {}
    for tk in ("level_3_converted", "level_2_threat", "level_0_low"):
        tier_data[tk] = {
            "total":     _i(f"tier_{tk}_total"),
            "per_match": _f(f"tier_{tk}_per_match"),
            "pct":       _f(f"tier_{tk}_pct"),
        }

    return {
        "season":                  str(row.get("season", season)),
        "team":                    team_name,
        "num_matches":             _i("num_matches", 1),
        "total_shots":             _i("total_shots"),
        "shots_per_match":         _f("shots_per_match"),
        "on_target_total":         _i("on_target_total"),
        "on_target_per_match":     _f("on_target_per_match"),
        "goals_conceded_total":    _i("goals_conceded_total"),
        "goals_conceded_per_match": _f("goals_conceded_per_match"),
        "big_chances_total":       _i("big_chances_total"),
        "big_chances_per_match":   _f("big_chances_per_match"),
        "xg_conceded_total":       _f("xg_conceded_total"),
        "xg_conceded_per_match":   _f("xg_conceded_per_match"),
        "origin_data":             origin_data,
        "tier_data":               tier_data,
        "shots":                   shots,           # list of {x, y, outcome}
        "zone_shot_counts":        zone_shot_counts,  # {zone_id: count}
    }


def _empty_result() -> dict:
    return {
        "season": "", "team": "", "num_matches": 0,
        "total_shots": 0, "shots_per_match": 0.0,
        "on_target_total": 0, "on_target_per_match": 0.0,
        "goals_conceded_total": 0, "goals_conceded_per_match": 0.0,
        "big_chances_total": 0, "big_chances_per_match": 0.0,
        "xg_conceded_total": 0.0, "xg_conceded_per_match": 0.0,
        "origin_data": {o: {"total": 0, "per_match": 0.0, "pct": 0.0, "goals_total": 0, "conversion_pct": None} for o in ORIGIN_LABELS},
        "tier_data": {tk: {"total": 0, "per_match": 0.0, "pct": 0.0}
                      for tk in ("level_3_converted", "level_2_threat", "level_0_low")},
        "shots": [],
        "zone_shot_counts": {},
    }


def load_league_cc_conceded_summary(season: str) -> pd.DataFrame | None:
    """Return the full chances_conceded_summary_{season}.parquet (all teams)."""
    return _load_cc_parquet(season)


# ═══════════════════════════════════════════════════════════════════════════════
# SHARED UI HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _expand_icon() -> html.I:
    return html.I(
        className="bi bi-box-arrow-up-right",
        style={"fontSize": "0.65rem", "color": "rgba(255,255,255,0.25)",
               "position": "absolute", "top": "6px", "right": "8px"},
    )


def _modal_kpi(
    label: str, value, subtitle: str, color: str, icon: str,
    click_id: str,
) -> html.Div:
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


# ═══════════════════════════════════════════════════════════════════════════════
# LEAGUE-COMPARISON TABLE BUILDER
# ═══════════════════════════════════════════════════════════════════════════════

def _league_table(
    summary_df: pd.DataFrame | None,
    metric_col: str,
    metric_label: str,
    highlight_team: str,
    ascending: bool = False,
    fmt: str = ".1f",
    total_col: str | None = None,
    show_xg_total: bool = False,
) -> html.Div:
    """
    Ranked table: # | Team | per-match value | [% Share or xG Total].
    total_col: if supplied, render % Share = (total_col / total_shots_col * 100).
    show_xg_total: if True, show absolute total instead of % share (for xG/xGOT).
    """
    if summary_df is None or summary_df.empty:
        return html.P("No league data available.", style={"color": "#8899aa"})
    if metric_col not in summary_df.columns:
        return html.P(f"Column '{metric_col}' not found.", style={"color": "#8899aa"})

    df = summary_df.copy().dropna(subset=[metric_col])
    df = df.sort_values(metric_col, ascending=ascending).reset_index(drop=True)
    df["rank"] = range(1, len(df) + 1)

    show_extra = (total_col is not None and total_col in df.columns) or show_xg_total
    extra_label = "xG Total" if show_xg_total else "% Share"

    hl_lower = canonical_name(highlight_team).lower()

    header = html.Div(
        [
            html.Span("#",             style={"width": "2rem", "color": "#8899aa",
                                              "fontSize": "0.75rem", "flexShrink": "0"}),
            html.Span("Team",          style={"flex": "1", "color": "#8899aa",
                                              "fontSize": "0.75rem"}),
            html.Span(metric_label,    style={"color": "#8899aa", "fontSize": "0.75rem",
                                              "minWidth": "4rem", "textAlign": "right"}),
            *(
                [html.Span(extra_label, style={"color": "#8899aa", "fontSize": "0.75rem",
                                               "minWidth": "4.5rem", "textAlign": "right"})]
                if show_extra else []
            ),
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
        val_str = format(float(val), fmt)

        extra_str = None
        if show_xg_total and total_col and total_col in df.columns:
            extra_str = f"{float(row.get(total_col, 0)):.2f}"
        elif show_xg_total:
            extra_str = val_str
        elif total_col and total_col in df.columns and "total_shots" in df.columns:
            shots_total = float(row.get("total_shots", 1)) or 1
            pct = float(row.get(total_col, 0)) / shots_total * 100
            extra_str = f"{pct:.1f}%"

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
                    *(
                        [html.Span(extra_str, style={
                            "fontWeight": "700" if is_hl else "400",
                            "color": _HIGHLIGHT if is_hl else "var(--text-secondary)",
                            "fontSize": "0.85rem", "minWidth": "4.5rem", "textAlign": "right",
                        })]
                        if show_extra and extra_str is not None else []
                    ),
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


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — SHOTS CONCEDED OVERVIEW
# ═══════════════════════════════════════════════════════════════════════════════

def _section_shots_overview(d: dict) -> html.Div:
    mp   = max(d.get("num_matches", 1), 1)

    # Total chances conceded across all origins (sum of origin totals)
    origin_data = d.get("origin_data", {})
    total_origin_chances = sum(
        info.get("total", 0) for info in origin_data.values()
    )

    return html.Div(
        [
            html.H6("SHOTS CONCEDED — OVERVIEW", className="buildup-subsection-title"),
            html.Div(
                [
                    _modal_kpi(
                        "Shots / Match", f"{d['shots_per_match']:.1f}",
                        f"Total: {d['total_shots']}",
                        COLORS_DARK["accent"], "bi-crosshair",
                        "opp-season-cc-conceded-kpi-shots-pm",
                    ),
                    _modal_kpi(
                        "On Target / Match", f"{d['on_target_per_match']:.1f}",
                        f"Total: {d['on_target_total']}",
                        "#f97316", "bi-bullseye",
                        "opp-season-cc-conceded-kpi-on-target-pm",
                    ),
                    _modal_kpi(
                        "Goals Conceded / Match", f"{d['goals_conceded_per_match']:.2f}",
                        f"Total: {d['goals_conceded_total']}",
                        "#ef4444", "bi-x-circle-fill",
                        "opp-season-cc-conceded-kpi-goals-pm",
                    ),
                    _modal_kpi(
                        "Big Chances / Match", f"{d['big_chances_per_match']:.1f}",
                        f"Total: {d['big_chances_total']}",
                        "#8b5cf6", "bi-exclamation-triangle-fill",
                        "opp-season-cc-conceded-kpi-big-chances-pm",
                    ),
                    _modal_kpi(
                        "xG Conceded / Match", f"{d['xg_conceded_per_match']:.2f}",
                        f"Total: {d['xg_conceded_total']:.2f}",
                        "#ef4444", "bi-graph-down-arrow",
                        "opp-season-cc-conceded-kpi-xg-pm",
                    ),
                    _modal_kpi(
                        "Origin of Chances Conceded", str(total_origin_chances),
                        f"Across {mp} matches",
                        "#64748b", "bi-diagram-3-fill",
                        "opp-season-cc-conceded-kpi-origin-breakdown",
                    ),
                ],
                className="team-kpi-row",
            ),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — ATTACK ORIGIN BREAKDOWN
# ═══════════════════════════════════════════════════════════════════════════════

def _section_origin_breakdown(d: dict) -> html.Div:
    origin_data = d.get("origin_data", {})

    # Build stacked bar
    bar_fig = go.Figure()
    for origin in ORIGIN_LABELS:
        info = origin_data.get(origin, {})
        pct  = info.get("pct", 0.0)
        n    = info.get("total", 0)
        if n == 0:
            continue
        bar_fig.add_trace(go.Bar(
            y=["Distribution"], x=[pct], orientation="h",
            name=origin,
            marker_color=ORIGIN_COLORS.get(origin, "#6b7280"),
            text=[f"{origin} {pct:.0f}%"],
            textposition="inside",
            textfont=dict(size=10, color="#fff"),
            hovertemplate=f"{origin}: {n} ({pct:.1f}%)<extra></extra>",
        ))
    apply_chart_theme(bar_fig, "dark")
    bar_fig.update_layout(
        barmode="stack",
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=0, b=0), height=42,
        xaxis=dict(showgrid=False, showticklabels=False, range=[0, 100], fixedrange=True),
        yaxis=dict(showgrid=False, showticklabels=False, fixedrange=True),
        showlegend=False,
    )

    cards = []
    for origin in ORIGIN_LABELS:
        info = origin_data.get(origin, {})
        n    = info.get("total", 0)
        if n == 0:
            continue
        slug         = _origin_slug(origin)
        pct          = info.get("pct", 0.0)
        pm           = info.get("per_match", 0.0)
        goals_total  = info.get("goals_total", 0)
        conv_pct     = info.get("conversion_pct")
        color        = ORIGIN_COLORS.get(origin, "#6b7280")

        if conv_pct is not None:
            conv_line = html.Span(
                f"{goals_total} goals conceded ({conv_pct:.1f}% conversion)",
                className="kpi-subtitle",
                style={"color": "var(--text-muted)", "fontSize": "0.72rem"},
            )
        else:
            conv_line = None

        card_children = [
            html.Div(
                html.I(className=f"bi {ORIGIN_ICONS.get(origin, 'bi-activity')}",
                       style={"color": color, "fontSize": "1.3rem"}),
                className="kpi-icon",
            ),
            html.Div(
                [
                    html.Span(origin, className="kpi-label"),
                    html.Span(f"{pm:.1f}", className="kpi-value"),
                    html.Span(f"Total: {n}  ({pct:.1f}%)",
                              className="kpi-subtitle",
                              style={"color": color}),
                    *([] if conv_line is None else [conv_line]),
                ],
                className="kpi-text",
            ),
            _expand_icon(),
        ]
        cards.append(
            html.Div(
                card_children,
                className="kpi-card",
                id=f"opp-season-cc-conceded-kpi-origin-{slug}",
                n_clicks=0,
                style={"cursor": "pointer", "position": "relative"},
            )
        )

    return html.Div(
        [
            html.H6("ATTACK ORIGIN BREAKDOWN", className="buildup-subsection-title"),
            html.Div(
                "How the opponent built each shot conceded — "
                "priority: Set Piece → High Regain → Cross → Through Ball → Cut Back → Combination",
                style={"fontSize": "0.78rem", "color": "var(--text-muted)",
                       "marginBottom": "0.6rem"},
            ),
            html.Div(cards, className="team-kpi-row",
                     style={"flexWrap": "wrap"}),
            dcc.Graph(figure=bar_fig, config={"displayModeBar": False},
                      style={"marginTop": "0.5rem"}),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — SHOT ORIGIN ZONES — DEFENSIVE FRAME (18-zone pitch map)
# ═══════════════════════════════════════════════════════════════════════════════

def _build_zone_pitch(zone_shot_counts: dict[int, int], shots: list[dict]) -> go.Figure:
    """
    Full-pitch 18-zone grid — defensive frame.
    Zone density fill: red gradient, darker = more shots (defensive third).
    Outcome markers in bottom annotation per zone: ✕ goal/on-target, ● miss.
    """
    # Per-zone outcome split
    zone_goal_ot:  dict[int, int] = {z: 0 for z in range(1, 19)}
    zone_miss:     dict[int, int] = {z: 0 for z in range(1, 19)}

    def _classify(x: float, y: float) -> int:
        row = min(int(x / 16.67), 5)
        col = min(int(y / 33.33), 2)
        return row * 3 + col + 1

    for sc in shots:
        try:
            z = _classify(float(sc["x"]), float(sc["y"]))
        except (TypeError, ValueError, KeyError):
            continue
        outcome = sc.get("outcome", "miss")
        if outcome in ("goal", "on_target"):
            zone_goal_ot[z] += 1
        else:
            zone_miss[z] += 1

    fig = go.Figure()
    max_count = max(zone_shot_counts.values(), default=1) or 1

    for zone_num in range(1, 19):
        row = (zone_num - 1) // _N_COLS
        col = (zone_num - 1) % _N_COLS
        x0  = _X_EDGES[row]
        x1  = _X_EDGES[row + 1]
        y0  = _Y_EDGES[col]
        y1  = _Y_EDGES[col + 1]
        cx  = (x0 + x1) / 2
        cy  = (y0 + y1) / 2

        total     = zone_shot_counts.get(zone_num, 0)
        intensity = total / max_count if max_count else 0

        # Defensive zones (1-6 = own defensive third after coordinate flip) glow red
        if zone_num <= 6:
            fill_a = 0.10 + 0.60 * intensity if total else 0.04
            fill   = f"rgba(239,68,68,{fill_a:.2f})"
        else:
            fill = "rgba(255,255,255,0.02)"

        fig.add_shape(
            type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
            line=dict(color="rgba(255,255,255,0.10)", width=0.5),
            fillcolor=fill, layer="below",
        )

        if total > 0:
            fig.add_annotation(
                x=cx, y=cy + 4,
                text=f"<b>{total}</b>",
                showarrow=False,
                font=dict(size=16, color="#f0f0f0"),
            )
            fig.add_annotation(
                x=cx, y=cy - 4,
                text=f"Z{zone_num}",
                showarrow=False,
                font=dict(size=9, color="rgba(255,255,255,0.55)"),
            )
            dot_parts: list[str] = []
            if zone_goal_ot[zone_num] > 0:
                dot_parts.append(
                    f"<span style='color:#ef4444'>✕{zone_goal_ot[zone_num]}</span>"
                )
            if zone_miss[zone_num] > 0:
                dot_parts.append(
                    f"<span style='color:#6b7280'>●{zone_miss[zone_num]}</span>"
                )
            if dot_parts:
                fig.add_annotation(
                    x=cx, y=cy - 12,
                    text=" ".join(dot_parts),
                    showarrow=False,
                    font=dict(size=10),
                )
        else:
            fig.add_annotation(
                x=cx, y=cy,
                text=f"Z{zone_num}",
                showarrow=False,
                font=dict(size=9, color="rgba(255,255,255,0.18)"),
            )

    # Zone grid lines
    for y_val in (33.33, 66.67):
        fig.add_shape(type="line", x0=0, x1=100, y0=y_val, y1=y_val,
                      line=dict(color="rgba(255,255,255,0.12)", width=1), layer="below")
    for x_val in _X_EDGES[1:-1]:
        fig.add_shape(type="line", x0=x_val, x1=x_val, y0=0, y1=100,
                      line=dict(color="rgba(255,255,255,0.12)", width=1), layer="below")

    # Pitch outline
    fig.add_shape(type="rect", x0=0, x1=100, y0=0, y1=100,
                  line=dict(color="rgba(255,255,255,0.35)", width=1.5),
                  fillcolor="rgba(0,0,0,0)")
    fig.add_shape(type="line", x0=50, x1=50, y0=0, y1=100,
                  line=dict(color="rgba(255,255,255,0.25)", width=1, dash="dash"),
                  layer="below")
    # Own penalty box (defensive frame: x near 0)
    fig.add_shape(type="rect", x0=0, x1=16.5, y0=21, y1=79,
                  line=dict(color="rgba(239,68,68,0.40)", width=2),
                  fillcolor="rgba(239,68,68,0.06)")
    # Opponent penalty box
    fig.add_shape(type="rect", x0=83.5, x1=100, y0=21, y1=79,
                  line=dict(color="rgba(255,255,255,0.18)", width=1),
                  fillcolor="rgba(0,0,0,0)")
    # Defensive third boundary
    fig.add_shape(type="line", x0=33.33, x1=33.33, y0=0, y1=100,
                  line=dict(color="rgba(239,68,68,0.5)", width=2, dash="dash"))

    fig.add_annotation(x=8, y=-6, text="← OWN GOAL", showarrow=False,
                       font=dict(size=9, color="rgba(255,255,255,0.35)"))
    fig.add_annotation(x=92, y=-6, text="ATK →", showarrow=False,
                       font=dict(size=9, color="rgba(255,255,255,0.35)"))

    apply_chart_theme(fig, "dark")
    fig.update_layout(
        plot_bgcolor="rgba(15,25,35,0.7)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=10, b=20), height=400,
        xaxis=dict(range=[-2, 102], showgrid=False, showticklabels=False,
                   fixedrange=True, zeroline=False),
        yaxis=dict(range=[-10, 105], showgrid=False, showticklabels=False,
                   fixedrange=True, zeroline=False,
                   scaleanchor="x", scaleratio=0.68),
        showlegend=False,
    )
    return fig


def _section_pitch_map(d: dict) -> html.Div:
    shots            = d.get("shots", [])
    zone_shot_counts = d.get("zone_shot_counts", {})

    fig = _build_zone_pitch(zone_shot_counts, shots)

    return html.Div(
        [
            html.H6("SHOT ORIGIN ZONES — DEFENSIVE FRAME",
                    className="buildup-subsection-title"),
            html.Div(
                [
                    html.Span("✕ ", style={"color": "#ef4444", "fontSize": "0.85rem"}),
                    html.Span("on target / goal conceded", style={
                        "fontSize": "0.75rem", "color": "var(--text-muted)",
                        "marginRight": "1rem"}),
                    html.Span("● ", style={"color": "#6b7280", "fontSize": "0.85rem"}),
                    html.Span("miss / blocked", style={
                        "fontSize": "0.75rem", "color": "var(--text-muted)"}),
                ],
                style={"marginBottom": "0.5rem"},
            ),
            html.Div(
                dcc.Graph(
                    id="opp-season-cc-conceded-pitch-zone-grid",
                    figure=fig,
                    config={"displayModeBar": False},
                ),
                className="pitch-dark-container",
            ),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — SHOT QUALITY TIERS CONCEDED
# ═══════════════════════════════════════════════════════════════════════════════

def _section_shot_quality_tiers(d: dict) -> html.Div:
    tier_data = d.get("tier_data", {})
    _TIER_KEYS = ["level_3_converted", "level_2_threat", "level_0_low"]

    cards = []
    for tk in _TIER_KEYS:
        meta = TIER_META[tk]
        info = tier_data.get(tk, {})
        n    = info.get("total", 0)
        pm   = info.get("per_match", 0.0)
        pct  = info.get("pct", 0.0)
        cards.append(
            html.Div(
                [
                    html.Div(
                        html.I(className=f"bi {meta['icon']}",
                               style={"color": meta["color"], "fontSize": "1.3rem"}),
                        className="kpi-icon",
                    ),
                    html.Div(
                        [
                            html.Span(meta["label"], className="kpi-label"),
                            html.Span(f"{pm:.1f}", className="kpi-value"),
                            html.Span(f"Total: {n}",
                                      className="kpi-subtitle",
                                      style={"color": meta["color"]}),
                            html.Span(f"{pct:.1f}% of shots conceded",
                                      className="kpi-subtitle",
                                      style={"color": "var(--text-muted)",
                                             "fontSize": "0.72rem"}),
                        ],
                        className="kpi-text",
                    ),
                ],
                className="kpi-card",
            )
        )

    return html.Div(
        [
            html.H6("SHOT QUALITY TIERS CONCEDED", className="buildup-subsection-title"),
            html.Div(cards, className="team-kpi-row"),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# MODALS
# ═══════════════════════════════════════════════════════════════════════════════

def _build_all_modals() -> list:
    modals = []

    # Overview KPI modals
    for slug, title in [
        ("shots-pm",       "Shots / Match — League Comparison"),
        ("on-target-pm",   "On Target / Match — League Comparison"),
        ("goals-pm",       "Goals Conceded / Match — League Comparison"),
        ("big-chances-pm", "Big Chances / Match — League Comparison"),
        ("xg-pm",          "xG Conceded / Match — League Comparison"),
    ]:
        modals.append(build_unified_modal(
            modal_id=f"opp-season-cc-conceded-modal-{slug}",
            title_id=f"opp-season-cc-conceded-modal-{slug}-title",
            body_id =f"opp-season-cc-conceded-modal-{slug}-body",
            title   =title,
            size    ="md",
        ))

    # Consolidated origin-breakdown modal (single-team, no league comparison)
    modals.append(build_unified_modal(
        modal_id="opp-season-cc-conceded-modal-origin-breakdown",
        title_id="opp-season-cc-conceded-modal-origin-breakdown-title",
        body_id ="opp-season-cc-conceded-modal-origin-breakdown-body",
        title   ="Origin of Chances Conceded — Season",
        size    ="md",
    ))

    # Per-origin league-comparison modals (one per origin)
    for origin in ORIGIN_LABELS:
        slug = _origin_slug(origin)
        modals.append(build_unified_modal(
            modal_id=f"opp-season-cc-conceded-modal-origin-{slug}",
            title_id=f"opp-season-cc-conceded-modal-origin-{slug}-title",
            body_id =f"opp-season-cc-conceded-modal-origin-{slug}-body",
            title   =f"{origin} — League Comparison",
            size    ="md",
        ))

    return modals


# ═══════════════════════════════════════════════════════════════════════════════
# STORE
# ═══════════════════════════════════════════════════════════════════════════════

def _cc_store(d: dict) -> dcc.Store:
    return dcc.Store(
        id="opp-season-cc-conceded-store",
        data={
            "season": d.get("season", ""),
            "team":   d.get("team", ""),
        },
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def build_cc_conceded_section(season: str, team_name: str) -> html.Div:
    """
    Build the full season-aggregate Chances Conceded section.
    Called lazily by the opp-section-ccc callback.
    """
    season_label = season.replace("_", "/")
    d = compute_season_cc_conceded(season, team_name)

    no_data_banner = None
    if d["total_shots"] == 0:
        no_data_banner = dbc.Alert(
            [
                html.I(className="bi bi-exclamation-triangle-fill me-2"),
                f"No chances conceded data found for {team_name} ({season_label}). "
                "Run precompute_season_chances_conceded() to generate the parquet.",
            ],
            color="warning", className="mb-3",
        )

    _hr = html.Hr(style={"borderColor": "var(--border-light)", "margin": "1.5rem 0"})

    return html.Div(
        [
            ds_header(
                "Opponent Analysis — Season View",
                "bi-shield-x",
                f"Chances Conceded — {team_name}  ({season_label})",
                "Season-aggregate shots conceded — volume, xG against, attack origin "
                "breakdown, shot zones and quality tiers",
            ),
            _cc_store(d),
            *_build_all_modals(),
            *([] if no_data_banner is None else [no_data_banner]),

            # Section 1 — Shots overview KPIs
            html.Div(_section_shots_overview(d), style={"marginBottom": "1.5rem"}),

            _hr,

            # Section 2 — Attack origin breakdown
            html.Div(_section_origin_breakdown(d), style={"marginBottom": "1.5rem"}),

            _hr,

            # Section 3 — Pitch map (18-zone defensive frame)
            html.Div(_section_pitch_map(d), style={"marginBottom": "1.5rem"}),

            _hr,

            # Section 4 — Shot quality tiers
            html.Div(_section_shot_quality_tiers(d), style={"marginBottom": "1.5rem"}),
        ],
        className="analysis-section buildup-card ma-card",
        style={"marginBottom": "2rem", "padding": "1.5rem"},
    )
