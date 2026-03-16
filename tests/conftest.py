"""Shared fixtures for frontier tests.

Provides a mock Kafka producer so no real Kafka is needed, mock S3 clients
via aioboto3 patching, and a TestClient that properly runs the app lifespan.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from matyan_frontier.kafka.producer import KafkaProducer

if TYPE_CHECKING:
    from collections.abc import Generator


class MockKafkaProducer(KafkaProducer):
    """In-memory Kafka producer stub that records published messages."""

    def __init__(self) -> None:
        super().__init__()
        self.published: list = []
        self.start_called = False
        self.stop_called = False
        self.flush_called = False
        self.flush_timeout: float | None = None

    async def start(self) -> None:
        self.start_called = True
        self._producer = MagicMock()

    async def flush(self, timeout: float = 5.0) -> None:  # noqa: ASYNC109
        self.flush_called = True
        self.flush_timeout = timeout

    async def stop(self) -> None:
        self.stop_called = True

    async def publish(self, message: object) -> None:
        self.published.append(message)


def _make_mock_s3_client() -> MagicMock:
    """Build a MagicMock that behaves like an aioboto3 S3 client."""
    client = MagicMock()
    client.head_bucket = AsyncMock(return_value={})
    client.create_bucket = AsyncMock(return_value={})
    client.generate_presigned_url = AsyncMock(return_value="https://mock-s3/presigned")
    return client


def _make_mock_session() -> MagicMock:
    """Build a MagicMock that behaves like aioboto3.Session().

    Each call to ``session.client(...)`` returns an async context manager
    that yields a fresh mock S3 client.
    """
    session = MagicMock()

    @asynccontextmanager
    async def _mock_client(**_kwargs: object) -> object:
        yield _make_mock_s3_client()

    session.client = _mock_client
    return session


@pytest.fixture
def mock_producer() -> MockKafkaProducer:
    return MockKafkaProducer()


@pytest.fixture
def client(mock_producer: MockKafkaProducer) -> Generator[TestClient, None, None]:
    """TestClient with the real app, but Kafka and S3 patched to no-op mocks."""
    with (
        patch("matyan_frontier.app.get_producer", return_value=mock_producer),
        patch("matyan_frontier.health.get_producer", return_value=mock_producer),
        patch("matyan_frontier.ws.handler.get_producer", return_value=mock_producer),
        patch("matyan_frontier.app.aioboto3.Session", return_value=_make_mock_session()),
        TestClient(
            __import__("matyan_frontier.app", fromlist=["app"]).app,
            raise_server_exceptions=False,
        ) as c,
    ):
        yield c


@pytest.fixture
def async_mock_producer() -> AsyncMock:
    """An AsyncMock-based producer for more fine-grained control (e.g. side_effect)."""  # noqa: D401
    mock = AsyncMock(spec=KafkaProducer)
    mock.published = []

    async def _publish(message: object) -> None:
        mock.published.append(message)

    mock.publish.side_effect = _publish
    return mock
