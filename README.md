# Serie A Analytics Dashboard

A local-first tactical analytics dashboard for Serie A, built with Plotly Dash. Processes Opta event data into interactive match and season reports covering attacking phases, defensive structure, set pieces, pressing metrics, and more.

---

## Features

### Pages

| Page | Description |
|------|-------------|
| **Team Overview** | Season standings, points progression, team KPIs, and league-wide comparisons |
| **Team Detail** | Per-team season breakdown — formations, KPI cards, style wheel |
| **Match Analysis** | Post-game tactical breakdown for a selected match |
| **Opponent Analysis** | Season-aggregate scouting reports for upcoming opponents |

### Analytics Modules

**Possession & Build-up**
- General build-up patterns and goalkeeper-initiated attacks
- Possession Value (Goal Probability Added — logistic regression model)
- Offensive transitions and high regains

**Shooting & Chance Creation**
- Chance creation and chances conceded (shot maps, xT)
- xG by team and match
- Final-third entry analysis

**Defensive Phase**
- PPDA (Passes Per Defensive Action) — pressing intensity
- Defensive pressing patterns and recovery locations
- Defensive structure and shape heatmaps

**Set Pieces**
- Corner kick delivery and outcome analysis
- Free kick pitch maps

**Squad & Season**
- Season-aggregate player KPIs
- Formation frequency and shape breakdown
- Playing Style Wheel — 12-KPI barpolar radar
- Multi-season standings and points trajectory

---

## Tech Stack

| Layer | Library / Version |
|-------|------------------|
| Web framework | Plotly Dash 4.1 |
| UI components | Dash Bootstrap Components 2.0 (DARKLY theme) |
| Charts | Plotly 6.5 |
| Data layer | Pandas 2.3, PyArrow 22 |
| ML model | scikit-learn 1.7 (Possession Value) |
| Export | Kaleido 1.2 (PNG / PDF) |
| Runtime | Python 3.10+ |

---

## Data

The dashboard runs on **Opta Sports** event-level match data (Serie A). Raw CSVs are **not included** in this repository — they are private proprietary data files.

**Coordinate system:** x ∈ [0, 100] (own goal → opponent goal), y ∈ [0, 100] (bottom touchline → top touchline).

Once raw CSVs are present, the app auto-detects changes on startup and recomputes all Parquet tables — no manual pipeline steps needed.

---

## Setup

```bash
# 1. Clone the repo
git clone <repo-url>
cd FMP_SerieA_Dashboard

# 2. Create and activate a virtual environment
cd dash_app
python -m venv .venv
source .venv/bin/activate      # macOS / Linux
# .venv\Scripts\activate       # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the app
python app.py
```

Open **http://127.0.0.1:8050** in your browser.

> **Note:** scikit-learn must be installed for the Possession Value model to function. The app will start without it, but PV charts will be empty.

---

## Data Update Workflow

1. Drop new Opta CSV files into `data/raw/serie_a_{season}/events/`
2. Restart the app
3. The pipeline auto-detects fresher raw files and recomputes all affected Parquet tables
4. Logs: `dash_app/logs/app.log`

---

## Project Structure

```
FMP_SerieA_Dashboard/
├── dash_app/
│   ├── app.py                  # Entry point (port 8050)
│   ├── src/
│   │   ├── analytics/          # Computation modules (xG, PPDA, PV, etc.)
│   │   ├── callbacks/          # Dash callback definitions
│   │   ├── components/         # Reusable UI components
│   │   └── pages/              # Page layouts
│   ├── assets/                 # CSS, fonts, logos
│   └── requirements.txt
├── data/
│   ├── raw/                    # Opta CSV input (gitignored)
│   ├── processed/              # Intermediate files
│   ├── ready/                  # Precomputed Parquet tables
│   └── cache/
├── docs/
│   ├── methodology/            # Module design documentation
│   └── OptaData Types & Qualifiers/
├── notebooks/                  # Exploratory analysis
├── outputs/                    # Generated artifacts + manifest.json
└── scripts/                    # Utility scripts
```

---

## Requirements

- Python 3.10+
- Opta Sports event data (CSV format)
- ~500 MB disk space for processed Parquet tables per season

---

## License

Private project — data and code are not for redistribution.
