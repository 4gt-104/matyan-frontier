"""Tests for the /api/v1/rest/version/ endpoint."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


class TestVersion:
    def test_returns_200_and_fields(self, client: TestClient) -> None:
        """GET /api/v1/rest/version/ returns 200 with version and component."""
        resp = client.get("/api/v1/rest/version/")
        assert resp.status_code == 200
        body = resp.json()
        assert "version" in body
        assert body["component"] == "frontier"
        assert body["version"]
