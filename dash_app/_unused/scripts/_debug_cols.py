import sys, pandas as pd
from pathlib import Path
sys.path.insert(0, '/Users/ricki/Local Projects/FMP_SerieA_Dashboard/dash_app')

# Find a 2025/2026 match with Inter
import glob
csvs = glob.glob('/Users/ricki/Local Projects/FMP_SerieA_Dashboard/data/raw/serie_a_2025_2026/events/*.csv')
print(f"Found {len(csvs)} files")
for f in csvs[:5]:
    df = pd.read_csv(f, nrows=3, low_memory=False)
    teams = df['team_name'].unique().tolist()
    print(Path(f).name, '→', teams)

# Load the Inter match and inspect relevant columns
target = None
for f in csvs:
    df = pd.read_csv(f, nrows=5, low_memory=False)
    if any('inter' in str(t).lower() for t in df['team_name'].unique()):
        target = f
        break

if target:
    print('\nUsing:', Path(target).name)
    df = pd.read_csv(target, low_memory=False)
    
    # Print columns that relate to: swerve, goalmouth, body, shot desc, blocked
    keywords = ['swerve', 'goal mouth', 'mouth', 'blocked', 'woodwork', 'saved off',
                'low', 'high', 'strong', 'weak', 'rising', 'dipping', 'big chance',
                'deflect', 'head', 'footed', 'free kick', 'free kick taken']
    for col in df.columns:
        if any(k in col.lower() for k in keywords):
            # Check if any row has 'Si'
            vals = df[col].dropna().unique()
            si_present = any(str(v).strip().lower() in ('si','yes','1','true') for v in vals)
            print(f"  {repr(col):40s} vals={vals[:3]}  has_si={si_present}")
