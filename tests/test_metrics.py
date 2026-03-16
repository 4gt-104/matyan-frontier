"""Tests for the /metrics/ Prometheus endpoint on the frontier service."""

from __future__ import annotations

from fastapi.testclient import TestClient

from matyan_frontier.app import app
from matyan_frontier.metrics import normalize_path


def _client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


class TestFrontierMetrics:
    def test_returns_200_with_prometheus_content_type(self) -> None:
        resp = _client().get("/metrics/")
        assert resp.status_code == 200
        assert "text/plain" in resp.headers["content-type"]

    def test_contains_ws_metrics_definitions(self) -> None:
        resp = _client().get("/metrics/")
        body = resp.text
        assert "matyan_ws_connections_active" in body

    def test_http_metrics_after_request(self) -> None:
        client = _client()
        client.get("/metrics/")
        resp = client.get("/metrics/")
        body = resp.text
        assert "matyan_http_requests_total" in body
        assert "matyan_http_request_duration_seconds" in body


class TestFrontierPathNormalization:
    def test_run_id_replaced(self) -> None:
        result = normalize_path("/api/v1/ws/runs/0cf28fd9b5bf2002")
        assert result == "/api/v1/ws/runs/{id}"

    def test_uuid_replaced(self) -> None:
        result = normalize_path("/api/v1/ws/runs/550e8400-e29b-41d4-a716-446655440000")
        assert result == "/api/v1/ws/runs/{id}"

    def test_no_id_unchanged(self) -> None:
        result = normalize_path("/metrics/")
        assert result == "/metrics/"

    def test_empty_path(self) -> None:
        result = normalize_path("")
        assert result == ""

    def test_short_hex_not_replaced(self) -> None:
        result = normalize_path("/api/v1/ws/runs/abc")
        assert result == "/api/v1/ws/runs/abc"
