"""
PV Model Heatmap — standalone visualization script
====================================================
Generates a heatmap of P(goal | x, y, type_id=1) across the full pitch
using the trained ML Possession Value model.

Usage (from repo root, with sports_analytics conda env active):

    cd /Users/ricki/Local\ Projects/FMP_SerieA_Dashboard
    conda run -n sports_analytics python dash_app/src/models/generate_pv_heatmap.py

Output:
    dash_app/src/models/pv_model_ml_heatmap.png

Pitch layout:
  x: 0 → 100  left = own goal, right = opponent goal
  y: 0 → 100  bottom = right touchline, top = left touchline
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np

# ─── Paths ────────────────────────────────────────────────────────────────────

_SCRIPT_DIR  = Path(__file__).parent
_SRC_DIR     = _SCRIPT_DIR.parent
_REPO_ROOT   = _SCRIPT_DIR.parents[3]

# Allow importing src modules
if str(_SRC_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR.parent))

OUTPUT_PNG     = _SCRIPT_DIR / "pv_model_ml_heatmap.png"
MODEL_PKL      = _SCRIPT_DIR / "pv_model_serie_a.pkl"
OLD_MODEL_PKL  = _SCRIPT_DIR / "pv_model_xt_backup.pkl"


# ─── Pitch drawing helpers ────────────────────────────────────────────────────

def _draw_pitch_lines(ax: plt.Axes, line_color: str = "white", lw: float = 1.0) -> None:
    """
    Overlay football pitch markings on the given axes.
    Opta coordinate space: x ∈ [0, 100], y ∈ [0, 100].
    Pitch is displayed with the attacking direction to the right (x→100).
    """
    kw = dict(color=line_color, linewidth=lw, zorder=3)

    # Pitch outline
    ax.plot([0, 100, 100, 0, 0], [0, 0, 100, 100, 0], **kw)

    # Halfway line
    ax.axvline(50, **kw)

    # Centre circle (radius ≈ 9.15 m ≈ 9.15 Opta units)
    centre_circle = mpatches.Circle(
        (50, 50), radius=9.15, fill=False,
        edgecolor=line_color, linewidth=lw, zorder=3,
    )
    ax.add_patch(centre_circle)
    ax.plot(50, 50, "o", color=line_color, markersize=3, zorder=3)

    # ── Attacking penalty box (right side) ────────────────────────────
    # x ∈ [83.33, 100], y ∈ [21.1, 78.9]
    box_x  = [83.33, 100, 100, 83.33, 83.33]
    box_y  = [21.1,  21.1, 78.9, 78.9, 21.1]
    ax.plot(box_x, box_y, **kw)

    # Attacking 6-yard box: x ∈ [94.2, 100], y ∈ [36.8, 63.2]
    six_x = [94.2, 100, 100, 94.2, 94.2]
    six_y = [36.8, 36.8, 63.2, 63.2, 36.8]
    ax.plot(six_x, six_y, **kw)

    # Penalty spot: x=89.5, y=50
    ax.plot(89.5, 50, "o", color=line_color, markersize=3, zorder=3)

    # ── Defensive penalty box (left side) ─────────────────────────────
    def_box_x = [0, 16.67, 16.67, 0, 0]
    def_box_y = [21.1, 21.1, 78.9, 78.9, 21.1]
    ax.plot(def_box_x, def_box_y, **kw)

    def_six_x = [0, 5.8, 5.8, 0, 0]
    def_six_y = [36.8, 36.8, 63.2, 63.2, 36.8]
    ax.plot(def_six_x, def_six_y, **kw)

    # Goal lines (y ∈ [45.2, 54.8] in Opta ≈ 7.32 m goal)
    for gx in (0, 100):
        ax.plot([gx, gx], [45.2, 54.8], color=line_color, linewidth=2.5, zorder=4)

    # Final third line
    ax.axvline(66.67, color=line_color, linewidth=lw, linestyle="--",
               alpha=0.6, zorder=3)


# ─── Grid scoring ─────────────────────────────────────────────────────────────

def _score_grid(pv, grid_size: int = 100, type_id: int = 1) -> np.ndarray:
    """
    Score a (grid_size × grid_size) pitch grid.

    Returns
    -------
    np.ndarray of shape (grid_size, grid_size) — rows = y (0→100 bottom-up),
    cols = x (0→100 left-right).  Row 0 = y=0 (right touchline).
    """
    xs = np.linspace(0, 100, grid_size)
    ys = np.linspace(0, 100, grid_size)
    grid = np.zeros((grid_size, grid_size), dtype=np.float32)

    for i, y in enumerate(ys):
        for j, x in enumerate(xs):
            grid[i, j] = pv.score(x, y, type_id=type_id)

    return grid


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    # Import PossessionValueModel from the utils module
    try:
        from src.utils.pv_model import PossessionValueModel
    except ImportError:
        # Try relative import (script called directly from models/)
        sys.path.insert(0, str(_SRC_DIR))
        from utils.pv_model import PossessionValueModel

    pv = PossessionValueModel(model_path=MODEL_PKL)
    if not pv.loaded:
        print(f"ERROR: Could not load model from {MODEL_PKL}")
        sys.exit(1)

    print(f"Model loaded: {pv!r}")
    print("Scoring 100×100 grid…  (type_id=1, generic pass)")

    grid_new = _score_grid(pv, grid_size=100, type_id=1)
    print(f"  Grid range: [{grid_new.min():.4f}, {grid_new.max():.4f}]")

    # ── Try loading old xT grid for comparison ────────────────────────
    old_pkl = OLD_MODEL_PKL if OLD_MODEL_PKL.exists() \
              else (_SCRIPT_DIR / "pv_model_xt_backup.pkl")
    has_old = old_pkl.exists()

    if has_old:
        try:
            old_pv = PossessionValueModel(model_path=old_pkl)
            grid_old = _score_grid(old_pv, grid_size=100, type_id=1)
            diff_grid = grid_new - grid_old
            print(f"  Diff grid range: [{diff_grid.min():.4f}, {diff_grid.max():.4f}]")
        except Exception as e:
            print(f"  Could not load old model: {e}")
            has_old = False

    # ── Plot ──────────────────────────────────────────────────────────
    n_subplots = 2 if has_old else 1
    fig, axes = plt.subplots(1, n_subplots, figsize=(8 * n_subplots, 6))
    if n_subplots == 1:
        axes = [axes]

    # ── Subplot 1: PV heatmap ─────────────────────────────────────────
    ax1 = axes[0]
    im1 = ax1.imshow(
        grid_new,
        origin="lower",      # y=0 at bottom
        extent=[0, 100, 0, 100],
        cmap="RdYlGn",
        vmin=0,
        vmax=min(grid_new.max(), 0.05),  # cap at 5% for better contrast
        aspect="equal",
        zorder=1,
    )
    _draw_pitch_lines(ax1, line_color="white", lw=1.0)
    plt.colorbar(im1, ax=ax1, fraction=0.03, pad=0.02,
                 label="P(goal | state)")
    ax1.set_title("Possession Value — P(goal | x, y)\nML model (type_id=1)",
                  fontsize=11, pad=8)
    ax1.set_xlabel("x  →  attacking direction")
    ax1.set_ylabel("y  →  left touchline")
    ax1.set_xlim(0, 100)
    ax1.set_ylim(0, 100)

    # ── Subplot 2: diff heatmap ───────────────────────────────────────
    if has_old:
        ax2 = axes[1]
        abs_max = max(abs(diff_grid.min()), abs(diff_grid.max()), 0.001)
        im2 = ax2.imshow(
            diff_grid,
            origin="lower",
            extent=[0, 100, 0, 100],
            cmap="RdYlGn",
            vmin=-abs_max,
            vmax=+abs_max,
            aspect="equal",
            zorder=1,
        )
        _draw_pitch_lines(ax2, line_color="gray", lw=1.0)
        plt.colorbar(im2, ax=ax2, fraction=0.03, pad=0.02,
                     label="ΔPV (ML − old xT)")
        ax2.set_title("Difference: ML model − legacy xT grid", fontsize=11, pad=8)
        ax2.set_xlabel("x  →  attacking direction")
        ax2.set_ylabel("y  →  left touchline")
        ax2.set_xlim(0, 100)
        ax2.set_ylim(0, 100)

    plt.suptitle("Possession Value Model — Serie A", fontsize=13, y=1.01)
    plt.tight_layout()
    fig.savefig(OUTPUT_PNG, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"\nHeatmap saved → {OUTPUT_PNG}")


if __name__ == "__main__":
    main()
