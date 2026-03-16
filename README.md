# Matyan Frontier

Ingestion gateway between training clients and the rest of the Matyan stack. Clients connect via **WebSocket** for metrics, params, and logs, and via **REST** for presigned S3 URLs; the frontier publishes to **Kafka**. The UI and backend do not talk to the frontier. Part of the Matyan experiment-tracking stack (fork of Aim).

## Layout

- **`src/matyan_frontier/`** — Python package: FastAPI app, WebSocket handler, REST presign endpoint, Kafka producer, config, health, metrics.
- **Entrypoints**: `app.py` (lifespan: start Kafka producer, create S3 clients, ensure bucket; shutdown: flush producer, close S3).
- **Routes**: `GET /api/v1/ws/runs/{run_id}` (WebSocket), `POST /api/v1/rest/artifacts/presign`, `GET /health/ready/`, `GET /health/live/`, `GET /metrics/` (Prometheus).

## Prerequisites

- Python 3.12+. The package uses `uv` in the repo: `uv run matyan-frontier` or install then `matyan-frontier` CLI.
- **Runtime dependencies**: Kafka (bootstrap reachable) and an S3-compatible store (e.g. MinIO/RustFS in dev, AWS S3 in prod). The smoke test and local dev assume Kafka and S3 are up (e.g. via docker-compose).

## Run (production-like)

From the frontier package directory: `uv run matyan-frontier start` (or `matyan-frontier start` if installed).

Options: `--host`, `--port` (defaults: `0.0.0.0`, `53801`). The CLI uses these option defaults; config also defines `host`/`port` for other entry points.

## Configuration (environment variables)

| Variable | Default | Purpose |
|----------|---------|---------|
| `MATYAN_ENVIRONMENT` / `ENVIRONMENT` | `development` | When `production`, S3/Kafka must be non-dev (validated at startup). |
| `LOG_LEVEL` | `INFO` | Log level (loguru + uvicorn). |
| `HOST` | `0.0.0.0` | Bind address. |
| `PORT` | `53801` | Bind port. |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Kafka broker list. |
| `KAFKA_DATA_INGESTION_TOPIC` | `data-ingestion` | Topic for ingestion messages. |
| `KAFKA_SECURITY_PROTOCOL` / `KAFKA_SASL_*` | (empty) | Optional Kafka SASL. |
| `S3_ENDPOINT` | `http://localhost:9000` | S3 API endpoint (e.g. MinIO). |
| `S3_PUBLIC_ENDPOINT` | `""` | Optional; used for presigned URLs if different from `S3_ENDPOINT`. |
| `S3_ACCESS_KEY` / `S3_SECRET_KEY` | (dev defaults) | S3 credentials. |
| `S3_BUCKET` | `matyan-artifacts` | Bucket for artifacts. |
| `S3_PRESIGN_EXPIRY` | `3600` | Presigned URL expiry (seconds). |
| `SHUTDOWN_FLUSH_TIMEOUT` | `5.0` | Seconds to wait for Kafka flush on shutdown. |
| `METRICS_ENABLED` | `true` | Expose Prometheus `/metrics/`. |
| `CORS_ORIGINS` | (localhost list) | Allowed origins (comma-separated or repeated). |

Source of truth: [config.py](src/matyan_frontier/config.py).

## Development and smoke test

- **Development**: Run Kafka and S3 (e.g. `docker compose up kafka kafka-init rustfs` or equivalent), then `uv run matyan-frontier start`. Clients (e.g. matyan-client) point at the frontier URL for WebSocket and presign.
- **Smoke test**: From `extra/matyan-frontier`, run `uv run python scripts/smoke_test.py`. Prerequisites: Kafka, S3, and frontier running. The script covers WebSocket (create_run, log_metric, log_hparams, finish_run, etc.) and REST presign, and optionally verifies Kafka consumption.

See [scripts/smoke_test.py](scripts/smoke_test.py) for the exact command and what it checks.

## Deployment

- **Docker**: Use [Dockerfile.dev](Dockerfile.dev) or [Dockerfile.prod](Dockerfile.prod) (context from repo root as needed; align with how the repo builds frontier images).
- **Kubernetes/Helm**: The chart in `deploy/helm/matyan` deploys the frontier as a separate Deployment. Configure Kafka and S3 via chart values (e.g. `kafka.*`, `s3.*`, `frontier.logLevel`, `frontier.replicaCount`). Ingress routes `/api/v1/ws` and `/api/v1/rest/artifacts` to the frontier. The frontier is stateless and can be scaled horizontally.

The UI talks only to the backend, not to the frontier; the frontier is for training clients.

## Related

- **Backend**: matyan-backend serves the REST API and consumes from Kafka (ingestion + control workers); it does not receive client traffic from the frontier directly.
- **Client**: matyan-client sends tracking data to the frontier (WebSocket + presign REST).
- **Monorepo**: This package lives under `extra/matyan-frontier` in the matyan-core repo.
