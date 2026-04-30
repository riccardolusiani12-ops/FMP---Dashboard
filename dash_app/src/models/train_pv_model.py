"""
Possession Value — Training Pipeline (Tasks 1-2-3)
====================================================
Trains an ML model to estimate P(goal | game_state) for every on-ball
event in a possession chain.  The resulting model replaces the old xT
grid (pv_model_serie_a.pkl) with a supervised classifier.

Usage (from the repo root, with sports_analytics conda env active):

    cd /Users/ricki/Local\ Projects/FMP_SerieA_Dashboard
    conda run -n sports_analytics python dash_app/src/models/train_pv_model.py

Output:
    data/serie_a_pv_features.parquet      ← engineered feature dataset
    dash_app/src/models/pv_model_serie_a.pkl  ← best model (overwrites old)
    dash_app/src/models/pv_feature_importance.png

Coordinate system (Opta standard):
    x: 0 → 100  (own goal → opponent goal)
    y: 0 → 100  (right touchline → left touchline)
    Final Third: x ≥ 66.67
    Penalty Box: x ≥ 83.33 AND 21.1 ≤ y ≤ 78.9
"""

from __future__ import annotations

import logging
import math
import pickle
import sys
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless rendering
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("train_pv_model")

# ─── Paths ────────────────────────────────────────────────────────────────────

_REPO_ROOT   = Path(__file__).resolve().parents[3]
_DATA_DIR    = _REPO_ROOT / "data"
_MODELS_DIR  = Path(__file__).parent

LABELLED_PARQUET = _DATA_DIR / "serie_a_pv_labelled.parquet"
FEATURES_PARQUET = _DATA_DIR / "serie_a_pv_features.parquet"
MODEL_PKL        = _MODELS_DIR / "pv_model_serie_a.pkl"
FI_PNG           = _MODELS_DIR / "pv_feature_importance.png"

# ─── Temporal splits ──────────────────────────────────────────────────────────

# Raw event CSVs available in data/raw/: 2021-2022 → 2025-2026
TRAIN_SEASONS = ["2021-2022"]
VAL_SEASONS   = ["2022-2023", "2023-2024"]
TEST_SEASONS  = ["2024-2025"]
# 2025-2026 excluded (season in progress — no data leakage)


# ═══════════════════════════════════════════════════════════════════════════════
# TASK 1 — FEATURE ENGINEERING
# ═══════════════════════════════════════════════════════════════════════════════

def _compute_dist_to_goal(x: pd.Series, y: pd.Series) -> pd.Series:
    """Euclidean distance to centre of the opponent goal (100, 50)."""
    return np.sqrt((100.0 - x) ** 2 + (50.0 - y) ** 2)


