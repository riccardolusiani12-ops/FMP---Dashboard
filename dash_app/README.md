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

## Weekly Database Update Procedure

Follow these steps every time new Opta match CSV files are available for the
current Serie A season. The procedure takes roughly 5–10 minutes.

### Before You Start

1. Create a dedicated git branch for the weekly update so that `main` always
   reflects a known-good state:
   ```bash
   git checkout -b weekly/YYYY-MM-DD
   ```
2. Confirm the app starts cleanly on the current branch before touching any
   data files:
   ```bash
   cd dash_app && python app.py
   ```
   Browse to `http://127.0.0.1:8050` and verify the dashboard loads without
   errors, then stop the server (`Ctrl+C`).

### Adding New Match CSVs

1. Copy the new Opta event CSV file(s) into the season events folder:
   ```
   data/raw/serie_a_2025_2026/events/
   ```
2. Follow the existing file naming convention:
   ```
   {week}_{HomeTeam}_{AwayTeam}_{matchId}.csv
   ```
   For example: `14_Inter_Milan_f9a3c1.csv`
3. No manual recompute command is needed — the app auto-detects new files
   on the next startup and triggers the preprocessing pipeline automatically.

### Verifying the Update

1. Start the app:
   ```bash
   cd dash_app && python app.py
   ```
2. Watch the startup output in the terminal. A successful pipeline run shows:
   ```
   🔍 Checking data freshness
   ✅ Data check complete.
   ```
3. Check the log file for any errors:
   ```bash
   grep ERROR dash_app/logs/app.log
   ```
   A clean update produces no `ERROR` lines.
4. In the browser, navigate to **Team Overview**, select the **2025/26** season,
   and confirm:
   - The expected teams appear in the standings table.
   - The newly added gameweek is reflected in the points progression chart.

### If Something Goes Wrong (Recovery)

1. If the app fails to start or displays wrong data, discard the weekly branch
   and return to the last known-good state:
   ```bash
   git checkout main
   ```
2. The raw CSV files in `data/raw/` are **not** tracked by git — they remain
   safely on disk even after switching branches.
3. To manually re-trigger preprocessing for the current season without restarting
   the full app:
   ```bash
   cd dash_app && python -m src.analytics.precompute_serie_a 2025_2026
   ```
4. After fixing the issue, re-run the verification steps above before merging.

### Backing Up Raw Data

> ⚠️ The raw Opta CSV files are gitignored (too large for git and contain
> confidential data). They exist **only** on your local machine.

1. After each successful weekly update, back up the entire `data/raw/` folder
   to an external drive or cloud storage (e.g. Google Drive, iCloud).
2. Perform the backup **before** merging the weekly branch to `main` so that
   the backup always corresponds to a verified, working state.
3. Recommended backup command:
   ```bash
   rsync -av --progress \
     "/Users/ricki/Local Projects/FMP_SerieA_Dashboard/data/raw/" \
     "/Volumes/BackupDrive/FMP_raw_backup/$(date +%Y-%m-%d)/"
   ```

### Merging to Main

Once the update is verified in the browser and the backup is complete:

```bash
# Stage any auto-generated manifest/count files that changed
git add data/ready/.csv_count_*

# Commit with a descriptive message
git commit -m "Weekly update: GW{n} 2025/26"

# Merge back to main
git checkout main
git merge weekly/YYYY-MM-DD
```

Replace `{n}` with the actual gameweek number and `YYYY-MM-DD` with today's
date.

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
