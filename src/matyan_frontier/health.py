"""Health and readiness probe endpoints.

``/health/live`` — lightweight liveness check (process is running).
``/health/ready`` — readiness check: verifies Kafka producer is started and
optionally reports S3 reachability.  Returns 503 when Kafka is not ready.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from loguru import logger

from .config import SETTINGS
from .kafka.producer import get_producer

health_router = APIRouter(prefix="/health", tags=["health"])


@health_router.get("/live/")
async def liveness() -> dict:
    return {"status": "ok"}


def _check_kafka() -> bool:
    producer = get_producer()
    return producer._producer is not None  # noqa: SLF001


@health_router.get("/ready/")
async def readiness(request: Request) -> JSONResponse:
    checks: dict[str, object] = {}
    healthy = True

    try:
        kafka_ok = _check_kafka()
        checks["kafka"] = "ok" if kafka_ok else "producer not started"
        if not kafka_ok:
            healthy = False
    except Exception as exc:  # noqa: BLE001
        checks["kafka"] = str(exc)
        healthy = False

    try:
        s3_client = getattr(request.app.state, "s3_client", None)
        if s3_client is not None:
            await s3_client.head_bucket(Bucket=SETTINGS.s3_bucket)
            checks["s3"] = "ok"
        else:
            checks["s3"] = "client not initialized"
    except Exception as exc:  # noqa: BLE001
        checks["s3"] = str(exc)
        logger.warning("S3 health check failed: {}", exc)

    status_code = 200 if healthy else 503
    return JSONResponse(
        {"status": "ok" if healthy else "degraded", "checks": checks},
        status_code=status_code,
    )
