# Offensive Transitions — Methodology

> **Dashboard location:** Match Analysis → Offensive Phase → Offensive Transitions
> **Analysis type:** Match-level
> **Primary source file(s):** `analytics/offensive_transitions.py` — `compute_offensive_transitions()`, `analyse_offensive_transitions()`; UI `components/offensive_transition_cards.py`
> **Precomputed parquet(s):** None per match (season aggregate: [opp-season-offensive-transitions.md](../../opponent-analysis/transitions/opp-season-offensive-transitions.md)).
> **Last reviewed:** 2026-06-24

---

## 1 — Purpose

An offensive transition is the moment a team wins the ball and counter-attacks. This component detects those moments and measures how dangerous the resulting attack became — capturing a team's counter-attacking threat after regaining possession. It is the exact inverse of Defensive Transitions ([defensive-transitions.md](defensive-transitions.md)): same machinery, opposite perspective.

---

## 2 — Input Data

- **Trigger event types:**
  - **Group A (team events — team wins the ball):** `49 Ball Recovery`, `8 Interception`, `7 Tackle` with `outcome == 1`.
  - **Group B (opponent events — opponent loses the ball):** `50 Dispossessed`, `51 Error`, `61 Ball Touch` with `outcome == 0`.
- **Outcome events:** team shots (`13,14,15,16`), corners won, crosses into the box, fouls won in the attacking third.
- **Coordinate system:** Opta normalised (0–100). Map origins filtered to `x ≤ OWN_HALF_MAX = 50` (genuine counters from deep). Attacking third `x ≥ ATT_THIRD_MIN`; box `x ≥ BOX_X`.
- **Seasons covered:** any match with a CSV.
- **Scope:** per-match only.

---

## 3 — Methodology

### 3.1 — Trigger detection
The sorted match is scanned row by row for Group A (team wins) and Group B (opponent loses) triggers — the inverse of the defensive-transition triggers. `total_transitions` is anchored to the team's raw Ball Recovery (`type_id == 49`) count.

### 3.2 — Origin resolution & qualification
- **Group A:** the trigger event's own `x, y` (team player position).
- **Group B:** scan forward to the team's first play event and use those coordinates.
Only origins with `x ≤ 50` are included in the `transition_origins` pitch map (focusing on counters from the defensive/midfield zone), though all triggers count toward `total_transitions`.

### 3.3 — Confirmation window & outcome tiers (P1/P2/P3)
Within `TRANSITION_WINDOW_SEC` after the trigger, the team's events are scanned and the **best** outcome reached classifies the transition:
- **P3 (most dangerous):** team shot, OR a penalty won (box foul drawn).
- **P2:** team won a corner, a free kick in the attacking third, or played a cross into the box.
- **P1:** team's own x reached the attacking third (`x ≥ ATT_THIRD_MIN`), OR retained the ball ≥ 15 s.
- **None:** not confirmed.
The same guards as the defensive module apply (set-piece exclusion via next-possession origin, foul guard, deduplication window).

### 3.4 — Aggregation
Qualified offensive transitions, P1/P2/P3 split, transition rate (qualified ÷ total), reaction times, and origin density (zone/corridor) for the pitch map.

---

## 4 — Key Metrics & Definitions

- **Qualifying offensive transitions:** confirmed counters (team reached danger within the window after a regain).
- **P1 / P2 / P3 outcome tiers:** escalating threat — P1 = territory/retention, P2 = corner/cross/att-third foul won, P3 = shot or penalty won.
- **Transition rate (%):** qualified ÷ total ball recoveries.
- **Reaction time (s):** trigger → first threat event.
- **Origins density map:** where qualifying transitions started (zone/corridor).

---

## 5 — Outputs

- **Result dict** (`analyse_offensive_transitions`): qualified count, P1/P2/P3 counts, transition rate, reaction-time stats, `transition_origins` (map), zone/corridor breakdowns.
- **Visual outputs:** outcome-tier (P1/P2/P3) distribution, origins density map, corridor split.
- **No parquet** — live per match.

---

## 6 — Methodological Decisions & Rationale

- **Exact inverse of defensive transitions:** sharing the detection/confirmation logic guarantees the offensive and defensive transition views are symmetric and use identical thresholds and guards.
- **`x ≤ 50` map filter:** the origins map highlights *counter-attacks from deep*; triggers won high up are less "transition" and more sustained pressure, so they are excluded from the map (but still counted in totals).
- **Ball Recovery as the rate denominator:** anchors the transition rate to a concrete, Opta-selective regain event.
- **"Best outcome" tiering:** a transition is judged by the most dangerous moment it produced (P3 if it ends in a shot).

---

## 7 — Limitations & Known Issues

- **Group B origin reconstruction:** using the team's first forward play event approximates the true win location.
- **Event-only:** counters that never generate a logged team event in the window are not confirmed.
- **Shares all defensive-transition caveats:** set-piece/foul guards and dedup behave identically.

---

## 8 — Relationship to Other Components

- **Upstream:** `general_buildup.build_possessions` (`poss_origin`), `_load_match_events`, `xy_to_zone`, `team_mapping.canonical_name()`.
- **Downstream:** `components/offensive_transition_cards.py`; season aggregate [opp-season-offensive-transitions.md](../../opponent-analysis/transitions/opp-season-offensive-transitions.md). Mirror of [defensive-transitions.md](defensive-transitions.md).
