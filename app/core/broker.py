"""Message broker integration (RabbitMQ / Kafka).

Provides abstract interface and concrete implementations for
publishing domain events to a message broker.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import aio_pika
    from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from app.core.events import Event

logger = logging.getLogger(__name__)


class BrokerType(str, Enum):
    """Supported message broker types."""
    RABBITMQ = "rabbitmq"
    KAFKA = "kafka"


@dataclass
class BrokerConfig:
    """Configuration for message broker connection."""
    type: BrokerType
    url: str
    exchange: str = "auth_events"  # RabbitMQ exchange / Kafka topic prefix
    durable: bool = True
    # RabbitMQ specific
    exchange_type: str = "topic"
    # Kafka specific
    bootstrap_servers: str | None = None
    consumer_group: str | None = None
    # SSL/TLS
    ssl: bool = False
    ssl_ca_file: str | None = None
    ssl_cert_file: str | None = None
    ssl_key_file: str | None = None


class BrokerPublisher(ABC):
    """Abstract interface for publishing events to a broker."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to broker."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to broker."""

    @abstractmethod
    async def publish(self, event: Event) -> None:
        """Publish a single event."""

    @abstractmethod
    async def publish_batch(self, events: list[Event]) -> None:
        """Publish multiple events efficiently."""


class RabbitMQPublisher(BrokerPublisher):
    """RabbitMQ publisher using aio-pika."""

    def __init__(self, config: BrokerConfig) -> None:
        self.config = config
        self._connection: aio_pika.abc.AbstractRobustConnection | None = None
        self._channel: aio_pika.abc.AbstractChannel | None = None
        self._exchange: aio_pika.abc.AbstractExchange | None = None

    async def connect(self) -> None:
        import aio_pika
        from aio_pika import ExchangeType

        self._connection = await aio_pika.connect_robust(
            self.config.url,
            ssl=self.config.ssl,
        )
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=10)

        self._exchange = await self._channel.declare_exchange(
            self.config.exchange,
            ExchangeType(self.config.exchange_type),
            durable=self.config.durable,
        )
        logger.info("RabbitMQ connected: %s", self.config.url)

    async def disconnect(self) -> None:
        if self._connection:
            await self._connection.close()
            self._connection = None
            self._channel = None
            self._exchange = None
            logger.info("RabbitMQ disconnected")

    async def publish(self, event: Event) -> None:
        if not self._exchange:
            raise RuntimeError("RabbitMQ not connected")

        import aio_pika

        message = aio_pika.Message(
            body=json.dumps(event.to_dict()).encode(),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            message_id=event.event_id,
            timestamp=event.timestamp,
            headers={
                "event_type": event.type,
                "correlation_id": event.correlation_id or "",
                "causation_id": event.causation_id or "",
            },
        )

        # Route by event type (e.g., "user.created", "auth.login")
        await self._exchange.publish(message, routing_key=event.type)
        logger.debug("Published event %s to RabbitMQ", event.type)

    async def publish_batch(self, events: list[Event]) -> None:
        for event in events:
            await self.publish(event)


class KafkaPublisher(BrokerPublisher):
    """Kafka publisher using aiokafka."""

    def __init__(self, config: BrokerConfig) -> None:
        self.config = config
        self._producer: AIOKafkaProducer | None = None

    async def connect(self) -> None:
        from aiokafka import AIOKafkaProducer

        self._producer = AIOKafkaProducer(
            bootstrap_servers=self.config.bootstrap_servers or self.config.url,
            value_serializer=lambda v: json.dumps(v).encode(),
            key_serializer=lambda k: k.encode() if k else None,
            enable_idempotence=True,
            acks="all",
        )
        await self._producer.start()
        logger.info("Kafka connected: %s", self.config.bootstrap_servers or self.config.url)

    async def disconnect(self) -> None:
        if self._producer:
            await self._producer.stop()
            self._producer = None
            logger.info("Kafka disconnected")

    async def publish(self, event: Event) -> None:
        if not self._producer:
            raise RuntimeError("Kafka not connected")

        topic = f"{self.config.exchange}.{event.type}"
        await self._producer.send_and_wait(
            topic,
            value=event.to_dict(),
            key=event.event_id.encode(),
            headers=[
                ("event_type", event.type.encode()),
                ("event_id", event.event_id.encode()),
                ("correlation_id", (event.correlation_id or "").encode()),
                ("causation_id", (event.causation_id or "").encode()),
            ],
            timestamp=int(event.timestamp.timestamp() * 1000),
        )
        logger.debug("Published event %s to Kafka topic %s", event.type, topic)

    async def publish_batch(self, events: list[Event]) -> None:
        if not self._producer:
            raise RuntimeError("Kafka not connected")

        # Batch send for efficiency
        tasks = []
        for event in events:
            topic = f"{self.config.exchange}.{event.type}"
            tasks.append(self._producer.send(
                topic,
                value=event.to_dict(),
                key=event.event_id.encode(),
                headers=[
                    ("event_type", event.type.encode()),
                    ("event_id", event.event_id.encode()),
                    ("correlation_id", (event.correlation_id or "").encode()),
                    ("causation_id", (event.causation_id or "").encode()),
                ],
                timestamp=int(event.timestamp.timestamp() * 1000),
            ))
        await asyncio.gather(*tasks)
        await self._producer.flush()
        logger.debug("Published batch of %d events to Kafka", len(events))


import asyncio


class BrokerConsumer(ABC):
    """Abstract interface for consuming events from a broker."""

    @abstractmethod
    async def start(self, handler) -> None:
        """Start consuming messages."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop consuming messages."""