def _compute_angle_to_goal(x: pd.Series, y: pd.Series) -> pd.Series:
    """
    Angle subtended by the goal posts at location (x, y), in degrees.
    Goal posts at (100, 50 ± 3.66) — Opta equivalent of 7.32 m goal.
    """
    # Half-width of goal in Opta units: 7.32 m ≈ 3.66 Opta units
    half_goal = 3.66
    dx = 100.0 - x
    dy_sq = (y - 50.0) ** 2
    numerator  = 2.0 * half_goal * dx
    denominator = dx ** 2 + dy_sq - half_goal ** 2
    # Use arctan2 to preserve sign; take absolute value → always positive angle
    angle_rad = np.arctan2(numerator, denominator)
    angle_rad = angle_rad.where(angle_rad > 0, angle_rad + math.pi)
    return np.degrees(angle_rad)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Engineer all features on the raw labelled parquet.

    Parameters
    ----------
    df : pd.DataFrame
        Raw labelled dataset (from serie_a_pv_labelled.parquet).

    Returns
    -------
    pd.DataFrame
        Original columns + engineered features.
    """
    log.info("Building features on %d rows…", len(df))
    t0 = time.time()

    # ── Pre-clean: numeric coercions ──────────────────────────────────────
    for col in ("x", "y", "type_id", "outcome", "distance_to_goal",
                "angle_to_goal", "through_ball", "cross", "head", "aerial"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Log NaN rates BEFORE fill
    log.info("NaN rates before fillna:")
    nan_report_cols = ["x", "y", "distance_to_goal", "angle_to_goal",
                       "through_ball", "cross", "head", "aerial",
                       "type_id", "outcome"]
    for col in nan_report_cols:
        if col in df.columns:
            pct = df[col].isna().mean() * 100
            log.info("  %-25s  %6.2f %%", col, pct)

    # Drop rows with missing coordinates (can't compute spatial features)
    before = len(df)
    df = df.dropna(subset=["x", "y"])
    log.info("Dropped %d rows with null x/y  (%d remain)", before - len(df), len(df))

    # ── Fill remaining NaN ────────────────────────────────────────────────
    df["type_id"]  = df["type_id"].fillna(1).astype(int)
    df["outcome"]  = df["outcome"].fillna(0)

    for col in ("through_ball", "cross", "head", "aerial"):
        if col in df.columns:
            df[col] = df[col].fillna(0)
        else:
            df[col] = 0

    # ── Spatial features ──────────────────────────────────────────────────
    df["x2"] = df["x"] ** 2
    df["y2"] = df["y"] ** 2
    df["xy"] = df["x"] * df["y"]

    # dist_to_goal: use existing column if populated, else recalculate
    if "distance_to_goal" in df.columns:
        missing = df["distance_to_goal"].isna()
        df.loc[missing, "distance_to_goal"] = _compute_dist_to_goal(
            df.loc[missing, "x"], df.loc[missing, "y"]
        )
        df["dist_to_goal"] = df["distance_to_goal"].fillna(0)
    else:
        df["dist_to_goal"] = _compute_dist_to_goal(df["x"], df["y"])

    # angle_to_goal: use existing column if populated, else recalculate
    if "angle_to_goal" in df.columns:
        missing = df["angle_to_goal"].isna()
        df.loc[missing, "angle_to_goal"] = _compute_angle_to_goal(
            df.loc[missing, "x"], df.loc[missing, "y"]
        )
        df["angle_to_goal"] = df["angle_to_goal"].fillna(0)
    else:
        df["angle_to_goal"] = _compute_angle_to_goal(df["x"], df["y"])

    df["in_box"] = (
        (df["x"] >= 83.33) & (df["y"] >= 21.1) & (df["y"] <= 78.9)
    ).astype(int)
    df["in_final_third"]   = (df["x"] >= 66.67).astype(int)
    df["central_corridor"] = ((df["y"] >= 33.3) & (df["y"] <= 66.7)).astype(int)
    df["dist_to_center_y"] = (df["y"] - 50.0).abs()

    # ── Event features ────────────────────────────────────────────────────
    df["is_pass"]          = (df["type_id"] == 1).astype(int)
    df["is_carry_touch"]   = (df["type_id"] == 44).astype(int)
    df["is_recovery"]      = (df["type_id"] == 49).astype(int)
    df["is_tackle"]        = (df["type_id"] == 7).astype(int)
    df["is_interception"]  = (df["type_id"] == 8).astype(int)

    # ── Possession features ───────────────────────────────────────────────
    log.info("Computing possession-level features (cumcount, cummax)…")
    df = df.sort_values(["poss_id", "minute", "second", "event_id"],
                        na_position="last")

    df["poss_event_index"]      = df.groupby("poss_id").cumcount()
    df["events_in_poss_so_far"] = df["poss_event_index"]  # alias

    df["x_max_in_poss_so_far"]  = (
        df.groupby("poss_id")["x"].cummax().astype(float)
    )

    log.info("Feature engineering done in %.1f s", time.time() - t0)

    # ── Label distribution ────────────────────────────────────────────────
    log.info("\nLabel: ends_in_goal")
    vc = df["ends_in_goal"].value_counts(normalize=True)
    log.info("  0 (no goal):  %6.2f %%", vc.get(False, vc.get(0, 0)) * 100)
    log.info("  1 (goal):     %6.2f %%", vc.get(True,  vc.get(1, 0)) * 100)

    return df


FEATURE_COLS = [
    # Spatial
    "x", "y", "x2", "y2", "xy",
    "dist_to_goal", "angle_to_goal",
    "in_box", "in_final_third", "central_corridor", "dist_to_center_y",
    # Event
    "type_id", "outcome",
    "is_pass", "is_carry_touch", "is_recovery", "is_tackle", "is_interception",
    "through_ball", "cross", "head", "aerial",
    # Possession context
    "poss_event_index", "x_max_in_poss_so_far",
]

LABEL_COL = "ends_in_goal"

ID_COLS = [
    "match_id", "season", "event_id", "team_id", "team_name",
    "player_id", "player_name", "poss_id", "ends_in_shot",
]


# ─── Raw-CSV season → label map ─────────────────────────────────────────────
_RAW_DIR = _DATA_DIR / "raw"

# Event type IDs to keep (exclude type_id 34 = Team setup, 30/32/35 etc)
_KEEP_TYPE_IDS = {
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16,
    41, 44, 49, 50, 61, 74,
}
_SHOT_TYPE_IDS = {13, 14, 15, 16}


def _season_from_folder(folder_name: str) -> str:
    """'serie_a_2024_2025' → '2024-2025'"""
    parts = folder_name.replace("serie_a_", "").split("_")
    return f"{parts[0]}-{parts[1]}"


def _build_labelled_from_raw() -> pd.DataFrame:
    """
    Build serie_a_pv_labelled.parquet from scratch by reading all
    raw event CSV files in data/raw/serie_a_YYYY_YYYY/events/.

    Steps:
    1. Read every CSV, tag with season
    2. Sort globally: match_id → period → time
    3. Build poss_id (team change OR time gap > 5 s)
    4. Label possessions: ends_in_shot, ends_in_goal
    5. Exclude shots from the training rows (data leakage)
    6. Save parquet and return df
    """
    log.info("Building labelled dataset from raw CSVs in %s …", _RAW_DIR)

    season_dirs = sorted(_RAW_DIR.glob("serie_a_*"))
    if not season_dirs:
        log.error("No raw season directories found in %s", _RAW_DIR)
        sys.exit(1)

    # Columns we actually need (CSV names — will be renamed below)
    _CSV_COLS = [
        "event_id", "type_id", "period_id", "time_min", "time_sec",
        "contestant_id", "team_name", "player_id", "player_name",
        "x", "y", "outcome", "match_id",
        "Cross", "Through ball", "Head", "Pass End X", "Pass End Y",
    ]

    chunks: list[pd.DataFrame] = []

    for season_dir in season_dirs:
        season = _season_from_folder(season_dir.name)
        events_dir = season_dir / "events"
        if not events_dir.exists():
            log.warning("No events/ folder in %s — skipping", season_dir.name)
            continue

        csv_files = sorted(events_dir.glob("*.csv"))
        log.info("  %s  →  %d CSV files", season, len(csv_files))

        for csv_path in csv_files:
            try:
                raw = pd.read_csv(
                    csv_path,
                    usecols=lambda c: c in _CSV_COLS,
                    low_memory=False,
                    na_values=["N/A", "", "None"],
                )
            except Exception as exc:
                log.warning("    skipping %s: %s", csv_path.name, exc)
                continue

            # Keep only play events
            raw["type_id"] = pd.to_numeric(raw["type_id"], errors="coerce")
            raw = raw[raw["type_id"].isin(_KEEP_TYPE_IDS)].copy()
            if raw.empty:
                continue

            raw["season"] = season
            chunks.append(raw)

    if not chunks:
        log.error("No data loaded from raw CSVs.")
        sys.exit(1)

    log.info("Concatenating %d chunks …", len(chunks))
    df = pd.concat(chunks, ignore_index=True)
    log.info("Total rows: %d", len(df))

    # ── Rename columns ──────────────────────────────────────────────────
    df = df.rename(columns={
        "contestant_id": "team_id",
        "time_min":      "minute",
        "time_sec":      "second",
        "Cross":         "cross",
        "Through ball":  "through_ball",
        "Head":          "head",
        "Pass End X":    "pass_end_x",
        "Pass End Y":    "pass_end_y",
    })

    # aerial not available as a direct CSV qualifier column → default 0
    df["aerial"] = 0

    # ── Numeric coercions ───────────────────────────────────────────────
    for col in ("x", "y", "outcome", "cross", "through_ball", "head",
                "pass_end_x", "pass_end_y"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Binary qualifier flags: 1 if the qualifier is present, 0 otherwise
    for col in ("cross", "through_ball", "head", "aerial"):
        df[col] = df[col].notna().astype(int) if df[col].dtype == object \
            else df[col].fillna(0).astype(int)

    # ── Sort globally ───────────────────────────────────────────────────
    df["minute"] = pd.to_numeric(df["minute"], errors="coerce").fillna(0)
    df["second"] = pd.to_numeric(df["second"], errors="coerce").fillna(0)
    df["_match_sec"] = df["minute"] * 60 + df["second"]
    df = df.sort_values(
        ["match_id", "period_id", "minute", "second", "event_id"],
        na_position="last",
    ).reset_index(drop=True)

    # ── Build possession IDs ────────────────────────────────────────────
    log.info("Building possession IDs …")
    team_change  = df["team_id"] != df["team_id"].shift(1)
    match_change = df["match_id"] != df["match_id"].shift(1)
    time_gap     = df["_match_sec"].diff().abs() > 5.0
    df["poss_id"] = (team_change | match_change | time_gap).cumsum()

    # ── Label possessions ───────────────────────────────────────────────
    log.info("Labelling possessions …")
    shot_mask = df["type_id"].isin(_SHOT_TYPE_IDS)
    goal_mask = df["type_id"] == 16

    poss_has_shot = df.groupby("poss_id")["type_id"].transform(
        lambda s: s.isin(_SHOT_TYPE_IDS).any()
    )
    poss_has_goal = df.groupby("poss_id")["type_id"].transform(
        lambda s: (s == 16).any()
    )

    df["ends_in_shot"] = poss_has_shot.astype(int)
    df["ends_in_goal"] = poss_has_goal.astype(int)

    # Exclude shots from training rows (keep them only for context)
    df = df[~shot_mask].copy()
    log.info("After excluding shots: %d rows", len(df))

    # ── Save labelled parquet ───────────────────────────────────────────
    log.info("Saving %s …", LABELLED_PARQUET)
    df = df.drop(columns=["_match_sec"], errors="ignore")
    df.to_parquet(LABELLED_PARQUET, index=False)
    log.info("Saved labelled parquet: %d rows × %d cols", *df.shape)

    # label distribution
    pct_goal = df["ends_in_goal"].mean() * 100
    log.info("ends_in_goal positive rate: %.3f %%", pct_goal)

    return df


def run_task1() -> pd.DataFrame:
    """Feature engineering — Task 1."""
    log.info("=" * 60)
    log.info("TASK 1 — Feature Engineering")
    log.info("=" * 60)

    # Try to load the pre-built parquet; fall back to raw CSVs if missing/corrupt
    df = None
    if LABELLED_PARQUET.exists():
        try:
            log.info("Loading %s …", LABELLED_PARQUET.name)
            df = pd.read_parquet(LABELLED_PARQUET)
            log.info("Loaded: %d rows × %d cols", *df.shape)
        except Exception as exc:
            log.warning("Could not read labelled parquet (%s) — rebuilding from raw CSVs", exc)
            df = None

    if df is None:
        log.info("Building labelled dataset from raw event CSVs …")
        df = _build_labelled_from_raw()
        log.info("Labelled dataset built: %d rows", len(df))

    df = build_features(df)

    # Verify all feature columns are present
    missing_feats = [c for c in FEATURE_COLS if c not in df.columns]
    if missing_feats:
        log.error("Missing feature columns after engineering: %s", missing_feats)
        sys.exit(1)

    log.info("Feature columns (%d):", len(FEATURE_COLS))
    for c in FEATURE_COLS:
        log.info("  • %s", c)

    log.info("Saving features parquet → %s", FEATURES_PARQUET)
    df.to_parquet(FEATURES_PARQUET, index=False)
    log.info("Saved: %d rows × %d cols", *df.shape)

    return df


# ═══════════════════════════════════════════════════════════════════════════════
# TASK 2 — TRAINING
# ═══════════════════════════════════════════════════════════════════════════════

def _split(df: pd.DataFrame):
    """Temporal split by season string."""
    train = df[df["season"].isin(TRAIN_SEASONS)]
    val   = df[df["season"].isin(VAL_SEASONS)]
    test  = df[df["season"].isin(TEST_SEASONS)]

    log.info("Split sizes — train: %d  val: %d  test: %d",
             len(train), len(val), len(test))

    X_train = train[FEATURE_COLS].fillna(0).values.astype(np.float32)
    y_train = train[LABEL_COL].fillna(0).astype(int).values

    X_val   = val[FEATURE_COLS].fillna(0).values.astype(np.float32)
    y_val   = val[LABEL_COL].fillna(0).astype(int).values

    X_test  = test[FEATURE_COLS].fillna(0).values.astype(np.float32)
    y_test  = test[LABEL_COL].fillna(0).astype(int).values

    return X_train, y_train, X_val, y_val, X_test, y_test


def _evaluate(name: str, y_true, y_prob, threshold: float = 0.5) -> dict:
    """Compute and log evaluation metrics."""
    from sklearn.metrics import (
        roc_auc_score, average_precision_score, brier_score_loss,
        precision_score, recall_score, f1_score,
    )

    roc   = roc_auc_score(y_true, y_prob)
    ap    = average_precision_score(y_true, y_prob)
    bs    = brier_score_loss(y_true, y_prob)

    y_pred_05 = (y_prob >= 0.5).astype(int)
    p05 = precision_score(y_true, y_pred_05, zero_division=0)
    r05 = recall_score(y_true, y_pred_05, zero_division=0)
    f05 = f1_score(y_true, y_pred_05, zero_division=0)

    # Optimal threshold (max F1)
    from sklearn.metrics import precision_recall_curve
    prec, rec, thresholds = precision_recall_curve(y_true, y_prob)
    f1_scores = 2 * prec * rec / np.where(prec + rec == 0, 1, prec + rec)
    opt_idx = np.argmax(f1_scores[:-1])  # last element has no threshold
    opt_thr = thresholds[opt_idx]
    y_pred_opt = (y_prob >= opt_thr).astype(int)
    p_opt = precision_score(y_true, y_pred_opt, zero_division=0)
    r_opt = recall_score(y_true, y_pred_opt, zero_division=0)
    f_opt = f1_score(y_true, y_pred_opt, zero_division=0)

    log.info("")
    log.info("  ── %s ──", name)
    log.info("  ROC-AUC          : %.4f", roc)
    log.info("  Avg Precision    : %.4f", ap)
    log.info("  Brier Score      : %.4f  (lower=better)", bs)
    log.info("  @ thr=0.5  P=%.3f  R=%.3f  F1=%.3f", p05, r05, f05)
    log.info("  @ thr=%.3f P=%.3f  R=%.3f  F1=%.3f  (opt)", opt_thr, p_opt, r_opt, f_opt)

    return {
        "roc_auc": roc,
        "avg_precision": ap,
        "brier_score": bs,
        "prec_05": p05, "rec_05": r05, "f1_05": f05,
        "opt_threshold": opt_thr,
        "prec_opt": p_opt, "rec_opt": r_opt, "f1_opt": f_opt,
    }


def train_logistic_regression(X_train, y_train, X_val, y_val, X_test, y_test):
    """Train logistic regression with StandardScaler."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    log.info("\n  Training Logistic Regression…")
    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_train)
    X_val_s = scaler.transform(X_val)
    X_test_s = scaler.transform(X_test)

    t0 = time.time()
    model = LogisticRegression(
        C=1.0, max_iter=1000, solver="lbfgs",
        class_weight="balanced", n_jobs=-1,
    )
    model.fit(X_tr_s, y_train)
    log.info("  LR training done in %.1f s", time.time() - t0)

    prob_val  = model.predict_proba(X_val_s)[:, 1]
    prob_test = model.predict_proba(X_test_s)[:, 1]

    log.info("  Validation set:")
    metrics_val  = _evaluate("LR — Val", y_val, prob_val)
    log.info("  Test set:")
    metrics_test = _evaluate("LR — Test", y_test, prob_test)

    return model, scaler, metrics_val, metrics_test


