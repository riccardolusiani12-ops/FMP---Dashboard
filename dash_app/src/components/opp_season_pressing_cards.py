"""
Opponent Analysis — Defensive Phase: Pressing Season Aggregate
==============================================================
Refinement pass — changes applied vs. original build:
  C1: Removed "Total Def. Actions" KPI card (no component ID was attached).
  C3: Removed "PPDA (High Press)" KPI card; renamed survivor to "PPDA".
      KPI row now has 5 cards: Actions/Match, PPDA, Press Success,
      PPDA (Mid Press), Pressing Line.
  C2: Actions/Match card is now clickable → league-comparison modal
      (opp-season-press-modal-actions-pm).
  C4: PPDA card is now clickable → league-comparison modal
      (opp-season-press-modal-ppda), sorted ascending.
  C5: Dual pitch maps replaced by single _build_density_outcome_pitch():
      18-zone density heatmap + green/red ●n indicator annotations at the
      bottom of each zone box. Call sites for _build_actions_scatter() and
      _build_combined_heatmap_outcomes() removed from this file (functions
      themselves in defensive_pressing_cards.py are untouched).

Phase 0 findings:
  • pressing_summary_ parquet has: zone_heatmap_1..18 (density),
    press_success_{high/mid/low}_{total/success/rate} (zone outcome counts),
    pressing_line_median, actions_per_match, ppda_overall.
  • pressing_actions_ parquet has: x,y,action,zone_group,corridor,success,minute,player.
  • Zone outcome counts for the pitch indicator layer are derived from
    press_success_by_zone (high/mid/low) — mapped to 18-zone grid via
    the same x-threshold boundaries used by the heatmap (row 0–1=low,
    row 2–3=mid, row 4–5=high in attacking-x orientation).
  • No per-action coords needed for indicator dots: zone-level counts suffice
    and are already in the parquet summary columns.
  • League-comparison data comes from pressing_summary_{season}.parquet filtered
    per-team; load_season_teams() gives the canonical team list.

IDs added:
  opp-season-press-modal-actions-pm, ...-actions-pm-title, ...-actions-pm-body
  opp-season-press-modal-ppda,       ...-ppda-title,       ...-ppda-body
  opp-season-press-pitch-density-outcomes  (single graph replacing the two maps)
IDs removed: none (the two old maps had no component IDs).
IDs unchanged:
  opp-season-press-modal-{high/mid/low}, opp-season-press-store,
  {"type":"opp-season-press-zone-tile","index":zone_key}
"""

from __future__ import annotations

import plotly.graph_objects as go
import dash_bootstrap_components as dbc
from dash import dcc, html

from src.config import READY_DATA_DIR
from src.team_mapping import canonical_name
from src.styling.theme import COLORS_DARK, SEMANTIC_COLORS
from src.styling.plotly_template import apply_chart_theme
from src.styling.pitch_utils import draw_pitch
from src.styling.ui_components import build_unified_modal, ds_header
from src.utils.caching import cache_get, cache_set
from src.utils.logging import log

# ── Palette — bound to shared design system ──────────────────────────────────
from src.components.defensive_pressing_cards import (
    _mini_kpi,
    ZONE_GROUP_COLORS,
    ZONE_GROUP_LABELS,
    CORRIDOR_COLORS,
    CORRIDOR_LABELS,
    HIGH_COLOR,
    MID_COLOR,
    LOW_COLOR,
    SUCCESS_COLOR,
    FAIL_COLOR,
    PRIMARY,
    _ppda_color,
    _fmt_ppda,
    _X_EDGES,
    _Y_EDGES,
)

_HIGHLIGHT = COLORS_DARK["accent"]   # "#8a1f33"
_NEUTRAL   = SEMANTIC_COLORS["benchmark_neutral"]   # "#4a6274"

# Zone metadata — drives tiles and modals
_ZONE_META = [
    ("high", "High Press",  HIGH_COLOR, "bi-shield-fill-exclamation"),
    ("mid",  "Mid Press",   MID_COLOR,  "bi-shield-half"),
    ("low",  "Low Block",   LOW_COLOR,  "bi-shield"),
]

# 18-zone → zone_group mapping (attacking x from left):
# zones 1-6  (rows 0-1, x 0-33.33)  → low block
# zones 7-12 (rows 2-3, x 33.33-66.67) → mid press
# zones 13-18(rows 4-5, x 66.67-100) → high press
_ZONE_TO_GROUP: dict[int, str] = {
    z: ("low" if z <= 6 else "mid" if z <= 12 else "high")
    for z in range(1, 19)
}


# ═══════════════════════════════════════════════════════════════════════════════
# DATA LAYER
# ═══════════════════════════════════════════════════════════════════════════════

