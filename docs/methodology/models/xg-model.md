# xG Model — Methodology

> **Dashboard location:** Cross-cutting model — feeds Match Analysis → Chance Creation / Chances Conceded, Opponent Analysis season aggregates, and Team Overview → xG Summary.
> **Analysis type:** Model (logistic regression)
> **Primary source file(s):** `analytics/xg.py`
> **Precomputed parquet(s):** None directly. The trained model is cached as a pickle at `CACHE_DIR/xg_model.pkl`. Per-shot xG values are written into `shots_{season}.parquet` by the precompute pipeline (see [precompute-pipeline.md](../infrastructure/precompute-pipeline.md)).
> **Last reviewed:** 2026-06-24

---

## 1 — Purpose

The xG (Expected Goals) model assigns every shot a probability of becoming a goal, based on the characteristics of the shot rather than its outcome. It converts a raw shot count into a quality-weighted measure of chance creation and concession, allowing an analyst to separate "how many chances" from "how good were those chances". Every downstream offensive and defensive analysis that talks about chance quality — Chance Creation, Chances Conceded, the season xG summary, and the Playing Style Wheel's non-penalty xG KPIs — is built on this single shared model, so that a shot is valued identically regardless of which view displays it.

---

## 2 — Input Data

- **Event types used:** `type_id` ∈ {13, 14, 15, 16} — Miss, Post, Saved, Goal. A goal is `type_id == 16`.
- **Qualifiers used (as binary features):** `Head`, `Right footed`, `Volley`, `Big Chance`, `1 on 1`, `Fast break`, `From corner`, `Set piece`, `Free kick`, `Individual Play`, plus assist-pass qualifiers `Cross`, `Through ball`, `Pull Back`, `Long ball` read from the shot's `Related event ID`. `Penalty` and `own goal` qualifiers are used to route shots out of the model.
- **Coordinate system:** Opta normalised pitch (0–100 × 0–100). Goal centre at (x=100, y=50). Coordinates are scaled to metres for geometry features using `X_SCALE = 1.05` (m per x-unit) and `Y_SCALE = 0.68` (m per y-unit); goal width `GOAL_WIDTH = 7.32` m.
- **Seasons covered:** All seasons present under `RAW_DATA_DIR/serie_a_*` (2021/22–2025/26). The model is trained on the pooled shot set across every season (~46k shots).
- **Scope:** Both per-match (row-level API) and season-aggregate (batch API).

---

## 3 — Methodology

### 3.1 — Geometry features
Two continuous features are derived from shot location:
- **`distance_to_goal`** — Euclidean distance in metres to the goal centre: `sqrt(((100−x)·1.05)² + ((50−y)·0.68)²)`.
- **`angle_to_goal`** — the visible angle (degrees) subtended by the two goalposts from the shot location: `|arctan2(dy_centre + 3.66, dx) − arctan2(dy_centre − 3.66, dx)|`, where `dx = (100−x)·1.05` and `dy_centre = (50−y)·0.68`. If `dx ≤ 0` the angle is 0.

### 3.2 — Binary qualifier features
Each Opta qualifier column is converted to 0/1 by `_flag()` (`1` if the column is non-null). This yields: `is_header`, `is_right_foot`, `is_volley`, `is_big_chance`, `is_one_on_one`, `is_fast_break`, `is_from_corner`, `is_set_piece`, `is_free_kick`, `is_individual_play`.

### 3.3 — Rebound feature (`is_rebound`)
A shot is flagged a rebound if a preceding shot **by the same team in the same period** occurred within `REBOUND_MAX_SECONDS = 6` seconds. Computed per match in `_enrich_rebound_flag()`. Only available in batch mode (the single-row API sets it to 0).

### 3.4 — Assist-type features
The shot's `Related event ID` is looked up against the full match event table to find the assisting pass. From that pass, four binary features are set: `assist_is_cross`, `assist_is_through_ball`, `assist_is_pull_back`, `assist_is_long_ball`. `is_unassisted` is `1` when the shot has no `Related event ID`. Only available in batch mode.

### 3.5 — Model: logistic regression via custom gradient descent
`XGModel.fit()` standardises each feature (zero mean, unit std, guarded against near-zero variance) and fits a logistic regression with a **hand-rolled gradient-descent solver** — no scikit-learn dependency. Defaults: learning rate `lr = 0.05`, `n_iter = 3000`, L2 regularisation `reg_lambda = 0.005`. The sigmoid is implemented in a numerically stable branched form (`_sigmoid`): `1/(1+e^−z)` for `z ≥ 0`, `e^z/(1+e^z)` otherwise, to avoid overflow. Predictions are clipped to [0.01, 0.99].

### 3.6 — Penalty and own-goal handling (outside the model)
- **Penalties** are excluded from training and assigned a **fixed xG of `PENALTY_XG = 0.79`** at prediction time (both row-level and batch). Routing is by the `Penalty` qualifier being non-null.
- **Own goals** are excluded from training and assigned **xG = 0.0**, routed by the `own goal` qualifier being non-null.

