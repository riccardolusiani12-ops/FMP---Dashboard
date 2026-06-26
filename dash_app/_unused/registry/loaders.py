"""
Artifact loaders – read artifact files into Python objects based on format.
Returns dash-ready components (dcc.Graph, html.Img, DataTable, etc.).
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from dash import dash_table, dcc, html
import dash_bootstrap_components as dbc

from src.registry.manifest_schema import ArtifactEntry
from src.registry.registry import ArtifactRegistry
from src.utils.caching import cached
from src.utils.logging import log


# ── Low-level readers (cached) ────────────────────────────────────────────────


@cached
def load_plotly_json(path: str) -> Optional[go.Figure]:
    """Load a Plotly figure from a JSON file."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        fig = pio.from_json(p.read_text(encoding="utf-8"))
        # Apply dark template
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=20, r=20, t=40, b=20),
        )
        return fig
    except Exception as exc:
        log.error("Failed to load Plotly JSON %s: %s", path, exc)
        return None


@cached
def load_dataframe(path: str) -> Optional[pd.DataFrame]:
    """Load a CSV or Parquet into a DataFrame."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        if p.suffix == ".parquet":
            return pd.read_parquet(p)
        elif p.suffix == ".csv":
            return pd.read_csv(p)
        elif p.suffix == ".json":
            return pd.read_json(p)
        else:
            log.warning("Unsupported table format: %s", p.suffix)
            return None
    except Exception as exc:
        log.error("Failed to load dataframe %s: %s", path, exc)
        return None


@cached
def load_html_content(path: str) -> Optional[str]:
    """Load raw HTML content from file."""
    p = Path(path)
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8")


@cached
def load_image_base64(path: str) -> Optional[str]:
    """Load a PNG/JPG and return a base64-encoded data URI."""
    p = Path(path)
    if not p.exists():
        return None
    suffix = p.suffix.lower().lstrip(".")
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(
        suffix, "image/png"
    )
    data = base64.b64encode(p.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{data}"


@cached
def load_markdown(path: str) -> Optional[str]:
    """Load markdown text."""
    p = Path(path)
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8")


# ── High-level: ArtifactEntry → Dash component ───────────────────────────────

def _missing_alert(entry: ArtifactEntry, resolved_path: Path) -> dbc.Alert:
    """Friendly alert when an artifact file is missing."""
    return dbc.Alert(
        [
            html.I(className="bi bi-exclamation-triangle-fill me-2"),
            html.Strong("Artifact not found: "),
            html.Span(entry.title),
            html.Br(),
            html.Small(f"Expected at: {resolved_path}", className="text-muted"),
        ],
        color="warning",
        className="mt-2",
    )


def render_artifact(entry: ArtifactEntry, style: Optional[dict] = None) -> Any:
    """
    Load and render an artifact entry into a Dash component.
    Handles all supported formats gracefully.
    """
    registry = ArtifactRegistry.instance()
    resolved = registry.resolve_path(entry)

    if not resolved.exists():
        return _missing_alert(entry, resolved)

    path_str = str(resolved)

    if entry.format == "plotly_json":
        fig = load_plotly_json(path_str)
        if fig is None:
            return _missing_alert(entry, resolved)
        return dcc.Graph(
            figure=fig,
            config={"displayModeBar": True, "toImageButtonOptions": {"format": "png"}},
            style=style or {"height": "500px"},
        )

    elif entry.format in ("png", "jpg"):
        src = load_image_base64(path_str)
        if src is None:
            return _missing_alert(entry, resolved)
        return html.Img(
            src=src,
            style=style or {"maxWidth": "100%", "height": "auto"},
            className="rounded",
        )

    elif entry.format in ("csv", "parquet", "table_json"):
        df = load_dataframe(path_str)
        if df is None:
            return _missing_alert(entry, resolved)
        return dash_table.DataTable(
            data=df.to_dict("records"),
            columns=[{"name": c, "id": c} for c in df.columns],
            page_size=15,
            sort_action="native",
            filter_action="native",
            style_table={"overflowX": "auto"},
            style_header={
                "backgroundColor": "#2c3e50",
                "color": "white",
                "fontWeight": "bold",
            },
            style_cell={
                "backgroundColor": "#1e1e1e",
                "color": "#ddd",
                "border": "1px solid #444",
                "textAlign": "left",
                "padding": "8px",
                "fontSize": "13px",
            },
            style_filter={
                "backgroundColor": "#2c3e50",
                "color": "white",
            },
        )

    elif entry.format == "html":
        content = load_html_content(path_str)
        if content is None:
            return _missing_alert(entry, resolved)
        return html.Iframe(
            srcDoc=content,
            style=style or {"width": "100%", "height": "600px", "border": "none"},
        )

    elif entry.format == "markdown":
        md = load_markdown(path_str)
        if md is None:
            return _missing_alert(entry, resolved)
        return dcc.Markdown(md, className="p-3")

    else:
        return dbc.Alert(
            f"Unsupported artifact format: {entry.format}",
            color="info",
        )


def render_artifacts_for_analysis(
    analysis: str,
    season: Optional[str] = None,
    team: Optional[str] = None,
    match_id: Optional[str] = None,
) -> list:
    """
    Query the registry and render all matching artifacts as a list of Dash components.
    Groups them with titles.
    """
    registry = ArtifactRegistry.instance()
    entries = registry.query(season=season, team=team, analysis=analysis, match_id=match_id)

    if not entries:
        return [
            dbc.Alert(
                [
                    html.I(className="bi bi-info-circle-fill me-2"),
                    f"No artifacts found for analysis '{analysis}'.",
                    html.Br(),
                    html.Small(
                        "Generate outputs from notebooks and update the manifest.",
                        className="text-muted",
                    ),
                ],
                color="secondary",
                className="mt-3",
            )
        ]

    components = []
    for entry in entries:
        components.append(
            dbc.Card(
                [
                    dbc.CardHeader(
                        html.H6(entry.title, className="mb-0 text-light"),
                        className="py-2",
                    ),
                    dbc.CardBody(
                        dcc.Loading(render_artifact(entry), type="circle"),
                        className="p-2",
                    ),
                ],
                className="mb-3 border-secondary",
            )
        )
    return components
