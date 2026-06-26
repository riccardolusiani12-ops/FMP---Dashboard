# Set Pieces — Free Kicks — Methodology

> **Dashboard location:** Match Analysis → Set Pieces → Free Kicks
> **Analysis type:** Match-level
> **Primary source file(s):** `analytics/free_kicks.py` — `analyse_free_kicks()`, `_classify_fk_delivery_type()`, `_fk_delivery_outcome_and_chain()`; UI `components/set_piece_cards.py` (FK sections)
> **Precomputed parquet(s):** None — computed live per match.
> **Last reviewed:** 2026-06-24

---

## 1 — Purpose

This component profiles a team's free-kick play: direct shots at goal versus free-kick deliveries into the box, how those deliveries are played (cross, chip, long ball, launch, short), where they land, body part and shot descriptors, and outcomes. It captures a team's set-piece threat from free kicks, separating direct attempts from delivery routines.

---

## 2 — Input Data

- **Event types used:**
  - **Direct FK shot:** `type_id ∈ {13,14,15,16}` with the `Free kick` qualifier (Q26) == "Si", **excluding** penalties (`Penalty`/Q9).
  - **FK delivery (pass):** free-kick pass events into the box.
  - Subsequent events for delivery outcome (`_OPP_DISRUPT_TYPES`, `_OUT_TYPES`, aerial, foul).
- **Qualifiers used:** `Free kick` (Q26), `Penalty` (Q9, exclusion), `Cross`, `Chipped`, `Long ball`, `Launch` (delivery type); zone, goalmouth-zone, body-part, shot-descriptor, miss-direction (Q73/74/75), and delivery qualifier columns.
- **Coordinate system:** Opta normalised (0–100); delivery origin/endpoint via x/y and `Pass End X/Y`.
- **Seasons covered:** any match with a CSV.
- **Scope:** per-match only.

---

## 3 — Methodology

### 3.1 — Direct vs. delivery split
- **Direct FK shots** are shot events tagged `Free kick` (Q26), with penalties excluded. Each is enriched with outcome (`_shot_outcome_from_type`: Goal / Shot on Target / Shot off Target / Hit Post), goalmouth zone, body part, descriptors, and miss-direction qualifiers (only meaningful for misses), and flagged `is_direct_shot = True`.
- **FK deliveries** are free-kick passes into the box, classified by delivery type and tracked through to an outcome.

### 3.2 — Delivery-type classification (`_classify_fk_delivery_type`) — priority
`Cross` → **Crossed into Box**; `Chipped` → **Chipped / Lofted**; `Long ball` → **Long Ball**; `Launch` → **Launch**; otherwise **Short**.

### 3.3 — Delivery outcome (`_fk_delivery_outcome_and_chain`)
Following a delivery, the event chain is scanned: opponent disrupting actions (clearance, interception, GK claim/pick-up, blocked pass) end it as "cleared"; out/corner-awarded end it; a team shot/goal is the productive outcome. Outcomes are accumulated per delivery type.

### 3.4 — Aggregation
Counts of FKs (total), direct shots, deliveries; outcome counts; delivery-type counts and delivery-type × outcome matrix; landing-zone counts; goalmouth-zone counts; body-part and descriptor counts.

---

## 4 — Key Metrics & Definitions

- **Direct FK shots:** free-kick attempts struck directly at goal (penalties excluded), with outcome.
- **FK deliveries:** free-kick passes into the box, by delivery type (Crossed / Chipped / Long Ball / Launch / Short).
- **Delivery × outcome matrix:** outcome breakdown per delivery type.
- **Landing-zone / goalmouth-zone distribution:** where deliveries / direct shots target.
- **Body-part & descriptor counts:** execution detail for direct shots.

---

## 5 — Outputs

- **Result dict** (`analyse_free_kicks`): `free_kicks`, `direct_shots`, `deliveries`, `total`, `outcomes`, `fk_type_counts`, `fk_type_outcomes`, `zone_counts`, `goalmouth_zone_counts`, `body_part_counts`, `descriptor_counts`.
- **Visual outputs:** FK delivery pitch map (origin → destination → outcome), FK direct-shot map (with xG/outcome and goalmouth), FK badge row summarising details.
- **No parquet** — live per match.

---

## 6 — Methodological Decisions & Rationale

- **Penalty exclusion from direct FK shots:** penalties are a distinct set-piece type (handled in Chance Creation's penalty tracking); excluding Q9 keeps the FK view to genuine free kicks.
- **Direct/delivery separation:** a direct strike and a delivery into the box are tactically different set-piece choices, so they are analysed and visualised separately.
- **Qualifier-driven delivery typing:** uses Opta's delivery qualifiers in priority order for reproducibility.
- **Miss-direction only for misses:** Q73/74/75 are only meaningful when the shot missed, so they are read conditionally.

---

## 7 — Limitations & Known Issues

- **Direct/indirect FK is identified via the shot/delivery split, not an explicit "indirect" flag:** an indirect free kick manifests as a delivery (pass) rather than a direct shot; there is no separate indirect-FK qualifier in the pipeline.
- **Delivery outcome is sequence-inferred:** unusual event ordering could mis-label an outcome.
- **No wall/trajectory data:** direct-shot difficulty is not modelled beyond xG and descriptors.

---

## 8 — Relationship to Other Components

- **Upstream:** `team_mapping.canonical_name()`, raw event CSV; xG for direct shots (via the shared model).
- **Downstream:** `components/set_piece_cards.py` (FK sections). Complements [corner-kicks.md](corner-kicks.md) in the Set Pieces tab.
