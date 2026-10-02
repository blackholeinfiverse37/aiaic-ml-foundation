# Backend Validation Handoff

Run date: 2026-10-02

## Minimum Training Run

The accepted minimum subset was selected from the official Agmarknet archive and trained with the existing walk-forward gates. It is a single series: Wheat, Bhikangaon, Madhya Pradesh. The run used horizons 7 and 30 days, `step_days=1`, and a 180-day holdout.

- Source rows: 268 (2024-12-09 through 2025-11-03)
- Generated training samples: 203
- Generated test samples: 305
- Backtest evaluation count after calibration split: 153
- p50 MAE: 252.59; persistence MAE: 100.37
- Skill vs persistence: -1.5166
- Calibrated p10-p90 coverage: 0.451
- Both horizon groups are marked `usable: false`; this is an integration proof only, not a deployable forecast model.

Artifacts:

- Subset CSV: `data/raw/agmarknet_minimum_validation.csv`
- Model: `models/forecast_minimum/forecast_20261002T063343Z_82136a5f.joblib`
- Metadata and full backtest: `models/forecast_minimum/forecast_20261002T063343Z_82136a5f.json`
- Served history: `models/forecast_minimum/forecast_20261002T063343Z_82136a5f_history.csv.gz`
- Reproduction script: `scripts/run_minimum_validation.py`

## Backend Probe

The `.env` backend host responded to both `/health` and `/catalog?state=maharashtra` with HTTP 200 and JSON bodies. Health reports service version 1.0.0 and explicitly says the engine is uncalibrated and its illustrative defaults are not farmer-ready advice.

## Local Forecast API Integration

The official model was loaded through this repository's FastAPI app by setting `AIAIC_MODELS_DIR=models/forecast_official`. Both `GET /v1/forecast/meta` and `POST /v1/forecast` returned HTTP 200. The forecast smoke request used Wheat / Madhya Pradesh / Satna APMC, `as_of=2026-08-26`, horizon 30 days, and 291 recent-history points. The response used model `forecast_20261002T064450Z_9595e12e.joblib`, did not abstain, and returned p10 2310.75, p50 2500.89, p90 2700.81 INR/quintal. Its backtest group was marked usable (skill +0.30, coverage 0.9444).

The live local server is running at `http://127.0.0.1:8100`. A second HTTP smoke test called those endpoints over localhost with no caller-supplied history; both returned 200 and the forecast did not abstain. Its saved response is `evidence_packet/runtime_logs/forecast_api_http_smoke_20261002.json`.

The deployable bundle is `evidence_packet/backend_integration_bundle_20261002.zip`; the extracted package is under `evidence_packet/backend_integration_bundle/`. The exact smoke request/result is in `proof/local_forecast_api_integration.json` inside that package.

This verifies integration with the local ML Foundation FastAPI service, not installation into the separate external AIAIC host. The remote host exposes an uncalibrated engine and no deployment endpoint/credentials were provided, so the ZIP is the handoff for that backend team's deployment step.

## Full Validation Suite

Completed on 2026-10-02.

The fresh full official-data training took 391.44 seconds (6m 31s). The official backtest comparison took 0.37 seconds and printed `AGREES with the official backtest.` The initial root-level `pytest -q` collection took 13.79 seconds but failed because pytest collected three archived UTF-16 `test_results*.txt` files outside the project test directory. The corrected project test run `pytest tests -q` passed: 86 passed, 8 warnings in 22.51 seconds. End-to-end elapsed time through the successful project test run was about 429 seconds (7m 09s).

The completed official-data output was:

- Model: `forecast_20261002T064450Z_9595e12e.joblib`
- Trained through: 2026-08-26; walk-forward cutoff: 2026-02-27
- Scored examples: 15,872
- p50 MAE: 307.51; persistence MAE: 265.72
- Skill vs persistence: -0.1573; p10-p90 coverage: 0.8151
- Official group-by-group comparison: exact agreement within the comparator's rounding tolerances

The full model's overall skill remains negative despite successful reproducibility. Individual group metadata controls whether a forecast is usable; the model should not be presented as universally useful. Health metadata also says the external engine is uncalibrated and not farmer-ready.

The timestamped full-suite log preserves the first root-level pytest collection failure as well as successful backend, training, and comparison outputs. The corrected `pytest tests -q` output is recorded separately. The reusable runner now targets `tests/` directly.

## Backend Team / Proof Files

Recommended files to share:

- This handoff summary: `evidence_packet/backend_validation_handoff.md`
- Raw full-suite output: `evidence_packet/runtime_logs/official_validation_suite_*.txt`
- Successful full project test output: `evidence_packet/runtime_logs/pytest_tests_20261002.txt`
- Model integration ZIP: `evidence_packet/backend_integration_bundle_20261002.zip`
- Extracted bundle README and contents: `evidence_packet/backend_integration_bundle/README.md`
- Local forecast API integration proof: `evidence_packet/backend_integration_bundle/proof/local_forecast_api_integration.json`
- Forecast metadata/backtest JSON: `models/forecast_official/forecast_*.json` from the completed run
- Model bundle and served history: matching `.joblib` and `_history.csv.gz` files under `models/forecast_official/`
- Minimum-run proof: the minimum metadata JSON and subset CSV listed above
- Reproduction scripts: `scripts/run_official_validation_suite.py` and `scripts/run_minimum_validation.py`
- Bundle/integration script: `scripts/package_forecast_backend_bundle.py`

Do not present the minimum-run model as calibrated or suitable for production; its backtest marks both horizons unusable.
