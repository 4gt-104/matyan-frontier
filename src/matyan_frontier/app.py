from __future__ import annotations

import asyncio
import time
import uuid
from contextlib import AsyncExitStack, asynccontextmanager
from typing import TYPE_CHECKING

import aioboto3
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from botocore.config import Config as BotoConfig
from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from google.cloud import storage
from loguru import logger
from prometheus_client import generate_latest
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from .config import SETTINGS, validate_settings
from .health import health_router
from .kafka.producer import get_producer
from .log_context import set_request_id
from .logging import configure_logging
from .metrics import HTTP_REQUEST_DURATION, HTTP_REQUESTS_TOTAL, normalize_path
from .rest import rest_router
from .ws import ws_router

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from typing import Any

    from types_aiobotocore_s3.client import S3Client

configure_logging(SETTINGS.log_level)


class RequestTimingMiddleware(BaseHTTPMiddleware):
    """Log method, path, status and elapsed time; record Prometheus metrics."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        req_id = str(uuid.uuid4())
        request.state.request_id = req_id
        set_request_id(req_id)

        start = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        elapsed = time.perf_counter() - start
        logger.trace(
            "{method} {path} -> {status} ({elapsed:.1f}ms)",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            elapsed=elapsed * 1000,
        )
        if SETTINGS.metrics_enabled:
            path_template = normalize_path(request.url.path)
            status_class = f"{response.status_code // 100}xx"
            HTTP_REQUESTS_TOTAL.labels(
                method=request.method,
                path_template=path_template,
                status_class=status_class,
            ).inc()
            HTTP_REQUEST_DURATION.labels(
                method=request.method,
                path_template=path_template,
                status_class=status_class,
            ).observe(elapsed)
        return response


def _s3_client_kwargs(endpoint_url: str) -> dict[str, Any]:
    return {
        "service_name": "s3",
        "endpoint_url": endpoint_url,
        "aws_access_key_id": SETTINGS.s3_access_key,
        "aws_secret_access_key": SETTINGS.s3_secret_key,
        "config": BotoConfig(signature_version="s3v4"),
        "region_name": SETTINGS.s3_region,
    }


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:  # noqa: PLR0915
    validate_settings(SETTINGS)

    producer = get_producer()
    await producer.start()

    if SETTINGS.blob_backend_type == "gcs":
        gcs_client = storage.Client()
        app.state.gcs_client = gcs_client
        app.state.gcs_presign_client = gcs_client

        def _ensure_gcs_bucket() -> None:
            b = gcs_client.bucket(SETTINGS.gcs_bucket)
            if not b.exists():
                b.create()
                logger.info("Created GCS bucket {!r}", SETTINGS.gcs_bucket)

        await asyncio.to_thread(_ensure_gcs_bucket)

        try:
            yield
        finally:
            logger.info("Shutdown: flushing Kafka producer…")
            await producer.flush(timeout=SETTINGS.shutdown_flush_timeout)
            logger.info("Shutdown: stopping Kafka producer…")
            await producer.stop()
            logger.info("Shutdown complete")

    elif SETTINGS.blob_backend_type == "azure":
        if SETTINGS.azure_conn_str:
            azure_client = BlobServiceClient.from_connection_string(SETTINGS.azure_conn_str)
        else:
            azure_client = BlobServiceClient(
                account_url=SETTINGS.azure_account_url,
                credential=DefaultAzureCredential(),
            )

        app.state.azure_presign_client = azure_client

        def _ensure_azure_container() -> None:
            container = azure_client.get_container_client(SETTINGS.azure_container)
            if not container.exists():
                container.create_container()
                logger.info("Created Azure container {!r}", SETTINGS.azure_container)

        await asyncio.to_thread(_ensure_azure_container)

        try:
            yield
        finally:
            logger.info("Shutdown: flushing Kafka producer…")
            await producer.flush(timeout=SETTINGS.shutdown_flush_timeout)
            logger.info("Shutdown: stopping Kafka producer…")
            await producer.stop()
            logger.info("Shutdown complete")

    else:
        session = aioboto3.Session()
        stack = AsyncExitStack()
        s3_client: S3Client = await stack.enter_async_context(
            session.client(**_s3_client_kwargs(SETTINGS.s3_endpoint)),
        )

        presign_endpoint = SETTINGS.s3_public_endpoint or SETTINGS.s3_endpoint
        s3_presign_client: S3Client = await stack.enter_async_context(
            session.client(**_s3_client_kwargs(presign_endpoint)),
        )

        app.state.s3_client = s3_client
        app.state.s3_presign_client = s3_presign_client

        try:
            yield
        finally:
            logger.info("Shutdown: flushing Kafka producer…")
            await producer.flush(timeout=SETTINGS.shutdown_flush_timeout)
            logger.info("Shutdown: stopping Kafka producer…")
            await producer.stop()
            logger.info("Shutdown: closing S3 clients…")
            await stack.aclose()
            logger.info("Shutdown complete")


app = FastAPI(title="Matyan Frontier", lifespan=lifespan)

app.add_middleware(RequestTimingMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=SETTINGS.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

metrics_router = APIRouter(tags=["metrics"])


@metrics_router.get("/metrics/")
async def prometheus_metrics() -> Response:
    return Response(
        content=await asyncio.to_thread(generate_latest),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


app.include_router(ws_router, prefix="/api/v1")
app.include_router(rest_router, prefix="/api/v1")
app.include_router(metrics_router)
app.include_router(health_router)