### 3.7 — Training data assembly
`_load_all_shots_for_training()` walks every `serie_a_*/events/*.csv`, extracts shot rows, tags each with its source match file and canonical home/away team names. Penalties and own goals are dropped before fitting. The target is `is_goal = (type_id == 16)`. After fitting, a calibration log line reports total predicted xG vs. total goals (ratio ≈ 1.0 indicates good calibration).

### 3.8 — Freshness fingerprint & caching
The number of raw shot CSVs across all seasons (`_count_shot_csvs()`) is stored alongside the pickled model as a fingerprint. On load, if the current CSV count differs from the cached count the model is **retrained**; otherwise the cached weights are reused. This makes the model self-refresh when a new matchday's CSVs are ingested, without manual intervention.

### 3.9 — Fallback model
If no training data is found, `_fallback_model()` returns a model with hand-calibrated coefficients (e.g. `is_big_chance = +1.50`, `distance_to_goal = −0.08`, intercept `−2.0`) so the dashboard still produces sensible xG values rather than failing.

---

## 4 — Key Metrics & Definitions

- **xG (per shot):** Model probability that the shot results in a goal, in [0.01, 0.99]. Penalties = 0.79, own goals = 0.0.
- **xG (team, for):** Sum of per-shot xG over a team's shots.
- **xGC / xG against:** Sum of per-shot xG over the opponent's shots against the team.
- **xG_diff:** `xG − xGC` at team-season level.
- **distance_to_goal / angle_to_goal:** geometry features (metres, degrees) — see §3.1.

---

## 5 — Outputs

- **Public API:**
  - `compute_shot_xg(row)` — row-level xG for a single shot (no rebound/assist context).
  - `compute_batch_xg(shots_df, all_events_by_match)` — vectorised batch xG with full rebound + assist context. **Preferred** for season-level computation.
  - `load_season_shots(season)` — all shots for a season with `xG`, `is_goal`, canonical `team` columns.
  - `compute_team_xg_summary(season)` — team-season table: `Team, Season, GF, GA, xG, xGC, xG_diff, Shots, ShotsAgainst` (see [xg-summary.md](../team-overview/xg-summary.md)).
- **Model coefficient summary:** `XGModel.summary()` returns raw and standardised coefficients, sorted by absolute magnitude.
- **No parquet written directly** — xG values flow into `shots_{season}.parquet` via the precompute pipeline.

---

## 6 — Methodological Decisions & Rationale

- **Custom gradient-descent solver instead of scikit-learn:** keeps the project dependency-light and avoids the environment-mismatch failure mode that affects the pickled PV model (see [possession-value-model.md](possession-value-model.md)). With 18 features convergence is fast.
- **Penalty xG fixed at 0.79:** penalties have near-constant difficulty independent of the model's spatial features; a fixed value aligned with public Opta references is more reliable than a model prediction, and excluding them from training prevents them from distorting the open-play coefficients.
- **Own goals = 0:** an own goal is not a chance the attacking team created, so it carries no expected-goal value.
- **Feature set limited to event-level qualifiers:** the model deliberately uses only what Opta event CSVs expose. Goalkeeper position, defender positions/pressure, goalmouth clarity (freeze-frame), shot speed/trajectory, and game state are **not available** and therefore not modelled (documented in code).
- **Freshness via CSV count:** a cheap, robust staleness signal — any new match file changes the count and triggers a retrain, so the model never silently goes stale.
- **Prediction clipping to [0.01, 0.99]:** avoids degenerate 0 or 1 probabilities that would break downstream sums and ratios.

---

## 7 — Limitations & Known Issues

- **No freeze-frame / tracking inputs:** the model cannot see defenders or the keeper, so it systematically cannot distinguish a clear sight of goal from a crowded one beyond what the `Big Chance` / `1 on 1` qualifiers capture. This is an inherent ceiling of event-only xG.
- **Single-row API is feature-incomplete:** `compute_shot_xg()` cannot compute rebound or assist-type features (set to 0), so its values differ slightly from the batch API. Season analytics use the batch path; the row API is a backward-compatible convenience only.
- **Penalty value is a flat constant:** all penalties score 0.79 regardless of taker or context.
- **Spec discrepancy (documented, code wins):** the audit brief stated penalty xG = 0.97 and referenced "xGOT estimation logic". The implementation uses **0.79** and contains **no xGOT** computation. This methodology reflects the code.
- **`is_unassisted` vs. data completeness:** shots missing a `Related event ID` are treated as unassisted, which conflates genuinely unassisted shots with shots whose related event was not tagged.

---

## 8 — Relationship to Other Components

- **Upstream:** `team_mapping.canonical_name()` (team-name normalisation for home/away parsing); raw Opta event CSVs; `config.RAW_DATA_DIR` / `CACHE_DIR`.
- **Downstream:**
  - `chance_creation.py` / Chance Creation — shot xG and quality tiers.
  - `chance_conceded.py` / Chances Conceded — xG against.
  - `xg.compute_team_xg_summary()` → Team Overview xG Summary ([xg-summary.md](../team-overview/xg-summary.md)).
  - `playing_style.py` — non-penalty xG per shot and per 90 KPIs ([playing-style-wheel.md](../team-overview/playing-style-wheel.md)).
  - Season offensive aggregates (`season_offensive_summary.py`) and the precompute pipeline.
