"""Tests for kafka/producer.py: KafkaProducer and get_producer."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from matyan_api_models.kafka import IngestionMessage

from matyan_frontier.kafka import producer as producer_mod
from matyan_frontier.kafka.producer import KafkaProducer, get_producer


class TestKafkaProducer:
    def test_init(self) -> None:
        p = KafkaProducer()
        assert p._producer is None  # noqa: SLF001

    def test_publish_before_start_raises(self) -> None:
        p = KafkaProducer()
        msg = IngestionMessage(
            type="create_run",
            run_id="r1",
            timestamp=datetime.now(UTC),
            payload={},
        )
        with pytest.raises(RuntimeError, match="not started"):
            asyncio.run(p.publish(msg))

    @patch("matyan_frontier.kafka.producer.AIOKafkaProducer")
    def test_start_stop_publish(self, mock_aio_cls: MagicMock) -> None:
        mock_instance = AsyncMock()
        mock_aio_cls.return_value = mock_instance

        p = KafkaProducer()

        asyncio.run(p.start())
        assert p._producer is not None  # noqa: SLF001
        mock_instance.start.assert_awaited_once()

        msg = IngestionMessage(
            type="log_metric",
            run_id="r2",
            timestamp=datetime.now(UTC),
            payload={"name": "loss", "value": 0.5},
        )
        asyncio.run(p.publish(msg))
        mock_instance.send_and_wait.assert_awaited_once()

        asyncio.run(p.stop())
        mock_instance.stop.assert_awaited_once()

    def test_stop_when_not_started(self) -> None:
        p = KafkaProducer()
        asyncio.run(p.stop())

    @patch("matyan_frontier.kafka.producer.AIOKafkaProducer")
    def test_flush_delegates_to_inner_producer(self, mock_aio_cls: MagicMock) -> None:
        mock_instance = AsyncMock()
        mock_aio_cls.return_value = mock_instance

        p = KafkaProducer()
        asyncio.run(p.start())
        asyncio.run(p.flush(timeout=2.0))

        mock_instance.flush.assert_awaited_once()

    def test_flush_when_not_started_is_noop(self) -> None:
        p = KafkaProducer()
        asyncio.run(p.flush())

    @patch("matyan_frontier.kafka.producer.AIOKafkaProducer")
    def test_flush_timeout(self, mock_aio_cls: MagicMock) -> None:
        mock_instance = AsyncMock()

        async def _slow_flush() -> None:
            await asyncio.sleep(10)

        mock_instance.flush.side_effect = _slow_flush
        mock_aio_cls.return_value = mock_instance

        p = KafkaProducer()
        asyncio.run(p.start())
        asyncio.run(p.flush(timeout=0.1))


class TestGetProducer:
    def test_returns_same_instance(self) -> None:
        producer_mod._producer = None  # noqa: SLF001
        try:
            p1 = get_producer()
            p2 = get_producer()
            assert p1 is p2
        finally:
            producer_mod._producer = None  # noqa: SLF001
