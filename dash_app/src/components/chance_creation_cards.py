"""
Chance Creation Analysis — UI Components
=========================================
Dash components for the Chance Creation card inside
Offensive Phase → Build-up.

Follows the exact same patterns as general_buildup_cards.py and
final_third_cards.py.
"""

from __future__ import annotations

from typing import Union

import pandas as pd
from dash import html, dcc
import plotly.graph_objects as go

from src.styling.theme import COLORS_DARK, SEMANTIC_COLORS
from src.styling.plotly_template import apply_chart_theme
from src.styling.ui_components import ds_header


# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

ORIGIN_LABELS = [
    "Set Piece", "High Regain", "Cross", "Through Ball", "Cut Back",
    "Individual Play", "Combination",
]
MATRIX_ROWS = ["N", "xG", "SoT%", "GS"]

# Canonical 7-category attack-origin taxonomy (SEMANTIC_COLORS origin_* —
# distinct from the FT entry-method taxonomy method_*; same-named categories
# like "Set Piece" intentionally keep different colours across the two).
ORIGIN_COLORS = {
    "Set Piece":       SEMANTIC_COLORS["origin_set_piece"],        # green
    "High Regain":     SEMANTIC_COLORS["origin_high_regain"],      # red — pressing recovery
    "Cross":           SEMANTIC_COLORS["origin_cross"],            # cyan
    "Through Ball":    SEMANTIC_COLORS["origin_through_ball"],     # purple
    "Cut Back":        SEMANTIC_COLORS["origin_cut_back"],         # orange
    "Individual Play": SEMANTIC_COLORS["origin_individual_play"],  # yellow — solo dribble
    "Combination":     SEMANTIC_COLORS["origin_combination"],      # blue — patient build-up
    "TOTAL":           COLORS_DARK["accent"],                      # primary
}

ORIGIN_ICONS = {
    "Set Piece":       "bi-flag-fill",
    "High Regain":     "bi-shield-fill-exclamation",
    "Cross":           "bi-arrow-up-right",
    "Through Ball":    "bi-chevron-double-up",
    "Cut Back":        "bi-arrow-return-left",
    "Individual Play": "bi-person-fill-up",
    "Combination":     "bi-shuffle",
}

TIER_META = {
    "level_3_converted": {
        "label": "Converted",
        "color": SEMANTIC_COLORS["tier_converted"],     # "#22c55e"
        "icon": "bi-check-circle-fill",
        "desc": "Goal scored",
    },
    "level_2_threat": {
        "label": "Big Chance",
        "color": SEMANTIC_COLORS["tier_big_chance"],    # "#f97316"
        "icon": "bi-exclamation-triangle-fill",
        "desc": "Opta Big Chance qualifier",
    },
    "level_0_low": {
        "label": "Speculative",
        "color": SEMANTIC_COLORS["tier_speculative"],   # "#6b7280"
        "icon": "bi-dash-circle",
        "desc": "No Big Chance qualifier",
    },
}

# Row label display config
ROW_META = {
    "N":    {"color": "#94a3b8", "fmt": "d"},
    "xG":   {"color": "#3b82f6", "fmt": ".2f"},
    "SoT%": {"color": "#f43f5e", "fmt": ".1f%"},
    "GS":   {"color": "#22c55e", "fmt": "d"},
}


# ═══════════════════════════════════════════════════════════════════════════════
# PENALTY STAT HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def extract_penalty_stats(
    shots: Union[list, pd.DataFrame],
    team: str | None = None,
) -> dict:
    """Return penalty counts for the given shot collection.

    ``is_penalty`` is set by ``ChanceCreationAnalyzer._extract_shots()`` at
    analysis time (per-match list path) or written into ``shots_{season}.parquet``
    by ``precompute_season_offensive()`` (season-aggregate DataFrame path).
    Both paths are handled transparently.

    Parameters
    ----------
    shots:
        Either a ``list[dict]`` (shots_detail from per-match analysis) or a
        ``pd.DataFrame`` (rows from ``shots_{season}.parquet``).
    team:
        Optional canonical team name.  When supplied, only rows whose ``team``
        column matches (case-insensitive, via ``canonical_name``) are counted.
        Ignored when the caller has already pre-filtered to one team.

    Returns
    -------
    dict with keys:
        awarded          – int: penalty shots taken (type_id in 13/14/15/16 with Penalty="Si")
        scored           – int: subset where is_goal is True
        conversion_rate  – float | None: scored/awarded*100 (1 dp), None if awarded==0
    """
    from src.team_mapping import canonical_name as _cn

    if isinstance(shots, pd.DataFrame):
        df = shots
        if team is not None and "team" in df.columns:
            target = _cn(team).lower()
            df = df[df["team"].apply(lambda t: _cn(str(t)).lower() == target)]
        if "is_penalty" not in df.columns:
            return {"awarded": 0, "scored": 0, "conversion_rate": None}
        pen = df[df["is_penalty"] == True]  # noqa: E712
        awarded = int(len(pen))
        scored  = int(pen["is_goal"].sum()) if "is_goal" in pen.columns else 0
    else:
        rows = shots
        if team is not None:
            target = _cn(team).lower()
            rows = [s for s in rows if _cn(str(s.get("team", ""))).lower() == target]
        awarded = sum(1 for s in rows if s.get("is_penalty"))
        scored  = sum(1 for s in rows if s.get("is_penalty") and s.get("is_goal"))

    conversion_rate = (
        round(scored / awarded * 100, 1) if awarded > 0 else None
    )
    return {"awarded": awarded, "scored": scored, "conversion_rate": conversion_rate}


