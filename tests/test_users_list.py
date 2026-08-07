"""Endpoint tests for GET /users — #31 listagem de usuários (admin)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.error_handlers import register_exception_handlers
from app.core.security import create_access_token
from app.db.session import get_db
from app.models.role import Role
from app.models.user import User
from tests.conftest import run_in_isolated_db

_BASE = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def _make_app() -> FastAPI:
    from app.api.routers.users import router as users_router

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(users_router)
    return app


@pytest.fixture
def admin_client(isolated_session_factory) -> TestClient:
    app = _make_app()

    async def _override_get_db():
        async with isolated_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app) as test_client:
        yield test_client


def _seed_admin(
    isolated_db_path: str,
    *,
    email: str = 'admin@example.com',
    created_at: datetime = _BASE,
) -> str:
    out: dict[str, str] = {}

    async def _coro(factory):
        async with factory() as session:
            role = Role(name='admin')
            user = User(
                email=email,
                hashed_password='not-a-real-hash',
                created_at=created_at,
            )
            user.roles.append(role)
            session.add(user)
            await session.commit()
            out['id'] = user.id

    run_in_isolated_db(isolated_db_path, _coro)
    return out['id']


def _seed_user(
    isolated_db_path: str,
    *,
    email: str,
    full_name: str | None = None,
    created_at: datetime = _BASE,
    role: str | None = None,
) -> str:
    out: dict[str, str] = {}

    async def _coro(factory):
        async with factory() as session:
            user = User(
                email=email,
                hashed_password='not-a-real-hash',
                full_name=full_name,
                created_at=created_at,
            )
            if role is not None:
                user.roles.append(Role(name=role))
            session.add(user)
            await session.commit()
            out['id'] = user.id

    run_in_isolated_db(isolated_db_path, _coro)
    return out['id']


def _auth_headers(token: str) -> dict[str, str]:
    return {'Authorization': f'Bearer {token}'}


def test_admin_can_list_users(admin_client, isolated_db_path) -> None:
    admin_id = _seed_admin(isolated_db_path)
    _seed_user(isolated_db_path, email='a@example.com', full_name='A')
    _seed_user(isolated_db_path, email='b@example.com', full_name='B')
    token = create_access_token({'sub': admin_id})

    response = admin_client.get('/users', headers=_auth_headers(token))
    assert response.status_code == 200

    body = response.json()
    assert body['total'] == 3
    assert body['page'] == 1
    assert body['page_size'] == 20
    emails = {item['email'] for item in body['items']}
    assert emails == {'admin@example.com', 'a@example.com', 'b@example.com'}


def test_non_admin_receives_403(admin_client, isolated_db_path) -> None:
    user_id = _seed_user(
        isolated_db_path, email='user@example.com', role='user'
    )
    token = create_access_token({'sub': user_id})

    response = admin_client.get('/users', headers=_auth_headers(token))
    assert response.status_code == 403
    assert response.json()['error']['type'] == 'PermissionDeniedError'
    assert response.json()['error']['code'] == 'INSUFFICIENT_ROLE'


def test_unauthenticated_receives_401(admin_client) -> None:
    response = admin_client.get('/users')
    assert response.status_code == 401
    assert response.json()['error']['code'] == 'NOT_AUTHENTICATED'


def test_pagination_returns_expected_subset(
    admin_client, isolated_db_path
) -> None:
    admin_id = _seed_admin(isolated_db_path)
    for i in range(1, 5):
        _seed_user(
            isolated_db_path,
            email=f'u{i}@example.com',
            created_at=_BASE + timedelta(minutes=i),
        )
    token = create_access_token({'sub': admin_id})

    page1 = admin_client.get(
        '/users',
        headers=_auth_headers(token),
        params={'page': 1, 'page_size': 2},
    ).json()
    page2 = admin_client.get(
        '/users',
        headers=_auth_headers(token),
        params={'page': 2, 'page_size': 2},
    ).json()
    page3 = admin_client.get(
        '/users',
        headers=_auth_headers(token),
        params={'page': 3, 'page_size': 2},
    ).json()

    assert page1['total'] == 5
    assert [item['email'] for item in page1['items']] == [
        'admin@example.com',
        'u1@example.com',
    ]
    assert [item['email'] for item in page2['items']] == [
        'u2@example.com',
        'u3@example.com',
    ]
    assert [item['email'] for item in page3['items']] == ['u4@example.com']
    assert page3['page'] == 3


def test_page_out_of_range_returns_empty_items(
    admin_client, isolated_db_path
) -> None:
    admin_id = _seed_admin(isolated_db_path)
    token = create_access_token({'sub': admin_id})

    response = admin_client.get(
        '/users', headers=_auth_headers(token), params={'page': 99}
    )
    assert response.status_code == 200
    assert response.json()['items'] == []
    assert response.json()['total'] == 1


def test_page_size_capped_at_max(admin_client, isolated_db_path) -> None:
    admin_id = _seed_admin(isolated_db_path)
    token = create_access_token({'sub': admin_id})

    ok = admin_client.get(
        '/users', headers=_auth_headers(token), params={'page_size': 100}
    )
    assert ok.status_code == 200
    assert ok.json()['page_size'] == 100

    rejected = admin_client.get(
        '/users', headers=_auth_headers(token), params={'page_size': 101}
    )
    assert rejected.status_code == 422


def test_invalid_page_rejected(admin_client, isolated_db_path) -> None:
    admin_id = _seed_admin(isolated_db_path)
    token = create_access_token({'sub': admin_id})

    response = admin_client.get(
        '/users', headers=_auth_headers(token), params={'page': 0}
    )
    assert response.status_code == 422


def test_response_has_no_sensitive_fields(
    admin_client, isolated_db_path
) -> None:
    admin_id = _seed_admin(isolated_db_path)
    _seed_user(isolated_db_path, email='secret@example.com')
    token = create_access_token({'sub': admin_id})

    response = admin_client.get('/users', headers=_auth_headers(token))
    body = response.json()
    for item in body['items']:
        assert 'hashed_password' not in item
        assert 'password' not in item
