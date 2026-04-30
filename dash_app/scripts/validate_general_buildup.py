#!/usr/bin/env python3
"""
Validation export for General Build-up (Open Play) analysis.

Produces one CSV for each team in a specified match containing every
Final-Third entry event that the model analyses, with all key fields
exposed for manual verification.

Usage (from dash_app/):
    python scripts/validate_general_buildup.py

Output:
    outputs/general_buildup_validation_inter_torino_gw1.csv
"""

from __future__ import annotations

import sys
from pathlib import Path

# ── Make sure `src` is importable ──────────────────────────────────────────
DASH_APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DASH_APP_DIR))

import pandas as pd

from src.analytics.goalkeeper_buildup import _load_match_events
from src.analytics.general_buildup import (
    build_possessions,
    filter_open_play,
    detect_entries,
    classify_entries,
    analyse_post_z3,
)

# ── Configuration ───────────────────────────────────────────────────────────
MATCH_CSV = (
    DASH_APP_DIR.parent
    / "data/raw/serie_a_2025_2026/events"
    / "1_Inter_Torino_cjir7ivrn1ol4vwld9wfrfcwk.csv"
)

TEAMS = ["inter", "torino"]        # partial names — matched via containment

OUTPUT_DIR = DASH_APP_DIR.parent / "outputs"
OUTPUT_FILE = OUTPUT_DIR / "general_buildup_validation_inter_torino_gw1.csv"


def _fmt_time(minute, second) -> str:
    try:
        return f"{int(minute)}:{int(second):02d}"
    except (TypeError, ValueError):
        return "?:??"


def build_validation_rows(
    match_csv: Path,
    team_lower: str,
    display_team: str,
) -> list[dict]:
    """Run the full pipeline for one team and return flat validation rows."""

    df = _load_match_events(match_csv)
    if df.empty:
        return []

    # Mirror the column aliases done in analyse_general_buildup()
    renames = {
        "Corner taken":      "corner_taken",
        "Free kick taken":   "free_kick_taken",
        "Throw In":          "throw_in",
        "Penalty":           "penalty",
        "Gk kick from hands": "gk_kick_from_hands",
        "Through ball":      "through_ball",
        "Long ball":         "long_ball",
    }
    for orig, new in renames.items():
        if orig in df.columns and new not in df.columns:
            df[new] = df[orig]

    # Pipeline steps
    df = build_possessions(df)
    open_df = filter_open_play(df, team_lower)
    entries = detect_entries(open_df)
    entries = classify_entries(entries)
    entries = analyse_post_z3(entries, df)

    rows = []
    for e in entries:
        rows.append({
            "Team":              display_team,
            "Period":            e.get("period"),
            "Time":              _fmt_time(e.get("minute"), e.get("second")),
            "Poss_ID":           e.get("poss_id"),
            "Player":            e.get("player"),
            "Entry_Type":        e.get("entry_type"),          # pass / carry
            "Origin_X":          round(float(e.get("origin_x") or 0), 1),
            "Origin_Y":          round(float(e.get("origin_y") or 0), 1),
            "Origin_Zone":       f"Z{e.get('origin_zone')}",
            "Entry_X":           round(float(e.get("entry_x") or 0), 1),
            "Entry_Y":           round(float(e.get("entry_y") or 0), 1),
            "Entry_Zone":        f"Z{e.get('entry_zone')}",
            "Progression_Type":  e.get("progression_type"),
            "Passes_Before":     e.get("passes_before_count"),
            "Elapsed_Sec":       round(float(e.get("elapsed_sec") or 0), 1),
            "Long_Ball_Flag":    e.get("long_ball_flag"),
            "Through_Ball_Flag": e.get("through_ball_flag"),
            "Entry_Length":      (
                round(float(e["entry_length"]), 1)
                if e.get("entry_length") is not None else ""
            ),
            "Z14_Touch":         e.get("z14_touch"),
            "Wide_Play":         e.get("wide_play"),
            "Box_Entry":         e.get("box_entry"),
        })

    return rows


def main() -> None:
    all_rows: list[dict] = []

    for team_lower in TEAMS:
        display = team_lower.capitalize()
        print(f"Processing {display}...")
        rows = build_validation_rows(MATCH_CSV, team_lower, display)
        print(f"  → {len(rows)} FT entries found")
        all_rows.extend(rows)

    if not all_rows:
        print("No entries found — check match file path.")
        return

    df_out = pd.DataFrame(all_rows)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df_out.to_csv(OUTPUT_FILE, index=False)
    print(f"\nSaved {len(df_out)} rows to:\n  {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
