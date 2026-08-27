"""Tests for REST Catch-Up notification sync endpoint (GET /api/notifications/sync)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers.notifications import router as notifications_router
from app.core.security import create_access_token
from app.models.notification import Notification
from app.models.user import User
from tests.conftest import run_in_isolated_db


def _make_notifications_app(isolated_session_factory) -> FastAPI:
    from app.core.web.error_handlers import register_exception_handlers
    from app.db.session import get_db

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(notifications_router, prefix='/api')

    async def _override_get_db():
        async with isolated_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    return app


def _seed_user_and_notifications(
    isolated_db_path: str,
    *,
    email: str = 'sync_user@example.com',
    notification_count: int = 3,
) -> tuple[str, list[int]]:
    out: dict[str, str | list[int]] = {}

    async def _coro(factory):
        async with factory() as session:
            user = User(
                email=email,
                hashed_password='not-a-real-hash',
                is_active=True,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

            n_ids = []
            for i in range(1, notification_count + 1):
                notif = Notification(
                    user_id=user.id,
                    channel='in_app',
                    event_type='user.roles_changed',
                    title=f'Role update {i}',
                    message=f'Your role set was updated ({i})',
                    read=False,
                )
                session.add(notif)
                await session.commit()
                await session.refresh(notif)
                n_ids.append(notif.id)

            out['user_id'] = user.id
            out['notification_ids'] = n_ids

    run_in_isolated_db(isolated_db_path, _coro)
    return str(out['user_id']), list(out['notification_ids'])


def test_sync_notifications_unauthenticated(isolated_session_factory) -> None:
    """Unauthenticated request must return HTTP 401."""
    app = _make_notifications_app(isolated_session_factory)
    with TestClient(app) as test_client:
        response = test_client.get('/api/notifications/sync')
        assert response.status_code == 401


def test_sync_notifications_success_all(
    isolated_session_factory, isolated_db_path
) -> None:
    """Fetching all notifications without parameters returns all items for user."""
    user_id, n_ids = _seed_user_and_notifications(
        isolated_db_path, notification_count=3
    )
    token = create_access_token({'sub': user_id})

    app = _make_notifications_app(isolated_session_factory)
    with TestClient(app) as test_client:
        response = test_client.get(
            '/api/notifications/sync',
            headers={'Authorization': f'Bearer {token}'},
        )
        assert response.status_code == 200
        data = response.json()
        assert data['total'] == 3
        assert len(data['events']) == 3
        assert data['has_more'] is False
        assert data['last_id'] == n_ids[-1]


def test_sync_notifications_filter_since_id(
    isolated_session_factory, isolated_db_path
) -> None:
    """Filtering by since_id returns only notifications with id > since_id."""
    user_id, n_ids = _seed_user_and_notifications(
        isolated_db_path, notification_count=4
    )
    token = create_access_token({'sub': user_id})
    since_id = n_ids[1]

    app = _make_notifications_app(isolated_session_factory)
    with TestClient(app) as test_client:
        response = test_client.get(
            f'/api/notifications/sync?since_id={since_id}',
            headers={'Authorization': f'Bearer {token}'},
        )
        assert response.status_code == 200
        data = response.json()
        assert data['total'] == 2
        assert [e['id'] for e in data['events']] == n_ids[2:]
        assert data['last_id'] == n_ids[-1]


def test_sync_notifications_empty_when_up_to_date(
    isolated_session_factory, isolated_db_path
) -> None:
    """When since_id equals the latest notification id, response is empty."""
    user_id, n_ids = _seed_user_and_notifications(
        isolated_db_path, notification_count=2
    )
    token = create_access_token({'sub': user_id})
    latest_id = n_ids[-1]

    app = _make_notifications_app(isolated_session_factory)
    with TestClient(app) as test_client:
        response = test_client.get(
            f'/api/notifications/sync?since_id={latest_id}',
            headers={'Authorization': f'Bearer {token}'},
        )
        assert response.status_code == 200
        data = response.json()
        assert data['total'] == 0
        assert data['events'] == []
        assert data['has_more'] is False
        assert data['last_id'] == latest_id


def test_sync_notifications_user_isolation(
    isolated_session_factory, isolated_db_path
) -> None:
    """Users can only see their own notifications during catch-up sync."""
    _user1_id, _ = _seed_user_and_notifications(
        isolated_db_path, email='u1@example.com', notification_count=2
    )
    user2_id, _n2_ids = _seed_user_and_notifications(
        isolated_db_path, email='u2@example.com', notification_count=3
    )

    token2 = create_access_token({'sub': user2_id})

    app = _make_notifications_app(isolated_session_factory)
    with TestClient(app) as test_client:
        response = test_client.get(
            '/api/notifications/sync',
            headers={'Authorization': f'Bearer {token2}'},
        )
        assert response.status_code == 200
        data = response.json()
        assert data['total'] == 3
        for event in data['events']:
            assert event['user_id'] == user2_id


def test_sync_notifications_limit_and_has_more(
    isolated_session_factory, isolated_db_path
) -> None:
    """Limiting results sets has_more to True when additional items exist."""
    user_id, n_ids = _seed_user_and_notifications(
        isolated_db_path, notification_count=5
    )
    token = create_access_token({'sub': user_id})

    app = _make_notifications_app(isolated_session_factory)
    with TestClient(app) as test_client:
        response = test_client.get(
            '/api/notifications/sync?limit=2',
            headers={'Authorization': f'Bearer {token}'},
        )
        assert response.status_code == 200
        data = response.json()
        assert data['total'] == 2
        assert len(data['events']) == 2
        assert data['has_more'] is True
        assert data['last_id'] == n_ids[1]
