"""
Tests for FastAPI routes — health check, predict endpoint,
input validation, error handling. Updated for v1 routes.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from src.api.main import app

client = TestClient(app)


def test_root_returns_200():
    response = client.get("/")
    assert response.status_code == 200
    assert "service" in response.json()


def test_health_returns_200():
    response = client.get("/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "model_loaded" in data
    assert "mongo_available" in data


def test_health_degraded_when_no_model():
    with patch("src.api.routes._get_model_and_metadata") as mock:
        mock.side_effect = FileNotFoundError("No model")
        response = client.get("/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["model_loaded"] is False


def test_predict_returns_200_with_valid_payload():
    mock_model = MagicMock()
    mock_model.predict.return_value = [1207.52]
    mock_metadata = {
        "feature_columns": ["commodity", "state", "grade", "month",
                            "day_of_week", "is_weekend", "season",
                            "month_sin", "month_cos",
                            "modal_price_lag_1", "modal_price_lag_7",
                            "modal_price_lag_14",
                            "modal_price_roll_mean_7", "modal_price_roll_std_7",
                            "modal_price_roll_mean_14", "modal_price_roll_std_14",
                            "modal_price_roll_mean_30", "modal_price_roll_std_30",
                            "min_price", "max_price"],
        "model_file": "test_model.joblib",
        "trained_at": "20260814T000000Z",
        "data_hash": "abc123",
    }
    with patch("src.inference.predictor._get_model_and_metadata",
               return_value=(mock_model, mock_metadata)):
        response = client.post("/v1/predict", json={
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
        })
    assert response.status_code == 200
    data = response.json()
    assert data["predicted_modal_price"] == 1207.52
    assert "features_used" in data
    assert "request_id" in data
    assert "execution_status" in data


def test_predict_422_missing_required_fields():
    """commodity and state are required — missing them fails Pydantic validation."""
    response = client.post("/v1/predict", json={"month": 8})
    assert response.status_code == 422


def test_predict_503_when_no_model():
    with patch("src.inference.predictor._get_model_and_metadata") as mock:
        mock.side_effect = FileNotFoundError("No trained model found")
        response = client.post("/v1/predict", json={
            "commodity": "Onion",
            "state": "Maharashtra",
            "month": 8,
        })
    assert response.status_code == 503