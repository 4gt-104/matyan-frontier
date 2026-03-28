"""Tests for rest/artifacts.py: presign endpoint, ensure_bucket (aioboto3)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from botocore.exceptions import ClientError


if TYPE_CHECKING:
    from fastapi.testclient import TestClient


class TestPresignEndpoint:
    def test_returns_upload_url_and_s3_key(self, client: TestClient) -> None:
        mock_presign = client.app.state.s3_presign_client  # ty:ignore[unresolved-attribute]
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
        mock_presign = client.app.state.s3_presign_client  # ty:ignore[unresolved-attribute]
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
