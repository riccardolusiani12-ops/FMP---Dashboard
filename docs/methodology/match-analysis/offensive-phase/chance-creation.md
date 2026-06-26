# Chance Creation — Methodology

> **Dashboard location:** Match Analysis → Offensive Phase → Chance Creation
> **Analysis type:** Match-level
> **Primary source file(s):** `analytics/chance_creation.py` — `ChanceCreationAnalyzer`, `analyse_chance_creation()`; UI `components/chance_creation_cards.py`
> **Precomputed parquet(s):** Per-match: none (live). Season: `shots_{season}.parquet` (includes `is_penalty`).
> **Last reviewed:** 2026-06-24
>
> *This is the §2-standard methodology. The legacy `CHANCE_CREATION_METHODOLOGY.md` (v1.0) is retained as a longer narrative record.*

---

## 1 — Purpose

Chance Creation is the core offensive analysis: it takes every shot a team took in a match, values it (xG), classifies how it was created (origin), grades its quality (tier), and assembles the **Chain-to-Goal Matrix** that cross-tabulates origins against shot quality. It answers "how many chances did we create, how good were they, and how did we make them?" — the foundation for the offensive-phase narrative and the input that Chances Conceded re-frames defensively.

---

## 2 — Input Data

- **Event types used:** shot events `type_id ∈ {13,14,15,16}` (Miss, Post, Saved, Goal); possession context via `build_possessions`.
- **Qualifiers used:** `Big Chance` (tier), `Penalty` (is_penalty + Set Piece origin), set-piece / through-ball / pull-back / cross qualifiers (origin), plus everything the xG model reads.
- **Coordinate system:** Opta normalised (0–100). Penalty box left edge `x = 83.33`; in-box test via `_is_in_penalty_box`. Final-third line `x = 66.67`.
- **Seasons covered:** all (2021/22–2025/26).
- **Scope:** per-match (analyzer) and season (via `shots_{season}.parquet`).

---

## 3 — Methodology

### 3.1 — Pipeline (`ChanceCreationAnalyzer.analyse`)
1. Prepare events and build possessions (`build_possessions`).
2. Extract all shots for the team (`_extract_shots`), enriching each with xG, xGOT, PV, origin, quality tier, box flag, and `is_penalty`.
3. Count qualifying team possessions (`poss_id` nunique) for rate denominators.
4. Build the Chain-to-Goal Matrix, shot metrics, and quality-tier distribution.
5. Compute integrated High-Regain KPIs (`compute_high_regain_kpis`, see [high-regains.md](../other/high-regains.md)).

### 3.2 — Per-shot enrichment (`_extract_shots`)
For each shot: `xG` via `compute_xg_for_shot` (delegates to the core xG model, [xg-model.md](../../models/xg-model.md)); `on_target = type_id ∈ {15,16}`; `xGOT = estimate_xgot(xG, y, on_target)` (a simplified placement heuristic, on-target only); `PV` via the possession-chain value; `is_big_chance` from the qualifier; **`is_penalty = type_id ∈ {13,14,15,16} AND Penalty == "Si"`** (explicitly excluding `type_id == 84` VAR/setup artefacts); `origin` via `classify_attack_origin` ([attack-origin-classification.md](../../models/attack-origin-classification.md)); `quality_tier` via `classify_shot_quality` ([shot-quality-tiers.md](../../models/shot-quality-tiers.md)); `in_box` via `_is_in_penalty_box`.

### 3.3 — Chain-to-Goal Matrix (`build_chain_to_goal_matrix`)
A matrix of **origins (`ORIGIN_LABELS`: Set Piece, High Regain, Cross, Through Ball, Cut Back, Individual Play, Combination)** × **rows (`MATRIX_ROWS`: N, xG, SoT%, GS)**. Each cell aggregates the shots of that origin: `N` = count, `xG` = summed xG, `SoT%` = % on target, `GS` = goals scored. (PV was removed from the displayed matrix in an earlier revision; the model still computes per-shot PV.)

