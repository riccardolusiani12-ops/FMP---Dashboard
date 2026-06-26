# Goalkeeper Build-up — Methodology

> **Dashboard location:** Match Analysis → Offensive Phase → Goalkeeper Build-up (goal kicks)
> **Analysis type:** Match-level
> **Primary source file(s):** `analytics/goalkeeper_buildup.py` — `analyse_goalkeeper_buildup()`; UI `components/buildup_cards.py`
> **Precomputed parquet(s):** None per match (season aggregate: [opp-season-goalkeeper-buildup.md](../../opponent-analysis/offensive-phase/opp-season-goalkeeper-buildup.md)).
> **Last reviewed:** 2026-06-24

---

## 1 — Purpose

This component analyses how a team builds out from **goal kicks** — whether it plays short into its own defensive third or goes long, where the ball first lands, and whether the team retains possession. It characterises a team's build-up philosophy from dead-ball restarts and how successful that approach is, distinct from open-play build-up.

---

## 2 — Input Data

- **Event types used:** goal-kick passes only — `type_id == 1` (Pass) with the Opta `Goal Kick` qualifier == "Si". The subsequent possession chain uses on-ball play events; `SHOT_EVENTS` (miss, saved shot, goal, save) for outcome.
- **Qualifiers used:** `Goal Kick` (detection, **exclusive**), plus chain/outcome events. Position is *not* used as a filter (defenders frequently take goal kicks).
- **Coordinate system:** Opta normalised (0–100) per-team, attacking left→right. The **18-zone grid** (`xy_to_zone`): rows of 16.67 x-units × columns of 33.33 y-units; Z1–Z3 = own box row, Z16–Z18 = opponent box row.
- **Seasons covered:** any match with a CSV.
- **Scope:** per-match only (goal kicks only — not all GK distributions).

---

## 3 — Methodology

### 3.1 — Goal-kick detection (`_is_goal_kick`)
A row is a goal kick if it is a Pass (`type_id == 1` / event "pass"), belongs to the analysed team, and carries the `Goal Kick == "Si"` qualifier. Detection is **exclusively** on the Opta `Goal Kick` flag — no other distribution type is counted.

### 3.2 — First receiver and short/long classification
`_find_first_receiver` locates the first genuine reception after the goal kick and its 18-zone. The build-up is:
- **Short** — first receiver in `SHORT_ZONES` = Z1–Z6 (own two rows / defensive third).
- **Long** — first receiver in `LONG_ZONES` = Z7–Z18 (everything beyond the defensive third).

### 3.3 — Chain reconstruction & outcome (`_extract_chain_and_outcome`)
Starting from the goal kick, the full event chain is reconstructed. The key principle: **an opponent touch does not automatically mean possession is lost** — after any opponent action the algorithm looks ahead to determine who actually controls the ball next (a constructive team action means possession was retained; an opponent constructive action or a team "lost" event means it changed). "Out" / "Corner Awarded" are resolved by which team gets the restart. The retention window is **15 s measured from the first receiver's touch**.

### 3.4 — Granular outcome levels
The outcome is `positive` (possession kept ≥15 s) or `negative` (lost within 15 s), each with a granular sub-level:
- **Positive P1/P2/P3** — escalating constructiveness of the retained possession (e.g. P3 reaching attacking areas / a corner or shot won).
- **Negative N1/N2/N3** — escalating cost of losing the ball.
The legacy `_classify_outcome` wrapper returns just positive/negative.

### 3.5 — Aggregation
Goal kicks are counted; short/long split and percentages computed; first-receiver zones accumulated into a `{zone: count}` map; per-zone outcome splits (`{zone: {positive, negative}}`); overall outcome counts; and a per-distribution event list (with optional debug trace).

---

## 4 — Key Metrics & Definitions

- **Goal kicks (total):** count of `Goal Kick == "Si"` passes by the team.
- **Short / Long count & %:** split by first-receiver zone (Z1–Z6 vs Z7–Z18).
- **First-receiver zone map:** counts per 18-zone cell.
- **Outcome (positive/negative):** possession retained ≥15 s vs lost within 15 s from first reception.
- **Granular outcome (P1–P3 / N1–N3):** sub-graded retention success / loss severity.
- **Per-zone outcomes:** positive/negative split for each receiving zone.

---

## 5 — Outputs

- **Result dict** (`analyse_goalkeeper_buildup`): `total`, `short_count`, `long_count`, `short_pct`, `long_pct`, `zone_counts`, `zone_outcomes`, `outcome_counts`, `events`, optional `debug_events`.
- **Visual outputs:** 18-zone heatmap of first-receiver locations, short/long summary, granular outcome summary, event-chain visualisation.
- **No parquet** — live per match.

---

## 6 — Methodological Decisions & Rationale

- **Goal-kick-only scope via the Opta flag:** restricting to `Goal Kick == "Si"` gives a clean, comparable population of build-up restarts and avoids conflating open-play GK passes or throws.
- **Position not used as a filter:** modern build-up frequently has a centre-back (not the keeper) take the goal kick, so filtering by player position would drop legitimate goal kicks.
- **Look-ahead possession resolution:** crediting retention only when the team genuinely controls the ball next (not merely the absence of an opponent touch) avoids over/under-counting losses around contested touches, outs, and corners.
- **15 s retention window from first reception:** a consistent, restart-anchored window that captures whether the build-up survived the immediate press.
- **Short vs long by first-receiver zone (not pass length):** the *landing zone* is what tactically defines a short vs long build-up, independent of the exact pass distance.

---

## 7 — Limitations & Known Issues

- **Spec discrepancy (documented, code wins):** the audit brief described a "short / medium / long / mixed" build-up taxonomy. The implementation classifies **short vs long** by first-receiver zone (Z1–Z6 vs Z7–Z18); there is no separate medium/mixed bucket.
- **Depends on Opta `Goal Kick` tagging:** a goal kick not flagged by Opta is missed.
- **Receiver resolution heuristics:** an immediately intercepted goal kick yields no receiver zone and is classified negative.
- **Historical note:** see the retained `GOAL_KICK_BUG_FIX.md` for a prior detection fix.

---

## 8 — Relationship to Other Components

- **Upstream:** the 18-zone grid `xy_to_zone` (defined here and reused app-wide), `_load_match_events`, `team_mapping.canonical_name()`.
- **Downstream:** `components/buildup_cards.py`; season aggregate [opp-season-goalkeeper-buildup.md](../../opponent-analysis/offensive-phase/opp-season-goalkeeper-buildup.md). The `xy_to_zone` / play-event helpers are imported by `defensive_pressing.py` and `defensive_castle.py`.
