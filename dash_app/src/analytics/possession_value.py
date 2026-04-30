"""
Possession Value (PV) Model — Goal Probability Added (GPA)
============================================================
Zone-based Possession Value model inspired by Ian Graham's
*Goal Probability Added* concept:

    For every area of the pitch, count every time a team has
    possession in that area, and count how many times those
    possessions lead to a goal.  That ratio is the **Goal
    Probability** P(goal | zone × situation).

    The **Possession Value Added** by any single action is the
    change in goal probability it produces:

        PV_added = P(goal | state_after) − P(goal | state_before)

The model provides two estimators:

  1. **Empirical Grid** — direct frequency ratio P(goal | zone)
     computed over the entire training corpus.  Zero-cost, fully
     transparent, and always available as a baseline.

  2. **ML Regressor** — a supervised model (Logistic Regression
     *and* LightGBM) trained on per-action features to predict
     P(goal within the current possession).  The feature set is:
     ``[zone_col, zone_row, game_situation_code, seconds_elapsed,
       is_home, pass_forward, is_shot, distance_to_goal]``.
     LightGBM is the primary; LR serves as an interpretable
     cross-check.

Both estimators share a common 16 × 12 pitch grid and the same
public API so that downstream consumers (``chance_creation.py``,
``final_third.py``) remain unchanged.

Coordinate system (Opta standard):
    x: 0 → 100  (own goal → opponent goal)
    y: 0 → 100  (right touchline → left touchline)

Public interface consumed by other modules
------------------------------------------
  Classes:  PossessionValueModel
  Functions: get_pv_model, get_xt_zone
  Constants: FT_X_THRESHOLD, SHOT_TYPE_IDS, NON_PLAY_EVENTS,
             X_ZONES, Y_ZONES
"""

from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import List, Optional, Dict, Tuple

import numpy as np
import pandas as pd

from src.config import RAW_DATA_DIR, CACHE_DIR

log = logging.getLogger("dashboard.pv_model")

# ═══════════════════════════════════════════════════════════════════════════════
# GRID CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

X_ZONES = 16       # columns along x-axis → each zone is 6.25 units wide
Y_ZONES = 12       # rows along y-axis   → each zone is ~8.33 units wide
X_STEP  = 100.0 / X_ZONES   # 6.25
Y_STEP  = 100.0 / Y_ZONES   # ~8.333

# Final Third threshold (x ≥ 66.67)
FT_X_THRESHOLD = 66.67

# ═══════════════════════════════════════════════════════════════════════════════
# OPTA EVENT CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

# Shot event type_ids (Opta): Miss, Post, Saved Shot, Goal
SHOT_TYPE_IDS = {13, 14, 15, 16}

# On-ball action event types (lowercase) — used for chain construction
ON_BALL_EVENTS = frozenset({
    "pass", "ball touch", "take on", "ball recovery",
    "clearance", "miss", "saved shot", "goal", "blocked pass",
    "dispossessed", "interception", "aerial", "tackle",
    "offside pass",
})

# Non-play events to skip during possession/chain analysis
NON_PLAY_EVENTS = frozenset({
    "deleted event", "team setp up", "start", "end",
    "player off", "player on", "resume", "unknown",
    "start delay", "end delay", "formation change",
    "collection end", "early end",
    "injury time announcement", "card",
    "contentious referee decision",
})

# ═══════════════════════════════════════════════════════════════════════════════
# GAME-SITUATION ENCODING
# ═══════════════════════════════════════════════════════════════════════════════

_SITUATION_MAP: Dict[str, int] = {
    "open_play":    0,
    "corner":       1,
    "free_kick":    2,
    "throw_in":     3,
    "penalty":      4,
    "goal_kick":    5,
    "gk_hands":     6,
}

_SET_PIECE_ORIGINS = frozenset({
    "corner", "free_kick", "throw_in", "penalty",
    "goal_kick", "gk_hands",
})

# Laplace smoothing (Bayesian pseudocounts) for empirical grid
_SMOOTH_ALPHA = 1.0   # pseudocount for goals
_SMOOTH_BETA  = 50.0  # pseudocount for possessions (prior: ~2 % baseline)


# ═══════════════════════════════════════════════════════════════════════════════
# ZONE HELPERS
# ═══════════════════════════════════════════════════════════════════════════════


def get_xt_zone(x: float, y: float) -> Tuple[int, int]:
    """Convert (x, y) Opta coordinates to (col, row) on the 16x12 grid.

    Parameters
    ----------
    x : float
        Horizontal coordinate, 0 (own goal) to 100 (opponent goal).
    y : float
        Vertical coordinate, 0 (right touchline) to 100 (left touchline).

    Returns
    -------
    tuple[int, int]
        ``(col, row)`` indices clamped to [0, X_ZONES-1] and [0, Y_ZONES-1].
    """
    col = min(int(x / X_STEP), X_ZONES - 1)
    row = min(int(y / Y_STEP), Y_ZONES - 1)
    return (max(col, 0), max(row, 0))


def _distance_to_goal(x: float, y: float) -> float:
    """Euclidean distance from (x, y) to the centre of the opponent goal."""
    return np.sqrt((100.0 - x) ** 2 + (50.0 - y) ** 2)


# ═══════════════════════════════════════════════════════════════════════════════
# DATA LOADING HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _discover_match_csvs(raw_dir: Optional[Path] = None) -> List[Path]:
    """Discover all match CSV files across every season under *raw_dir*.

    Returns
    -------
    list[Path]
        Sorted list of CSV paths.
    """
    base = raw_dir or RAW_DATA_DIR
    csvs = sorted(base.glob("serie_a_*/events/*.csv"))
    log.info("Discovered %d match CSVs under %s", len(csvs), base)
    return csvs


