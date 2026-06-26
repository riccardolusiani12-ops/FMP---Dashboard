# Defensive Transitions — Methodology

> **Dashboard location:** Match Analysis → Defensive Phase → Defensive Transitions
> **Analysis type:** Match-level
> **Primary source file(s):** `analytics/defensive_structure.py` — `compute_defensive_transitions()`; UI `components/defensive_structure_cards.py`
> **Precomputed parquet(s):** None per match (season aggregate: [opp-season-defensive-transitions.md](../../opponent-analysis/transitions/opp-season-defensive-transitions.md)).
> **Last reviewed:** 2026-06-24

---

## 1 — Purpose

A defensive transition is the moment a team loses the ball in the attacking half and the opponent counter-attacks. This component detects those moments and measures how dangerous the resulting opponent attack became — capturing a team's vulnerability when caught out of shape after losing possession high up the pitch. It is the defensive mirror of Offensive Transitions ([offensive-transitions.md](offensive-transitions.md)).

---

## 2 — Input Data

- **Trigger event types:**
  - **Group A (opponent events — opponent gains the ball):** `49 Ball Recovery` (primary), `8 Interception`, `7 Tackle` with `outcome == 1`.
  - **Group B (team events — our player loses the ball):** `50 Dispossessed`, `51 Error`, `61 Ball Touch` with `outcome == 0`.
- **Confirmation / outcome events:** shots (`13,14,15,16`), `6 Corner`, crosses (`Pass` with `Cross` qualifier and `Pass End X ≥ box`), opponent positional events.
- **Excluded triggers:** `5 Out`, `6 Corner` (as trigger), `2 Offside Pass`, `9 Turnover` (deprecated), `4 Foul victim`, `44 Aerial`, `45 Challenge` (contested duels via `DEFENSIVE_LOSS_TYPE_IDS`), `52 GK pick-up`, all shots.
- **Coordinate system:** Opta normalised. Loss must originate at `origin_x ≥ ATTACKING_HALF_MIN = 50` (team's frame). Opponent confirmation at raw `x ≥ OPP_ATT_THIRD_MIN = 66.67`. Box `x ≥ BOX_X`, box y-band `OPP_BOX_Y_MIN..MAX`.
- **Scope:** per-match only.

---

## 3 — Methodology

### 3.1 — Trigger detection (row-scan, not possession-pair)
`compute_defensive_transitions` scans every row of the sorted match (`[period, _match_sec, event_id]`) and flags Group A / Group B triggers individually. This replaced an earlier possession-boundary approach that fragmented counters and missed team-side losses (`Dispossessed`/`Error` are logged on the *team's* rows).

### 3.2 — Origin resolution & filtering
- **Group B:** the loss location is the trigger event's own `x, y`.
- **Group A:** scan backwards for the last team play event in the same period; use its `x, y`.
- Discard if `origin_x < 50` (must start in the attacking half), if the origin is a contested duel / shot, or if coordinates are out of bounds.

### 3.3 — Guards
- **Set-piece exclusion:** if the opponent's next possession `poss_origin` is a set piece (corner, free_kick, throw_in, goal_kick, penalty, gk_hands), skip — the loss led to an organised restart, not a transition.
- **Foul guard:** if the opponent committed a foul within `FOUL_GUARD_SEC = 3 s` before the trigger, the ball wasn't genuinely won (free kick coming) — skip.
- **Deduplication:** if a confirmed transition was recorded within `DEDUP_WINDOW_SEC = 30 s`, skip (same counter episode).

### 3.4 — Confirmation window & outcome tiers
For each trigger, scan `[trigger_sec, trigger_sec + TRANSITION_WINDOW_SEC = 25 s]`. A transition is **confirmed** when the opponent reaches their attacking third (raw `x ≥ 66.67`). The worst (most dangerous) outcome reached classifies it:
- **N3 (most dangerous):** opponent shot, OR a penalty/box-foul conceded by the team in the window.
- **N2:** opponent corner won in the final third, OR a cross into the box, OR a team foul conceded in the final third.
- **N1:** opponent merely reached the final third (`x ≥ 66.67`), OR retained possession ≥ 15 s.
- **None:** not confirmed / non-qualified (discarded from rates).

**Reaction time** is the time from trigger to the first outcome-flag event (capped at the 25 s window). **Counter-press response** (`team_first_press_sec`) is the time to the team's first defensive action (`COUNTER_PRESS_ACTION_IDS`) after the loss.

### 3.5 — Aggregation
Counts of qualified transitions and N1/N2/N3 splits; **transition rate** = qualified ÷ total losses (%); average reaction time; zone-group (high/mid/low) and corridor (L/C/R) breakdowns of origin locations.

---

## 4 — Key Metrics & Definitions

- **Qualified defensive transitions:** confirmed counters conceded (opponent reached the final third within 25 s of a high loss).
- **N1 / N2 / N3 outcome tiers:** escalating danger — N1 = territory/retention, N2 = corner/cross/final-third foul, N3 = shot or box-foul/penalty conceded.
- **Transition rate (%):** qualified ÷ total possession losses in the attacking half.
- **Reaction time (s):** trigger → first danger event.
- **Counter-press response (s):** trigger → team's first defensive action.
- **Zone-group / corridor distribution:** where losses that became transitions originated.

---

## 5 — Outputs

- **Result dict** merged into `analyse_defensive_structure()`: qualified count, N1/N2/N3 counts, transition rate, mean reaction time, zone/corridor breakdowns, per-transition records.
- **Visual outputs:** outcome-tier distribution, origin density/zone map, corridor split.
- **No parquet** — live per match.

---

## 6 — Methodological Decisions & Rationale

- **Row-scan over possession pairs:** the possession engine can fragment a single counter into multiple IDs and logs some losses (`Dispossessed`, `Error`) on the team's own rows; scanning individual trigger events is more precise and complete.
- **`Ball Recovery` as primary trigger:** Opta only logs it when the recovering team keeps the ball ≥2 passes or sustains an attack — the most selective signal of a genuine turnover.
- **Tackle/Ball-Touch outcome gating:** `Tackle` counts only with confirmed retention (`outcome == 1`); `Ball Touch` only as a failed control (`outcome == 0`) — avoiding contested or accidental contacts.
- **Set-piece and foul guards:** ensure only *open-play* transitions are counted; a loss that becomes a free kick or corner is organised defending, not a transition vulnerability.
- **"Worst outcome" tiering:** a transition is judged by the most dangerous moment it produced, so a counter that ends in a shot is N3 even if it also passed through N1/N2 stages.
- **25 s window / 30 s dedup:** long enough to capture a developing counter, with dedup preventing a single sustained episode from being counted multiple times.

---

## 7 — Limitations & Known Issues

- **Spec discrepancy (documented, code wins):** the audit brief referred to P1/P2/P3 tiers; the implementation uses **N1/N2/N3** (N for the *negative*/conceded perspective). Definitions are as above.
- **Origin coordinate for Group A is reconstructed** from the preceding team event, which can be slightly off if the last play event was distant.
- **Event-only:** off-ball recovery runs and pressing that prevents a counter without an event are invisible.
- **Exception-guarded:** returns an empty/zeroed dict on error.

---

## 8 — Relationship to Other Components

- **Upstream:** `general_buildup.build_possessions` (`poss_origin`), `_is_play_event`, `xy_to_zone`, `team_mapping.canonical_name()`.
- **Downstream:** `components/defensive_structure_cards.py`; season aggregate ([opp-season-defensive-transitions.md](../../opponent-analysis/transitions/opp-season-defensive-transitions.md)). Mirror of [offensive-transitions.md](offensive-transitions.md).
