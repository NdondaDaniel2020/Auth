"""RabbitMQ EventBus implementation using aio-pika."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from app.messaging.base import Event
from app.messaging.buses.in_memory import InMemoryEventBus

if TYPE_CHECKING:
    import aio_pika

logger = logging.getLogger(__name__)


class RabbitMQEventBus(InMemoryEventBus):
    """RabbitMQ-backed event bus with in-memory fallback and retry capabilities."""

    def __init__(
        self,
        url: str,
        exchange_name: str = 'auth_events',
        durable: bool = True,
        max_retries: int = 3,
    ) -> None:
        super().__init__(max_retries=max_retries)
        self.url = url
        self.exchange_name = exchange_name
        self.durable = durable
        self._connection: aio_pika.abc.AbstractRobustConnection | None = None
        self._channel: aio_pika.abc.AbstractChannel | None = None
        self._exchange: aio_pika.abc.AbstractExchange | None = None

    async def connect(self) -> None:
        """Connect to RabbitMQ broker."""
        import aio_pika
        from aio_pika import ExchangeType

        self._connection = await aio_pika.connect_robust(self.url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=10)
        self._exchange = await self._channel.declare_exchange(
            self.exchange_name,
            ExchangeType.TOPIC,
            durable=self.durable,
        )
        logger.info('RabbitMQEventBus connected: %s', self.url)

    async def disconnect(self) -> None:
        """Disconnect from RabbitMQ broker."""
        if self._connection:
            await self._connection.close()
            self._connection = None
            self._channel = None
            self._exchange = None
            logger.info('RabbitMQEventBus disconnected')

    async def publish(self, event: Event) -> None:
        """Publish event to RabbitMQ broker and deliver locally."""
        await super().publish(event)
        if self._exchange:
            import aio_pika

            message = aio_pika.Message(
                body=json.dumps(event.to_dict()).encode(),
                content_type='application/json',
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                message_id=event.event_id,
                timestamp=event.timestamp,
                headers={
                    'event_type': event.type,
                    'correlation_id': event.correlation_id or '',
                    'causation_id': event.causation_id or '',
                },
            )
            await self._exchange.publish(message, routing_key=event.type)
            logger.debug('Published event %s to RabbitMQ exchange', event.type)
