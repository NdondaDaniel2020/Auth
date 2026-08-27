"""WebSocket authentication dependency."""

from __future__ import annotations

from fastapi import WebSocket, WebSocketException, status

from app.services.websocket_service import get_ws_manager


async def authenticate_websocket(websocket: WebSocket, ticket: str) -> str:
    """FastAPI dependency for WebSocket authentication.

    Raises WebSocketException on authentication failure.
    Returns user_id on success.
    """
    manager = get_ws_manager()
    user_id = await manager.connect(websocket, ticket)
    if user_id is None:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason='Authentication failed',
        )
    return user_id
