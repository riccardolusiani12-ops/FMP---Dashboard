"""
dash_app/src/styling/pitch_utils.py
=====================================
Canonical, theme-aware pitch-drawing primitive for the Calcio Italiano
dashboard.  This module consolidates the duplicated private pitch helpers
that currently live in each chart module.

Existing functions this is intended to eventually REPLACE (later phases):
  - dash_app/src/components/defensive_pressing_cards.py   :: _draw_full_pitch()  (line 497)
  - dash_app/src/components/defensive_pressing_cards.py   :: _pitch_layout()     (line 550)
  - dash_app/src/components/defensive_structure_cards.py  :: _draw_full_pitch()  (line 89)
  - dash_app/src/components/defensive_structure_cards.py  :: _pitch_layout()     (line 138)
  - dash_app/src/components/defensive_castle_cards.py     :: _draw_full_pitch()  (line 106)
  - dash_app/src/components/defensive_castle_cards.py     :: _pitch_layout()     (line 164)
  - dash_app/src/components/final_third_pitch.py          :: _draw_pitch_base()  (line 80)
  - dash_app/src/components/final_third_pitch.py          :: _base_layout()      (line 169)
  - dash_app/src/components/pitch_zones.py                :: pitch_zone_figure() — inline pitch markings (lines 136–179)
  - dash_app/src/components/set_piece_cards.py            :: _pitch_layout()     (line 532)  [half-pitch/attacking view]
  - dash_app/src/components/set_piece_cards.py            :: _apply_gm_layout()  (line 963)  [GK perspective]
  - dash_app/src/components/set_piece_cards.py            :: _fk_pitch_layout()  (line 1148) [FK half-pitch]
  - dash_app/src/models/generate_pv_heatmap.py            :: _draw_pitch_lines() (line 48)   [matplotlib, separate adapter needed]

Usage (Phase 0 — not yet imported from any chart module):
    from dash_app.src.styling.pitch_utils import draw_pitch
    fig = go.Figure()
    draw_pitch(fig, theme="dark", half=None)

PHASE 1 ADDITION (additive):
  - draw_pitch() gained ``style="formation"`` and ``width`` parameters.
    ``style="formation"`` renders the decorative square formation pitch
    (centre circle/spot, penalty areas, 6-yard boxes, penalty spots, goal
    mouths, seamless background fill) previously drawn inline by
    ``dash_app/src/analytics/formations.py :: build_formation_pitch_figure()``
    — that function is now the FIRST adopter of this module.
    The default ``style="analysis"`` path is unchanged.
"""

from __future__ import annotations

import plotly.graph_objects as go

from .theme import FONT_FAMILY, get_colors


# ── Pitch geometry constants (Opta coordinate system, 0–100 × 0–100) ──────────
# x = depth (0 = own goal line, 100 = opponent goal line; team attacks L→R)
# y = width (0 = right touchline, 100 = left touchline in broadcast view)

_X_EDGES = [0.0, 16.67, 33.33, 50.0, 66.67, 83.33, 100.0]
_Y_EDGES = [0.0, 33.33, 66.67, 100.0]

# GEOMETRY CORRECTION (Phase 2c): box edges aligned to the Opta-normalised
# values used by the analytics layer for classification (chance_creation.py:
# "Penalty Box: x ≥ 83.33 AND 21.1 ≤ y ≤ 78.9"; final_third.py _OPP_BOX_X =
# 100/6*5 ≈ 83.33 — also the 18-zone grid edge). Previous values (83.5 / 16.5 /
# 21 / 79) were a cosmetic approximation; the shift is sub-pixel at chart scale
# and was visually verified against all Phase 1/2a/2b callers (no shape/trace
# count changes, no data change).
_PENALTY_BOX_X0 = 83.33   # attacking penalty area left edge
_PENALTY_BOX_X1 = 100.0
_OWN_BOX_X0 = 0.0
_OWN_BOX_X1 = 16.67
_BOX_Y0 = 21.1
_BOX_Y1 = 78.9

