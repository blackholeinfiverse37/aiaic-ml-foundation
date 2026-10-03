"""
API routes for the AIAIC ML Foundation v1 service: liveness, readiness, and the retired /v1/predict.

The served model is the FORECAST (`src/forecast`, `/v1/forecast`), the one AIAIC calls. /health and /ready describe
it. /v1/predict is retired (410 Gone): it read the SAME day's min and max price to predict that day's modal price,
so it described a day already known, and its R² of 0.99 measured that, not forecasting skill. Its training code
stays in `src/training` as Test 1 history; nothing serves it.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from src.api.schemas import HealthResponse, ReadyResponse
from src.config.settings import settings
from src.forecast.service import ForecastUnavailable, load_bundle
from src.observability.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/v1")

PREDICT_RETIRED = (
    "/v1/predict is retired. It read the same day's min and max price, so it described a price already known. "
    "Use POST /v1/forecast: a range for a future day, from prices known on the day asked, with its backtest."
)


def _forecast_meta() -> dict:
    """The served forecast's metadata; raises ForecastUnavailable when no trained bundle is in models_dir."""
    return load_bundle(str(settings.models_dir))["meta"]


@router.get("/health", response_model=HealthResponse)
def health_check():
    """
    Liveness. Always 200, even when degraded (a health check that crashes is worse than useless).
    `status` is "ok" only when the forecast model is loaded; orchestrators that need a model use /v1/ready.
    """
    try:
        meta = _forecast_meta()
    except (ForecastUnavailable, OSError, ValueError, KeyError) as e:
        logger.warning("Health check: no forecast model loaded", extra={"error": str(e)})
        return HealthResponse(status="degraded", model_loaded=False, api_version=settings.api_version)
    return HealthResponse(
        status="ok",
        model_loaded=True,
        model_file=meta.get("model_file"),
        model_version=meta.get("trained_at"),
        trained_through=meta.get("trained_through"),
        data_hash=meta.get("data_hash"),
        api_version=settings.api_version,
    )


@router.get("/ready", response_model=ReadyResponse)
def ready_check():
    """
    Readiness: 200 only when the forecast model is loaded, 503 otherwise. The Docker HEALTHCHECK calls this, so a
    container without a model is reported unhealthy instead of healthy-and-empty.
    """
    try:
        _forecast_meta()
    except (ForecastUnavailable, OSError, ValueError, KeyError) as e:
        logger.warning("Readiness check failed", extra={"error": str(e)})
        raise HTTPException(status_code=503, detail=f"Service not ready: {e}") from None
    return ReadyResponse(ready=True)


@router.api_route("/predict", methods=["GET", "POST"], include_in_schema=False)
def predict_retired():
    return JSONResponse(status_code=410, content={"detail": PREDICT_RETIRED, "execution_status": "FAILED",
                                                  "use": "/v1/forecast"})
