# Defensive Pressing & PPDA (Match Analysis) — Methodology

> **Dashboard location:** Match Analysis → Defensive Phase → Pressing
> **Analysis type:** Match-level
> **Primary source file(s):** `analytics/defensive_pressing.py`; UI `components/defensive_pressing_cards.py`
> **Precomputed parquet(s):** None — computed live per match from the match CSV (season aggregate is a separate path, see [opp-season-defensive-pressing.md](../../opponent-analysis/defensive-phase/opp-season-defensive-pressing.md)).
> **Last reviewed:** 2026-06-24

---

## 1 — Purpose

This component measures *how aggressively and how high up the pitch* a team presses in a single match. Its headline metric, PPDA (Passes Allowed Per Defensive Action), captures pressing intensity: a low PPDA means the team allows few opponent passes before challenging for the ball. Supporting metrics describe *where* the pressure is applied (height), *which side* (direction), *how often it works* (success rate), and *its spatial footprint* (action heatmap). Together they let an analyst characterise a team's out-of-possession approach for the specific game.

---

## 2 — Input Data

- **Event types used:**
  - **PPDA denominator (`PPDA_ACTION_IDS`):** `{4 Foul, 7 Tackle, 8 Interception, 45 Challenge}` — the narrow industry-standard set. Foul counts only the committed side (`outcome == 0`).
  - **Wide defensive set (`DEFENSIVE_ACTION_IDS`):** `{4, 7, 8, 12 Clearance, 44 Aerial, 45, 49 Ball Recovery, 74 Blocked Pass}` — used for height, direction, success, heatmap, and the displayed "total defensive actions" KPI, but **not** for PPDA.
  - **Opponent passes (`OPPONENT_PASS_IDS`):** `{1 Pass, 2 (offside pass), 74 Blocked Pass}`; a throw-in (`Throw In` qualifier on a `type_id == 1`) also counts.
- **Qualifiers used:** `Long ball`, `Length` (long-ball exclusion variant), `Throw In`.
- **Coordinate system:** Opta normalised (0–100). Opponent x is reflected to the pressing frame via `x_att = 100 − x_opp`. Pressing-zone bounds: overall `x_att ≤ 60`, high press `≤ 33.33`, mid press `33.33 < x_att ≤ 60`.
- **Seasons covered:** any match with a CSV.
- **Scope:** per-match only.

---

## 3 — Methodology

