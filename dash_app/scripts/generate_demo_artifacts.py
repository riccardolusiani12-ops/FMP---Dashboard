#!/usr/bin/env python3
"""
Generate demo artifact files for the dashboard.
Run once to create sample Plotly JSON figures and CSV tables.
"""

import json
import sys
from pathlib import Path
import random

DEMO_DIR = Path(__file__).resolve().parent.parent.parent / "outputs" / "demo"
DEMO_DIR.mkdir(parents=True, exist_ok=True)


def _plotly_fig(data, layout):
    """Build a minimal Plotly figure dict."""
    return json.dumps({"data": data, "layout": layout}, indent=2)


def gen_points_progression():
    """Season points progression line chart."""
    matchdays = list(range(1, 39))
    points = []
    total = 0
    random.seed(42)
    for _ in matchdays:
        r = random.choice([0, 1, 3, 3, 1, 0, 3])
        total += r
        points.append(total)

    fig = _plotly_fig(
        [
            {
                "x": matchdays,
                "y": points,
                "type": "scatter",
                "mode": "lines+markers",
                "name": "Bologna",
                "line": {"color": "#c8102e", "width": 3},
                "marker": {"size": 6},
            }
        ],
        {
            "title": {"text": "Points Progression – Bologna 2024/2025"},
            "xaxis": {"title": "Matchday", "dtick": 5},
            "yaxis": {"title": "Points"},
            "template": "plotly_dark",
            "height": 400,
        },
    )
    (DEMO_DIR / "season_points_progression_bologna.json").write_text(fig)
    print("  ✅ season_points_progression_bologna.json")


def gen_high_regains():
    """High regains scatter on pitch."""
    random.seed(123)
    n = 45
    xs = [random.uniform(67, 100) for _ in range(n)]
    ys = [random.uniform(0, 100) for _ in range(n)]

    fig = _plotly_fig(
        [
            {
                "x": xs,
                "y": ys,
                "type": "scatter",
                "mode": "markers",
                "name": "High Regains",
                "marker": {
                    "color": "#c8102e",
                    "size": 10,
                    "opacity": 0.7,
                    "line": {"width": 1, "color": "white"},
                },
            },
            # Pitch outline (simplified)
            {
                "x": [0, 100, 100, 0, 0, 50, 50, 66.7, 66.7],
                "y": [0, 0, 100, 100, 0, 0, 100, 0, 100],
                "type": "scatter",
                "mode": "lines",
                "name": "",
                "showlegend": False,
                "line": {"color": "#555", "width": 1},
            },
        ],
        {
            "title": {"text": "High Regains – Bologna 2024/2025"},
            "xaxis": {"title": "x", "range": [0, 105], "showgrid": False},
            "yaxis": {"title": "y", "range": [0, 105], "showgrid": False, "scaleanchor": "x"},
            "template": "plotly_dark",
            "height": 500,
        },
    )
    (DEMO_DIR / "high_regains_bologna.json").write_text(fig)
    print("  ✅ high_regains_bologna.json")


def gen_ppda():
    """PPDA trend line chart."""
    random.seed(77)
    matchdays = list(range(1, 39))
    ppda_vals = [round(random.uniform(7, 14), 2) for _ in matchdays]

    fig = _plotly_fig(
        [
            {
                "x": matchdays,
                "y": ppda_vals,
                "type": "scatter",
                "mode": "lines+markers",
                "name": "PPDA",
                "line": {"color": "#3498db", "width": 2},
                "marker": {"size": 5},
            },
            {
                "x": matchdays,
                "y": [10] * len(matchdays),
                "type": "scatter",
                "mode": "lines",
                "name": "League Avg",
                "line": {"color": "#888", "dash": "dash", "width": 1},
            },
        ],
        {
            "title": {"text": "PPDA Trend – Bologna 2024/2025"},
            "xaxis": {"title": "Matchday", "dtick": 5},
            "yaxis": {"title": "PPDA (lower = more intense pressing)"},
            "template": "plotly_dark",
            "height": 400,
        },
    )
    (DEMO_DIR / "ppda_bologna.json").write_text(fig)
    print("  ✅ ppda_bologna.json")


def gen_xt():
    """xT heatmap for a match."""
    random.seed(55)
    zones_x = list(range(12))
    zones_y = list(range(8))
    z = [[round(random.uniform(0, 0.15), 3) for _ in zones_x] for _ in zones_y]
    # Make attacking zones higher
    for row in z:
        for i in range(8, 12):
            row[i] = round(row[i] + random.uniform(0.05, 0.2), 3)

    fig = _plotly_fig(
        [
            {
                "z": z,
                "type": "heatmap",
                "colorscale": "RdYlGn",
                "name": "xT",
                "colorbar": {"title": "xT"},
            }
        ],
        {
            "title": {"text": "xT Zones – Bologna vs Udinese (GW1)"},
            "xaxis": {"title": "Pitch Zone (x)"},
            "yaxis": {"title": "Pitch Zone (y)"},
            "template": "plotly_dark",
            "height": 400,
        },
    )
    (DEMO_DIR / "xt_bologna_gw1.json").write_text(fig)
    print("  ✅ xt_bologna_gw1.json")


