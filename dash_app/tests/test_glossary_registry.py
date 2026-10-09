"""
Validation of the metric glossary registry (src/glossary).

Checks schema completeness, controlled vocabularies, source docs, the locked
definitions (two PPDA variants, PENALTY_XG, box boundary, season aggregation
wording) and that every UI metric label maps to a registry entry or is
explicitly listed as unmapped.
"""

import re
from pathlib import Path

import pytest

from src.glossary import loader
from src.glossary._common import (
    LEGACY_DOC_PREFIXES, LEGACY_DOCS, READINGS, REQUIRED_FIELDS,
    SEASON_AGGREGATIONS, SEASON_MEAN_DEVIATION, SEASON_RATIO, SECTIONS, STATUSES,
)
from src.glossary.registry import METRICS
from src.glossary.ui_inventory import UI_METRICS, UNMAPPED

REPO_ROOT = Path(__file__).resolve().parents[2]
BY_ID = {m["id"]: m for m in METRICS}


def _ids(entries):
    return [m["id"] for m in entries]


# ── Schema ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("entry", METRICS, ids=_ids(METRICS))
def test_entry_has_exactly_the_schema_fields(entry):
    assert set(entry) == set(REQUIRED_FIELDS)


def test_ids_are_unique_slugs():
    ids = _ids(METRICS)
    assert len(ids) == len(set(ids)), [i for i in ids if ids.count(i) > 1]
    for mid in ids:
        assert re.fullmatch(r"[a-z0-9_]+", mid), mid


@pytest.mark.parametrize("entry", METRICS, ids=_ids(METRICS))
def test_sections_and_modules_are_valid(entry):
    assert entry["sections"], "at least one section"
    assert len(entry["sections"]) == len(set(entry["sections"]))
    assert set(entry["sections"]) <= set(SECTIONS)
    assert set(entry["module"]) == set(entry["sections"])
    assert all(isinstance(v, str) and v.strip() for v in entry["module"].values())


@pytest.mark.parametrize("entry", METRICS, ids=_ids(METRICS))
def test_controlled_vocabularies(entry):
    assert entry["reading"] in READINGS
    assert entry["reading_note"].strip()
    assert entry["status"] in STATUSES
    assert entry["season_aggregation"] is None or entry["season_aggregation"] in SEASON_AGGREGATIONS
    assert entry["unit"].strip()
    assert entry["name"].strip()
    assert entry["formula"] is None or entry["formula"].strip()


@pytest.mark.parametrize("entry", METRICS, ids=_ids(METRICS))
def test_definitions_are_present(entry):
    short = entry["short_definition"].strip()
    assert short
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", short) if s]
    assert len(sentences) <= 2, short
    if entry["status"] != "needs_review":
        assert entry["methodology"].strip()


@pytest.mark.parametrize("entry", METRICS, ids=_ids(METRICS))
def test_variants_are_well_formed(entry):
    variants = entry["variants"]
    if variants is None:
        return
    assert len(variants) >= 2
    for v in variants:
        assert v["section"] in entry["sections"]
        assert v["name"].strip() and v["definition"].strip()


def test_review_status():
    assert not [m["id"] for m in METRICS if m["status"] == "needs_review"]
    # Known season-aggregation deviation (mean of per-match values), fix pending.
    assert {m["id"] for m in METRICS if m["status"] == "pending_fix"} == {
        "possession_pct", "tempo", "ps_possession",
        "immediate_press_rate", "organised_drop_rate",
    }
    assert "pending_fix" in STATUSES


def test_name_is_unique_within_each_module():
    seen = {}
    for m in METRICS:
        for section in m["sections"]:
            key = (m["name"], section, m["module"][section])
            assert key not in seen, f"{key} used by {seen[key]} and {m['id']}"
            seen[key] = m["id"]


# ── Source docs ───────────────────────────────────────────────────────────────

# code-derived, no methodology doc; reviewed by owner on 2026-10-09
NO_SOURCE_DOC = {
    "league_position", "season_record", "last_5_form", "goal_difference",
    "points_per_game", "mean_age", "lineup_minutes", "lineup_avg_minutes",
    "pressing_tier",
}