def train_xgboost(X_train, y_train, X_val, y_val, X_test, y_test):
    """Train XGBoost with scale_pos_weight and early stopping."""
    try:
        import xgboost as xgb
    except ImportError:
        log.error("xgboost not installed. Run: pip install xgboost")
        return None, None, None

    n_neg = int((y_train == 0).sum())
    n_pos = int((y_train == 1).sum())
    spw   = n_neg / n_pos
    log.info("\n  Training XGBoost  (scale_pos_weight=%.1f)…", spw)

    model = xgb.XGBClassifier(
        n_estimators=500,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=spw,
        eval_metric="aucpr",
        use_label_encoder=False,
        tree_method="hist",       # faster on large datasets
        n_jobs=-1,
        verbosity=0,
        random_state=42,
    )

    t0 = time.time()
    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        early_stopping_rounds=30,
        verbose=50,
    )
    log.info("  XGBoost training done in %.1f s  (best iter=%d)",
             time.time() - t0, model.best_iteration)

    prob_val  = model.predict_proba(X_val)[:, 1]
    prob_test = model.predict_proba(X_test)[:, 1]

    log.info("  Validation set:")
    metrics_val  = _evaluate("XGB — Val", y_val, prob_val)
    log.info("  Test set:")
    metrics_test = _evaluate("XGB — Test", y_test, prob_test)

    return model, spw, metrics_val, metrics_test


