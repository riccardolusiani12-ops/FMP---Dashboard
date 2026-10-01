"""
Published match events — Match Analysis without data/raw/ (Render).
=====================================================================

The Match Analysis modules read one Opta event CSV per match via
``pd.read_csv(match_csv)``. data/raw/ is not versioned, so for the seasons
listed in ``match_analysis_seasons`` (pipeline/seasons.toml) each match is
published as a compact parquet:

    data/match_events/<season>/<original CSV stem>.parquet

holding only MATCH_EVENT_COLUMNS, every cell stored as its original CSV text
(null for empty). On demand the selected match is rebuilt as a CSV with the same
file name under a temp dir, so the analytics run unchanged and pandas infers the
dtypes exactly as it does on the raw file (dtypes differ from match to match,
which is why the cells are kept as text).

Rebuilt CSVs: deterministic path ``<FMP_MATCH_CSV_DIR or /tmp/fmp_match_events>/
<season>/<stem>.csv``, atomic write, at most MATCH_CSV_CACHE_MAX files (LRU).

CLI (from dash_app/):
    python -m src.utils.match_events export --season 2026_2027 [--season ...] [--force]
    python -m src.utils.match_events prune --keep 2026_2027 2025_2026
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import threading
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.config import MATCH_EVENTS_DIR, RAW_DATA_DIR
from src.utils.match_event_columns import MATCH_EVENT_COLUMNS

MATCH_CSV_CACHE_DIR: Path = Path(os.getenv("FMP_MATCH_CSV_DIR", "/tmp/fmp_match_events"))
MATCH_CSV_CACHE_MAX: int = 30

_SCHEMA = pa.schema([(c, pa.string()) for c in MATCH_EVENT_COLUMNS])


def _atomic_tmp(dest: Path) -> Path:
    """Unique sibling temp path (per process and thread) for an atomic replace."""
    return dest.with_name(f".{dest.name}.{os.getpid()}.{threading.get_ident()}.tmp")


# ═══════════════════════════════════════════════════════════════════════════════
# EXPORT  (raw CSV → published parquet)
# ═══════════════════════════════════════════════════════════════════════════════

def export_match(csv_path: Path, out_path: Path) -> Path:
    """Write the MATCH_EVENT_COLUMNS of one raw match CSV as a text-only parquet."""
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False, na_values=[""])
    missing = [c for c in MATCH_EVENT_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{csv_path.name}: missing columns {missing}")
    table = pa.Table.from_pandas(df[list(MATCH_EVENT_COLUMNS)], schema=_SCHEMA,
                                 preserve_index=False)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = _atomic_tmp(out_path)
    try:
        pq.write_table(table, tmp, compression="zstd", compression_level=19)
        os.replace(tmp, out_path)
    finally:
        tmp.unlink(missing_ok=True)
    return out_path


def export_season(season: str, raw_events_dir: Path | None = None,
                  out_dir: Path | None = None, force: bool = False) -> tuple[int, int]:
    """Export every raw match CSV of *season*. Existing parquets are kept unless
    *force*. Returns (written, skipped)."""
    raw_events_dir = raw_events_dir or RAW_DATA_DIR / f"serie_a_{season}" / "events"
    out_dir = out_dir or MATCH_EVENTS_DIR / season
    csvs = sorted(raw_events_dir.glob("*.csv"))
    if not csvs:
        raise FileNotFoundError(f"no match CSVs in {raw_events_dir}")
    written = skipped = 0
    for csv in csvs:
        out = out_dir / f"{csv.stem}.parquet"
        if out.exists() and not force:
            skipped += 1
            continue
        export_match(csv, out)
        written += 1
    return written, skipped


def prune(keep: list[str], base_dir: Path | None = None) -> list[str]:
    """Remove published seasons not in *keep*. Returns the removed season keys."""
    base_dir = base_dir or MATCH_EVENTS_DIR
    removed = []
    for d in sorted(base_dir.glob("*")):
        if d.is_dir() and d.name not in keep:
            shutil.rmtree(d)
            removed.append(d.name)
    return removed


# ═══════════════════════════════════════════════════════════════════════════════
# MATERIALISE  (published parquet → temp CSV read by the analytics)
# ═══════════════════════════════════════════════════════════════════════════════

def _evict(keep: Path) -> None:
    """Keep at most MATCH_CSV_CACHE_MAX rebuilt CSVs (least recently used out)."""
    files = []
    for p in MATCH_CSV_CACHE_DIR.glob("*/*.csv"):
        try:
            files.append((p.stat().st_mtime, p))
        except FileNotFoundError:          # removed meanwhile by another worker
            pass
    files.sort(reverse=True)
    for _, p in files[MATCH_CSV_CACHE_MAX:]:
        if p != keep:
            p.unlink(missing_ok=True)


def materialize_match_csv(parquet_path: Path) -> Path:
    """Rebuild the match CSV for *parquet_path*; returns the temp CSV path."""
    dest = MATCH_CSV_CACHE_DIR / parquet_path.parent.name / f"{parquet_path.stem}.csv"
    try:
        if dest.stat().st_mtime >= parquet_path.stat().st_mtime:
            os.utime(dest)                  # LRU touch
            return dest
    except FileNotFoundError:
        pass
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = _atomic_tmp(dest)
    try:
        pd.read_parquet(parquet_path).to_csv(tmp, index=False)
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)
    _evict(keep=dest)
    return dest


def ensure_match_csv(path: Path) -> Path:
    """Return a readable match CSV for *path*.

    A raw CSV (or a still-cached rebuilt one) is returned as is. A rebuilt CSV
    that has been evicted — e.g. a Player Analysis store pointing to it — is
    rebuilt from its published parquet.
    """
    path = Path(path)
    if path.suffix == ".parquet":
        return materialize_match_csv(path)
    if path.exists():
        return path
    try:
        path.relative_to(MATCH_CSV_CACHE_DIR)
    except ValueError:
        return path
    parquet = MATCH_EVENTS_DIR / path.parent.name / f"{path.stem}.parquet"
    return materialize_match_csv(parquet) if parquet.exists() else path


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Publish per-match event parquets")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("export", help="raw CSVs → data/match_events/<season>/")
    ex.add_argument("--season", action="append", required=True)
    ex.add_argument("--force", action="store_true", help="rewrite existing parquets")
    pr = sub.add_parser("prune", help="remove published seasons not listed")
    pr.add_argument("--keep", nargs="+", required=True)
    args = ap.parse_args(argv)

    if args.cmd == "export":
        for season in args.season:
            written, skipped = export_season(season, force=args.force)
            print(f"{season}: {written} written, {skipped} already published")
    else:
        removed = prune(args.keep)
        print(f"removed: {', '.join(removed) or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