@pytest.mark.parametrize("entry", METRICS, ids=_ids(METRICS))
def test_source_doc_exists_and_is_current(entry):
    doc = entry["source_doc"]
    if doc is None:
        assert entry["status"] == "needs_review" or entry["id"] in NO_SOURCE_DOC, \
            "undocumented entries must be flagged or explicitly allowlisted"
        return
    assert entry["id"] not in NO_SOURCE_DOC, "allowlisted entry now has a doc; drop it from NO_SOURCE_DOC"
    assert (REPO_ROOT / doc).is_file(), doc
    assert doc not in LEGACY_DOCS
    assert not doc.startswith(LEGACY_DOC_PREFIXES)


# ── Locked definitions ────────────────────────────────────────────────────────

def test_two_distinct_ppda_definitions():
    to_ppda = BY_ID["ppda_team_overview"]
    opp_ppda = BY_ID["ppda_defensive_actions"]
    match_ppda = BY_ID["ppda_final_third"]

    assert to_ppda["name"] == opp_ppda["name"] == "PPDA"
    assert to_ppda["sections"] == ["team_overview"]
    assert "team_overview" not in opp_ppda["sections"] + match_ppda["sections"]
    assert "ball recover" in to_ppda["formula"]
    for entry in (opp_ppda, match_ppda):
        assert "tackles + interceptions + fouls + challenges" in entry["formula"]
        assert "recover" not in entry["formula"]
    for entry in (to_ppda, opp_ppda, match_ppda):
        assert "never merge" in entry["methodology"]


def test_penalty_xg_and_box_boundary_match_code():
    from src.analytics.chance_creation import PENALTY_BOX_X_MIN
    from src.analytics.xg import PENALTY_XG

    assert PENALTY_XG == 0.79
    assert PENALTY_BOX_X_MIN == 83.33
    text = " ".join(m["methodology"] + " " + (m["formula"] or "") for m in METRICS)
    assert "0.79" in text
    assert "83.33" in text
    assert "83.5" not in text


@pytest.mark.parametrize("entry", METRICS, ids=_ids(METRICS))
def test_season_ratio_wording(entry):
    agg = entry["season_aggregation"]
    if agg == "ratio_of_sums":
        assert SEASON_RATIO in entry["methodology"]
    if agg == "mean_of_match_values":
        assert SEASON_MEAN_DEVIATION in entry["methodology"]
    seasonal = set(entry["sections"]) & {"team_overview", "opponent_analysis"}
    if seasonal and entry["unit"] in ("%", "ratio") and agg not in (None, "rank_percentile", "shrinkage_adjusted"):
        assert SEASON_RATIO in entry["methodology"] or SEASON_MEAN_DEVIATION in entry["methodology"]


# ── UI inventory coverage ─────────────────────────────────────────────────────

@pytest.mark.parametrize("row", UI_METRICS, ids=[f"{r[1]}:{r[0]}" for r in UI_METRICS])
def test_every_ui_metric_maps_to_an_entry(row):
    label, section, module, file, metric_id = row
    assert (REPO_ROOT / file).is_file(), file
    assert metric_id in BY_ID, f"{label!r} → unknown id {metric_id!r}"
    entry = BY_ID[metric_id]
    assert section in entry["sections"], f"{metric_id} not in {section}"
    assert module in entry["module"][section], (module, entry["module"][section])


def test_every_entry_is_shown_somewhere():
    referenced = {row[4] for row in UI_METRICS}
    assert set(BY_ID) - referenced == set()


def test_unmapped_rows_are_explained_and_disjoint():
    mapped = {(r[0], r[1], r[2]) for r in UI_METRICS}
    for label, section, module, file, reason in UNMAPPED:
        assert section in SECTIONS
        assert (REPO_ROOT / file).is_file(), file
        assert reason.strip()
        assert (label, section, module) not in mapped


# ── Loader ────────────────────────────────────────────────────────────────────

def test_loader_accessors():
    assert len(loader.get_registry()) == len(METRICS)
    m = loader.get_metric("ppda_team_overview")
    m["name"] = "mutated"
    assert loader.get_metric("ppda_team_overview")["name"] == "PPDA"
    assert loader.get_metric("does_not_exist") is None
    for section in SECTIONS:
        assert all(section in e["sections"] for e in loader.metrics_for_section(section))
    with pytest.raises(ValueError):
        loader.metrics_for_section("glossary")
    assert loader.metrics_for_module("team_overview", "Pressing Intensity")
