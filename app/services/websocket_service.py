"""WebSocket connection management, Redis Pub/Sub, and event bus integrations."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

from app.messaging.buses import get_event_bus
from app.messaging.events import UserEvents
from app.core.infrastructure.redis import get_redis_client
from app.db.session import get_session_factory
from app.repositories.user_repository import UserRepository
from app.services.auth_service import consume_ws_ticket

logger = logging.getLogger(__name__)

REDIS_WS_CHANNEL = 'ws:events'
_redis_pubsub_task: asyncio.Task | None = None


class WebSocketManager:
    """Manages WebSocket connections with authentication and optional Redis Pub/Sub."""

    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}  # user_id -> WebSocket
        self._user_data: dict[
            str, dict[str, Any]
        ] = {}  # user_id -> {socket, metadata}

    async def connect(
        self,
        websocket: WebSocket,
        ticket: str,
    ) -> str | None:
        """Authenticate and register a WebSocket connection using a single-use ticket.

        Returns user_id on success, None on failure.
        """
        user_id = await consume_ws_ticket(ticket)
        if not user_id:
            logger.warning(
                'WebSocket auth failed: invalid, expired or reused ticket'
            )
            return None

        # Verify user exists and is active
        session_factory = get_session_factory()
        async with session_factory() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_by_id(user_id)
            if user is None or not user.is_active:
                logger.warning(
                    'WebSocket auth failed: user not found or inactive: %s',
                    user_id,
                )
                return None

        # Accept connection
        await websocket.accept()

        # Store connection
        self._connections[user_id] = websocket
        self._user_data[user_id] = {
            'socket': websocket,
        }

        logger.info('WebSocket connected: user_id=%s', user_id)
        return user_id

    def disconnect(self, user_id: str) -> None:
        """Disconnect and cleanup a WebSocket connection (natural, forced or ping/pong timeout)."""
        if user_id in self._connections:
            del self._connections[user_id]
        if user_id in self._user_data:
            del self._user_data[user_id]
        logger.info(
            'WebSocket disconnected and cleaned up: user_id=%s', user_id
        )

    def is_connected(self, user_id: str) -> bool:
        """Check if a user has an active WebSocket connection locally."""
        return user_id in self._connections

    async def publish_message(
        self,
        user_id: str,
        message: dict[str, Any],
        *,
        force_disconnect: bool = False,
    ) -> bool:
        """Publish a message to a specific user via Redis Pub/Sub or local fallback."""
        payload = {
            'target_user_id': user_id,
            'message': message,
            'force_disconnect': force_disconnect,
        }
        redis_client = get_redis_client()
        if redis_client:
            try:
                await redis_client.publish(
                    REDIS_WS_CHANNEL, json.dumps(payload)
                )
                return True
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    'Redis WS publish failed: %s; using local fallback', e
                )

        # Fallback for local connection if Redis unavailable
        return await self._send_personal_message_local(
            user_id, message, force_disconnect=force_disconnect
        )

    async def _send_personal_message_local(
        self,
        user_id: str,
        message: dict[str, Any],
        *,
        force_disconnect: bool = False,
    ) -> bool:
        """Deliver a message directly to a locally connected user."""
        websocket = self._connections.get(user_id)
        if not websocket:
            return False
        try:
            await websocket.send_json(message)
            if force_disconnect:
                try:
                    await websocket.close(code=4001)
                except Exception as e:  # noqa: BLE001
                    logger.warning(
                        'Failed to close websocket frame for user %s: %s',
                        user_id,
                        e,
                    )
                self.disconnect(user_id)
            return True
        except Exception as e:  # noqa: BLE001
            logger.error('Failed to send message to user %s: %s', user_id, e)
            self.disconnect(user_id)
            return False

    async def send_personal_message(
        self, user_id: str, message: dict[str, Any]
    ) -> bool:
        """Send a message to a specific user's WebSocket."""
        return await self.publish_message(user_id, message)

    async def broadcast(
        self, message: dict[str, Any], exclude: set[str] | None = None
    ) -> int:
        """Broadcast a message to all connected users locally."""
        exclude = exclude or set()
        count = 0
        for user_id, websocket in list(self._connections.items()):
            if user_id in exclude:
                continue
            try:
                await websocket.send_json(message)
                count += 1
            except Exception as e:  # noqa: BLE001
                logger.error('Failed to broadcast to user %s: %s', user_id, e)
                self.disconnect(user_id)
        return count