# Detailed-marking constants (Opta-normalised, used when detailed_boxes=True)
_SIX_YARD_DEPTH = 5.83          # six-yard box depth (94.17 → 100 attacking)
_SIX_Y0, _SIX_Y1 = 36.8, 63.2   # six-yard box width
_PEN_SPOT_X_ATK = 88.5          # penalty spot (attacking); own side mirrored
_ARC_R = 9.15                   # D-arc / centre-circle radius
_GOAL_Y0, _GOAL_Y1 = 44.2, 55.8 # goalmouth posts
_GOAL_DEPTH = 2.0               # goal mouth drawn depth behind the goal line

_FINAL_THIRD_X = 66.67


def _line_color(theme: str) -> str:
    return "rgba(255,255,255,0.35)" if theme != "light" else "rgba(60,60,80,0.45)"


def _faint_line_color(theme: str, opacity_dark: float = 0.10) -> str:
    if theme == "light":
        return f"rgba(60,60,80,{opacity_dark * 0.7:.2f})"
    return f"rgba(255,255,255,{opacity_dark:.2f})"


def _label_color(theme: str) -> str:
    return "rgba(255,255,255,0.30)" if theme != "light" else "rgba(60,60,80,0.40)"


def _draw_formation_markings(fig: go.Figure, theme: str) -> str:
    """
    Add the decorative square-pitch markings used by formation cards
    (centre circle/spot, penalty areas, 6-yard boxes, penalty spots,
    goal mouths). Returns the pitch fill colour so the caller can make
    paper/plot/pitch seamless.

    Geometry and colour values replicate the original private drawing in
    formations.py exactly (dark theme), with light-theme equivalents.
    """
    c = get_colors(theme)
    pitch_fill = c["surface_solid"]
    if theme == "light":
        line = "rgba(60, 60, 80, 0.25)"
        goal_line = "rgba(60, 60, 80, 0.30)"
        goal_fill = "rgba(60, 60, 80, 0.05)"
    else:
        line = "rgba(255, 255, 255, 0.15)"
        goal_line = "rgba(255, 255, 255, 0.20)"
        goal_fill = "rgba(255, 255, 255, 0.04)"
    lw = 1.2
    below = "below"

    # Outer boundary (filled — seamless with paper/plot background)
    fig.add_shape(type="rect", x0=0, y0=0, x1=100, y1=100,
                  line=dict(color=line, width=lw),
                  fillcolor=pitch_fill, layer=below)
    # Centre line
    fig.add_shape(type="line", x0=50, y0=0, x1=50, y1=100,
                  line=dict(color=line, width=lw), layer=below)
    # Centre circle
    fig.add_shape(type="circle", x0=42, y0=42, x1=58, y1=58,
                  line=dict(color=line, width=lw), layer=below)
    # Centre spot
    fig.add_shape(type="circle", x0=49.3, y0=49.3, x1=50.7, y1=50.7,
                  fillcolor=line, line=dict(width=0), layer=below)
    # Penalty areas
    fig.add_shape(type="rect", x0=0, y0=22, x1=16.5, y1=78,
                  line=dict(color=line, width=lw), layer=below)
    fig.add_shape(type="rect", x0=83.5, y0=22, x1=100, y1=78,
                  line=dict(color=line, width=lw), layer=below)
    # 6-yard boxes
    fig.add_shape(type="rect", x0=0, y0=36, x1=5.5, y1=64,
                  line=dict(color=line, width=lw), layer=below)
    fig.add_shape(type="rect", x0=94.5, y0=36, x1=100, y1=64,
                  line=dict(color=line, width=lw), layer=below)
    # Penalty spots
    fig.add_shape(type="circle", x0=11.2, y0=49.3, x1=12.4, y1=50.7,
                  fillcolor=line, line=dict(width=0), layer=below)
    fig.add_shape(type="circle", x0=87.6, y0=49.3, x1=88.8, y1=50.7,
                  fillcolor=line, line=dict(width=0), layer=below)
    # Goal mouths
    fig.add_shape(type="rect", x0=-2.5, y0=44, x1=0, y1=56,
                  line=dict(color=goal_line, width=1.5),
                  fillcolor=goal_fill, layer=below)
    fig.add_shape(type="rect", x0=100, y0=44, x1=102.5, y1=56,
                  line=dict(color=goal_line, width=1.5),
                  fillcolor=goal_fill, layer=below)

    return pitch_fill


