"""
Controlli di qualità sui CSV convertiti, eseguiti PRIMA della copia nella
cartella raw della dash. Qualsiasi problema → QualityError (la pipeline si ferma).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from config import DASH_DIR, REPO_ROOT

if str(DASH_DIR) not in sys.path:
    sys.path.insert(0, str(DASH_DIR))

from src.team_mapping import TEAM_LOGO_MAP, canonical_name  # noqa: E402


class QualityError(Exception):
    pass


def match_id_from_csv_name(path: Path) -> str:
    return path.stem.rsplit("_", 1)[-1]


def reference_columns(raw_events_dir: Path) -> tuple[list[str], Path]:
    """Colonne di un CSV già presente nella dash (stagione corrente, altrimenti la più recente)."""
    dirs = [raw_events_dir] + sorted(
        (REPO_ROOT / "data" / "raw").glob("serie_a_*/events"), reverse=True
    )
    for d in dirs:
        if d.exists():
            ref = next(iter(sorted(d.glob("*.csv"))), None)
            if ref is not None:
                return list(pd.read_csv(ref, nrows=0, encoding="utf-8-sig").columns), ref
    raise QualityError("Nessun CSV di riferimento trovato in data/raw/")


def _resolvable(name: str) -> bool:
    return canonical_name(name) in TEAM_LOGO_MAP


def check_csvs(csv_paths: list[Path], expected_ids: set[str], raw_events_dir: Path) -> None:
    ref_cols, ref_path = reference_columns(raw_events_dir)
    errors: list[str] = []

    ids = [match_id_from_csv_name(p) for p in csv_paths]
    dupes = {m for m in ids if ids.count(m) > 1}
    if dupes:
        errors.append(f"match_id duplicati tra i nuovi CSV: {sorted(dupes)}")

    existing = {match_id_from_csv_name(p) for p in raw_events_dir.glob("*.csv")} if raw_events_dir.exists() else set()
    already = set(ids) & existing
    if already:
        errors.append(f"match_id già presenti nella cartella raw: {sorted(already)}")

    missing = expected_ids - set(ids)
    if missing:
        errors.append(f"partite attese senza CSV: {sorted(missing)}")

    for p in csv_paths:
        name = p.name
        df = pd.read_csv(p, encoding="utf-8-sig", low_memory=False)
        if df.empty:
            errors.append(f"{name}: CSV vuoto")
            continue
        if list(df.columns) != ref_cols:
            errors.append(f"{name}: colonne diverse da {ref_path.name}")
        # week valorizzato, numerico e coerente col nome file
        weeks = df["week"].dropna().astype(str).unique().tolist()
        if len(weeks) != 1 or not weeks[0].isdigit() or df["week"].isna().any():
            errors.append(f"{name}: colonna week non valida ({weeks})")
        elif name.split("_", 1)[0] != weeks[0]:
            errors.append(f"{name}: week del nome file diverso da week={weeks[0]}")
        # match_id unico e coerente col nome file
        mids = df["match_id"].astype(str).unique().tolist()
        if mids != [match_id_from_csv_name(p)]:
            errors.append(f"{name}: match_id nel file {mids} non coerente col nome")
        # nomi squadra risolvibili da canonical_name()
        parts = p.stem.split("_")
        if len(parts) < 4:
            errors.append(f"{name}: nome file non nel formato <week>_<Home>_<Away>_<id>")
        else:
            for team in (parts[1], parts[2]):
                if not _resolvable(team):
                    errors.append(f"{name}: squadra '{team}' non risolta da canonical_name()")
        for team in df["team_name"].dropna().astype(str).unique():
            if team != "N/A" and not _resolvable(team):
                errors.append(f"{name}: team_name '{team}' non risolto da canonical_name()")

    if errors:
        raise QualityError("; ".join(errors))
