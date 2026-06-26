"""
Corner Kick Delivery Type Audit — 2025/2026 Season
====================================================
Objective: Select a team from 2025/2026 data, extract all corner kicks
taken, and audit all Delivery Types present in the raw data.

Specifically checks whether the "Straight" qualifier (Q225) is populated
for corner kicks that are neither Inswinger nor Outswinger.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

# ── Path setup ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "raw" / "serie_a_2025_2026" / "events"
sys.path.insert(0, str(ROOT / "dash_app"))

# ── Config ───────────────────────────────────────────────────────────────────
TEAM_FILTER = "FC Internazionale Milano"   # change to any 2025/26 team

# Qualifier columns relevant to corner delivery type
COL_CORNER_TAKEN = "Corner taken"
COL_INSWINGER    = "Inswinger"
COL_OUTSWINGER   = "Outswinger"
COL_STRAIGHT     = "Straight"
COL_CROSS        = "Cross"


def _is_si(val) -> bool:
    if pd.isna(val):
        return False
    return str(val).strip().lower() in ("si", "yes", "1", "true")


def classify_delivery(row: pd.Series) -> str:
    if _is_si(row.get(COL_INSWINGER)):
        return "Inswinger"
    if _is_si(row.get(COL_OUTSWINGER)):
        return "Outswinger"
    if _is_si(row.get(COL_STRAIGHT)):
        return "Straight"
    # Short corner heuristic (Pass End X near flag)
    end_x_raw = row.get("Pass End X")
    try:
        end_x = float(end_x_raw)
        if not _is_si(row.get(COL_CROSS)) and end_x >= 93.0:
            return "Short"
    except (TypeError, ValueError):
        pass
    return "Unknown"


def main() -> None:
    csv_files = sorted(DATA_DIR.glob("*.csv"))
    print(f"Found {len(csv_files)} match CSV files for 2025/2026\n")

    frames: list[pd.DataFrame] = []
    team_lower = TEAM_FILTER.lower()

    for f in csv_files:
        try:
            df = pd.read_csv(f, low_memory=False)
        except Exception as e:
            print(f"  [WARN] Could not load {f.name}: {e}")
            continue

        # Normalise team name column
        if "team_name" not in df.columns:
            continue

        # Filter: type_id == 1 (Pass) AND Corner taken == "Si" AND team matches
        if COL_CORNER_TAKEN not in df.columns:
            continue

        mask_type  = pd.to_numeric(df.get("type_id", pd.Series(dtype=float)), errors="coerce") == 1
        mask_team  = df["team_name"].str.lower().str.strip() == team_lower
        mask_corner = df[COL_CORNER_TAKEN].apply(_is_si)

        corners = df[mask_type & mask_team & mask_corner].copy()
        if not corners.empty:
            corners["_match_file"] = f.name
            frames.append(corners)

    if not frames:
        # Try partial match on team name
        print(f"No exact matches for '{TEAM_FILTER}'. Trying partial match...\n")
        for f in csv_files:
            try:
                df = pd.read_csv(f, low_memory=False)
            except Exception:
                continue
            if "team_name" not in df.columns or COL_CORNER_TAKEN not in df.columns:
                continue
            mask_type   = pd.to_numeric(df.get("type_id", pd.Series(dtype=float)), errors="coerce") == 1
            mask_team   = df["team_name"].str.lower().str.contains(team_lower.split()[0].lower(), na=False)
            mask_corner = df[COL_CORNER_TAKEN].apply(_is_si)
            corners = df[mask_type & mask_team & mask_corner].copy()
            if not corners.empty:
                corners["_match_file"] = f.name
                frames.append(corners)

    if not frames:
        print(f"ERROR: No corner kicks found for team '{TEAM_FILTER}'.")
        print("Available team names in first file:")
        df0 = pd.read_csv(csv_files[0], low_memory=False)
        print(sorted(df0["team_name"].dropna().unique().tolist()))
        return

    all_corners = pd.concat(frames, ignore_index=True)
    all_corners["_delivery"] = all_corners.apply(classify_delivery, axis=1)

    print("=" * 70)
    print(f"CORNER KICK DELIVERY TYPE AUDIT — {TEAM_FILTER}")
    print(f"Season: 2025/2026 — Total corner kicks found: {len(all_corners)}")
    print("=" * 70)

    # ── 1. Delivery type distribution ────────────────────────────────────────
    print("\n── Delivery Type Distribution ──")
    dist = all_corners["_delivery"].value_counts()
    for dtype, cnt in dist.items():
        pct = 100 * cnt / len(all_corners)
        print(f"  {dtype:<15} {cnt:>4}  ({pct:5.1f}%)")

    # ── 2. Raw qualifier flags on every corner ────────────────────────────────
    print("\n── Raw Qualifier Column Presence (across all corner rows) ──")
    for col in [COL_INSWINGER, COL_OUTSWINGER, COL_STRAIGHT, COL_CROSS]:
        present = all_corners[col].apply(_is_si).sum() if col in all_corners.columns else "N/A (col missing)"
        print(f"  {col:<20} flagged = {present}")

    # ── 3. Deep-dive: rows where Straight is flagged ─────────────────────────
    if COL_STRAIGHT in all_corners.columns:
        straight_rows = all_corners[all_corners[COL_STRAIGHT].apply(_is_si)]
        print(f"\n── Rows with 'Straight' qualifier flagged: {len(straight_rows)} ──")
        if not straight_rows.empty:
            show_cols = [c for c in ["_match_file", "team_name", "player_name",
                                      "time_min", "time_sec", "x", "y",
                                      COL_INSWINGER, COL_OUTSWINGER, COL_STRAIGHT,
                                      COL_CROSS, "Pass End X", "Pass End Y"]
                         if c in straight_rows.columns]
            print(straight_rows[show_cols].to_string(index=False))
    else:
        print(f"\n  [!] Column '{COL_STRAIGHT}' NOT FOUND in DataFrame columns.")

    # ── 4. Unknown corners — what qualifiers do they actually carry? ──────────
    unknown = all_corners[all_corners["_delivery"] == "Unknown"]
    print(f"\n── 'Unknown' corners: {len(unknown)} ──")
    if not unknown.empty:
        # Show all qualifier-type columns that appear for unknowns
        qual_cols = [c for c in all_corners.columns
                     if any(kw in c.lower() for kw in
                            ["inswing", "outswing", "straight", "cross",
                             "pass end", "short", "delivery"])]
        if qual_cols:
            print(f"  Qualifier columns inspected: {qual_cols}")
            print(unknown[qual_cols].head(20).to_string(index=False))
        else:
            print("  No obvious qualifier columns found — printing first 5 rows:")
            print(unknown.head(5).to_string())

    # ── 5. All unique column names that contain qualifier-like keywords ───────
    print("\n── All qualifier-related columns present in this dataset ──")
    qual_any = sorted([c for c in all_corners.columns
                       if any(kw in c.lower() for kw in
                              ["inswing", "outswing", "straight", "corner",
                               "cross", "delivery", "pass end", "zone", "swing"])])
    for c in qual_any:
        n_flagged = all_corners[c].apply(_is_si).sum() if all_corners[c].dtype == object else "numeric"
        print(f"  {c:<35}  n_flagged={n_flagged}")

    print("\n── DONE ──")


if __name__ == "__main__":
    main()
