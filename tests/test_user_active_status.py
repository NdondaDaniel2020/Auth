"""Endpoint tests for PATCH /users/{id}/deactivate|activate — #34."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.error_handlers import register_exception_handlers
from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.models.refresh_token import RefreshToken
from app.models.role import Role
from app.models.user import User
from tests.conftest import run_in_isolated_db


def _make_app() -> FastAPI:
    from app.api.routers.auth import router as auth_router
    from app.api.routers.users import router as users_router

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(auth_router)
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
    password: str = 'password123',
    is_active: bool = True,
    role: str | None = None,
) -> str:
    out: dict[str, str] = {}

    async def _coro(factory):
        async with factory() as session:
            user = User(
                email=email,
                hashed_password=hash_password(password),
                is_active=is_active,
            )
            if role is not None:
                user.roles.append(Role(name=role))
            session.add(user)
            await session.commit()
            out['id'] = user.id

    run_in_isolated_db(isolated_db_path, _coro)
    return out['id']


def _active_refresh_tokens(isolated_db_path: str, user_id: str) -> int:
    out: dict[str, int] = {}

    async def _coro(factory):
        async with factory() as session:
            result = await session.execute(
                RefreshToken.__table__.select().where(
                    RefreshToken.user_id == user_id,
                    RefreshToken.revoked.is_(False),
                )
            )
            out['count'] = len(result.all())

    run_in_isolated_db(isolated_db_path, _coro)
    return out['count']


def _login(client: TestClient, email: str, password: str = 'password123'):
    return client.post(
        '/auth/login', json={'email': email, 'password': password}
    )


def _admin_headers(isolated_db_path: str) -> dict[str, str]:
    admin_id = _seed_user(
        isolated_db_path, email='admin@example.com', role='admin'
    )
    return {
        'Authorization': f'Bearer {create_access_token({"sub": admin_id})}'
    }


def test_admin_deactivates_user(client, isolated_db_path) -> None:
    headers = _admin_headers(isolated_db_path)
    target_id = _seed_user(isolated_db_path, email='target@example.com')

    response = client.patch(f'/users/{target_id}/deactivate', headers=headers)
    assert response.status_code == 200
    assert response.json()['is_active'] is False
    assert response.json()['id'] == target_id


def test_deactivated_user_cannot_login(client, isolated_db_path) -> None:
    headers = _admin_headers(isolated_db_path)
    target_id = _seed_user(isolated_db_path, email='target@example.com')

    assert _login(client, 'target@example.com').status_code == 200

    client.patch(f'/users/{target_id}/deactivate', headers=headers)

    response = _login(client, 'target@example.com')
    assert response.status_code == 401
    assert response.json()['error']['code'] == 'INVALID_CREDENTIALS'


def test_token_before_deactivation_rejected_after(
    client, isolated_db_path
) -> None:
    headers = _admin_headers(isolated_db_path)
    target_id = _seed_user(isolated_db_path, email='target@example.com')

    access_token = _login(client, 'target@example.com').json()['access_token']
    user_headers = {'Authorization': f'Bearer {access_token}'}

    assert client.get('/users/me', headers=user_headers).status_code == 200

    client.patch(f'/users/{target_id}/deactivate', headers=headers)

    response = client.get('/users/me', headers=user_headers)
    assert response.status_code == 401
    assert response.json()['error']['code'] == 'ACCOUNT_INACTIVE'


def test_reactivation_restores_access(client, isolated_db_path) -> None:
    headers = _admin_headers(isolated_db_path)
    target_id = _seed_user(isolated_db_path, email='target@example.com')

    client.patch(f'/users/{target_id}/deactivate', headers=headers)
    assert _login(client, 'target@example.com').status_code == 401

    client.patch(f'/users/{target_id}/activate', headers=headers)
    assert _login(client, 'target@example.com').status_code == 200


def test_deactivation_revokes_refresh_tokens(client, isolated_db_path) -> None:
    headers = _admin_headers(isolated_db_path)
    target_id = _seed_user(isolated_db_path, email='target@example.com')

    _login(client, 'target@example.com')
    assert _active_refresh_tokens(isolated_db_path, target_id) == 1

    client.patch(f'/users/{target_id}/deactivate', headers=headers)

    assert _active_refresh_tokens(isolated_db_path, target_id) == 0


def test_reactivation_keeps_user_record(client, isolated_db_path) -> None:
    headers = _admin_headers(isolated_db_path)
    target_id = _seed_user(isolated_db_path, email='target@example.com')

    client.patch(f'/users/{target_id}/deactivate', headers=headers)

    stored = client.get(f'/users/{target_id}', headers=headers)
    assert stored.status_code == 200
    assert stored.json()['is_active'] is False
    assert stored.json()['email'] == 'target@example.com'


def test_non_admin_cannot_deactivate(client, isolated_db_path) -> None:
    user_id = _seed_user(
        isolated_db_path, email='user@example.com', role='user'
    )
    target_id = _seed_user(isolated_db_path, email='target@example.com')
    token = create_access_token({'sub': user_id})

    response = client.patch(
        f'/users/{target_id}/deactivate',
        headers={'Authorization': f'Bearer {token}'},
    )
    assert response.status_code == 403
    assert response.json()['error']['code'] == 'INSUFFICIENT_ROLE'


def test_nonexistent_user_returns_404(client, isolated_db_path) -> None:
    headers = _admin_headers(isolated_db_path)
    missing = '00000000-0000-0000-0000-000000000000'

    deactivate = client.patch(f'/users/{missing}/deactivate', headers=headers)
    assert deactivate.status_code == 404
    assert deactivate.json()['error']['code'] == 'USER_NOT_FOUND'

    activate = client.patch(f'/users/{missing}/activate', headers=headers)
    assert activate.status_code == 404
    assert activate.json()['error']['code'] == 'USER_NOT_FOUND'


def test_admin_cannot_deactivate_self(client, isolated_db_path) -> None:
    admin_id = _seed_user(
        isolated_db_path, email='admin@example.com', role='admin'
    )
    headers = {
        'Authorization': f'Bearer {create_access_token({"sub": admin_id})}'
    }

    response = client.patch(f'/users/{admin_id}/deactivate', headers=headers)
    assert response.status_code == 400
    assert response.json()['error']['code'] == 'SELF_DEACTIVATION_NOT_ALLOWED'


def test_unauthenticated_returns_401(client, isolated_db_path) -> None:
    target_id = _seed_user(isolated_db_path, email='target@example.com')

    response = client.patch(f'/users/{target_id}/deactivate')
    assert response.status_code == 401
    assert response.json()['error']['code'] == 'NOT_AUTHENTICATED'
