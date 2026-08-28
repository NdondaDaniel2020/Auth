"""WebSocket event consumer - subscribes to domain events and forwards frames."""

from __future__ import annotations

import logging

from app.messaging.base import Event
from app.messaging.buses import get_event_bus
from app.messaging.events.user_events import UserEvents
from app.services.websocket_service import get_ws_manager

logger = logging.getLogger(__name__)


class WebSocketConsumer:
    """Consumes domain events and forwards real-time messages to WebSocket clients."""

    def __init__(self) -> None:
        self._subscribed = False

    async def subscribe(self) -> None:
        """Subscribe to relevant domain events."""
        if self._subscribed:
            return

        bus = get_event_bus()

        await bus.subscribe(UserEvents.UPDATED, self._handle_user_updated)
        await bus.subscribe(
            UserEvents.DEACTIVATED, self._handle_user_deactivated
        )
        await bus.subscribe(
            UserEvents.ROLES_CHANGED, self._handle_user_roles_changed
        )
        await bus.subscribe(
            UserEvents.PASSWORD_CHANGED, self._handle_password_changed
        )

        self._subscribed = True
        logger.info('WebSocketConsumer subscribed to domain events')

    async def unsubscribe(self) -> None:
        """Unsubscribe from events."""
        if not self._subscribed:
            return

        bus = get_event_bus()

        await bus.unsubscribe(UserEvents.UPDATED, self._handle_user_updated)
        await bus.unsubscribe(
            UserEvents.DEACTIVATED, self._handle_user_deactivated
        )
        await bus.unsubscribe(
            UserEvents.ROLES_CHANGED, self._handle_user_roles_changed
        )
        await bus.unsubscribe(
            UserEvents.PASSWORD_CHANGED, self._handle_password_changed
        )

        self._subscribed = False
        logger.info('WebSocketConsumer unsubscribed from domain events')

    async def _handle_user_updated(self, event: Event) -> None:
        payload = event.payload
        user_id = payload['user_id']
        manager = get_ws_manager()
        await manager.publish_message(
            user_id,
            {
                'type': 'user.updated',
                'data': payload,
            },
        )

    async def _handle_user_deactivated(self, event: Event) -> None:
        payload = event.payload
        user_id = payload['user_id']
        manager = get_ws_manager()
        await manager.publish_message(
            user_id,
            {
                'type': 'user.deactivated',
                'data': {'reason': 'Account deactivated by administrator'},
            },
            force_disconnect=True,
        )

    async def _handle_user_roles_changed(self, event: Event) -> None:
        payload = event.payload
        user_id = payload['user_id']
        manager = get_ws_manager()
        force_disc = 'admin' in payload.get(
            'old_roles', []
        ) and 'admin' not in payload.get('new_roles', [])
        await manager.publish_message(
            user_id,
            {
                'type': 'user.roles_changed',
                'data': payload,
            },
            force_disconnect=force_disc,
        )

    async def _handle_password_changed(self, event: Event) -> None:
        payload = event.payload
        user_id = payload['user_id']
        manager = get_ws_manager()
        await manager.publish_message(
            user_id,
            {
                'type': 'user.password_changed',
                'data': {
                    'message': 'Your password was changed. Please log in again.'
                },
            },
            force_disconnect=True,
        )


_ws_consumer: WebSocketConsumer | None = None


def get_ws_consumer() -> WebSocketConsumer:
    """Get global WebSocketConsumer instance."""
    global _ws_consumer
    if _ws_consumer is None:
        _ws_consumer = WebSocketConsumer()
    return _ws_consumer