def _load_pressing_parquet(data_type: str, season: str):
    """Load a pressing parquet with in-memory TTL cache (season-level)."""
    import pandas as pd
    cache_key = f"opp_pressing_{data_type}_{season}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    path = READY_DATA_DIR / f"{data_type}_{season}.parquet"
    if not path.exists():
        log.warning("Pressing parquet missing: %s — run precompute_season_pressing()", path.name)
        return None
    try:
        df = pd.read_parquet(path)
    except Exception as exc:
        log.error("Failed to read %s: %s", path.name, exc)
        return None

    cache_set(cache_key, df)
    return df


def _filter_team(df, team_name: str):
    if df is None or df.empty:
        import pandas as pd
        return pd.DataFrame()
    target = canonical_name(team_name).lower()
    mask = df["team"].apply(lambda t: canonical_name(str(t)).lower() == target)
    return df[mask].reset_index(drop=True)


def compute_season_pressing(season: str, team_name: str) -> dict:
    """Return all pressing season-aggregate data for one team."""
    summary_full = _load_pressing_parquet("pressing_summary", season)
    actions_full = _load_pressing_parquet("pressing_actions", season)

    summary = _filter_team(summary_full, team_name)
    actions = _filter_team(actions_full, team_name)

    if summary.empty:
        return _empty_pressing_result()

    row = summary.iloc[0]

    def _f(col, default=0.0):
        v = row.get(col, default)
        return None if (v != v) else v

    def _i(col, default=0):
        v = row.get(col, default)
        try:
            return int(v) if v == v else default
        except (TypeError, ValueError):
            return default

    press_success_by_zone = {
        zg: {
            "total":   _i(f"press_success_{zg}_total"),
            "success": _i(f"press_success_{zg}_success"),
            "rate":    float(_f(f"press_success_{zg}_rate", 0.0) or 0.0),
        }
        for zg in ("high", "mid", "low")
    }

    zone_heatmap = {z: _i(f"zone_heatmap_{z}") for z in range(1, 19)}

    # Per-zone (Z1–Z18) press outcome counts (granular, from precompute_season_pressing)
    zone_press_outcomes = {
        z: {
            "total":   _i(f"press_zone_{z}_total", 0),
            "success": _i(f"press_zone_{z}_success", 0),
        }
        for z in range(1, 19)
    }

    press_actions_detail: list[dict] = []
    if not actions.empty:
        for _, ar in actions.iterrows():
            press_actions_detail.append({
                "x":          ar.get("x"),
                "y":          ar.get("y"),
                "action":     str(ar.get("action", "")),
                "zone_group": str(ar.get("zone_group", "")),
                "corridor":   str(ar.get("corridor", "")),
                "success":    bool(ar.get("success", False)),
                "minute":     int(ar.get("minute", 0) or 0),
                "player":     str(ar.get("player", "")),
            })

    return {
        "total_def_actions":        _i("total_def_actions"),
        "actions_per_match":        float(_f("actions_per_match", 0.0) or 0.0),
        "matches_played":           _i("matches_played", 1),
        "ppda_overall":             _f("ppda_overall"),
        "ppda_high":                _f("ppda_high"),
        "ppda_mid":                 _f("ppda_mid"),
        "ppda_num_overall":         _i("ppda_num_overall"),
        "ppda_den_overall":         _i("ppda_den_overall"),
        "ppda_num_high":            _i("ppda_num_high"),
        "ppda_den_high":            _i("ppda_den_high"),
        "ppda_num_mid":             _i("ppda_num_mid"),
        "ppda_den_mid":             _i("ppda_den_mid"),
        "pressing_line_median":     _f("pressing_line_median"),
        "high_press_count":         _i("high_press_count"),
        "high_press_pct":           float(_f("high_press_pct", 0.0) or 0.0),
        "mid_press_count":          _i("mid_press_count"),
        "mid_press_pct":            float(_f("mid_press_pct", 0.0) or 0.0),
        "low_block_count":          _i("low_block_count"),
        "low_block_pct":            float(_f("low_block_pct", 0.0) or 0.0),
        "pressing_left_count":      _i("pressing_left_count"),
        "pressing_left_pct":        float(_f("pressing_left_pct", 0.0) or 0.0),
        "pressing_centre_count":    _i("pressing_centre_count"),
        "pressing_centre_pct":      float(_f("pressing_centre_pct", 0.0) or 0.0),
        "pressing_right_count":     _i("pressing_right_count"),
        "pressing_right_pct":       float(_f("pressing_right_pct", 0.0) or 0.0),
        "press_success_rate":       float(_f("press_success_rate", 0.0) or 0.0),
        "press_success_total":      _i("press_success_total"),
        "press_success_successful": _i("press_success_successful"),
        "press_success_by_zone":    press_success_by_zone,
        "zone_press_outcomes":      zone_press_outcomes,
        "zone_heatmap":             zone_heatmap,
        "press_actions_detail":     press_actions_detail,
        "season":                   str(row.get("season", season)),
        "team":                     team_name,
    }


