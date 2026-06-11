"""
dash_app/src/styling/plotly_template.py
========================================
Shared Plotly chart theming utilities for Phase 0 of the visual redesign.

Functions defined here are NOT yet called from existing chart modules.
They are scaffolding for later phases.  The list below documents which
existing functions are the primary adoption candidates:

  Candidates for apply_chart_theme():
    - dash_app/src/analytics/multi_season_standings.py :: build_standings_figure()
      (currently uses template="plotly_dark" + hardcoded paper_bgcolor="#1b2838")
    - dash_app/src/analytics/multi_season_standings_v1.py :: build_standings_figure()
    - dash_app/src/components/opponent_offensive_phase.py ::
      _build_benchmark_bar() and the xG/FT benchmark figures
    - dash_app/src/components/defensive_pressing_cards.py ::
      _pitch_layout() (non-pitch axis charts)
    - dash_app/src/components/chance_creation_cards.py ::
      _build_origin_bars() and related bar figures

  Candidates for kpi_strip_style():
    - dash_app/src/components/kpis.py :: kpi_card() — Bootstrap card, currently
      uses inline style {"backgroundColor": "rgba(44,62,80,0.5)"}
    - dash_app/src/components/defensive_pressing_cards.py :: _mini_kpi()
      (uses CSS class "kpi-card" — style props complement the CSS)
    - dash_app/src/components/defensive_castle_cards.py :: _mini_kpi()
    - dash_app/src/components/offensive_transition_cards.py :: _mini_kpi()
    - dash_app/src/components/chance_creation_cards.py :: _mini_kpi()
"""

from __future__ import annotations

import plotly.graph_objects as go

from .theme import FONT_FAMILY, get_colors


def apply_chart_theme(fig: go.Figure, theme: str = "dark") -> go.Figure:
    """
    Apply the dashboard's shared visual theme to *fig* non-destructively.

    Sets paper/plot backgrounds, font family and colour, gridline styling,
    margins, legend appearance, and hover label style — all sourced from
    theme.py.  Existing traces, annotations, and axis ranges are preserved.

    Parameters
    ----------
    fig : go.Figure
        A Plotly figure to theme in-place.
    theme : str
        "dark" (default) or "light".

    Returns
    -------
    go.Figure
        The same figure object, mutated in-place and returned for chaining.
    """
    c = get_colors(theme)

    fig.update_layout(
        # Backgrounds — always transparent so the CSS card bg shows through,
        # except for pitch maps which manage their own bg via plot_bgcolor.
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",

        # Font
        font=dict(
            family=FONT_FAMILY,
            color=c["text_primary"],
            size=12,
        ),

        # Title font
        title=dict(
            font=dict(
                family=FONT_FAMILY,
                color=c["text_primary"],
                size=14,
            ),
            x=0.5,
            xanchor="center",
        ),

        # Margins — generous whitespace per the design target
        margin=dict(l=48, r=24, t=48, b=40),

        # X axis defaults
        xaxis=dict(
            color=c["text_secondary"],
            tickfont=dict(family=FONT_FAMILY, color=c["text_secondary"], size=11),
            title=dict(font=dict(family=FONT_FAMILY, color=c["text_secondary"], size=11)),
            gridcolor=c["gridline"],
            linecolor=c["zeroline"],
            zerolinecolor=c["zeroline"],
            gridwidth=1,
        ),

        # Y axis defaults
        yaxis=dict(
            color=c["text_secondary"],
            tickfont=dict(family=FONT_FAMILY, color=c["text_secondary"], size=11),
            title=dict(font=dict(family=FONT_FAMILY, color=c["text_secondary"], size=11)),
            gridcolor=c["gridline"],
            linecolor=c["zeroline"],
            zerolinecolor=c["zeroline"],
            gridwidth=1,
        ),

        # Legend
        legend=dict(
            font=dict(family=FONT_FAMILY, color=c["text_secondary"], size=11),
            bgcolor=c["legend_bg"],
            bordercolor=c["legend_border"],
            borderwidth=1,
        ),

        # Hover label
        hoverlabel=dict(
            bgcolor=c["hover_bg"],
            bordercolor=c["hover_border"],
            font=dict(family=FONT_FAMILY, color=c["text_primary"], size=12),
        ),
    )

    return fig


def kpi_strip_style(theme: str = "dark") -> dict[str, object]:
    """
    Return a dict of CSS-style props for KPI / mini-KPI card elements.

    Suitable for use as the ``style=`` prop on a Dash html.Div or as the
    base for inline styles on Bootstrap dbc.Card components.

    The returned dict targets the rounded-card look specified in Phase 0:
    soft border, subtle shadow, rounded corners, generous padding,
    theme-aware background.

    Parameters
    ----------
    theme : str
        "dark" or "light".

    Returns
    -------
    dict
        CSS-style property dict ready for ``style={}`` in Dash.
    """
    c = get_colors(theme)

    if theme == "light":
        return {
            "background":    "linear-gradient(160deg, #ffffff 0%, #f7f8fa 100%)",
            "border":        f"1px solid {c['border']}",
            "borderRadius":  "8px",
            "padding":       "1rem 1.2rem",
            "boxShadow":     "0 2px 8px rgba(0,0,0,0.05)",
            "transition":    "all 0.25s cubic-bezier(0.4, 0, 0.2, 1)",
            "fontFamily":    FONT_FAMILY,
        }

    return {
        "background":    c["surface"],
        "border":        f"1px solid {c['border']}",
        "borderRadius":  "8px",
        "padding":       "1rem 1.2rem",
        "boxShadow":     "0 4px 20px rgba(0,0,0,0.3)",
        "transition":    "all 0.25s cubic-bezier(0.4, 0, 0.2, 1)",
        "fontFamily":    FONT_FAMILY,
    }
