# Player Analysis (Season) — Methodology

> **Dashboard location:** Opponent Analysis → Player Analysis (season, per team)
> **Analysis type:** Season-aggregate (per player, within-role league percentiles)
> **Primary source file(s):** `analytics/season_player_analysis.py` (`aggregate_team_season`, `estimate_k_per_metric`, `apply_shrinkage`, `precompute_season_players`); per-match `analytics/player_analysis.py`; UI `components/opp_season_player_cards.py`
> **Precomputed parquet(s):** `player_season_{season}.parquet`; sidecar `player_season_{season}_k_table.json`
> **Last reviewed:** 2026-06-24

---

## 1 — Purpose

Player Analysis profiles every player who featured for a team across a season, scoring them on role-appropriate per-90 KPIs and ranking each within their positional peer group across all 20 Serie A clubs. It lets an analyst quickly read a squad's strengths by role — who presses, who progresses, who creates — on a like-for-like basis, with small-sample noise controlled by empirical-Bayes shrinkage.

---

## 2 — Input Data

- **Event types used:** inherited from the per-match player bundle (`analyse_player_analysis`) — minutes, in/out-of-possession KPI counts, PVA, regains, position/role.
- **Qualifiers used:** position/formation-slot tagging for role assignment; KPI-specific qualifiers (e.g. `Switch of play`).
- **Coordinate system:** not directly (player KPIs are counts/rates).
- **Seasons covered:** all (2021/22–2025/26).
- **Scope:** season-aggregate per player.

---

## 3 — Methodology

### 3.1 — Per-match bundle, computed once
Each match's player bundle (minutes, KPIs, PVA) is computed once (it covers both teams) and routed to both teams' accumulators, avoiding duplicate PV work.

### 3.2 — Role taxonomy & assignment
Granular Opta positions map via `ROLE_GROUP_MAP` to role groups in `ROLE_GROUP_ORDER`: **GK, CB, FB, DM, CM, WM, AM, W, CF, UNCL** (Unclassified). A player's role is decided by **minutes-weighted voting**: for every match they *started*, the minutes are credited to that match's role; the role group with the most started-minutes wins.

### 3.3 — Minutes threshold (dim, not drop)
`MIN_MINUTES_DIM = 450.0` (~5 full matches). Players below 450 minutes are **kept but flagged `low_minutes`** and dimmed in the UI — they are never dropped. Percentile/role-mean computations qualify on `minutes ≥ 450` so low-minute players don't distort the peer baseline.

### 3.4 — Partial-season flag
`partial_season = True` when a player featured in fewer than `PARTIAL_SEASON_THRESHOLD = 50%` of the team's matchdays.

### 3.5 — Per-90 normalisation
Counting KPIs are aggregated as season totals, then normalised per 90 minutes (`total ÷ minutes × 90`). Raw `{metric}` columns are kept.

### 3.6 — Empirical-Bayes shrinkage (IMPLEMENTED — Phase 1)
For every per-90 metric, a shrinkage constant **K (in minutes)** is estimated per role group via split-half reliability (`estimate_k_per_metric`, using per-match (minute, count) series stored in the parquet so K can be re-derived without re-precompute). `apply_shrinkage` then adds an `{metric}_adj` column:

```
w = minutes / (minutes + K)
adj = w · observed_per90 + (1 − w) · role_group_mean
```

Low-minute players are pulled toward their role-group mean (weight inversely proportional to minutes); high-minute players keep their observed rate. Unclassified players get `adj == raw` (no role prior). A `{metric}_p90_adj` column is what the UI **ranks and percentiles** on; the raw per-90 is shown on hover for transparency. The K-table is persisted as a JSON sidecar for the thesis methodology.

### 3.7 — Within-role league percentiles
Percentile ranks are computed **within role group across all 20 clubs**, on the shrinkage-adjusted per-90 value, qualifying on `minutes ≥ 450`.

---

## 4 — Key Metrics & Definitions

- **Role group:** GK/CB/FB/DM/CM/WM/AM/W/CF/UNCL via minutes-weighted started-role voting.
- **Per-90 KPIs:** role-appropriate in/out-of-possession rates and PVA per 90.
- **`{metric}_p90_adj`:** shrinkage-adjusted per-90 (ranked value).
- **Within-role percentile:** rank vs. same-role players league-wide (on the adjusted value, ≥450′ qualified).
- **`low_minutes` flag:** minutes < 450 (dimmed).
- **`partial_season` flag:** featured in < 50% of matchdays.

---

## 5 — Outputs

- **Parquet `player_season_{season}.parquet`:** one row per player with team, role_group, minutes, appearances, starts, raw per-90 metrics, `{metric}_adj` / `{metric}_p90_adj`, flags, and per-match (minute,count) series JSON.
- **Sidecar:** `player_season_{season}_k_table.json` (K and role means per metric).
- **Visual outputs:** player-card grid with percentile bars, role filter, season selector; low-minute/partial dimming.

---

## 6 — Methodological Decisions & Rationale

- **Minutes-weighted most-frequent role:** a utility player who mostly started at CM is ranked as a CM, even if they occasionally filled in elsewhere — using started-minutes weights avoids letting brief cameos mislabel a player.
- **450-minute dim-not-drop:** ~5 full matches is enough to have *some* signal; dropping low-minute players hides squad depth, so they are kept but visually de-emphasised and excluded from the peer baseline.
- **Per-90 over per-match/raw:** per-90 makes starters, substitutes, and rotation players comparable on rate, not on accumulated volume.
- **Empirical-Bayes shrinkage (implemented):** small-sample per-90 rates are noisy and can hand a low-minute player an extreme percentile (the Asllani Inter 2024/25 scenario). Pulling each rate toward the role-group mean, weighted by minutes, damps that noise while leaving high-minute players' rates intact — and ranking on the adjusted value makes percentiles trustworthy. The per-match series and K-table are persisted so the shrinkage is reproducible and auditable.
- **Within-role percentiles:** comparing a full-back's progression to other full-backs (not to centre-backs or wingers) is the only fair benchmark.

---

## 7 — Limitations & Known Issues

- **Spec discrepancy (documented, code wins):** the audit brief described empirical-Bayes shrinkage as "identified, planned, not yet implemented". It is in fact **implemented** (`estimate_k_per_metric` + `apply_shrinkage`, called in `precompute_season_players`; the UI ranks on `{metric}_p90_adj`). This methodology documents it as live (Phase 1).
- **Role assignment needs starts:** a player who almost never started has weak role votes and may land in UNCL (no role prior, no shrinkage).
- **Percentiles depend on peer-group size:** thin role groups in a season give coarse percentiles.
- **Inherits per-match KPI definitions** from `player_analysis.py` (e.g. geometric fallbacks for switches/line-breaks).

---

## 8 — Relationship to Other Components

- **Upstream:** `player_analysis.py` (per-match bundle), [possession-value-model.md](../../models/possession-value-model.md) (PVA), `team_mapping.canonical_name()`, [precompute-pipeline.md](../../infrastructure/precompute-pipeline.md) (`precompute_season_players_if_needed`).
- **Downstream:** `components/opp_season_player_cards.py` (card grid, percentile bars, role filter).
