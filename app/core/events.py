"""Event bus abstraction for domain events.

Provides an in-memory event bus for development/testing and broker integration,
supporting automatic retry policies with exponential backoff and a Redis-backed
Dead-Letter Queue (DLQ) for failed events.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.core.redis import get_redis_client

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
            'event_id': self.event_id,
            'type': self.type,
            'payload': self.payload,
            'timestamp': self.timestamp.isoformat(),
            'correlation_id': self.correlation_id,
            'causation_id': self.causation_id,
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
    async def unsubscribe(
        self, event_type: str, handler: EventHandler
    ) -> None:
        """Unsubscribe a handler from an event type."""


class InMemoryEventBus(EventBus):
    """In-memory event bus with retry policy and Dead-Letter Queue (DLQ)."""

    def __init__(
        self,
        max_retries: int = 3,
        initial_delay: float = 0.1,
        backoff_factor: float = 2.0,
        max_delay: float = 10.0,
    ) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.backoff_factor = backoff_factor
        self.max_delay = max_delay
        self._dlq_in_memory: list[dict[str, Any]] = []

    async def publish(self, event: Event) -> None:
        handlers = self._handlers.get(event.type, [])
        if not handlers:
            logger.debug('No handlers for event type: %s', event.type)
            return

        for handler in handlers:
            for attempt in range(1, self.max_retries + 1):
                try:
                    await handler(event.to_dict())
                    break
                except Exception as e:  # noqa: BLE001
                    if attempt < self.max_retries:
                        delay = min(
                            self.initial_delay
                            * (self.backoff_factor ** (attempt - 1)),
                            self.max_delay,
                        )
                        logger.warning(
                            'Handler %s failed for event %s (attempt %d/%d). Retrying in %.2fs: %s',
                            handler,
                            event.type,
                            attempt,
                            self.max_retries,
                            delay,
                            e,
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            'Handler %s failed permanently for event %s after %d attempts: %s',
                            handler,
                            event.type,
                            self.max_retries,
                            e,
                        )
                        await self.push_to_dlq(
                            event=event,
                            handler_name=getattr(
                                handler, '__name__', str(handler)
                            ),
                            error=str(e),
                        )

    async def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)
        logger.debug('Subscribed handler to %s', event_type)

    async def unsubscribe(
        self, event_type: str, handler: EventHandler
    ) -> None:
        if handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)
            logger.debug('Unsubscribed handler from %s', event_type)

    async def push_to_dlq(
        self, event: Event, handler_name: str, error: str
    ) -> None:
        """Push a failed event record to Redis DLQ (and in-memory fallback)."""
        record = {
            'event': event.to_dict(),
            'handler': handler_name,
            'error': error,
            'failed_at': datetime.now(UTC).isoformat(),
        }
        self._dlq_in_memory.append(record)
        client = get_redis_client()
        if client:
            try:
                await client.rpush('events:dlq', json.dumps(record))
            except Exception as e:  # noqa: BLE001
                logger.warning('Failed to push DLQ record to Redis: %s', e)

    async def get_dlq_events(self) -> list[dict[str, Any]]:
        """Retrieve all events stored in the Dead-Letter Queue."""
        client = get_redis_client()
        if client:
            try:
                items = await client.lrange('events:dlq', 0, -1)
                if items:
                    return [json.loads(item) for item in items]
            except Exception as e:  # noqa: BLE001
                logger.warning('Failed to read DLQ from Redis: %s', e)
        return list(self._dlq_in_memory)

    async def clear_dlq(self) -> None:
        """Clear all events in the Dead-Letter Queue."""
        self._dlq_in_memory.clear()
        client = get_redis_client()
        if client:
            try:
                await client.delete('events:dlq')
            except Exception as e:  # noqa: BLE001
                logger.warning('Failed to clear Redis DLQ: %s', e)

    async def reprocess_dlq_events(self) -> int:
        """Reprocess all events currently stored in the DLQ."""
        events_to_process = await self.get_dlq_events()
        if not events_to_process:
            return 0
        await self.clear_dlq()
        reprocessed = 0
        for record in events_to_process:
            event_data = record['event']
            event = Event(
                event_id=event_data['event_id'],
                type=event_data['type'],
                payload=event_data['payload'],
                correlation_id=event_data.get('correlation_id'),
                causation_id=event_data.get('causation_id'),
            )
            await self.publish(event)
            reprocessed += 1
        return reprocessed


class BrokerEventBus(InMemoryEventBus):
    """Broker-backed event bus (RabbitMQ/Kafka) with in-memory retry fallback."""

    def __init__(
        self,
        broker_url: str,
        max_retries: int = 3,
        initial_delay: float = 0.1,
        backoff_factor: float = 2.0,
        max_delay: float = 10.0,
    ) -> None:
        super().__init__(
            max_retries=max_retries,
            initial_delay=initial_delay,
            backoff_factor=backoff_factor,
            max_delay=max_delay,
        )
        self.broker_url = broker_url
        logger.warning(
            'BrokerEventBus using in-memory retry/DLQ fallback for: %s',
            broker_url,
        )


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
    CREATED = 'user.created'
    UPDATED = 'user.updated'
    DELETED = 'user.deleted'
    ACTIVATED = 'user.activated'
    DEACTIVATED = 'user.deactivated'
    ROLES_CHANGED = 'user.roles_changed'
    PASSWORD_CHANGED = 'user.password_changed'
    EMAIL_VERIFIED = 'user.email_verified'


class AuthEvents:
    LOGIN = 'auth.login'
    LOGOUT = 'auth.logout'
    LOGIN_FAILED = 'auth.login_failed'
    TOKEN_REFRESHED = 'auth.token_refreshed'
    PASSWORD_RESET_REQUESTED = 'auth.password_reset_requested'
    PASSWORD_RESET_COMPLETED = 'auth.password_reset_completed'
    ACCOUNT_TEMPORARILY_LOCKED = 'auth.account_temporarily_locked'


class NotificationEvents:
    EMAIL_SEND = 'notification.email.send'
    PUSH_SEND = 'notification.push.send'
    IN_APP_CREATE = 'notification.in_app.create'
