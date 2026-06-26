# Possession Value (PV) Model — Design Document

## 1-Paragraph Summary Recommendation

**We recommend extending the existing xT-based `PossessionValueModel` (already in `possession_value.py`) into a _context-enriched xT_ approach that layers Entry Method categories and High Regain flags on top of the existing zone-based xT grid.** Rather than replacing the proven iterative Markov-chain xT with a complex supervised learning model, we propose: (a) keeping the 16×12 xT grid as the backbone for action-level PV scoring, (b) building a lightweight LightGBM "PV Uplift" model that predicts **P(goal | possession state)** using features derived from the dashboard's own KPIs (Entry Method, location zone, sequence length, High Regain flag, set-piece boolean, time elapsed), and (c) defining PV-Added per action as the change in predicted goal probability before/after each action. This hybrid approach gives interpretability (zone-based heatmaps) plus context sensitivity (Entry Method matters), requires only event-level data (no tracking), trains in seconds on a laptop, and produces outputs compatible with the existing Chain-to-Goal Matrix and dashboard visuals.

---

## 2. Repo Reconnaissance — Files Inspected

| # | File | Purpose | Key functions/classes |
|---|------|---------|---------------------|
| 1 | `dash_app/src/analytics/possession_value.py` (648 lines) | **Zone-based xT model** (16×12 grid). Builds P_shot, P_goal, transition matrix, iterates xT. Provides `get_xT()`, `get_chain_pv()`, `get_chain_pv_from_raw_events()`. Cached to disk. | `PossessionValueModel`, `get_pv_model()`, `get_xt_zone()` |
| 2 | `dash_app/src/analytics/chance_creation.py` (836 lines) | **Phase 3: Chance Creation**. Classifies shot attack origins (Set Play, Counter, Through, Cross, Out Box), builds Chain-to-Goal Matrix (PV/xG/xGOT/GS × origin), computes shot metrics. | `ChanceCreationAnalyzer`, `classify_attack_origin()`, `build_chain_to_goal_matrix()` |
| 3 | `dash_app/src/analytics/final_third.py` (968 lines) | **Phase 2: Build-up to Final Third**. Detects FT entries, classifies Entry Method (8 types: through_ball, switch_of_play, set_piece, long_ball, transition_recovery, individual_carry, combination_play, short_pass), classifies outcomes, post-FT zone analysis. | `analyse_final_third()`, `detect_ft_entries()`, `_classify_ft_method()`, `_classify_outcome()` |
| 4 | `dash_app/src/analytics/general_buildup.py` (662 lines) | **Possession chain builder** (shared). Assigns `poss_id` by team change, period change, goal, set-piece restart. Open-play filtering, origin detection. | `build_possessions()`, `_is_set_piece()`, `_detect_origin()` |
| 5 | `dash_app/src/analytics/goalkeeper_buildup.py` | **Phase 1: GK Build-up**. Shared helpers: `_load_match_events()`, `xy_to_zone()`, `_is_play_event()`, `_is_same_team()`, `_elapsed_seconds()`. 18-zone grid. | Zone helpers, event loading |
| 6 | `notebooks/01_high_regains.ipynb` (729 lines, 8 cells) | **High Regains** analysis. Loads events, standardizes schema, tags open/set play, normalizes attack direction, filters `Ball recovery` events with `x ≥ 66.7`, builds league table, links regains → first shot within N seconds, visualizes on pitch. | `build_high_regains_df()`, `build_high_regains_to_shots_df()`, `plot_high_regains_on_pitch_points_only()` |
| 7 | `notebooks/02_xt.ipynb` (636 lines, 8 cells) | **xT notebook** for single-match analysis. Team detection, xT computation and visualization. | xT grid build + visualization |
| 8 | `notebooks/06_epv.ipynb` (852 lines, 22 cells) | **EPV notebook**. Loads all season CSVs, standardizes, computes possession chains, EPV-related metrics, visualizations. | EPV feature engineering + plots |
| 9 | `notebooks/09_offensive_moment.ipynb` (1516 lines, 15 cells) | **Offensive Moment** analysis (full offensive phase notebook). Data loading, preprocessing, entry method detection, corridor analysis, outcome classification, chain-to-goal matrix visualization. | Full offensive analysis pipeline |
| 10 | `OFFENSIVE_PHASE_METHODOLOGY.md` (559 lines) | **Design spec** for all 3 offensive phases (GK Build-up, General Build-up, Chance Creation). Entry method definitions, outcome rules, zone model. | Methodology reference |