def _empty_pressing_result() -> dict:
    _ez = {zg: {"total": 0, "success": 0, "rate": 0.0} for zg in ("high", "mid", "low")}
    return {
        "total_def_actions": 0, "actions_per_match": 0.0, "matches_played": 0,
        "ppda_overall": None, "ppda_high": None, "ppda_mid": None,
        "ppda_num_overall": 0, "ppda_den_overall": 0,
        "ppda_num_high": 0, "ppda_den_high": 0,
        "ppda_num_mid": 0, "ppda_den_mid": 0,
        "pressing_line_median": None,
        "high_press_count": 0, "high_press_pct": 0.0,
        "mid_press_count": 0,  "mid_press_pct": 0.0,
        "low_block_count": 0,  "low_block_pct": 0.0,
        "pressing_left_count": 0,   "pressing_left_pct": 0.0,
        "pressing_centre_count": 0, "pressing_centre_pct": 0.0,
        "pressing_right_count": 0,  "pressing_right_pct": 0.0,
        "press_success_rate": 0.0, "press_success_total": 0,
        "press_success_successful": 0,
        "press_success_by_zone": _ez,
        "zone_press_outcomes": {z: {"total": 0, "success": 0} for z in range(1, 19)},
        "zone_heatmap": {z: 0 for z in range(1, 19)},
        "press_actions_detail": [],
        "season": "", "team": "",
    }


def load_league_pressing_summary(season: str) -> "pd.DataFrame | None":
    """
    Return the full pressing_summary_{season}.parquet (all teams).
    Used by league-comparison modal callbacks.
    """
    return _load_pressing_parquet("pressing_summary", season)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION A — Overview KPI Row  (C1: 6→5 cards; C3: PPDA High removed)
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
    """KPI card with top-right expand icon — participates in flex row as a direct .kpi-card."""
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


