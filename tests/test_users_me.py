"""Endpoint tests for GET /users/me — #30 perfil atual."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.error_handlers import register_exception_handlers
from app.core.security import create_access_token
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
    is_active: bool = True,
) -> str:
    out: dict[str, str] = {}

    async def _coro(factory):
        async with factory() as session:
            user = User(
                email=email,
                hashed_password='not-a-real-hash',
                full_name=full_name,
                is_active=is_active,
            )
            session.add(user)
            await session.commit()
            out['id'] = user.id

    run_in_isolated_db(isolated_db_path, _coro)
    return out['id']


def _auth_headers(token: str) -> dict[str, str]:
    return {'Authorization': f'Bearer {token}'}


def test_me_returns_public_user_data(client, isolated_db_path) -> None:
    user_id = _seed_user(
        isolated_db_path, email='me@example.com', full_name='Me User'
    )
    token = create_access_token({'sub': user_id})

    response = client.get('/users/me', headers=_auth_headers(token))
    assert response.status_code == 200

    body = response.json()
    assert body['id'] == user_id
    assert body['email'] == 'me@example.com'
    assert body['full_name'] == 'Me User'
    assert body['is_active'] is True
    assert body['is_verified'] is False
    assert 'created_at' in body


def test_me_does_not_expose_sensitive_fields(client, isolated_db_path) -> None:
    user_id = _seed_user(isolated_db_path, email='secret@example.com')
    token = create_access_token({'sub': user_id})

    response = client.get('/users/me', headers=_auth_headers(token))
    assert response.status_code == 200

    body = response.json()
    assert 'hashed_password' not in body
    assert 'password' not in body
    assert body.keys() == {
        'id',
        'email',
        'full_name',
        'is_active',
        'is_verified',
        'mfa_enabled',
        'mfa_type',
        'created_at',
    }


def test_me_without_token_returns_401(client) -> None:
    response = client.get('/users/me')
    assert response.status_code == 401
    assert response.json()['error']['code'] == 'NOT_AUTHENTICATED'


def test_me_with_invalid_token_returns_401(client) -> None:
    response = client.get('/users/me', headers=_auth_headers('garbage'))
    assert response.status_code == 401
    assert response.json()['error']['code'] == 'TOKEN_INVALID'


def test_me_with_expired_token_returns_401(client, isolated_db_path) -> None:
    user_id = _seed_user(isolated_db_path, email='expired@example.com')
    token = create_access_token(
        {'sub': user_id}, expires_delta=timedelta(minutes=-5)
    )

    response = client.get('/users/me', headers=_auth_headers(token))
    assert response.status_code == 401
    assert response.json()['error']['code'] == 'TOKEN_EXPIRED'