---

## 3. Literature Review — PV-like Models

### 3.1 Annotated Bibliography

| # | Model / Paper | Authors / Year | Key Idea | Link |
|---|--------------|---------------|----------|------|
| 1 | **Pollard & Reep — "Markov process" approach** | Pollard & Reep, 1997 | Pioneering work modelling football as a stochastic process. Each possession is a chain of states; goal probability depends on where the ball is and what happens next. The foundational "chain to goal" idea. | Pollard, R. & Reep, C. (1997). *Measuring the effectiveness of playing strategies at association football.* JRSS-D. |
| 2 | **Expected Threat (xT)** | Karun Singh, 2018 | Zone-based (16×12 grid) Markov model. Each zone has a value = $s_{x,y} \cdot g_{x,y} + m_{x,y} \cdot \sum T_{(x,y)\to(z,w)} \cdot xT_{z,w}$. Iterated to convergence. Action value = $xT_{end} - xT_{start}$. Simple, interpretable, event-data only. | [karun.in/blog/expected-threat.html](https://karun.in/blog/expected-threat.html) |
| 3 | **VAEP** (Valuing Actions by Estimating Probabilities) | Decroos, Bransen, Van Haaren, Davis — KDD 2019 | Supervised ML framework. For each action, predict P(scoring in next 10 actions) and P(conceding). Value = ΔP_scoring − ΔP_conceding. Uses SPADL action representation. More context-rich than xT but needs training infrastructure. | [arXiv:1802.07127](https://arxiv.org/abs/1802.07127), [dtai.cs.kuleuven.be/sports/vaep](https://dtai.cs.kuleuven.be/sports/vaep) |
| 4 | **EPV** (Expected Possession Value) | Fernandez, Bornn, Cervone — Sloan 2019 | Full-field continuous EPV using tracking + event data. Decomposes value into pass, carry, shot components. Most sophisticated but requires tracking data. | Fernandez, J., Bornn, L., Cervone, D. (2019). *Decomposing the Immeasurable Sport.* Sloan Sports Analytics. |
| 5 | **GPA** (Goal Probability Added) | American Soccer Analysis / StatsPerform | Each action changes the probability of scoring. GPA = P(goal after action) − P(goal before action). Similar to VAEP but often uses simpler features. | [americansocceranalysis.com](https://www.americansocceranalysis.com/home/2020/8/27/goal-probability-added) |
| 6 | **xGChain / xGBuildup** | StatsBomb | Distributes shot xG equally among all players in the buildup chain (xGChain) or excluding the assister and shooter (xGBuildup). Simple, no model needed, but unfairly distributes credit. | StatsBomb, via FBref |
| 7 | **OBSO** (Off-Ball Scoring Opportunity) | Spearman, 2018 | Evaluates off-ball movement by estimating scoring probability if a pass were made to each location. Requires tracking. | Spearman, W. (2018). *Beyond Expected Goals.* Sloan. |
| 8 | **Atomic SPADL + xT hybrid** | socceraction library | Open-source implementation combining SPADL event representation with xT or VAEP. Well-documented Python library. | [github.com/ML-KULeuven/socceraction](https://github.com/ML-KULeuven/socceraction) |

### 3.2 Ian Graham / Liverpool Rationale (excerpt mapping)

The Ian Graham concept of "possession value" at Liverpool centres on the idea that **every on-ball action changes the probability that the team in possession will score before losing the ball**. The critical definition:

> *"The value of a possession state is the probability that the team currently in possession will score before they next lose the ball."*

This maps directly to our implementation:
- **State** → (zone, Entry Method, sequence length, time elapsed, High Regain flag, open/set-play)
- **P(score | state)** → the target variable in our supervised model
- **PV-Added per action** → ΔP(score) = P(state_after) − P(state_before)
- **Accumulated PV** → sum of positive ΔP along a possession chain

### 3.3 Strengths/Weaknesses Comparison for This Dashboard

| Approach | Interpretability | Compute | Data Needs | Fits Dashboard? |
|----------|-----------------|---------|------------|----------------|
| **xT (zone grid)** | ★★★★★ High — heatmap + single number per zone | ★★★★★ Seconds to build | Event data only ✓ | ★★★★ Already implemented. Lacks Entry Method context. |
| **VAEP (supervised ML)** | ★★★☆ Moderate — needs SHAP for explanations | ★★★☆ Minutes to train | Event data + SPADL ✓ | ★★★ Good, but heavy infra for a dashboard. |
| **EPV (tracking-based)** | ★★☆☆ Complex — continuous field | ★★☆☆ Needs GPU/tracking | Tracking data ✗ | ★☆☆☆ Not feasible without tracking. |
| **Context-enriched xT (recommended)** | ★★★★☆ Zone heatmap + Entry Method segmentation | ★★★★☆ 1-2 min train | Event data only ✓ | ★★★★★ Best fit — extends existing code, uses dashboard KPIs. |

---

## 4. Model Design Proposals

### Proposal A — Discrete State/Value Table (Empirical Lookup)

**Idea:** Extend the 16×12 xT grid to a multi-dimensional lookup: **Zone × Entry Method × High Regain flag → P(goal)**.

- **Input features:** Zone (192 cells), Entry Method (8 categories), is_high_regain (bool), is_set_piece (bool)
- **Target:** P(possession leads to a shot on target OR goal)
- **Training:** Empirical frequency counts with Laplace smoothing
- **Pros:** Dead simple, fully interpretable, instant lookup, no ML dependencies
- **Cons:** Sparse data for rare combinations (e.g., switch_of_play + high_regain + zone 16), poor generalization, can't handle continuous features
- **Dashboard fit:** ★★★★ — easy heatmaps, but may need 5+ seasons of data

### Proposal B — Expected Threat (xT) + Entry Method Segmentation (Recommended)

**Idea:** Keep the existing xT grid as the base layer. Build a second lightweight model (LightGBM or Logistic Regression) that predicts **P(score | possession state)** using:

- **Input features (explicit list):**
  1. `zone_col, zone_row` — xT grid position (0-15, 0-11)
  2. `xT_value` — current xT at location (from existing model)
  3. `entry_method` — one-hot: through_ball, switch_of_play, set_piece, long_ball, transition_recovery, individual_carry, combination_play, short_pass
  4. `is_high_regain` — boolean (possession started from a high regain)
  5. `is_set_piece` — boolean (possession origin)
  6. `is_open_play` — boolean
  7. `sequence_length` — number of actions in possession so far
  8. `elapsed_sec` — seconds since possession started
  9. `x_progress` — cumulative forward distance (Δx) in possession
  10. `corridor` — L/C/R entry corridor
  11. `actions_in_ft` — count of actions in final third
  12. `shot_angle`, `shot_distance` — for shot actions only

- **Target definition:** Binary label — **1 if the possession produces a goal, 0 otherwise** (alternatively: 1 if possession produces a shot with xG > 0.05). Can also use continuous xG as target for a regression variant.
- **Training labels:** Built from possession chains (`build_possessions()`). For each possession, label = 1 if any event is a Goal (type_id=16). Each action within the possession inherits that label.
- **PV computation:**
  - For each action *a* in a possession: **PV(a) = P(score | state_after_a) − P(score | state_before_a)**
  - Accumulated chain PV = Σ max(PV(a), 0) for positive contributions
- **Pros:** Interpretable (feature importances), uses all dashboard KPIs as features, fast training (<1 min), works with event data, can segment by Entry Method naturally
- **Cons:** Slightly more complex than pure lookup, needs cross-validation
- **Dashboard fit:** ★★★★★

### Proposal C — Full VAEP-style Supervised Model

**Idea:** Implement the VAEP framework: for each action, predict P(scoring within next 10 actions) and P(conceding within next 10 actions).

- **Input features:** Same as Proposal B + game state (score differential, time remaining), action type (pass/carry/shot/tackle), body part
- **Target:** Two binary classifiers: P_score_10 and P_concede_10
- **Training:** Requires SPADL-formatted actions, gradient-boosted trees
- **Pros:** Most accurate, captures defensive value too
- **Cons:** Heavy infrastructure (SPADL conversion), two models to maintain, harder to explain to dashboard users
- **Dashboard fit:** ★★★ — overkill for current scope

---

## 5. Recommended Implementation — Proposal B (Context-Enriched xT)

### 5.1 Justification

| Criterion | Proposal B Score | Reasoning |
|-----------|-----------------|-----------|
| Interpretability | ★★★★☆ | Zone heatmap from xT + feature importance from LightGBM + Entry Method segmentation |
| Compute | ★★★★☆ | Train in <1 min, inference in milliseconds |
| Data needs | ★★★★★ | Only Opta event CSVs (already available, 5 seasons) |
| Integration effort | ★★★★★ | Extends existing `PossessionValueModel`, uses existing `build_possessions()`, `_classify_ft_method()` |
| Consistency with dashboard | ★★★★★ | Uses the same 8 Entry Method categories and High Regain definition |

### 5.2 Step-by-Step Implementation Plan

#### Phase 1: Feature Engineering & Label Creation (New Notebook)

```
notebooks/10_possession_value_model.ipynb
```

1. Load all season CSVs using `_load_all_match_dataframes()` from possession_value.py
2. Build possession chains using `build_possessions()` from general_buildup.py
3. For each possession:
   - Detect FT entry and classify Entry Method (reuse `_classify_ft_method()`)
   - Detect if possession started from High Regain (x ≥ 66.7 + ball recovery)
   - Label: 1 if goal in possession, 0 otherwise
4. For each action within each possession:
   - Extract features: zone, xT, entry_method, is_high_regain, is_set_piece, sequence_position, elapsed_sec, x_progress, corridor, actions_in_ft
5. Save features to `data/processed/pv_features.parquet`

#### Phase 2: Model Training (Same Notebook)

1. Train/test split: by season (leave 2025-2026 as test)
2. Train LightGBM binary classifier: P(goal | state)
3. Cross-validate: 5-fold within training seasons
4. Save model to `data/cache/pv_lgbm_model.pkl`

#### Phase 3: Inference & Aggregation (New Module)

```
dash_app/src/analytics/pv_model.py  (new file)
```

Core functions:
```python
def extract_possessions(events_df: pd.DataFrame) -> pd.DataFrame:
    """Build possession chains with poss_id, origin, duration."""

def compute_high_regains(events_df: pd.DataFrame, team: str) -> pd.Series:
    """Identify high regain events (x ≥ 66.7, Ball recovery, open play)."""

def compute_pv_features(possessions_df: pd.DataFrame, events_df: pd.DataFrame) -> pd.DataFrame:
    """Extract PV model features for each action in each possession."""

def train_pv_model(features_df: pd.DataFrame, labels: pd.Series) -> Any:
    """Train LightGBM and return fitted model."""

def infer_pv(model, match_events: pd.DataFrame) -> pd.DataFrame:
    """Per-action PV inference: returns DataFrame with columns
    [poss_id, action_idx, player, x, y, zone, entry_method,
     is_high_regain, pv_before, pv_after, pv_added, cum_pv]."""

def aggregate_pv(per_action_df: pd.DataFrame) -> dict:
    """Aggregate PV KPIs: PV per 90, PV per entry method, PV by player,
    PV per action type, team-level PV summary."""
```

#### Phase 4: Dashboard Integration

- Update `chance_creation.py`: add `high_regains_count` and `pv_by_entry_method` to output dict
- Update `final_third.py`: add `high_regains_count` field to metrics dict
- Add new visualization components for PV heatmap and PV-by-method bar chart

### 5.3 Pseudocode — Core Pipeline

```python
# ─── Feature Extraction ───
def compute_pv_features(poss_df, events_df, xT_model):
    features = []
    for poss_id, poss_events in events_df.groupby("poss_id"):
        poss_meta = poss_df[poss_df.poss_id == poss_id].iloc[0]
        entry_method = poss_meta.get("entry_method", "short_pass")
        is_hr = poss_meta.get("is_high_regain", False)
        is_sp = poss_meta.get("is_set_piece", False)

        for i, (_, action) in enumerate(poss_events.iterrows()):
            zone_col, zone_row = get_xt_zone(action.x, action.y)
            feat = {
                "poss_id": poss_id,
                "action_idx": i,
                "player": action.get("player_name", ""),
                "zone_col": zone_col,
                "zone_row": zone_row,
                "xT_value": xT_model.get_xT(action.x, action.y),
                "entry_method": entry_method,
                "is_high_regain": int(is_hr),
                "is_set_piece": int(is_sp),
                "is_open_play": int(not is_sp),
                "sequence_position": i,
                "elapsed_sec": action._match_sec - poss_events._match_sec.iloc[0],
                "x_progress": action.x - poss_events.x.iloc[0],
                "in_final_third": int(action.x >= 66.67),
                "corridor": classify_corridor(action.y),
            }
            features.append(feat)
    return pd.DataFrame(features)

# ─── Label Creation ───
def build_labels(events_df):
    """For each possession, 1 if goal scored, 0 otherwise."""
    goal_poss = events_df[events_df.type_id == 16]["poss_id"].unique()
    labels = events_df.groupby("poss_id").first()
    labels["label"] = labels.index.isin(goal_poss).astype(int)
    return labels["label"]

# ─── Model Training ───
def train_pv_model(features_df, labels):
    import lightgbm as lgb
    feature_cols = [
        "zone_col", "zone_row", "xT_value",
        "is_high_regain", "is_set_piece", "is_open_play",
        "sequence_position", "elapsed_sec", "x_progress",
        "in_final_third",
    ]
    cat_cols = ["entry_method", "corridor"]
    X = features_df[feature_cols + cat_cols].copy()
    for c in cat_cols:
        X[c] = X[c].astype("category")
    y = labels.reindex(features_df["poss_id"]).values

    model = lgb.LGBMClassifier(
        n_estimators=200, max_depth=6, learning_rate=0.05,
        random_state=42, verbose=-1
    )
    model.fit(X, y, categorical_feature=cat_cols)
    return model

# ─── Inference ───
def infer_pv(model, match_events_df, xT_model):
    features = compute_pv_features(...)
    probs = model.predict_proba(features[feature_cols])[:, 1]
    features["pv_state"] = probs
    # PV-Added = change in P(goal) between consecutive actions
    features["pv_added"] = features.groupby("poss_id")["pv_state"].diff().fillna(0)
    features["pv_added_positive"] = features["pv_added"].clip(lower=0)
    return features
```

### 5.4 Expected Per-Possession Output (Example)

| poss_id | action_idx | player | x | y | zone | entry_method | is_high_regain | pv_state | pv_added | cum_pv |
|---------|-----------|--------|---|---|------|-------------|---------------|---------|---------|--------|
| 127 | 0 | Barella | 55.2 | 48.1 | (8,5) | transition_recovery | 1 | 0.032 | 0.000 | 0.000 |
| 127 | 1 | Çalhanoğlu | 68.4 | 42.3 | (10,5) | transition_recovery | 1 | 0.071 | 0.039 | 0.039 |
| 127 | 2 | Thuram | 82.1 | 55.6 | (13,6) | transition_recovery | 1 | 0.142 | 0.071 | 0.110 |

---

## 6. Integration: Entry Method KPIs and High Regains

### 6.1 How Entry Method Categories Will Be Used

**As categorical features in the PV model:** Entry Method is encoded as a categorical feature in LightGBM (native handling). This means the model learns _different_ goal-probability curves for each entry method. For example, `transition_recovery` possessions may have higher PV early in the chain (quick counter = more dangerous), while `short_pass` possessions accumulate PV gradually.

**As segmentation for aggregated KPIs:** Dashboard outputs will be segmented by Entry Method:
- PV per Entry Method (bar chart)
- Mean PV per possession by Entry Method
- PV contribution % by Entry Method (stacked bar)
- Outcome × PV cross-tabulation

### 6.2 How High Regains Will Be Integrated

**Computation:** Use the existing `notebooks/01_high_regains.ipynb` logic — Ball Recovery events with `x ≥ 66.7` during open play. The dashboard module will call a refactored function:

```python
def compute_high_regains(events_df, team_lower):
    """Returns boolean Series aligned to events_df index."""
    is_recovery = events_df["event_type"].str.lower() == "ball recovery"
    is_team = events_df["team_name"].str.lower().str.contains(team_lower)
    is_open = events_df["phase_of_play"] == "open_play"  # or poss_origin check
    is_ft = events_df["x"] >= 66.7
    return is_recovery & is_team & is_open & is_ft
```

**In the PV model:** `is_high_regain` is a boolean feature at the possession level (1 if the possession started from a high regain action). This allows the model to learn that possessions originating from high regains have elevated goal probability.

**In Build-up to Final Third section:** Add a new KPI card:
- `high_regains_total` — count of high regains in the match
- `high_regains_leading_to_shot` — count leading to shot within 15s
- `high_regains_leading_to_goal` — count leading to goal

**In Chance Creation section:** Add:
- `pv_from_high_regain_chains` — total PV accumulated in possession chains that started from high regains
- `shot_origins_from_high_regain` — breakdown of shot origins when chain started from high regain

### 6.3 New PV KPIs for Dashboard

#### Build-up to Final Third

| KPI Name | Unit | Description |
|----------|------|-------------|
| `high_regains_total` | count | Ball recoveries in opponent's third (x≥66.7), open play |
| `high_regains_per_90` | count/90min | Normalized |
| `high_regain_shot_rate` | % | % of high regains leading to shot within 15s |
| `pv_per_ft_entry` | probability (0-1) | Mean PV accumulated per FT entry |
| `pv_by_entry_method` | dict | PV totals segmented by 8 entry methods |

#### Chance Creation

| KPI Name | Unit | Description |
|----------|------|-------------|
| `high_regains_total` | count | Same metric, shown in both sections |
| `high_regain_to_shot_pct` | % | % of high regains leading to shot |
| `pv_per_possession` | probability (0-1) | Mean PV per possession |
| `pv_per_90` | PV/90min | Total team PV normalized to 90 minutes |
| `pv_by_attack_origin` | dict | PV by Through/Cross/Counter/Out Box/Set Play |
| `pv_per_player` | dict | PV contributed by each player |
| `chain_to_goal_matrix_pv_row` | dict | PV row in Chain-to-Goal Matrix (already exists) |

### 6.4 Recommended Visualizations

1. **PV Heatmap** — 16×12 zone grid colored by average PV-Added originating from each zone (similar to xT heatmap but contextualized)
2. **PV by Entry Method Bar Chart** — horizontal bar chart, 8 bars, total PV accumulated per method
3. **Chain-to-Goal Matrix** — existing 5×4 matrix (Through|Cross|Counter|Out Box|Set Play × PV|xG|xGOT|GS) — PV row already exists, will now use the enriched model
4. **High Regains Pitch Map** — scatter plot on pitch (already in notebook), to be added to both sections
5. **High Regain → Shot Linkage** — line plot connecting regain → shot on pitch (already in notebook)
6. **PV Contribution by Player** — bar chart of top 5 PV contributors per match

---

## 7. Code Review of `notebooks/01_high_regains.ipynb`

### 7.1 Static Code Review

| Aspect | Assessment | Notes |
|--------|-----------|-------|
| **Core logic** | ✅ Correct | Ball recovery + x ≥ 66.7 + open play filter is the standard definition |
| **Attack direction normalization** | ✅ Good | Uses shot distribution to detect which direction team attacks; flips x coordinates per half/period |
| **HIGH_REGAIN_TYPES** | ⚠️ Restrictive | Currently `["Ball recovery"]` only. Commented out: `"Interception", "Tackle"`. This is a deliberate choice but should be documented. Many analytics frameworks include Interceptions as high regains. |
| **Open play filter** | ✅ Correct | `add_phase_of_play()` correctly identifies set pieces vs open play |
| **Tackle outcome filter** | ✅ Correct | Only successful tackles (outcome=1) counted — but irrelevant since Tackle is commented out |
| **Data path** | ⚠️ Hardcoded | Uses `Path.home() / "Documents" / ...` — not the project `data/raw/` path. Should be updated for dashboard integration |
| **Match key inference** | ✅ Robust | `infer_match_key_col()` tries multiple candidates, good fallback chain |
| **Regain → Shot linkage** | ✅ Well-implemented | Uses `np.searchsorted` for efficient time-based matching, configurable window (default 30s, later 15s) |
| **Shot types** | ✅ Complete | `["Goal", "Saved Shot", "Miss", "Post"]` covers all Opta shot types |
| **Edge cases** | ⚠️ Minor | If all shots are in own half (mean x < 50), flip logic triggers — could theoretically misfire for very unusual datasets, but practically fine for Serie A |
| **Per-team normalization for league table** | ✅ Good | Cell 2 normalizes attack direction per team separately before computing league table |
| **Documentation** | ⚠️ Sparse | Comments in Italian, no docstrings for some functions, no type hints |
| **Runtime complexity** | ✅ Acceptable | Linear scan per match for events, O(n log n) for shot matching — efficient |

### 7.2 Suggested Changes (REQUIRING USER APPROVAL)

1. **Data path**: Change from hardcoded `Path.home() / "Documents"` to project-relative `data/raw/serie_a_*/events/`. _Impact: functionality only, no KPI change._

2. **HIGH_REGAIN_TYPES scope**: Consider whether to include `"Interception"` alongside `"Ball recovery"`. Interceptions in the opponent's third are arguably "high regains" too. _Impact: would increase high regain counts by ~40-60%. Needs explicit approval._

3. **Refactor for reuse**: Extract the core `is_high_regain()` logic into a standalone function in `dash_app/src/analytics/` so it can be called from both the Build-up and Chance Creation modules without duplicating code. _Impact: no KPI change, just code organization._

4. **Add English docstrings**: For dashboard integration, translate Italian comments to English and add type hints. _Impact: none on output._

**⚠️ I will NOT apply any of these changes without your explicit approval.**

---

## 8. Evaluation & Validation Plan

### 8.1 Metrics

| Metric | What it measures | Target |
|--------|-----------------|--------|
| **Brier Score** | Calibration of P(goal) predictions | < 0.05 (goal rate ~3-5% of possessions) |
| **Log Loss** | Probabilistic accuracy | Lower is better; compare to baseline |
| **ROC-AUC** | Discrimination ability | > 0.70 |
| **Calibration Plot** | Predicted vs actual goal rate by decile | Diagonal line |
| **Feature Importance** | Entry Method and High Regain contribution | Verify these are informative |
| **Stability** | Season-to-season consistency | PV rankings stable across seasons |

### 8.2 Experimental Design

1. **Train/test split:** Train on seasons 2021-2025, test on 2025-2026
2. **Cross-validation:** 5-fold within training data, stratified by season
3. **Per-Entry-Method stratified evaluation:** Report AUC separately for each Entry Method
4. **Calibration plots:** 10-bin reliability diagram for test set
5. **Comparison notebook:** Show old PV (pure xT) vs new PV (context-enriched) for 3 sample matches

### 8.3 Baselines

| Baseline | Description |
|----------|-------------|
| **Distance-only** | P(goal) = f(distance_to_goal) — logistic regression on 1 feature |
| **xT-only** | Current `PossessionValueModel.get_xT()` — zone lookup, no context |
| **Logistic Regression** | Same features as LightGBM but linear model — tests if nonlinearity helps |
| **Random (calibrated)** | Always predict the marginal goal rate — floor for any model |

---

## 9. Deliverables & Artifacts

| # | Artifact | Format | Location |
|---|----------|--------|----------|
| 1 | Design doc | Markdown | `docs/POSSESSION_VALUE_DESIGN.md` (this file) |
| 2 | PV model training notebook | Jupyter | `notebooks/10_possession_value_model.ipynb` |
| 3 | High regains integration notebook | Jupyter | `notebooks/11_high_regains_integration.ipynb` |
| 4 | PV inference module | Python | `dash_app/src/analytics/pv_model.py` |
| 5 | Updated chance_creation.py | Python | Add high_regain + PV fields |
| 6 | Updated final_third.py | Python | Add high_regain fields |
| 7 | Feature data | Parquet | `data/processed/pv_features.parquet` |
| 8 | Trained model | Pickle | `data/cache/pv_lgbm_model.pkl` |
| 9 | Per-action PV output (sample) | CSV | `outputs/pv_per_action_sample.csv` |
| 10 | Dashboard integration spec | JSON | `outputs/pv_dashboard_spec.json` |

---

## 10. New/Modified Files & Function Signatures

### New Files

```
dash_app/src/analytics/pv_model.py
├── extract_possessions(events_df: pd.DataFrame) -> pd.DataFrame
├── compute_high_regains(events_df: pd.DataFrame, team: str) -> pd.Series
├── compute_pv_features(possessions_df: pd.DataFrame, events_df: pd.DataFrame, xT_model) -> pd.DataFrame
├── build_pv_labels(events_df: pd.DataFrame) -> pd.Series
├── train_pv_model(features_df: pd.DataFrame, labels: pd.Series) -> lgb.LGBMClassifier
├── load_pv_model(path: Path) -> lgb.LGBMClassifier
├── infer_pv(model, match_events: pd.DataFrame, xT_model) -> pd.DataFrame
├── aggregate_pv(per_action_df: pd.DataFrame) -> dict
└── get_pv_by_entry_method(per_action_df: pd.DataFrame) -> dict

notebooks/10_possession_value_model.ipynb   (training & evaluation)
notebooks/11_high_regains_integration.ipynb  (integration testing)
```

### Modified Files (pending approval)

```
dash_app/src/analytics/chance_creation.py
  — Add high_regains_count to analyze() output
  — Add pv_by_entry_method to output

dash_app/src/analytics/final_third.py
  — Add high_regains_total, high_regains_per_90 to compute_ft_metrics()
```

---

## 11. Questions for the User / Approval Required

1. **HIGH_REGAIN_TYPES scope:** Currently only `"Ball recovery"`. Should we also include `"Interception"` and/or `"Tackle"` (successful)? This would increase counts significantly. **Please confirm.**

2. **Data path refactoring in `01_high_regains.ipynb`:** May I update the hardcoded `Path.home() / "Documents"` path to use the project's `data/raw/` directory? This is a non-KPI-changing housekeeping fix. **Please confirm.**

3. **PV target label:** Should we use `P(goal in this possession)` as the binary target (strict), or `P(shot with xG > 0.05)` (more data, less sparse)? I recommend starting with `P(goal)` and switching to `P(shot)` only if the model is too sparse. **Please confirm preference.**

4. **Model choice:** LightGBM is recommended for speed and categorical feature handling. Is there a preference for a simpler model (Logistic Regression) or do you want both compared in the evaluation notebook? **Please confirm.**

5. **Refactoring the existing `possession_value.py`:** The current file contains a solid xT model. I propose keeping it untouched and building the new enriched PV model in a _new_ file (`pv_model.py`). The enriched model will _import_ the xT model for zone values. **Please confirm this non-destructive approach.**

6. **Italian → English translation:** May I add English docstrings to the high regains functions when integrating into the dashboard module (without changing logic)? **Please confirm.**

---

## 12. Suggested Timeline

| Week | Milestone | Deliverables | Check-in |
|------|-----------|-------------|----------|
| **Week 1** (Days 1-5) | Research + Design + Feature Engineering | ✅ This design doc, `pv_features.parquet` created, high regains code reviewed | User reviews design doc, answers approval questions |
| **Week 2** (Days 6-10) | Model Training + Evaluation + High Regains Integration | Training notebook complete, evaluation metrics computed, baselines compared, high regains refactored into module | User reviews evaluation notebook, confirms model quality |
| **Week 3** (Days 11-15) | Dashboard Integration + Final Review | `pv_model.py` module complete, `chance_creation.py` and `final_third.py` updated, visualization components added, comparison notebook (old vs new PV) | Final review, merge to main |

### Milestone Check-ins

- **Day 3:** Feature engineering notebook shared — user validates feature definitions
- **Day 7:** Evaluation notebook shared — user reviews AUC, calibration, baseline comparisons
- **Day 10:** High regains integration tested end-to-end for 3 sample matches
- **Day 13:** Dashboard components wired, demo with live data
- **Day 15:** Final QA, documentation complete

---

## Appendix A: Dashboard Integration Spec (JSON Schema)

```json
{
  "new_kpis": {
    "build_up_to_final_third": {
      "high_regains_total": {"type": "int", "unit": "count"},
      "high_regains_per_90": {"type": "float", "unit": "count/90min"},
      "high_regain_shot_rate": {"type": "float", "unit": "%"},
      "pv_per_ft_entry": {"type": "float", "unit": "probability", "range": [0, 1]},
      "pv_by_entry_method": {
        "type": "dict",
        "keys": ["through_ball", "switch_of_play", "set_piece", "long_ball",
                 "transition_recovery", "individual_carry", "combination_play", "short_pass"],
        "value_type": "float",
        "unit": "probability"
      }
    },
    "chance_creation": {
      "high_regains_total": {"type": "int", "unit": "count"},
      "high_regain_to_shot_pct": {"type": "float", "unit": "%"},
      "pv_per_possession": {"type": "float", "unit": "probability", "range": [0, 1]},
      "pv_per_90": {"type": "float", "unit": "PV/90min"},
      "pv_by_attack_origin": {
        "type": "dict",
        "keys": ["Through", "Cross", "Counter", "Out Box", "Set Play"],
        "value_type": "float"
      },
      "pv_per_player": {
        "type": "dict",
        "keys": "dynamic (player names)",
        "value_type": "float"
      }
    }
  },
  "visualizations": {
    "pv_heatmap": {
      "type": "heatmap",
      "data": "16x12 grid of average PV-Added per zone",
      "colorscale": "YlOrRd",
      "location": "both sections"
    },
    "pv_by_entry_method_bar": {
      "type": "horizontal_bar",
      "data": "8 bars, one per entry method",
      "location": "build_up section"
    },
    "high_regains_pitch_map": {
      "type": "scatter_on_pitch",
      "data": "high regain events (x, y)",
      "marker": "yellow circle",
      "location": "both sections"
    },
    "pv_chain_to_goal_matrix": {
      "type": "matrix/table",
      "data": "5 origins × 4 metrics (PV, xG, xGOT, GS)",
      "location": "chance_creation section"
    },
    "pv_player_contribution_bar": {
      "type": "horizontal_bar",
      "data": "top 5 players by PV contribution",
      "location": "chance_creation section"
    }
  }
}
```

---

*Document generated: 2 April 2026*
*Author: GitHub Copilot (automated design)*
*Status: DRAFT — Pending user approval on questions in Section 11*
