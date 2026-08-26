"""Unit tests for rate limiting on WebSocket handshake endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.rate_limiter import request_rate_limiter
from app.services.auth_service import create_ws_ticket


def _make_ws_app() -> FastAPI:
    from app.api.routers.websockets import router as ws_router
    from app.core.error_handlers import register_exception_handlers

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(ws_router)
    return app


@pytest.mark.asyncio
async def test_websocket_connection_within_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_user = MagicMock()
    mock_user.id = 'ws-user-1'
    mock_user.is_active = True

    monkeypatch.setattr(
        'app.api.websockets.UserRepository.get_by_id',
        AsyncMock(return_value=mock_user),
    )

    app = _make_ws_app()
    ticket = await create_ws_ticket('ws-user-1')

    with (
        TestClient(app) as client,
        client.websocket_connect(f'/ws/connect?ticket={ticket}') as ws,
    ):
        ws.send_json({'ping': 'hello'})
        data = ws.receive_json()
        assert data['type'] == 'echo'
        assert data['data'] == {'ping': 'hello'}


@pytest.mark.asyncio
async def test_websocket_handshake_rate_limit_exceeded() -> None:
    app = _make_ws_app()
    ticket = await create_ws_ticket('ws-user-2')

    # Fill rate limit slots (30 per minute default) for testclient IP
    key = 'RATE_LIMIT_WEBSOCKET:testclient'
    for _ in range(30):
        request_rate_limiter.check_and_consume(key, 30, 60.0)

    # Next attempt must be rejected due to rate limiting
    with (
        TestClient(app) as client,
        pytest.raises((Exception, WebSocketDisconnect)),
        client.websocket_connect(f'/ws/connect?ticket={ticket}'),
    ):
        pass
