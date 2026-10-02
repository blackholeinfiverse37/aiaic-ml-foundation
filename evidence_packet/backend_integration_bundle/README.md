# AIAIC Forecast Backend Bundle

This package contains the full-data official Agmarknet forecast model and the files required by this repository's `/v1/forecast` endpoint.

## Contents

- `model/forecast_20261002T064450Z_9595e12e.joblib`: joblib quantile model bundle
- `metadata/forecast_20261002T064450Z_9595e12e.json`: training metadata and walk-forward backtest
- `history/forecast_20261002T064450Z_9595e12e_history.csv.gz`: served per-mandi price history
- `proof/`: in-process and live HTTP API smoke-test results, suite logs, and handoff summary

## Local API Integration

The API reads `forecast_20261002T064450Z_9595e12e.joblib` and its history from the configured models directory. Set `AIAIC_MODELS_DIR` to a directory containing the matching model, metadata, and history files. From the project root, the tested configuration is:

```powershell
$env:AIAIC_MODELS_DIR = (Resolve-Path 'models/forecast_official').Path
.\.venv\Scripts\python.exe -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

Endpoints:

- `GET /v1/forecast/meta`
- `POST /v1/forecast`

Request fields: `commodity`, `state`, `market`, `as_of` (`YYYY-MM-DD`), `horizon_days`, and optional mandi `history` (`date`, `modal_price`). See `proof/local_forecast_api_integration.json` for the verified request and response.

The running local HTTP smoke test was also verified at `http://127.0.0.1:8100` without caller-supplied history. Its response is in `proof/forecast_api_http_smoke_20261002.json`.

## Readiness Caveat

The model reproduces the official backtest, but aggregate skill versus persistence is -0.1573. Forecasts are abstained when their crop/state/horizon backtest is unusable. The separately configured external backend reported `calibrated: false`; this package verifies integration with this repository's local FastAPI service, not deployment to or calibration of that remote service.
