# Architecture Summary

**Service:** AIAIC ML Foundation — Crop Price Prediction  
**Candidate:** Aryan Sawant  
**Date:** August 2026  

---

## What This Service Does

Ingests real Indian mandi price data, validates and cleans it, engineers
time-series features, trains a LightGBM regression model, and serves
predictions via a FastAPI REST API — all in a single deterministic,
replay-safe pipeline.

---

## Pipeline Flow
data/raw/.csv (740,125 rows — real mandi price data, 2023–2025)
│
▼
┌─────────────────────────────────────┐
│ STAGE 1 — INGESTION │
│ │
│ csv_loader.py │
│ → Loads all CSVs from data/raw/ │
│ → Normalizes column names to │
│ canonical schema regardless │
│ of source formatting │
│ │
│ dataset_registry.py │
│ → Computes SHA-256 content hash │
│ → Writes version manifest JSON │
│ → Mirrors to MongoDB (optional) │
└────────────────┬────────────────────┘
│ 740,125 rows + hash recorded
▼
┌─────────────────────────────────────┐
│ STAGE 2 — VALIDATION │
│ │
│ schema.py │
│ → Declares required columns and │
│ expected dtypes │
│ │
│ validation/pipeline.py │
│ → Checks required fields (null) │
│ → Parses and validates dates │
│ → Checks price sanity bounds │
│ → Quarantines bad rows with reason │
│ (NOT silent drop) │
└────────────────┬────────────────────┘
│ 737,389 clean rows
│ 2,736 quarantined (logged)
▼
┌─────────────────────────────────────┐
│ STAGE 3 — PREPROCESSING │
│ │
│ missing_values.py │
│ → Group-median fill for prices │
│ (within commodity + state group) │
│ → Constant placeholder fill for │
│ categoricals (district, market) │
│ → Target column (modal_price) │
│ never imputed — rows dropped │
│ │
│ outliers.py │
│ → MAD-based robust z-score │
│ (not mean/std — outlier-stable) │
│ → Computed per commodity+state │
│ group (prices vary by crop) │
│ → Outliers capped, not dropped │
└────────────────┬────────────────────┘
│ 737,389 rows (no rows lost)
▼
┌─────────────────────────────────────┐
│ STAGE 4 — FEATURE ENGINEERING │
│ │
│ lag_features.py │
│ → modal_price_lag_1 (1 day ago) │
│ → modal_price_lag_7 (7 days ago) │
│ → modal_price_lag_14 (14 days ago) │
│ → Per commodity+state group │
│ │
│ rolling_features.py │
│ → Rolling mean + std │
│ over 7 / 14 / 30 day windows │
│ → shift(1) applied before rolling │
│ — NO leakage of today's price │
│ │
│ season_encoding.py │
│ → kharif / rabi / zaid seasons │
│ → month_sin + month_cos │
│ (cyclical encoding) │
│ → day_of_week, is_weekend │
└────────────────┬────────────────────┘
│ 735,774 rows
│ (1,615 dropped — insufficient history
│ at series start, expected)
▼
┌─────────────────────────────────────┐
│ STAGE 5 — TRAINING │
│ │
│ train.py │
│ → Time-based split (NOT random) │
│ last 30 days = test set │
│ Train: 699,750 | Test: 36,024 │
│ → LightGBM regressor │
│ (random_seed=42, deterministic) │
│ │
│ evaluate.py │
│ → MAE : 44.07 INR/quintal │
│ → RMSE : 91.69 INR/quintal │
│ → MAPE : 4.52% │
│ → R² : 0.9946 │
│ → Baseline MAE (naive lag-1): │
│ 435.46 → model is 10x better │
│ │
│ persistence.py │
│ → Saves model as .joblib │
│ → Saves metadata as .json │
│ (feature list, metrics, hash) │
│ │
│ run_registry.py │
│ → Logs run to local JSON │
│ → Mirrors to MongoDB (optional) │
└────────────────┬────────────────────┘
│ models/price_predictor_.joblib
▼
┌─────────────────────────────────────┐
│ FASTAPI INFERENCE SERVICE │
│ │
│ predictor.py │
│ → Loads model once (lru_cache) │
│ → Builds feature row from payload │
│ → Handles missing features safely │
│ │
│ routes.py │
│ → POST /predict │
│ 200 → predicted_modal_price │
│ 422 → inference error │
│ 503 → no model trained yet │
│ → GET /health │
│ reports model_loaded, │
│ mongo_available, status │
│ │
│ schemas.py │
│ → Pydantic request validation │
│ → Structured response types │
└─────────────────────────────────────┘

---

## Replay Safety — How It Works

Every stage computes a SHA-256 hash of the dataframe and writes a manifest:

raw_2910ec7fd15d.json ← ingestion output
└─ parent_hash: null

validated_84322ce525d7.json ← validation output
└─ parent_hash: 2910ec7fd15d

processed_971f9394762c.json ← preprocessing output
└─ parent_hash: 84322ce525d7

features_78d16a7e9a21.json ← feature engineering output
└─ parent_hash: 971f9394762c
Any training run can be reproduced exactly by tracing back through
the hash chain to the original source data.

---

## MongoDB Usage (Optional)

| Collection | What it stores | Fallback if unavailable |
|---|---|---|
| `dataset_versions` | Hash manifests for each stage | Local JSON in data/versions/ |
| `training_runs` | Run metadata, metrics, model path | Local JSON in data/versions/training_runs/ |

MongoDB connection times out in 2 seconds and fails silently.
The pipeline never blocks or crashes due to MongoDB being unavailable.

---

## Integration Points for AIAIC Platform

```python
# Option 1 — Direct Python import (for internal service use)
from src.inference.predictor import predict_price

result = predict_price({
    "commodity": "Onion",
    "state": "Maharashtra",
    "grade": "FAQ",
    "month": 8,
    "season": "kharif",
    "modal_price_lag_1": 1200.0,
    "modal_price_roll_mean_7": 1175.0,
    ...
})
# result["predicted_modal_price"] → 1207.52


# Option 2 — HTTP REST (for cross-service use)
POST http://localhost:8000/predict
Content-Type: application/json
{ ...same payload... }
```

Feature columns consumed by the model are stored in the model's companion
`.json` metadata file — no hardcoded column lists in integration code.

---

## Technology Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| ML Model | LightGBM (LGBMRegressor) |
| Data processing | Pandas 2.2, NumPy |
| Model serialization | Joblib |
| API framework | FastAPI + Uvicorn |
| Request validation | Pydantic v2 |
| Database (optional) | MongoDB via PyMongo |
| Testing | Pytest (42 tests) |
| Containerization | Docker + Docker Compose |
| Version tracking | SHA-256 content hashing (custom) |