def _section_overview(d: dict) -> html.Div:
    """Four KPI cards: Actions/Match, PPDA, Press Success Rate, Pressing Line — all clickable with expand icon."""
    per_match    = d.get("actions_per_match", 0.0)
    ppda         = d.get("ppda_overall")
    success_rate = d.get("press_success_rate", 0.0)
    succ_n       = d.get("press_success_successful", 0)
    succ_tot     = d.get("press_success_total", 0)
    median_line  = d.get("pressing_line_median")
    median_str   = f"{median_line:.1f}" if median_line is not None else "N/A"

    return html.Div(
        [
            html.H6("Season Overview", className="buildup-subsection-title"),
            html.Div(
                [
                    # C2 — clickable → opp-season-press-modal-actions-pm
                    _modal_kpi(
                        "Actions / Match", f"{per_match:.1f}",
                        f"across {d.get('matches_played', 0)} matches",
                        PRIMARY, "bi-bar-chart-line-fill",
                        "opp-season-press-kpi-actions-pm",
                    ),
                    # C4 — clickable → opp-season-press-modal-ppda
                    _modal_kpi(
                        "PPDA", _fmt_ppda(ppda),
                        f"{d.get('ppda_num_overall',0)} opp. passes / "
                        f"{d.get('ppda_den_overall',0)} def. actions",
                        _ppda_color(ppda), "bi-shield-fill-exclamation",
                        "opp-season-press-kpi-ppda",
                    ),
                    # clickable → opp-season-press-modal-success-rate
                    _modal_kpi(
                        "Press Success Rate", f"{success_rate:.1f}%",
                        f"{succ_n} / {succ_tot} presses",
                        SUCCESS_COLOR, "bi-check-circle-fill",
                        "opp-season-press-kpi-success-rate",
                    ),
                    # clickable → opp-season-press-modal-offside-line
                    _modal_kpi(
                        "Pressing Line (median)", median_str,
                        "median x of all defensive actions",
                        SEMANTIC_COLORS["offside_line"], "bi-rulers",
                        "opp-season-press-kpi-offside-line",
                    ),
                ],
                className="team-kpi-row",
            ),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION B — Three-column distribution (unchanged logic)
# ═══════════════════════════════════════════════════════════════════════════════

def _stacked_bar(
    segments: list[tuple[str, int, float, str]],
    row_label: str = "Distribution",
) -> go.Figure:
    fig = go.Figure()
    for label, n, pct, color in segments:
        if n == 0:
            continue
        fig.add_trace(go.Bar(
            y=[row_label], x=[pct], orientation="h",
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


def _col_actions_by_zone(d: dict) -> html.Div:
    segs = [
        ("Final Third", d.get("high_press_count", 0), d.get("high_press_pct", 0.0), HIGH_COLOR),
        ("Middle Third", d.get("mid_press_count", 0), d.get("mid_press_pct", 0.0), MID_COLOR),
        ("Own Third",   d.get("low_block_count",  0), d.get("low_block_pct",  0.0), LOW_COLOR),
    ]
    mp = max(d.get("matches_played", 1), 1)
    low_cnt  = d.get("low_block_count",  0)
    mid_cnt  = d.get("mid_press_count",  0)
    high_cnt = d.get("high_press_count", 0)
    kpis = [
        _modal_kpi(
            "Own Third",    f"{low_cnt / mp:.1f}",
            f"Total: {low_cnt}",
            LOW_COLOR, "bi-shield",
            "opp-season-press-kpi-zone-low",
        ),
        _modal_kpi(
            "Middle Third", f"{mid_cnt / mp:.1f}",
            f"Total: {mid_cnt}",
            MID_COLOR, "bi-shield-half",
            "opp-season-press-kpi-zone-mid",
        ),
        _modal_kpi(
            "Final Third",  f"{high_cnt / mp:.1f}",
            f"Total: {high_cnt}",
            HIGH_COLOR, "bi-shield-fill-exclamation",
            "opp-season-press-kpi-zone-high",
        ),
    ]
    return html.Div([
        html.H6("Actions by Zone", className="buildup-subsection-title"),
        html.Div(kpis, className="team-kpi-row",
                 style={"flexDirection": "column", "gap": "0.5rem"}),
        dcc.Graph(figure=_stacked_bar(segs), config={"displayModeBar": False},
                  style={"marginTop": "0.75rem"}),
    ])


def _col_pressing_direction(d: dict) -> html.Div:
    segs = [
        (CORRIDOR_LABELS["L"], d.get("pressing_left_count",   0),
         d.get("pressing_left_pct",   0.0), CORRIDOR_COLORS["L"]),
        (CORRIDOR_LABELS["C"], d.get("pressing_centre_count", 0),
         d.get("pressing_centre_pct", 0.0), CORRIDOR_COLORS["C"]),
        (CORRIDOR_LABELS["R"], d.get("pressing_right_count",  0),
         d.get("pressing_right_pct",  0.0), CORRIDOR_COLORS["R"]),
    ]
    mp2 = max(d.get("matches_played", 1), 1)
    kpis = [
        _mini_kpi(
            CORRIDOR_LABELS[k],
            f"{d.get(f'pressing_{name}_count', 0) / mp2:.1f}",
            f"Total: {d.get(f'pressing_{name}_count', 0)}",
            CORRIDOR_COLORS[k], "bi-arrows-expand-vertical",
        )
        for k, name in (("L", "left"), ("C", "centre"), ("R", "right"))
    ]
    return html.Div([
        html.H6("Pressing Direction", className="buildup-subsection-title"),
        html.Div(kpis, className="team-kpi-row",
                 style={"flexDirection": "column", "gap": "0.5rem"}),
        dcc.Graph(figure=_stacked_bar(segs), config={"displayModeBar": False},
                  style={"marginTop": "0.75rem"}),
    ])


def _zone_tile(zone_key: str, label: str, color: str, icon: str,
               info: dict) -> html.Div:
    total   = info.get("total", 0)
    success = info.get("success", 0)
    rate    = info.get("rate", 0.0)
    return html.Div(
        [
            html.I(className=f"bi {icon}",
                   style={"color": color, "fontSize": "1.2rem", "marginRight": "0.5rem"}),
            html.Span(label, style={"flex": "1", "fontWeight": "600",
                                    "color": "var(--text-primary)", "fontSize": "0.9rem"}),
            html.Span(f"{rate:.1f}%",
                      style={"fontWeight": "700", "color": color,
                             "fontSize": "1.1rem", "marginRight": "0.5rem"}),
            html.Span(f"{success}/{total}",
                      style={"fontSize": "0.78rem", "color": "var(--text-secondary)"}),
            html.I(className="bi bi-chevron-right ms-2",
                   style={"color": "var(--text-secondary)", "fontSize": "0.7rem"}),
        ],
        id={"type": "opp-season-press-zone-tile", "index": zone_key},
        n_clicks=0,
        style={
            "display": "flex", "alignItems": "center",
            "padding": "0.6rem 0.75rem", "borderRadius": "8px",
            "border": f"1px solid {color}33", "background": f"{color}11",
            "cursor": "pointer", "marginBottom": "0.5rem",
            "transition": "background 0.15s",
        },
    )


def _col_success_by_zone(d: dict) -> html.Div:
    by_zone     = d.get("press_success_by_zone", {})
    overall_rate = d.get("press_success_rate", 0.0)
    overall_n   = d.get("press_success_successful", 0)
    overall_tot = d.get("press_success_total", 0)
    tiles = [
        _zone_tile(zk, lbl, col, ico,
                   by_zone.get(zk, {"total": 0, "success": 0, "rate": 0.0}))
        for zk, lbl, col, ico in _ZONE_META
    ]
    return html.Div([
        html.H6("Press Success by Zone", className="buildup-subsection-title"),
        _mini_kpi("Overall", f"{overall_rate:.1f}%",
                  f"{overall_n} / {overall_tot} presses",
                  SUCCESS_COLOR, "bi-check-circle-fill"),
        html.Div(tiles, style={"marginTop": "0.75rem"}),
    ])


def _section_distributions(d: dict) -> html.Div:
    col_style = {"flex": "1", "minWidth": "200px"}
    return html.Div(
        [
            html.Div(_col_actions_by_zone(d),    style=col_style),
            html.Div(_col_pressing_direction(d), style=col_style),
            html.Div(_col_success_by_zone(d),    style=col_style),
        ],
        style={"display": "flex", "gap": "2rem", "flexWrap": "wrap",
               "alignItems": "flex-start"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION C — C5: Single combined density + outcome indicator pitch map
# ═══════════════════════════════════════════════════════════════════════════════

def _build_density_outcome_pitch(
    zone_counts: dict[int, int],
    zone_press_outcomes: dict[int, dict],
    pressing_line_median: float | None,
) -> go.Figure:
    """
    Single full-width pitch map combining:
      (a) 18-zone action density heatmap (navy→crimson gradient fill)
      (b) Green / Red ●n indicator annotations at the bottom of each zone,
          showing successful and unsuccessful press counts per zone.

    zone_press_outcomes keys are zone IDs 1–18 with per-zone success/total counts.
    """
    _ROWS = 6
    _COLS = 3

    zone_success: dict[int, int] = {}
    zone_fail:    dict[int, int] = {}
    for z in range(1, 19):
        info = zone_press_outcomes.get(z, {})
        suc  = info.get("success", 0)
        tot  = info.get("total", 0)
        zone_success[z] = suc
        zone_fail[z]    = max(tot - suc, 0)

    fig = go.Figure()
    max_count = max(zone_counts.values(), default=1) or 1

    for zone_num in range(1, 19):
        row = (zone_num - 1) // _COLS
        col = (zone_num - 1) % _COLS
        x0 = _X_EDGES[row]
        x1 = _X_EDGES[row + 1]
        y0 = _Y_EDGES[col]
        y1 = _Y_EDGES[col + 1]
        cx = (x0 + x1) / 2
        cy = (y0 + y1) / 2

        count     = zone_counts.get(zone_num, 0)
        intensity = count / max_count

        # Navy → crimson density fill (same ramp as _build_combined_heatmap_outcomes)
        r = int(27  + (138 - 27)  * intensity)
        g = int(40  + (31  - 40)  * intensity)
        b = int(56  + (51  - 56)  * intensity)
        a = 0.25 + 0.60 * intensity
        fig.add_shape(
            type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
            line=dict(color="rgba(255,255,255,0.10)", width=1),
            fillcolor=f"rgba({r},{g},{b},{a:.2f})",
            layer="below",
        )

        # Total action count (centre of zone, faint)
        if count > 0:
            fig.add_annotation(
                x=cx, y=cy + 5,
                text=f"<b>{count}</b>",
                showarrow=False,
                font=dict(size=14, color="#f0f0f0"),
            )

        # Zone number label (small, very faint)
        fig.add_annotation(
            x=cx, y=cy - 4,
            text=f"Z{zone_num}",
            showarrow=False,
            font=dict(size=8, color="rgba(255,255,255,0.45)"),
        )

        # Green ● success / Red ● fail indicators at bottom of zone
        s_n = zone_success.get(zone_num, 0)
        f_n = zone_fail.get(zone_num, 0)
        if s_n > 0 or f_n > 0:
            indicator = ""
            if s_n > 0:
                indicator += f"<span style='color:#22c55e'>●{s_n}</span>"
            if f_n > 0:
                if indicator:
                    indicator += " "
                indicator += f"<span style='color:#ef4444'>●{f_n}</span>"
            fig.add_annotation(
                x=cx, y=cy - 12,
                text=indicator,
                showarrow=False,
                font=dict(size=9),
            )

    # Median pressing line overlay
    if pressing_line_median is not None:
        fig.add_shape(
            type="line",
            x0=pressing_line_median, x1=pressing_line_median, y0=0, y1=100,
            line=dict(color="rgba(255,255,255,0.70)", width=2, dash="dot"),
        )
        fig.add_annotation(
            x=pressing_line_median, y=103,
            text=f"<b>Pressing line x={pressing_line_median}</b>",
            showarrow=False,
            font=dict(size=10, color="rgba(255,255,255,0.80)"),
            xanchor="center",
        )

    apply_chart_theme(fig, "dark")
    draw_pitch(fig, theme="dark",
               title="Action Density + Press Outcomes by Zone",
               height=480, show_legend=False, draw_zones=True)
    return fig


def _section_pitch_map(d: dict) -> html.Div:
    """C5: Single full-width combined density + outcome indicator pitch map."""
    return html.Div(
        [
            html.H6("Pitch Map — Action Density & Press Outcomes",
                    className="buildup-subsection-title"),
            html.P(
                "Zone fill = action density · ●n green = successful presses · "
                "●n red = unsuccessful · white dotted = pressing line",
                className="kpi-subtitle",
                style={"marginBottom": "0.5rem"},
            ),
            html.Div(
                dcc.Graph(
                    id="opp-season-press-pitch-density-outcomes",
                    figure=_build_density_outcome_pitch(
                        d.get("zone_heatmap", {z: 0 for z in range(1, 19)}),
                        d.get("zone_press_outcomes", {z: {"total": 0, "success": 0} for z in range(1, 19)}),
                        d.get("pressing_line_median"),
                    ),
                    config={"displayModeBar": False},
                ),
                className="pitch-dark-container",
            ),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# LEAGUE-COMPARISON TABLE BUILDER  (C2 + C4)
# ═══════════════════════════════════════════════════════════════════════════════

def _league_table(
    summary_df,
    metric_col: str,
    metric_label: str,
    highlight_team: str,
    ascending: bool = False,
    fmt: str = ".1f",
) -> html.Div:
    """
    Ranked table of all teams in the season by a single pressing metric.
    Selected team row is highlighted with accent background + bold text.
    """
    import pandas as pd

    if summary_df is None or summary_df.empty:
        return html.P("No league data available.", style={"color": "#8899aa"})

    df = summary_df.copy()
    if metric_col not in df.columns:
        return html.P(f"Column '{metric_col}' not found in summary.",
                      style={"color": "#8899aa"})

    df = df.dropna(subset=[metric_col])
    df = df.sort_values(metric_col, ascending=ascending).reset_index(drop=True)
    df["rank"] = range(1, len(df) + 1)

    hl_lower = canonical_name(highlight_team).lower()

    rows = []
    for _, row in df.iterrows():
        team     = str(row.get("team", ""))
        val      = row[metric_col]
        rank     = int(row["rank"])
        is_hl    = canonical_name(team).lower() == hl_lower
        val_str  = format(float(val), fmt) if fmt else str(val)

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
                    html.Span(
                        str(rank),
                        style={"width": "2rem", "color": "#8899aa",
                               "fontSize": "0.8rem", "flexShrink": "0"},
                    ),
                    html.Span(
                        team,
                        style={
                            "flex": "1",
                            "fontWeight": "700" if is_hl else "400",
                            "color": _HIGHLIGHT if is_hl else "var(--text-primary)",
                            "fontSize": "0.88rem",
                        },
                    ),
                    html.Span(
                        val_str,
                        style={
                            "fontWeight": "700" if is_hl else "400",
                            "color": _HIGHLIGHT if is_hl else "var(--text-secondary)",
                            "fontSize": "0.9rem", "minWidth": "3.5rem",
                            "textAlign": "right",
                        },
                    ),
                ],
                style=row_style,
            )
        )

    header = html.Div(
        [
            html.Span("#", style={"width": "2rem", "color": "#8899aa",
                                  "fontSize": "0.75rem", "flexShrink": "0"}),
            html.Span("Team", style={"flex": "1", "color": "#8899aa",
                                     "fontSize": "0.75rem"}),
            html.Span(metric_label, style={"color": "#8899aa", "fontSize": "0.75rem",
                                           "minWidth": "3.5rem", "textAlign": "right"}),
        ],
        style={"display": "flex", "padding": "6px 10px",
               "borderBottom": "1px solid rgba(255,255,255,0.15)",
               "marginBottom": "2px"},
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
# MODALS — zone success (unchanged) + league comparison (C2, C4)
# ═══════════════════════════════════════════════════════════════════════════════

def _zone_modal_body(zone_key: str, by_zone: dict):
    """Column-chart body for a zone success modal (unchanged from original)."""
    label   = ZONE_GROUP_LABELS.get(zone_key, zone_key)
    info    = by_zone.get(zone_key, {"total": 0, "success": 0, "rate": 0.0})
    color   = ZONE_GROUP_COLORS.get(zone_key, PRIMARY)
    total   = info.get("total", 0)
    success = info.get("success", 0)
    fail    = total - success

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=["Success", "No Success"],
        y=[success, fail],
        marker_color=[SUCCESS_COLOR, FAIL_COLOR],
        text=[str(success), str(fail)],
        textposition="outside",
        textfont=dict(size=13, color="#d0d0d0"),
        hovertemplate="%{x}: %{y}<extra></extra>",
    ))
    apply_chart_theme(fig, "dark")
    fig.update_layout(
        title=dict(text=f"{label} — Press Outcomes",
                   font=dict(size=14, color=color), x=0.5),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        height=300, margin=dict(l=40, r=40, t=60, b=40), showlegend=False,
        yaxis=dict(gridcolor="rgba(255,255,255,0.07)", tickfont=dict(color="#8899aa")),
        xaxis=dict(tickfont=dict(color="#d0d0d0", size=13)),
    )
    return dcc.Graph(figure=fig, config={"displayModeBar": False})


def _zone_league_comparison_body(
    summary_df,
    zone_key: str,
    highlight_team: str,
) -> html.Div:
    """
    Single-table league comparison for a zone card (Own / Middle / Final Third).
    Columns: # | Team | Actions/M | % Share — sorted descending by Actions/M.
    Selected team row highlighted in accent colour.
    """
    import pandas as pd

    _PCT_COL = {"low": "low_block_pct", "mid": "mid_press_pct", "high": "high_press_pct"}
    _CNT_COL = {"low": "low_block_count", "mid": "mid_press_count", "high": "high_press_count"}
    _COLOR   = {"low": LOW_COLOR, "mid": MID_COLOR, "high": HIGH_COLOR}

    pct_col = _PCT_COL[zone_key]
    cnt_col = _CNT_COL[zone_key]
    color   = _COLOR[zone_key]

    if summary_df is None or summary_df.empty:
        return html.P("No league data available.", style={"color": "#8899aa"})

    df = summary_df.copy()

    if "matches_played" in df.columns:
        df["_zone_pm"] = (
            df[cnt_col].fillna(0) / df["matches_played"].clip(lower=1)
        ).round(1)
    else:
        df["_zone_pm"] = df[cnt_col].fillna(0)

    df = df.dropna(subset=["_zone_pm"]).sort_values("_zone_pm", ascending=False).reset_index(drop=True)
    df["rank"] = range(1, len(df) + 1)

    has_pct = pct_col in df.columns
    hl_lower = canonical_name(highlight_team).lower()

    header = html.Div(
        [
            html.Span("#", style={"width": "2rem", "color": "#8899aa",
                                  "fontSize": "0.75rem", "flexShrink": "0"}),
            html.Span("Team", style={"flex": "1", "color": "#8899aa", "fontSize": "0.75rem"}),
            html.Span("Actions/M", style={"color": "#8899aa", "fontSize": "0.75rem",
                                          "minWidth": "4.5rem", "textAlign": "right"}),
            *(
                [html.Span("% Share", style={"color": "#8899aa", "fontSize": "0.75rem",
                                             "minWidth": "4rem", "textAlign": "right"})]
                if has_pct else []
            ),
        ],
        style={"display": "flex", "padding": "6px 10px",
               "borderBottom": "1px solid rgba(255,255,255,0.15)", "marginBottom": "2px"},
    )

    rows = []
    for _, row in df.iterrows():
        team    = str(row.get("team", ""))
        pm_val  = row["_zone_pm"]
        rank    = int(row["rank"])
        is_hl   = canonical_name(team).lower() == hl_lower
        pm_str  = f"{float(pm_val):.1f}"
        pct_str = f"{float(row[pct_col]):.1f}%" if has_pct else None

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

        rows.append(html.Div(
            [
                html.Span(str(rank), style={"width": "2rem", "color": "#8899aa",
                                            "fontSize": "0.8rem", "flexShrink": "0"}),
                html.Span(team, style={
                    "flex": "1",
                    "fontWeight": "700" if is_hl else "400",
                    "color": _HIGHLIGHT if is_hl else "var(--text-primary)",
                    "fontSize": "0.88rem",
                }),
                html.Span(pm_str, style={
                    "fontWeight": "700" if is_hl else "400",
                    "color": _HIGHLIGHT if is_hl else "var(--text-secondary)",
                    "fontSize": "0.9rem", "minWidth": "4.5rem", "textAlign": "right",
                }),
                *(
                    [html.Span(pct_str, style={
                        "fontWeight": "700" if is_hl else "400",
                        "color": _HIGHLIGHT if is_hl else "var(--text-secondary)",
                        "fontSize": "0.85rem", "minWidth": "4rem", "textAlign": "right",
                    })]
                    if has_pct else []
                ),
            ],
            style=row_style,
        ))

    return html.Div(
        [header, *rows],
        style={"maxHeight": "460px", "overflowY": "auto",
               "borderRadius": "6px", "border": "1px solid rgba(255,255,255,0.07)"},
    )


def _build_all_modals() -> list:
    """All modal shells: three zone modals + zone KPI league-comparison modals + overview league-comparison modals."""
    modals = []

    # Zone success modals (high / mid / low)
    for zone_key, label, _color, _icon in _ZONE_META:
        modals.append(build_unified_modal(
            modal_id =f"opp-season-press-modal-{zone_key}",
            title_id =f"opp-season-press-modal-{zone_key}-title",
            body_id  =f"opp-season-press-modal-{zone_key}-body",
            title    =f"{label} — Press Outcomes",
            size     ="md",
        ))

    # Zone KPI card league-comparison modals (own / mid / final third)
    modals.append(build_unified_modal(
        modal_id ="opp-season-press-modal-zone-low",
        title_id ="opp-season-press-modal-zone-low-title",
        body_id  ="opp-season-press-modal-zone-low-body",
        title    ="Own Third — League Comparison",
        size     ="lg",
    ))
    modals.append(build_unified_modal(
        modal_id ="opp-season-press-modal-zone-mid",
        title_id ="opp-season-press-modal-zone-mid-title",
        body_id  ="opp-season-press-modal-zone-mid-body",
        title    ="Middle Third — League Comparison",
        size     ="lg",
    ))
    modals.append(build_unified_modal(
        modal_id ="opp-season-press-modal-zone-high",
        title_id ="opp-season-press-modal-zone-high-title",
        body_id  ="opp-season-press-modal-zone-high-body",
        title    ="Final Third — League Comparison",
        size     ="lg",
    ))

    # C2 — Actions/Match league comparison
    modals.append(build_unified_modal(
        modal_id ="opp-season-press-modal-actions-pm",
        title_id ="opp-season-press-modal-actions-pm-title",
        body_id  ="opp-season-press-modal-actions-pm-body",
        title    ="Defensive Actions / Match — League Comparison",
        size     ="md",
    ))

    # C4 — PPDA league comparison
    modals.append(build_unified_modal(
        modal_id ="opp-season-press-modal-ppda",
        title_id ="opp-season-press-modal-ppda-title",
        body_id  ="opp-season-press-modal-ppda-body",
        title    ="PPDA — League Comparison",
        size     ="md",
    ))

    # Press Success Rate league comparison
    modals.append(build_unified_modal(
        modal_id ="opp-season-press-modal-success-rate",
        title_id ="opp-season-press-modal-success-rate-title",
        body_id  ="opp-season-press-modal-success-rate-body",
        title    ="Press Success Rate — League Comparison",
        size     ="md",
    ))

    # Pressing Line (Median) league comparison
    modals.append(build_unified_modal(
        modal_id ="opp-season-press-modal-offside-line",
        title_id ="opp-season-press-modal-offside-line-title",
        body_id  ="opp-season-press-modal-offside-line-body",
        title    ="Pressing Line (Median) — League Comparison",
        size     ="md",
    ))

    return modals


# ═══════════════════════════════════════════════════════════════════════════════
# STORE
# ═══════════════════════════════════════════════════════════════════════════════

def _pressing_stores(d: dict) -> list:
    store_data = {
        "season":                   d.get("season", ""),
        "team":                     d.get("team", ""),
        "press_success_by_zone":    d.get("press_success_by_zone", {}),
        "press_success_rate":       d.get("press_success_rate", 0.0),
        "press_success_total":      d.get("press_success_total", 0),
        "press_success_successful": d.get("press_success_successful", 0),
    }
    return [dcc.Store(id="opp-season-press-store", data=store_data)]


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def build_pressing_section(season: str, team_name: str) -> html.Div:
    """
    Build the full season-aggregate Defensive Pressing section.
    Called lazily by the opp-section-dp callback.
    """
    season_label = season.replace("_", "/")
    d = compute_season_pressing(season, team_name)

    no_data_banner = None
    if d["total_def_actions"] == 0:
        no_data_banner = dbc.Alert(
            [
                html.I(className="bi bi-exclamation-triangle-fill me-2"),
                f"No pressing data found for {team_name} ({season_label}). "
                "Run precompute_season_pressing() to generate the parquet.",
            ],
            color="warning", className="mb-3",
        )

    return html.Div(
        [
            ds_header(
                "Opponent Analysis — Season View",
                "bi-shield-fill-exclamation",
                f"Defensive Pressing — {team_name}  ({season_label})",
                "Season-aggregate pressing intensity, direction, success by zone "
                "and action density map",
            ),
            *_pressing_stores(d),
            *_build_all_modals(),
            *([] if no_data_banner is None else [no_data_banner]),

            # A — KPI overview (5 cards)
            html.Div(_section_overview(d), style={"marginBottom": "1.5rem"}),

            html.Hr(style={"borderColor": "var(--border-light)", "margin": "1.5rem 0"}),

            # B — Three-column distributions
            html.Div(_section_distributions(d), style={"marginBottom": "1.5rem"}),

            html.Hr(style={"borderColor": "var(--border-light)", "margin": "1.5rem 0"}),

            # C — Single combined pitch map (C5)
            html.Div(_section_pitch_map(d), style={"marginBottom": "1.5rem"}),
        ],
        className="analysis-section buildup-card ma-card",
        style={"marginBottom": "2rem", "padding": "1.5rem"},
    )
