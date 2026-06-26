# Attack Origin Classification — Methodology

> **Dashboard location:** Match Analysis → Offensive Phase → Chance Creation (Chain-to-Goal Matrix rows / origin breakdown); reused in the season-aggregate Chance Creation view.
> **Analysis type:** Classification rule (per-shot label)
> **Primary source file(s):** `analytics/chance_creation.py` — `classify_attack_origin()` and the `_check_*` helpers.
> **Precomputed parquet(s):** Origin is derived from shot + possession context; the `is_penalty` boolean column is stored on `shots_{season}.parquet`.
> **Last reviewed:** 2026-06-24

---

## 1 — Purpose

Attack origin classification labels every shot with *how the chance was created* — the tactical pattern that produced it (a through ball, a cross, a high turnover, a set piece, etc.). This turns a flat shot list into a profile of a team's chance-creation style and is the column axis of the Chain-to-Goal Matrix. For a coaching staff it answers "where do our (or our opponent's) good chances come from?".

> **PROTECTED FUNCTION.** `classify_attack_origin()` is a protected classifier and **must not be modified**. Its priority ordering is depended upon across the Chain-to-Goal Matrix, the origin breakdown charts, and the season aggregates; any reordering or predicate change would silently shift historical classifications and break cross-view consistency. Document it — do not edit it.

---

## 2 — Input Data

- **Event types used:** shot events (`type_id ∈ {13,14,15,16}`); within the possession, passes, recoveries (`ball recovery`, `interception`, `tackle`), and dead-ball restart events (`SET_PIECE_EVENTS`). Turnover events (`error`, `dispossessed`) for direct-score detection.
- **Qualifiers used:** `Through ball`, `Pull Back` (Opta qualifier 195 — cut-back), `Cross`, `Individual Play`, and set-piece qualifiers (`Free kick taken`, `Corner taken`, `Direct free`, `Penalty`, `Throw In`, etc.).
- **Coordinate system:** Opta normalised (0–100). Final-third line `FT_X_THRESHOLD = 66.67`; high-regain requires recovery `x ≥ HIGH_REGAIN_X_MIN = 66.67`.
- **Seasons covered:** all (2021/22–2025/26).
- **Scope:** per-shot, evaluated within its possession (and up to several previous possessions via `match_df`).

---

## 3 — Methodology

### 3.1 — Priority-ordered classification
`classify_attack_origin()` evaluates rules in strict priority order and returns the **first** match. The seven possible labels are: **Through Ball, Set Piece, High Regain, Cut Back, Cross, Individual Play, Combination**. Order matters — a shot matching several patterns takes the highest-priority one.

1. **Through Ball** *(highest)* — `_check_through_ball()`: the assisting pass carries the `Through ball` qualifier. First-party data; deliberately ranked above Set Piece so a through ball after a restart is not mis-labelled.
2. **Set Piece** — `_check_set_piece()`: a dead-ball restart within `SET_PIECE_LOOKBACK_SEC = 15 s` and `≤ SET_PIECE_MAX_PASSES = 5` passes before the shot, OR a direct set-piece qualifier on the shot row itself (`_DIRECT_SP_SHOT_QUALS` → unconditional). Penalties always resolve here.
3. **Individual Play** — `_check_individual_play()`: the `Individual Play` qualifier is attached directly to the shot (solo dribble, no assist). Ranked after Set Piece so a direct free kick is never overridden.
4. **High Regain** — `_check_high_regain()`: ball won in the attacking final third (`x ≥ 66.67`) with the shot inside `COUNTER_MAX_SEC = 8 s`. Two cases: (A) explicit recovery event; (B) direct-score turnover where the goal *is* the recovery (opponent error/dispossession at the final-third end). A directionality guard suppresses recoveries that follow an opponent set piece (defensive clearance, not a high press).
5. **Cut Back** — `_check_cut_back()`: a `Pull Back` (qualifier 195) pass within a 12 s lookback. Checked before Cross because a by-line pull-back also matches wide-zone cross detection; the Pull Back qualifier is definitive.
6. **Cross** — `_check_cross()`: a wide-zone final-third pass with a cross qualifier or wide-zone origin.
7. **Combination** *(default)* — patient passing-chain build-up; any shot not matching the above. Shot location (in/out of box) is exposed separately, not via the origin label.

### 3.2 — Multi-possession lookback
Set Piece, High Regain, and direct-score detection search not just the shot's own possession but up to several **previous** possessions via `match_df` and `poss_id`, to handle the common pattern where an aerial duel splits the restart possession from the possession containing the shot.

