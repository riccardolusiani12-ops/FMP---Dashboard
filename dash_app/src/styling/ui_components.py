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

import dash_bootstrap_components as dbc
from dash import dcc, html


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


def build_unified_modal(modal_id: str, title_id: str, body_id: str,
                        title: str = "", size: str = "lg",
                        body=None) -> dbc.Modal:
    """
    Shared dark-themed modal shell — the single standard for card drill-downs.

    Visuals (bg rgba(15,25,35,0.97), 1px white-10 header rule, 1.25rem body
    padding) follow the FT-section modal reference standard (the since-removed
    `_ft_modal`); they live in assets/styles.css under "UNIFIED MODAL"
    (`.unified-modal*` classes), which also adds the fade + scale-in open
    transition.  Backdrop click and ESC
    close are dbc defaults and intentionally left enabled.

    ``title`` sets the initial header text; pass children to ``title_id`` from
    a callback to retitle dynamically.  Open/close callbacks must target
    ``modal_id`` ("is_open") with prevent_initial_call=True.  The body is
    either callback-filled (leave ``body`` unset, output to ``body_id``
    "children") or static/persistent (pass ``body`` — e.g. a pre-built layout
    or a dcc.Graph populated by its own callback).
    """
    return dbc.Modal(
        [
            dbc.ModalHeader(
                dbc.ModalTitle(title, id=title_id,
                               className="unified-modal-title"),
                close_button=True,
                class_name="unified-modal-header",
            ),
            dbc.ModalBody(
                html.Div(body, id=body_id),
                class_name="unified-modal-body",
            ),
        ],
        id=modal_id,
        is_open=False,
        scrollable=True,
        size=size,
        centered=True,
        backdrop=True,
        class_name="unified-modal",
    )


def unified_dropdown(dropdown_id: str, options, value=None, *,
                     placeholder: str = "Select…",
                     clearable: bool = False) -> dcc.Dropdown:
    """
    Standard compact filter dropdown (e.g. "Top Method" style selectors).

    Styling only — options/value/default logic stay with the caller (in
    particular the short-pass-exclusion default rule, where it applies).
    `.unified-dropdown` (assets/styles.css) fixes the width; dark-theme colours
    come from the global `.dash-dropdown*` rules.
    """
    return dcc.Dropdown(
        id=dropdown_id,
        options=options,
        value=value,
        placeholder=placeholder,
        clearable=clearable,
        className="unified-dropdown dash-dropdown-dark",
    )
