# `canonical_name()` — Team Name Normalisation — Methodology

> **Dashboard location:** Cross-cutting infrastructure (no UI surface)
> **Analysis type:** Infrastructure / utility
> **Primary source file(s):** `src/team_mapping.py` — `canonical_name()`, `_CSV_ALIASES`
> **Precomputed parquet(s):** None — used everywhere data is keyed by team.
> **Last reviewed:** 2026-06-24

---

## 1 — Purpose

`canonical_name()` normalises the many Opta long-form team names (e.g. "FC Internazionale Milano", "Atalanta Bergamasca Calcio") to a single canonical short name (e.g. "Inter", "Atalanta"). Because every analytical module keys its data by team, this one function is what lets shots, possessions, pressing actions, players, and standings from different files and modules all line up to the same team identity.

---

## 2 — Input Data

- **Input:** any raw team-name string (Opta long form, filename fragment, or already-canonical).
- **Mapping:** the `_CSV_ALIASES` dict (long form → canonical short name).
- **Scope:** every team-keyed operation in the app.

---

## 3 — Methodology

### 3.1 — Lookup
`canonical_name(raw_name)` returns `_CSV_ALIASES.get(raw_name, raw_name)` — the canonical alias if known, otherwise the input unchanged. It is a pure, deterministic, side-effect-free lookup.

### 3.2 — Ubiquity
It is called in essentially every module that resolves a team: team filtering (`_filter_team`, `_team_mask`), home/away parsing from filenames, role/possession attribution, league benchmarking, logo resolution (`logo_filename`), and season team discovery (`teams_for_season`). In the project's knowledge graph it is the most connected node (~47 edges), reflecting that it is the universal bridge between every team-keyed community of code.

---

## 4 — Key Metrics & Definitions

Not applicable — utility function. Its "output" is a normalised team string.

---

## 5 — Outputs

- **Canonical team name** (string) for any input alias.
- Indirectly: logo filenames/URLs and season team lists built on top of it.

---

## 6 — Methodological Decisions & Rationale

> **PROTECTED FUNCTION — must never be modified.** Because `canonical_name()` is the cross-community bridge that every team-keyed module depends on, any change to its mapping or behaviour would silently break name matching across modules: shots might no longer join to standings, a player's team might not match their club's aggregates, benchmarking could drop or double-count teams. The fan-in is so large (the most connected node in the codebase) that a change cannot be locally reasoned about. It is therefore frozen — extend the alias dict only with extreme care, never alter the lookup semantics.

- **Identity fallback:** returning the input unchanged when no alias is known means already-canonical names pass through safely and unknown names degrade gracefully (rather than erroring), while still being correctable by adding an alias.
- **Pure lookup:** no I/O or state, so it is fast, deterministic, and safe to call in hot paths and inside `apply`/`map`.

---

## 7 — Limitations & Known Issues

- **Alias coverage is manual:** a new Opta long-form spelling not in `_CSV_ALIASES` passes through unnormalised and could fragment a team's data until the alias is added.
- **Exact-string match only:** there is no fuzzy matching; a typo or unexpected casing would not be normalised.

---

## 8 — Relationship to Other Components

- **Upstream:** none (leaf utility).
- **Downstream:** essentially every analytical module — `xg.py`, `chance_creation.py`, `defensive_*`, `playing_style.py`, `player_analysis.py`, the precompute pipeline, and the season aggregates all depend on it for team identity.
