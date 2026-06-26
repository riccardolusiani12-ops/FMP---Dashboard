# Offensive Phase — Part 2: Build-up to Final Third

This document explains how the **Build-up to Final Third** module works — from Opta raw event data all the way to the dashboard KPIs.

Code reference:
- `dash_app/src/analytics/final_third.py`
- UI card: `dash_app/src/components/final_third_cards.py`
- Pitch visuals: `dash_app/src/components/final_third_pitch.py`

---

## 1) What this phase measures

How a team progresses the ball from its own half into the opponent's final third during a match.

It answers four questions:
1. How often does the team reach the final third?
2. Through which corridor (left / centre / right)?
3. By what method (through ball, long ball, cross, carry, etc.)?
4. Are those entries productive or wasted?

---

## 2) Opta data foundations (F1 event types & F3 qualifiers)

Every metric in this module is built from Opta event-level data.  
Below are the **exact definitions** used, taken from the official F1 and F3 reference files.

### 2a) F1 — Event types used

| ID | Event name | Opta definition | Role in this module |
|----|-----------|-----------------|---------------------|
| 1 | **Pass** | Any pass attempted from one player to another — free kicks, corners, throw-ins, goal kicks and goal assists | Main event for detecting FT entries (via pass endpoint). Also builds the pass chain. |
| 2 | **Offside Pass** | Attempted pass made to a player in an offside position | Treated identically to Pass for entry detection. |
| 3 | **Take On** | Attempted dribble past an opponent | Carry-based FT entry detection (same player, x crosses threshold). |
| 4 | **Foul** | Foul committed resulting in a free kick | Outcome classification (foul by defending team = positive, foul by attacking team = negative). |
| 6 | **Corner Awarded** | Ball goes out for a corner kick | Immediate positive outcome trigger. |
| 7 | **Tackle** | Dispossesses an opponent. Outcome 1 = win & retain, 0 = win but not possession. | Possession-origin for transition_recovery method. |
| 8 | **Interception** | Intercepts a pass between opposition players and prevents it reaching its target. | Possession-origin for transition_recovery method. |
| 12 | **Clearance** | Player under pressure hits ball clear | Not an FT-entry event but is a play event. |
| 13 | **Miss** | Shot on goal which goes wide or over | Immediate positive outcome trigger (shot event). |
| 14 | **Post** | Ball hits the frame of the goal | Immediate positive outcome trigger. |
| 15 | **Saved Shot** | Shot saved (for the shooting player) | Immediate positive outcome trigger. |
| 16 | **Goal** | All goals | Immediate positive outcome trigger; also breaks possession chain. |
| 44 | **Aerial** | 50/50 duel when the ball is in the air | Excluded from box-touch count (duels are not controlled touches). |
| 49 | **Ball recovery** | Team wins possession and keeps it for ≥2 passes or an attacking play | Possession-origin for transition_recovery method. |
| 50 | **Dispossessed** | Player successfully tackled and loses possession | Play event tracked for possession boundaries. |
| 61 | **Ball touch** | Player makes a touch on the ball. Outcome 0 = unsuccessful control, 1 = unintentional. | Carry-based FT entry detection (same player, x crosses threshold). |
| 74 | **Blocked Pass** | Player blocks a pass while already close to the ball | Treated identically to Pass for entry detection via endpoint. |

### 2b) F3 — Qualifier types used

