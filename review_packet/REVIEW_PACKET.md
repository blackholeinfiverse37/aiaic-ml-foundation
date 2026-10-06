# REVIEW PACKET — AIAIC ML Foundation
**Candidate:** Aryan Sawant
**Test:** Test 1 — ML Foundation & Prediction Service
**Intake:** AIAIC 7-4-3
**Submitted:** August 2026
**Status:** COMPLETE

---

## Quick Summary

| Item | Result |
|------|--------|
| Real dataset used | ✅ 740,125 rows, Indian mandi price data |
| Deterministic preprocessing | ✅ Hash-verified at every stage |
| Feature engineering | ✅ Lag (1/7/14d), rolling (7/14/30d), seasonal |
| Forecast-quality evidence | ❌ The retired `/v1/predict` scores below are invalid for forecasting: same-day min/max prices leaked into the target |
| Forecast service | `/v1/predict` retired (410); use `/v1/forecast` and its release backtest |
| FastAPI service | ✅ /predict + /health, Pydantic validated |
| Docker deployment | ✅ Dockerfile + docker-compose (API + Mongo) |
| Unit tests | ✅ 42/42 passing |
| Replay-safe | ✅ SHA-256 content hash at every pipeline stage |
| Integration-ready | ✅ No modifications to existing architecture |

---

## Folder Index

| Folder/File | Contents |
|-------------|----------|
| `REVIEW_PACKET.md` | This file — master index |
| `Executive_Assessment.md` | Self-assessment of build quality |
| `Assignment_vs_Delivery.md` | Line-by-line requirement mapping |
| `architecture_summary.md` | System architecture explanation |
| `known_limitations.md` | Honest gaps and assumptions |
| `screenshots/` | API, pipeline, test, repo screenshots |
| `code_packet/` | 8 key files with explanations |
| `api_samples/` | predict + health JSON samples |
| `runtime_logs/` | Pipeline run log + test results |
| `deployment_proof/` | Docker setup proof |

---

## Key Numbers

- **740,125** rows ingested
- **737,389** clean rows after validation
- **2,736** rows quarantined (logged with reasons)
- **735,774** rows used for training after feature engineering
- **699,750** training rows / **36,024** test rows (time-based split)
- **Retired `/v1/predict` metrics (not forecast quality):** R² 0.9946, MAE 44.07 INR/quintal, MAPE 4.52%.
  The endpoint used same-day min/max prices to predict the same day's modal price, so these figures are leakage-
  contaminated and must not be used as model-quality or production-accuracy claims.
- **42/42** unit tests passing
- **~55 seconds** full pipeline runtime on 740k rows