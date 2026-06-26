# Set Pieces — Corner Kicks — Methodology

> **Dashboard location:** Match Analysis → Set Pieces → Corner Kicks
> **Analysis type:** Match-level
> **Primary source file(s):** `analytics/corner_kicks.py` — `analyse_corner_kicks()`, `_classify_delivery()`, `_classify_zone_by_coords()`, `_corner_outcome()`; UI `components/set_piece_cards.py`
> **Precomputed parquet(s):** None per match (season aggregate: [opp-season-corner-kicks.md](../../opponent-analysis/set-pieces/opp-season-corner-kicks.md)).
> **Last reviewed:** 2026-06-24

---

## 1 — Purpose

This component profiles a team's corner-kick attacking: how corners are delivered (in-swinger, out-swinger, straight, short), where they target inside and around the box (9-zone goalmouth taxonomy), what defensive setup they face, and what outcomes they produce (goal, shot, cleared, second-phase). It lets an analyst understand a team's set-piece routines and their effectiveness.

---

## 2 — Input Data

- **Event types used:** corner kicks = `type_id == TYPE_PASS` (1) with the Opta `Corner taken` qualifier == "Si". Subsequent events (next ~50 rows) for outcome detection.
- **Qualifiers used:** `Inswinger` (Q223), `Outswinger` (Q224), `Straight` (Q225), `Cross`; defensive-setup qualifiers (e.g. `Both Posts`); `Pass End X` / `Pass End Y` for zone and coordinate fallback.
- **Coordinate system:** Opta normalised (0–100). Box depth `x ≥ 83.33`; 6-yard depth `x ≥ 94.8`; box width `21.1 ≤ y ≤ 78.9`. Near/far post resolved by corner side (`is_left_corner`).
- **Seasons covered:** any match with a CSV.
- **Scope:** per-match only.

---

## 3 — Methodology

### 3.1 — Corner identification
A corner is a Pass (`type_id == 1`) by the analysed team flagged `Corner taken == "Si"`.

### 3.2 — Delivery classification (`_classify_delivery`) — priority
1. **Opta qualifier flags (authoritative):** Inswinger → Outswinger → Straight.
2. **Coordinate fallback** (only when *all* delivery qualifiers are absent — a confirmed Opta tagging gap, video-verified on 2025/26 Serie A): using `Pass End X/Y`, near-flag (`end_x ≥ 93`) → **Short**; front-zone wide byline corridor (`end_x ≥ 83.33` and `end_y` outside box width) → **Short**; outside box depth (`end_x < 83.33`) → **Straight**. Otherwise **Unknown**.

### 3.3 — 9-zone goalmouth taxonomy (`_classify_zone_by_coords`)
The delivery endpoint maps to one of nine zones, relative to the corner side:
- **GA1 / GA2 / GA3** — 6-yard box near / centre / far post (`end_x ≥ 94.8`).
- **CA1 / CA2 / CA3** — penalty-area near / centre / far post (`end_x ≥ 83.33`, inside box width).
- **Edge** — full-width strip just outside box depth (`79.0 ≤ end_x < 83.33`).
- **Front** — near-post wide strip (outside box width).
- **Back** — far-post wide strip.
Near/far post is flipped by `is_left_corner` so the taxonomy is symmetric across sides.

### 3.4 — Defensive setup (`_classify_def_setup`)
Labels the opponent's setup from qualifiers (e.g. Both Posts).

### 3.5 — Outcome classification (`_corner_outcome` + second-phase override)
Scanning the subsequent events, each corner is classified: **goal**, **shot on target**, **shot off target**, **cleared**, or **second_phase** (when no direct shot/goal but the attack continues into a second phase). Own goals from corners are handled distinctly at aggregation (counted in the matrix but excluded from the headline Goals KPI — see season aggregate).

### 3.6 — Aggregation
Per-corner records plus: total corners, outcome counts, delivery-type counts, delivery-type × outcome matrix, 9-zone counts, and defensive-setup counts.

---

## 4 — Key Metrics & Definitions

- **Corners (total):** team `Corner taken` events.
- **Delivery type:** Inswinger / Outswinger / Straight / Short / Unknown.
- **9-zone distribution:** counts across GA1–3, CA1–3, Edge, Front, Back.
- **Outcomes:** goal / shot_on_target / shot_off_target / cleared / second_phase.
- **Delivery × outcome matrix:** outcome breakdown per delivery type.
- **Defensive setup:** opponent setup counts.

---

## 5 — Outputs

- **Result dict** (`analyse_corner_kicks`): `corners`, `total`, `outcomes`, `delivery_counts`, `delivery_outcomes`, `zone_counts`, `def_setup_counts`.
- **Visual outputs:** delivery-type matrix, 9-zone corner-box map, goalmouth figure, corner outcome summary.
- **No parquet** — live per match.

---

## 6 — Methodological Decisions & Rationale

- **Qualifier-first delivery classification:** Opta swing qualifiers are authoritative; the coordinate fallback exists only because a verified tagging gap leaves some corners without any swing qualifier, and video analysis confirmed the endpoint-based rules.
- **9-zone taxonomy relative to corner side:** corners from left and right mirror each other, so near/far post is defined relative to the taking side, keeping zone semantics consistent across sides.
- **Second-phase override:** corners frequently produce danger after the first contact; capturing a `second_phase` outcome avoids under-counting corner threat that doesn't end in an immediate shot.
- **~50-event outcome window:** broad enough to capture the corner's resolution including knock-downs and rebounds.

---

## 7 — Limitations & Known Issues

- **Coordinate fallback is heuristic:** when swing qualifiers are missing, the Short/Straight inference from endpoints is video-validated but still an approximation; ambiguous deliveries fall to **Unknown**.
- **Outcome detection is sequence-based:** an unusual event ordering could mis-attribute the outcome.
- **No delivery-height/trajectory data:** in-swing vs out-swing relies on Opta tags, not ball-flight.

---

## 8 — Relationship to Other Components

- **Upstream:** `team_mapping.canonical_name()`, raw event CSV.
- **Downstream:** `components/set_piece_cards.py`; season aggregate [opp-season-corner-kicks.md](../../opponent-analysis/set-pieces/opp-season-corner-kicks.md) (adds KPI cards, left/right maps, own-goal handling).
