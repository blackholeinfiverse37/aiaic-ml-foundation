"""
API routes for the AIAIC ML Foundation v1 service.

v1 changes:
- All routes under /v1/ prefix
- Every response includes request_id and execution_status
- /ready endpoint added (separate from /health)
- Every prediction is recorded for replay
"""

import logging
import uuid

from fastapi import APIRouter, HTTPException, Request

from src.api.schemas import (
    PredictionRequest, PredictionResponse,
    HealthResponse, ReadyResponse, ErrorResponse,
)
from src.inference.predictor import predict_price, PredictionError, _get_model_and_metadata
from src.storage.mongo_client import mongo_is_available
from src.observability.replay import record_execution
from src.observability.logger import get_logger
from src.config.settings import settings

logger = get_logger(__name__)

router = APIRouter(prefix="/v1")


@router.get("/health", response_model=HealthResponse)
def health_check():
    """
    Reports service liveness. Always returns 200 — even when degraded.
    A health check that itself crashes is worse than useless.
    """
    model_loaded = False
    model_file = None
    model_version = None

    try:
        _, metadata = _get_model_and_metadata()
        model_loaded = True
        model_file = metadata.get("model_file")
        model_version = metadata.get("trained_at")
    except Exception as e:
        logger.warning("Health check: no model loaded", extra={"error": str(e)})

    status = "ok" if model_loaded else "degraded"
    logger.info("Health check", extra={"status": status, "model_loaded": model_loaded})

    return HealthResponse(
        status=status,
        model_loaded=model_loaded,
        model_file=model_file,
        model_version=model_version,
        mongo_available=mongo_is_available(),
        api_version=settings.api_version,
    )


@router.get("/ready", response_model=ReadyResponse)
def ready_check():
    """
    Readiness check — returns 200 only when the service is fully ready
    to serve predictions (model loaded). Returns 503 if not ready.
    Used by orchestrators (Docker, k8s) to decide whether to send traffic.
    """
    try:
        _get_model_and_metadata()
        logger.info("Readiness check passed")
        return ReadyResponse(ready=True)
    except Exception as e:
        logger.warning("Readiness check failed", extra={"error": str(e)})
        raise HTTPException(
            status_code=503,
            detail=f"Service not ready: {e}"
        )


@router.post("/predict", response_model=PredictionResponse)
def predict(request: PredictionRequest):
    """
    Predicts modal crop price.
    Every request is assigned a unique request_id and recorded for replay.

    Returns:
        200 — successful prediction
        422 — inference error (model failed on input)
        503 — no model trained yet
    """
    request_id = str(uuid.uuid4())
    payload = request.model_dump()

    logger.info(
        "Prediction request received",
        extra={
            "request_id": request_id,
            "commodity": payload.get("commodity"),
            "state": payload.get("state"),
        }
    )

    try:
        result = predict_price(payload)
    except PredictionError as e:
        message = str(e)
        record_execution(
            request_id=request_id,
            payload=payload,
            result={},
            status="FAILED",
            error=message,
        )
        logger.error(
            "Prediction failed",
            extra={"request_id": request_id, "error": message}
        )
        if "No trained model found" in message:
            raise HTTPException(status_code=503, detail=message)
        raise HTTPException(status_code=422, detail=message)

    replay_file = record_execution(
        request_id=request_id,
        payload=payload,
        result=result,
        status="SUCCESS",
    )

    logger.info(
        "Prediction successful",
        extra={
            "request_id": request_id,
            "predicted_modal_price": result["predicted_modal_price"],
            "model_file": result.get("model_file"),
        }
    )

    return PredictionResponse(
        request_id=request_id,
        execution_status="SUCCESS",
        predicted_modal_price=result["predicted_modal_price"],
        model_file=result.get("model_file"),
        model_version=result.get("trained_at"),
        trained_at=result.get("trained_at"),
        data_hash=result.get("data_hash"),
        features_used=result.get("features_used", []),
        features_missing=result.get("features_missing", []),
        replay_file=str(replay_file),
    )