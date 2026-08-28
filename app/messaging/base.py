"""Base abstractions and contracts for event-driven messaging."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

EventHandler = Callable[['Event'], Awaitable[None]]


@dataclass
class Event:
    """Base domain event with standard metadata."""

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

    def __getitem__(self, key: str) -> Any:
        if hasattr(self, key):
            return getattr(self, key)
        return self.to_dict()[key]


@dataclass
class DomainEvent(Event):
    """Event notification representing a fact that occurred in the domain."""


@dataclass
class Command(Event):
    """Command message representing an intentional action to be executed."""


class EventBus(ABC):
    """Abstract interface for event bus implementations."""

    @abstractmethod
    async def publish(self, event: Event) -> None:
        """Publish an event to all subscribed handlers."""

    @abstractmethod
    async def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Subscribe a handler to a specific event type."""

    @abstractmethod
    async def unsubscribe(
        self, event_type: str, handler: EventHandler
    ) -> None:
        """Unsubscribe a handler from a specific event type."""