def gen_attacking_phase():
    """Shot map scatter."""
    random.seed(99)
    n = 18
    xs = [random.uniform(75, 100) for _ in range(n)]
    ys = [random.uniform(15, 85) for _ in range(n)]
    xg = [round(random.uniform(0.02, 0.6), 2) for _ in range(n)]
    goals = [1 if x > 0.4 else 0 for x in xg]
    colors = ["#c8102e" if g else "#3498db" for g in goals]
    sizes = [max(8, int(x * 40)) for x in xg]

    fig = _plotly_fig(
        [
            {
                "x": xs,
                "y": ys,
                "type": "scatter",
                "mode": "markers",
                "name": "Shots",
                "text": [f"xG: {x}" for x in xg],
                "marker": {"color": colors, "size": sizes, "opacity": 0.8},
            }
        ],
        {
            "title": {"text": "Shot Map – Bologna vs Udinese (GW1)"},
            "xaxis": {"title": "x", "range": [60, 105]},
            "yaxis": {"title": "y", "range": [0, 100]},
            "template": "plotly_dark",
            "height": 450,
        },
    )
    (DEMO_DIR / "attacking_phase_bologna_gw1.json").write_text(fig)
    print("  ✅ attacking_phase_bologna_gw1.json")


def gen_passing_network():
    """Passing network with nodes and edges."""
    random.seed(11)
    players = [
        ("GK", 10, 50),
        ("LB", 25, 15),
        ("CB1", 25, 38),
        ("CB2", 25, 62),
        ("RB", 25, 85),
        ("CM1", 45, 30),
        ("CM2", 45, 55),
        ("CM3", 45, 75),
        ("LW", 70, 15),
        ("ST", 75, 50),
        ("RW", 70, 85),
    ]
    nodes = {
        "x": [p[1] for p in players],
        "y": [p[2] for p in players],
        "type": "scatter",
        "mode": "markers+text",
        "text": [p[0] for p in players],
        "textposition": "top center",
        "textfont": {"color": "white", "size": 10},
        "marker": {"color": "#c8102e", "size": 20, "line": {"width": 2, "color": "white"}},
        "name": "Players",
    }

    # Random edges
    edge_x, edge_y = [], []
    for i in range(len(players)):
        for j in range(i + 1, len(players)):
            if random.random() > 0.5:
                edge_x.extend([players[i][1], players[j][1], None])
                edge_y.extend([players[i][2], players[j][2], None])

    edges = {
        "x": edge_x,
        "y": edge_y,
        "type": "scatter",
        "mode": "lines",
        "line": {"color": "rgba(200,200,200,0.3)", "width": 2},
        "name": "Passes",
        "showlegend": False,
    }

    fig = _plotly_fig(
        [edges, nodes],
        {
            "title": {"text": "Passing Network – Bologna vs Udinese (GW1)"},
            "xaxis": {"range": [0, 105], "showgrid": False, "zeroline": False},
            "yaxis": {"range": [0, 100], "showgrid": False, "zeroline": False, "scaleanchor": "x"},
            "template": "plotly_dark",
            "height": 500,
            "showlegend": False,
        },
    )
    (DEMO_DIR / "passing_network_bologna_gw1.json").write_text(fig)
    print("  ✅ passing_network_bologna_gw1.json")


def gen_epv():
    """EPV heatmap."""
    random.seed(33)
    z = [[round(random.uniform(0, 0.08), 3) for _ in range(12)] for _ in range(8)]
    for r in range(8):
        for c in range(9, 12):
            z[r][c] = round(z[r][c] + random.uniform(0.1, 0.35), 3)

    fig = _plotly_fig(
        [
            {
                "z": z,
                "type": "heatmap",
                "colorscale": "Viridis",
                "colorbar": {"title": "EPV"},
            }
        ],
        {
            "title": {"text": "EPV Grid – Bologna 2024/2025"},
            "xaxis": {"title": "Zone X"},
            "yaxis": {"title": "Zone Y"},
            "template": "plotly_dark",
            "height": 400,
        },
    )
    (DEMO_DIR / "epv_bologna_season.json").write_text(fig)
    print("  ✅ epv_bologna_season.json")


def gen_league_table_csv():
    """High regains league table CSV."""
    teams = [
        "Atalanta", "Bologna", "Cagliari", "Como", "Empoli",
        "Fiorentina", "Genoa", "Inter", "Juventus", "Lazio",
        "Lecce", "Milan", "Monza", "Napoli", "Parma",
        "Roma", "Torino", "Udinese", "Venezia", "Verona",
    ]
    random.seed(42)
    rows = []
    for t in teams:
        rows.append(f"{t},{random.randint(20, 80)},{random.randint(10, 50)},{random.randint(5, 30)}")
    header = "Team,High Regains,Final Third Recoveries,Counter Attacks"
    csv_content = header + "\n" + "\n".join(sorted(rows, key=lambda x: -int(x.split(",")[1])))
    (DEMO_DIR / "high_regains_league_table.csv").write_text(csv_content)
    print("  ✅ high_regains_league_table.csv")


if __name__ == "__main__":
    print("Generating demo artifacts...")
    gen_points_progression()
    gen_high_regains()
    gen_ppda()
    gen_xt()
    gen_attacking_phase()
    gen_passing_network()
    gen_epv()
    gen_league_table_csv()
    print(f"\n✅ All demo artifacts created in {DEMO_DIR}")
