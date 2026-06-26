# Caching Layer — Methodology

> **Dashboard location:** Cross-cutting infrastructure (no UI surface)
> **Analysis type:** Infrastructure / utility
> **Primary source file(s):** `src/utils/caching.py` — `cache_get()`, `cache_set()`, `cache_clear()`, `cached`; `analytics/data_loader.py` (`_read_parquet` lru_cache, `invalidate_cache`)
> **Precomputed parquet(s):** None — caches in-memory.
> **Last reviewed:** 2026-06-24

---

## 1 — Purpose

The caching layer keeps frequently-read artifacts (loaded Parquet tables, computed results) in memory so repeated callback invocations don't re-read from disk or recompute. Combined with the precompute pipeline, it ensures the dashboard stays responsive under interactive use.

---

## 2 — Input Data

- **Input:** any keyed value a caller wishes to memoise (typically loaded Parquet DataFrames or derived results).
- **Config:** `CACHE_TTL` (time-to-live for the TTL dict cache).
- **Scope:** application-wide, in-process.

---

## 3 — Methodology

### 3.1 — Dual-layer caching
- **`functools.lru_cache`** at the loader level (e.g. `data_loader._read_parquet`) memoises parquet reads by path within the process — an in-memory LRU.
- **TTL-aware dict cache** (`_cache: {key: (timestamp, value)}`) for artifact data, accessed via `cache_get` / `cache_set`.

### 3.2 — `cache_get` / `cache_set`
`cache_get(key)` returns the value if present and `time.time() − stored_ts < CACHE_TTL`, otherwise evicts the stale entry and returns `None`. `cache_set(key, value)` stores the value with the current timestamp. This is the pattern callbacks use to wrap expensive reads: try `cache_get`, compute on miss, `cache_set`.

### 3.3 — `cached` decorator
`@cached` wraps a function, keying the cache on `module.func:args:kwargs` (stringified), returning the cached result on hit and storing it on miss. It exposes `__wrapped__` for introspection.

### 3.4 — Invalidation
- **`cache_clear()`** empties the TTL dict cache entirely.
- **TTL expiry** evicts individual entries lazily on access.
- **`data_loader.invalidate_cache()`** clears the loader-level lru_cache (called when ready data is refreshed by the precompute chain), so a recompute is reflected without a stale read.

---

## 4 — Key Metrics & Definitions

Not applicable — infrastructure. Key concepts: TTL (entry lifetime), LRU (loader-level eviction), cache key (`module.func:args:kwargs` or caller-chosen string).

---

## 5 — Outputs

- **Cached values** returned to callers; no persisted artifacts.

---

## 6 — Methodological Decisions & Rationale

- **Two layers for two access shapes:** `lru_cache` is ideal for pure, path-keyed loader functions; the TTL dict cache suits arbitrary caller-chosen keys with a freshness bound. Using both covers loader reads and ad-hoc results without one mechanism fighting the other.
- **TTL freshness bound:** a time-to-live ensures cached artifacts are eventually re-read, complementing the precompute staleness detection so a refreshed Parquet is picked up.
- **Explicit invalidation on refresh:** `invalidate_cache()` is called when the ready data is regenerated, preventing the loader LRU from serving pre-refresh tables.
- **Lazy eviction:** stale TTL entries are removed on access rather than via a background sweeper, keeping the layer simple and dependency-free.

---

## 7 — Limitations & Known Issues

- **In-process only:** the cache is per-process and not shared across workers; a multi-worker deployment caches independently.
- **Unbounded TTL dict:** the TTL dict cache has no size cap (only time-based eviction), so a very high-cardinality key space could grow memory until entries expire.
- **Stringified cache keys:** the `cached` decorator keys on stringified args, so non-stringable or large arguments could produce awkward keys or collisions.

---

## 8 — Relationship to Other Components

- **Upstream:** `config.CACHE_TTL`.
- **Downstream:** `data_loader.py` and any callback wrapping reads with `cache_get`/`cache_set`; works in tandem with [precompute-pipeline.md](precompute-pipeline.md) (the precompute writes Parquets; the cache serves them quickly and is invalidated on refresh).
