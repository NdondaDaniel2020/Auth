"""WebSocket authentication and connection management."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import WebSocket, WebSocketException, status
from jwt import InvalidTokenError

from app.core.events import get_event_bus
from app.core.security import decode_access_token
from app.db.session import get_session_factory
from app.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manages WebSocket connections with authentication."""

    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}  # user_id -> WebSocket
        self._user_data: dict[
            str, dict[str, Any]
        ] = {}  # user_id -> {socket, metadata}

    async def connect(
        self,
        websocket: WebSocket,
        token: str,
    ) -> str | None:
        """
        Authenticate and register a WebSocket connection.

        Returns user_id on success, None on failure.
        """
        try:
            payload = decode_access_token(token)
        except InvalidTokenError as e:
            logger.warning('WebSocket auth failed: invalid token: %s', e)
            return None

        user_id = payload.get('sub')
        if not user_id:
            logger.warning('WebSocket auth failed: no subject in token')
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
            'connected_at': payload.get('iat'),
        }

        logger.info('WebSocket connected: user_id=%s', user_id)
        return user_id

    def disconnect(self, user_id: str) -> None:
        """Disconnect and cleanup a WebSocket connection."""
        if user_id in self._connections:
            del self._connections[user_id]
        if user_id in self._user_data:
            del self._user_data[user_id]
        logger.info('WebSocket disconnected: user_id=%s', user_id)

    def is_connected(self, user_id: str) -> bool:
        """Check if a user has an active WebSocket connection."""
        return user_id in self._connections

    async def send_personal_message(
        self, user_id: str, message: dict[str, Any]
    ) -> bool:
        """Send a message to a specific user's WebSocket."""
        websocket = self._connections.get(user_id)
        if not websocket:
            return False
        try:
            await websocket.send_json(message)
            return True
        except Exception as e:  # noqa: BLE001
            logger.error('Failed to send message to user %s: %s', user_id, e)
            self.disconnect(user_id)
            return False

    async def broadcast(
        self, message: dict[str, Any], exclude: set[str] | None = None
    ) -> int:
        """Broadcast a message to all connected users."""
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


async def authenticate_websocket(websocket: WebSocket, token: str) -> str:
    """
    FastAPI dependency for WebSocket authentication.

    Raises WebSocketException on authentication failure.
    Returns user_id on success.
    """
    manager = get_ws_manager()
    user_id = await manager.connect(websocket, token)
    if user_id is None:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason='Authentication failed',
        )
    return user_id


# --- Event-driven WebSocket notifications ---


async def setup_ws_event_handlers() -> None:
    """Subscribe to events and forward to WebSocket clients."""
    bus = get_event_bus()
    manager = get_ws_manager()

    async def handle_user_updated(event: dict[str, Any]) -> None:
        payload = event['payload']
        user_id = payload['user_id']
        if manager.is_connected(user_id):
            await manager.send_personal_message(
                user_id,
                {
                    'type': 'user.updated',
                    'data': payload,
                },
            )

    async def handle_user_deactivated(event: dict[str, Any]) -> None:
        payload = event['payload']
        user_id = payload['user_id']
        if manager.is_connected(user_id):
            await manager.send_personal_message(
                user_id,
                {
                    'type': 'user.deactivated',
                    'data': {'reason': 'Account deactivated by administrator'},
                },
            )
            # Force disconnect
            manager.disconnect(user_id)

    async def handle_roles_changed(event: dict[str, Any]) -> None:
        payload = event['payload']
        user_id = payload['user_id']
        if manager.is_connected(user_id):
            await manager.send_personal_message(
                user_id,
                {
                    'type': 'user.roles_changed',
                    'data': payload,
                },
            )
            # Force disconnect if admin role removed
            if 'admin' in payload.get(
                'old_roles', []
            ) and 'admin' not in payload.get('new_roles', []):
                manager.disconnect(user_id)

    async def handle_password_changed(event: dict[str, Any]) -> None:
        payload = event['payload']
        user_id = payload['user_id']
        if manager.is_connected(user_id):
            await manager.send_personal_message(
                user_id,
                {
                    'type': 'user.password_changed',
                    'data': {
                        'message': 'Your password was changed. Please log in again.'
                    },
                },
            )
            # Force disconnect to require re-authentication
            manager.disconnect(user_id)

    # Subscribe to relevant events
    from app.core.events import UserEvents

    await bus.subscribe(UserEvents.UPDATED, handle_user_updated)
    await bus.subscribe(UserEvents.DEACTIVATED, handle_user_deactivated)
    await bus.subscribe(UserEvents.ROLES_CHANGED, handle_roles_changed)
    await bus.subscribe(UserEvents.PASSWORD_CHANGED, handle_password_changed)

    logger.info('WebSocket event handlers subscribed')
