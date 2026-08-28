"""In-memory event bus implementation with retry policy and DLQ fallback."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any

from app.messaging.base import Event, EventBus, EventHandler
from app.messaging.dlq.redis_dlq import get_dlq_manager

logger = logging.getLogger(__name__)


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

    async def publish(self, event: Event) -> None:
        handlers = self._handlers.get(event.type, [])
        if not handlers:
            logger.debug('No handlers for event type: %s', event.type)
            return

        dlq_manager = get_dlq_manager()
        for handler in handlers:
            for attempt in range(1, self.max_retries + 1):
                try:
                    await handler(event)
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
                        await dlq_manager.push_to_dlq(
                            event=event,
                            handler_name=getattr(
                                handler, '__name__', str(handler)
                            ),
                            error=str(e),
                        )

    async def subscribe(self, event_type: str, handler: EventHandler) -> None:
        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)
            logger.debug('Subscribed handler to %s', event_type)

    async def unsubscribe(
        self, event_type: str, handler: EventHandler
    ) -> None:
        if handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)
            logger.debug('Unsubscribed handler from %s', event_type)

    async def get_dlq_events(self) -> list[dict[str, Any]]:
        """Retrieve stored DLQ events from DLQ manager."""
        dlq_manager = get_dlq_manager()
        return await dlq_manager.get_dlq_events()

    async def clear_dlq(self) -> None:
        """Clear all stored DLQ events."""
        dlq_manager = get_dlq_manager()
        await dlq_manager.clear_dlq()

    async def reprocess_dlq_events(self) -> int:
        """Reprocess all events currently stored in the DLQ."""
        dlq_manager = get_dlq_manager()
        events_to_process = await dlq_manager.get_dlq_events()
        if not events_to_process:
            return 0
        await dlq_manager.clear_dlq()
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
