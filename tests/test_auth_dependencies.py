"""Tests for the auth dependencies — #25, #26, #27 (get_current_user, require_role, check_permission)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies.auth import CurrentUserDep
from app.api.dependencies.permissions import check_permission, require_role
from app.core.error_handlers import register_exception_handlers
from app.core.security import create_access_token
from app.db.session import get_db
from app.models.permission import Permission
from app.models.role import Role
from app.models.user import User
from tests.conftest import run_in_isolated_db


def _make_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get('/me')
    async def me(user: CurrentUserDep) -> dict:
        return {'id': user.id}

    @app.get('/admin-only')
    async def admin_only(user=Depends(require_role('admin'))) -> dict:
        return {'id': user.id}

    @app.get('/users-read')
    async def users_read(user=Depends(check_permission('users:read'))) -> dict:
        return {'id': user.id}

    return app


@pytest.fixture
def authz_client(isolated_session_factory) -> TestClient:
    app = _make_app()

    async def _override_get_db():
        async with isolated_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app) as client:
        yield client


def _seed_user(
    isolated_db_path: str,
    *,
    email: str,
    roles: tuple[str, ...] = (),
    permissions: tuple[str, ...] = (),
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

            for role_name in roles:
                role = Role(name=role_name)

                for code in permissions:
                    permission = Permission(code=code)
                    role.permissions.append(permission)

                user.roles.append(role)

            session.add(user)
            await session.commit()
            out['id'] = user.id

    run_in_isolated_db(isolated_db_path, _coro)
    return out['id']


def _auth_headers(token: str) -> dict[str, str]:
    return {'Authorization': f'Bearer {token}'}


def test_no_token_returns_401(authz_client) -> None:
    response = authz_client.get('/me')
    assert response.status_code == 401
    assert response.json()['error']['type'] == 'NotAuthenticatedError'
    assert response.headers.get('WWW-Authenticate') == 'Bearer'


def test_invalid_token_returns_401(authz_client) -> None:
    response = authz_client.get('/me', headers=_auth_headers('not-a-jwt'))
    assert response.status_code == 401
    assert response.json()['error']['type'] == 'NotAuthenticatedError'


def test_expired_token_returns_401(authz_client, isolated_db_path) -> None:
    user_id = _seed_user(isolated_db_path, email='expired@example.com')
    token = create_access_token(
        {'sub': user_id}, expires_delta=timedelta(minutes=-5)
    )
    response = authz_client.get('/me', headers=_auth_headers(token))
    assert response.status_code == 401
    assert response.json()['error']['type'] == 'NotAuthenticatedError'


def test_valid_token_returns_user(authz_client, isolated_db_path) -> None:
    user_id = _seed_user(isolated_db_path, email='valid@example.com')
    token = create_access_token({'sub': user_id})

    response = authz_client.get('/me', headers=_auth_headers(token))
    assert response.status_code == 200
    assert response.json()['id'] == user_id


def test_inactive_user_rejected(authz_client, isolated_db_path) -> None:
    user_id = _seed_user(
        isolated_db_path,
        email='inactive@example.com',
        is_active=False,
    )
    token = create_access_token({'sub': user_id})

    response = authz_client.get('/me', headers=_auth_headers(token))
    assert response.status_code == 401


def test_unknown_user_rejected(authz_client) -> None:
    token = create_access_token({
        'sub': '00000000-0000-0000-0000-000000000000'
    })
    response = authz_client.get('/me', headers=_auth_headers(token))
    assert response.status_code == 401


def test_require_role_allowed(authz_client, isolated_db_path) -> None:
    user_id = _seed_user(
        isolated_db_path, email='admin@example.com', roles=('admin',)
    )
    token = create_access_token({'sub': user_id})

    response = authz_client.get('/admin-only', headers=_auth_headers(token))
    assert response.status_code == 200
    assert response.json()['id'] == user_id


def test_require_role_denied(authz_client, isolated_db_path) -> None:
    user_id = _seed_user(
        isolated_db_path, email='user@example.com', roles=('user',)
    )
    token = create_access_token({'sub': user_id})

    response = authz_client.get('/admin-only', headers=_auth_headers(token))
    assert response.status_code == 403
    assert response.json()['error']['type'] == 'PermissionDeniedError'


def test_check_permission_allowed(authz_client, isolated_db_path) -> None:
    user_id = _seed_user(
        isolated_db_path,
        email='reader@example.com',
        roles=('user',),
        permissions=('users:read',),
    )
    token = create_access_token({'sub': user_id})

    response = authz_client.get('/users-read', headers=_auth_headers(token))
    assert response.status_code == 200
    assert response.json()['id'] == user_id


def test_check_permission_denied(authz_client, isolated_db_path) -> None:
    user_id = _seed_user(
        isolated_db_path, email='noperm@example.com', roles=('user',)
    )
    token = create_access_token({'sub': user_id})

    response = authz_client.get('/users-read', headers=_auth_headers(token))
    assert response.status_code == 403
    assert response.json()['error']['type'] == 'PermissionDeniedError'


def test_role_check_requires_authentication(authz_client) -> None:
    response = authz_client.get('/admin-only')
    assert response.status_code == 401
    assert response.json()['error']['type'] == 'NotAuthenticatedError'
