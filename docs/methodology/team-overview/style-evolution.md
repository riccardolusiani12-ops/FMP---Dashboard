# Style Evolution — Methodology

> **Dashboard location:** Team Overview → Style Evolution (directly below the Playing Style Wheel)
> **Analysis type:** Cross-season trend (within-season percentiles assembled across seasons)
> **Primary source file(s):** `components/playing_style_evolution_cards.py`; data via `data_loader.load_playing_style_all_seasons()`
> **Precomputed parquet(s):** `playing_style_league_{season}.parquet` (one per season, assembled at render time)
> **Last reviewed:** 2026-06-24

---

## 1 — Purpose

Style Evolution shows how a team's playing identity has changed over five seasons. For each of the 12 Playing Style KPIs it plots the team's within-Serie-A percentile rank across 2021/22–2025/26, so an analyst can see, for example, a team becoming more possession-dominant or pressing more intensely under a new manager.

---

## 2 — Input Data

- **Event types used:** none directly — reuses the precomputed Playing Style league parquets.
- **Coordinate system:** not used.
- **Seasons covered:** all 5 (2021/22–2025/26).
- **Scope:** one team, all seasons, all 12 KPIs.

---

## 3 — Methodology

### 3.1 — Data assembly
`load_playing_style_all_seasons(team)` reads each season's `playing_style_league_{season}.parquet` and extracts the team's `{kid}_pct` (percentile) columns, assembling a per-season percentile series for each of the 12 KPIs at render time.

### 3.2 — 12 small multiples
The section renders **12 small-multiple area+line charts** (`make_subplots`), one per KPI, each plotting the team's percentile rank across the 5 seasons. KPIs are laid out in `KPI_ORDER` (D1–D3, P1–P3, G1–G3, A1–A3) with human-readable labels:
- DEFENCE: Chance Prevention (D1), Intensity (D2), High Line (D3)
- POSSESSION: Deep Build-up (P1), Press Resistance (P2), Possession (P3)
- PROGRESSION: Central Progression (G1), Circulate (G2), Field Tilt (G3)
- ATTACK: Patient Attack (A1), Shot Quality (A2), Chance Creation (A3)

### 3.3 — Quadrant colour coding
Each chart is coloured by its quadrant (`KPI_PHASE` → DEFENCE/POSSESSION/PROGRESSION/ATTACK colours), imported from `playing_style_cards` so the wheel and the evolution charts share one palette.

---

## 4 — Key Metrics & Definitions

- **Per-KPI percentile trend:** the team's within-season percentile (0–99) for each of the 12 Playing Style KPIs, plotted season-over-season. The KPI definitions are identical to those in [playing-style-wheel.md](playing-style-wheel.md).

---

## 5 — Outputs

- **Visual output:** 12 area+line small-multiple charts showing 5-season percentile evolution, quadrant-coloured.
- **Parquet:** reads the per-season `playing_style_league_{season}.parquet` files.

---

## 6 — Methodological Decisions & Rationale

- **Percentile trends, not raw-value trends:** plotting the within-season *rank* controls for league-wide drift (e.g. if the whole league presses harder over time), isolating the team's relative stylistic change.
- **Reuse of the wheel's parquets:** the evolution view assembles the same `{kid}_pct` columns the wheel uses, guaranteeing the two views are consistent and requiring no extra precompute.
- **Shared palette with the wheel:** importing the quadrant colours (rather than redefining them) keeps the wheel and evolution charts visually coherent.

---

## 7 — Limitations & Known Issues

- **Relative, not absolute:** a flat percentile line means stable *rank*, not necessarily stable underlying performance (the whole league could have shifted).
- **Depends on all season parquets:** a missing season parquet leaves a gap in that KPI's trend.
- **Inherits Playing Style KPI caveats:** see [playing-style-wheel.md](playing-style-wheel.md) (proxy KPIs, NaN propagation).

---

## 8 — Relationship to Other Components

- **Upstream:** [playing-style-wheel.md](playing-style-wheel.md) (KPI definitions, per-season parquets), `data_loader.load_playing_style_all_seasons`.
- **Downstream:** Team Overview Style Evolution section (rendered below the wheel).