### 3.4 — Shot metrics (`compute_shot_metrics`)
Totals and shares: shots total, in/out of box, SoT% total, xG per shot, shot frequency per possession (%), in/out-of-box percentages.

### 3.5 — Penalty card (companion to origin row)
Penalties classify as **Set Piece** in the origin matrix but are tracked separately via the `is_penalty` flag (and the `is_penalty` column on `shots_{season}.parquet`). The UI Penalty card sits in the origin row and shows penalties scored, penalties awarded, and conversion rate; after the team-filter fix the Set Piece origin count is reported excluding penalties.

---

## 4 — Key Metrics & Definitions

- **Shots / xG / non-penalty xG:** shot volume and summed expected goals (penalty xG = 0.79; non-pen xG sums the rest).
- **xG per shot:** total xG ÷ shots — average chance quality.
- **SoT%:** share of shots on target (`type_id ∈ {15,16}`).
- **xGOT (display):** simplified expected goals on target for on-target shots (placement heuristic; not the core xG model).
- **Origin breakdown:** counts/percentages across the seven origins (donut/bar).
- **Chain-to-Goal Matrix:** origins × {N, xG, SoT%, GS}.
- **Quality tiers:** distribution across {0 Speculative, 2 Big Chance, 3 Converted}.
- **Penalty card:** penalties scored / awarded / conversion %.

---

## 5 — Outputs

- **Result dict** (`analyse_chance_creation`): `chain_to_goal_matrix`, `shot_metrics`, `shot_quality_tiers`, `shots_detail`, `high_regain_kpis`.
- **`shots_detail`** per shot: origin, x/y, type_id, is_goal, on_target, in_box, xG, xGOT, PV, quality_tier, **is_penalty**, minute/second.
- **Parquet (season):** `shots_{season}.parquet` with the `is_penalty` boolean column.
- **Visual outputs:** shot pitch scatter, Chain-to-Goal Matrix, origin breakdown donut/bar, quality-tier distribution, Penalty card.

---

## 6 — Methodological Decisions & Rationale

- **Shared xG via a thin adapter:** `chance_creation.py` calls `src.utils.xg_model.compute_xg_for_shot`, which delegates to the core `analytics/xg.py` model — one xG definition across the app, with the adapter isolating the call site.
- **Penalty as separate flag, not a separate origin:** keeps the origin taxonomy stable (penalties are Set Piece) while letting the UI report penalty conversion distinctly; the `type_id ∈ {13,14,15,16}` guard with `type_id == 84` exclusion prevents VAR/setup artefacts from inflating penalty counts.
- **Matrix rows N/xG/SoT%/GS:** chosen as additive, season-aggregatable quantities; PV was dropped from the *display* to keep the matrix readable while preserving the model.
- **Possession-based rate denominator:** shot frequency per possession normalises chance creation by how much the ball the team had, rather than raw counts.

---

## 7 — Limitations & Known Issues

- **Origin/tier limitations inherited:** see [attack-origin-classification.md](../../models/attack-origin-classification.md) (Combination catch-all, heuristic origins) and [shot-quality-tiers.md](../../models/shot-quality-tiers.md) (3-tier, Big-Chance-dependent).
- **xGOT is a rough heuristic:** the placement bonus (±0.05/0.15 by y-offset) approximates xGOT and does not reflect true shot speed/placement/GK position; treat it as indicative.
- **No shots → empty output:** teams with zero shots return an empty structure.

---

## 8 — Relationship to Other Components

- **Upstream:** `general_buildup.build_possessions`, [xg-model.md](../../models/xg-model.md) (via `utils/xg_model`), [attack-origin-classification.md](../../models/attack-origin-classification.md), [shot-quality-tiers.md](../../models/shot-quality-tiers.md), [high-regains.md](../other/high-regains.md), PV model, `team_mapping.canonical_name()`.
- **Downstream:** `components/chance_creation_cards.py`; Chances Conceded re-frames this for the opponent ([chance-conceded.md](../defensive-phase/chance-conceded.md)); season aggregate [opp-season-chance-creation.md](../../opponent-analysis/offensive-phase/opp-season-chance-creation.md); `shots_{season}.parquet` consumers.
