from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd

repo = Path(__file__).resolve().parents[1]
raw = repo / 'data' / 'raw' / 'agmarknet_mh_mp_2016_2026.csv.gz'
out = repo / 'data' / 'raw' / 'agmarknet_mh_mp_2016_2026_100.csv'
models_dir = repo / 'models' / 'forecast_100row'


def build_subset() -> pd.DataFrame:
    df = pd.read_csv(raw)
    keep_crops = ['Onion', 'Soyabean', 'Wheat']
    keep_markets = ['Nashik', 'Lasalgaon', 'Pimpalgaon', 'Akluj', 'Nagpur', 'Wardha']
    df = df[df['commodity'].isin(keep_crops)]
    df = df[df['state'].eq('Maharashtra')]
    df = df[df['market'].isin(keep_markets)]
    df = df[['commodity', 'state', 'market', 'date', 'modal_price']].copy()
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values(['commodity', 'market', 'date'], kind='mergesort').drop_duplicates()
    selected = []
    for commodity in keep_crops:
        for market in keep_markets:
            g = df[(df['commodity'] == commodity) & (df['market'] == market)]
            if g.empty:
                continue
            g = g.sort_values('date').drop_duplicates().reset_index(drop=True)
            idxs = list(range(0, len(g), max(1, len(g) // 8)))
            idxs = idxs[:8]
            selected.append(g.iloc[idxs])
    subset_df = pd.concat(selected, ignore_index=True) if selected else df.head(100)
    subset_df = subset_df.sort_values(['commodity', 'market', 'date'], kind='mergesort').reset_index(drop=True)
    subset_df = subset_df.head(100)
    subset_df.to_csv(out, index=False)
    return subset_df


def run_training() -> None:
    cmd = [
        sys.executable,
        '-m', 'src.forecast.train',
        '--input', str(out),
        '--crops', 'Onion', 'Soyabean', 'Wheat',
        '--horizons', '7', '30',
        '--holdout-days', '30',
        '--step-days', '7',
        '--seed', '42',
        '--models-dir', str(models_dir),
        '--source', '100-row validation subset from official Agmarknet export'
    ]
    print('TRAIN CMD:', ' '.join(cmd))
    p = subprocess.run(cmd, cwd=str(repo), capture_output=True, text=True)
    print('TRAIN RETURN:', p.returncode)
    if p.stdout:
        print(p.stdout)
    if p.stderr:
        print('STDERR:\n' + p.stderr)
    if p.returncode != 0:
        raise SystemExit(p.returncode)


def run_pytest() -> None:
    p = subprocess.run([sys.executable, '-m', 'pytest', 'tests/forecast', '-q'], cwd=str(repo), capture_output=True, text=True)
    print('PYTEST RETURN:', p.returncode)
    if p.stdout:
        print(p.stdout)
    if p.stderr:
        print('STDERR:\n' + p.stderr)
    if p.returncode != 0:
        raise SystemExit(p.returncode)


if __name__ == '__main__':
    subset = build_subset()
    print('SUBSET_ROWS=', len(subset))
    print(subset[['commodity', 'state', 'market', 'date', 'modal_price']].head(10).to_string(index=False))
    run_training()
    run_pytest()
    print('SMOKE TEST PASS: 100-row validation completed successfully.')
