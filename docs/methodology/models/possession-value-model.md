# Possession Value Model (GPA) — Methodology

> **Dashboard location:** Cross-cutting model — feeds High Regains PV, Player Analysis PVA, and chain-value computations used in build-up / final-third analyses.
> **Analysis type:** Model (empirical grid + ML regressor)
> **Primary source file(s):** `analytics/possession_value.py`; trainer `models/train_pv_model.py`; pickled artefact `models/pv_model_serie_a.pkl`.
> **Precomputed parquet(s):** None — the model is a pickle (`CACHE_DIR/pv_model_gpa.pkl`, legacy `pv_model.pkl`). PV deltas are computed live and surfaced through per-action / per-match aggregates.
> **Last reviewed:** 2026-06-24
>
> *Note: this file is the §2-standard methodology for the current implementation. The pre-existing `possession_value_model.md` (Italian, v2.0) and `POSSESSION_VALUE_DESIGN.md` are retained as background/design records.*

---

## 1 — Purpose

The Possession Value (PV) model quantifies how much each on-ball action changes a team's probability of scoring. It implements Ian Graham's **Goal Probability Added (GPA)** idea: every pitch location carries a goal probability, and the value an action adds is the change in that probability between the state before and the state after the action. This lets the dashboard answer "which players and which sequences moved the ball into more dangerous situations", independent of whether a shot or goal actually followed — the basis for the High Regains PV figures and the Player Analysis Possession Value Added (PVA) metrics.

---

## 2 — Input Data

- **Event types used:** on-ball actions in `ON_BALL_EVENTS` (pass, ball touch, take on, ball recovery, clearance, miss, saved shot, goal, blocked pass, dispossessed, interception, aerial, tackle, offside pass). Shots are `SHOT_TYPE_IDS = {13,14,15,16}`. `NON_PLAY_EVENTS` (admin events, cards, delays, formation changes) are skipped during chain/possession construction.
- **Qualifiers / situation:** possessions are tagged with a game-situation code via `_SITUATION_MAP` (open_play=0, corner=1, free_kick=2, throw_in=3, penalty=4, goal_kick=5, gk_hands=6).
- **Coordinate system:** Opta normalised pitch (0–100 × 0–100), x = own goal → opponent goal.
- **Seasons covered:** all matches under `RAW_DATA_DIR/serie_a_*` (2021/22–2025/26).
- **Scope:** model trained once across the full corpus; applied per-action / per-chain at runtime.

---

## 3 — Methodology

### 3.1 — Pitch grid
The pitch is divided into a **16 × 12 grid** (`X_ZONES = 16`, `Y_ZONES = 12`): 16 columns of 6.25 x-units each, 12 rows of ≈8.33 y-units each. `get_xt_zone(x, y)` maps a coordinate to a `(col, row)` cell. This 16×12 grid is the PV/xT taxonomy and is **distinct from** the 18-zone display grid used in the UI (see §6).

### 3.2 — Two parallel estimators
The model provides two estimators sharing one API:

1. **Empirical grid (`goal_prob_grid`, aliased `xT`)** — a direct frequency ratio `P(goal | zone)` computed over the whole training corpus. Always available, zero-cost, fully transparent. This is the **primary lookup** used downstream via `get_xT()` / `get_gpa()`.
2. **ML regressor** — supervised models predicting `P(goal within the current possession)` from per-action features. Both **Logistic Regression** (interpretable cross-check) and **LightGBM** (primary, when installed) are trained. Feature set (`_FEATURE_COLS`): `zone_col, zone_row, situation, seconds_elapsed, is_home, pass_forward, is_shot, dist_to_goal`.

### 3.3 — Empirical grid construction
During `build()`, for every match the events are normalised, possessions are tagged (`_tag_possessions`), and counters are accumulated per zone: possessions, possessions that led to a goal, shots, and goals. `_finalise_empirical_grid()` then computes:
- **`goal_prob_grid`** = `(goal_poss_counts + α) / (poss_counts + β)` with Laplace smoothing `α = 1.0`, `β = 50.0` (a ~2% baseline prior that stabilises low-traffic zones).
- **`P_shot`** = `(shot_counts + 0.5) / (actions + 10.0)`.
- **`P_goal`** = `(goal_counts + 0.1) / (shot_counts + 1.0)`.

### 3.4 — ML training
`_train_ml()` fits the two classifiers on the pooled action records with target `poss_leads_to_goal`:
- **LogisticRegression** — `max_iter=500`, `solver="lbfgs"`, `class_weight="balanced"`, `C=1.0`, `random_state=42`.
- **LGBMClassifier** — `n_estimators=300`, `max_depth=6`, `learning_rate=0.05`, `num_leaves=31`, `min_child_samples=50`, `subsample=0.8`, `colsample_bytree=0.8`, `class_weight="balanced"`. If LightGBM is not installed, this estimator is skipped (LR remains).

