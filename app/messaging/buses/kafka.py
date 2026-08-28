"""Kafka EventBus implementation using aiokafka."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from app.messaging.base import Event, EventBus, EventHandler
from app.messaging.buses.in_memory import InMemoryEventBus

if TYPE_CHECKING:
    from aiokafka import AIOKafkaProducer

logger = logging.getLogger(__name__)


class KafkaEventBus(InMemoryEventBus):
    """Kafka-backed event bus with in-memory fallback and retry capabilities."""

    def __init__(
        self,
        bootstrap_servers: str,
        topic_prefix: str = 'auth_events',
        max_retries: int = 3,
    ) -> None:
        super().__init__(max_retries=max_retries)
        self.bootstrap_servers = bootstrap_servers
        self.topic_prefix = topic_prefix
        self._producer: AIOKafkaProducer | None = None

    async def connect(self) -> None:
        """Connect to Kafka broker."""
        from aiokafka import AIOKafkaProducer

        self._producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode(),
            key_serializer=lambda k: k.encode() if k else None,
            enable_idempotence=True,
            acks='all',
        )
        await self._producer.start()
        logger.info('KafkaEventBus connected: %s', self.bootstrap_servers)

    async def disconnect(self) -> None:
        """Disconnect from Kafka broker."""
        if self._producer:
            await self._producer.stop()
            self._producer = None
            logger.info('KafkaEventBus disconnected')

    async def publish(self, event: Event) -> None:
        """Publish event to Kafka topic and deliver locally."""
        await super().publish(event)
        if self._producer:
            topic = f'{self.topic_prefix}.{event.type}'
            await self._producer.send_and_wait(
                topic,
                value=event.to_dict(),
                key=event.event_id,
                timestamp=int(event.timestamp.timestamp() * 1000),
            )
            logger.debug(
                'Published event %s to Kafka topic %s', event.type, topic
            )
