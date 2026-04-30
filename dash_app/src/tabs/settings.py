"""
Settings tab – configuration paths, toggles, debug info, Data QA diagnostics.
"""

import json

import dash_bootstrap_components as dbc
from dash import html

from src.config import (
    DATA_DIR,
    DEBUG,
    LOGS_DIR,
    MANIFEST_PATH,
    OUTPUTS_DIR,
    RAW_DATA_DIR,
    REPO_ROOT,
    AVAILABLE_SEASONS,
)
from src.registry.registry import ArtifactRegistry


def layout() -> html.Div:
    """Return settings layout."""
    return html.Div(
        [
            html.H5(
                [
                    html.I(className="bi bi-gear-fill me-2"),
                    "Settings & Diagnostics",
                ],
                className="text-light mb-3",
            ),
            dbc.Row(
                [
                    # Paths info
                    dbc.Col(
                        dbc.Card(
                            [
                                dbc.CardHeader("📁 Paths", className="py-2"),
                                dbc.CardBody(
                                    _paths_table(),
                                    className="p-3",
                                ),
                            ],
                            className="border-secondary mb-3",
                        ),
                        md=6,
                    ),
                    # Data QA
                    dbc.Col(
                        dbc.Card(
                            [
                                dbc.CardHeader("🔍 Data QA", className="py-2"),
                                dbc.CardBody(
                                    html.Div(id="settings-data-qa"),
                                    className="p-3",
                                ),
                            ],
                            className="border-secondary mb-3",
                        ),
                        md=6,
                    ),
                ],
            ),
            # Debug toggle
            dbc.Card(
                [
                    dbc.CardHeader("⚙️ Debug Info", className="py-2"),
                    dbc.CardBody(
                        [
                            html.P(f"Debug mode: {'ON' if DEBUG else 'OFF'}", className="text-muted"),
                            html.P(
                                f"Available seasons: {', '.join(s.replace('_', '/') for s in AVAILABLE_SEASONS)}",
                                className="text-muted",
                            ),
                            dbc.Button(
                                [html.I(className="bi bi-arrow-clockwise me-1"), "Reload Manifest"],
                                id="btn-reload-manifest",
                                color="outline-light",
                                size="sm",
                                className="me-2",
                            ),
                            dbc.Button(
                                [html.I(className="bi bi-trash me-1"), "Clear Cache"],
                                id="btn-clear-cache",
                                color="outline-warning",
                                size="sm",
                            ),
                            html.Div(id="settings-action-feedback", className="mt-2"),
                        ],
                        className="p-3",
                    ),
                ],
                className="border-secondary mb-3",
            ),
        ],
        className="p-3",
    )


def _paths_table() -> html.Table:
    """Display key paths as a small table."""
    rows = [
        ("Repository Root", str(REPO_ROOT)),
        ("Raw Data", str(RAW_DATA_DIR)),
        ("Outputs", str(OUTPUTS_DIR)),
        ("Manifest", str(MANIFEST_PATH)),
        ("Logs", str(LOGS_DIR)),
    ]
    return html.Table(
        [
            html.Tbody(
                [
                    html.Tr(
                        [
                            html.Td(label, className="text-muted pe-3", style={"fontSize": "0.85rem"}),
                            html.Td(
                                html.Code(path, style={"fontSize": "0.75rem"}),
                            ),
                        ]
                    )
                    for label, path in rows
                ]
            )
        ],
        className="table table-sm table-borderless mb-0",
    )


def render_data_qa() -> html.Div:
    """Generate Data QA diagnostics panel."""
    registry = ArtifactRegistry.instance()
    diag = registry.diagnostics()

    items = [
        html.P(
            [
                html.Strong("Manifest: "),
                html.Span(
                    "✅ Found" if diag["manifest_exists"] else "❌ Not found",
                    className="text-success" if diag["manifest_exists"] else "text-danger",
                ),
            ],
            className="mb-1",
        ),
        html.P(
            f"Total artifacts: {diag['total_artifacts']}",
            className="text-muted mb-1",
            style={"fontSize": "0.85rem"},
        ),
        html.P(
            [
                html.Strong("Missing files: "),
                html.Span(
                    str(diag["missing_files"]),
                    className="text-warning" if diag["missing_files"] > 0 else "text-success",
                ),
            ],
            className="mb-1",
        ),
    ]

    # Format breakdown
    if diag["formats_breakdown"]:
        items.append(html.P("Format breakdown:", className="text-muted mb-1 mt-2", style={"fontSize": "0.85rem"}))
        for fmt, count in diag["formats_breakdown"].items():
            items.append(
                html.P(f"  • {fmt}: {count}", className="text-muted mb-0", style={"fontSize": "0.8rem"})
            )

    # Missing details
    if diag["missing_details"]:
        items.append(html.Hr(className="border-secondary my-2"))
        items.append(html.P("Missing files:", className="text-warning mb-1", style={"fontSize": "0.85rem"}))
        for m in diag["missing_details"][:10]:
            items.append(
                html.P(
                    html.Code(m["file"], style={"fontSize": "0.75rem"}),
                    className="mb-0",
                )
            )

    return html.Div(items)