| ID | Qualifier name | Opta definition | How it is used |
|----|---------------|-----------------|----------------|
| **1** | **Long ball** | Long pass over 32 metres (~35 yards) | Entry method classifier: if flag is present OR `Length >= 32`, classify as `long_ball`. |
| **2** | **Cross** | Ball played in from wide areas into the box | Entry method classifier: `cross` (priority 3). Rare as an FT *entry* since most crosses originate inside the FT already. |
| **3** | **Head pass** | Pass made with a player's head | Stored per entry as `head_pass_flag`. Available for sub-type analysis. |
| **4** | **Through ball** | Ball played through for a player making an attacking run to create a chance on goal | Entry method classifier: highest priority (`through_ball`). |
| **5** | **Free kick taken** | Any free kick — direct or indirect | Possession origin detection → `free_kick`. |
| **6** | **Corner taken** | All corners | Possession origin detection → `corner`. |
| **9** | **Penalty** | Penalty kick | Outcome classification (immediate positive). Also set-piece origin. |
| **106** | **Attacking Pass** | Pass in the opponent's half of the pitch | Stored per entry as `attacking_pass_flag`. Not actively empty in current Serie A data. |
| **107** | **Throw In** | Throw-in taken | Possession origin detection → `throw_in`. |
| **124** | **Goal Kick** | Goal kick | Possession origin detection → `goal_kick`. |
| **140** | **Pass End X** | X pitch coordinate for the endpoint of a pass (0–100) | Core to FT-entry detection: if `pass_end_x >= 66.67` and origin `x < 66.67`, entry is detected. |
| **141** | **Pass End Y** | Y pitch coordinate for the endpoint of a pass (0–100) | Determines corridor (Left / Centre / Right) at entry point. |
| **155** | **Chipped** | Pass which was chipped into the air | Stored per entry as `chipped_flag`. Enriches pass sub-type. |
| **156** | **Lay-off** | Pass where player laid ball into the path of a teammate's run | Stored per entry as `lay_off_flag`. |
| **157** | **Launch** | Pass played from own half towards front players, aimed at a zone rather than a specific player | Stored per entry as `launch_flag`. Closely related to long_ball but more directional. |
| **168** | **Flick-on** | Player has "flicked" the ball forward using their head | Stored per entry as `flick_on_flag`. |
| **195** | **Pull Back** | Player in opposition box reaches by-line and passes the ball backwards to a teammate | Stored per entry as `pull_back_flag`. Very rare as an FT entry (origin is already in the box). |
| **196** | **Switch of play** | Any pass crossing the centre zone of the pitch AND > 60 on the y-axis | Entry method classifier: `switch_of_play` (priority 2). |
| **198** | **GK hoof** | Goalkeeper drops the ball on the ground and kicks it long toward a position | GK build-up detection (Phase 1). |
| **199** | **Gk kick from hands** | Goalkeeper kicks ball forward straight out of hands | GK build-up detection (Phase 1). |
| **210** | **Assist** | The pass was an assist for a shot | Stored per entry as `assist` flag. |
| **212** | **Length** | Estimated length the ball has travelled during the event (metres on 0–100 grid) | Used to classify `long_ball` when Opta flag is absent but `Length >= 32`. |
| **213** | **Angle** | Angle the ball travels at, in radians, relative to direction of play | Now loaded (as `angle`). Available for future analysis. |
| **214** | **Big Chance** | Shot deemed by Opta analysts as a clear-cut chance (e.g. one-on-one) | Stored per entry as `big_chance` flag. |
| **215** | **Individual Play** | Player created the shooting chance by himself — not assisted | Stored per entry as `individual_play` flag. |

### 2c) Qualifiers *not* currently used but available in the CSV

These columns exist in the data but are not consumed by the module yet. Noted here for completeness and future work:

