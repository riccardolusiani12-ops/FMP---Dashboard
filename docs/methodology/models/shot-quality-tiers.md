# Shot Quality Tier System — Methodology

> **Dashboard location:** Match Analysis → Offensive Phase → Chance Creation (quality-tier distribution); reused in the season-aggregate Chance Creation and Chances Conceded views.
> **Analysis type:** Model / classification rule (per-shot label)
> **Primary source file(s):** `analytics/chance_creation.py` — `classify_shot_quality()`, `ChanceCreationAnalyzer._compute_quality_tiers()`.
> **Precomputed parquet(s):** Tier is derived at render/aggregate time from shot rows; the underlying shot attributes live in `shots_{season}.parquet`.
> **Last reviewed:** 2026-06-24

---

## 1 — Purpose

The shot-quality tier system buckets every attempt into a small number of interpretable quality bands so an analyst can read the *shape* of a team's chance creation at a glance — how many speculative efforts versus genuine high-quality chances versus actual conversions. It complements the continuous xG value with a discrete, communicable classification used in the quality-tier distribution charts.

---

## 2 — Input Data

- **Event types used:** shot events `type_id` ∈ {13, 14, 15, 16} (Miss, Post, Saved, Goal). Goal = 16; on target = type_id ∈ {15, 16}.
- **Qualifiers used:** `Big Chance` (drives Tier 2). The shot's xG value is passed in but, in the current implementation, **not** used as a tier threshold.
- **Coordinate system:** not used for tiering (location feeds other KPIs).
- **Seasons covered:** all (2021/22–2025/26).
- **Scope:** per-match and season-aggregate.

---

## 3 — Methodology

### 3.1 — Tier assignment (`classify_shot_quality`)
The function takes `type_id, xg_value, is_on_target, is_goal_event, is_big_chance` and returns an integer tier using strict priority:

```
if is_goal_event:    return 3      # Converted
if is_big_chance:    return 2      # Big Chance
else:                return 0      # Speculative
```

A goal outranks the Big Chance qualifier; a Big Chance that was not scored is Tier 2; everything else is Tier 0.

### 3.2 — Tier distribution (`_compute_quality_tiers`)
The analyzer initialises a `{0: 0, 2: 0, 3: 0}` counter and increments the tier of each shot, producing the per-match (or per-season) distribution across the three buckets.

### 3.3 — "On Target" is a separate axis, not a tier
On-target status (`type_id ∈ {15, 16}`) is tracked independently as the **SoT%** row of the Chain-to-Goal Matrix and the `on_target` flag on each shot — it is *not* emitted as a quality tier by the current code.

---

## 4 — Key Metrics & Definitions

- **Tier 3 — Converted:** the shot was a goal (`type_id == 16`).
- **Tier 2 — Big Chance:** the Opta `Big Chance` qualifier is present on the shot row and it was not scored.
- **Tier 0 — Speculative:** all remaining shots (no goal, no Big Chance qualifier).
- **SoT% (companion metric, not a tier):** share of shots on target (`type_id ∈ {15,16}`).

---

## 5 — Outputs

- **`shot_quality_tiers`** dict in the analyzer result: counts keyed by tier `{0, 2, 3}`.
- **Visual output:** quality-tier distribution chart in the Chance Creation card (and its season-aggregate equivalent).
- **No dedicated parquet column** — tiers are recomputed from `is_goal` and the `Big Chance` qualifier.

---

## 6 — Methodological Decisions & Rationale

- **Qualifier-driven, not xG-threshold-driven:** the Opta `Big Chance` qualifier is first-party data reflecting a clear scoring opportunity; using it directly is more defensible than picking an arbitrary xG cut-off, and it keeps Tier 2 aligned with how Opta itself flags premium chances. The `xg_value` argument is retained in the signature for forward compatibility but does not currently affect the tier.
- **Goal outranks Big Chance:** a converted Big Chance should read as a conversion (Tier 3), not double-count as an unconverted premium chance.
- **On-target handled separately:** keeping SoT% on its own axis avoids collapsing two different quality signals (chance quality vs. execution accuracy) into one ordinal scale.

---

## 7 — Limitations & Known Issues

- **Spec discrepancy (documented, code wins):** the audit brief described a **4-tier** system with a distinct "Tier 1 — On Target". The implementation produces **three** buckets `{0, 2, 3}`; on-target is represented via SoT% / the `on_target` flag, not as a quality tier. This methodology reflects the code. The numbering gap (no Tier 1) is intentional given that On Target is not a tier.
- **Big Chance dependence:** Tier 2 is only as good as Opta's `Big Chance` tagging; matches or seasons with sparse Big Chance qualifiers will show few Tier 2 shots.
- **No xG-based gradation within Tier 0:** a 0.30-xG effort and a 0.02-xG effort both land in Tier 0 unless flagged a Big Chance.

---

## 8 — Relationship to Other Components

- **Upstream:** [xg-model.md](xg-model.md) (xG value, though not used for the tier), the `Big Chance` Opta qualifier.
- **Downstream:** Chance Creation card and its season aggregate ([chance-creation.md](../match-analysis/offensive-phase/chance-creation.md), [opp-season-chance-creation.md](../opponent-analysis/offensive-phase/opp-season-chance-creation.md)); Chances Conceded tier distribution ([chance-conceded.md](../match-analysis/defensive-phase/chance-conceded.md), [opp-season-chances-conceded.md](../opponent-analysis/defensive-phase/opp-season-chances-conceded.md)).
