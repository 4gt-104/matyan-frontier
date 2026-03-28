"""Tests for the /health/live and /health/ready endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

    from .conftest import MockKafkaProducer


class TestLiveness:
    def test_returns_200(self, client: TestClient) -> None:
        resp = client.get("/health/live/")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_without_trailing_slash(self, client: TestClient) -> None:
        resp = client.get("/health/live")
        assert resp.status_code == 200


class TestReadiness:
    def test_all_healthy(self, client: TestClient) -> None:
        resp = client.get("/health/ready/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["checks"]["kafka"] == "ok"
        assert "blob" in body["checks"]

    def test_kafka_not_started(
        self,
        client: TestClient,
        mock_producer: MockKafkaProducer,
    ) -> None:
        mock_producer._producer = None  # noqa: SLF001
        resp = client.get("/health/ready/")
        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "degraded"
        assert body["checks"]["kafka"] == "producer not started"

    def test_kafka_check_exception(self, client: TestClient) -> None:
        with patch(
            "matyan_frontier.health._check_kafka",
            side_effect=RuntimeError("boom"),
        ):
            resp = client.get("/health/ready/")
        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "degraded"
        assert "boom" in body["checks"]["kafka"]

    def test_s3_client_not_initialized(self, client: TestClient) -> None:
        original = client.app.state.s3_client  # ty:ignore[unresolved-attribute]
        try:
            del client.app.state.s3_client  # ty:ignore[unresolved-attribute]
            resp = client.get("/health/ready/")
            assert resp.status_code == 200
            body = resp.json()
            assert body["checks"]["blob"] == "client not initialized"
        finally:
            client.app.state.s3_client = original  # ty:ignore[unresolved-attribute]

    def test_s3_check_failure(self, client: TestClient) -> None:
        mock_client = MagicMock()
        from unittest.mock import AsyncMock  # noqa: PLC0415

        mock_client.head_bucket = AsyncMock(side_effect=RuntimeError("S3 unreachable"))
        original = client.app.state.s3_client  # ty:ignore[unresolved-attribute]
        client.app.state.s3_client = mock_client  # ty:ignore[unresolved-attribute]
        try:
            resp = client.get("/health/ready/")
            assert resp.status_code == 200
            body = resp.json()
            assert "S3 unreachable" in body["checks"]["blob"]
            assert body["status"] == "ok"
        finally:
            client.app.state.s3_client = original  # ty:ignore[unresolved-attribute]

    def test_gcs_success(self, client: TestClient) -> None:
        with patch("matyan_frontier.health.SETTINGS.blob_backend_type", "gcs"):
            mock_client = MagicMock()
            mock_client.bucket.return_value.exists.return_value = True
            client.app.state.gcs_client = mock_client  # ty:ignore[unresolved-attribute]
            try:
                resp = client.get("/health/ready/")
                assert resp.status_code == 200
                assert resp.json()["checks"]["blob"] == "ok"
            finally:
                del client.app.state.gcs_client  # ty:ignore[unresolved-attribute]

    def test_gcs_not_found(self, client: TestClient) -> None:
        with patch("matyan_frontier.health.SETTINGS.blob_backend_type", "gcs"):
            mock_client = MagicMock()
            mock_client.bucket.return_value.exists.return_value = False
            client.app.state.gcs_client = mock_client  # ty:ignore[unresolved-attribute]
            try:
                resp = client.get("/health/ready/")
                assert resp.status_code == 200
                assert resp.json()["checks"]["blob"] == "bucket not found"
            finally:
                del client.app.state.gcs_client  # ty:ignore[unresolved-attribute]

    def test_gcs_client_not_initialized(self, client: TestClient) -> None:
        with patch("matyan_frontier.health.SETTINGS.blob_backend_type", "gcs"):
            resp = client.get("/health/ready/")
            assert resp.status_code == 200
            assert resp.json()["checks"]["blob"] == "client not initialized"

    def test_gcs_check_failure(self, client: TestClient) -> None:
        with patch("matyan_frontier.health.SETTINGS.blob_backend_type", "gcs"):
            mock_client = MagicMock()
            mock_client.bucket.return_value.exists.side_effect = RuntimeError("GCS error")
            client.app.state.gcs_client = mock_client  # ty:ignore[unresolved-attribute]
            try:
                resp = client.get("/health/ready/")
                assert resp.status_code == 200
                assert "GCS error" in resp.json()["checks"]["blob"]
            finally:
                del client.app.state.gcs_client  # ty:ignore[unresolved-attribute]

    def test_azure_success(self, client: TestClient) -> None:
        with patch("matyan_frontier.health.SETTINGS.blob_backend_type", "azure"):
            mock_client = MagicMock()
            mock_client.get_container_client.return_value.exists.return_value = True
            client.app.state.azure_presign_client = mock_client  # ty:ignore[unresolved-attribute]
            try:
                resp = client.get("/health/ready/")
                assert resp.status_code == 200
                assert resp.json()["checks"]["blob"] == "ok"
            finally:
                del client.app.state.azure_presign_client  # ty:ignore[unresolved-attribute]

    def test_azure_not_found(self, client: TestClient) -> None:
        with patch("matyan_frontier.health.SETTINGS.blob_backend_type", "azure"):
            mock_client = MagicMock()
            mock_client.get_container_client.return_value.exists.return_value = False
            client.app.state.azure_presign_client = mock_client  # ty:ignore[unresolved-attribute]
            try:
                resp = client.get("/health/ready/")
                assert resp.status_code == 200
                assert resp.json()["checks"]["blob"] == "container not found"
            finally:
                del client.app.state.azure_presign_client  # ty:ignore[unresolved-attribute]

    def test_azure_client_not_initialized(self, client: TestClient) -> None:
        with patch("matyan_frontier.health.SETTINGS.blob_backend_type", "azure"):
            resp = client.get("/health/ready/")
            assert resp.status_code == 200
            assert resp.json()["checks"]["blob"] == "client not initialized"

    def test_azure_check_failure(self, client: TestClient) -> None:
        with patch("matyan_frontier.health.SETTINGS.blob_backend_type", "azure"):
            mock_client = MagicMock()
            mock_client.get_container_client.return_value.exists.side_effect = RuntimeError("Azure error")
            client.app.state.azure_presign_client = mock_client  # ty:ignore[unresolved-attribute]
            try:
                resp = client.get("/health/ready/")
                assert resp.status_code == 200
                assert "Azure error" in resp.json()["checks"]["blob"]
            finally:
                del client.app.state.azure_presign_client  # ty:ignore[unresolved-attribute]
