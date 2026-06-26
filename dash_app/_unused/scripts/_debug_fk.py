import sys, pandas as pd
from pathlib import Path

df = pd.read_csv('/Users/ricki/Local Projects/FMP_SerieA_Dashboard/data/raw/serie_a_2025_2026/events/38_Bologna_Inter_1iz38m02tzgh8x5a9yg2ztgyc.csv', low_memory=False)
fk_shots = df[df['player_name'].str.contains('Dimarco|Di Marco', case=False, na=False) & df['type_id'].isin([13,14,15,16])]
for idx, row in fk_shots.iterrows():
    non_null = {k: v for k, v in row.items() if pd.notna(v) and str(v).strip() not in ('nan', '',)}
    for k, v in non_null.items():
        print(f"  {k!r}: {v!r}")
    print()
