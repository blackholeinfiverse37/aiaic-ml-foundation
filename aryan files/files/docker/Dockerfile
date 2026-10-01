# --- AIAIC ML Foundation - Crop Price Prediction Service ---
# Multi-stage build kept simple (single stage) since this is a
# service, not a compiled binary — the main goal here is a small,
# reproducible image, not build-time optimization.

FROM python:3.11-slim

# Prevents Python from writing .pyc files and buffers stdout, so logs
# show up immediately in `docker logs` instead of being buffered.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps needed by lightgbm/xgboost wheels on slim images.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (separate layer) so code changes don't
# invalidate the dependency cache on every rebuild.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and data directories (raw/ populated by
# ingestion at runtime or mounted via volume — see docker-compose.yml).
COPY src/ ./src/
COPY data/ ./data/
COPY models/ ./models/

# Non-root user for basic container hygiene.
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Health check hits our own /health endpoint so `docker ps` and
# orchestrators (Compose, k8s) can detect a degraded (no model) state.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/v1/health')" || exit 1

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]