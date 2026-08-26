"""Tests for WebSocket single-use ticket authentication and endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.security import create_access_token
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


@pytest.mark.asyncio
async def test_websocket_disconnect_cleans_up_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WebSocket disconnection cleanly removes user connection from WebSocketManager."""
    from app.api.websockets import get_ws_manager

    mock_user = MagicMock()
    mock_user.id = 'ws-cleanup-user'
    mock_user.is_active = True

    monkeypatch.setattr(
        'app.api.websockets.UserRepository.get_by_id',
        AsyncMock(return_value=mock_user),
    )

    app = _make_ws_app()
    ticket = await create_ws_ticket('ws-cleanup-user')
    manager = get_ws_manager()

    with (
        TestClient(app) as test_client,
        test_client.websocket_connect(f'/ws/connect?ticket={ticket}') as ws,
    ):
        assert manager.is_connected('ws-cleanup-user')
        ws.send_json({'msg': 'ping'})
        ws.receive_json()

    # After exiting context (connection closed), user must be disconnected
    assert not manager.is_connected('ws-cleanup-user')


@pytest.mark.asyncio
async def test_websocket_force_disconnect_closes_socket_with_code_4001() -> (
    None
):
    """Test that force_disconnect=True sends code 4001 and cleans up connection."""
    from app.api.websockets import WebSocketManager

    manager = WebSocketManager()
    mock_ws = AsyncMock()
    user_id = 'test-force-disconnect-user'

    manager._connections[user_id] = mock_ws
    manager._user_data[user_id] = {'socket': mock_ws}

    assert manager.is_connected(user_id)

    msg = {
        'type': 'user.deactivated',
        'data': {'reason': 'Account deactivated'},
    }
    success = await manager._send_personal_message_local(
        user_id, msg, force_disconnect=True
    )

    assert success is True
    mock_ws.send_json.assert_called_once_with(msg)
    mock_ws.close.assert_called_once_with(code=4001)
    assert not manager.is_connected(user_id)


@pytest.mark.asyncio
async def test_redis_ws_listener_handles_force_disconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test Redis WS listener receiving a message with force_disconnect=True."""
    import json

    from app.api.websockets import WebSocketManager, start_redis_ws_listener

    manager = WebSocketManager()
    mock_ws = AsyncMock()
    user_id = 'redis-force-user'

    manager._connections[user_id] = mock_ws
    manager._user_data[user_id] = {'socket': mock_ws}

    pubsub_msg = {
        'type': 'message',
        'data': json.dumps({
            'target_user_id': user_id,
            'message': {'type': 'user.password_changed'},
            'force_disconnect': True,
        }),
    }

    async def mock_listen():
        yield pubsub_msg

    mock_pubsub = MagicMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_pubsub.listen = mock_listen

    mock_redis = MagicMock()
    mock_redis.pubsub.return_value = mock_pubsub

    monkeypatch.setattr(
        'app.api.websockets.get_redis_client', lambda: mock_redis
    )

    await start_redis_ws_listener(manager)

    mock_ws.close.assert_called_once_with(code=4001)
    assert not manager.is_connected(user_id)


@pytest.mark.asyncio
async def test_ws_event_handlers_publish_force_disconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test event handlers for DEACTIVATED, PASSWORD_CHANGED, and ROLES_CHANGED."""
    from app.api.websockets import setup_ws_event_handlers
    from app.core.events import Event, UserEvents, get_event_bus

    published_events = []

    async def mock_publish(user_id, message, force_disconnect=False):
        published_events.append({
            'user_id': user_id,
            'message': message,
            'force_disconnect': force_disconnect,
        })
        return True

    manager = AsyncMock()
    manager.publish_message = mock_publish
    monkeypatch.setattr('app.api.websockets.get_ws_manager', lambda: manager)
    monkeypatch.setattr(
        'app.api.websockets.start_redis_ws_listener', AsyncMock()
    )

    await setup_ws_event_handlers()
    bus = get_event_bus()

    # Trigger DEACTIVATED
    await bus.publish(
        Event(type=UserEvents.DEACTIVATED, payload={'user_id': 'user-1'})
    )
    # Trigger PASSWORD_CHANGED
    await bus.publish(
        Event(type=UserEvents.PASSWORD_CHANGED, payload={'user_id': 'user-2'})
    )
    # Trigger ROLES_CHANGED with admin role removed
    await bus.publish(
        Event(
            type=UserEvents.ROLES_CHANGED,
            payload={
                'user_id': 'user-3',
                'old_roles': ['admin', 'user'],
                'new_roles': ['user'],
            },
        )
    )

    assert len(published_events) == 3
    assert published_events[0]['user_id'] == 'user-1'
    assert published_events[0]['force_disconnect'] is True

    assert published_events[1]['user_id'] == 'user-2'
    assert published_events[1]['force_disconnect'] is True

    assert published_events[2]['user_id'] == 'user-3'
    assert published_events[2]['force_disconnect'] is True
