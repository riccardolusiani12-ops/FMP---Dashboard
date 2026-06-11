"""
Pitch Zone Visualisation Component
====================================
Renders an 18-zone pitch heatmap using Plotly, consistent with the
dashboard dark theme.  Used by goalkeeper build-up and future analyses.
"""

from __future__ import annotations

import plotly.graph_objects as go

from src.styling.theme import SEMANTIC_COLORS
from src.styling.plotly_template import apply_chart_theme

from src.config import PRIMARY_COLOR

# ═══════════════════════════════════════════════════════════════════════════════
# ZONE GRID CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

ROWS = 6
COLS = 3
X_EDGES = [0, 16.67, 33.33, 50.0, 66.67, 83.33, 100.0]
Y_EDGES = [0, 33.33, 66.67, 100.0]

# Zone numbering: Z1 = row0-col0, Z2 = row0-col1, Z3 = row0-col2, etc.
ZONE_LABELS = {r * COLS + c + 1: f"Z{r * COLS + c + 1}" for r in range(ROWS) for c in range(COLS)}

# Outcome colours (same semantic used everywhere — bound to the design system)
OUTCOME_COLORS = {
    "positive": SEMANTIC_COLORS["outcome_positive"],   # green — possession kept >= 15 s
    "negative": SEMANTIC_COLORS["outcome_negative"],   # red   — possession lost within 15 s
}


# ═══════════════════════════════════════════════════════════════════════════════
# PITCH + ZONE HEATMAP FIGURE
# ═══════════════════════════════════════════════════════════════════════════════

def pitch_zone_figure(
    zone_counts: dict[int, int],
    zone_outcomes: dict[int, dict] | None = None,
    title: str = "First Receiver Zones",
    height: int = 370,
) -> go.Figure:
    """
    Build a Plotly figure showing the 18-zone pitch with count heatmap
    and optional outcome-coloured annotations.

    Parameters
    ----------
    zone_counts : dict[int, int]
        {zone_number: pass_count}
    zone_outcomes : dict  (optional)
        {zone_number: {"positive": n, "negative": n}}
    title : str
    height : int

    Returns
    -------
    go.Figure
    """
    fig = go.Figure()

    max_count = max(zone_counts.values()) if zone_counts else 1

    # Draw zone rectangles
    for zone_num in range(1, 19):
        row = (zone_num - 1) // COLS
        col = (zone_num - 1) % COLS

        x0 = X_EDGES[row]
        x1 = X_EDGES[row + 1]
        y0 = Y_EDGES[col]
        y1 = Y_EDGES[col + 1]

        count = zone_counts.get(zone_num, 0)
        intensity = count / max_count if max_count else 0

        # Zone fill colour (dark navy → primary red based on frequency) —
        # the dashboard's unified sequential ramp (encoded as
        # SEMANTIC_COLORS["heatmap_colorscale"]; same interpolation as the
        # Phase 2a pressing/castle zone heatmaps)
        fill_r = int(27 + (138 - 27) * intensity)
        fill_g = int(40 + (31 - 40) * intensity)
        fill_b = int(56 + (51 - 56) * intensity)
        fill_a = 0.3 + 0.55 * intensity
        fill_color = f"rgba({fill_r},{fill_g},{fill_b},{fill_a})"

        # Rectangle shape
        fig.add_shape(
            type="rect",
            x0=x0, x1=x1, y0=y0, y1=y1,
            line=dict(color="rgba(255,255,255,0.15)", width=1),
            fillcolor=fill_color,
            layer="below",
        )

        # Zone label
        cx = (x0 + x1) / 2
        cy = (y0 + y1) / 2

        # Count text
        if count > 0:
            fig.add_annotation(
                x=cx, y=cy + 4,
                text=f"<b>{count}</b>",
                showarrow=False,
                font=dict(size=16, color="#f0f0f0"),
            )
            fig.add_annotation(
                x=cx, y=cy - 6,
                text=f"Z{zone_num}",
                showarrow=False,
                font=dict(size=9, color="rgba(255,255,255,0.5)"),
            )

            # Outcome dots (small coloured circles)
            if zone_outcomes and zone_num in zone_outcomes:
                oc = zone_outcomes[zone_num]
                dot_texts = []
                for key, colour in OUTCOME_COLORS.items():
                    n = oc.get(key, 0)
                    if n > 0:
                        dot_texts.append(f"<span style='color:{colour}'>●{n}</span>")
                if dot_texts:
                    fig.add_annotation(
                        x=cx, y=cy - 13,
                        text=" ".join(dot_texts),
                        showarrow=False,
                        font=dict(size=9),
                    )
        else:
            # Empty zone — just label
            fig.add_annotation(
                x=cx, y=cy,
                text=f"Z{zone_num}",
                showarrow=False,
                font=dict(size=9, color="rgba(255,255,255,0.25)"),
            )

    # ── Pitch markings ──
    # Halfway line
    fig.add_shape(type="line", x0=50, x1=50, y0=0, y1=100,
                  line=dict(color="rgba(255,255,255,0.18)", width=1, dash="dot"))

    # Penalty areas (approximate)
    for px in [0, 100]:
        if px == 0:
            fig.add_shape(type="rect", x0=0, x1=16.5, y0=21, y1=79,
                          line=dict(color="rgba(255,255,255,0.12)", width=1))
        else:
            fig.add_shape(type="rect", x0=83.5, x1=100, y0=21, y1=79,
                          line=dict(color="rgba(255,255,255,0.12)", width=1))

    # Attacking direction arrow — analysed team always L → R
    fig.add_annotation(
        x=92, y=-5,
        text="ATK →",
        showarrow=False,
        font=dict(size=9, color="rgba(255,255,255,0.35)"),
    )
    fig.add_annotation(
        x=8, y=-5,
        text="← OWN GOAL",
        showarrow=False,
        font=dict(size=9, color="rgba(255,255,255,0.35)"),
    )

    apply_chart_theme(fig, "dark")

    fig.update_layout(
        title=dict(text=title, font=dict(size=13, color="#f0f0f0"), x=0.5),
        xaxis=dict(
            range=[-2, 102], showgrid=False, zeroline=False,
            showticklabels=False, fixedrange=True,
        ),
        yaxis=dict(
            range=[-10, 105], showgrid=False, zeroline=False,
            showticklabels=False, fixedrange=True,
            scaleanchor="x", scaleratio=0.68,
        ),
        plot_bgcolor="rgba(15,25,35,0.7)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=40, b=20),
        height=height,
        showlegend=False,
    )

    return fig
