"""
dash_app/src/components/playing_style_cards.py
==============================================
Playing Style Wheel section for the Team Overview (team detail) page.

A 12-segment Barpolar (Nightingale/rose) chart grouped into 4 colour-coded
phase quadrants — Defence, Possession, Progression, Attack — each holding 3
within-Serie-A season-percentile KPIs (0–99). Below the wheel sits a compact
2×6 grid of the underlying raw values, and a "View League Comparison" button
opens a unified modal with the full 20-team percentile table.

Theme: built server-side for "dark"/"light" (the client-side toggle observer
does not patch polar axes), with transparent backgrounds so the CSS card bg
shows through. The four phase accent colours are the only hardcoded hues and
are defined once below so they can be changed from a single place.

Data source: data_loader.load_playing_style(season) →
playing_style_league_{season}.parquet (see analytics/playing_style.py).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import dash_bootstrap_components as dbc
from dash import dcc, html, dash_table

from src.styling.theme import FONT_FAMILY
from src.styling.ui_components import ds_header, build_unified_modal


# ── Phase quadrant accent colours (single source of truth) ──────────────────
DEFENCE_COLOR     = "#8B2635"   # dark red
POSSESSION_COLOR  = "#1D6F6A"   # teal
PROGRESSION_COLOR = "#C8882A"   # amber
ATTACK_COLOR      = "#2563A8"   # blue

QUADRANT_CONFIG = [
    {"label": "DEFENCE",     "ids": ["D1", "D2", "D3"], "color": DEFENCE_COLOR},
    {"label": "POSSESSION",  "ids": ["P1", "P2", "P3"], "color": POSSESSION_COLOR},
    {"label": "PROGRESSION", "ids": ["G1", "G2", "G3"], "color": PROGRESSION_COLOR},
    {"label": "ATTACK",      "ids": ["A1", "A2", "A3"], "color": ATTACK_COLOR},
]

# Display names in wheel order (DEFENCE → POSSESSION → PROGRESSION → ATTACK).
KPI_ORDER = ["D1", "D2", "D3", "P1", "P2", "P3", "G1", "G2", "G3", "A1", "A2", "A3"]
KPI_THETA_LABELS = [
    "Chance Prevention", "Intensity", "High Line",
    "Deep Build-up", "Press Resistance", "Possession",
    "Central Progr.", "Circulate", "Field Tilt",
    "Chance Creation", "Patient Attack", "Shot Quality",
]
# Full names for tables / tooltips.
KPI_FULL_NAMES = {
    "D1": "Chance Prevention", "D2": "Defensive Intensity", "D3": "High Line",
    "P1": "Deep Build-up", "P2": "Press Resistance", "P3": "Possession",
    "G1": "Central Progression", "G2": "Circulate", "G3": "Field Tilt",
    "A1": "Chance Creation", "A2": "Patient Attack", "A3": "Shot Quality",
}

# Modal titles (same as full names, kept explicit per spec).
KPI_MODAL_TITLES = dict(KPI_FULL_NAMES)

# Plain-English explanation shown in each KPI's info modal.
KPI_EXPLANATIONS = {
    "D1": "Measures how few quality chances the team concedes, expressed as "
          "non-penalty expected goals against per 90 minutes. A lower raw value "
          "means better defensive performance — the percentile is inverted so "
          "higher = better.",
    "D2": "Measures how quickly the team engages opponents in their own half: "
          "opposition touches per team defensive action (tackle, interception, "
          "foul, or challenge) in the attacking two-thirds. A lower raw value "
          "means more intense, high-frequency defending — the percentile is "
          "inverted so higher = better.",
    "D3": "Captures how aggressively the team defends a high line: the combined "
          "count of offsides provoked, through-balls conceded, and GK sweeper "
          "actions per 100 opposition passes into the final third. A higher "
          "value indicates a more aggressive, high-risk/high-reward defensive "
          "structure.",
    "P1": "Measures how often the goalkeeper plays short rather than launching "
          "long: the share of GK passes that are short (not long balls ≥ 40 "
          "yards). A higher percentage reflects a possession-oriented, "
          "build-from-the-back style.",
    "P2": "Measures the team's ability to maintain possession under pressure in "
          "their own half: touches completed in the first two-thirds of the "
          "pitch per opposition defensive action in the same zone. A higher "
          "value indicates greater composure and technical quality under the "
          "press.",
    "P3": "The team's share of total open-play passes attempted across the "
          "season — a direct measure of territorial and ball dominance. Values "
          "above 50% indicate the team controls the tempo of matches.",
    "G1": "Measures how centrally the team progresses the ball: the inverse of "
          "crosses per 100 passes. A higher percentile means fewer wide "
          "deliveries and more central, combinational build-up play.",
    "G2": "Measures how indirectly (patiently) the team moves the ball: the "
          "inverse of the share of progressive distance in total "
          "passing/carrying distance. A higher percentile reflects more "
          "circulation and recycling rather than direct vertical play.",
    "G3": "Measures territorial dominance in the final third: the team's share "
          "of both teams' combined final-third passes. Values above 50% mean "
          "the team consistently pins opponents back and plays the majority of "
          "the game in the attacking third.",
    "A1": "The team's attacking output in terms of quality: non-penalty "
          "expected goals generated per 90 minutes. This is the primary measure "
          "of how dangerous the team is in attack, accounting for shot location "
          "and type rather than just volume.",
    "A2": "Measures attacking patience: shots taken per 100 final-third "
          "touches. A lower raw value means the team spends more time in the "
          "final third before attempting a shot — the percentile is inverted so "
          "higher = better (more patient).",
    "A3": "Measures the average quality of shots the team creates: non-penalty "
          "expected goals per shot. A higher value means the team consistently "
          "generates high-quality chances rather than taking speculative "
          "efforts from distance.",
}


def _fmt_raw(kid: str, v: float) -> str:
    """
    Human-readable rendering of a raw KPI value for the reference grid.

    Several raw values are stored on a percentile-friendly (inverted) scale that
    is not directly interpretable; here we map each back to the metric an analyst
    expects to read, with units.
    """
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "–"
    if kid == "D1":
        return f"{v:.2f} xGA/90"
    if kid == "D2":
        return f"{v:.1f} PPDA"
    if kid == "D3":
        return f"{v:.1f} /100"            # high-line events per 100 opp FT passes
    if kid == "P1":
        return f"{v * 100:.0f}% short"    # 1 − GK launch rate → % short GK passes
    if kid == "P2":
        return f"{v:.1f} touch/act"
    if kid == "P3":
        return f"{v:.1f}% poss"
    if kid == "G1":
        # raw = 1 − crosses per 100 passes → crosses per 100 passes
        return f"{(1.0 - v):.1f} cr/100"
    if kid == "G2":
        # raw = 1 − directness → directness %
        return f"{(1.0 - v) * 100:.0f}% direct"
    if kid == "G3":
        return f"{v:.0f}% tilt"
    if kid == "A1":
        return f"{v:.2f} xG/90"
    if kid == "A2":
        return f"{v:.1f} sh/100"          # shots per 100 FT touches
    if kid == "A3":
        return f"{v:.2f} xG/sh"
    return f"{v:.2f}"


# ═══════════════════════════════════════════════════════════════════════════════
# THEME
# ═══════════════════════════════════════════════════════════════════════════════

def _theme_dict(theme: str) -> dict:
    """Background / font / gridline values for the wheel, per theme."""
    if theme == "light":
        return {
            "font": "#1a1a2e",
            "muted": "#718096",
            "grid": "rgba(0,0,0,0.10)",
            "ring": "rgba(0,0,0,0.06)",
        }
    return {
        "font": "#f0f0f0",
        "muted": "#8899aa",
        "grid": "rgba(255,255,255,0.12)",
        "ring": "rgba(255,255,255,0.05)",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# WHEEL FIGURE
# ═══════════════════════════════════════════════════════════════════════════════

def _build_wheel_figure(team: str, df_league: pd.DataFrame,
                        theme: str = "dark") -> go.Figure:
    """
    Build the 12-segment Barpolar wheel for *team* using percentile values.

    One trace per phase quadrant (so each phase carries its own colour); bars
    sit at 12 evenly spaced theta positions. DEFENCE top-right, POSSESSION
    bottom-right, PROGRESSION bottom-left, ATTACK top-left (The Athletic layout).
    """
    t = _theme_dict(theme)
    row = df_league[df_league["team"] == team]
    pct = {kid: (float(row.iloc[0][f"{kid}_pct"]) if not row.empty
                 and not pd.isna(row.iloc[0][f"{kid}_pct"]) else 0.0)
           for kid in KPI_ORDER}

    # Theta: 12 sectors of 30°. Plotly polar default 0° = East (right), angles
    # increase counter-clockwise. We lay the 12 KPIs out CLOCKWISE starting just
    # right of north so DEFENCE lands top-right, POSSESSION bottom-right,
    # PROGRESSION bottom-left, ATTACK top-left (The Athletic layout). Going
    # clockwise = decreasing angle. We keep the angular axis in its default
    # direction and pin tick positions to these same centres so labels align.
    n = len(KPI_ORDER)
    step = 360.0 / n
    theta_centres = [(90.0 - step / 2.0 - i * step) % 360.0 for i in range(n)]

    fig = go.Figure()
    label_by_id = dict(zip(KPI_ORDER, KPI_THETA_LABELS))

    # Collected for the in-bar text overlay (Barpolar has no text label support).
    lbl_r, lbl_th, lbl_txt = [], [], []

    for q in QUADRANT_CONFIG:
        r_vals, th_vals, hover = [], [], []
        for kid in q["ids"]:
            i = KPI_ORDER.index(kid)
            val = pct[kid]
            r_vals.append(val)
            th_vals.append(theta_centres[i])
            hover.append(
                f"<b>{KPI_FULL_NAMES[kid]}</b><br>"
                f"Percentile: {val:.0f}<extra></extra>"
            )
            if val >= 15:
                lbl_r.append(max(val - 8, 6))     # nudge inside the bar tip
                lbl_th.append(theta_centres[i])
                lbl_txt.append(f"{val:.0f}")
        fig.add_trace(go.Barpolar(
            r=r_vals,
            theta=th_vals,
            width=[step * 0.86] * len(r_vals),   # thin angular gap between sectors
            marker_color=q["color"],
            marker_line_color=t["grid"],
            marker_line_width=1,
            opacity=0.92,
            hovertemplate=hover,
            name=q["label"],
            showlegend=False,
        ))

    # In-bar percentile labels.
    if lbl_txt:
        fig.add_trace(go.Scatterpolar(
            r=lbl_r,
            theta=lbl_th,
            mode="text",
            text=lbl_txt,
            textfont=dict(color="#ffffff", size=11, family=FONT_FAMILY),
            hoverinfo="skip",
            showlegend=False,
        ))

    # Concentric reference rings at 25/50/75 are drawn by the radial grid below.
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT_FAMILY, color=t["font"], size=12),
        margin=dict(t=46, l=46, r=46, b=46),
        height=460,
        polar=dict(
            bgcolor="rgba(0,0,0,0)",
            hole=0.18,
            radialaxis=dict(
                range=[0, 99],
                tickvals=[25, 50, 75],
                ticktext=["25", "50", "75"],
                tickfont=dict(color=t["muted"], size=9),
                gridcolor=t["grid"],
                linecolor="rgba(0,0,0,0)",
                angle=90,
                tickangle=90,
            ),
            angularaxis=dict(
                tickmode="array",
                tickvals=theta_centres,
                ticktext=[label_by_id[k] for k in KPI_ORDER],
                tickfont=dict(color=t["font"], size=10, family=FONT_FAMILY),
                gridcolor=t["ring"],
                linecolor=t["grid"],
                rotation=0,
                direction="counterclockwise",
            ),
        ),
    )

    # Phase labels as annotations beyond the outermost ring, in each phase
    # colour. Pushed out to paper-radius 0.72 (was 0.56) so they clear the KPI
    # spoke labels that Plotly auto-places just outside the r=99 ring.
    # Centre angle of each 3-sector group (matches theta_centres above):
    # DEFENCE 45°, POSSESSION 315°, PROGRESSION 225°, ATTACK 135°.
    phase_angles = {"DEFENCE": 45.0, "POSSESSION": 315.0,
                    "PROGRESSION": 225.0, "ATTACK": 135.0}
    for q in QUADRANT_CONFIG:
        ang = np.radians(phase_angles[q["label"]])
        fig.add_annotation(
            x=0.5 + 0.72 * np.cos(ang),
            y=0.5 + 0.72 * np.sin(ang),
            xref="paper", yref="paper",
            text=f"<b>{q['label']}</b>",
            showarrow=False,
            bgcolor="rgba(0,0,0,0)",
            font=dict(color=q["color"], size=11, family=FONT_FAMILY),
        )

    # Centre: team logo (replaces the former team-name + season text). Resolved
    # via the shared logo_url() helper; silently omitted if the file is missing.
    _add_centre_logo(fig, team)
    return fig


def _add_centre_logo(fig: go.Figure, team: str) -> None:
    """Place the team's crest in the wheel's centre hole, if the asset exists."""
    try:
        from pathlib import Path
        from src.team_mapping import logo_url, logo_filename
        asset = Path(__file__).resolve().parents[2] / "assets" / "logos" / logo_filename(team)
        if not asset.exists():
            return
        fig.add_layout_image(dict(
            source=logo_url(team),
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            sizex=0.16, sizey=0.16,
            xanchor="center", yanchor="middle",
            layer="above",
            sizing="contain",
            opacity=1.0,
        ))
    except Exception:
        # Never let a missing/odd logo break the wheel.
        return


# ═══════════════════════════════════════════════════════════════════════════════
# RAW-VALUE REFERENCE GRID
# ═══════════════════════════════════════════════════════════════════════════════

def _color_for(kid: str) -> str:
    for q in QUADRANT_CONFIG:
        if kid in q["ids"]:
            return q["color"]
    return "#888"


def _build_raw_grid(team: str, df_league: pd.DataFrame) -> html.Div:
    """Compact 2×6 grid of raw KPI values, styled as small clickable chips.

    Each chip triggers a per-KPI explanation modal (rendered as a sibling here
    so the static modal IDs exist in the DOM whenever a chip is clicked).
    """
    row = df_league[df_league["team"] == team]
    if row.empty:
        return html.Div()
    r = row.iloc[0]

    children = []
    for kid in KPI_ORDER:
        raw = r.get(f"{kid}_raw")
        children.append(
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(KPI_FULL_NAMES[kid], className="ps-chip-label"),
                            html.I(className="bi bi-info-circle ps-chip-info"),
                        ],
                        className="ps-chip-top",
                    ),
                    html.Span(_fmt_raw(kid, raw), className="ps-chip-value"),
                ],
                id=f"team-ps-kpi-modal-open-{kid}",
                n_clicks=0,
                className="ps-chip ps-chip-clickable",
                style={"borderLeft": f"3px solid {_color_for(kid)}"},
            )
        )
        children.append(_build_kpi_modal(kid))
    return html.Div(children, className="ps-raw-grid")


def _build_kpi_modal(kid: str) -> dbc.Modal:
    """Small explanation modal for one KPI, header tinted with its phase colour."""
    color = _color_for(kid)
    return dbc.Modal(
        [
            dbc.ModalHeader(
                dbc.ModalTitle(KPI_MODAL_TITLES[kid]),
                close_button=True,
                style={"borderLeft": f"5px solid {color}",
                       "color": color, "fontWeight": "700"},
            ),
            dbc.ModalBody(KPI_EXPLANATIONS[kid], className="ps-kpi-modal-body"),
            dbc.ModalFooter(
                dbc.Button(
                    "Close",
                    id=f"team-ps-kpi-modal-close-{kid}",
                    className="ms-auto",
                    n_clicks=0,
                    size="sm",
                )
            ),
        ],
        id=f"team-ps-kpi-modal-{kid}",
        is_open=False,
        centered=True,
        size="md",
        class_name="unified-modal",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# LEAGUE COMPARISON TABLE (modal)
# ═══════════════════════════════════════════════════════════════════════════════

def _build_league_comparison_table(df_league: pd.DataFrame,
                                   team: str) -> dash_table.DataTable:
    """All-20-team percentile table, sorted by mean percentile desc, team row hi."""
    pct_cols = [f"{kid}_pct" for kid in KPI_ORDER]
    tbl = df_league[["team"] + pct_cols].copy()
    tbl["Avg"] = tbl[pct_cols].mean(axis=1).round(0)
    tbl = tbl.sort_values("Avg", ascending=False).reset_index(drop=True)

    rename = {f"{kid}_pct": kid for kid in KPI_ORDER}
    rename["team"] = "Team"
    tbl = tbl.rename(columns=rename)
    for kid in KPI_ORDER:
        tbl[kid] = tbl[kid].round(0).astype("Int64")
    tbl["Avg"] = tbl["Avg"].astype("Int64")

    columns = [{"name": "Team", "id": "Team"}] + \
              [{"name": kid, "id": kid} for kid in KPI_ORDER] + \
              [{"name": "Avg", "id": "Avg"}]

    return dash_table.DataTable(
        data=tbl.to_dict("records"),
        columns=columns,
        sort_action="native",
        style_as_list_view=True,
        style_table={"overflowX": "auto"},
        style_header={
            "backgroundColor": "rgba(255,255,255,0.04)",
            "color": "var(--text-secondary)",
            "fontWeight": "600",
            "border": "none",
            "fontSize": "0.78rem",
            "textTransform": "uppercase",
        },
        style_cell={
            "backgroundColor": "transparent",
            "color": "var(--text-primary)",
            "border": "none",
            "borderBottom": "1px solid var(--border-light)",
            "padding": "6px 8px",
            "fontFamily": FONT_FAMILY,
            "fontSize": "0.82rem",
            "textAlign": "center",
        },
        style_cell_conditional=[
            {"if": {"column_id": "Team"}, "textAlign": "left", "fontWeight": "600"},
        ],
        style_data_conditional=[
            {
                "if": {"filter_query": f'{{Team}} = "{team}"'},
                "backgroundColor": "rgba(138,31,51,0.22)",
                "fontWeight": "700",
            },
        ],
        tooltip_header={kid: KPI_FULL_NAMES[kid] for kid in KPI_ORDER},
        tooltip_delay=200,
        tooltip_duration=None,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC: full section card
# ═══════════════════════════════════════════════════════════════════════════════

def playing_style_wheel_card(team: str, season: str,
                             df_league: pd.DataFrame | None,
                             theme: str = "dark") -> html.Div:
    """
    Full Playing Style section: header, wheel, raw-value grid, and the
    "View League Comparison" button. The modal shell itself lives in the page
    layout; this returns the in-section content rendered into team-ps-container.
    """
    if df_league is None or df_league.empty or \
            df_league[df_league["team"] == team].empty:
        return html.Div(
            [
                html.I(className="bi bi-info-circle me-2",
                       style={"fontSize": "1.2rem", "opacity": 0.5}),
                html.P("Playing-style data not yet available for this season.",
                       className="text-muted mb-0"),
            ],
            className="formations-empty",
            style={"display": "flex", "alignItems": "center",
                   "justifyContent": "center", "padding": "2rem"},
        )

    fig = _build_wheel_figure(team, df_league, theme)

    return html.Div(
        [
            dcc.Graph(
                figure=fig,
                config={"displayModeBar": False, "responsive": True},
                className="ps-wheel-graph",
            ),
            _build_raw_grid(team, df_league),
            html.Div(
                html.Button(
                    [html.I(className="bi bi-table me-1"), "View League Comparison"],
                    id="team-ps-modal-open",
                    n_clicks=0,
                    className="kpi-interval-btn",
                ),
                className="ps-compare-btn-row",
            ),
        ],
        className="ps-wheel-block",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# CALLBACK REGISTRATION — per-KPI explanation modals
# ═══════════════════════════════════════════════════════════════════════════════

def register_playing_style_kpi_modals(app) -> None:
    """
    Register the 12 open/close callbacks for the per-KPI explanation modals.

    Called once from register_team_detail_callbacks(). Each modal toggles open
    when its chip is clicked and closes via its Close button — registered via a
    factory so there is exactly one small callback per KPI.
    """
    from dash import Input, Output, State

    def _register(kid: str) -> None:
        @app.callback(
            Output(f"team-ps-kpi-modal-{kid}", "is_open"),
            Input(f"team-ps-kpi-modal-open-{kid}", "n_clicks"),
            Input(f"team-ps-kpi-modal-close-{kid}", "n_clicks"),
            State(f"team-ps-kpi-modal-{kid}", "is_open"),
            prevent_initial_call=True,
        )
        def _toggle(open_clicks, close_clicks, is_open):
            return not is_open

    for kid in KPI_ORDER:
        _register(kid)