def _plot_feature_importance(model, model_type: str, feature_names: list[str]) -> None:
    """Plot and save top-15 feature importances."""
    if model_type == "xgboost":
        scores = model.feature_importances_
        title = "XGBoost Feature Importance (gain)"
    else:
        scores = np.abs(model.coef_[0])
        title = "Logistic Regression |Coefficient|"

    idx  = np.argsort(scores)[-15:]
    names = [feature_names[i] for i in idx]
    vals  = scores[idx]

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.barh(names, vals, color="#4C72B0")
    ax.set_xlabel("Importance")
    ax.set_title(title)
    plt.tight_layout()
    fig.savefig(FI_PNG, dpi=150)
    plt.close(fig)
    log.info("Feature importance plot saved → %s", FI_PNG)


def _plot_calibration(y_true, prob, label: str) -> None:
    """Reliability diagram."""
    from sklearn.calibration import calibration_curve

    fig, ax = plt.subplots(figsize=(6, 5))
    frac_pos, mean_pred = calibration_curve(y_true, prob, n_bins=20)
    ax.plot(mean_pred, frac_pos, marker="o", label=label)
    ax.plot([0, 1], [0, 1], "k--", label="Perfect calibration")
    ax.set_xlabel("Mean predicted probability")
    ax.set_ylabel("Fraction of positives")
    ax.set_title("Reliability Diagram")
    ax.legend()
    plt.tight_layout()
    cal_path = FI_PNG.parent / "pv_calibration_curve.png"
    fig.savefig(cal_path, dpi=150)
    plt.close(fig)
    log.info("Calibration curve saved → %s", cal_path)


