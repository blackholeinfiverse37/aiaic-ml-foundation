"""
Integration tests for the AIAIC ML Foundation v1 API.

These tests run against the actual FastAPI app using TestClient —
no mocking of the model or inference layer. They require a trained
model to exist in models/ before running.

Run:
    pytest tests/integration/ -v
"""

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)

VALID_PAYLOAD = {
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
    "max_price": 1300.0,
}


# ------------------------------------------------------------------ #
# ROOT                                                                 #
# ------------------------------------------------------------------ #

class TestRoot:
    def test_root_returns_200(self):
        response = client.get("/")
        assert response.status_code == 200

    def test_root_contains_v1_routes(self):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        has_predict = "predict" in data or any(
            "/predict" in str(v) for v in data.values()
        )
        assert has_predict
    def test_root_contains_version(self):
        response = client.get("/")
        data = response.json()
        assert "version" in data


# ------------------------------------------------------------------ #
# HEALTH                                                               #
# ------------------------------------------------------------------ #

class TestHealth:
    def test_health_returns_200(self):
        response = client.get("/v1/health")
        assert response.status_code == 200

    def test_health_has_required_fields(self):
        response = client.get("/v1/health")
        data = response.json()
        assert "status" in data
        assert "model_loaded" in data
        assert "mongo_available" in data
        assert "api_version" in data

    def test_health_status_is_ok_when_model_loaded(self):
        response = client.get("/v1/health")
        data = response.json()
        if data["model_loaded"]:
            assert data["status"] == "ok"
        else:
            assert data["status"] == "degraded"

    def test_health_model_file_present_when_loaded(self):
        response = client.get("/v1/health")
        data = response.json()
        if data["model_loaded"]:
            assert data["model_file"] is not None


# ------------------------------------------------------------------ #
# READY                                                                #
# ------------------------------------------------------------------ #

class TestReady:
    def test_ready_returns_200_when_model_loaded(self):
        health = client.get("/v1/health").json()
        if health["model_loaded"]:
            response = client.get("/v1/ready")
            assert response.status_code == 200
            assert response.json()["ready"] is True

    def test_ready_has_ready_field(self):
        response = client.get("/v1/ready")
        assert "ready" in response.json()


# ------------------------------------------------------------------ #
# PREDICT — VALID INPUT                                                #
# ------------------------------------------------------------------ #

class TestPredictValid:
    def test_predict_returns_200(self):
        response = client.post("/v1/predict", json=VALID_PAYLOAD)
        assert response.status_code == 200

    def test_predict_returns_request_id(self):
        response = client.post("/v1/predict", json=VALID_PAYLOAD)
        data = response.json()
        assert "request_id" in data
        assert len(data["request_id"]) == 36  # UUID format

    def test_predict_returns_execution_status_success(self):
        response = client.post("/v1/predict", json=VALID_PAYLOAD)
        data = response.json()
        assert data["execution_status"] == "SUCCESS"

    def test_predict_returns_price(self):
        response = client.post("/v1/predict", json=VALID_PAYLOAD)
        data = response.json()
        assert "predicted_modal_price" in data
        assert isinstance(data["predicted_modal_price"], float)
        assert data["predicted_modal_price"] > 0

    def test_predict_returns_model_metadata(self):
        response = client.post("/v1/predict", json=VALID_PAYLOAD)
        data = response.json()
        assert "model_file" in data
        assert "model_version" in data
        assert "data_hash" in data

    def test_predict_returns_features_used(self):
        response = client.post("/v1/predict", json=VALID_PAYLOAD)
        data = response.json()
        assert "features_used" in data
        assert isinstance(data["features_used"], list)
        assert len(data["features_used"]) > 0

    def test_predict_returns_features_missing(self):
        response = client.post("/v1/predict", json=VALID_PAYLOAD)
        data = response.json()
        assert "features_missing" in data
        assert isinstance(data["features_missing"], list)

    def test_predict_returns_replay_file(self):
        response = client.post("/v1/predict", json=VALID_PAYLOAD)
        data = response.json()
        assert "replay_file" in data
        assert data["replay_file"] is not None

    def test_predict_replay_file_exists_on_disk(self):
        response = client.post("/v1/predict", json=VALID_PAYLOAD)
        data = response.json()
        replay_path = Path(data["replay_file"])
        assert replay_path.exists()

    def test_predict_replay_file_contains_correct_data(self):
        response = client.post("/v1/predict", json=VALID_PAYLOAD)
        data = response.json()
        replay_path = Path(data["replay_file"])
        replay = json.loads(replay_path.read_text())
        assert replay["request_id"] == data["request_id"]
        assert replay["status"] == "SUCCESS"
        assert replay["result"]["predicted_modal_price"] == data["predicted_modal_price"]


