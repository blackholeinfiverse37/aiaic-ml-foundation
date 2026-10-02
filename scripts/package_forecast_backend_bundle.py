from __future__ import annotations

import json
import os
import sys
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
MODEL_DIR = REPO / 'models' / 'forecast_official'
META_PATH = MODEL_DIR / 'forecast_20261002T064450Z_9595e12e.json'
BUNDLE_DIR = REPO / 'evidence_packet' / 'backend_integration_bundle'
ZIP_PATH = REPO / 'evidence_packet' / 'backend_integration_bundle_20261002.zip'

sys.path.insert(0, str(REPO))
os.environ['AIAIC_MODELS_DIR'] = str(MODEL_DIR)

from fastapi.testclient import TestClient
from src.api.main import app


def run_local_api_smoke_test(meta: dict) -> dict:
    history_path = MODEL_DIR / meta['history_file']
    history = pd.read_csv(history_path, parse_dates=['date'])
    usable = [group for group in meta['backtest']['groups'] if group.get('usable')]
    if not usable:
        raise RuntimeError('Official bundle has no usable groups to exercise through /v1/forecast.')

    group = next((g for g in usable if g['horizon_days'] == 30), usable[0])
    commodity, state, horizon = group['commodity'], group['state'], int(group['horizon_days'])
    as_of = date.fromisoformat(meta['trained_through'])
    candidates = history[
        (history['commodity'] == commodity)
        & (history['state'] == state)
        & (history['date'].dt.date <= as_of)
    ]
    recent_markets = []
    for market_name, market_history in candidates.groupby('market'):
        market_history = market_history.sort_values('date').tail(400)
        latest_quote = market_history['date'].max().date()
        quote_age = (as_of - latest_quote).days
        if quote_age <= 7 and len(market_history) >= 10:
            recent_markets.append((quote_age, -len(market_history), market_name, market_history))
    if not recent_markets:
        raise RuntimeError(f'No sufficiently recent served history found for {commodity}/{state} at {as_of}.')
    _, _, market, selected = min(recent_markets, key=lambda item: (item[0], item[1], item[2]))

    request_body = {
        'commodity': commodity,
        'state': state,
        'market': market,
        'as_of': as_of.isoformat(),
        'horizon_days': horizon,
        'history': [
            {'date': row.date.date().isoformat(), 'modal_price': float(row.modal_price)}
            for row in selected.itertuples(index=False)
        ],
    }
    with TestClient(app) as client:
        meta_response = client.get('/v1/forecast/meta')
        if meta_response.status_code != 200:
            raise RuntimeError(f'/v1/forecast/meta returned {meta_response.status_code}: {meta_response.text}')
        api_meta = meta_response.json()
        if api_meta.get('model_file') != meta['model_file']:
            raise RuntimeError(f'API loaded {api_meta.get("model_file")}, expected {meta["model_file"]}.')

        response = client.post('/v1/forecast', json=request_body)
        if response.status_code != 200:
            raise RuntimeError(f'/v1/forecast returned {response.status_code}: {response.text}')
        result = response.json()
        if result.get('abstain') is not False:
            raise RuntimeError(f'Expected a forecast from usable backtest group; API response: {result}')
        if not all(result.get(key) is not None for key in ('p10', 'p50', 'p90')):
            raise RuntimeError(f'Forecast response is missing quantiles: {result}')

    return {
        'status': 'PASS',
        'meta_endpoint_status': meta_response.status_code,
        'forecast_endpoint_status': response.status_code,
        'model_file_loaded': api_meta['model_file'],
        'request': {key: value for key, value in request_body.items() if key != 'history'},
        'history_points_sent': len(selected),
        'response': result,
    }


def main() -> None:
    if not META_PATH.is_file():
        raise FileNotFoundError(f'Expected completed official model metadata at {META_PATH}')
    meta = json.loads(META_PATH.read_text(encoding='utf-8'))
    integration_result = run_local_api_smoke_test(meta)

    if BUNDLE_DIR.exists():
        for path in sorted(BUNDLE_DIR.rglob('*'), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    for folder in ('model', 'metadata', 'history', 'proof'):
        (BUNDLE_DIR / folder).mkdir()

    model_path = MODEL_DIR / meta['model_file']
    history_path = MODEL_DIR / meta['history_file']
    (BUNDLE_DIR / 'model' / model_path.name).write_bytes(model_path.read_bytes())
    (BUNDLE_DIR / 'metadata' / META_PATH.name).write_bytes(META_PATH.read_bytes())
    (BUNDLE_DIR / 'history' / history_path.name).write_bytes(history_path.read_bytes())

    integration_path = BUNDLE_DIR / 'proof' / 'local_forecast_api_integration.json'
    integration_path.write_text(json.dumps(integration_result, indent=2), encoding='utf-8')
    handoff = REPO / 'evidence_packet' / 'backend_validation_handoff.md'
    handoff_path = BUNDLE_DIR / 'proof' / handoff.name
    handoff_path.write_bytes(handoff.read_bytes())
    for log_name in (
        'official_validation_suite_20261002T063823Z.txt',
        'pytest_tests_20261002.txt',
        'forecast_api_http_smoke_20261002.json',
    ):
        source = REPO / 'evidence_packet' / 'runtime_logs' / log_name
        if source.is_file():
            (BUNDLE_DIR / 'proof' / source.name).write_bytes(source.read_bytes())

    readme = f'''# AIAIC Forecast Backend Bundle

This package contains the full-data official Agmarknet forecast model and the files required by this repository's `/v1/forecast` endpoint.

## Contents

- `model/{model_path.name}`: joblib quantile model bundle
- `metadata/{META_PATH.name}`: training metadata and walk-forward backtest
- `history/{history_path.name}`: served per-mandi price history
- `proof/`: in-process and live HTTP API smoke-test results, suite logs, and handoff summary

## Local API Integration

The API reads `{meta['model_file']}` and its history from the configured models directory. Set `AIAIC_MODELS_DIR` to a directory containing the matching model, metadata, and history files. From the project root, the tested configuration is:

```powershell
$env:AIAIC_MODELS_DIR = (Resolve-Path 'models/forecast_official').Path
.\\.venv\\Scripts\\python.exe -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

Endpoints:

- `GET /v1/forecast/meta`
- `POST /v1/forecast`

Request fields: `commodity`, `state`, `market`, `as_of` (`YYYY-MM-DD`), `horizon_days`, and optional mandi `history` (`date`, `modal_price`). See `proof/local_forecast_api_integration.json` for the verified request and response.

The running local HTTP smoke test was also verified at `http://127.0.0.1:8100` without caller-supplied history. Its response is in `proof/forecast_api_http_smoke_20261002.json`.

## Readiness Caveat

The model reproduces the official backtest, but aggregate skill versus persistence is -0.1573. Forecasts are abstained when their crop/state/horizon backtest is unusable. The separately configured external backend reported `calibrated: false`; this package verifies integration with this repository's local FastAPI service, not deployment to or calibration of that remote service.
'''
    (BUNDLE_DIR / 'README.md').write_text(readme, encoding='utf-8')

    ZIP_PATH.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ZIP_PATH, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(BUNDLE_DIR.rglob('*')):
            if path.is_file():
                archive.write(path, path.relative_to(BUNDLE_DIR.parent))

    print(json.dumps({
        'integration': integration_result,
        'bundle_dir': str(BUNDLE_DIR),
        'zip_path': str(ZIP_PATH),
        'zip_bytes': ZIP_PATH.stat().st_size,
    }, indent=2))


if __name__ == '__main__':
    main()
