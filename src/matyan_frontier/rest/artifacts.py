from __future__ import annotations

import asyncio
import datetime
import importlib.metadata
import os
from typing import TYPE_CHECKING

from botocore.exceptions import ClientError
from fastapi import APIRouter, Request
from loguru import logger
from pydantic import BaseModel

from matyan_frontier.config import SETTINGS

if TYPE_CHECKING:
    from types_aiobotocore_s3.client import S3Client

rest_router = APIRouter(prefix="/rest")


def _get_frontier_version() -> str:
    """Return the installed matyan-frontier package version."""
    try:
        return importlib.metadata.version("matyan-frontier")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0.dev0"


@rest_router.get("/version/")
async def get_version() -> dict:
    """Return frontier version.

    :returns: JSON with ``version`` and ``component``.
    """
    return {
        "version": _get_frontier_version(),
        "component": "frontier",
    }


async def ensure_bucket(client: S3Client, bucket: str) -> None:
    """Create *bucket* if it does not exist yet (async, using aioboto3 client)."""
    try:
        await client.head_bucket(Bucket=bucket)
    except ClientError:
        await client.create_bucket(Bucket=bucket)
        logger.info("Created S3 bucket {!r}", bucket)


class PresignRequest(BaseModel):
    run_id: str
    artifact_path: str
    content_type: str = "application/octet-stream"


class PresignResponse(BaseModel):
    upload_url: str
    s3_key: str


@rest_router.post("/artifacts/presign", response_model=PresignResponse)
async def presign_upload(body: PresignRequest, request: Request) -> PresignResponse:
    s3_key = f"{body.run_id}/{body.artifact_path}"

    if SETTINGS.blob_backend_type == "gcs":
        gcs_presign_client = request.app.state.gcs_presign_client
        bucket = gcs_presign_client.bucket(SETTINGS.gcs_bucket)
        blob = bucket.blob(s3_key)

        if "STORAGE_EMULATOR_HOST" in os.environ:
            host = os.environ["STORAGE_EMULATOR_HOST"].replace("fake-gcs-server", "localhost")
            upload_url = f"{host}/upload/storage/v1/b/{SETTINGS.gcs_bucket}/o?uploadType=media&name={s3_key}"
        else:
            upload_url = await asyncio.to_thread(
                blob.generate_signed_url,
                expiration=datetime.timedelta(seconds=SETTINGS.s3_presign_expiry),
                method="PUT",
                content_type=body.content_type,
                version="v4",
            )
    else:
        presign_client: S3Client = request.app.state.s3_presign_client
        upload_url = await presign_client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": SETTINGS.s3_bucket,
                "Key": s3_key,
                "ContentType": body.content_type,
            },
            ExpiresIn=SETTINGS.s3_presign_expiry,
        )

    return PresignResponse(upload_url=upload_url, s3_key=s3_key)
