# --- AIAIC ML Foundation: the price FORECAST service (/v1/forecast), as AIAIC runs it ---
#
# The image carries ITS model. models/release/ must hold one trained bundle (forecast_*.json, forecast_*.joblib,
# forecast_*_history.csv.gz) and SHA256SUMS, as written by scripts/package_forecast_release.py (or downloaded from
# the GitHub release that holds them). The build FAILS if a file is missing or does not match its checksum, so an
# image can never start without its model, or with a different one than its release names.
#
# MongoDB is not part of the service: it only ever mirrored training-run logs.
#
#   python scripts/package_forecast_release.py --from models/forecast_pilot
#   docker build -f docker/Dockerfile -t aiaic-ml-foundation:<release tag> .

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AIAIC_MODELS_DIR=/app/models/release

WORKDIR /app

# libgomp1: the OpenMP runtime LightGBM needs on slim images.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Only what serving needs, at the SAME versions that trained the model (a joblib model must be loaded by the
# library versions that wrote it).
COPY requirements-serve.txt .
RUN pip install --no-cache-dir -r requirements-serve.txt

COPY src/ ./src/
COPY models/release/ ./models/release/
RUN cd /app/models/release \
    && sha256sum -c SHA256SUMS \
    && test "$(ls forecast_*.json | wc -l)" = "1" \
    && ls forecast_*.joblib forecast_*_history.csv.gz

RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# /v1/ready answers 200 only when the forecast model is loaded, so "healthy" means "can answer".
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/v1/ready', timeout=4).status == 200 else 1)" || exit 1

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
