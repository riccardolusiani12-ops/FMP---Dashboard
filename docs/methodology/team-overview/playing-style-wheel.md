# Playing Style Wheel — Methodology

> **Dashboard location:** Team Overview → Playing Style Wheel
> **Analysis type:** Season-aggregate / League-wide (within-season percentiles)
> **Primary source file(s):** `analytics/playing_style.py` — `compute_playing_style_kpis()`, `compute_league_playing_style()`, `_raw_counters_for_match()`; UI `components/playing_style_cards.py`
> **Precomputed parquet(s):** `playing_style_league_{season}.parquet` (one row per team: 12 raw + 12 percentile + team/season)
> **Last reviewed:** 2026-06-24

---

## 1 — Purpose

The Playing Style Wheel is a 12-spoke polar chart that fingerprints a team's style across four tactical quadrants (Defence, Possession, Progression, Attack), each spoke a within-season percentile against all 20 Serie A clubs. Inspired by The Athletic's *Playstyle Wheels 2.0* (February 2024), it lets an analyst read a team's identity at a glance and compare teams on a like-for-like, percentile basis.

---

## 2 — Input Data

- **Event types used:** passes (`type_id PASS`), crosses (`Cross`), through balls (`Through ball`), tackles/interceptions/clearances, offsides provoked, plus touches by zone. Many KPIs reuse precomputed parquets (`chances_conceded_summary`, `pressing_summary`, `offensive_summary`, `shots`).
- **Qualifiers used:** `Cross`, `Through ball`, `is_penalty` (to exclude penalties from npxG), `Pass End X/Y` for directness.
- **Coordinate system:** Opta normalised (0–100); final-third `x ≥ 66.67`, own-two-thirds `x ≤ 66.67`, attacking-two-thirds threshold for opponent actions.
- **Seasons covered:** all (2021/22–2025/26).
- **Scope:** season-aggregate per team, percentiled within season.

---

## 3 — Methodology

### 3.1 — Raw counters per match (`_raw_counters_for_match`)
A single pass over each match CSV produces per-team season-summable counters (crosses, total/final-third passes, progressive vs total pass distance, own-2/3 and final-third touches, offsides provoked, through-balls conceded, GK-sweeper actions, opponent FT passes, opponent defensive actions in own 2/3). "Conceded/opp" counters are stored on the *defending* team. `_aggregate_raw` sums them across the season.

### 3.2 — The 12 KPIs (`compute_playing_style_kpis`)
**DEFENCE:**
- **D1** — non-penalty xGA per 90 (from `chances_conceded_summary.xg_conceded_per_match`; *lower better*).
- **D2** — PPDA overall = `ppda_num_overall ÷ ppda_den_overall` (*lower better*).
- **D3** — high-line events (offsides provoked + through-balls conceded + GK-sweeper actions) per 100 opponent final-third passes.

**POSSESSION:**
- **P1** — deep build-up = `1 − GK long-pass rate` (more short GK passes = higher).
- **P2** — own-2/3 touches per opponent defensive action in that zone.
- **P3** — possession share (`ft_possession_pct`).

**PROGRESSION:**
- **G1** — central progression = `1 − crosses per 100 passes` (fewer crosses = higher).
- **G2** — circulation = `1 − directness` where directness = progressive x-distance ÷ total pass travel.
- **G3** — field tilt = team FT passes ÷ (team + opp FT passes) × 100.

**ATTACK:**
- **A1** — non-penalty xG per 90.
- **A2** — shots per 100 final-third touches (*lower = more patient*).
- **A3** — non-penalty xG per shot.

### 3.3 — Within-season percentiles (`compute_league_playing_style`)
For each KPI, all 20 teams' raw values are ranked and converted to a percentile (`scipy percentileofscore`, kind="rank", scaled 0–99). **Lower-is-better KPIs (`LOWER_IS_BETTER`) are inverted (`100 − pct`)** so a higher percentile always means "better/more of that style trait". NaNs propagate.

### 3.4 — Parquet
`playing_style_league_{season}.parquet`: one row per team with `team, season` and, for each of the 12 KPI ids, `{kid}_raw` and `{kid}_pct` — i.e. 12 raw + 12 percentile + 2 identifiers (26 columns).

### 3.5 — Rendering
The wheel is a Plotly polar bar (`Barpolar`) with 12 spokes, quadrant-colour-coded (DEFENCE/POSSESSION/PROGRESSION/ATTACK), each bar length the percentile.

---

## 4 — Key Metrics & Definitions

See §3.2 for all 12 KPIs (D1–D3, P1–P3, G1–G3, A1–A3), each reported as a raw value and a within-season percentile (0–99, higher = "more"/"better" after inversion of lower-is-better metrics).