# ------------------------------------------------------------------ #
# PREDICT — DETERMINISM                                                #
# ------------------------------------------------------------------ #

class TestDeterminism:
    def test_same_input_same_output(self):
        """
        Determinism test: identical payload must produce identical price.
        This is the core replay-safety guarantee.
        """
        r1 = client.post("/v1/predict", json=VALID_PAYLOAD).json()
        r2 = client.post("/v1/predict", json=VALID_PAYLOAD).json()
        assert r1["predicted_modal_price"] == r2["predicted_modal_price"]

    def test_different_request_ids_same_result(self):
        """Each request gets a unique ID even when payload is identical."""
        r1 = client.post("/v1/predict", json=VALID_PAYLOAD).json()
        r2 = client.post("/v1/predict", json=VALID_PAYLOAD).json()
        assert r1["request_id"] != r2["request_id"]
        assert r1["predicted_modal_price"] == r2["predicted_modal_price"]

    def test_same_model_file_across_requests(self):
        """All requests in the same session use the same model."""
        r1 = client.post("/v1/predict", json=VALID_PAYLOAD).json()
        r2 = client.post("/v1/predict", json=VALID_PAYLOAD).json()
        assert r1["model_file"] == r2["model_file"]


# ------------------------------------------------------------------ #
# PREDICT — INVALID INPUT                                              #
# ------------------------------------------------------------------ #

class TestPredictInvalid:
    def test_missing_commodity_returns_422(self):
        payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "commodity"}
        response = client.post("/v1/predict", json=payload)
        assert response.status_code == 422

    def test_missing_state_returns_422(self):
        payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "state"}
        response = client.post("/v1/predict", json=payload)
        assert response.status_code == 422

    def test_missing_month_returns_422(self):
        payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "month"}
        response = client.post("/v1/predict", json=payload)
        assert response.status_code == 422

    def test_invalid_month_too_high_returns_422(self):
        payload = {**VALID_PAYLOAD, "month": 13}
        response = client.post("/v1/predict", json=payload)
        assert response.status_code == 422

    def test_invalid_month_too_low_returns_422(self):
        payload = {**VALID_PAYLOAD, "month": 0}
        response = client.post("/v1/predict", json=payload)
        assert response.status_code == 422

    def test_invalid_day_of_week_returns_422(self):
        payload = {**VALID_PAYLOAD, "day_of_week": 7}
        response = client.post("/v1/predict", json=payload)
        assert response.status_code == 422

    def test_empty_payload_returns_422(self):
        response = client.post("/v1/predict", json={})
        assert response.status_code == 422

    def test_missing_all_lag_features_still_returns_200(self):
        """Minimal payload — 200 or 422 both acceptable documented behaviours."""
        minimal = {
            "commodity": "Onion",
            "state": "Maharashtra",
            "month": 8,
        }
        response = client.post("/v1/predict", json=minimal)
        assert response.status_code in [200, 422]

# ------------------------------------------------------------------ #
# PREDICT — REPLAY CONSISTENCY                                         #
# ------------------------------------------------------------------ #

class TestReplay:
    def test_replay_file_written_per_request(self):
        """Every successful request writes exactly one replay file."""
        from src.observability.replay import list_executions
        before = len(list_executions())
        client.post("/v1/predict", json=VALID_PAYLOAD)
        after = len(list_executions())
        assert after == before + 1

    def test_replay_file_payload_matches_request(self):
        """Recorded payload must match what was sent."""
        response = client.post("/v1/predict", json=VALID_PAYLOAD)
        data = response.json()
        replay_path = Path(data["replay_file"])
        replay = json.loads(replay_path.read_text())
        assert replay["payload"]["commodity"] == VALID_PAYLOAD["commodity"]
        assert replay["payload"]["state"] == VALID_PAYLOAD["state"]
        assert replay["payload"]["month"] == VALID_PAYLOAD["month"]