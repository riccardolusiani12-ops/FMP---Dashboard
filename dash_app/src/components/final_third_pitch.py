"""
Final Third Entry — Pitch Visualisations
==========================================
Custom Plotly figures for the final-third entry analysis.
Follows the same style/conventions as pitch_zones.py.
"""

from __future__ import annotations

import plotly.graph_objects as go


# ═══════════════════════════════════════════════════════════════════════════════
# PALETTE CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

CORRIDOR_COLORS = {
    "L": "#3b82f6",   # blue  — Left
    "C": "#8b5cf6",   # purple — Centre
    "R": "#06b6d4",   # cyan  — Right
}

CORRIDOR_LABELS = {
    "L": "Left",
    "C": "Centre",
    "R": "Right",
}

METHOD_COLORS = {
    "transition_recovery": "#22c55e",   # green
    "through_ball":        "#f43f5e",   # rose
    "switch_of_play":      "#14b8a6",   # teal
    "set_piece":           "#6366f1",   # indigo
    "long_ball":           "#f97316",   # orange
    "cross_delivery":      "#ec4899",   # pink — distinct from orange and amber
    "individual_carry":    "#eab308",   # amber
    "short_pass":          "#3b82f6",   # blue
}

METHOD_LABELS = {
    "transition_recovery": "Transition / Recovery",
    "through_ball":        "Through Ball",
    "switch_of_play":      "Switch of Play",
    "set_piece":           "Set-Piece",
    "long_ball":           "Long Ball",
    "cross_delivery":      "Cross Delivery",
    "individual_carry":    "Individual Carry",
    "short_pass":          "Short Pass",
}

OUTCOME_COLORS = {
    "positive": "#22c55e",   # green
    "negative": "#ef4444",   # red
}

# Zone grid (mirrors pitch_zones.py)
_X_EDGES = [0, 16.67, 33.33, 50.0, 66.67, 83.33, 100.0]
_Y_EDGES = [0, 33.33, 66.67, 100.0]
_COLS = 3

# Final Third x boundary
_FT_X = 66.67

# FT zone type colours
# Z14 = central danger (purple), Z13/15/16/18 = flanks (cyan), Z17 = box (no fill)
_ZONE_TYPE_COLOR = {
    13: "#06b6d4",   # cyan — flank
    14: "#8b5cf6",   # purple — Zone 14
    15: "#06b6d4",   # cyan — flank
    16: "#06b6d4",   # cyan — flank
    17: None,        # box — no color (transparent)
    18: "#06b6d4",   # cyan — flank
}


# ═══════════════════════════════════════════════════════════════════════════════
# SHARED PITCH-DRAWING HELPER
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_pitch_base(fig: go.Figure, draw_zones: bool = False) -> None:
    """
    Add standard pitch markings to *fig* in-place.

    Parameters
    ----------
    draw_zones : bool
        When True, overlay the full 18-zone grid (row and corridor lines)
        as faint background divisions.  Used on scatter plots so the
        L/C/R corridor split and zone rows are visible.
    """
    # Outer pitch rectangle
    fig.add_shape(
        type="rect", x0=0, x1=100, y0=0, y1=100,
        line=dict(color="rgba(255,255,255,0.35)", width=1.5),
        fillcolor="rgba(0,0,0,0)",
        layer="below",
    )

    # ── Optional 18-zone grid ──────────────────────────────────────────────────
    if draw_zones:
        # Horizontal corridor dividers (y-axis lines at 33.33 and 66.67)
        for y_val in (33.33, 66.67):
            fig.add_shape(
                type="line", x0=0, x1=100, y0=y_val, y1=y_val,
                line=dict(color="rgba(255,255,255,0.12)", width=1),
                layer="below",
            )
        # Vertical zone-row dividers (x-axis lines at each row boundary)
        for x_val in _X_EDGES[1:-1]:   # 16.67, 33.33, 50.0, 66.67, 83.33
            fig.add_shape(
                type="line", x0=x_val, x1=x_val, y0=0, y1=100,
                line=dict(color="rgba(255,255,255,0.08)", width=1),
                layer="below",
            )
        # Corridor labels (near own goal, facing attacking direction)
        # Opta y=0 is the right touchline (broadcast view bottom);
        # from the player's perspective (attacking L→R) low-y = Right, high-y = Left.
        for label, y_centre in (("Right", 16.67), ("Centre", 50.0), ("Left", 83.33)):
            fig.add_annotation(
                x=2, y=y_centre,
                text=label,
                showarrow=False,
                font=dict(size=8, color="rgba(255,255,255,0.22)"),
                textangle=-90,
            )

    # Halfway line
    fig.add_shape(
        type="line", x0=50, x1=50, y0=0, y1=100,
        line=dict(color="rgba(255,255,255,0.25)", width=1, dash="dash"),
        layer="below",
    )

    # Own penalty box (x 0–16.5, y 21–79)
    fig.add_shape(
        type="rect", x0=0, x1=16.5, y0=21, y1=79,
        line=dict(color="rgba(255,255,255,0.18)", width=1),
        fillcolor="rgba(0,0,0,0)",
    )

    # Attacking penalty box (x 83.5–100, y 21–79)
    fig.add_shape(
        type="rect", x0=83.5, x1=100, y0=21, y1=79,
        line=dict(color="rgba(255,255,255,0.18)", width=1),
        fillcolor="rgba(0,0,0,0)",
    )

    # Final third line (highlighted)
    fig.add_shape(
        type="line", x0=_FT_X, x1=_FT_X, y0=0, y1=100,
        line=dict(color="rgba(255,255,255,0.6)", width=2, dash="dash"),
    )

    # Direction labels
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