---

## 5 — KPI Code ID to Display Label Crosswalk

The wheel uses internal code identifiers (D1–A3) throughout the analytics and
precompute layers. The table below maps each code ID to the human-readable label
displayed in the dashboard UI, its quadrant, and a brief formula summary.

| Code ID | Quadrant | Display Label | Formula Summary |
|---|---|---|---|
| D1 | Defence | Chance Prevention | Non-penalty xGA per 90 (lower-is-better, inverted) |
| D2 | Defence | Defensive Intensity | PPDA overall = pressing actions ÷ opponent passes (lower-is-better, inverted) |
| D3 | Defence | High Line | (Offsides provoked + through-balls conceded + GK-sweeper actions) per 100 opponent FT passes |
| P1 | Possession | Deep Build-up | `1 − GK long-pass rate` (more short GK passes → higher) |
| P2 | Possession | Press Resistance | Own-2/3 touches per opponent defensive action in that zone |
| P3 | Possession | Possession | Team share of total open-play passes (`ft_possession_pct`) |
| G1 | Progression | Central Progression | `1 − crosses per 100 passes` (fewer crosses → higher) |
| G2 | Progression | Circulate | `1 − directness`, where directness = progressive x-distance ÷ total pass travel |
| G3 | Progression | Field Tilt | Team FT passes ÷ (team + opponent FT passes) × 100 |
| A1 | Attack | Chance Creation | Non-penalty xG per 90 |
| A2 | Attack | Patient Attack | Shots per 100 final-third touches (lower-is-better, inverted) |
| A3 | Attack | Shot Quality | Non-penalty xG per shot |

> The formula summaries are abbreviated — see §4 for the full definitions.

**Note on label variants:** `playing_style_cards.py` uses `KPI_FULL_NAMES` (e.g. "Defensive Intensity" for D2, "Central Progression" for G1) as tooltip/card labels, and shortened `KPI_THETA_LABELS` on the wheel spokes (e.g. "Intensity", "Central Progr."). The evolution cards in `playing_style_evolution_cards.py` use a third label set with a different A-quadrant ordering (A1="Patient Attack", A2="Shot Quality", A3="Chance Creation"). The table above follows `KPI_FULL_NAMES` as the primary UI label; the parquet column identifiers (e.g. `A1_pct`) are the same across all components.

---

## 6 — Outputs

- **Parquet:** `playing_style_league_{season}.parquet` (26 columns).
- **Visual output:** 12-spoke polar bar chart, quadrant-coloured, percentile-scaled.

---

## 7 — Methodological Decisions & Rationale

- **Percentiles, not raw values, on the wheel:** raw KPI units are incomparable across spokes; percentiles put every spoke on a common 0–99 scale so the *shape* is readable.
- **Lower-is-better inversion:** inverting metrics like PPDA and xGA so higher always means "better/more" keeps the wheel intuitively readable (longer spoke = stronger in that trait).
- **Reuse of precomputed parquets:** most KPIs read existing season summaries; only the event-level counters with no precomputed source require a raw CSV pass, keeping the build efficient.
- **Penalty exclusion in attack KPIs:** A1/A3 use non-penalty xG (via `is_penalty`) so a team's open-play attacking quality isn't inflated by penalties.
- **Theme-toggle constraint:** the polar chart is not auto-patched by the global theme toggle (Plotly polar layout), so its colours are set explicitly at build time.

---

## 8 — Limitations & Known Issues

- **Within-season percentiles only:** a spoke says where a team ranks *this season*, not in absolute terms; a "high" spoke in a weak league season is relative.
- **Proxy KPIs:** several spokes are constructed proxies (e.g. directness via pass distance, high-line via offsides+through-balls+sweeper) rather than direct measurements, and inherit any qualifier gaps.
- **NaN propagation:** missing source parquets yield NaN spokes for affected KPIs.
- **Spec note:** the audit brief's KPI labels are approximate; this file documents the exact code definitions (D1–A3).

---

## 9 — Relationship to Other Components

- **Upstream:** [xg-model.md](../models/xg-model.md) (npxG), `chances_conceded_summary` / `pressing_summary` / `offensive_summary` / `shots` parquets, `team_mapping.canonical_name()`, [precompute-pipeline.md](../infrastructure/precompute-pipeline.md) (`precompute_playing_style`).
- **Downstream:** `components/playing_style_cards.py` (wheel); [style-evolution.md](style-evolution.md) (cross-season trends use the same parquets). The KPI code IDs used in the precomputed parquet columns correspond to the display labels listed in §5.
