# Defensive Structure & Offside Trap — Methodology

> **Dashboard location:** Match Analysis → Defensive Phase → Defensive Structure (offside line, offside trap, structural mirror)
> **Analysis type:** Match-level
> **Primary source file(s):** `analytics/defensive_structure.py` — `analyse_defensive_structure()`, `compute_offside_line()`, `compute_offside_trap()`, `compute_structural_mirror()`; UI `components/defensive_structure_cards.py`
> **Precomputed parquet(s):** None — computed live per match.
> **Last reviewed:** 2026-06-24
>
> *Defensive transitions are computed in this same module (`compute_defensive_transitions`) but are documented separately in [defensive-transitions.md](../transitions/defensive-transitions.md).*

---

## 1 — Purpose

This component describes the *shape* of a team's defending: how high it holds its defensive line, how disciplined/co-ordinated its offside trap is, and — via the "structural mirror" — how the opponent attacked against that structure. It lets an analyst judge whether a team defends with a high, aggressive line that springs offside traps, or a deep, passive block, and where the opponent found space.

---

## 2 — Input Data

- **Event types used:** `type_id == 55` (Offside Provoked) for the line/trap; `analyse_final_third` events (via the mirror). Transition triggers are documented separately.
- **Qualifiers used:** none beyond `type_id`, `x`, `y`, `minute`.
- **Coordinate system:** Opta normalised (0–100), team's own defensive frame. The offside-provoked event is awarded to the **last defender of the defending team**, so its x directly gives the defensive-line height. Height bands via `_x_to_zone_group` (high/mid/low); corridors via `_y_to_corridor` (L `y > 66.67`, R `y < 33.33`, C otherwise).
- **Seasons covered:** any match with a CSV.
- **Scope:** per-match only.

---

## 3 — Methodology

### 3.1 — Offside-event collection (`_get_offside_events`)
Only `type_id == 55` (Offside Provoked) events from the analysed team are used. Each yields `{x, y, minute, source="provoked"}`. The former fallback that reflected the opponent's offside-pass position (`type_id == 2`) was **removed** because `type_id == 2` records the *passer's* position, not the defender's line, producing spurious deep values; every `type_id == 55` is always paired with its `type_id == 2`, so no data is lost.

### 3.2 — Offside line (`compute_offside_line`)
From the provoked-offside x-coordinates:
- **`offside_line_median`** — median x of provoked offsides (line height).
- **`offside_line_variance`** — standard deviation of x (line consistency).
- **First/second-half medians** — split at minute 45 to show how the line dropped or held.
- **`offside_count`** — number of offsides provoked.

### 3.3 — Offside trap (`compute_offside_trap`)
- **`offsides_provoked`** — count.
- **`offside_clustering_index`** — % of offsides whose x is within ±5 of the median (a high value means a co-ordinated, simultaneously-stepping line; a low value means scattered, individually-triggered offsides).
- **Corridor distribution** — L/C/R counts and percentages.
- **Zone distribution** — counts across the 18-zone grid (`xy_to_zone`).
- **Height-zone distribution** — high/mid/low (by x).

### 3.4 — Structural mirror (`compute_structural_mirror`)
Runs the opponent's full-third offensive analysis (`analyse_final_third(match_csv, opponent_name)`) and re-keys every output with an `opp_` prefix: final-third entries, corridor split, entry methods (with dominant method), zone reach (z14, flanks), positive/negative outcomes, average passes/seconds to entry, and possession %. This shows the defending team how the opponent broke them down (see [buildup-final-third.md](../offensive-phase/buildup-final-third.md) for the underlying metrics).

---

## 4 — Key Metrics & Definitions

- **Offside line median (x):** typical defensive-line height when an offside is provoked.
- **Offside line variance (std x):** dispersion of the line height.
- **Offside clustering index (%):** share of offsides within ±5 x-units of the median — a co-ordination measure.
- **Offsides provoked:** total count; broken down by corridor, 18-zone, and height band.
- **Structural mirror (`opp_*`):** opponent's final-third entry profile against this team.

---

## 5 — Outputs

- **Result dict** from `analyse_defensive_structure()` merging line, trap, mirror (and transitions) keys, consumed by `defensive_structure_cards.py`.
- **Visual outputs:** offside-line height indicators (incl. half splits), offside-trap zone/corridor distributions and clustering index, structural-mirror summary of opponent attacks.
- **No parquet** — live per match.

---

## 6 — Methodological Decisions & Rationale

- **`type_id == 55` only for the line:** it is logged on the *last defender*, giving the true line height; using the passer's position (`type_id == 2`) was inaccurate and was deliberately removed.
- **Clustering index via ±5 band:** a simple, interpretable proxy for line co-ordination — a well-drilled trap steps up together so most offsides cluster at one x.
- **Half-split medians:** capture fatigue / tactical line drops between halves.
- **Mirror reuses the offensive pipeline:** rather than re-implement opponent attack analysis, the module calls `analyse_final_third` for the opponent and prefixes the keys, guaranteeing the defensive view and the offensive view use identical definitions.

---

## 7 — Limitations & Known Issues

- **Offside-line height only sampled when an offside is provoked:** a team that never catches anyone offside yields no line estimate (`None`), even if it defends with a high line; the metric is event-conditional, not a continuous line tracker.
- **Small-sample volatility:** with few offsides per match, the median and clustering index are noisy.
- **No tracking data:** the actual back-line position between offside events is not observed; this is an event-derived approximation of structure.
- **Exception-guarded:** each sub-computation falls back to an empty/zeroed dict on error, so missing values should be read as "not computable", not zero.

---

## 8 — Relationship to Other Components

- **Upstream:** `final_third.analyse_final_third` (mirror), `xy_to_zone`, `team_mapping.canonical_name()`.
- **Downstream:** `components/defensive_structure_cards.py`; co-resident with Defensive Transitions ([defensive-transitions.md](../transitions/defensive-transitions.md)).