- **Volley** (F3 #108) — shot taken as a volley
- **Scramble** (F3 #112) — goal from a scramble situation
- **Regular play** (F3 #22) — shot during open play (not set piece)
- **Fast break** (F3 #23) — shot following a fast-break situation (now loaded as `fast_break`)
- **Blocked** (F3 #82) — shot blocked
- **Related event ID** (F3 #55) — links shots to assists

---

## 3) Core definitions

| Concept | Value | Source |
|---------|-------|--------|
| Final third threshold | `x >= 66.67` | Opta 0–100 scale; 66.67 ≈ 70 m on a 105 m pitch |
| Qualifying possession | duration `>= 10 s` | Filters out very short turnovers |
| Left corridor | `y > 66.67` | Opta y-axis: y=100 is left touchline (broadcast view) |
| Centre corridor | `33.33 <= y <= 66.67` | |
| Right corridor | `y < 33.33` | Opta y-axis: y=0 is right touchline |
| Opposition box | `x >= 83.33` and `21 <= y <= 79` | Approximation of the penalty area |

---

## 4) Data pipeline (step by step)

```
Raw CSV (Opta F1/F3 events)
    │
    ▼
1. _load_match_events()          — renames columns, parses types
    │
    ▼
2. Apply _QUALIFIER_RENAMES      — snake_case all qualifier columns
    │
    ▼
3. build_possessions()           — assigns poss_id, poss_origin, _match_sec
    │
    ▼
4. Filter to selected team
    │
    ▼
5. build_possession_stats()      — possession %, qualifying count
    │
    ▼
6. detect_ft_entries()           — scans each qualifying possession
   │  for x crossing from < 66.67 to >= 66.67
   │  (via pass endpoint OR carry by same player)
    │
    ▼
7. _classify_ft_method()         — priority-based (see §5)
    │
    ▼
8. _classify_outcome()           — scans forward events (see §6)
    │
    ▼
9. analyse_post_ft_zones()       — 10 s window post-entry
    │
    ▼
10. count_box_touches()          — all team touches in opp. box
    │
    ▼
11. compute_ft_metrics()         — aggregates everything into KPIs
```

---

## 5) KPI list and formulas

### A. Possession & volume KPIs

| KPI | Formula | Notes |
|-----|---------|-------|
| **Possession %** | `team_poss_time / total_match_poss_time × 100` | Built from play-event durations only (non-play events excluded) |
| **Qualifying Possessions** | count of team possessions with duration ≥ 10 s | |
| **Total FT Entries** | count of detected crossings from qualifying possessions | |
| **FT Entry %** | `possessions_with_≥1_FT_entry / qualifying_possessions × 100` | Measures conversion efficiency |
| **Avg Passes to FT** | mean of `passes_before_count` across all entries | Indicates build-up tempo |
| **Avg Seconds to FT** | mean of `elapsed_sec` across all entries | |
| **Opp. Box Touches** | count of team events in opp. box (`x ≥ 83.33`, `21 ≤ y ≤ 79`), excluding duels/fouls/non-play | |

### B. Entry distribution KPIs

| KPI | Formula |
|-----|---------|
| **Corridor counts / %** | entries grouped by Left / Centre / Right |
| **Method counts / %** | entries grouped by method (see taxonomy below) |

### Method taxonomy (priority order — first match wins)

| Priority | Method | Detection rule | Opta source |
|----------|--------|---------------|-------------|
| 1 | `through_ball` | Through ball qualifier on entry pass OR last pass in chain | F3 #4 |
| 2 | `switch_of_play` | Switch of play qualifier on entry pass or last pass | F3 #196 — cross-field pass > 60 on y-axis |
| 3 | `cross` | Cross qualifier on entry pass or last pass | F3 #2 — ball from wide area into the box |
| 4 | `set_piece` | Possession origin is set-piece AND entry within 12 s | F3 #5, #6, #9, #107, #124 |
| 5 | `long_ball` | Long ball qualifier OR `Length >= 32` on entry or last pass | F3 #1 |
| 6 | `transition_recovery` | Possession starts from ball recovery / interception / tackle AND entry within 8 s | F1 #49, #8, #7 |
| 7 | `individual_carry` | Same player carries the ball across the FT line (ball touch / take on) | F1 #3, #61 |
| 8 | `combination_play` | A→B→A pattern detected in the pass chain before entry | Inferred from passer/receiver sequence |
| 9 | `short_pass` | Default — none of the above matched | |

### C. Zone reach KPIs (post-entry)

For each entry, the entry zone (where the ball first appears in the FT) is checked:

| KPI | Zone(s) | Description |
|-----|---------|-------------|
| **Zone 14** | Z14 | Central danger zone (x 66.67–83.33, y 33.33–66.67) |
| **Flanks** | Z13, Z15, Z16, Z18 | Wide channels inside the FT |
| **Box** | Z17 | Central penalty area |

### D. Entry outcome KPIs

After each entry, the algorithm scans forward through the full match events.

**Positive** — any of:
- Shot by team (saved shot / miss / post / goal) — F1 #13, #14, #15, #16
- Corner awarded — F1 #6
- Foul committed by opponent (outcome = 0 on opponent's foul row) — F1 #4
- Penalty won — F3 #9
- Team retains possession for **≥ 5 seconds**

**Negative** — any of:
- Team loses possession within **≤ 3 seconds**
- Team commits a foul (attacking foul) — F1 #4
- Opponent gains immediate possession after entry

**Neutral** — no clear trigger in either direction.

Aggregated as:
- `outcomes` — count and % for positive / negative / neutral
- `outcome_by_corridor` — split by L / C / R
- `outcome_by_method` — split by the 9 methods

### E. Pass sub-type flags (stored per entry, not aggregated into KPIs yet)

Each entry record also stores these boolean flags from Opta qualifiers:

| Flag | F3 ID | Meaning |
|------|-------|---------|
| `chipped_flag` | #155 | Pass was lofted / chipped into the air |
| `launch_flag` | #157 | Long pass aimed at a zone (not a specific player) |
| `lay_off_flag` | #156 | Ball laid into the path of a teammate's run |
| `flick_on_flag` | #168 | Headed flick forward |
| `pull_back_flag` | #195 | Cut-back from the by-line |
| `head_pass_flag` | #3 | Pass made with the player's head |
| `attacking_pass_flag` | #106 | Pass in the opponent's half |

These are available for future sub-type breakdowns (e.g., "what % of long-ball entries were launched vs chipped?").

---

## 6) How to read this phase quickly

1. **Volume**: `FT Entry %` + `total_ft_entries` — is the team getting into the final third?
2. **Style**: corridor and method profile — central vs wide, patient vs direct.
3. **Quality**: positive outcome rate — are those entries dangerous or wasted?

Quick benchmarks from Serie A 2025-26 data:
- ~15–35 FT entries per team per match
- Dominant methods are usually `long_ball` and `short_pass`
- Through balls are rare (0–3 per match) but high-value
- Crosses as FT *entries* are rare since most crosses originate inside the FT

---

## 7) Implementation notes

- The card is labelled **Build-up to Final Third**, but it does not hard-exclude set-piece-origin possessions. Instead, entries from set-piece possessions (when the ball reaches FT within 12 s of the restart) are classified as `set_piece` method.

- The `_load_match_events()` function in `goalkeeper_buildup.py` renames only a subset of Opta columns. The `_QUALIFIER_RENAMES` dict in `final_third.py` then adds the remaining qualifier columns needed for this analysis.

- Opta's **Long ball** (F3 #1) definition says "over 35 yards". The code uses `Length >= 32` (Opta units ≈ metres on a 100×100 grid) as a fallback when the flag is missing, which is approximately equivalent.

- The **Through ball** qualifier (F3 #4) is sparsely populated in Serie A data (~1–4 per match across all teams). When the flag is present on a pass but `Pass End X/Y` coordinates are missing, the code infers the endpoint from the next event's position.
