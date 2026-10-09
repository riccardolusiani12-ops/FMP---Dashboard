"""
Metric Glossary Page — every dashboard metric with a short definition and an
expandable full methodology, read from the Metric Registry.

Routes: /glossary  (supports hash anchors, e.g. /glossary#match-analysis or
/glossary#match-analysis--defensive-phase-pressure)
"""

from dash import dcc, html

# Importing the callbacks module registers the glossary callbacks (dash.callback).
import src.callbacks.glossary_callbacks  # noqa: F401
from src.components.glossary_cards import build_glossary_body
from src.styling.ui_components import ds_header


def layout() -> html.Div:
    """Return the glossary page layout."""
    toolbar, body = build_glossary_body()
    return html.Div(
        [
            dcc.Store(id="gl-state", data={"section": "all"}),
            # Set by a hashchange listener for in-page anchor changes.
            dcc.Store(id="gl-hash", data=None),
            # Fires once after mount: applies the URL hash (anchor navigation).
            dcc.Interval(id="gl-boot", interval=250, n_intervals=0, max_intervals=1),
            html.Div(
                ds_header(
                    "REFERENCE", "bi-journal-bookmark-fill", "Metric Glossary",
                    "Every metric shown in the dashboard, grouped by section and "
                    "module. Each one has a short definition; open 'Full "
                    "methodology' for the complete calculation details.",
                ),
                className="ma-card gl-header",
            ),
            toolbar,
            body,
        ],
        className="page-container glossary-page",
    )
