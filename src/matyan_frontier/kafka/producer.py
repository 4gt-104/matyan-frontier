from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from aiokafka import AIOKafkaProducer
from loguru import logger

from matyan_frontier.config import SETTINGS

from ._security import kafka_security_kwargs

if TYPE_CHECKING:
    from matyan_api_models.kafka import IngestionMessage


class KafkaProducer:
    """Thin wrapper around ``AIOKafkaProducer`` tied to the data-ingestion topic."""

    def __init__(self) -> None:
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        security_kwargs = kafka_security_kwargs()
        self._producer = AIOKafkaProducer(
            bootstrap_servers=SETTINGS.kafka_bootstrap_servers,
            value_serializer=lambda v: v.encode() if isinstance(v, str) else v,
            key_serializer=lambda k: k.encode() if isinstance(k, str) else k,
            **security_kwargs,
        )
        await self._producer.start()
        logger.info("Kafka producer started ({})", SETTINGS.kafka_bootstrap_servers)

    async def flush(self, timeout: float = 5.0) -> None:  # noqa: ASYNC109
        """Wait for all buffered messages to be delivered, with a timeout."""
        if self._producer is None:
            return
        try:
            await asyncio.wait_for(self._producer.flush(), timeout=timeout)
            logger.debug("Kafka producer flushed")
        except TimeoutError:
            logger.warning("Kafka producer flush timed out after {:.1f}s", timeout)

    async def stop(self) -> None:
        if self._producer is not None:
            await self._producer.stop()
            logger.info("Kafka producer stopped")

    async def publish(self, message: IngestionMessage) -> None:
        """Publish an ingestion message, partitioned by ``run_id``."""
        if self._producer is None:
            msg = "Kafka producer not started"
            raise RuntimeError(msg)
        await self._producer.send_and_wait(
            topic=SETTINGS.kafka_data_ingestion_topic,
            key=message.run_id,
            value=message.model_dump_json(),
        )


_producer: KafkaProducer | None = None


def get_producer() -> KafkaProducer:
    global _producer  # noqa: PLW0603
    if _producer is None:
        _producer = KafkaProducer()
    return _producer
