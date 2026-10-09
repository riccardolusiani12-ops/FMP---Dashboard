"""
Metric Registry — the single source of truth for glossary definitions.

``METRICS`` is the ordered list of every entry (Team Overview → offensive →
defensive → transitions/set pieces → players). Each metric is defined once,
even when it appears in several sections; ``sections`` and the per-section
``module`` dict say where it is shown. Field meanings: see ``_common.REQUIRED_FIELDS``
and docs/glossary_review.md.
"""

from __future__ import annotations

from src.glossary import (
    entries_defensive,
    entries_offensive,
    entries_players,
    entries_team_overview,
    entries_transitions_set_pieces,
)

METRICS: list[dict] = [
    *entries_team_overview.ENTRIES,
    *entries_offensive.ENTRIES,
    *entries_defensive.ENTRIES,
    *entries_transitions_set_pieces.ENTRIES,
    *entries_players.ENTRIES,
]
