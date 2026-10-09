"""
Shared vocabulary, canonical wording and the entry constructor for the
metric glossary registry.

Every entry module builds its metrics with ``metric(...)`` and reuses the
wording constants below, so the same concept ("final third", "open play",
"season aggregate" …) is phrased identically across the whole registry.
"""

from __future__ import annotations

from typing import Optional

# ═══════════════════════════════════════════════════════════════════════════════
# CONTROLLED VOCABULARIES
# ═══════════════════════════════════════════════════════════════════════════════

SECTIONS = ("team_overview", "match_analysis", "opponent_analysis")
READINGS = ("higher_better", "lower_better", "contextual")
STATUSES = ("ok", "needs_review", "pending_fix")

# How a value shown at season level is built from match-level data.
#   sum                  — season total of a count
#   total_per_match      — season total ÷ matches played
#   ratio_of_sums        — Σ numerator ÷ Σ denominator (the locked rule)
#   mean_of_match_values — arithmetic mean of per-match values (rule deviation)
#   median_of_match_values — median of per-match values
#   season_events        — computed once over the pooled season event table
#   rank_percentile      — within-season rank / percentile of a season value
#   shrinkage_adjusted   — empirical-Bayes adjusted per-90 (player analysis)
#   external             — value comes from an external source (no aggregation)
SEASON_AGGREGATIONS = (
    "sum", "total_per_match", "ratio_of_sums", "mean_of_match_values",
    "median_of_match_values", "season_events", "rank_percentile",
    "shrinkage_adjusted", "external",
)

REQUIRED_FIELDS = (
    "id", "name", "sections", "module", "short_definition", "formula", "unit",
    "reading", "reading_note", "methodology", "notes", "source_doc",
    "variants", "status", "season_aggregation",
)

# ═══════════════════════════════════════════════════════════════════════════════
# METHODOLOGY DOCS
# ═══════════════════════════════════════════════════════════════════════════════

_M = "docs/methodology/"

D_FORMATION = _M + "team-overview/formation-analysis.md"
D_GOAL_DIST = _M + "team-overview/goal-distribution.md"
D_WHEEL = _M + "team-overview/playing-style-wheel.md"
D_PPDA_TO = _M + "team-overview/ppda-team-overview.md"
D_STYLE_EVO = _M + "team-overview/style-evolution.md"
D_XG_SUMMARY = _M + "team-overview/xg-summary.md"

D_GK = _M + "match-analysis/offensive-phase/goalkeeper-buildup.md"
D_FT = _M + "match-analysis/offensive-phase/buildup-final-third.md"
D_CC = _M + "match-analysis/offensive-phase/chance-creation.md"
D_CCON = _M + "match-analysis/defensive-phase/chance-conceded.md"
D_CASTLE = _M + "match-analysis/defensive-phase/defensive-castle.md"
D_PRESS = _M + "match-analysis/defensive-phase/defensive-pressing.md"
D_STRUCT = _M + "match-analysis/other/defensive-structure.md"
D_HIGH_REGAINS = _M + "match-analysis/other/high-regains.md"
D_CORNERS = _M + "match-analysis/set-pieces/corner-kicks.md"
D_FREE_KICKS = _M + "match-analysis/set-pieces/free-kicks.md"
D_DEF_TRANS = _M + "match-analysis/transitions/defensive-transitions.md"
D_OFF_TRANS = _M + "match-analysis/transitions/offensive-transitions.md"

D_ORIGIN = _M + "models/attack-origin-classification.md"
D_PV = _M + "models/possession-value-model.md"
D_TIERS = _M + "models/shot-quality-tiers.md"
D_XG = _M + "models/xg-model.md"

D_OA_CCON = _M + "opponent-analysis/defensive-phase/opp-season-chances-conceded.md"
D_OA_CASTLE = _M + "opponent-analysis/defensive-phase/opp-season-defensive-castle.md"
D_OA_PRESS = _M + "opponent-analysis/defensive-phase/opp-season-defensive-pressing.md"
D_OA_FT = _M + "opponent-analysis/offensive-phase/opp-season-buildup-final-third.md"
D_OA_CC = _M + "opponent-analysis/offensive-phase/opp-season-chance-creation.md"
D_OA_GK = _M + "opponent-analysis/offensive-phase/opp-season-goalkeeper-buildup.md"
D_PLAYER = _M + "opponent-analysis/player-analysis/player-analysis.md"
D_OA_CORNERS = _M + "opponent-analysis/set-pieces/opp-season-corner-kicks.md"
D_OA_DEF_TRANS = _M + "opponent-analysis/transitions/opp-season-defensive-transitions.md"
D_OA_OFF_TRANS = _M + "opponent-analysis/transitions/opp-season-offensive-transitions.md"