### 3.5 — Chain PV (the GPA computation)
`get_chain_pv(chain)` computes the value added along an ordered sequence of actions:
- **New (telescoping) mode:** `PV = P(goal | last location) − P(goal | first location)`, i.e. the net change in goal probability across the chain.
- **Legacy mode** (`ft_entry_time` supplied): accumulates only *positive* per-pass `xT` deltas from the final-third entry time onward (preserved for older callers).
`get_chain_pv_from_raw_events()` does the same starting from a raw event DataFrame. `predict_gp(...)` exposes the ML estimator directly for a single feature vector (`model="lgb"` or `"lr"`).

### 3.6 — Loading & fallback (`get_pv_model`)
Load order: (1) in-memory cache; (2) new GPA pickle `pv_model_gpa.pkl`; (3) legacy pickle `pv_model.pkl`; (4) **fallback hand-calibrated grid** (`_fallback_xt_grid()`), which is instant and always works. **Building is never triggered during dashboard use** — it must be run explicitly via `python -m src.analytics.possession_value --build`.

---

## 4 — Key Metrics & Definitions

- **GPA / xT (per zone):** `P(goal | zone)` — empirical, smoothed goal probability for the 16×12 cell containing a location.
- **Chain PV:** net change in goal probability across an action sequence (telescoping), or sum of positive deltas (legacy mode).
- **PVA (Possession Value Added):** per-player / per-team accumulation of chain PV over a match (computed in `player_analysis.py`, offensive and defensive totals).
- **`predict_gp`:** ML estimate of `P(goal within possession)` for a single action's features.

---

## 5 — Outputs

- **Lookups:** `get_xT(x,y)`, `get_gpa(x,y)`, `predict_gp(...)`.
- **Chain value:** `get_chain_pv(chain)`, `get_chain_pv_from_raw_events(df)`.
- **Grids (post-build):** `goal_prob_grid` / `xT` (16×12), `P_shot` (16×12), `P_goal` (16×12).
- **Artefacts:** `pv_model_gpa.pkl` (model + grids + estimators). Visual diagnostics in `models/`: `pv_calibration_curve.png`, `pv_feature_importance.png`, `pv_model_heatmap.png`.
- **No parquet** — values are consumed live by `high_regains.py` and `player_analysis.py`.

---

## 6 — Methodological Decisions & Rationale

- **Empirical grid as the primary estimator:** transparent and always available; the ML models are a refinement/cross-check rather than the default lookup, avoiding hard ML dependencies on the hot path.
- **Laplace smoothing (α=1, β=50):** prevents sparse zones (e.g. wide defensive corners with few possessions) from producing unstable or zero goal probabilities; β=50 encodes a ~2% baseline prior.
- **16×12 grid vs. 18-zone display grid:** the PV model uses a fine 16×12 grid for goal-probability resolution, whereas the UI heatmaps (`components/pitch_zones.py`) use a coarse 6-column × 3-row = 18-zone grid for human-readable display. These are **separate taxonomies**: the 18-zone grid is never used for PV lookups, and the 16×12 grid is never rendered directly. Downstream code that needs a displayed zone uses the 18-zone helper; code that needs goal probability uses `get_xt_zone` on the 16×12 grid.
- **Build is CLI-only:** training scans the full corpus and is expensive, so it is deliberately excluded from the runtime load path; the dashboard always loads a pre-built pickle or the fallback.
- **LightGBM optional:** the model degrades gracefully to LR-only (and then to the empirical grid) so missing optional dependencies never break the dashboard.

---

## 7 — Limitations & Known Issues

- **Silent ML failure mode (scikit-learn / LightGBM environment mismatch):** if the pickled estimators were trained under a different sklearn/LightGBM version, unpickling or prediction can fail. The load path catches exceptions and falls back to the empirical grid or the hand-calibrated fallback grid; the consequence is that `predict_gp` / ML-based values may silently revert to grid-based or fallback values rather than the trained ML output. This is logged as a warning but produces no user-facing error — analysts should treat a sudden flattening of PV values as a signal to check the model load logs and rebuild. The empirical grid path is unaffected by this.
- **Fallback grid is coarse:** when no cache is present the hand-calibrated grid is used, which is directionally correct but not data-fitted.
- **Telescoping chain PV ignores the path:** the new-mode chain value depends only on the first and last locations, not the route taken; a long progressive carry and a single long pass to the same endpoint score identically.
- **Possession tagging heuristics:** possession boundaries and situation codes are derived from event sequences and inherit any Opta tagging gaps.

---

## 8 — Relationship to Other Components

- **Upstream:** raw Opta event CSVs; `config.RAW_DATA_DIR` / `CACHE_DIR`; optional `scikit-learn` / `lightgbm`.
- **Downstream:**
  - `high_regains.py` — PV generated by high-regain sequences ([high-regains.md](../match-analysis/other/high-regains.md)).
  - `player_analysis.py` — per-player PVA offensive/defensive totals ([player-analysis.md](../opponent-analysis/player-analysis/player-analysis.md)).
  - Chain-value usage in build-up / final-third chain reconstructions.
- **Sibling display system:** `components/pitch_zones.py` (18-zone heatmaps) — independent taxonomy, see §6.
