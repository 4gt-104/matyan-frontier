"""Tests for app.py: lifespan, middleware, router mounting."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from matyan_frontier.app import app

from .conftest import _make_mock_session

if TYPE_CHECKING:
    from .conftest import MockKafkaProducer


class TestLifespan:
    def test_producer_start_and_stop_called(
        self,
        client: TestClient,
        mock_producer: MockKafkaProducer,
    ) -> None:
        resp = client.get("/metrics/")
        assert resp.status_code == 200
        assert mock_producer.start_called

    def test_producer_flush_and_stop_on_exit(self, mock_producer: MockKafkaProducer) -> None:

        with (
            patch("matyan_frontier.app.get_producer", return_value=mock_producer),
            patch("matyan_frontier.ws.handler.get_producer", return_value=mock_producer),
            patch("matyan_frontier.app.aioboto3.Session", return_value=_make_mock_session()),
            TestClient(app),
        ):
            pass
        assert mock_producer.flush_called
        assert mock_producer.stop_called

    def test_s3_clients_set_on_app_state(self, client: TestClient) -> None:
        assert hasattr(client.app.state, "s3_client")  # ty:ignore[unresolved-attribute]
        assert hasattr(client.app.state, "s3_presign_client")  # ty:ignore[unresolved-attribute]
        assert client.app.state.s3_client is not None  # ty:ignore[unresolved-attribute]
        assert client.app.state.s3_presign_client is not None  # ty:ignore[unresolved-attribute]

    def test_shutdown_order_flush_before_stop(self, mock_producer: MockKafkaProducer) -> None:
        """Verify flush() is called before stop() during shutdown."""
        call_order: list[str] = []
        original_flush = mock_producer.flush
        original_stop = mock_producer.stop

        async def _tracking_flush(timeout: float = 5.0) -> None:  # noqa: ASYNC109
            call_order.append("flush")
            await original_flush(timeout=timeout)

        async def _tracking_stop() -> None:
            call_order.append("stop")
            await original_stop()

        mock_producer.flush = _tracking_flush  # ty:ignore[invalid-assignment]
        mock_producer.stop = _tracking_stop  # ty:ignore[invalid-assignment]

        with (
            patch("matyan_frontier.app.get_producer", return_value=mock_producer),
            patch("matyan_frontier.ws.handler.get_producer", return_value=mock_producer),
            patch("matyan_frontier.app.aioboto3.Session", return_value=_make_mock_session()),
            TestClient(app),
        ):
            pass

        assert call_order == ["flush", "stop"]


class TestMiddleware:
    def test_metrics_enabled(self, client: TestClient) -> None:
        client.get("/metrics/")
        resp = client.get("/metrics/")
        assert "matyan_http_requests_total" in resp.text

    def test_metrics_disabled(self, mock_producer: MockKafkaProducer) -> None:

        with (
            patch("matyan_frontier.app.get_producer", return_value=mock_producer),
            patch("matyan_frontier.ws.handler.get_producer", return_value=mock_producer),
            patch("matyan_frontier.app.aioboto3.Session", return_value=_make_mock_session()),
            patch("matyan_frontier.app.SETTINGS") as mock_settings,
        ):
            mock_settings.metrics_enabled = False
            mock_settings.cors_origins = ("*",)
            mock_settings.log_level = "INFO"
            mock_settings.blob_backend_type = "s3"
            mock_settings.s3_endpoint = "http://localhost:9000"
            mock_settings.s3_public_endpoint = ""
            mock_settings.s3_access_key = "key"
            mock_settings.s3_secret_key = "secret"  # noqa: S105
            mock_settings.s3_bucket = "test"

            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.get("/metrics/")
                assert resp.status_code == 200


class TestRequestId:
    def test_rest_response_includes_x_request_id(self, client: TestClient) -> None:
        resp = client.get("/metrics/")
        assert "X-Request-ID" in resp.headers
        rid = resp.headers["X-Request-ID"]
        assert len(rid) == 36  # UUID format

    def test_x_request_id_is_unique_per_request(self, client: TestClient) -> None:
        r1 = client.get("/metrics/")
        r2 = client.get("/metrics/")
        assert r1.headers["X-Request-ID"] != r2.headers["X-Request-ID"]


class TestRouterMounting:
    def test_ws_route_exists(self, client: TestClient) -> None:
        resp = client.get("/api/v1/ws/runs/test123")
        assert resp.status_code in {403, 404}

    def test_rest_route_exists(self, client: TestClient) -> None:
        resp = client.get("/api/v1/rest/artifacts/presign")
        assert resp.status_code == 405


class TestConfigValidation:
    def test_invalid_config_prevents_startup(self, mock_producer: MockKafkaProducer) -> None:

        with (
            pytest.raises(ValueError, match="kafka_bootstrap_servers"),
            patch("matyan_frontier.app.get_producer", return_value=mock_producer),
            patch("matyan_frontier.health.get_producer", return_value=mock_producer),
            patch("matyan_frontier.ws.handler.get_producer", return_value=mock_producer),
            patch("matyan_frontier.app.aioboto3.Session", return_value=_make_mock_session()),
            patch("matyan_frontier.app.SETTINGS.kafka_bootstrap_servers", ""),
            TestClient(app, raise_server_exceptions=True),
        ):
            pass
