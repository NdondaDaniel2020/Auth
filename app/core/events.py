"""Event bus abstraction for domain events.

Provides a simple in-memory event bus for development/testing,
with a pluggable interface for future broker integration (RabbitMQ, Kafka).
"""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

EventHandler = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass
class Event:
    """Domain event with metadata."""
    type: str
    payload: dict[str, Any]
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    correlation_id: str | None = None
    causation_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "type": self.type,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
        }


class EventBus(ABC):
    """Abstract event bus interface."""

    @abstractmethod
    async def publish(self, event: Event) -> None:
        """Publish an event to all subscribers."""

    @abstractmethod
    async def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Subscribe a handler to an event type."""

    @abstractmethod
    async def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """Unsubscribe a handler from an event type."""


class InMemoryEventBus(EventBus):
    """In-memory event bus for development and testing."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    async def publish(self, event: Event) -> None:
        handlers = self._handlers.get(event.type, [])
        if not handlers:
            logger.debug("No handlers for event type: %s", event.type)
            return

        for handler in handlers:
            try:
                await handler(event.to_dict())
            except Exception as e:  # noqa: BLE001
                logger.error("Handler failed for event %s: %s", event.type, e)

    async def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)
        logger.debug("Subscribed handler to %s", event_type)

    async def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        if handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)
            logger.debug("Unsubscribed handler from %s", event_type)


class BrokerEventBus(EventBus):
    """Broker-backed event bus (RabbitMQ/Kafka) - to be implemented."""

    def __init__(self, broker_url: str) -> None:
        self.broker_url = broker_url
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        logger.warning("BrokerEventBus not yet implemented; using in-memory fallback")

    async def publish(self, event: Event) -> None:
        # TODO: publish to broker (RabbitMQ exchange / Kafka topic)
        for handler in self._handlers.get(event.type, []):
            try:
                await handler(event.to_dict())
            except Exception as e:  # noqa: BLE001
                logger.error("Handler failed for event %s: %s", event.type, e)

    async def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)

    async def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        if handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)


_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """Get the global event bus instance."""
    global _event_bus
    if _event_bus is None:
        _event_bus = InMemoryEventBus()
    return _event_bus


def set_event_bus(bus: EventBus) -> None:
    """Set the global event bus (for testing or broker integration)."""
    global _event_bus
    _event_bus = bus


@asynccontextmanager
async def event_bus_lifespan(broker_url: str | None = None):
    """Lifecycle for event bus with optional broker."""
    global _event_bus
    if broker_url:
        _event_bus = BrokerEventBus(broker_url)
    else:
        _event_bus = InMemoryEventBus()
    try:
        yield
    finally:
        _event_bus = None


# --- Domain event types (constants) ---

class UserEvents:
    CREATED = "user.created"
    UPDATED = "user.updated"
    DELETED = "user.deleted"
    ACTIVATED = "user.activated"
    DEACTIVATED = "user.deactivated"
    ROLES_CHANGED = "user.roles_changed"
    PASSWORD_CHANGED = "user.password_changed"
    EMAIL_VERIFIED = "user.email_verified"


class AuthEvents:
    LOGIN = "auth.login"
    LOGOUT = "auth.logout"
    LOGIN_FAILED = "auth.login_failed"
    TOKEN_REFRESHED = "auth.token_refreshed"
    PASSWORD_RESET_REQUESTED = "auth.password_reset_requested"
    PASSWORD_RESET_COMPLETED = "auth.password_reset_completed"


class NotificationEvents:
    EMAIL_SEND = "notification.email.send"
    PUSH_SEND = "notification.push.send"
    IN_APP_CREATE = "notification.in_app.create"