_ws_manager: WebSocketManager | None = None


def get_ws_manager() -> WebSocketManager:
    """Get the global WebSocket manager."""
    global _ws_manager
    if _ws_manager is None:
        _ws_manager = WebSocketManager()
    return _ws_manager


async def start_redis_ws_listener(manager: WebSocketManager) -> None:
    """Subscribe to Redis WS channel and deliver messages to local sockets."""
    redis_client = get_redis_client()
    if not redis_client:
        logger.info(
            'Redis unavailable — WebSocketManager running in local mode'
        )
        return

    try:
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(REDIS_WS_CHANNEL)
        logger.info(
            'Subscribed WebSocketManager to Redis channel: %s',
            REDIS_WS_CHANNEL,
        )

        async for message in pubsub.listen():
            if message['type'] == 'message':
                try:
                    data = json.loads(message['data'])
                    target_user_id = data.get('target_user_id')
                    ws_msg = data.get('message')
                    force_disc = data.get('force_disconnect', False)
                    if target_user_id and manager.is_connected(target_user_id):
                        await manager._send_personal_message_local(
                            target_user_id, ws_msg, force_disconnect=force_disc
                        )
                except Exception as e:  # noqa: BLE001
                    logger.error('Error handling Redis WS message: %s', e)
    except asyncio.CancelledError:
        logger.info('Redis WS listener task cancelled')
    except Exception as e:  # noqa: BLE001
        logger.warning('Redis WS listener stopped: %s', e)


async def setup_ws_event_handlers() -> None:
    """Subscribe to events and forward to WebSocket clients."""
    bus = get_event_bus()
    manager = get_ws_manager()

    global _redis_pubsub_task
    if _redis_pubsub_task is None or _redis_pubsub_task.done():
        _redis_pubsub_task = asyncio.create_task(
            start_redis_ws_listener(manager)
        )

    async def handle_user_updated(event: dict[str, Any]) -> None:
        payload = event['payload']
        user_id = payload['user_id']
        await manager.publish_message(
            user_id,
            {
                'type': 'user.updated',
                'data': payload,
            },
        )

    async def handle_user_deactivated(event: dict[str, Any]) -> None:
        payload = event['payload']
        user_id = payload['user_id']
        await manager.publish_message(
            user_id,
            {
                'type': 'user.deactivated',
                'data': {'reason': 'Account deactivated by administrator'},
            },
            force_disconnect=True,
        )

    async def handle_roles_changed(event: dict[str, Any]) -> None:
        payload = event['payload']
        user_id = payload['user_id']
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

    async def handle_password_changed(event: dict[str, Any]) -> None:
        payload = event['payload']
        user_id = payload['user_id']
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

    # Subscribe to relevant events
    await bus.subscribe(UserEvents.UPDATED, handle_user_updated)
    await bus.subscribe(UserEvents.DEACTIVATED, handle_user_deactivated)
    await bus.subscribe(UserEvents.ROLES_CHANGED, handle_roles_changed)
    await bus.subscribe(UserEvents.PASSWORD_CHANGED, handle_password_changed)

    logger.info('WebSocket event handlers subscribed')


async def teardown_ws_event_handlers() -> None:
    """Clean up Redis WS listener task on shutdown."""
    global _redis_pubsub_task
    if _redis_pubsub_task and not _redis_pubsub_task.done():
        _redis_pubsub_task.cancel()
        _redis_pubsub_task = None
    logger.info('WebSocket event handlers torn down')
