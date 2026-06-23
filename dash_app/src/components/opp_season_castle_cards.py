"""
Opponent Analysis — Defensive Phase: Defensive Castle Season Aggregate (D3)
===========================================================================
Season-aggregate Defensive Castle section for Opponent Analysis.

Keys from analyse_defensive_castle() / castle_summary_{season}.parquet:
  Scalar KPIs (per team row):
    total_actions, actions_per_match,
    in_own_box_total, in_own_box_per_match,
    wide_flanks_total, wide_flanks_per_match,
    def_third_edge_total, def_third_edge_per_match,
    actions_by_type_json  (JSON: [[action, count], ...] sorted desc)
    corridor_L_n, corridor_C_n, corridor_R_n,
    corridor_L_pct, corridor_C_pct, corridor_R_pct

Parquet: READY_DATA_DIR / castle_summary_{season}.parquet

Component ID prefix: opp-season-castle-
IDs introduced:
  opp-season-castle-store
  opp-season-castle-kpi-actions-pm
  opp-season-castle-kpi-own-box
  opp-season-castle-kpi-wide-flanks
  opp-season-castle-kpi-def-edge
  opp-season-castle-kpi-action-types   (replaces old see-all button)
  opp-season-castle-modal-actions-pm   / -title / -body
  opp-season-castle-modal-own-box      / -title / -body
  opp-season-castle-modal-wide-flanks  / -title / -body
  opp-season-castle-modal-def-edge     / -title / -body
  opp-season-castle-modal-action-types / -title / -body
  opp-season-castle-corridors-bar      (stacked distribution bar graph)
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
from src.components.defensive_castle_cards import _build_castle_heatmap

# ── Palette ──────────────────────────────────────────────────────────────────
_HIGHLIGHT  = COLORS_DARK["accent"]                        # "#8a1f33"
_NEUTRAL    = SEMANTIC_COLORS["benchmark_neutral"]         # "#4a6274"
PRIMARY     = COLORS_DARK["accent"]

SUCCESS_COLOR = SEMANTIC_COLORS["outcome_positive"]
FAIL_COLOR    = SEMANTIC_COLORS["outcome_negative"]

SUBZONE_COLORS = {
    "box":            SEMANTIC_COLORS["press_high"],   # "#ef4444"
    "deep_flank":     SEMANTIC_COLORS["press_mid"],    # "#f97316"
    "def_third_edge": SEMANTIC_COLORS["press_low"],    # "#6b7280"
}

CORRIDOR_COLORS = {
    "L": SEMANTIC_COLORS["corridor_left"],
    "C": SEMANTIC_COLORS["corridor_centre"],
    "R": SEMANTIC_COLORS["corridor_right"],
}
CORRIDOR_LABELS = {"L": "Left", "C": "Centre", "R": "Right"}


# ═══════════════════════════════════════════════════════════════════════════════
# DATA LAYER
# ═══════════════════════════════════════════════════════════════════════════════

def _load_castle_parquet(season: str) -> pd.DataFrame | None:
    cache_key = f"opp_castle_summary_{season}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    path = READY_DATA_DIR / f"castle_summary_{season}.parquet"
    if not path.exists():
        log.warning("Castle parquet missing: %s — run precompute_season_castle()", path.name)
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


def compute_season_castle(season: str, team_name: str) -> dict:
    """Return all castle season-aggregate data for one team."""
    df = _load_castle_parquet(season)
    row_df = _filter_team(df, team_name)

    if row_df.empty:
        return _empty_castle_result()

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

    # Parse actions_by_type_json
    try:
        actions_by_type = json.loads(str(row.get("actions_by_type_json", "[]")))
    except (ValueError, TypeError):
        actions_by_type = []

    # Parse zone_action_counts_json — keys are str zone IDs, convert to int
    try:
        _raw_zones = json.loads(str(row.get("zone_action_counts_json", "{}")))
        zone_action_counts = {int(k): int(v) for k, v in _raw_zones.items()}
    except (ValueError, TypeError):
        zone_action_counts = {}

    return {
        "total_actions":            _i("total_actions"),
        "actions_per_match":        _f("actions_per_match"),
        "in_own_box_total":         _i("in_own_box_total"),
        "in_own_box_per_match":     _f("in_own_box_per_match"),
        "wide_flanks_total":        _i("wide_flanks_total"),
        "wide_flanks_per_match":    _f("wide_flanks_per_match"),
        "def_third_edge_total":     _i("def_third_edge_total"),
        "def_third_edge_per_match": _f("def_third_edge_per_match"),
        "actions_by_type":          actions_by_type,   # [[action, count], ...]
        "zone_action_counts":       zone_action_counts,  # {zone_id: count} zones 1-6
        "corridor_L_n":   _i("corridor_L_n"),
        "corridor_C_n":   _i("corridor_C_n"),
        "corridor_R_n":   _i("corridor_R_n"),
        "corridor_L_pct": _f("corridor_L_pct"),
        "corridor_C_pct": _f("corridor_C_pct"),
        "corridor_R_pct": _f("corridor_R_pct"),
        "season":   str(row.get("season", season)),
        "team":     team_name,
        "matches_played": _i("matches_played", 1),
    }


def _empty_castle_result() -> dict:
    return {
        "total_actions": 0, "actions_per_match": 0.0,
        "in_own_box_total": 0, "in_own_box_per_match": 0.0,
        "wide_flanks_total": 0, "wide_flanks_per_match": 0.0,
        "def_third_edge_total": 0, "def_third_edge_per_match": 0.0,
        "actions_by_type": [], "zone_action_counts": {},
        "corridor_L_n": 0, "corridor_C_n": 0, "corridor_R_n": 0,
        "corridor_L_pct": 0.0, "corridor_C_pct": 0.0, "corridor_R_pct": 0.0,
        "season": "", "team": "", "matches_played": 0,
    }


def load_league_castle_summary(season: str) -> pd.DataFrame | None:
    """Return the full castle_summary_{season}.parquet (all teams)."""
    return _load_castle_parquet(season)


# ═══════════════════════════════════════════════════════════════════════════════
# SHARED UI HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _expand_icon() -> html.I:
    return html.I(
        className="bi bi-box-arrow-up-right",
        style={"fontSize": "0.65rem", "color": "var(--text-muted)",
               "position": "absolute", "top": "6px", "right": "8px"},
    )


def _modal_kpi(
    label: str, value, subtitle: str, color: str, icon: str,
    click_id: str,
) -> html.Div:
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
    share_total_col: str | None = None,
    share_subzone_col: str | None = None,
) -> html.Div:
    """
    Ranked table of all teams by a single castle metric, selected team highlighted.

    When share_total_col and share_subzone_col are both supplied, a fourth
    "% Share" column is appended showing (subzone_total / total_actions * 100).
    """
    if summary_df is None or summary_df.empty:
        return html.P("No league data available.", style={"color": "#8899aa"})
    if metric_col not in summary_df.columns:
        return html.P(f"Column '{metric_col}' not found.", style={"color": "#8899aa"})

    df = summary_df.copy().dropna(subset=[metric_col])
    df = df.sort_values(metric_col, ascending=ascending).reset_index(drop=True)
    df["rank"] = range(1, len(df) + 1)

    show_share = (
        share_total_col is not None
        and share_subzone_col is not None
        and share_total_col in df.columns
        and share_subzone_col in df.columns
    )
    if show_share:
        df["_share_pct"] = (
            df[share_subzone_col].fillna(0) /
            df[share_total_col].clip(lower=1) * 100
        ).round(1)

    hl_lower = canonical_name(highlight_team).lower()

    header = html.Div(
        [
            html.Span("#",          style={"width": "2rem", "color": "#8899aa",
                                           "fontSize": "0.75rem", "flexShrink": "0"}),
            html.Span("Team",       style={"flex": "1", "color": "#8899aa",
                                           "fontSize": "0.75rem"}),
            html.Span(metric_label, style={"color": "#8899aa", "fontSize": "0.75rem",
                                           "minWidth": "3.5rem", "textAlign": "right"}),
            *(
                [html.Span("% Share", style={"color": "#8899aa", "fontSize": "0.75rem",
                                             "minWidth": "4rem", "textAlign": "right"})]
                if show_share else []
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
        share_str = f"{row['_share_pct']:.1f}%" if show_share else None

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
                        "fontSize": "0.9rem", "minWidth": "3.5rem", "textAlign": "right",
                    }),
                    *(
                        [html.Span(share_str, style={
                            "fontWeight": "700" if is_hl else "400",
                            "color": _HIGHLIGHT if is_hl else "var(--text-secondary)",
                            "fontSize": "0.85rem", "minWidth": "4rem", "textAlign": "right",
                        })]
                        if show_share else []
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
# SECTION A — Overview KPI Row
# ═══════════════════════════════════════════════════════════════════════════════

def _section_overview(d: dict) -> html.Div:
    total      = d.get("total_actions", 0)
    apm        = d.get("actions_per_match", 0.0)
    box_total  = d.get("in_own_box_total", 0)
    box_pm     = d.get("in_own_box_per_match", 0.0)
    flank_total= d.get("wide_flanks_total", 0)
    flank_pm   = d.get("wide_flanks_per_match", 0.0)
    edge_total = d.get("def_third_edge_total", 0)
    edge_pm    = d.get("def_third_edge_per_match", 0.0)

    return html.Div(
        [
            html.H6("Season Overview", className="buildup-subsection-title"),
            html.Div(
                [
                    _modal_kpi(
                        "Def. Actions in 1st Third", f"{apm:.1f}",
                        f"Total: {total}",
                        PRIMARY, "bi-shield-fill",
                        "opp-season-castle-kpi-actions-pm",
                    ),
                    _modal_kpi(
                        "In Own Box", f"{box_pm:.1f}",
                        f"Total: {box_total}",
                        SUBZONE_COLORS["box"], "bi-pentagon-fill",
                        "opp-season-castle-kpi-own-box",
                    ),
                    _modal_kpi(
                        "Wide Flanks", f"{flank_pm:.1f}",
                        f"Total: {flank_total}",
                        SUBZONE_COLORS["deep_flank"], "bi-arrows-expand",
                        "opp-season-castle-kpi-wide-flanks",
                    ),
                    _modal_kpi(
                        "Def. Third Edge", f"{edge_pm:.1f}",
                        f"Total: {edge_total}",
                        SUBZONE_COLORS["def_third_edge"], "bi-chevron-right",
                        "opp-season-castle-kpi-def-edge",
                    ),
                ],
                className="team-kpi-row",
            ),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION B — Actions by Type card + See All modal trigger
# ═══════════════════════════════════════════════════════════════════════════════

def _section_actions_by_type(d: dict) -> html.Div:
    actions_by_type = d.get("actions_by_type", [])   # [[action, count], ...]
    total = d.get("total_actions", 1) or 1

    mp = max(d.get("matches_played", 1), 1)

    if actions_by_type:
        top_action, top_count = actions_by_type[0]
    else:
        top_action, top_count = "N/A", 0

    ACTION_ICONS: dict[str, str] = {
        "Tackle":        "bi-shield-fill-check",
        "Interception":  "bi-hand-index-thumb-fill",
        "Clearance":     "bi-arrow-up-circle-fill",
        "Aerial":        "bi-arrows-collapse-vertical",
        "Ball Recovery": "bi-arrow-counterclockwise",
        "Challenge":     "bi-person-fill-slash",
        "Foul":          "bi-exclamation-triangle-fill",
        "Blocked Pass":  "bi-ban",
    }
    icon = ACTION_ICONS.get(top_action, "bi-activity")

    return html.Div(
        [
            html.H6("Actions by Type", className="buildup-subsection-title"),
            _modal_kpi(
                f"Top Action: {top_action}", f"{top_count / mp:.1f}",
                f"Total: {top_count}",
                PRIMARY, icon,
                "opp-season-castle-kpi-action-types",
            ),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION C — Defensive Corridors distribution row
# ═══════════════════════════════════════════════════════════════════════════════

def _corridor_bar(counts: dict, pcts: dict) -> go.Figure:
    """Horizontal stacked bar matching the Pressing Direction bar pattern exactly."""
    segs = [
        (CORRIDOR_LABELS["L"], counts["L"], pcts["L"], CORRIDOR_COLORS["L"]),
        (CORRIDOR_LABELS["C"], counts["C"], pcts["C"], CORRIDOR_COLORS["C"]),
        (CORRIDOR_LABELS["R"], counts["R"], pcts["R"], CORRIDOR_COLORS["R"]),
    ]
    fig = go.Figure()
    for label, n, pct, color in segs:
        if n == 0:
            continue
        fig.add_trace(go.Bar(
            y=["Distribution"], x=[pct], orientation="h",
            name=label, marker_color=color,
            text=[f"{label}  {pct:.0f}%"],
            textposition="inside",
            textfont=dict(size=11, color="#fff"),
            hovertemplate=f"{label}: {n} ({pct:.1f}%)<extra></extra>",
        ))
    apply_chart_theme(fig, "dark")
    fig.update_layout(
        barmode="stack",
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=0, b=0), height=42,
        xaxis=dict(showgrid=False, showticklabels=False, range=[0, 100], fixedrange=True),
        yaxis=dict(showgrid=False, showticklabels=False, fixedrange=True),
        showlegend=False,
    )
    return fig


_CORRIDOR_ICONS = {"L": "bi-arrow-left", "C": "bi-arrows-expand-vertical", "R": "bi-arrow-right"}


def _section_corridors(d: dict) -> html.Div:
    counts = {
        "L": d.get("corridor_L_n", 0),
        "C": d.get("corridor_C_n", 0),
        "R": d.get("corridor_R_n", 0),
    }
    pcts = {
        "L": d.get("corridor_L_pct", 0.0),
        "C": d.get("corridor_C_pct", 0.0),
        "R": d.get("corridor_R_pct", 0.0),
    }

    kpis = [
        _mini_kpi(
            CORRIDOR_LABELS[k],
            counts[k],
            f"{pcts[k]:.1f}%",
            CORRIDOR_COLORS[k],
            _CORRIDOR_ICONS[k],
        )
        for k in ("L", "C", "R")
    ]

    return html.Div(
        [
            html.H6("Defensive Corridors", className="buildup-subsection-title"),
            html.Div(kpis, className="team-kpi-row",
                     style={"flexDirection": "row", "gap": "0.5rem"}),
            dcc.Graph(
                id="opp-season-castle-corridors-bar",
                figure=_corridor_bar(counts, pcts),
                config={"displayModeBar": False},
                style={"marginTop": "0.75rem"},
            ),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# MODALS
# ═══════════════════════════════════════════════════════════════════════════════

def _build_all_modals() -> list:
    modals = []

    # Four KPI league-comparison modals
    for slug, title in [
        ("actions-pm",   "Def. Actions / Match — League Comparison"),
        ("own-box",      "In Own Box / Match — League Comparison"),
        ("wide-flanks",  "Wide Flanks / Match — League Comparison"),
        ("def-edge",     "Def. Third Edge / Match — League Comparison"),
    ]:
        modals.append(build_unified_modal(
            modal_id=f"opp-season-castle-modal-{slug}",
            title_id=f"opp-season-castle-modal-{slug}-title",
            body_id =f"opp-season-castle-modal-{slug}-body",
            title   =title,
            size    ="md",
        ))

    # Action types modal (single-team, no league comparison)
    modals.append(build_unified_modal(
        modal_id="opp-season-castle-modal-action-types",
        title_id="opp-season-castle-modal-action-types-title",
        body_id ="opp-season-castle-modal-action-types-body",
        title   ="Defensive Actions by Type",
        size    ="md",
    ))

    return modals


# ═══════════════════════════════════════════════════════════════════════════════
# STORE
# ═══════════════════════════════════════════════════════════════════════════════

def _castle_store(d: dict) -> dcc.Store:
    return dcc.Store(
        id="opp-season-castle-store",
        data={
            "season":       d.get("season", ""),
            "team":         d.get("team", ""),
            "actions_by_type": d.get("actions_by_type", []),
            "total_actions":   d.get("total_actions", 0),
        },
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def build_castle_section(season: str, team_name: str) -> html.Div:
    """
    Build the full season-aggregate Defensive Castle section.
    Called lazily by the opp-section-dc callback.
    """
    season_label = season.replace("_", "/")
    d = compute_season_castle(season, team_name)

    no_data_banner = None
    if d["total_actions"] == 0:
        no_data_banner = dbc.Alert(
            [
                html.I(className="bi bi-exclamation-triangle-fill me-2"),
                f"No defensive castle data found for {team_name} ({season_label}). "
                "Run precompute_season_castle() to generate the parquet.",
            ],
            color="warning", className="mb-3",
        )

    _hr = html.Hr(style={"borderColor": "var(--border-light)", "margin": "1.5rem 0"})

    return html.Div(
        [
            ds_header(
                "Opponent Analysis — Season View",
                "bi-bricks",
                f"Defensive Castle — {team_name}  ({season_label})",
                "Season-aggregate defensive actions in the own defensive third "
                "— sub-zone breakdown, action types and corridor split",
            ),
            _castle_store(d),
            *_build_all_modals(),
            *([] if no_data_banner is None else [no_data_banner]),

            # A — KPI overview (4 clickable cards)
            html.Div(_section_overview(d), style={"marginBottom": "1.5rem"}),

            _hr,

            # B — Actions by type card + see-all trigger
            html.Div(_section_actions_by_type(d), style={"marginBottom": "1.5rem"}),

            _hr,

            # C — Corridor distribution tiles (no modal)
            html.Div(_section_corridors(d), style={"marginBottom": "1.5rem"}),

            _hr,

            # D — Zone action density pitch map (season aggregate)
            html.Div(
                [
                    html.H6("Pitch Map — Zone Action Density",
                            className="buildup-subsection-title"),
                    html.P(
                        "Season-aggregate action density per defensive-third zone "
                        "— darker fill = more actions",
                        className="kpi-subtitle",
                        style={"marginBottom": "0.5rem"},
                    ),
                    html.Div(
                        dcc.Graph(
                            id="opp-season-castle-pitch-density",
                            figure=_build_castle_heatmap(
                                d.get("zone_action_counts", {})
                            ),
                            config={"displayModeBar": False},
                        ),
                        className="pitch-dark-container",
                    ),
                ],
                style={"marginBottom": "1.5rem"},
            ),
        ],
        className="analysis-section buildup-card ma-card",
        style={"marginBottom": "2rem", "padding": "1.5rem"},
    )