# Docs classified LEGACY in the Phase 0 audit — never valid as source_doc.
LEGACY_DOC_PREFIXES = (_M + "_archive/",)
LEGACY_DOCS = (_M + "match-analysis/other/match-report.md",)

# ═══════════════════════════════════════════════════════════════════════════════
# CANONICAL WORDING
# ═══════════════════════════════════════════════════════════════════════════════

COORDS = (
    "Coordinates are Opta-normalised (0–100) and team-relative: x runs from "
    "the team's own goal (0) to the opponent's goal (100) in both halves; "
    "y runs from the right touchline (0) to the left touchline (100)."
)
FINAL_THIRD = "the final third (x ≥ 66.67)"
PENALTY_BOX = "the penalty box (x ≥ 83.33 and 21.1 ≤ y ≤ 78.9)"
OPEN_PLAY = (
    "open play (the possession does not start from a corner, free kick, "
    "throw-in, goal kick, penalty or goalkeeper-hands restart)"
)
CORRIDORS = "Corridors: Left y > 66.67, Centre 33.33 ≤ y ≤ 66.67, Right y < 33.33."
GRID_18 = (
    "18-zone grid: 6 bands along x (16.67 units each) × 3 corridors along y "
    "(33.33 units each); Z1–Z3 is the team's own box band, Z13–Z15 the band "
    "just outside the opponent box (Z14 = central), Z16–Z18 the opponent box band."
)
THIRDS = "Thirds by x: own third x < 33.33, middle third 33.33 ≤ x < 66.67, final third x ≥ 66.67."

SEASON_RATIO = (
    "**Season aggregate:** numerators and denominators are summed across all "
    "of the team's matches first and divided once (ratio of sums); the season "
    "value is not an average of per-match rates."
)
SEASON_MEAN_DEVIATION = (
    "**Season aggregate (code reference):** the season value is the "
    "arithmetic mean of the per-match values, not a ratio of summed "
    "numerators and denominators. This deviates from the ratio-of-sums rule "
    "and is reported in docs/glossary_review.md; it has not been changed."
)
PER_MATCH = (
    "Per-match values are the season total ÷ matches played (matches counted "
    "from the season's match files)."
)
MODAL_TOTALS = "League comparison modal: ranks all 20 teams on the season total."
MODAL_PER_MATCH = (
    "League comparison modal: ranks all 20 teams on the per-match value "
    "(not on the season total)."
)
MODAL_RATE = "League comparison modal: ranks all 20 teams on the season rate."

PENALTY_XG_TEXT = "Penalties carry a fixed xG of 0.79 (PENALTY_XG); own goals carry xG 0."
ROW_XG_NOTE = (
    "Shot xG here comes from the row-level xG API (compute_shot_xg via "
    "compute_xg_for_shot), which sets the rebound and assist-type features to 0. "
    "Team Overview xG uses the batch API with those features, so totals can "
    "differ slightly for the same team and season."
)
OWN_GOAL_ROWS = (
    "Opponent own goals are added to the team's shot list as 'Own Goal' rows "
    "(xG 0, on target, tier 3), so they are counted in shot totals, SoT% and "
    "goals, and appear in the TOTAL column but in no origin column."
)


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY CONSTRUCTOR
# ═══════════════════════════════════════════════════════════════════════════════

def metric(
    *,
    id: str,
    name: str,
    sections: list[str],
    module: dict[str, str],
    short_definition: str,
    formula: Optional[str],
    unit: str,
    reading: str,
    reading_note: str,
    methodology: str,
    source_doc: Optional[str],
    notes: Optional[str] = None,
    variants: Optional[list[dict]] = None,
    status: str = "ok",
    season_aggregation: Optional[str] = None,
) -> dict:
    """Build one registry entry; keyword-only so every field is explicit."""
    return {
        "id": id,
        "name": name,
        "sections": list(sections),
        "module": dict(module),
        "short_definition": short_definition,
        "formula": formula,
        "unit": unit,
        "reading": reading,
        "reading_note": reading_note,
        "methodology": methodology.strip(),
        "notes": notes,
        "source_doc": source_doc,
        "variants": variants,
        "status": status,
        "season_aggregation": season_aggregation,
    }


def md(*parts: str) -> str:
    """Join methodology paragraphs with blank lines."""
    return "\n\n".join(p.strip() for p in parts if p and p.strip())
