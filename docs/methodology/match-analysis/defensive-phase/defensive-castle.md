# Defensive Castle (D3) — Methodology

> **Dashboard location:** Match Analysis → Defensive Phase → Defensive Castle
> **Analysis type:** Match-level
> **Primary source file(s):** `analytics/defensive_castle.py`; UI `components/defensive_castle_cards.py`
> **Precomputed parquet(s):** None per match (season aggregate: see [opp-season-defensive-castle.md](../../opponent-analysis/defensive-phase/opp-season-defensive-castle.md)).
> **Last reviewed:** 2026-06-24

---

## 1 — Purpose

The Defensive Castle analyses how a team defends its own defensive third — the "castle" it protects in front of its goal. It profiles the volume, type, and location of defending actions in the deepest zones, distinguishing box defending, deep-flank defending, and defensive-third-edge actions. This tells an analyst how a team holds its low block: where it wins the ball back, which corridors it is forced to defend, and how reliant it is on clearances versus tackles/interceptions.

---

## 2 — Input Data

- **Event types used (`CASTLE_ACTION_IDS`):** `{4 Foul, 7 Tackle, 8 Interception, 12 Clearance, 44 Aerial, 45 Challenge, 49 Ball Recovery, 74 Blocked Pass}`. Fouls count only the committed side (`outcome == 0`). Aerials at `x ≥ 83.33` (opponent box) are excluded as attacking header contests.
- **Qualifiers used:** `outcome` (for fouls); none beyond type/coordinate filtering.
- **Coordinate system:** Opta normalised (0–100), team's own attacking frame. Defensive third = `x < 33.33` (`DEF_THIRD_X_MAX`). Own box: `x ≤ 16.5`, `21 ≤ y ≤ 79`. Deep sub-zone boundary: `x ≤ 16.67`.
- **Seasons covered:** any match with a CSV.
- **Scope:** per-match only.

---

## 3 — Methodology

### 3.1 — Action filtering (`_is_castle_action` + defensive-third gate)
Each team event is kept only if its `type_id` is in `CASTLE_ACTION_IDS`, it passes the foul/aerial guards, and it occurs in the defensive third (`x < 33.33`). Actions outside the defensive third are discarded.

### 3.2 — Corridor classification (`_corridor`)
By y-coordinate: **Left** (`y > 66.67`), **Right** (`y < 33.33`), **Central** (otherwise).

### 3.3 — Sub-zone classification (`_subzone`)
- **box** — inside the own penalty area (`x ≤ 16.5` and `21 ≤ y ≤ 79`).
- **deep_flank** — `x ≤ 16.67` but outside the box (deep wide areas).
- **def_third_edge** — remaining defensive-third area (`16.67 < x < 33.33`).

### 3.4 — Spatial aggregation
Each retained action is also mapped to the 18-zone display grid via `xy_to_zone(x, y)` for the heatmap, and tagged with its action label (`ACTION_LABELS`), corridor, and sub-zone. Counts are accumulated by type, corridor, and sub-zone.

---

## 4 — Key Metrics & Definitions

- **Castle action count (by type):** number of Fouls / Tackles / Interceptions / Clearances / Aerials / Challenges / Ball Recoveries / Blocked Passes in the defensive third.
- **Corridor distribution:** share of castle actions in Left / Central / Right corridors.
- **Sub-zone distribution:** share in box / deep_flank / def_third_edge.
- **Zone heatmap:** count per 18-zone cell within the defensive third.

---

## 5 — Outputs

- **Flat result dict** consumed by `defensive_castle_card()`: action counts by type, corridor breakdown, sub-zone breakdown, zone-count map.
- **Visual outputs:** defensive-third pitch scatter (action points) and a zone heatmap.
- **No parquet** — live per match.

---

## 6 — Methodological Decisions & Rationale

- **Includes the wide action set (incl. clearances, aerials, recoveries):** unlike PPDA, the Defensive Castle is about *all* deep defending activity, so clearances and aerials — central to low-block defending — are deliberately included.
- **Fouls limited to the committed side:** counting only `outcome == 0` ensures a foul is attributed to the team that conceded it, not the team that won it.
- **Box-aerial exclusion (`x ≥ 83.33`):** kept for consistency with the pressing module; in practice the `x < 33.33` defensive-third gate already removes opponent-box aerials, so this is defence-in-depth.
- **Three sub-zones:** separating the penalty box, the deep flanks, and the defensive-third edge mirrors how coaches think about low-block responsibilities (protect the box, manage wide deliveries, screen the edge).

---

## 7 — Limitations & Known Issues

- **Event-only defending:** off-ball positional defending that produces no event is invisible; a perfectly organised block that forces a turnover elsewhere may show few castle actions.
- **Fixed box boundaries:** the own-box rectangle uses Opta-standard fixed coordinates and does not adapt to data noise in event positions.
- **No outcome quality:** the module counts actions but does not weight them by how decisively they ended an attack.

---

## 8 — Relationship to Other Components

- **Upstream:** `goalkeeper_buildup` helpers (`_load_match_events`, `xy_to_zone`), `team_mapping.canonical_name()`.
- **Downstream:** `components/defensive_castle_cards.py`; season-aggregate Defensive Castle ([opp-season-defensive-castle.md](../../opponent-analysis/defensive-phase/opp-season-defensive-castle.md)). Shares action-set and box-aerial conventions with [defensive-pressing.md](defensive-pressing.md).
