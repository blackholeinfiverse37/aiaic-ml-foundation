"""
Routes with NO model present (a clean clone, or a container whose model is missing): liveness answers and says
"degraded", readiness and the forecast answer 503, and the retired /v1/predict answers 410 everywhere.
"""

import pytest
from fastapi.testclient import TestClient

from src.forecast import service


@pytest.fixture
def client(monkeypatch, tmp_path):
    from src.api.main import app
    from src.config.settings import settings
    monkeypatch.setattr(settings, "models_dir", tmp_path)     # an empty models directory
    service.reset_cache()
    yield TestClient(app)
    service.reset_cache()


def test_root_lists_the_forecast_and_names_predict_as_retired(client):
    data = client.get("/").json()
    assert data["forecast"] == "/v1/forecast"
    assert "predict" not in data and "/v1/predict" in data["retired"]


def test_health_is_200_and_degraded_without_a_model(client):
    r = client.get("/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "degraded" and r.json()["model_loaded"] is False


def test_ready_is_503_without_a_model(client):
    assert client.get("/v1/ready").status_code == 503


def test_the_forecast_is_503_without_a_model_and_says_how_to_train(client):
    r = client.post("/v1/forecast", json={"commodity": "Onion", "state": "Maharashtra", "market": "Lasalgaon",
                                          "as_of": "2026-08-26", "horizon_days": 7})
    assert r.status_code == 503
    assert "src.forecast.train" in r.json()["detail"]
    assert client.get("/v1/forecast/meta").status_code == 503


@pytest.mark.parametrize("method", ["get", "post"])
def test_predict_is_gone_and_points_to_the_forecast(client, method):
    r = getattr(client, method)("/v1/predict")
    assert r.status_code == 410
    assert r.json()["use"] == "/v1/forecast"


@pytest.mark.parametrize("bad", [
    {"horizon_days": 0}, {"horizon_days": 91}, {"market": ""}, {"as_of": "26/08/2026"}, {"commodity": "x" * 65},
])
def test_bad_input_is_422_before_any_model_is_touched(client, bad):
    body = {"commodity": "Onion", "state": "Maharashtra", "market": "Lasalgaon", "as_of": "2026-08-26",
            "horizon_days": 7, **bad}
    assert client.post("/v1/forecast", json=body).status_code == 422
