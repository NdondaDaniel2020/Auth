"""WebSocket router for real-time communication."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from app.api.dependencies.rate_limit import rate_limit
from app.api.dependencies.websocket import authenticate_websocket
from app.services.websocket_service import get_ws_manager

router = APIRouter(prefix='/ws', tags=['websockets'])

logger = logging.getLogger(__name__)


@router.websocket(
    '/connect',
    dependencies=[Depends(rate_limit('RATE_LIMIT_WEBSOCKET'))],
)
async def websocket_endpoint(
    websocket: WebSocket,
    ticket: Annotated[
        str, Query(description='One-time WebSocket authentication ticket')
    ],
    user_id: Annotated[str, Depends(authenticate_websocket)],
) -> None:
    """
    WebSocket connection endpoint.

    Requires a valid one-time authentication ticket as query parameter: `?ticket=<ws_tkt_...>`
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
    except WebSocketDisconnect:
        logger.info(
            'WebSocket disconnected naturally or via heartbeat ping/pong timeout for user %s',
            user_id,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(
            'WebSocket connection terminated with error for user %s: %s',
            user_id,
            e,
        )
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
