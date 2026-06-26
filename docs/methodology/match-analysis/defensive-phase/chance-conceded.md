# Chance Conceded — Methodology

> **Dashboard location:** Match Analysis → Defensive Phase → Chances Conceded
> **Analysis type:** Match-level
> **Primary source file(s):** `analytics/chance_conceded.py` — `analyse_chance_conceded()`; UI `components/chance_conceded_cards.py`
> **Precomputed parquet(s):** None per match (season aggregate: [opp-season-chances-conceded.md](../../opponent-analysis/defensive-phase/opp-season-chances-conceded.md)).
> **Last reviewed:** 2026-06-24

---

## 1 — Purpose

Chances Conceded profiles the quality and pattern of the opportunities a team allowed its opponent in a match. By running the full Chance Creation pipeline for the *opponent* and re-framing the result into the defending team's perspective, it answers "how many and how good were the chances we gave up, and how were they created?" — using exactly the same xG model, origin taxonomy, and quality tiers as the attacking view, so created and conceded chances are directly comparable.

---

## 2 — Input Data

- **Event types used:** identical to Chance Creation (shot events `13,14,15,16`, plus possession/qualifier context). Inherited entirely from `analyse_chance_creation` run on the opponent.
- **Qualifiers used:** same as Chance Creation (`Big Chance`, set-piece, through-ball, etc.).
- **Coordinate system:** Opta normalised (0–100). Shots are **flipped** into the defending team's frame: `x → 100 − x`, `y → 100 − y`, so all conceded shots attack toward the same goal regardless of which team took them.
- **Seasons covered:** any match with a CSV.
- **Scope:** per-match only.

---

## 3 — Methodology

### 3.1 — Opponent identification (`_find_opponent`)
The first team name in the match that is not the analysed team (canonical comparison) is taken as the opponent.

### 3.2 — Run Chance Creation for the opponent
`analyse_chance_conceded` calls `analyse_chance_creation(match_csv, opponent, pv_model=...)`. This produces the opponent's shots, chain-to-goal matrix, origin breakdown, shot metrics, and quality tiers (see [chance-creation.md](../offensive-phase/chance-creation.md)) — all from the opponent's attacking perspective.

### 3.3 — Coordinate flip (`_flip_coords`)
Each opponent shot's `x` and `y` are reflected (`100 − x`, `100 − y`) in place, putting every conceded shot into the defending team's coordinate frame so the pitch scatter renders all conceded shots attacking toward one goal.

### 3.4 — Matrix re-keying (`_rename_gs_to_gc`)
The Chain-to-Goal Matrix row `GS` (Goals Scored) is renamed `GC` (Goals Conceded); all other rows (N, xG, SoT%) and the origin columns are preserved. The result is a **chain-to-concede matrix**.

### 3.5 — Convenience aggregates
From the flipped shots: `goals_conceded` (shots with `is_goal`), `xg_against` (sum of per-shot xG, rounded), `big_chances_conceded` (shots with `quality_tier == 2`). Shot quality tiers are passed through unchanged.

---

## 4 — Key Metrics & Definitions

- **xG against (xGA):** sum of xG over all conceded shots — expected goals allowed.
- **Goals conceded:** count of conceded shots that were goals.
- **Big chances conceded:** conceded shots flagged Tier 2 (Big Chance qualifier).
- **Shot metrics (conceded):** total shots faced, in/out of box, SoT% faced, xG per shot faced, in/out-of-box shares.
- **Chain-to-concede matrix:** origins × {N, xG, SoT%, GC} for conceded chances.
- **Quality-tier distribution (conceded):** counts in tiers {0, 2, 3} (see [shot-quality-tiers.md](../../models/shot-quality-tiers.md)).

---

## 5 — Outputs

- **Result dict** consumed by `chance_conceded_card()`: `chain_to_concede_matrix`, `shot_metrics`, `shots_detail` (flipped), `shot_quality_tiers`, `goals_conceded`, `xg_against`, `big_chances_conceded`, `opponent`.
- **Visual outputs:** conceded-shots pitch scatter (defending frame), chain-to-concede matrix, quality-tier distribution.
- **No parquet** — live per match.

---

## 6 — Methodological Decisions & Rationale

- **Reuse the attacking pipeline:** running `analyse_chance_creation` for the opponent guarantees conceded chances are valued and classified identically to created chances (same xG model, same origin priority, same tiers) — there is no separate "defensive xG" definition to drift.
- **Coordinate flip rather than re-computation:** flipping into the defending frame is a pure presentation transform; it keeps the underlying shot quality untouched while making the pitch view intuitive (all conceded shots attack one goal).
- **GS → GC rename only:** the matrix structure is shared; only the goals row is relabelled to read as "conceded", avoiding a parallel matrix implementation.
- **Set-piece vs. open-play distinction is inherited** from the opponent's origin classification ([attack-origin-classification.md](../../models/attack-origin-classification.md)), so conceded set-piece chances are separable from open-play ones via the matrix origin columns.

---

## 7 — Limitations & Known Issues

- **Single-opponent assumption:** `_find_opponent` takes the first non-team name, which is correct for a two-team match file but would mis-resolve in malformed data.
- **Inherits all Chance Creation limitations:** any origin mis-classification or xG limitation in the attacking pipeline propagates here unchanged.
- **No own-goal nuance:** conceded shots use the same own-goal/penalty handling as Chance Creation (penalty xG fixed, own goals 0).

---

## 8 — Relationship to Other Components

- **Upstream:** `chance_creation.analyse_chance_creation` (entire pipeline), [xg-model.md](../../models/xg-model.md), [attack-origin-classification.md](../../models/attack-origin-classification.md), [shot-quality-tiers.md](../../models/shot-quality-tiers.md), `team_mapping.canonical_name()`, optional PV model.
- **Downstream:** `components/chance_conceded_cards.py`; season aggregate [opp-season-chances-conceded.md](../../opponent-analysis/defensive-phase/opp-season-chances-conceded.md) (which adds the Clean Sheet card).