### 3.1 — PPDA computation (`compute_ppda`)
PPDA = opponent passes in the pressing zone ÷ team defensive actions in the same zone. Four variants are produced:
- **`ppda_overall`** — zone `x_att ≤ 60`.
- **`ppda_high`** — high-press zone `x_att ≤ 33.33` (opponent's own third).
- **`ppda_mid`** — mid zone `33.33 < x_att ≤ 60`.
- **`ppda_overall_excl_long`** — overall, excluding opponent long balls from the numerator (a long ball is the `Long ball` qualifier or `Length ≥ 32`).

The **denominator** uses only `PPDA_ACTION_IDS` (tackles + interceptions + fouls + challenges) mapped to the same pressing zone in the team's own attacking frame (`x ≥ 100 − zone_bound`, e.g. `x ≥ 40` for the overall zone). A zero denominator yields `None` (not displayed).

### 3.2 — Pressing height (`compute_pressing_height`)
Using the **wide** defensive set, actions are bucketed by the team's attacking x: High press (`x ≥ 66.67`), Mid (`33.33–66.67`), Low block (`x < 33.33`). The output describes the share/centroid of where defending occurs.

### 3.3 — Pressing direction (`compute_pressing_direction`)
Defensive actions are split by corridor on the y-axis: Left (`y > 66.67`), Central, Right (`y < 33.33`), indicating which flank the team funnels/presses toward.

### 3.4 — Pressing success (`compute_pressing_success`)
A press is "successful" when the defensive action is followed within `PRESS_SUCCESS_SEC = 10 s` by the team regaining/retaining the ball (per the event sequence). The success rate is successful presses ÷ total presses.

### 3.5 — Action heatmap (`compute_action_heatmap`)
Defensive actions (wide set) are aggregated into the 18-zone display grid (`xy_to_zone`) to produce a `{zone: count}` heatmap of pressing activity.

### 3.6 — Aerial-in-box exclusion
Aerial duels (`type_id == 44`) at `x ≥ 83.33` (opponent's box) are *attacking* header contests from corners/crosses, not defending — they are excluded from defensive counts.

---

## 4 — Key Metrics & Definitions

- **PPDA (overall/high/mid):** opponent passes ÷ team {tackles+interceptions+fouls+challenges} in the pressing zone. Lower = more intense pressing.
- **PPDA excl. long:** as overall, removing opponent long balls from the numerator (a team cannot "press" a long ball over the top).
- **Pressing height:** distribution of defensive actions across High/Mid/Low thirds.
- **Pressing direction:** distribution across Left/Central/Right corridors.
- **Pressing success rate:** % of defensive actions followed by a regain within 10 s.
- **Total defensive actions:** count over the wide `DEFENSIVE_ACTION_IDS` set (full pitch) — the Section-A KPI.

---

## 5 — Outputs

- **KPI values:** `ppda_overall`, `ppda_high`, `ppda_mid`, `ppda_overall_excl_long`, raw numerators/denominators, `total_def_actions`.
- **Visual outputs:** pressing-height summary, direction split, success rate, PPDA scatter and bar figures, action heatmap (18-zone).
- **No parquet** — live per match.

---

## 6 — Methodological Decisions & Rationale

- **Narrow PPDA denominator (tackles + interceptions + fouls + challenges only):** this is the industry-standard PPDA definition (StatsBomb / Wyscout / Opta). **Clearances** are reactive last-ditch actions, not pressing; **aerials** are duels not ground pressure; **ball recoveries** are loose-ball pickups that inflate the denominator and would understate pressing intensity; **blocked passes** are passive interventions. Each is therefore excluded. Ball recoveries are reserved for the Team Overview PPDA variant (see [ppda-team-overview.md](../../team-overview/ppda-team-overview.md)).
- **Opponent-x reflection (`100 − x`):** PPDA is defined in terms of how deep the team presses into the opponent's build-up, so opponent coordinates are mirrored into a common pressing frame.
- **Long-ball exclusion variant:** a long ball over the press is not a pass the defence "allowed" by failing to press, so an alternative PPDA removes them for a fairer pressing read.
- **Wide set for descriptive metrics:** height/direction/success/heatmap aim to describe *all* defensive activity, so they intentionally use the broader action set the PPDA denominator excludes.
- **Box-aerial exclusion:** prevents corner/cross header contests from being mistaken for high pressing.

---

## 7 — Limitations & Known Issues

- **Event-only pressing:** without tracking data, "pressing" is inferred from where defensive *events* occur, not from off-ball pressure that never results in an event; passive containment is undercounted.
- **Success heuristic:** the 10 s regain window is a proxy; a press that forces a hurried clearance the team does not recover is not counted as successful.
- **Zero-denominator zones:** in low-activity zones PPDA can be `None`; the UI must handle missing values.
- **Throw-in handling:** only throw-ins tagged on a `type_id == 1` pass are counted as opponent passes.

---

## 8 — Relationship to Other Components

- **Upstream:** `goalkeeper_buildup` helpers (`_load_match_events`, `xy_to_zone`, play-event filters), `general_buildup.build_possessions`, `team_mapping.canonical_name()`.
- **Downstream:** `components/defensive_pressing_cards.py` (UI); the season-aggregate pressing view ([opp-season-defensive-pressing.md](../../opponent-analysis/defensive-phase/opp-season-defensive-pressing.md)) and Team Overview PPDA ([ppda-team-overview.md](../../team-overview/ppda-team-overview.md)) are related but use different aggregation/denominator choices.
