# Serie A – Game Analysis Dashboard

**Single-page Dash dashboard for viewing precomputed football analysis artifacts.**
Focus team: **Bologna** | Competition: **Serie A** | Local-only.

---

## Quick Start

### 1. Create virtual environment

```bash
cd dash_app
python -m venv .venv
source .venv/bin/activate    # macOS/Linux
# .venv\Scripts\activate     # Windows
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Generate demo artifacts (first time only)

```bash
python scripts/generate_demo_artifacts.py
```

### 4. Run the dashboard

```bash
python app.py
```

Open **http://127.0.0.1:8050** in your browser.

---

## Project Structure

```
dash_app/
├── app.py                          # Entrypoint – run this
├── requirements.txt
├── assets/
│   └── styles.css                  # Dark theme CSS
├── logs/
│   └── app.log                     # Runtime logs
├── scripts/
│   └── generate_demo_artifacts.py  # Demo data generator
└── src/
    ├── config.py                   # Paths, defaults, constants
    ├── registry/
    │   ├── manifest_schema.py      # Manifest JSON schema & dataclasses
    │   ├── registry.py             # Artifact registry (singleton)
    │   └── loaders.py              # Load artifacts → Dash components
    ├── components/
    │   ├── navbar.py               # Top navigation bar
    │   ├── filters.py              # Global filter bar
    │   ├── kpis.py                 # KPI cards row
    │   └── tables.py               # Reusable DataTable helper
    ├── tabs/
    │   ├── home.py                 # Season overview tab
    │   ├── match_report.py         # Pre/Post match report tab
    │   ├── team_season.py          # Team season performance tab
    │   ├── player_analysis.py      # Player-level analysis tab
    │   └── settings.py             # Settings & Data QA tab
    ├── callbacks/
    │   ├── filters_callbacks.py    # Filter dropdowns chaining
    │   ├── tabs_callbacks.py       # Tab content rendering
    │   └── download_callbacks.py   # PDF & CSV export
    ├── reporting/
    │   ├── pdf_template.py         # ReportLab styles & layout
    │   └── pdf_builder.py          # PDF generation pipeline
    └── utils/
        ├── caching.py              # TTL-based in-memory cache
        ├── logging.py              # Centralized logging
        └── paths.py                # Path builders for raw data & artifacts
```

---

## Where to Place Outputs

All precomputed analysis outputs go under the **repository-level** `outputs/` folder:

```
FMP_SerieA_Dashboard/
└── outputs/
    ├── manifest.json               # ← Central artifact index
    ├── demo/                       # Demo artifacts (sample data)
    ├── 2024_2025/                  # Season-organized outputs
    │   ├── high_regains/
    │   │   └── Bologna/
    │   │       ├── season_overview.json
    │   │       └── league_table.csv
    │   ├── xt/
    │   │   └── Bologna/
    │   │       └── {match_id}/
    │   │           └── xt_zones.json
    │   └── ...
    └── 2025_2026/
        └── ...
```

### Supported file formats

| Format        | Extension     | Rendered as                |
|---------------|---------------|----------------------------|
| `plotly_json`  | `.json`       | Interactive Plotly chart    |
| `png` / `jpg`  | `.png/.jpg`   | Static image               |
| `csv`          | `.csv`        | Interactive DataTable       |
| `parquet`      | `.parquet`    | Interactive DataTable       |
| `html`         | `.html`       | Embedded iframe             |
| `table_json`   | `.json`       | DataTable from JSON records |
| `markdown`     | `.md`         | Rendered Markdown           |

---

## How the Manifest Works

The `outputs/manifest.json` file is the **central index** that tells the dashboard which artifacts exist, where they are, and how to display them.

### Adding a new artifact

1. **Save your output** to `outputs/{season}/{analysis}/{team}/{filename}`.
2. **Add an entry** to `manifest.json`:

```json
{
  "id": "unique-id",
  "season": "2024_2025",
  "competition": "Serie A",
  "analysis": "high_regains",
  "team": "Bologna",
  "match_id": "abc123",
  "match_label": "GW1 Bologna–Udinese",
  "title": "High Regains – Bologna vs Udinese",
  "description": "Ball recoveries in the final third.",
  "format": "plotly_json",
  "file": "2024_2025/high_regains/Bologna/abc123/map.json",
  "tags": ["match", "defensive"],
  "created_at": "2026-02-27T12:00:00"
}
```

3. **Reload** the manifest from the Settings tab or restart the app.

### Key fields

| Field        | Required | Description                                    |
|--------------|----------|------------------------------------------------|
| `id`         | ✅       | Unique identifier                              |
| `season`     | ✅       | Season folder name (e.g. `2024_2025`)          |
| `competition`| ✅       | Competition name                               |
| `analysis`   | ✅       | Analysis type (maps to notebook)               |
| `title`      | ✅       | Display title                                  |
| `format`     | ✅       | File format (see table above)                  |
| `file`       | ✅       | Path relative to `outputs/`                    |
| `team`       | –        | Team filter                                    |
| `match_id`   | –        | Match-level filter                             |
| `match_label`| –        | Human-readable match label                     |
| `tags`       | –        | Categorization tags                            |

---

## PDF Export

Click **Export PDF** in the navbar. The report includes:
- Cover page with meta info (competition, season, team, match)
- All artifacts for the currently active tab
- Charts rendered as PNG images (via kaleido)
- Fixed template with dark theme styling

Requires `kaleido` for Plotly-to-PNG conversion. Works fully offline.

---

## Analysis Types

| Analysis                    | Notebook                   | Description                       |
|-----------------------------|----------------------------|-----------------------------------|
| `high_regains`              | `01_high_regains.ipynb`    | Final-third ball recoveries       |
| `xt`                        | `02_xt.ipynb`              | Expected Threat by zone           |
| `attacking_phase`           | `03_attacking_phase.ipynb` | Shot maps, progressive actions    |
| `passing_network`           | `04_passing_network.ipynb` | Player passing connections        |
| `ppda`                      | `05_ppda.ipynb`            | Pressing intensity (PPDA)         |
| `epv`                       | `06_epv.ipynb`             | Expected Possession Value         |
| `season_points_progression` | `07_season_points.ipynb`   | Cumulative points over season     |
