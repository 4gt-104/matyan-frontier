"""Health and readiness probe endpoints.

``/health/live`` — lightweight liveness check (process is running).
``/health/ready`` — readiness check: verifies Kafka producer is started and
optionally reports blob storage reachability.  Returns 503 when Kafka is not ready.
"""

from __future__ import annotations

import asyncio

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
async def readiness(request: Request) -> JSONResponse:  # noqa: C901, PLR0912
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
        if SETTINGS.blob_backend_type == "gcs":
            gcs_client = getattr(request.app.state, "gcs_client", None)
            if gcs_client is not None:
                bucket = gcs_client.bucket(SETTINGS.gcs_bucket)
                exists = await asyncio.to_thread(bucket.exists)
                if exists:
                    checks["blob"] = "ok"
                else:
                    checks["blob"] = "bucket not found"
            else:
                checks["blob"] = "client not initialized"
        elif SETTINGS.blob_backend_type == "azure":
            azure_client = getattr(request.app.state, "azure_presign_client", None)
            if azure_client is not None:
                container = azure_client.get_container_client(SETTINGS.azure_container)
                exists = await asyncio.to_thread(container.exists)
                if exists:
                    checks["blob"] = "ok"
                else:
                    checks["blob"] = "container not found"
            else:
                checks["blob"] = "client not initialized"
        else:
            s3_client = getattr(request.app.state, "s3_client", None)
            if s3_client is not None:
                await s3_client.head_bucket(Bucket=SETTINGS.s3_bucket)
                checks["blob"] = "ok"
            else:
                checks["blob"] = "client not initialized"
    except Exception as exc:  # noqa: BLE001
        checks["blob"] = str(exc)
        logger.warning("Storage health check failed: {}", exc)

    status_code = 200 if healthy else 503
    return JSONResponse(
        {"status": "ok" if healthy else "degraded", "checks": checks},
        status_code=status_code,
    )