def set_piece_count_excl_penalties(
    shots: Union[list, pd.DataFrame],
    team: str | None = None,
) -> int:
    """Return the Set Piece shot count with penalty shots subtracted.

    Penalties are classified as "Set Piece" by ``classify_attack_origin()``
    (via the direct-qualifier path).  This helper removes them so the Set Piece
    card reflects only corners, free kicks, and throw-ins.

    Parameters
    ----------
    shots:
        Either a ``list[dict]`` (shots_detail from per-match analysis) or a
        ``pd.DataFrame`` (rows from ``shots_{season}.parquet``).
    team:
        Optional canonical team name filter (same semantics as
        ``extract_penalty_stats``).

    Returns
    -------
    int – count of shots where ``origin == "Set Piece"`` AND ``is_penalty`` is falsy.
    """
    from src.team_mapping import canonical_name as _cn

    if isinstance(shots, pd.DataFrame):
        df = shots
        if team is not None and "team" in df.columns:
            target = _cn(team).lower()
            df = df[df["team"].apply(lambda t: _cn(str(t)).lower() == target)]
        if "is_penalty" not in df.columns:
            # Parquet pre-dates the column — fall back to raw Set Piece count
            return int((df["origin"] == "Set Piece").sum()) if "origin" in df.columns else 0
        mask = (df["origin"] == "Set Piece") & (~df["is_penalty"].fillna(False))
        return int(mask.sum())
    else:
        return sum(
            1 for s in shots
            if s.get("origin") == "Set Piece" and not s.get("is_penalty", False)
        )


# ═══════════════════════════════════════════════════════════════════════════════
# PENALTY CARD COMPONENT
# ═══════════════════════════════════════════════════════════════════════════════

# Visual identity for the Penalty card — matches the Set Piece green family
# (penalties are a Set Piece sub-type) with a distinct dot-circle icon.
_PENALTY_COLOR = SEMANTIC_COLORS["origin_set_piece"]
_PENALTY_ICON  = "bi-dot"


def penalty_origin_card(
    awarded: int,
    scored: int,
    conversion_rate: float | None,
    card_id: str | None = None,
) -> html.Div:
    """Penalty origin card for the Attack Origin Breakdown row.

    Visually identical to the other origin cards in ``_section_origin_breakdown``
    (same container class ``kpi-card``, same ``kpi-icon`` / ``kpi-text`` layout,
    same CSS variable references).  Penalty is always placed LAST in the row.

    Parameters
    ----------
    awarded:
        Total penalties awarded (shot rows with is_penalty=True).
    scored:
        Penalties that resulted in a goal.
    conversion_rate:
        ``scored / awarded * 100`` rounded to 1 dp, or ``None`` if awarded==0.
    card_id:
        Optional component id (required only for the season-aggregate defensive
        location which registers a callback on the card).

    Theme compatibility
    -------------------
    Uses only existing CSS variables (``var(--text-muted)``, ``kpi-card``,
    ``kpi-label``, ``kpi-value``, ``kpi-subtitle``, ``kpi-icon``, ``kpi-text``).
    No new CSS classes are introduced.
    """
    if awarded == 0:
        primary_value = "—"
        subtitle_text = "No penalties"
    else:
        primary_value = str(scored)
        conv_str = f"{conversion_rate}%" if conversion_rate is not None else "—"
        subtitle_text = f"{awarded} awarded · {conv_str} conv."

    children = [
        html.Div(
            html.I(
                className=f"bi {_PENALTY_ICON}",
                style={"color": _PENALTY_COLOR, "fontSize": "1.1rem"},
            ),
            className="kpi-icon",
        ),
        html.Div(
            [
                html.Span("Penalty", className="kpi-label"),
                html.Span(primary_value, className="kpi-value"),
                html.Span(
                    subtitle_text,
                    className="kpi-subtitle",
                    style={"color": _PENALTY_COLOR},
                ),
            ],
            className="kpi-text",
        ),
    ]

    kwargs: dict = {"className": "kpi-card"}
    if card_id is not None:
        kwargs["id"] = card_id

    return html.Div(children, **kwargs)


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER — mini KPI card (same as other cards modules)
# ═══════════════════════════════════════════════════════════════════════════════

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
# A. SHOT OVERVIEW KPIs
# ═══════════════════════════════════════════════════════════════════════════════

