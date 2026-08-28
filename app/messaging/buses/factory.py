"""EventBus factory and singleton management."""

from __future__ import annotations

import logging

from app.core.config import get_settings
from app.messaging.base import EventBus
from app.messaging.buses.in_memory import InMemoryEventBus
from app.messaging.buses.kafka import KafkaEventBus
from app.messaging.buses.rabbitmq import RabbitMQEventBus

logger = logging.getLogger(__name__)

_event_bus: EventBus | None = None


def create_event_bus_from_settings() -> EventBus:
    """Create an EventBus instance based on application settings."""
    settings = get_settings()
    broker_type = getattr(settings, 'BROKER_TYPE', None)
    broker_url = getattr(settings, 'BROKER_URL', None) or getattr(
        settings, 'RABBITMQ_URL', None
    )
    kafka_servers = getattr(settings, 'KAFKA_BOOTSTRAP_SERVERS', None)

    if broker_type == 'rabbitmq' and broker_url:
        logger.info('Initializing RabbitMQEventBus with URL: %s', broker_url)
        return RabbitMQEventBus(url=broker_url)
    if broker_type == 'kafka' and kafka_servers:
        logger.info(
            'Initializing KafkaEventBus with servers: %s', kafka_servers
        )
        return KafkaEventBus(bootstrap_servers=kafka_servers)

    logger.info('Initializing default InMemoryEventBus')
    return InMemoryEventBus()


def get_event_bus() -> EventBus:
    """Get global EventBus instance."""
    global _event_bus
    if _event_bus is None:
        _event_bus = create_event_bus_from_settings()
    return _event_bus


def set_event_bus(bus: EventBus) -> None:
    """Set global EventBus instance (for testing or custom initialization)."""
    global _event_bus
    _event_bus = bus


def reset_event_bus() -> None:
    """Reset global EventBus instance to None."""
    global _event_bus
    _event_bus = None
