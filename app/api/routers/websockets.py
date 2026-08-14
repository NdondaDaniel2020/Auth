"""WebSocket router for real-time communication."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query, WebSocket

from app.api.dependencies.rate_limit import rate_limit
from app.api.websockets import (
    authenticate_websocket,
    get_ws_manager,
)

router = APIRouter(prefix='/ws', tags=['websockets'])

logger = logging.getLogger(__name__)


@router.websocket(
    '/connect',
    dependencies=[Depends(rate_limit('RATE_LIMIT_WEBSOCKET'))],
)
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description='JWT access token'),
    user_id: str = Depends(authenticate_websocket),
) -> None:
    """
    WebSocket connection endpoint.

    Requires a valid JWT access token as query parameter: `?token=<jwt>`
    """
    manager = get_ws_manager()
    try:
        while True:
            data = await websocket.receive_json()
            # Echo for now - in production, handle different message types
            await websocket.send_json({
                'type': 'echo',
                'data': data,
            })
    except Exception:  # noqa: BLE001
        # Connection closed by client or network error - expected during disconnect
        logger.debug('WebSocket connection closed for user %s', user_id)
    finally:
        manager.disconnect(user_id)


@router.get('/status')
async def websocket_status() -> dict[str, Any]:
    """Get WebSocket connection statistics."""
    manager = get_ws_manager()
    return {
        'connected_users': list(manager._connections.keys()),
        'total_connections': len(manager._connections),
    }
