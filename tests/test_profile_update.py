"""Endpoint tests for PATCH /users/me — #33 atualização de perfil."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.security.security import create_access_token
from app.core.web.error_handlers import register_exception_handlers
from app.db.session import get_db
from app.models.user import User
from tests.conftest import run_in_isolated_db


def _make_app() -> FastAPI:
    from app.api.routers.users import router as users_router

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(users_router)
    return app


@pytest.fixture
def client(isolated_session_factory) -> TestClient:
    app = _make_app()

    async def _override_get_db():
        async with isolated_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app) as test_client:
        yield test_client


def _seed_user(
    isolated_db_path: str,
    *,
    email: str,
    full_name: str | None = None,
) -> str:
    out: dict[str, str] = {}

    async def _coro(factory):
        async with factory() as session:
            user = User(
                email=email,
                hashed_password='not-a-real-hash',
                full_name=full_name,
            )
            session.add(user)
            await session.commit()
            out['id'] = user.id

    run_in_isolated_db(isolated_db_path, _coro)
    return out['id']


def _read_user(isolated_db_path: str, user_id: str) -> User:
    out: dict[str, User] = {}

    async def _coro(factory):
        async with factory() as session:
            out['user'] = await session.get(User, user_id)

    run_in_isolated_db(isolated_db_path, _coro)
    return out['user']


def _auth_headers(token: str) -> dict[str, str]:
    return {'Authorization': f'Bearer {token}'}


def test_successful_update_reflected_in_db(client, isolated_db_path) -> None:
    user_id = _seed_user(
        isolated_db_path, email='me@example.com', full_name='Before'
    )
    token = create_access_token({'sub': user_id})

    response = client.patch(
        '/users/me',
        headers=_auth_headers(token),
        json={'full_name': 'After'},
    )
    assert response.status_code == 200

    body = response.json()
    assert body['full_name'] == 'After'
    assert body['id'] == user_id
    assert 'hashed_password' not in body

    stored = _read_user(isolated_db_path, user_id)
    assert stored.full_name == 'After'
    assert stored.email == 'me@example.com'


def test_partial_update_does_not_affect_other_fields(
    client, isolated_db_path
) -> None:
    user_id = _seed_user(isolated_db_path, email='me@example.com')
    token = create_access_token({'sub': user_id})

    response = client.patch(
        '/users/me',
        headers=_auth_headers(token),
        json={'full_name': 'New Name'},
    )
    assert response.status_code == 200

    body = response.json()
    assert body['full_name'] == 'New Name'
    assert body['email'] == 'me@example.com'
    assert body['is_active'] is True
    assert body['is_verified'] is False


def test_empty_payload_returns_unchanged_profile(
    client, isolated_db_path
) -> None:
    user_id = _seed_user(
        isolated_db_path, email='me@example.com', full_name='Keep'
    )
    token = create_access_token({'sub': user_id})

    response = client.patch('/users/me', headers=_auth_headers(token), json={})
    assert response.status_code == 200
    assert response.json()['full_name'] == 'Keep'


def test_sensitive_fields_rejected_and_not_persisted(
    client, isolated_db_path
) -> None:
    user_id = _seed_user(
        isolated_db_path, email='me@example.com', full_name='Keep'
    )
    token = create_access_token({'sub': user_id})

    response = client.patch(
        '/users/me',
        headers=_auth_headers(token),
        json={'is_active': False, 'hashed_password': 'pwned'},
    )
    assert response.status_code == 422

    stored = _read_user(isolated_db_path, user_id)
    assert stored.is_active is True
    assert stored.full_name == 'Keep'
    assert stored.hashed_password == 'not-a-real-hash'


def test_unauthenticated_returns_401(client) -> None:
    response = client.patch('/users/me', json={'full_name': 'X'})
    assert response.status_code == 401
    assert response.json()['error']['code'] == 'NOT_AUTHENTICATED'