def _base_layout(fig: go.Figure, title: str, height: int = 400,
                 show_legend: bool = False) -> None:
    """Apply the shared dark-theme layout to *fig* in-place."""
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
        showlegend=show_legend,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# A. ENTRY SCATTER — METHOD VIEW (with hover detail)
# ═══════════════════════════════════════════════════════════════════════════════

def ft_entry_scatter_method(entries: list[dict]) -> go.Figure:
    """
    Full pitch scatter plot of FT entry points, coloured by entry method.
    This is the primary interactive figure — hovers show entry details.

    Returns
    -------
    go.Figure
    """
    fig = go.Figure()

    # Group by method (preserve priority display order)
    METHOD_ORDER = [
        "transition_recovery", "through_ball", "switch_of_play", "set_piece",
        "long_ball", "cross_delivery", "individual_carry", "short_pass",
    ]

    grouped: dict[str, list[tuple[float, float, str]]] = {k: [] for k in METHOD_ORDER}
    for e in entries:
        m = e.get("method", "short_pass")
        x = e.get("entry_x", 0)
        y = e.get("entry_y", 50)
        minute = int(e.get("minute", 0))
        second = int(e.get("second", 0))
        player = e.get("player", "?")
        corridor = e.get("corridor", "?")
        outcome = e.get("outcome", "negative")
        grouped.setdefault(m, []).append(
            (x, y, f"{minute}:{second:02d} {player} [{corridor}] [{outcome}]")
        )

    for method in METHOD_ORDER:
        pts = grouped.get(method, [])
        if not pts:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        hovers = [p[2] for p in pts]
        fig.add_trace(go.Scatter(
            x=xs,
            y=ys,
            mode="markers",
            name=METHOD_LABELS[method],
            marker=dict(
                color=METHOD_COLORS[method],
                size=8,
                opacity=0.8,
                line=dict(color="rgba(255,255,255,0.4)", width=0.5),
            ),
            hovertemplate=(
                f"<b>{METHOD_LABELS[method]}</b><br>"
                "x=%{x:.1f}, y=%{y:.1f}<br>"
                "%{text}<extra></extra>"
            ),
            text=hovers,
            showlegend=True,
        ))

    _draw_pitch_base(fig, draw_zones=True)
    _base_layout(fig, "Entry Points by Method", height=400, show_legend=True)
    fig.update_layout(
        legend=dict(
            orientation="v",
            yanchor="middle", y=0.5,
            xanchor="left", x=1.01,
            font=dict(size=9, color="#d0d0d0"),
            bgcolor="rgba(15,25,35,0.8)",
            bordercolor="rgba(255,255,255,0.1)",
            borderwidth=1,
        ),
        margin=dict(l=10, r=130, t=40, b=20),
    )
    return fig


# ═══════════════════════════════════════════════════════════════════════════════
# B. ZONE + OUTCOME HEATMAP (combined)
# ═══════════════════════════════════════════════════════════════════════════════