class RabbitMQConsumer(BrokerConsumer):
    """RabbitMQ consumer using aio-pika."""

    def __init__(self, config: BrokerConfig, queue_name: str, routing_keys: list[str]) -> None:
        self.config = config
        self.queue_name = queue_name
        self.routing_keys = routing_keys
        self._connection: aio_pika.abc.AbstractRobustConnection | None = None
        self._channel: aio_pika.abc.AbstractChannel | None = None
        self._queue: aio_pika.abc.AbstractQueue | None = None

    async def start(self, handler: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        import aio_pika
        from aio_pika import ExchangeType

        self._connection = await aio_pika.connect_robust(self.config.url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=10)

        exchange = await self._channel.declare_exchange(
            self.config.exchange,
            ExchangeType(self.config.exchange_type),
            durable=self.config.durable,
        )

        self._queue = await self._channel.declare_queue(
            self.queue_name,
            durable=self.config.durable,
        )

        for routing_key in self.routing_keys:
            await self._queue.bind(exchange, routing_key=routing_key)

        async with self._queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    event_data = json.loads(message.body.decode())
                    await handler(event_data)

    async def stop(self) -> None:
        if self._connection:
            await self._connection.close()


class KafkaConsumer(BrokerConsumer):
    """Kafka consumer using aiokafka."""

    def __init__(self, config: BrokerConfig, topics: list[str], group_id: str) -> None:
        self.config = config
        self.topics = topics
        self.group_id = group_id
        self._consumer: AIOKafkaConsumer | None = None

    async def start(self, handler: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        from aiokafka import AIOKafkaConsumer

        self._consumer = AIOKafkaConsumer(
            *self.topics,
            bootstrap_servers=self.config.bootstrap_servers or self.config.url,
            group_id=self.group_id,
            value_deserializer=lambda v: json.loads(v.decode()),
            key_deserializer=lambda k: k.decode() if k else None,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
        )
        await self._consumer.start()

        async for msg in self._consumer:
            event_data = msg.value
            await handler(event_data)

    async def stop(self) -> None:
        if self._consumer:
            await self._consumer.stop()


def create_publisher(config: BrokerConfig) -> BrokerPublisher:
    """Factory function to create publisher based on broker type."""
    if config.type == BrokerType.RABBITMQ:
        return RabbitMQPublisher(config)
    elif config.type == BrokerType.KAFKA:
        return KafkaPublisher(config)
    else:
        raise ValueError(f"Unsupported broker type: {config.type}")


def create_consumer(
    config: BrokerConfig,
    queue_name: str | None = None,
    routing_keys: list[str] | None = None,
    topics: list[str] | None = None,
    group_id: str | None = None,
) -> BrokerConsumer:
    """Factory function to create consumer based on broker type."""
    if config.type == BrokerType.RABBITMQ:
        if not queue_name or not routing_keys:
            raise ValueError("RabbitMQ consumer requires queue_name and routing_keys")
        return RabbitMQConsumer(config, queue_name, routing_keys)
    elif config.type == BrokerType.KAFKA:
        if not topics or not group_id:
            raise ValueError("Kafka consumer requires topics and group_id")
        return KafkaConsumer(config, topics, group_id)
    else:
        raise ValueError(f"Unsupported broker type: {config.type}")


@asynccontextmanager
async def broker_lifespan(config: BrokerConfig | None = None):
    """Context manager for broker publisher lifecycle."""
    publisher = None
    if config:
        publisher = create_publisher(config)
        await publisher.connect()
    try:
        yield publisher
    finally:
        if publisher:
            await publisher.disconnect()


def get_broker_config_from_settings() -> BrokerConfig | None:
    """Create BrokerConfig from application settings."""
    from app.core.config import get_settings

    settings = get_settings()

    broker_url = getattr(settings, "MESSAGE_BROKER_URL", "")
    if not broker_url:
        return None

    broker_type_str = getattr(settings, "MESSAGE_BROKER_TYPE", "rabbitmq")
    try:
        broker_type = BrokerType(broker_type_str)
    except ValueError:
        logger.warning("Unknown broker type: %s, defaulting to rabbitmq", broker_type_str)
        broker_type = BrokerType.RABBITMQ

    return BrokerConfig(
        type=broker_type,
        url=broker_url,
        exchange=getattr(settings, "MESSAGE_BROKER_EXCHANGE", "auth_events"),
        durable=True,
        exchange_type=getattr(settings, "MESSAGE_BROKER_EXCHANGE_TYPE", "topic"),
        bootstrap_servers=getattr(settings, "MESSAGE_BROKER_BOOTSTRAP_SERVERS", None),
        consumer_group=getattr(settings, "MESSAGE_BROKER_CONSUMER_GROUP", "auth-api"),
        ssl=getattr(settings, "MESSAGE_BROKER_SSL", False),
        ssl_ca_file=getattr(settings, "MESSAGE_BROKER_SSL_CA_FILE", None),
        ssl_cert_file=getattr(settings, "MESSAGE_BROKER_SSL_CERT_FILE", None),
        ssl_key_file=getattr(settings, "MESSAGE_BROKER_SSL_KEY_FILE", None),
    )