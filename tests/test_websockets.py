"""Tests for WebSocket single-use ticket authentication and endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.security import create_access_token
from app.db.session import get_db
from app.models.user import User
from app.services.auth_service import consume_ws_ticket, create_ws_ticket
from tests.conftest import run_in_isolated_db


def _make_ws_app() -> FastAPI:
    from app.api.routers.websockets import router as ws_router
    from app.core.error_handlers import register_exception_handlers

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(ws_router)
    return app


def _seed_user(
    isolated_db_path: str,
    *,
    email: str = 'wsuser@example.com',
    is_active: bool = True,
) -> str:
    out: dict[str, str] = {}

    async def _coro(factory):
        async with factory() as session:
            user = User(
                email=email,
                hashed_password='not-a-real-hash',
                is_active=is_active,
            )
            session.add(user)
            await session.commit()
            out['id'] = user.id

    run_in_isolated_db(isolated_db_path, _coro)
    return out['id']


def test_request_ws_ticket_success(api_client, isolated_db_path) -> None:
    """Authenticated users should be able to request a WebSocket ticket."""
    user_id = _seed_user(isolated_db_path, email='ticket_user@example.com')
    token = create_access_token({'sub': user_id})

    response = api_client.post(
        '/auth/ws-ticket', headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 200
    data = response.json()
    assert 'ticket' in data
    assert data['ticket'].startswith('ws_tkt_')
    assert data['expires_in'] == 15


def test_request_ws_ticket_unauthenticated(api_client) -> None:
    """Unauthenticated users should receive 401 when requesting a WS ticket."""
    response = api_client.post('/auth/ws-ticket')
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_and_consume_ws_ticket() -> None:
    """Ticket creation and atomic consumption logic test."""
    user_id = 'test-user-ws-123'
    ticket = await create_ws_ticket(user_id)
    assert ticket.startswith('ws_tkt_')

    # First consumption should return user_id
    consumed_user_id = await consume_ws_ticket(ticket)
    assert consumed_user_id == user_id

    # Second consumption should return None (one-time use)
    reconsumed = await consume_ws_ticket(ticket)
    assert reconsumed is None


@pytest.mark.asyncio
async def test_websocket_connection_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WebSocket connection succeeds with a valid ticket."""
    mock_user = MagicMock()
    mock_user.id = 'ws-test-user'
    mock_user.is_active = True

    monkeypatch.setattr(
        'app.api.websockets.UserRepository.get_by_id',
        AsyncMock(return_value=mock_user),
    )

    app = _make_ws_app()
    ticket = await create_ws_ticket('ws-test-user')

    with (
        TestClient(app) as test_client,
        test_client.websocket_connect(f'/ws/connect?ticket={ticket}') as ws,
    ):
        ws.send_json({'msg': 'hello'})
        data = ws.receive_json()
        assert data['type'] == 'echo'
        assert data['data'] == {'msg': 'hello'}


@pytest.mark.asyncio
async def test_websocket_connection_ticket_reuse_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Attempting to reuse a WebSocket ticket must fail."""
    mock_user = MagicMock()
    mock_user.id = 'ws-test-user-2'
    mock_user.is_active = True

    monkeypatch.setattr(
        'app.api.websockets.UserRepository.get_by_id',
        AsyncMock(return_value=mock_user),
    )

    app = _make_ws_app()
    ticket = await create_ws_ticket('ws-test-user-2')

    # First connection uses the ticket
    with (
        TestClient(app) as test_client,
        test_client.websocket_connect(f'/ws/connect?ticket={ticket}') as ws,
    ):
        ws.send_json({'msg': 'first'})
        ws.receive_json()

    # Second connection using the same ticket must be rejected
    with (
        TestClient(app) as test_client,
        pytest.raises((Exception, WebSocketDisconnect)),
        test_client.websocket_connect(f'/ws/connect?ticket={ticket}'),
    ):
        pass


@pytest.mark.asyncio
async def test_websocket_connection_invalid_ticket_fails() -> None:
    """WebSocket connection with invalid ticket fails."""
    app = _make_ws_app()
    invalid_ticket = 'ws_tkt_invalid_ticket_string'

    with (
        TestClient(app) as test_client,
        pytest.raises((Exception, WebSocketDisconnect)),
        test_client.websocket_connect(f'/ws/connect?ticket={invalid_ticket}'),
    ):
        pass