def _load_and_normalise(csv_path: Path) -> pd.DataFrame:
    """Load one match CSV and normalise column names for processing.

    Handles both Opta naming conventions (e.g. ``event`` vs
    ``event_type``, ``time_min`` vs ``minute``).  Adds a
    ``_match_sec`` helper column.
    """
    try:
        df = pd.read_csv(csv_path, low_memory=False)
    except Exception as exc:
        log.warning("Could not read %s: %s", csv_path, exc)
        return pd.DataFrame()

    if df.empty:
        return df

    # Column renames
    renames: Dict[str, str] = {
        "event":       "event_type",
        "time_min":    "minute",
        "time_sec":    "second",
        "period_id":   "period",
        "contestant_id": "team_id",
    }
    for old, new in renames.items():
        if old in df.columns and new not in df.columns:
            df[new] = df[old]

    # Numeric coercions
    for col in ("x", "y", "Pass End X", "Pass End Y", "Length",
                "minute", "second", "event_id", "period",
                "outcome", "type_id"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Sort
    sort_cols = [c for c in ["period", "minute", "second", "event_id"]
                 if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols).reset_index(drop=True)

    # Helper columns
    df["_match_sec"] = df["minute"].fillna(0) * 60 + df["second"].fillna(0)

    return df


def _load_and_normalise_df(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise an already-loaded DataFrame (same transforms as
    ``_load_and_normalise`` but without the CSV read step).

    Used when DataFrames are passed directly via the constructor
    (e.g. in tests or when data is already in memory).
    """
    if df.empty:
        return df

    df = df.copy()

    # Column renames
    renames: Dict[str, str] = {
        "event":       "event_type",
        "time_min":    "minute",
        "time_sec":    "second",
        "period_id":   "period",
        "contestant_id": "team_id",
    }
    for old, new in renames.items():
        if old in df.columns and new not in df.columns:
            df[new] = df[old]

    # Numeric coercions
    for col in ("x", "y", "Pass End X", "Pass End Y", "Length",
                "minute", "second", "event_id", "period",
                "outcome", "type_id"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Sort
    sort_cols = [c for c in ["period", "minute", "second", "event_id"]
                 if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols).reset_index(drop=True)

    # Helper columns
    df["_match_sec"] = df["minute"].fillna(0) * 60 + df["second"].fillna(0)

    return df


# ═══════════════════════════════════════════════════════════════════════════════
# POSSESSION CHAIN BUILDER (LIGHTWEIGHT, PV-SPECIFIC)
# ═══════════════════════════════════════════════════════════════════════════════

_SET_PIECE_COLS = (
    "corner_taken", "Corner taken",
    "free_kick_taken", "Free kick taken",
    "throw_in", "Throw In",
    "penalty", "Penalty",
    "goal_kick", "Goal Kick",
    "gk_kick_from_hands", "Gk kick from hands",
)


def _tag_possessions(df: pd.DataFrame) -> pd.DataFrame:
    """Assign ``_poss_id`` and ``_poss_origin`` to each row.

    A new possession starts when:
      - The team on the ball changes.
      - The period changes.
      - A goal is scored.
      - A set-piece restart occurs.

    This mirrors ``general_buildup.build_possessions()`` but avoids
    a hard import so the PV module can remain self-contained.
    """
    n = len(df)
    poss_ids    = np.zeros(n, dtype=np.int64)
    origins     = [""] * n
    cur_poss    = 0
    cur_team    = None
    cur_period  = None

    for i in range(n):
        row   = df.iloc[i]
        et    = str(row.get("event_type", "")).strip().lower()
        tid   = str(row.get("team_id", "")).strip()
        per   = row.get("period")

        # Non-play events inherit current possession
        if et in NON_PLAY_EVENTS or et == "":
            poss_ids[i] = cur_poss
            origins[i]  = origins[i - 1] if i > 0 else "open_play"
            continue

        new_poss = False

        if per != cur_period and cur_period is not None:
            new_poss = True
        elif tid != cur_team and cur_team is not None and tid != "":
            new_poss = True
        elif et == "goal":
            # Goal terminates the possession
            poss_ids[i] = cur_poss
            origins[i]  = origins[i - 1] if i > 0 else "open_play"
            cur_team   = None
            cur_period = per
            continue

        # Set-piece restart
        if not new_poss:
            for col in _SET_PIECE_COLS:
                val = str(row.get(col, "")).strip().lower()
                if val in ("si", "yes", "1", "true"):
                    new_poss = True
                    break

        if new_poss or cur_poss == 0:
            cur_poss  += 1
            cur_team   = tid
            cur_period = per
        elif tid != "" and tid != cur_team:
            cur_poss  += 1
            cur_team   = tid
            cur_period = per

        poss_ids[i] = cur_poss
        origins[i]  = _detect_origin(row)

    df = df.copy()
    df["_poss_id"] = poss_ids

    # Propagate the FIRST non-empty origin across the whole possession
    origin_s = pd.Series(origins, index=df.index)
    first_origins = (
        df.assign(_origin=origin_s)
        .groupby("_poss_id")["_origin"]
        .first()
    )
    df["_poss_origin"] = df["_poss_id"].map(first_origins).fillna("open_play")
    df["_poss_start_sec"] = df.groupby("_poss_id")["_match_sec"].transform("first")

    return df


def _detect_origin(row: pd.Series) -> str:
    """Classify possession origin from the first event's qualifiers."""
    for cols, label in (
        (("corner_taken", "Corner taken"), "corner"),
        (("free_kick_taken", "Free kick taken"), "free_kick"),
        (("throw_in", "Throw In"), "throw_in"),
        (("penalty", "Penalty"), "penalty"),
        (("goal_kick", "Goal Kick"), "goal_kick"),
        (("gk_kick_from_hands", "Gk kick from hands"), "gk_hands"),
    ):
        for col in cols:
            val = str(row.get(col, "")).strip().lower()
            if val in ("si", "yes", "1", "true"):
                return label
    return "open_play"


# ═══════════════════════════════════════════════════════════════════════════════
# TRAINING RECORD EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_training_records(df: pd.DataFrame) -> pd.DataFrame:
    """Build a training DataFrame from a single match's normalised events.

    Each row represents one **on-ball action** with features and a
    binary target ``poss_leads_to_goal`` (1 if the current possession
    produces a goal for the acting team, else 0).

    Features
    --------
    zone_col, zone_row : int
        16x12 grid indices of the action location.
    situation : int
        Encoded game-situation (see ``_SITUATION_MAP``).
    seconds_elapsed : float
        Seconds since the possession started.
    is_home : int
        1 if team_position == 'home', else 0.
    pass_forward : int
        1 if a pass moves the ball closer to the opponent goal.
    is_shot : int
        1 if the action is a shot event.
    dist_to_goal : float
        Euclidean distance from the event location to centre of goal.
    poss_leads_to_goal : int
        Binary target.
    """
    if df.empty or "_poss_id" not in df.columns:
        return pd.DataFrame()

    # Pre-compute which possessions contain a goal
    goal_mask = df["event_type"].str.strip().str.lower() == "goal"
    goal_poss = set(df.loc[goal_mask, "_poss_id"].dropna().unique())

    records: list[dict] = []

    for _, row in df.iterrows():
        et = str(row.get("event_type", "")).strip().lower()
        if et in NON_PLAY_EVENTS or et == "":
            continue

        x = row.get("x")
        y = row.get("y")
        if pd.isna(x) or pd.isna(y):
            continue

        x, y = float(x), float(y)
        if x < 0 or x > 100 or y < 0 or y > 100:
            continue

        col, rw = get_xt_zone(x, y)
        poss_id = row.get("_poss_id", 0)
        origin  = str(row.get("_poss_origin", "open_play"))
        situation = _SITUATION_MAP.get(origin, 0)

        poss_start = row.get("_poss_start_sec", 0) or 0
        match_sec  = row.get("_match_sec", 0) or 0
        elapsed    = max(match_sec - poss_start, 0.0)

        # Home/away
        pos = str(row.get("team_position", "")).strip().lower()
        is_home = 1 if pos == "home" else 0

        # Pass direction
        pass_forward = 0
        if et == "pass":
            end_x = row.get("Pass End X")
            if pd.notna(end_x) and float(end_x) > x:
                pass_forward = 1

        # Shot flag
        type_id = row.get("type_id")
        is_shot = 1 if (pd.notna(type_id) and int(type_id) in SHOT_TYPE_IDS) else 0

        # Target
        leads_to_goal = 1 if poss_id in goal_poss else 0

        records.append({
            "zone_col":            col,
            "zone_row":            rw,
            "situation":           situation,
            "seconds_elapsed":     round(elapsed, 2),
            "is_home":             is_home,
            "pass_forward":        pass_forward,
            "is_shot":             is_shot,
            "dist_to_goal":        round(_distance_to_goal(x, y), 2),
            "poss_leads_to_goal":  leads_to_goal,
            "_x": x,
            "_y": y,
            "_poss_id": poss_id,
        })

    return pd.DataFrame(records)


# ═══════════════════════════════════════════════════════════════════════════════
# FALLBACK xT GRID (hand-calibrated exponential)
# ═══════════════════════════════════════════════════════════════════════════════

def _fallback_xt_grid() -> np.ndarray:
    """Return a hand-calibrated 16x12 xT grid as a fall-back.

    Values increase exponentially toward the opponent goal (column 15)
    and are mildly higher in the central y-band.

    This grid is used when no training data is available so the
    dashboard can still render reasonable PV values.
    """
    grid = np.zeros((X_ZONES, Y_ZONES), dtype=np.float64)
    for col in range(X_ZONES):
        for row in range(Y_ZONES):
            # x-progression: exponential from ~0.002 to ~0.40
            x_frac = col / (X_ZONES - 1)
            base   = 0.002 + 0.40 * (np.exp(3.5 * x_frac) - 1) / (np.exp(3.5) - 1)

            # y-centrality bonus (max +20 % in the centre)
            y_frac     = row / (Y_ZONES - 1)
            centrality = 1.0 - 2.0 * abs(y_frac - 0.5)
            bonus      = 1.0 + 0.20 * centrality

            grid[col, row] = round(base * bonus, 6)
    return grid


# ═══════════════════════════════════════════════════════════════════════════════
# POSSESSION VALUE MODEL
# ═══════════════════════════════════════════════════════════════════════════════


class PossessionValueModel:
    """Goal Probability Added model for computing Possession Value.

    After ``build()`` the model exposes:

    * ``goal_prob_grid``  -- (16, 12) empirical P(goal | zone)
    * ``xT``              -- alias for ``goal_prob_grid`` (backward compat)
    * ``P_shot``          -- (16, 12) P(shot | zone)
    * ``P_goal``          -- (16, 12) P(goal | shot, zone)
    * ``lr_model``        -- trained LogisticRegression estimator
    * ``lgb_model``       -- trained LightGBM estimator (primary)

    Public methods
    --------------
    build()               Train both estimators from all raw event data.
    get_xT(x, y)          Return the goal probability at (x, y).
    get_gpa(x, y)         Alias for get_xT.
    predict_gp(features)  ML-based goal probability prediction.
    get_chain_pv(chain)           Chain PV from a list of dicts.
    get_chain_pv_from_raw_events  Chain PV from a raw DataFrame.
    save(path) / load(path)       Persistence.
    """

    def __init__(self, all_match_events: Optional[List[pd.DataFrame]] = None) -> None:
        # Legacy parameter: list of pre-loaded DataFrames for build()
        self._all_events = all_match_events or []

        # Empirical grid
        self.goal_prob_grid: np.ndarray = np.zeros(
            (X_ZONES, Y_ZONES), dtype=np.float64,
        )
        self.P_shot: np.ndarray = np.zeros(
            (X_ZONES, Y_ZONES), dtype=np.float64,
        )
        self.P_goal: np.ndarray = np.zeros(
            (X_ZONES, Y_ZONES), dtype=np.float64,
        )

        # Backward-compatible alias -- chance_creation.py reads
        # model.xT via get_xT(); after build this points to
        # the same underlying array as goal_prob_grid.
        self.xT: np.ndarray = self.goal_prob_grid

        # ML estimators (set after build)
        self.lr_model  = None   # sklearn LogisticRegression
        self.lgb_model = None   # lightgbm.LGBMClassifier

        # Book-keeping
        self._built: bool = False
        self._n_matches: int = 0
        self._n_actions: int = 0

        # Empirical counters (used during build)
        self._poss_counts: np.ndarray = np.zeros(
            (X_ZONES, Y_ZONES), dtype=np.float64,
        )
        self._goal_poss_counts: np.ndarray = np.zeros(
            (X_ZONES, Y_ZONES), dtype=np.float64,
        )
        self._shot_counts: np.ndarray = np.zeros(
            (X_ZONES, Y_ZONES), dtype=np.float64,
        )
        self._goal_counts: np.ndarray = np.zeros(
            (X_ZONES, Y_ZONES), dtype=np.float64,
        )

    # ──────────────────────────────────────────────────────────────────────
    # BUILD
    # ──────────────────────────────────────────────────────────────────────

    def build(
        self,
        raw_dir: Optional[Path] = None,
        max_matches: Optional[int] = None,
    ) -> "PossessionValueModel":
        """Train the PV model from all Opta match CSVs.

        Parameters
        ----------
        raw_dir : Path, optional
            Root directory containing ``serie_a_*/events/*.csv``.
            Defaults to ``RAW_DATA_DIR`` from config.
        max_matches : int, optional
            Cap the number of matches processed (useful for debugging).

        Returns
        -------
        PossessionValueModel
            ``self``, for chaining.
        """
        csvs = _discover_match_csvs(raw_dir)
        if max_matches is not None:
            csvs = csvs[:max_matches]

        # If pre-loaded DataFrames were passed via constructor, use them
        # instead of (or in addition to) CSV discovery.
        pre_loaded = self._all_events if self._all_events else []

        if not csvs and not pre_loaded:
            log.warning("No match CSVs found -- using fallback grid.")
            self._apply_fallback()
            return self

        total = len(csvs) + len(pre_loaded)
        log.info("Building GPA model from %d matches ...", total)

        all_train_frames: list[pd.DataFrame] = []

        # Process pre-loaded DataFrames first
        for idx, df in enumerate(pre_loaded, 1):
            df = _load_and_normalise_df(df)
            if df.empty:
                continue
            df = _tag_possessions(df)
            self._accumulate_empirical(df)
            train_df = _extract_training_records(df)
            if not train_df.empty:
                all_train_frames.append(train_df)
            self._n_matches += 1

        # Process CSV files from disk
        for idx, csv_path in enumerate(csvs, len(pre_loaded) + 1):
            if idx % 100 == 0 or idx == total:
                log.info("  Processing match %d / %d ...", idx, total)

            df = _load_and_normalise(csv_path)
            if df.empty:
                continue

            df = _tag_possessions(df)
            self._accumulate_empirical(df)

            train_df = _extract_training_records(df)
            if not train_df.empty:
                all_train_frames.append(train_df)

            self._n_matches += 1

        # Finalise empirical grid
        self._finalise_empirical_grid()

        # Train ML estimators
        if all_train_frames:
            full_train = pd.concat(all_train_frames, ignore_index=True)
            self._n_actions = len(full_train)
            log.info("Training ML models on %d action records ...",
                     self._n_actions)
            self._train_ml(full_train)
        else:
            log.warning("No training records -- ML models unavailable.")

        self._built = True
        log.info(
            "GPA model built: %d matches, %d actions, "
            "grid range [%.5f ... %.5f]",
            self._n_matches,
            self._n_actions,
            float(self.goal_prob_grid.min()),
            float(self.goal_prob_grid.max()),
        )
        return self

    # -- Empirical accumulation ────────────────────────────────────────────

    def _accumulate_empirical(self, df: pd.DataFrame) -> None:
        """Accumulate zone-level possession and goal counts from one match."""
        if "_poss_id" not in df.columns:
            return

        # Find possessions that contain a goal
        goal_mask = df["event_type"].str.strip().str.lower() == "goal"
        goal_poss_ids = set(df.loc[goal_mask, "_poss_id"].dropna().unique())

        # For each possession, record which zones were visited
        for poss_id, grp in df.groupby("_poss_id"):
            leads_to_goal = poss_id in goal_poss_ids
            visited_zones: set = set()

            for _, row in grp.iterrows():
                et = str(row.get("event_type", "")).strip().lower()
                if et in NON_PLAY_EVENTS or et == "":
                    continue

                x, y = row.get("x"), row.get("y")
                if pd.isna(x) or pd.isna(y):
                    continue

                x, y = float(x), float(y)
                if not (0 <= x <= 100 and 0 <= y <= 100):
                    continue

                col, rw = get_xt_zone(x, y)
                visited_zones.add((col, rw))

                # Shot / goal tracking
                type_id = row.get("type_id")
                if pd.notna(type_id) and int(type_id) in SHOT_TYPE_IDS:
                    self._shot_counts[col, rw] += 1
                    if int(type_id) == 16:  # Goal
                        self._goal_counts[col, rw] += 1

            # Record zone visits once per possession (not per event)
            for (c, r) in visited_zones:
                self._poss_counts[c, r] += 1
                if leads_to_goal:
                    self._goal_poss_counts[c, r] += 1

    def _finalise_empirical_grid(self) -> None:
        """Compute smoothed P(goal | zone) from accumulated counts."""
        # Laplace-smoothed goal probability
        self.goal_prob_grid = (
            (self._goal_poss_counts + _SMOOTH_ALPHA)
            / (self._poss_counts + _SMOOTH_BETA)
        )
        # Keep backward-compatible alias
        self.xT = self.goal_prob_grid

        # P(shot | zone) and P(goal | shot, zone)
        total_actions = self._poss_counts.copy()
        total_actions[total_actions == 0] = 1.0
        self.P_shot = (self._shot_counts + 0.5) / (total_actions + 10.0)

        shot_denom = self._shot_counts.copy()
        shot_denom[shot_denom == 0] = 1.0
        self.P_goal = (self._goal_counts + 0.1) / (shot_denom + 1.0)

    # -- ML Training ───────────────────────────────────────────────────────

    _FEATURE_COLS = [
        "zone_col", "zone_row", "situation", "seconds_elapsed",
        "is_home", "pass_forward", "is_shot", "dist_to_goal",
    ]

    def _train_ml(self, train_df: pd.DataFrame) -> None:
        """Train Logistic Regression and LightGBM classifiers."""
        X = train_df[self._FEATURE_COLS].values
        y = train_df["poss_leads_to_goal"].values

        # Logistic Regression
        try:
            from sklearn.linear_model import LogisticRegression

            self.lr_model = LogisticRegression(
                max_iter=500,
                solver="lbfgs",
                class_weight="balanced",
                C=1.0,
                random_state=42,
            )
            self.lr_model.fit(X, y)
            log.info("  Logistic Regression trained (classes=%s)",
                     self.lr_model.classes_)
        except Exception as exc:
            log.warning("LR training failed: %s", exc)
            self.lr_model = None

        # LightGBM
        try:
            import lightgbm as lgb

            self.lgb_model = lgb.LGBMClassifier(
                n_estimators=300,
                max_depth=6,
                learning_rate=0.05,
                num_leaves=31,
                min_child_samples=50,
                subsample=0.8,
                colsample_bytree=0.8,
                class_weight="balanced",
                random_state=42,
                verbose=-1,
            )
            self.lgb_model.fit(X, y)
            log.info("  LightGBM trained (best_iteration=%s)",
                     getattr(self.lgb_model, "best_iteration_", "N/A"))
        except ImportError:
            log.warning("LightGBM not installed -- skipping LGB model.")
            self.lgb_model = None
        except Exception as exc:
            log.warning("LGB training failed: %s", exc)
            self.lgb_model = None

    # -- Fallback ──────────────────────────────────────────────────────────

    def _apply_fallback(self) -> None:
        """Apply the hand-calibrated fallback grid."""
        self.goal_prob_grid = _fallback_xt_grid()
        self.xT = self.goal_prob_grid
        self.P_shot = np.full((X_ZONES, Y_ZONES), 0.05)
        self.P_goal = np.full((X_ZONES, Y_ZONES), 0.01)
        self._built = True

    # ──────────────────────────────────────────────────────────────────────
    # LOOKUPS
    # ──────────────────────────────────────────────────────────────────────

    def get_xT(self, x: float, y: float) -> float:
        """Return the empirical goal probability at pitch location (x, y).

        This is the primary lookup used by downstream modules.
        Reads from ``self.xT`` (which normally aliases ``goal_prob_grid``
        but may be overwritten in tests or by legacy callers).

        Parameters
        ----------
        x, y : float
            Opta coordinates (0-100).

        Returns
        -------
        float
            P(goal | zone) -- the goal probability for the zone
            containing (x, y).
        """
        col, row = get_xt_zone(x, y)
        return float(self.xT[col, row])

    def get_gpa(self, x: float, y: float) -> float:
        """Alias for ``get_xT`` -- Goal Probability at (x, y)."""
        return self.get_xT(x, y)

    def predict_gp(
        self,
        zone_col: int,
        zone_row: int,
        situation: int = 0,
        seconds_elapsed: float = 0.0,
        is_home: int = 0,
        pass_forward: int = 0,
        is_shot: int = 0,
        dist_to_goal: float = 50.0,
        model: str = "lgb",
    ) -> float:
        """Predict goal probability using an ML estimator.

        Parameters
        ----------
        zone_col, zone_row : int
            Grid zone indices.
        situation : int
            Game-situation code (see ``_SITUATION_MAP``).
        seconds_elapsed : float
            Seconds since possession start.
        is_home : int
            1 if home team, else 0.
        pass_forward : int
            1 if the action moves the ball forward.
        is_shot : int
            1 if the action is a shot.
        dist_to_goal : float
            Euclidean distance to goal centre.
        model : str
            ``"lgb"`` (default) or ``"lr"`` for Logistic Regression.

        Returns
        -------
        float
            Predicted P(goal | features).  Falls back to the
            empirical grid if the requested estimator is unavailable.
        """
        estimator = self.lgb_model if model == "lgb" else self.lr_model
        if estimator is None:
            # Fall back to empirical grid
            return float(self.xT[
                min(max(zone_col, 0), X_ZONES - 1),
                min(max(zone_row, 0), Y_ZONES - 1),
            ])

        features = np.array([[
            zone_col, zone_row, situation, seconds_elapsed,
            is_home, pass_forward, is_shot, dist_to_goal,
        ]])
        proba = estimator.predict_proba(features)
        # Return probability of class 1 (goal)
        goal_idx = list(estimator.classes_).index(1) if 1 in estimator.classes_ else -1
        if goal_idx < 0:
            return float(self.xT[
                min(max(zone_col, 0), X_ZONES - 1),
                min(max(zone_row, 0), Y_ZONES - 1),
            ])
        return float(proba[0, goal_idx])

    # ──────────────────────────────────────────────────────────────────────
    # CHAIN PV (dict-based)
    # ──────────────────────────────────────────────────────────────────────

    def get_chain_pv(
        self,
        chain: List[dict],
        ft_entry_time: Optional[float] = None,
    ) -> float:
        """Compute cumulative Goal Probability Added along a chain.

        Accepts either the new-style call (list of {x, y} dicts) or
        the legacy call with ``ft_entry_time`` from older code.

        When ``ft_entry_time`` is provided, events whose ``match_sec``
        is before that threshold are skipped, and only *positive*
        deltas are accumulated (legacy clamp behaviour).

        Otherwise, the PV telescopes to
        ``P(goal | last) - P(goal | first)``.

        Parameters
        ----------
        chain : list[dict]
            Ordered sequence of on-ball actions with at least 'x', 'y'.
            May also contain 'event_type', 'match_sec', 'pass_end_x',
            'pass_end_y', 'player_name'.
        ft_entry_time : float, optional
            If provided, use the legacy positive-delta-only accumulation
            starting from this match-second.

        Returns
        -------
        float
            Chain Possession Value.
        """
        if not chain:
            return 0.0

        # Legacy mode: positive-delta accumulation with FT entry filter
        if ft_entry_time is not None:
            return self._chain_pv_legacy(chain, ft_entry_time)

        # New mode: telescoping delta
        if len(chain) < 2:
            return 0.0

        first = chain[0]
        last  = chain[-1]
        gp_start = self.get_xT(float(first["x"]), float(first["y"]))
        gp_end   = self.get_xT(float(last["x"]),  float(last["y"]))
        return round(gp_end - gp_start, 6)

    def _chain_pv_legacy(
        self,
        events: List[dict],
        ft_entry_time: float,
    ) -> float:
        """Legacy chain PV: accumulate only positive xT deltas for
        passes from the FT entry point onward."""
        pv = 0.0
        for evt in events:
            et = str(evt.get("event_type", "")).strip().lower()
            x  = evt.get("x")
            y  = evt.get("y")
            sec = evt.get("match_sec", 0) or 0

            if sec < ft_entry_time:
                continue

            if pd.isna(x) or pd.isna(y):
                continue
            x_f, y_f = float(x), float(y)

            if et in ("pass", "offside pass", "blocked pass"):
                end_x = evt.get("pass_end_x")
                end_y = evt.get("pass_end_y")
                if pd.notna(end_x) and pd.notna(end_y):
                    xt_start = self.get_xT(x_f, y_f)
                    xt_end   = self.get_xT(float(end_x), float(end_y))
                    delta = max(xt_end - xt_start, 0.0)
                    pv += delta

        return round(pv, 4)

    # ──────────────────────────────────────────────────────────────────────
    # CHAIN PV (DataFrame-based -- used by ChanceCreationAnalyzer)
    # ──────────────────────────────────────────────────────────────────────

    def get_chain_pv_from_raw_events(
        self,
        events_df: pd.DataFrame,
        ft_entry_time: Optional[float] = None,
        shot_time: Optional[float] = None,
    ) -> float:
        """Compute chain PV from a DataFrame of raw match events.

        This slices the events between ``ft_entry_time`` and
        ``shot_time``, detects implicit carries, and sums the
        delta-P(goal) for each consecutive on-ball action.

        Parameters
        ----------
        events_df : pd.DataFrame
            Events for a single possession (or wider window).
        ft_entry_time : float, optional
            Match-second of the Final Third entry.
        shot_time : float, optional
            Match-second of the shot.

        Returns
        -------
        float
            Chain PV (delta-P sum).
        """
        df = events_df.copy()

        # Timing columns
        if "_match_sec" not in df.columns:
            df["_match_sec"] = (
                df.get("minute", df.get("time_min", pd.Series(0, index=df.index))).fillna(0) * 60
                + df.get("second", df.get("time_sec", pd.Series(0, index=df.index))).fillna(0)
            )

        # Filter to FT-entry -> shot window
        if ft_entry_time is not None:
            df = df[df["_match_sec"] >= ft_entry_time]
        if shot_time is not None:
            df = df[df["_match_sec"] <= shot_time]

        # Keep only on-ball events with valid coordinates
        chain_rows: list = []
        prev_player = None

        for _, row in df.iterrows():
            et = str(row.get("event_type", row.get("event", ""))).strip().lower()
            if et in NON_PLAY_EVENTS or et == "":
                continue
            if et not in ON_BALL_EVENTS:
                continue

            x, y = row.get("x"), row.get("y")
            if pd.isna(x) or pd.isna(y):
                continue
            x, y = float(x), float(y)

            player = str(row.get("player_name", "")).strip()

            # Detect implicit carry (same player, position changed)
            if (chain_rows and player == prev_player and player != ""):
                prev_x, prev_y = chain_rows[-1]
                if abs(x - prev_x) > X_STEP or abs(y - prev_y) > Y_STEP:
                    # Insert synthetic carry midpoint
                    mid_x = (prev_x + x) / 2
                    mid_y = (prev_y + y) / 2
                    chain_rows.append((mid_x, mid_y))

            chain_rows.append((x, y))
            prev_player = player

        if len(chain_rows) < 2:
            # Single-point chain: return the raw goal probability
            if chain_rows:
                return self.get_xT(chain_rows[0][0], chain_rows[0][1])
            return 0.0

        # Sum delta-P(goal) across consecutive actions
        pv = 0.0
        for i in range(1, len(chain_rows)):
            gp_before = self.get_xT(chain_rows[i - 1][0], chain_rows[i - 1][1])
            gp_after  = self.get_xT(chain_rows[i][0],     chain_rows[i][1])
            pv += (gp_after - gp_before)

        return round(pv, 6)

    # ──────────────────────────────────────────────────────────────────────
    # EXPORT / DEBUG
    # ──────────────────────────────────────────────────────────────────────

    def export_heatmap(self) -> np.ndarray:
        """Return the goal-probability grid as a NumPy array for heatmap
        visualisation."""
        return self.xT.copy()

    # ──────────────────────────────────────────────────────────────────────
    # VALIDATION
    # ──────────────────────────────────────────────────────────────────────

    def validate(self) -> dict:
        """Run basic sanity checks on the built model.

        Returns
        -------
        dict
            Validation summary with pass/fail flags and diagnostics.
        """
        checks: dict = {"passed": True, "details": {}}
        grid = self.xT  # may be goal_prob_grid or overridden

        # 1. Grid shape
        shape_ok = grid.shape == (X_ZONES, Y_ZONES)
        checks["details"]["grid_shape"] = {
            "ok": shape_ok,
            "shape": list(grid.shape),
        }
        if not shape_ok:
            checks["passed"] = False

        # 2. Values in [0, 1]
        vmin = float(grid.min())
        vmax = float(grid.max())
        range_ok = 0.0 <= vmin and vmax <= 1.0
        checks["details"]["grid_range"] = {
            "ok": range_ok,
            "min": round(vmin, 6),
            "max": round(vmax, 6),
        }
        if not range_ok:
            checks["passed"] = False

        # 3. Monotonicity (average by column should broadly increase)
        col_means = grid.mean(axis=1)
        monotonic_violations = sum(
            1 for i in range(1, len(col_means))
            if col_means[i] < col_means[i - 1] - 0.01
        )
        mono_ok = monotonic_violations <= 3
        checks["details"]["monotonicity"] = {
            "ok": mono_ok,
            "violations": monotonic_violations,
            "col_means": [round(float(v), 5) for v in col_means],
        }
        if not mono_ok:
            checks["passed"] = False

        # 4. ML models available
        checks["details"]["lr_available"]  = self.lr_model is not None
        checks["details"]["lgb_available"] = self.lgb_model is not None

        # 5. Stats
        checks["details"]["n_matches"] = self._n_matches
        checks["details"]["n_actions"] = self._n_actions

        return checks

    # ──────────────────────────────────────────────────────────────────────
    # PERSISTENCE
    # ──────────────────────────────────────────────────────────────────────

    _DEFAULT_FILENAME = "pv_model_gpa.pkl"

    def save(self, path: Optional[Path] = None) -> Path:
        """Persist the model to a pickle file.

        Parameters
        ----------
        path : Path, optional
            Target file.  Defaults to ``CACHE_DIR / pv_model_gpa.pkl``.

        Returns
        -------
        Path
            The path the model was saved to.
        """
        if path is None:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            path = CACHE_DIR / self._DEFAULT_FILENAME

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "goal_prob_grid":    self.xT,  # use self.xT (may be overridden)
            "xT":                self.xT,  # backward-compat alias
            "P_shot":            self.P_shot,
            "P_goal":            self.P_goal,
            "lr_model":          self.lr_model,
            "lgb_model":         self.lgb_model,
            "_n_matches":        self._n_matches,
            "_n_actions":        self._n_actions,
            "_poss_counts":      self._poss_counts,
            "_goal_poss_counts": self._goal_poss_counts,
            "_shot_counts":      self._shot_counts,
            "_goal_counts":      self._goal_counts,
        }
        with open(path, "wb") as f:
            pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)

        log.info("PV model saved to %s (%.1f MB)",
                 path, path.stat().st_size / 1_048_576)
        return path

    def load(self, path: Path) -> "PossessionValueModel":
        """Load a previously saved model from disk (instance method).

        Also works as a constructor-like pattern::

            model = PossessionValueModel()
            model.load(path)

        Parameters
        ----------
        path : Path
            Pickle file written by ``save()``.

        Returns
        -------
        PossessionValueModel
            ``self`` (mutated in-place), for chaining.

        Raises
        ------
        FileNotFoundError
            If *path* does not exist.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"PV model cache not found: {path}")

        with open(path, "rb") as f:
            payload = pickle.load(f)

        self.goal_prob_grid    = payload.get("goal_prob_grid",
                                              payload.get("xT",
                                              np.zeros((X_ZONES, Y_ZONES))))
        self.xT               = self.goal_prob_grid
        self.P_shot            = payload.get("P_shot",
                                              np.full((X_ZONES, Y_ZONES), 0.05))
        self.P_goal            = payload.get("P_goal",
                                              np.full((X_ZONES, Y_ZONES), 0.01))
        self.lr_model          = payload.get("lr_model")
        self.lgb_model         = payload.get("lgb_model")
        self._n_matches        = payload.get("_n_matches", 0)
        self._n_actions        = payload.get("_n_actions", 0)
        self._poss_counts      = payload.get("_poss_counts",
                                              np.zeros((X_ZONES, Y_ZONES)))
        self._goal_poss_counts = payload.get("_goal_poss_counts",
                                              np.zeros((X_ZONES, Y_ZONES)))
        self._shot_counts      = payload.get("_shot_counts",
                                              np.zeros((X_ZONES, Y_ZONES)))
        self._goal_counts      = payload.get("_goal_counts",
                                              np.zeros((X_ZONES, Y_ZONES)))
        self._built = True

        log.info("PV model loaded from %s (%d matches, %d actions)",
                 path, self._n_matches, self._n_actions)
        return self

    @classmethod
    def from_file(cls, path: Path) -> "PossessionValueModel":
        """Class-method alternative to ``load()`` — creates a new
        model instance and loads the pickle in one step.

        Parameters
        ----------
        path : Path
            Pickle file written by ``save()``.

        Returns
        -------
        PossessionValueModel
        """
        model = cls()
        model.load(path)
        return model


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLETON / FACTORY
# ═══════════════════════════════════════════════════════════════════════════════

_model_cache: Optional[PossessionValueModel] = None

# Legacy cache filename (pre-GPA rewrite)
_LEGACY_CACHE_FILENAME = "pv_model.pkl"


def get_pv_model(
    force_rebuild: bool = False,
    raw_dir: Optional[Path] = None,
) -> PossessionValueModel:
    """Return a shared ``PossessionValueModel`` instance.

    Load order:
      1. In-memory cache (fastest).
      2. Pickle on disk — ``pv_model_gpa.pkl`` (new format).
      3. Legacy pickle — ``pv_model.pkl`` (old format, backward compat).
      4. Fallback hand-calibrated grid (instant, always works).

    Building from scratch is **never** triggered during normal
    dashboard use — it must be run explicitly via CLI
    (``python -m src.analytics.possession_value --build``).

    Parameters
    ----------
    force_rebuild : bool
        If True, ignore cache and rebuild from data.
    raw_dir : Path, optional
        Override the raw-data directory.

    Returns
    -------
    PossessionValueModel
    """
    global _model_cache

    if _model_cache is not None and not force_rebuild:
        return _model_cache

    if force_rebuild:
        # Explicit rebuild requested (CLI only)
        try:
            model = PossessionValueModel()
            model.build(raw_dir=raw_dir)
            model.save()
            _model_cache = model
            return _model_cache
        except Exception as exc:
            log.error("PV model build failed: %s -- using fallback grid.", exc)
            model = PossessionValueModel()
            model._apply_fallback()
            _model_cache = model
            return _model_cache

    # 1. Try new GPA cache file
    cache_file = CACHE_DIR / PossessionValueModel._DEFAULT_FILENAME
    if cache_file.exists():
        try:
            model = PossessionValueModel()
            model.load(cache_file)
            _model_cache = model
            log.info("PV model loaded from %s", cache_file)
            return _model_cache
        except Exception as exc:
            log.warning("Could not load GPA cache %s: %s", cache_file, exc)

    # 2. Try legacy cache file (pre-GPA rewrite)
    legacy_file = CACHE_DIR / _LEGACY_CACHE_FILENAME
    if legacy_file.exists():
        try:
            model = PossessionValueModel()
            model.load(legacy_file)
            _model_cache = model
            log.info("PV model loaded from legacy cache %s", legacy_file)
            return _model_cache
        except Exception as exc:
            log.warning("Could not load legacy cache %s: %s", legacy_file, exc)

    # 3. Fallback — instant hand-calibrated grid (no I/O)
    log.warning(
        "No PV model cache found. Using fallback grid. "
        "Run `python -m src.analytics.possession_value --build` to train."
    )
    model = PossessionValueModel()
    model._apply_fallback()
    _model_cache = model
    return _model_cache


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    import json
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(name)-30s  %(levelname)-7s  %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Build / validate the GPA Possession Value model.",
    )
    parser.add_argument(
        "--build", action="store_true",
        help="(Re)build the model from all raw data and save to cache.",
    )
    parser.add_argument(
        "--validate", action="store_true",
        help="Load the cached model and run validation checks.",
    )
    parser.add_argument(
        "--max-matches", type=int, default=None,
        help="Limit the number of matches processed (debug).",
    )
    parser.add_argument(
        "--print-grid", action="store_true",
        help="Print the 16x12 goal-probability grid as JSON.",
    )
    args = parser.parse_args()

    if args.build:
        m = PossessionValueModel()
        m.build(max_matches=args.max_matches)
        path = m.save()
        print(f"Model built and saved to {path}")

        v = m.validate()
        print(json.dumps(v, indent=2, default=str))

        if args.print_grid:
            grid = m.goal_prob_grid.tolist()
            print("\n-- Goal Probability Grid (16x12) --")
            print(json.dumps(grid, indent=2))

    elif args.validate:
        m = get_pv_model()
        v = m.validate()
        print(json.dumps(v, indent=2, default=str))
        sys.exit(0 if v["passed"] else 1)

    elif args.print_grid:
        m = get_pv_model()
        grid = m.goal_prob_grid.tolist()
        print(json.dumps(grid, indent=2))

    else:
        parser.print_help()
