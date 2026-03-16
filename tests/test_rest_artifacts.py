"""Tests for rest/artifacts.py: presign endpoint, ensure_bucket (aioboto3)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from botocore.exceptions import ClientError

from matyan_frontier.rest.artifacts import ensure_bucket

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


class TestPresignEndpoint:
    def test_returns_upload_url_and_s3_key(self, client: TestClient) -> None:
        mock_presign = client.app.state.s3_presign_client
        mock_presign.generate_presigned_url = AsyncMock(
            return_value="https://s3.example.com/presigned",
        )

        resp = client.post(
            "/api/v1/rest/artifacts/presign",
            json={
                "run_id": "run123",
                "artifact_path": "images/test.png",
                "content_type": "image/png",
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["s3_key"] == "run123/images/test.png"
        assert data["upload_url"] == "https://s3.example.com/presigned"

    def test_default_content_type(self, client: TestClient) -> None:
        mock_presign = client.app.state.s3_presign_client
        mock_presign.generate_presigned_url = AsyncMock(
            return_value="https://example.com/url",
        )

        resp = client.post(
            "/api/v1/rest/artifacts/presign",
            json={"run_id": "r1", "artifact_path": "data.bin"},
        )

        assert resp.status_code == 200
        mock_presign.generate_presigned_url.assert_awaited_once()
        call_kwargs = mock_presign.generate_presigned_url.call_args
        assert call_kwargs.kwargs["Params"]["ContentType"] == "application/octet-stream"


class TestEnsureBucket:
    @pytest.mark.anyio
    async def test_creates_bucket_on_head_failure(self) -> None:
        mock_client = MagicMock()
        mock_client.head_bucket = AsyncMock(
            side_effect=ClientError(
                {"Error": {"Code": "404", "Message": "Not Found"}},
                "HeadBucket",
            ),
        )
        mock_client.create_bucket = AsyncMock()

        await ensure_bucket(mock_client, "test-bucket")
        mock_client.create_bucket.assert_awaited_once_with(Bucket="test-bucket")

    @pytest.mark.anyio
    async def test_no_create_when_bucket_exists(self) -> None:
        mock_client = MagicMock()
        mock_client.head_bucket = AsyncMock(return_value={})
        mock_client.create_bucket = AsyncMock()

        await ensure_bucket(mock_client, "test-bucket")
        mock_client.create_bucket.assert_not_awaited()
