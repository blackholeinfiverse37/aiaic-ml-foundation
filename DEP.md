# DEP.md — Deployment and Execution Protocol
# AIAIC ML Foundation — Crop Price Prediction Service
# Test 2: Production ML Runtime Integration

**Owner:** Aryan Sawant  
**Version:** 1.0.0  
**Date:** September 2026  

---

## System Entry Point
run_pipeline.py ← trains the model (run once before API)
src/api/main.py ← FastAPI application entry point
uvicorn src.api.main:app ← starts the inference service

---

## Execution Flow
Place CSVs in data/raw/
↓
python run_pipeline.py --save-report
(ingest → validate → preprocess → features → train)
↓
Model saved to models/*.joblib
↓
uvicorn src.api.main:app --port 8000
↓
POST /v1/predict → prediction + replay file written
↓
python scripts/producer.py (sends real data row to API)
↓
python scripts/consumer.py (processes result, income assessment)
↓
python scripts/replay_runner.py --latest (proves determinism)

---

## Prerequisites

- Python 3.11+
- Anaconda or virtualenv
- Dataset CSVs in `data/raw/`

---

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp .env.example .env
```

---

## Dataset Setup

Place these files in `data/raw/`:
- `Agriculture_price_dataset.csv`
- `commodity_price.csv`

---

## Train the Model

```bash
# Full pipeline — ingest, validate, preprocess, features, train
python run_pipeline.py --save-report

# Expected output:
# STAGE 1/5 — INGESTION    → 740,125 rows
# STAGE 2/5 — VALIDATION   → 737,389 clean, 2,736 quarantined
# STAGE 3/5 — PREPROCESSING → outliers capped
# STAGE 4/5 — FEATURES     → 735,774 rows, 15 feature columns
# STAGE 5/5 — TRAINING     → MAE: 44.07 | MAPE: 4.52% | R²: 0.9946
```

---

## Start the API

```bash
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

| Endpoint | Method | Purpose |
|---|---|---|
| `/` | GET | Service info and route index |
| `/v1/health` | GET | Liveness check — always 200 |
| `/v1/ready` | GET | Readiness check — 503 if no model |
| `/v1/predict` | POST | Crop price prediction |
| `/docs` | GET | Swagger UI |

---

## API Contract

### POST /v1/predict

**Required fields:**
```json
{
  "commodity": "Onion",
  "state": "Maharashtra",
  "month": 8
}
```

**Full request:**
```json
{
  "commodity": "Onion",
  "state": "Maharashtra",
  "grade": "FAQ",
  "month": 8,
  "day_of_week": 3,
  "is_weekend": 0,
  "season": "kharif",
  "month_sin": -0.866,
  "month_cos": -0.5,
  "modal_price_lag_1": 1200.0,
  "modal_price_lag_7": 1150.0,
  "modal_price_lag_14": 1100.0,
  "modal_price_roll_mean_7": 1175.0,
  "modal_price_roll_std_7": 35.0,
  "modal_price_roll_mean_14": 1160.0,
  "modal_price_roll_std_14": 40.0,
  "modal_price_roll_mean_30": 1140.0,
  "modal_price_roll_std_30": 50.0,
  "min_price": 1100.0,
  "max_price": 1300.0
}
```

**Response:**
```json
{
  "request_id": "40f5f999-721f-4ca4-9a9a-23a9af902703",
  "execution_status": "SUCCESS",
  "predicted_modal_price": 949.46,
  "model_file": "price_predictor_20260815T065020Z_78d16a7e.joblib",
  "model_version": "20260815T065020Z",
  "trained_at": "20260815T065020Z",
  "data_hash": "78d16a7e9a219fa2cb1711dfdbe74546cf0e6ae84350857997f6e77022c65392",
  "features_used": ["state", "commodity", "grade", "..."],
  "features_missing": [],
  "replay_file": "evidence_packet/replay_logs/40f5f999-....json"
}
```

**Status codes:**
| Code | Meaning |
|---|---|
| 200 | Successful prediction |
| 422 | Invalid input or inference error |
| 503 | No trained model available |

---

## Model Version Identification

Every response includes:
- `request_id` — UUID per request (for tracing)
- `model_file` — exact filename of model used
- `model_version` — timestamp of training run
- `data_hash` — SHA-256 hash of training data

Every model saved in `models/` has a companion `.json` metadata file:
models/
price_predictor_20260815T065020Z_78d16a7e.joblib
price_predictor_20260815T065020Z_78d16a7e.json

---

## Test Commands

```bash
# Run all tests (74 tests)
pytest tests/ -v

# Run unit tests only
pytest tests/ -v --ignore=tests/integration/

# Run integration tests only
pytest tests/integration/ -v

# Save test output to evidence packet
pytest tests/ -v --tb=short 2>&1 | tee evidence_packet/runtime_logs/test_results_v2.txt
```

---

## Local Integration Harness

```bash
# Start API first (in a separate terminal)
uvicorn src.api.main:app --port 8000

# Producer — sends real data row to API
python scripts/producer.py
python scripts/producer.py --commodity Onion --state Maharashtra
python scripts/producer.py --random

# Consumer — processes prediction result
python scripts/consumer.py

# Replay — proves determinism
python scripts/replay_runner.py --latest
python scripts/replay_runner.py --list
python scripts/replay_runner.py --request-id <uuid>
```

---

## Evidence and Replay Mechanism

Every prediction request is automatically recorded:
evidence_packet/replay_logs/<request_id>.json

Each replay file contains:
- `request_id` — unique execution ID
- `recorded_at` — UTC timestamp
- `status` — SUCCESS or FAILED
- `payload` — exact input sent
- `result` — exact output received
- `model_file` — model used
- `data_hash` — data version used

**To replay any execution:**
```bash
python scripts/replay_runner.py --request-id <uuid>
```

**Determinism is proven when:**

This was verified live:
Original prediction : 949.46
Replayed prediction : 949.46
RESULT: DETERMINISTIC — predictions match exactly ✓

---

## Docker Commands

```bash
# Build and start API + MongoDB
docker compose -f docker/docker-compose.yml up --build

# Start in background
docker compose -f docker/docker-compose.yml up -d --build

# Stop
docker compose -f docker/docker-compose.yml down

# View logs
docker logs aiaic_ml_api
docker logs aiaic_mongo
```

Service will be available at `http://localhost:8000` after containers start.

---

## Failure Behaviour

| Scenario | Behaviour |
|---|---|
| No model trained | `/v1/ready` returns 503, `/v1/predict` returns 503 |
| Invalid input fields | Returns 422 with Pydantic validation detail |
| All lag features missing | Returns 422 with inference error (documented limitation) |
| MongoDB unreachable | Service continues — falls back to local JSON |
| Model inference crash | Returns 422 with error detail, execution recorded as FAILED |
| Unhandled exception | Returns 500 with clean JSON, full traceback logged server-side |

---

## Known Limitations

- Model reload requires API restart (no hot-reload of new models)
- Docker not smoke-tested locally — Docker Desktop unavailable
- Lag/rolling features must be pre-computed by caller for best accuracy
- MongoDB optional — version tracking falls back to local JSON files
- Single global model — not per-commodity specialized models
- No automated retraining trigger — manual `run_pipeline.py` required

---

## Handover — Zero Context Setup

A reviewer with no prior context can reproduce the full system:

```bash
# 1. Install
pip install -r requirements.txt

# 2. Place datasets in data/raw/

# 3. Train
python run_pipeline.py --save-report

# 4. Start API
uvicorn src.api.main:app --port 8000

# 5. Hit API
curl -X POST http://localhost:8000/v1/predict \
  -H "Content-Type: application/json" \
  -d '{"commodity":"Onion","state":"Maharashtra","month":8}'

# 6. Run tests
pytest tests/ -v

# 7. Run Docker
docker compose -f docker/docker-compose.yml up --build

# 8. Inspect evidence
ls evidence_packet/replay_logs/

# 9. Replay an execution
python scripts/replay_runner.py --latest
```

---

## Structured Observability

All logs are structured JSON — every line is a valid JSON object:

```json
{
  "timestamp": "2026-09-04T04:26:28.344373+00:00",
  "level": "INFO",
  "logger": "src.api.routes",
  "message": "Prediction successful",
  "request_id": "40f5f999-721f-4ca4-9a9a-23a9af902703",
  "predicted_modal_price": 949.46,
  "model_file": "price_predictor_20260815T065020Z_78d16a7e.joblib"
}
```

Logs can be ingested by any log aggregator without parsing.