def run_task2(df: pd.DataFrame) -> tuple:
    """Training — Task 2."""
    log.info("\n%s", "=" * 60)
    log.info("TASK 2 — Training Models")
    log.info("=" * 60)

    X_train, y_train, X_val, y_val, X_test, y_test = _split(df)

    log.info("Label distribution — train: %.3f%% positives  val: %.3f%%  test: %.3f%%",
             y_train.mean() * 100, y_val.mean() * 100, y_test.mean() * 100)

    # ── Logistic Regression ───────────────────────────────────────────────
    lr_model, scaler, lr_val_metrics, lr_test_metrics = \
        train_logistic_regression(X_train, y_train, X_val, y_val, X_test, y_test)

    # ── XGBoost ───────────────────────────────────────────────────────────
    xgb_result = train_xgboost(X_train, y_train, X_val, y_val, X_test, y_test)
    xgb_model, spw, xgb_val_metrics, xgb_test_metrics = xgb_result \
        if len(xgb_result) == 4 else (None, None, None, None)

    # ── Model selection ───────────────────────────────────────────────────
    log.info("\n%s", "─" * 60)
    log.info("Model selection (ROC-AUC on validation set):")
    lr_auc  = lr_val_metrics["roc_auc"]
    xgb_auc = xgb_val_metrics["roc_auc"] if xgb_val_metrics else -1.0

    log.info("  Logistic Regression : %.4f", lr_auc)
    log.info("  XGBoost             : %.4f", xgb_auc)

    if xgb_model is not None and (xgb_auc - lr_auc) > 0.002:
        best_model      = xgb_model
        best_type       = "xgboost"
        best_scaler     = None
        best_val_m      = xgb_val_metrics
        best_test_m     = xgb_test_metrics
        best_spw        = spw
        log.info("  → Winner: XGBoost (Δ=%.4f)", xgb_auc - lr_auc)
    else:
        best_model      = lr_model
        best_type       = "logistic_regression"
        best_scaler     = scaler
        best_val_m      = lr_val_metrics
        best_test_m     = lr_test_metrics
        best_spw        = None
        log.info("  → Winner: Logistic Regression (≤0.002 diff or XGB unavailable)")

    # ── Calibration check ─────────────────────────────────────────────────
    if best_type == "xgboost":
        prob_val = best_model.predict_proba(X_val)[:, 1]
    else:
        X_val_s = scaler.transform(X_val)
        prob_val = best_model.predict_proba(X_val_s)[:, 1]
    _plot_calibration(y_val, prob_val, label=best_type)

    # ── Feature importance plot ────────────────────────────────────────────
    _plot_feature_importance(best_model, best_type, FEATURE_COLS)

    return (
        best_model, best_type, best_scaler, best_val_m, best_test_m,
        best_spw,
        lr_val_metrics, xgb_val_metrics,
        len(X_train), len(X_val), len(X_test),
        int((y_train == 0).sum()) / max(int((y_train == 1).sum()), 1),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# TASK 3 — SAVE MODEL
# ═══════════════════════════════════════════════════════════════════════════════

def run_task3(
    best_model,
    best_type: str,
    best_scaler,
    best_val_m: dict,
    best_test_m: dict,
    best_spw: float | None,
    n_train: int,
    _spw_full: float,
) -> None:
    """Serialize the winning model as a unified pkl dict — Task 3."""
    log.info("\n%s", "=" * 60)
    log.info("TASK 3 — Saving Model")
    log.info("=" * 60)

    payload = {
        "model":             best_model,
        "model_type":        best_type,
        "scaler":            best_scaler,    # StandardScaler | None
        "feature_cols":      FEATURE_COLS,
        "label":             LABEL_COL,
        "trained_on":        "Italy_Serie_A",
        "train_seasons":     "2008-2009 → 2021-2022",
        "val_seasons":       "2022-2023 → 2023-2024",
        "test_season":       "2024-2025",
        "roc_auc_val":       round(best_val_m["roc_auc"], 4),
        "roc_auc_test":      round(best_test_m["roc_auc"], 4),
        "avg_precision_val": round(best_val_m["avg_precision"], 4),
        "brier_score_val":   round(best_val_m["brier_score"], 4),
        "n_train":           n_train,
        "n_features":        len(FEATURE_COLS),
        "scale_pos_weight":  best_spw,       # float | None
    }

    MODEL_PKL.parent.mkdir(parents=True, exist_ok=True)
    with open(MODEL_PKL, "wb") as fh:
        pickle.dump(payload, fh, protocol=5)

    log.info("Model saved → %s", MODEL_PKL)
    log.info("  model_type       : %s", best_type)
    log.info("  roc_auc_val      : %.4f", payload["roc_auc_val"])
    log.info("  roc_auc_test     : %.4f", payload["roc_auc_test"])
    log.info("  avg_precision_val: %.4f", payload["avg_precision_val"])
    log.info("  n_train          : %d", n_train)
    log.info("  n_features       : %d", len(FEATURE_COLS))


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    t_start = time.time()

    # Task 1
    df = run_task1()

    # Task 2
    results = run_task2(df)
    (
        best_model, best_type, best_scaler,
        best_val_m, best_test_m,
        best_spw,
        lr_val_m, xgb_val_m,
        n_train, n_val, n_test,
        spw_full,
    ) = results

    # Task 3
    run_task3(
        best_model, best_type, best_scaler,
        best_val_m, best_test_m, best_spw,
        n_train, spw_full,
    )

    log.info("\nTotal pipeline time: %.1f s", time.time() - t_start)
    log.info("Done ✓")


if __name__ == "__main__":
    main()
