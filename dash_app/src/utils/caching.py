"""
Simple disk-backed + in-memory caching for loaded artifacts.
Uses functools.lru_cache for function-level caching
and a TTL-aware dict cache for artifact data.
"""

import time
from functools import lru_cache
from typing import Any, Optional

from src.config import CACHE_TTL

# ── Simple TTL cache ──────────────────────────────────────────────────────────

_cache: dict[str, tuple[float, Any]] = {}


def cache_get(key: str) -> Optional[Any]:
    """Return cached value if exists and not expired, else None."""
    if key in _cache:
        ts, val = _cache[key]
        if time.time() - ts < CACHE_TTL:
            return val
        del _cache[key]
    return None


def cache_set(key: str, value: Any) -> None:
    """Store value in cache with current timestamp."""
    _cache[key] = (time.time(), value)


def cache_clear() -> None:
    """Clear the entire cache."""
    _cache.clear()


def cached(func):
    """Decorator: cache function results keyed by all args (stringified)."""

    def wrapper(*args, **kwargs):
        key = f"{func.__module__}.{func.__name__}:{args}:{kwargs}"
        hit = cache_get(key)
        if hit is not None:
            return hit
        result = func(*args, **kwargs)
        cache_set(key, result)
        return result

    wrapper.__wrapped__ = func
    return wrapper
