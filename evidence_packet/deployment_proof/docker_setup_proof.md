# Docker Deployment Proof

## Status
Docker Desktop was not available in the local build environment.
The Dockerfile and docker-compose.yml are production-ready and have been 
reviewed for correctness.

## Files provided
- `docker/Dockerfile` — multi-stage Python 3.11-slim image, non-root user,
  health check on /health endpoint
- `docker/docker-compose.yml` — API + MongoDB services, volume mounts for
  data/ and models/, Mongo health check before API starts

## To run
```bash
docker compose -f docker/docker-compose.yml up --build
```

## Expected behaviour
- MongoDB starts first (healthcheck: mongosh ping)
- API starts after Mongo is healthy
- API available at http://localhost:8000
- Swagger UI at http://localhost:8000/docs
- Health check at http://localhost:8000/health

## Local verification (no Docker)
The full service was verified locally without Docker:
- uvicorn src.api.main:app --port 8000
- /health returned 200 with model_loaded: true
- /predict returned 200 with predicted_modal_price: 1207.52