def _section_shot_overview(sm: dict, matrix: dict) -> html.Div:
    """Top-level shot volume and xG overview KPIs."""
    total_xg = matrix.get("TOTAL", {}).get("xG", 0.0)
    total_sot_pct = matrix.get("TOTAL", {}).get("SoT%", 0.0)
    total_gs = matrix.get("TOTAL", {}).get("GS", 0)

    return html.Div(
        [
            html.H6("Shot Overview", className="buildup-subsection-title"),
            html.Div(
                [
                    _mini_kpi(
                        "Total Shots", sm.get("shots_total", 0),
                        f"{sm.get('shot_freq_pct', 0)}% of possessions",
                        "#3b82f6", "bi-crosshair",
                    ),
                    _mini_kpi(
                        "In-Box", sm.get("shots_in_box", 0),
                        f"{sm.get('pct_in_box', 0)}% of shots",
                        "#8b5cf6", "bi-box-arrow-in-down-right",
                    ),
                    _mini_kpi(
                        "Out-Box", sm.get("shots_out_box", 0),
                        f"{sm.get('pct_out_box', 0)}% of shots",
                        "#6b7280", "bi-box-arrow-up-right",
                    ),
                    _mini_kpi(
                        "SoT %", f"{sm.get('sot_pct_total', 0)}%",
                        "shots on target",
                        "#f43f5e", "bi-bullseye",
                    ),
                    _mini_kpi(
                        "xG Total", f"{total_xg:.2f}",
                        f"xG/Shot: {sm.get('xg_per_shot', 0):.2f}",
                        "#3b82f6", "bi-graph-up-arrow",
                    ),
                    _mini_kpi(
                        "Goals", total_gs,
                        f"SoT%: {total_sot_pct:.1f}%",
                        "#22c55e", "bi-trophy-fill",
                    ),
                ],
                className="team-kpi-row",
            ),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# B. CHAIN-TO-GOAL MATRIX
# ═══════════════════════════════════════════════════════════════════════════════

def _section_chain_to_goal_matrix(matrix: dict) -> html.Div:
    """Render the 5-origin × 4-row Chain-to-Goal Matrix as a styled table."""
    # Column headers = origins + TOTAL
    columns = ORIGIN_LABELS + ["TOTAL"]

    # Build table header
    header_cells = [html.Th("", style={"width": "60px"})]
    for col in columns:
        color = ORIGIN_COLORS.get(col, "#8a1f33")
        header_cells.append(
            html.Th(
                col,
                style={
                    "color": color,
                    "fontWeight": "600",
                    "fontSize": "0.78rem",
                    "textAlign": "center",
                    "padding": "0.6rem 0.5rem",
                    "textTransform": "uppercase",
                    "letterSpacing": "0.5px",
                },
            )
        )

    # Build table body rows
    body_rows = []
    for row_key in MATRIX_ROWS:
        meta = ROW_META[row_key]
        row_cells = [
            html.Td(
                row_key,
                style={
                    "fontWeight": "600",
                    "color": meta["color"],
                    "fontSize": "0.82rem",
                    "padding": "0.5rem 0.6rem",
                },
            )
        ]

        # Gather values to find max for highlighting
        values = []
        for col in columns:
            val = matrix.get(col, {}).get(row_key, 0)
            values.append(val)

        max_val = max(values) if values else 0

        for i, col in enumerate(columns):
            val = values[i]
            is_total = col == "TOTAL"
            is_max = (val == max_val and max_val > 0 and not is_total)

            # Format value
            if meta["fmt"] == "d":
                display = str(int(val))
            elif meta["fmt"] == ".1f%":
                display = f"{val:.1f}%"
            else:
                display = f"{val:.2f}"

            cell_style = {
                "textAlign": "center",
                "padding": "0.5rem 0.4rem",
                "fontSize": "0.95rem",
                "fontWeight": "700" if is_total else "600",
                "borderRadius": "6px",
            }

            if is_total:
                cell_style["color"] = "#8a1f33"
                cell_style["background"] = "rgba(138, 31, 51, 0.08)"
            elif is_max:
                # Highlight the max origin per row
                cell_style["color"] = ORIGIN_COLORS.get(col, "#fff")
                cell_style["background"] = f"rgba(138, 31, 51, 0.06)"
            else:
                cell_style["color"] = "var(--text-secondary)"

            row_cells.append(html.Td(display, style=cell_style))

        body_rows.append(html.Tr(row_cells))

    # Shot count sub-row (number of shots per origin)
    count_cells = [
        html.Td(
            "Shots",
            style={
                "fontWeight": "500",
                "color": "var(--text-muted)",
                "fontSize": "0.75rem",
                "padding": "0.4rem 0.6rem",
                "textTransform": "uppercase",
                "letterSpacing": "0.5px",
            },
        )
    ]
    # shots_detail not available here, so derive from GS or use matrix info
    # We'll count from the matrix (approximate via xG distribution)
    for col in columns:
        gs = matrix.get(col, {}).get("GS", 0)
        xg = matrix.get(col, {}).get("xG", 0)
        # Estimate count from xG (rough: shots ~ xG / avg_xG)
        # This is displayed in the shot-origin section instead
        count_cells.append(
            html.Td(
                "",
                style={
                    "textAlign": "center",
                    "padding": "0.3rem 0.4rem",
                    "fontSize": "0.75rem",
                    "color": "var(--text-muted)",
                },
            )
        )

    table = html.Table(
        [
            html.Thead(html.Tr(header_cells)),
            html.Tbody(body_rows),
        ],
        style={
            "width": "100%",
            "borderCollapse": "separate",
            "borderSpacing": "4px",
        },
    )

    return html.Div(
        [
            html.H6("Chain-to-Goal Matrix", className="buildup-subsection-title"),
            html.Div(
                "Rows: N (shots) · xG (total) · SoT% (shots on target) · GS (goals) — all columns use consistent aggregation",
                style={
                    "fontSize": "0.75rem",
                    "color": "var(--text-muted)",
                    "marginBottom": "0.8rem",
                },
            ),
            html.Div(
                table,
                className="pitch-dark-container chain-goal-matrix-table",
                style={
                    "borderRadius": "var(--radius-sm)",
                    "padding": "0.8rem",
                    "overflowX": "auto",
                },
            ),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# C. ORIGIN BREAKDOWN (bar + KPIs)
# ═══════════════════════════════════════════════════════════════════════════════

def _section_origin_breakdown(shots_detail: list) -> html.Div:
    """Show the distribution of shots across the 5 attack origins."""
    total = max(len(shots_detail), 1)

    counts = {}
    for origin in ORIGIN_LABELS:
        counts[origin] = sum(1 for s in shots_detail if s["origin"] == origin)

    # Stacked horizontal bar
    bar_fig = go.Figure()
    for origin in ORIGIN_LABELS:
        count = counts[origin]
        if count == 0:
            continue
        pct = round(count / total * 100, 1)
        bar_fig.add_trace(go.Bar(
            y=["Origin"],
            x=[pct],
            orientation="h",
            name=origin,
            marker_color=ORIGIN_COLORS[origin],
            text=[f"{origin} {pct}%"],
            textposition="inside",
            textfont=dict(size=10, color="#fff"),
            hovertemplate=f"{origin}: {count} ({pct}%)<extra></extra>",
        ))
    apply_chart_theme(bar_fig, "dark")
    bar_fig.update_layout(
        barmode="stack",
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=0, b=0), height=42,
        xaxis=dict(showgrid=False, showticklabels=False,
                   range=[0, 100], fixedrange=True),
        yaxis=dict(showgrid=False, showticklabels=False, fixedrange=True),
        showlegend=False,
    )

    # Penalty stats and adjusted Set Piece count (penalty shots excluded from Set Piece)
    _pen_stats_detail = extract_penalty_stats(shots_detail)
    _sp_excl          = set_piece_count_excl_penalties(shots_detail)

    # KPI cards per origin
    cards = []
    for origin in ORIGIN_LABELS:
        count = counts[origin]
        if origin == "Set Piece":
            count = _sp_excl
        if count == 0:
            continue
        pct = round(count / total * 100, 1)
        goals = sum(1 for s in shots_detail
                    if s["origin"] == origin and s["is_goal"])
        xg_sum = sum(s["xG"] for s in shots_detail if s["origin"] == origin)

        cards.append(
            html.Div(
                [
                    html.Div(
                        html.I(
                            className=f"bi {ORIGIN_ICONS[origin]}",
                            style={
                                "color": ORIGIN_COLORS[origin],
                                "fontSize": "1.1rem",
                            },
                        ),
                        className="kpi-icon",
                    ),
                    html.Div(
                        [
                            html.Span(origin, className="kpi-label"),
                            html.Span(str(count), className="kpi-value"),
                            html.Span(
                                f"{pct}% · {goals}G · xG {xg_sum:.2f}",
                                className="kpi-subtitle",
                                style={"color": ORIGIN_COLORS[origin]},
                            ),
                        ],
                        className="kpi-text",
                    ),
                ],
                className="kpi-card",
            )
        )

    # Penalty card appended last
    cards.append(penalty_origin_card(
        awarded=_pen_stats_detail["awarded"],
        scored=_pen_stats_detail["scored"],
        conversion_rate=_pen_stats_detail["conversion_rate"],
    ))

    return html.Div(
        [
            html.H6("Attack Origin Breakdown", className="buildup-subsection-title"),
            html.Div(
                "Priority: Set Piece → High Regain → Counter → Cross → Through Ball → Combination · Penalty",
                style={
                    "fontSize": "0.78rem",
                    "color": "var(--text-muted)",
                    "marginBottom": "0.6rem",
                },
            ),
            html.Div(cards, className="team-kpi-row"),
            dcc.Graph(figure=bar_fig, config={"displayModeBar": False},
                      style={"marginTop": "0.5rem"}),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# D. SHOT QUALITY TIERS
# ═══════════════════════════════════════════════════════════════════════════════

def _section_shot_quality(tiers: dict, shots_detail: list) -> html.Div:
    """Shot quality tier distribution — donut chart + KPI cards."""
    total = max(len(shots_detail), 1)

    # Donut chart
    tier_keys = ["level_3_converted", "level_2_threat", "level_0_low"]
    labels = []
    values = []
    colors = []
    for tk in tier_keys:
        meta = TIER_META[tk]
        t = tiers.get(tk, {})
        labels.append(meta["label"])
        values.append(t.get("count", 0))
        colors.append(meta["color"])

    donut_fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        hole=0.55,
        marker=dict(colors=colors, line=dict(color="rgba(0,0,0,0.3)", width=1)),
        textinfo="label+percent",
        textfont=dict(size=11, color="#e2e8f0"),
        hovertemplate="%{label}: %{value} shots (%{percent})<extra></extra>",
        sort=False,
    )])
    apply_chart_theme(donut_fig, "dark")
    donut_fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=10, b=10), height=220,
        showlegend=False,
        annotations=[dict(
            text=f"<b>{total}</b><br><span style='font-size:10px'>shots</span>",
            x=0.5, y=0.5, font_size=18, font_color="#e2e8f0",
            showarrow=False,
        )],
    )

    # KPI cards
    cards = []
    for tk in tier_keys:
        meta = TIER_META[tk]
        t = tiers.get(tk, {})
        cards.append(
            _mini_kpi(
                meta["label"], t.get("count", 0),
                f"{t.get('pct', 0)}% · {meta['desc']}",
                meta["color"], meta["icon"],
            )
        )

    return html.Div(
        [
            html.H6("Shot Quality Tiers", className="buildup-subsection-title"),
            html.Div(
                [
                    html.Div(
                        dcc.Graph(figure=donut_fig, config={"displayModeBar": False}),
                        style={"flex": "0 0 240px", "minWidth": "200px"},
                    ),
                    html.Div(
                        cards,
                        className="team-kpi-row",
                        style={"flex": "1", "minWidth": "0"},
                    ),
                ],
                style={"display": "flex", "gap": "1.5rem",
                       "alignItems": "center", "flexWrap": "wrap"},
            ),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# E. SHOT MAP (scatter on half-pitch)
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_half_pitch(fig: go.Figure) -> None:
    """Draw right half of pitch outline (x ≥ 50)."""
    line_color = "rgba(255,255,255,0.25)"
    lw = 1.5

    shapes = [
        # Pitch outline (right half)
        dict(type="rect", x0=50, y0=0, x1=100, y1=100,
             line=dict(color=line_color, width=lw)),
        # Penalty box
        dict(type="rect", x0=83.33, y0=21.1, x1=100, y1=78.9,
             line=dict(color=line_color, width=lw)),
        # Six-yard box
        dict(type="rect", x0=94.17, y0=36.8, x1=100, y1=63.2,
             line=dict(color=line_color, width=lw)),
        # Penalty spot
        dict(type="circle", x0=88-0.6, y0=50-0.6, x1=88+0.6, y1=50+0.6,
             fillcolor=line_color, line=dict(color=line_color, width=0)),
        # Centre circle arc (partial — right half only)
        dict(type="circle", x0=50-9.15, y0=50-9.15, x1=50+9.15, y1=50+9.15,
             line=dict(color=line_color, width=lw)),
        # D-arc
        dict(type="circle", x0=88-9.15, y0=50-9.15, x1=88+9.15, y1=50+9.15,
             line=dict(color=line_color, width=lw)),
        # Goal
        dict(type="rect", x0=100, y0=44.2, x1=102, y1=55.8,
             line=dict(color=line_color, width=lw)),
        # Final third line
        dict(type="line", x0=66.67, y0=0, x1=66.67, y1=100,
             line=dict(color="rgba(255,255,255,0.12)", width=1, dash="dot")),
    ]
    for s in shapes:
        fig.add_shape(**s)


def _section_shot_map(shots_detail: list) -> html.Div:
    """Scatter plot of shot locations coloured by origin."""
    if not shots_detail:
        return html.Div()

    fig = go.Figure()

    for origin in ORIGIN_LABELS:
        origin_shots = [s for s in shots_detail if s["origin"] == origin]
        if not origin_shots:
            continue

        xs = [s["x"] for s in origin_shots]
        ys = [s["y"] for s in origin_shots]
        goals = [s["is_goal"] for s in origin_shots]
        texts = [
            f"{s['player']}<br>{s['minute']}' — xG {s['xG']:.2f}"
            + (" ⚽" if s["is_goal"] else "")
            for s in origin_shots
        ]

        # Goals as stars, others as circles
        goal_xs = [x for x, g in zip(xs, goals) if g]
        goal_ys = [y for y, g in zip(ys, goals) if g]
        goal_texts = [t for t, g in zip(texts, goals) if g]
        non_xs = [x for x, g in zip(xs, goals) if not g]
        non_ys = [y for y, g in zip(ys, goals) if not g]
        non_texts = [t for t, g in zip(texts, goals) if not g]

        if non_xs:
            fig.add_trace(go.Scatter(
                x=non_xs, y=non_ys,
                mode="markers",
                marker=dict(
                    size=10,
                    color=ORIGIN_COLORS[origin],
                    opacity=0.75,
                    line=dict(color="rgba(255,255,255,0.4)", width=1),
                ),
                name=origin,
                text=non_texts,
                hoverinfo="text",
            ))

        if goal_xs:
            fig.add_trace(go.Scatter(
                x=goal_xs, y=goal_ys,
                mode="markers",
                marker=dict(
                    size=14,
                    color=ORIGIN_COLORS[origin],
                    symbol="star",
                    line=dict(color="#fff", width=1.5),
                ),
                name=f"{origin} (Goal)",
                text=goal_texts,
                hoverinfo="text",
            ))

    _draw_half_pitch(fig)

    apply_chart_theme(fig, "dark")

    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=5, r=5, t=5, b=5),
        height=320,
        xaxis=dict(
            range=[49, 103], showgrid=False, showticklabels=False,
            fixedrange=True, zeroline=False,
        ),
        yaxis=dict(
            range=[-2, 102], showgrid=False, showticklabels=False,
            fixedrange=True, zeroline=False, scaleanchor="x",
        ),
        showlegend=True,
        legend=dict(
            orientation="h", yanchor="bottom", y=-0.15,
            xanchor="center", x=0.5,
            font=dict(size=10, color="#94a3b8"),
            bgcolor="rgba(0,0,0,0)",
        ),
    )

    return html.Div(
        [
            html.H6("Shot Map", className="buildup-subsection-title"),
            html.Div(
                "⭐ = goal · circle = shot · colour = attack origin",
                style={
                    "fontSize": "0.75rem",
                    "color": "var(--text-muted)",
                    "marginBottom": "0.5rem",
                },
            ),
            html.Div(
                dcc.Graph(figure=fig, config={"displayModeBar": False}),
                className="pitch-dark-container",
            ),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# F. PER-ORIGIN xG BARS
# ═══════════════════════════════════════════════════════════════════════════════

def _section_xg_by_origin(matrix: dict) -> html.Div:
    """Horizontal bar chart of xG per attack origin."""
    origins = [o for o in ORIGIN_LABELS if matrix.get(o, {}).get("xG", 0) > 0]
    if not origins:
        return html.Div()

    xg_vals = [matrix[o]["xG"] for o in origins]
    colors = [ORIGIN_COLORS[o] for o in origins]

    fig = go.Figure(go.Bar(
        y=origins,
        x=xg_vals,
        orientation="h",
        marker_color=colors,
        text=[f"{v:.2f}" for v in xg_vals],
        textposition="outside",
        textfont=dict(size=11, color="#e2e8f0"),
        hovertemplate="%{y}: xG = %{x:.2f}<extra></extra>",
    ))
    apply_chart_theme(fig, "dark")
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=80, r=40, t=10, b=10), height=max(120, len(origins) * 35),
        xaxis=dict(showgrid=False, showticklabels=False, fixedrange=True),
        yaxis=dict(
            showgrid=False, fixedrange=True, autorange="reversed",
            tickfont=dict(size=11, color="#94a3b8"),
        ),
        showlegend=False,
    )

    return html.Div(
        [
            html.H6("xG by Attack Origin", className="buildup-subsection-title"),
            dcc.Graph(figure=fig, config={"displayModeBar": False}),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# G. ATTACK ORIGIN GRID — Full Pitch (18 Zones + Half-Space overlays)
# ═══════════════════════════════════════════════════════════════════════════════

# Standard 18-zone grid (same as pitch_zones / final_third_cards)
_OG_X_EDGES = [0, 16.67, 33.33, 50.0, 66.67, 83.33, 100.0]
_OG_Y_EDGES = [0, 33.33, 66.67, 100.0]
_OG_N_ROWS = 6   # x-axis bands
_OG_N_COLS = 3   # y-axis corridors (R / C / L)

# Half-space y boundaries (visual dashed overlays only)
_HS_Y_VALS = (15.0, 30.0, 70.0, 85.0)


def _classify_18zone(x: float, y: float) -> int:
    """Return zone number 1–18 for standard 18-zone grid."""
    row = min(int(x / 16.67), 5)
    col = min(int(y / 33.33), 2)
    return row * 3 + col + 1


def _section_origin_grid(shots_detail: list) -> html.Div:
    """
    Full-pitch 18-zone grid showing shot outcome dots (green/red).

    Half-space boundaries drawn as dashed lines with labels in the
    first two thirds of the pitch.  Matches FT Entry Zones style/size.
    """
    if not shots_detail:
        return html.Div()

    # Accumulate per zone: total positive / negative counts
    zone_pos: dict[int, int] = {z: 0 for z in range(1, 19)}
    zone_neg: dict[int, int] = {z: 0 for z in range(1, 19)}

    for s in shots_detail:
        z = _classify_18zone(s["x"], s["y"])
        if s["is_goal"] or s["on_target"]:
            zone_pos[z] += 1
        else:
            zone_neg[z] += 1

    fig = go.Figure()

    max_count = max(
        (zone_pos[z] + zone_neg[z] for z in range(1, 19)),
        default=1,
    ) or 1

    for zone_num in range(1, 19):
        row = (zone_num - 1) // _OG_N_COLS
        col = (zone_num - 1) % _OG_N_COLS

        x0 = _OG_X_EDGES[row]
        x1 = _OG_X_EDGES[row + 1]
        y0 = _OG_Y_EDGES[col]
        y1 = _OG_Y_EDGES[col + 1]
        cx = (x0 + x1) / 2
        cy = (y0 + y1) / 2

        pos = zone_pos[zone_num]
        neg = zone_neg[zone_num]
        total = pos + neg
        intensity = total / max_count if max_count else 0

        fill_a = 0.08 + 0.50 * intensity if total else 0.04
        fill = f"rgba(138, 31, 51, {fill_a:.2f})"

        fig.add_shape(
            type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
            line=dict(color="rgba(255,255,255,0.10)", width=0.5),
            fillcolor=fill, layer="below",
        )

        if total > 0:
            # Bold count
            fig.add_annotation(
                x=cx, y=cy + 4,
                text=f"<b>{total}</b>",
                showarrow=False,
                font=dict(size=16, color="#f0f0f0"),
            )
            # Zone label
            fig.add_annotation(
                x=cx, y=cy - 4,
                text=f"Z{zone_num}",
                showarrow=False,
                font=dict(size=9, color="rgba(255,255,255,0.55)"),
            )
            # Outcome dots — only green/red, no origin abbreviation
            dot_parts: list[str] = []
            if pos > 0:
                dot_parts.append(
                    f"<span style='color:#22c55e'>●{pos}</span>"
                )
            if neg > 0:
                dot_parts.append(
                    f"<span style='color:#ef4444'>●{neg}</span>"
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

    # ── Half-space dashed lines (full pitch) ──
    for y_val in _HS_Y_VALS:
        fig.add_shape(
            type="line", x0=0, x1=100, y0=y_val, y1=y_val,
            line=dict(color="rgba(255,255,255,0.20)", width=1, dash="dash"),
            layer="below",
        )

    # ── "half space" labels in the first 2/3 of the pitch ──
    # Right half-space (y 15–30) and Left half-space (y 70–85)
    for hs_y, label in ((22.5, "half space"), (77.5, "half space")):
        fig.add_annotation(
            x=33.33, y=hs_y,
            text=label,
            showarrow=False,
            font=dict(size=9, color="rgba(255,255,255,0.30)"),
            textangle=0,
        )

    # ── Corridor dividers (solid, standard 18-zone) ──
    for y_val in (33.33, 66.67):
        fig.add_shape(
            type="line", x0=0, x1=100, y0=y_val, y1=y_val,
            line=dict(color="rgba(255,255,255,0.12)", width=1),
            layer="below",
        )
    for x_val in _OG_X_EDGES[1:-1]:
        fig.add_shape(
            type="line", x0=x_val, x1=x_val, y0=0, y1=100,
            line=dict(color="rgba(255,255,255,0.12)", width=1),
            layer="below",
        )

    # ── Pitch markings ──
    fig.add_shape(
        type="rect", x0=0, x1=100, y0=0, y1=100,
        line=dict(color="rgba(255,255,255,0.35)", width=1.5),
        fillcolor="rgba(0,0,0,0)",
    )
    fig.add_shape(
        type="line", x0=50, x1=50, y0=0, y1=100,
        line=dict(color="rgba(255,255,255,0.25)", width=1, dash="dash"),
        layer="below",
    )
    fig.add_shape(
        type="rect", x0=0, x1=16.5, y0=21, y1=79,
        line=dict(color="rgba(255,255,255,0.18)", width=1),
        fillcolor="rgba(0,0,0,0)",
    )
    fig.add_shape(
        type="rect", x0=83.5, x1=100, y0=21, y1=79,
        line=dict(color="rgba(255,255,255,0.18)", width=1),
        fillcolor="rgba(0,0,0,0)",
    )
    fig.add_shape(
        type="line", x0=66.67, x1=66.67, y0=0, y1=100,
        line=dict(color="rgba(255,255,255,0.6)", width=2, dash="dash"),
    )

    fig.add_annotation(
        x=92, y=-6,
        text="ATK →",
        showarrow=False,
        font=dict(size=9, color="rgba(255,255,255,0.35)"),
    )
    fig.add_annotation(
        x=8, y=-6,
        text="← OWN GOAL",
        showarrow=False,
        font=dict(size=9, color="rgba(255,255,255,0.35)"),
    )

    apply_chart_theme(fig, "dark")

    fig.update_layout(
        plot_bgcolor="rgba(15,25,35,0.7)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=10, b=20),
        height=400,
        xaxis=dict(
            range=[-2, 102], showgrid=False, showticklabels=False,
            fixedrange=True, zeroline=False,
        ),
        yaxis=dict(
            range=[-10, 105], showgrid=False, showticklabels=False,
            fixedrange=True, zeroline=False,
            scaleanchor="x", scaleratio=0.68,
        ),
        showlegend=False,
    )

    return html.Div(
        [
            html.H6("Attack Origin Zones",
                     className="buildup-subsection-title"),
            html.Div(
                [
                    html.Span("● ", style={"color": "#22c55e",
                                            "fontSize": "0.85rem"}),
                    html.Span("on target / goal", style={
                        "fontSize": "0.75rem",
                        "color": "var(--text-muted)",
                        "marginRight": "1rem",
                    }),
                    html.Span("● ", style={"color": "#ef4444",
                                            "fontSize": "0.85rem"}),
                    html.Span("miss / block", style={
                        "fontSize": "0.75rem",
                        "color": "var(--text-muted)",
                    }),
                ],
                style={"marginBottom": "0.5rem"},
            ),
            html.Div(
                dcc.Graph(figure=fig, config={"displayModeBar": False}),
                className="pitch-dark-container",
            ),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# FULL CARD ASSEMBLER
# ═══════════════════════════════════════════════════════════════════════════════

def chance_creation_card(data: dict) -> html.Div:
    """
    Assemble the complete Chance Creation card.

    Parameters
    ----------
    data : dict
        Output of ``analyse_chance_creation()``.
        Must contain keys:
        - ``chain_to_goal_matrix``
        - ``shot_metrics``
        - ``shot_quality_tiers``
        - ``shots_detail``
    """
    matrix = data.get("chain_to_goal_matrix", {})
    sm = data.get("shot_metrics", {})
    tiers = data.get("shot_quality_tiers", {})
    shots = data.get("shots_detail", [])

    _header = ds_header(
        "Offensive Phase — Chance Creation", "bi-bullseye",
        "Chance Creation",
        "Shots by attack origin — volume, xG, quality tiers and locations",
    )

    if sm.get("shots_total", 0) == 0 and not shots:
        return html.Div(
            [
                _header,
                html.P(
                    "No shots found for this team in this match.",
                    className="text-muted",
                    style={"padding": "2rem", "textAlign": "center"},
                ),
            ],
            className="buildup-card ma-card",
        )

    sep = html.Hr(style={"borderColor": "var(--border-light)",
                         "margin": "1.5rem 0"})

    sections = [
        _header,
        # 1 — Shot overview KPIs
        _section_shot_overview(sm, matrix),
        sep,
        # 2 — Attack origin breakdown
        _section_origin_breakdown(shots),
        sep,
        # 3 — xG by origin
        _section_xg_by_origin(matrix),
        sep,
        # 4 — Attack Origin Zones (offensive third grid)
        _section_origin_grid(shots),
        sep,
        # 5 — Shot Map
        _section_shot_map(shots),
        sep,
        # 5 — Shot quality tiers
        _section_shot_quality(tiers, shots),
        sep,
        # 6 — Chain-to-Goal Matrix (end of page)
        _section_chain_to_goal_matrix(matrix),
    ]

    return html.Div(sections, className="buildup-card ma-card")
