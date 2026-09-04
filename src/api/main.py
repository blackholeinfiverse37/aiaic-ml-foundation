"""
FastAPI application entry point — AIAIC ML Foundation v1.

Run locally:
    uvicorn src.api.main:app --reload --port 8000

Run in Docker:
    docker compose -f docker/docker-compose.yml up --build
"""

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from src.config.settings import settings
from src.api.routes import router
from src.observability.logger import setup_structured_logging, get_logger

setup_structured_logging(level=settings.log_level)
logger = get_logger(__name__)

app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description=(
        "AIAIC ML Foundation — Crop Price Prediction Service v1. "
        "Versioned, observable, replay-capable inference API."
    ),
)

app.include_router(router)


@app.get("/")
def root():
    logger.info("Root endpoint hit")
    return {
        "service": settings.api_title,
        "version": settings.api_version,
        "api_v1": "/v1",
        "docs": "/docs",
        "health": "/v1/health",
        "ready": "/v1/ready",
        "predict": "/v1/predict",
    }


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    logger.exception(
        "Unhandled exception",
        extra={"path": str(request.url.path), "error": str(exc)}
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "execution_status": "FAILED"}
    )