### 3.3 — Set-piece team filter (`_is_set_piece_event`)
`_is_set_piece_event(row, attacking_team=...)` returns `True` only when the restart event belongs to the *attacking* team (compared via `canonical_name()`). When the opponent takes a restart and the attacking team immediately wins the ball and scores within the 15 s window, the restart is **not** counted as the attacking team's set piece. Both call sites in the classifier pass `attacking_team` through.

### 3.4 — Penalty as a distinct origin (companion to Set Piece)
Penalties are classified as **Set Piece** by the origin rule, but are *also* tracked separately via the `is_penalty` boolean column on `shots_{season}.parquet`, populated by `_check_penalty_in_events()` with the predicate `type_id ∈ {13,14,15,16} AND Penalty == "Si"`, explicitly excluding `type_id == 84` (VAR artefacts). This lets the UI surface a dedicated Penalty card (scored / awarded / conversion) and present a Set Piece origin count that excludes penalties.

---

## 4 — Key Metrics & Definitions

- **Through Ball:** chance from a defence-splitting pass (qualifier-detected).
- **Set Piece:** chance from a dead-ball restart within 15 s / ≤5 passes, or direct set-piece execution. Includes penalties in the origin label (tracked separately via `is_penalty`).
- **High Regain:** chance from a turnover won in the attacking final third, shot within 8 s.
- **Cut Back:** chance from a by-line pull-back (qualifier 195).
- **Cross:** chance from a wide-zone final-third cross.
- **Individual Play:** chance created solo (dribble, no assist).
- **Combination:** default — patient passing build-up not matching the above.

---

## 5 — Outputs

- **Per-shot origin label** (one of the seven), consumed by the Chain-to-Goal Matrix (origin columns) and the origin breakdown donut/bar.
- **`is_penalty`** boolean column on `shots_{season}.parquet`.
- No standalone parquet for origin — recomputed from shot + possession context.

---

## 6 — Methodological Decisions & Rationale

- **Priority over multi-label:** a single dominant origin is more interpretable than a multi-label tag; the ordering encodes which signal is most authoritative when several apply (first-party qualifiers > proximity heuristics).
- **Qualifiers outrank heuristics:** `Through ball`, `Pull Back`, `Individual Play`, and direct set-piece qualifiers are first-party Opta data and are trusted over time-window/zone heuristics.
- **15 s / 5-pass set-piece gate:** a restart played short in the own half and built through many passes should read as open play, not a set piece; the pass-count gate enforces this.
- **8 s high-regain window:** ties the "high regain" label to genuine transition speed rather than slow possession after a recovery.
- **Team filter on restarts:** prevents the forensic mis-attribution where an *opponent's* restart inside the 15 s window caused the attacking team's immediate goal to be wrongly labelled Set Piece (Inter 2025/26: GW13 min 68, GW17 min 64, GW19 min 97). This filter is **implemented and wired through** both call sites.
- **Penalty separated from Set Piece for reporting:** penalties dominate set-piece xG and would distort the open-play picture; the `is_penalty` column lets the UI report them distinctly while keeping the origin taxonomy stable.

---

## 7 — Limitations & Known Issues

- **Spec discrepancies (documented, code wins):**
  - The audit brief listed origins including "Counter Attack" and "Penalty" as separate labels. The implementation's seven labels are **Through Ball, Set Piece, High Regain, Cut Back, Cross, Individual Play, Combination**; counter-attacking chances surface as **High Regain**, and penalties are folded into **Set Piece** (with `is_penalty` tracked separately).
  - The brief described the set-piece team filter as "scoped but not yet applied". It is in fact **implemented and wired through** (the `attacking_team` argument is passed at both call sites). The forensic Inter mis-attributions are addressed.
- **Heuristic origins inherit qualifier gaps:** Cross/High Regain detection depends on coordinates and possession tagging; matches with sparse or noisy event data may mis-route shots into the Combination default.
- **Combination is a catch-all:** it aggregates genuinely varied build-up patterns and should not be read as a single tactical mechanism.

---

## 8 — Relationship to Other Components

- **Upstream:** possession tagging (`poss_id`, `poss_origin`), `team_mapping.canonical_name()` (team filter), the set-piece / through-ball / pull-back qualifiers.
- **Downstream:** `ChanceCreationAnalyzer` Chain-to-Goal Matrix and origin breakdown ([chance-creation.md](../match-analysis/offensive-phase/chance-creation.md)); season-aggregate Chance Creation ([opp-season-chance-creation.md](../opponent-analysis/offensive-phase/opp-season-chance-creation.md)); the Penalty card.
