"""
dash_app/src/styling/ui_components.py
======================================
Shared Dash UI building blocks for the design-system redesign (Phase 2a+).

``ds_header()`` replicates the house-style card header introduced in Phase 1
(`pages/team_detail.py :: _ds_header()` — kept private there to avoid page →
styling circularity). New phases should import from THIS module.

The CSS classes (.ds-header, .ds-eyebrow, .ds-title, .ds-sub) are styled per
page-scope in assets/styles.css ("PHASE 1 — TEAM OVERVIEW REDESIGN" under
.team-overview; "PHASE 2a — MATCH ANALYSIS CARDS" under .ma-card).
"""

from __future__ import annotations

from dash import html


def ds_header(eyebrow: str, icon: str, title: str, subtitle: str) -> html.Div:
    """House-style card header: uppercase eyebrow + icon, bold title, muted subtitle."""
    return html.Div(
        [
            html.Div(
                [html.I(className=f"bi {icon}"), html.Span(eyebrow)],
                className="ds-eyebrow",
            ),
            html.H4(title, className="ds-title"),
            html.P(subtitle, className="ds-sub"),
        ],
        className="ds-header",
    )