def draw_pitch(
    fig: go.Figure,
    theme: str = "dark",
    half: str | None = None,
    height: int = 430,
    title: str = "",
    show_legend: bool = True,
    draw_zones: bool = False,
    highlight_final_third: bool = False,
    highlight_defensive_third: bool = False,
    x_range: list[float] | None = None,
    margin: dict | None = None,
    style: str = "analysis",
    width: int | None = None,
    emphasize_own_box: bool = False,
    detailed_boxes: bool = False,
) -> go.Figure:
    """
    Add pitch markings to *fig* and apply a shared dark/light layout.

    This is the single canonical pitch primitive.  It consolidates every
    variant documented at the top of this module.

    Parameters
    ----------
    fig : go.Figure
        An existing figure to draw on (in-place + returned).
    theme : str
        "dark" (default) or "light".
    half : str | None
        None  → full pitch (default).
        "attacking" → attacking half only (x 50–100, centred, like set_piece_cards).
        "defensive" → defensive half only (x 0–50).
    height : int
        Figure height in pixels.
    title : str
        Chart title text.
    show_legend : bool
        Whether to show the Plotly legend.
    draw_zones : bool
        If True, overlay the 18-zone grid (corridor + depth dividers).
    highlight_final_third : bool
        If True, draw the final-third boundary line (x=66.67) with emphasis.
    highlight_defensive_third : bool
        If True, add a faint red fill over the defensive third (x 0–33.33),
        as used in defensive_castle_cards.
    x_range : list[float] | None
        Override the x-axis range.  Default: [-2, 102] (full) or
        [48, 102] (attacking half).
    margin : dict | None
        Override figure margins.  Default: {"l": 10, "r": 120, "t": 40, "b": 20}
        for full pitch with side legend; or {"l": 15, "r": 15, "t": 30, "b": 50}
        for half-pitch with bottom legend.

    style : str
        "analysis" (default) → the standard analysis pitch below.
        "formation" → decorative square formation pitch (centre circle,
        6-yard boxes, penalty spots, goal mouths, seamless fill); only
        ``theme``, ``height`` and ``width`` apply in this mode.
    width : int | None
        Fixed figure width in pixels (formation mode; defaults to ``height``
        so the figure is square).
    emphasize_own_box : bool
        Phase 2a addition — draw the own penalty box with a stronger line and
        dim the attacking box (defensive-third focused maps, e.g. Defensive
        Castle).
    detailed_boxes : bool
        Phase 2c addition — also draw six-yard boxes, penalty spots, D-arcs,
        centre circle and goal mouths (Opta-normalised landscape geometry)
        for whichever half/halves are visible. Intended for shot-map style
        figures.

    Returns
    -------
    go.Figure
        The same figure (mutated in-place), returned for chaining.
    """
    if style == "formation":
        pitch_fill = _draw_formation_markings(fig, theme)
        fig.update_layout(
            paper_bgcolor=pitch_fill,
            plot_bgcolor=pitch_fill,
            xaxis=dict(range=[-5, 105], showgrid=False, zeroline=False,
                       showticklabels=False, fixedrange=True, visible=False),
            yaxis=dict(range=[-5, 105], showgrid=False, zeroline=False,
                       showticklabels=False, fixedrange=True, visible=False),
            width=width or height,
            height=height,
            autosize=False,
            margin=dict(l=0, r=0, t=0, b=0),
            dragmode=False,
            font=dict(family=FONT_FAMILY, color=get_colors(theme)["text_primary"]),
        )
        return fig

    c = get_colors(theme)
    lc = _line_color(theme)

    # ── Determine half extents ─────────────────────────────────────────────────
    if half == "attacking":
        x0_pitch, x1_pitch = 50.0, 100.0
        default_x_range = [48.0, 102.0]
    elif half == "defensive":
        x0_pitch, x1_pitch = 0.0, 50.0
        default_x_range = [-2.0, 52.0]
    else:
        x0_pitch, x1_pitch = 0.0, 100.0
        default_x_range = [-2.0, 102.0]

    x_range = x_range or default_x_range

    # ── Outer pitch rectangle ──────────────────────────────────────────────────
    fig.add_shape(
        type="rect", x0=x0_pitch, x1=x1_pitch, y0=0, y1=100,
        line=dict(color=lc, width=1.5),
        fillcolor="rgba(0,0,0,0)",
        layer="below",
    )

    # ── Optional zone grid ─────────────────────────────────────────────────────
    if draw_zones:
        for y_val in (33.33, 66.67):
            fig.add_shape(
                type="line", x0=x0_pitch, x1=x1_pitch, y0=y_val, y1=y_val,
                line=dict(color=_faint_line_color(theme, 0.12), width=1),
                layer="below",
            )
        for x_val in _X_EDGES[1:-1]:
            if x0_pitch <= x_val <= x1_pitch:
                fig.add_shape(
                    type="line", x0=x_val, x1=x_val, y0=0, y1=100,
                    line=dict(color=_faint_line_color(theme, 0.08), width=1),
                    layer="below",
                )
        for label, y_centre in (("Right", 16.67), ("Centre", 50.0), ("Left", 83.33)):
            fig.add_annotation(
                x=x0_pitch + 2, y=y_centre,
                text=label, showarrow=False, textangle=-90,
                font=dict(size=8, color=_label_color(theme)),
            )

    # ── Halfway line (full pitch only) ─────────────────────────────────────────
    if half is None:
        fig.add_shape(
            type="line", x0=50, x1=50, y0=0, y1=100,
            line=dict(color=_faint_line_color(theme, 0.22), width=1, dash="dash"),
            layer="below",
        )

    # ── Own penalty box ────────────────────────────────────────────────────────
    # Phase 2a addition: emphasize_own_box draws the own box with a stronger
    # line (and dims the attacking box) — used by defensive-third focused maps
    # like the Defensive Castle card.
    if half in (None, "defensive"):
        own_box_line = (
            dict(color=lc, width=1.5) if emphasize_own_box
            else dict(color=_faint_line_color(theme, 0.18), width=1)
        )
        fig.add_shape(
            type="rect", x0=_OWN_BOX_X0, x1=_OWN_BOX_X1, y0=_BOX_Y0, y1=_BOX_Y1,
            line=own_box_line,
            fillcolor="rgba(0,0,0,0)",
        )

    # ── Attacking penalty box ──────────────────────────────────────────────────
    if half in (None, "attacking"):
        atk_box_opacity = 0.10 if emphasize_own_box else 0.18
        fig.add_shape(
            type="rect", x0=_PENALTY_BOX_X0, x1=_PENALTY_BOX_X1,
            y0=_BOX_Y0, y1=_BOX_Y1,
            line=dict(color=_faint_line_color(theme, atk_box_opacity), width=1),
            fillcolor="rgba(0,0,0,0)",
        )

    # ── Optional: detailed markings (Phase 2c — shot-map style figures) ────────
    if detailed_boxes:
        detail_line = dict(color=_faint_line_color(theme, 0.18), width=1)
        if half in (None, "attacking"):
            # Six-yard box, penalty spot, D-arc, goal mouth (attacking end)
            fig.add_shape(type="rect", x0=100 - _SIX_YARD_DEPTH, x1=100,
                          y0=_SIX_Y0, y1=_SIX_Y1, line=detail_line,
                          fillcolor="rgba(0,0,0,0)")
            fig.add_shape(type="circle",
                          x0=_PEN_SPOT_X_ATK - 0.6, x1=_PEN_SPOT_X_ATK + 0.6,
                          y0=49.4, y1=50.6,
                          fillcolor=detail_line["color"], line=dict(width=0))
            fig.add_shape(type="circle",
                          x0=_PEN_SPOT_X_ATK - _ARC_R, x1=_PEN_SPOT_X_ATK + _ARC_R,
                          y0=50 - _ARC_R, y1=50 + _ARC_R,
                          line=detail_line, layer="below")
            fig.add_shape(type="rect", x0=100, x1=100 + _GOAL_DEPTH,
                          y0=_GOAL_Y0, y1=_GOAL_Y1, line=detail_line,
                          fillcolor="rgba(0,0,0,0)")
        if half in (None, "defensive"):
            # Mirrored markings (own end)
            fig.add_shape(type="rect", x0=0, x1=_SIX_YARD_DEPTH,
                          y0=_SIX_Y0, y1=_SIX_Y1, line=detail_line,
                          fillcolor="rgba(0,0,0,0)")
            own_spot = 100 - _PEN_SPOT_X_ATK
            fig.add_shape(type="circle",
                          x0=own_spot - 0.6, x1=own_spot + 0.6,
                          y0=49.4, y1=50.6,
                          fillcolor=detail_line["color"], line=dict(width=0))
            fig.add_shape(type="circle",
                          x0=own_spot - _ARC_R, x1=own_spot + _ARC_R,
                          y0=50 - _ARC_R, y1=50 + _ARC_R,
                          line=detail_line, layer="below")
            fig.add_shape(type="rect", x0=-_GOAL_DEPTH, x1=0,
                          y0=_GOAL_Y0, y1=_GOAL_Y1, line=detail_line,
                          fillcolor="rgba(0,0,0,0)")
        if half is None:
            # Centre circle (full pitch only; halves get the partial arc via
            # the centre-circle overlapping the visible range)
            fig.add_shape(type="circle",
                          x0=50 - _ARC_R, x1=50 + _ARC_R,
                          y0=50 - _ARC_R, y1=50 + _ARC_R,
                          line=detail_line, layer="below")

    # ── Optional: defensive-third highlight band ───────────────────────────────
    if highlight_defensive_third and half in (None, "defensive"):
        fig.add_shape(
            type="rect", x0=0, x1=33.33, y0=0, y1=100,
            line=dict(color="rgba(239,68,68,0.20)", width=1),
            fillcolor="rgba(239,68,68,0.04)",
            layer="below",
        )

    # ── Optional: final-third boundary line ───────────────────────────────────
    if highlight_final_third:
        fig.add_shape(
            type="line", x0=_FINAL_THIRD_X, x1=_FINAL_THIRD_X, y0=0, y1=100,
            line=dict(color=_faint_line_color(theme, 0.60), width=2, dash="dash"),
        )

    # ── Direction labels ───────────────────────────────────────────────────────
    if half in (None, "attacking"):
        fig.add_annotation(
            x=94, y=-6, text="ATK →", showarrow=False,
            font=dict(size=9, color=_label_color(theme)),
        )
    if half in (None, "defensive"):
        fig.add_annotation(
            x=6, y=-6, text="← OWN GOAL", showarrow=False,
            font=dict(size=9, color=_label_color(theme)),
        )

    # ── Layout ────────────────────────────────────────────────────────────────
    default_margin = (
        {"l": 15, "r": 15, "t": 30, "b": 50}
        if half is not None
        else {"l": 10, "r": 120, "t": 40, "b": 20}
    )
    margin = margin or default_margin

    legend_cfg: dict = (
        dict(orientation="h", yanchor="top", y=-0.03,
             xanchor="center", x=0.5,
             font=dict(family=FONT_FAMILY, size=10, color=c["text_secondary"]),
             bgcolor="rgba(0,0,0,0)", itemsizing="constant")
        if half is not None
        else dict(orientation="v", yanchor="middle", y=0.5,
                  xanchor="left", x=1.01,
                  font=dict(family=FONT_FAMILY, size=10, color=c["text_secondary"]),
                  bgcolor=c["legend_bg"],
                  bordercolor=c["legend_border"],
                  borderwidth=1)
    )

    pitch_bg = "rgba(15,25,35,0.7)" if theme != "light" else "rgba(0,0,0,0)"

    fig.update_layout(
        title=dict(
            text=title,
            font=dict(family=FONT_FAMILY, size=13, color=c["text_primary"]),
            x=0.5,
        ),
        xaxis=dict(
            range=x_range, showgrid=False, zeroline=False,
            showticklabels=False, fixedrange=True,
        ),
        yaxis=dict(
            range=[-12, 106], showgrid=False, zeroline=False,
            showticklabels=False, fixedrange=True,
            scaleanchor="x", scaleratio=0.68,
        ),
        plot_bgcolor=pitch_bg,
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(**margin),
        height=height,
        showlegend=show_legend,
        legend=legend_cfg,
        font=dict(family=FONT_FAMILY, color=c["text_primary"]),
    )

    return fig
