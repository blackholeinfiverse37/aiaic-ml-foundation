from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

repo = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo))

from src.forecast.series import daily_series, training_samples
from src.forecast.train import train, walk_forward_split

raw = repo / 'data' / 'raw' / 'agmarknet_mh_mp_2016_2026.csv.gz'
subset_path = repo / 'data' / 'raw' / 'agmarknet_minimum_validation.csv'
models_dir = repo / 'models' / 'forecast_minimum'
horizons = [7, 30]
holdout_days = 180
step_days = 1
minimum_train_samples = 200
minimum_test_samples = 50


def find_smallest_accepted_subset() -> tuple[pd.DataFrame, dict]:
    columns = ['commodity', 'state', 'market', 'date', 'modal_price']
    print('Reading official source and filtering supported crops/states...', flush=True)
    df = pd.read_csv(raw, usecols=columns)
    df = df[df['state'].isin(['Maharashtra', 'Madhya Pradesh'])]
    df = df[df['commodity'].isin(['Onion', 'Soyabean', 'Wheat'])]
    daily = daily_series(df)
    candidates = []

    groups = sorted(
        daily.groupby(['commodity', 'state', 'market'], sort=True, observed=True),
        key=lambda item: len(item[1]),
        reverse=True,
    )
    print('Candidate mandi groups:', len(groups), flush=True)
    for group_number, (key, group) in enumerate(groups, start=1):
        group = group.sort_values('date').reset_index(drop=True)
        full_samples = training_samples(group, horizons, step_days=step_days)
        if full_samples.empty:
            continue
        train_all, test_all, cutoff = walk_forward_split(full_samples, holdout_days)
        if len(train_all) < minimum_train_samples or len(test_all) < minimum_test_samples:
            print(f'Group {group_number} is too small: {len(train_all)} train / {len(test_all)} test', flush=True)
            continue

        train_asof = np_sorted(train_all['as_of'])
        test_asof = np_sorted(test_all['as_of'])
        low, high = 0, len(group) - 1
        best_start = None
        while low <= high:
            start = (low + high) // 2
            first_asof = pd.Timestamp(group.loc[start, 'date']) + pd.Timedelta(days=30)
            first_asof_value = first_asof.to_datetime64()
            train_count = len(train_asof) - train_asof.searchsorted(first_asof_value, side='left')
            test_count = len(test_asof) - test_asof.searchsorted(first_asof_value, side='left')
            if train_count >= minimum_train_samples and test_count >= minimum_test_samples:
                best_start = start
                low = start + 1
            else:
                high = start - 1

        if best_start is not None:
            subset = group.iloc[best_start:].copy()
            candidates.append((len(subset), subset, key))
            print(f'Selected first qualifying group: {key}; source daily rows={len(group)}', flush=True)
            break

    if not candidates:
        raise RuntimeError('No single crop/state/market group in the selected official data meets the 200/50 sample gates.')

    _, subset, key = min(candidates, key=lambda item: item[0])
    subset.to_csv(subset_path, index=False)
    actual_samples = training_samples(daily_series(subset), horizons, step_days=step_days)
    train_samples, test_samples, cutoff = walk_forward_split(actual_samples, holdout_days)
    stats = {
        'commodity': key[0],
        'state': key[1],
        'market': key[2],
        'raw_rows': len(subset),
        'first_date': str(subset['date'].min().date()),
        'last_date': str(subset['date'].max().date()),
        'all_samples': len(actual_samples),
        'train_samples': len(train_samples),
        'test_samples': len(test_samples),
        'cutoff': str(cutoff.date()),
    }
    return subset, stats


def np_sorted(values: pd.Series):
    import numpy as np

    return np.sort(pd.to_datetime(values).to_numpy(dtype='datetime64[ns]'))


if __name__ == '__main__':
    subset, stats = find_smallest_accepted_subset()
    print('MINIMUM_SUBSET', json.dumps(stats, indent=2))
    print('SUBSET_CSV', subset_path)
    meta = train(
        subset,
        horizons=horizons,
        source='Minimum accepted date-contiguous subset of official Agmarknet export',
        models_dir=models_dir,
        seed=42,
        holdout_days=holdout_days,
        step_days=step_days,
    )
    print('TRAINING_OUTPUT', json.dumps({
        'model_file': meta['model_file'],
        'trained_through': meta['trained_through'],
        'backtest_cutoff': meta['backtest_cutoff'],
        'backtest': meta['backtest'],
    }, indent=2))
    print('MODEL_ARTIFACT', models_dir / meta['model_file'])
    print('METADATA_ARTIFACT', models_dir / (Path(meta['model_file']).stem + '.json'))
    print('HISTORY_ARTIFACT', models_dir / meta['history_file'])
