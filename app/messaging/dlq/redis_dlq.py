"""Dead-Letter Queue (DLQ) manager backed by Redis and in-memory fallback."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from app.core.infrastructure.redis import get_redis_client
from app.messaging.base import Event

logger = logging.getLogger(__name__)

REDIS_DLQ_KEY = 'events:dlq'


class RedisDLQManager:
    """Manages Dead-Letter Queue storage, inspection, and clearing."""

    def __init__(self) -> None:
        self._dlq_in_memory: list[dict[str, Any]] = []

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
                await client.rpush(REDIS_DLQ_KEY, json.dumps(record))
            except Exception as e:  # noqa: BLE001
                logger.warning('Failed to push DLQ record to Redis: %s', e)

    async def get_dlq_events(self) -> list[dict[str, Any]]:
        """Retrieve all events stored in the Dead-Letter Queue."""
        client = get_redis_client()
        if client:
            try:
                items = await client.lrange(REDIS_DLQ_KEY, 0, -1)
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
                await client.delete(REDIS_DLQ_KEY)
            except Exception as e:  # noqa: BLE001
                logger.warning('Failed to clear Redis DLQ: %s', e)


_dlq_manager: RedisDLQManager | None = None


def get_dlq_manager() -> RedisDLQManager:
    """Get global DLQ manager instance."""
    global _dlq_manager
    if _dlq_manager is None:
        _dlq_manager = RedisDLQManager()
    return _dlq_manager
