"""
Reusable interactive DataTable helper.
"""

from typing import Optional
import pandas as pd
from dash import dash_table, html
import dash_bootstrap_components as dbc


def create_datatable(
    df: Optional[pd.DataFrame],
    table_id: str = "data-table",
    title: str = "",
    page_size: int = 15,
) -> html.Div:
    """
    Create a styled interactive DataTable from a DataFrame.
    Returns a friendly message if df is None or empty.
    """
    if df is None or df.empty:
        return dbc.Alert(
            "No data available for the current selection.",
            color="secondary",
            className="mt-3",
        )

    children = []
    if title:
        children.append(html.H6(title, className="text-light mb-2"))

    children.append(
        dash_table.DataTable(
            id=table_id,
            data=df.to_dict("records"),
            columns=[{"name": str(c), "id": str(c)} for c in df.columns],
            page_size=page_size,
            sort_action="native",
            filter_action="native",
            export_format="csv",
            style_table={"overflowX": "auto"},
            style_header={
                "backgroundColor": "#2c3e50",
                "color": "white",
                "fontWeight": "bold",
                "fontSize": "13px",
            },
            style_cell={
                "backgroundColor": "#1e1e1e",
                "color": "#ddd",
                "border": "1px solid #444",
                "textAlign": "left",
                "padding": "8px",
                "fontSize": "13px",
                "maxWidth": "200px",
                "overflow": "hidden",
                "textOverflow": "ellipsis",
            },
            style_filter={
                "backgroundColor": "#2c3e50",
                "color": "white",
            },
            style_data_conditional=[
                {
                    "if": {"row_index": "odd"},
                    "backgroundColor": "#252525",
                }
            ],
        )
    )

    return html.Div(children, className="mt-2")
