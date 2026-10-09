"""
Read-only accessors for the metric registry.

Entries are returned as deep copies so callers (e.g. a glossary page) cannot
mutate the cached registry.
"""

from __future__ import annotations

import copy
from functools import lru_cache
from typing import Optional

from src.glossary._common import SECTIONS


@lru_cache(maxsize=1)
def _registry() -> tuple[dict, ...]:
    from src.glossary.registry import METRICS
    return tuple(METRICS)


@lru_cache(maxsize=1)
def _by_id() -> dict[str, dict]:
    return {m["id"]: m for m in _registry()}


def get_registry() -> list[dict]:
    """All entries, in registry order."""
    return copy.deepcopy(list(_registry()))


def get_metric(metric_id: str) -> Optional[dict]:
    """One entry by id, or None."""
    entry = _by_id().get(metric_id)
    return copy.deepcopy(entry) if entry is not None else None


def metrics_for_section(section: str) -> list[dict]:
    """Entries shown in *section* ("team_overview", "match_analysis", "opponent_analysis")."""
    if section not in SECTIONS:
        raise ValueError(f"Unknown section {section!r}; expected one of {SECTIONS}")
    return [copy.deepcopy(m) for m in _registry() if section in m["sections"]]


def metrics_for_module(section: str, module: str) -> list[dict]:
    """Entries shown in one module (card) of a section."""
    return [m for m in metrics_for_section(section) if m["module"].get(section) == module]