def ft_zone_outcome_heatmap(entries: list[dict]) -> go.Figure:
    """
    18-zone pitch heatmap showing FT entry counts per zone with outcome dots.

    FT zones (13-18) are coloured by type:
      Z14              → purple  (central danger / Zone 14)
      Z13, Z15, Z16, Z18 → cyan  (flanks)
      Z17              → red    (box — clearly delimited)

    Each FT zone with entries shows:
      • bold count (large)
      • zone label
      • outcome dots: ●n green (positive) and/or ●n red (negative)

    Zones 1-12 are drawn dimly for spatial reference.
    No hover interactions — use ft_entry_scatter_method() for entry detail.

    Returns
    -------
    go.Figure
    """
    # Compute entry counts and outcomes per zone from entry_x / entry_y
    zone_counts:  dict[int, int]  = {z: 0 for z in range(1, 19)}
    zone_outcomes: dict[int, dict] = {
        z: {"positive": 0, "negative": 0} for z in range(1, 19)
    }

    for e in entries:
        ex = e.get("entry_x")
        ey = e.get("entry_y", 50)
        if ex is None:
            continue
        row = min(int(float(ex) / 16.67), 5)
        col = min(int(float(ey) / 33.33), 2)
        zone = row * 3 + col + 1
        zone_counts[zone] += 1
        oc = e.get("outcome", "negative")
        if oc in ("positive", "negative"):
            zone_outcomes[zone][oc] += 1

    fig = go.Figure()
    max_count = max(zone_counts.values()) if zone_counts else 1

    for zone_num in range(1, 19):
        row = (zone_num - 1) // _COLS
        col = (zone_num - 1) % _COLS

        x0 = _X_EDGES[row]
        x1 = _X_EDGES[row + 1]
        y0 = _Y_EDGES[col]
        y1 = _Y_EDGES[col + 1]
        cx = (x0 + x1) / 2
        cy = (y0 + y1) / 2
        count = zone_counts.get(zone_num, 0)

        if zone_num <= 12:
            # Pre-FT zones — dim fill, label only
            fig.add_shape(
                type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
                line=dict(color="rgba(255,255,255,0.08)", width=1),
                fillcolor="rgba(15,25,35,0.4)",
                layer="below",
            )
            fig.add_annotation(
                x=cx, y=cy,
                text=f"Z{zone_num}",
                showarrow=False,
                font=dict(size=9, color="rgba(255,255,255,0.18)"),
            )
        else:
            # FT zones — coloured by type (Z17 has no fill)
            color = _ZONE_TYPE_COLOR.get(zone_num)
            intensity = count / max_count if max_count else 0
            
            if color is None:
                # Z17 (box) — transparent, just border outline
                border_color = "rgba(255,255,255,0.4)"
                fill_color = "rgba(0,0,0,0)"
            else:
                border_color = color
                r_hex = color.lstrip("#")
                r_rgb = tuple(int(r_hex[i:i + 2], 16) for i in (0, 2, 4))
                fill_a = 0.08 + 0.55 * intensity
                fill_color = f"rgba({r_rgb[0]},{r_rgb[1]},{r_rgb[2]},{fill_a:.2f})"
            
            border_width = 1.5
            fig.add_shape(
                type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
                line=dict(color=border_color, width=border_width),
                fillcolor=fill_color,
                layer="below",
            )

            if count > 0:
                # Bold count
                fig.add_annotation(
                    x=cx, y=cy + 4,
                    text=f"<b>{count}</b>",
                    showarrow=False,
                    font=dict(size=16, color="#f0f0f0"),
                )
                # Zone label
                label_color = border_color if color is None else color
                fig.add_annotation(
                    x=cx, y=cy - 6,
                    text=f"Z{zone_num}",
                    showarrow=False,
                    font=dict(size=9, color=label_color),
                )
                # Outcome dots (●n format)
                oc = zone_outcomes.get(zone_num, {})
                dot_parts: list[str] = []
                for key, dot_color in (("positive", "#22c55e"), ("negative", "#ef4444")):
                    n = oc.get(key, 0)
                    if n > 0:
                        dot_parts.append(
                            f"<span style='color:{dot_color}'>●{n}</span>"
                        )
                if dot_parts:
                    fig.add_annotation(
                        x=cx, y=cy - 14,
                        text=" ".join(dot_parts),
                        showarrow=False,
                        font=dict(size=9),
                    )
            else:
                # Empty FT zone — faint label
                if color is None:
                    label_color = "rgba(255,255,255,0.25)"
                else:
                    r_hex = color.lstrip("#")
                    r_rgb = tuple(int(r_hex[i:i + 2], 16) for i in (0, 2, 4))
                    label_color = f"rgba({r_rgb[0]},{r_rgb[1]},{r_rgb[2]},0.35)"
                fig.add_annotation(
                    x=cx, y=cy,
                    text=f"Z{zone_num}",
                    showarrow=False,
                    font=dict(size=9, color=label_color),
                )

    # Pitch markings
    fig.add_shape(
        type="rect", x0=0, x1=100, y0=0, y1=100,
        line=dict(color="rgba(255,255,255,0.3)", width=1.5),
        fillcolor="rgba(0,0,0,0)",
    )
    fig.add_shape(
        type="line", x0=50, x1=50, y0=0, y1=100,
        line=dict(color="rgba(255,255,255,0.15)", width=1, dash="dot"),
    )
    fig.add_annotation(
        x=92, y=-5, text="ATK →", showarrow=False,
        font=dict(size=9, color="rgba(255,255,255,0.35)"),
    )
    fig.add_annotation(
        x=8, y=-5, text="← OWN GOAL", showarrow=False,
        font=dict(size=9, color="rgba(255,255,255,0.35)"),
    )

    _base_layout(fig, "FT Entry Zones & Outcomes", height=400, show_legend=False)
    return fig
