"""End-to-end tests for the token revocation strategy — #43.

Covers the total-vs-selective distinction and the centralized
``auth_service.revoke_all_user_sessions`` entry point, plus the role-loss
trigger consolidated in this issue.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.error_handlers import register_exception_handlers
from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.models.refresh_token import RefreshToken
from app.models.role import Role
from app.models.user import User
from app.services import auth_service
from tests.conftest import run_in_isolated_db

PASSWORD = 'T3st!Passw0rd'


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


def _seed_role(isolated_db_path: str, name: str) -> str:
    out: dict[str, str] = {}

    async def _coro(factory):
        async with factory() as session:
            role = Role(name=name)
            session.add(role)
            await session.commit()
            out['id'] = role.id

    run_in_isolated_db(isolated_db_path, _coro)
    return out['id']


def _seed_user(
    isolated_db_path: str,
    *,
    email: str,
    role_ids: tuple[str, ...] = (),
) -> str:
    out: dict[str, str] = {}

    async def _coro(factory):
        async with factory() as session:
            user = User(
                email=email,
                hashed_password=hash_password(PASSWORD),
            )
            if role_ids:
                result = await session.execute(
                    select(Role).where(Role.id.in_(role_ids))
                )
                user.roles.extend(result.scalars().all())
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


def _login(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        '/auth/login', json={'email': email, 'password': PASSWORD}
    )
    assert response.status_code == 200
    return response.json()


def _admin_headers(isolated_db_path: str) -> dict[str, str]:
    admin_role_id = _seed_role(isolated_db_path, 'admin')
    admin_id = _seed_user(
        isolated_db_path, email='admin@example.com', role_ids=(admin_role_id,)
    )
    return {
        'Authorization': f'Bearer {create_access_token({"sub": admin_id})}'
    }


def test_logout_revokes_only_the_single_session(
    client, isolated_db_path
) -> None:
    target_id = _seed_user(isolated_db_path, email='target@example.com')

    session_a = _login(client, 'target@example.com')
    session_b = _login(client, 'target@example.com')
    assert session_a['refresh_token'] != session_b['refresh_token']
    assert _active_refresh_tokens(isolated_db_path, target_id) == 2

    logout = client.post(
        '/auth/logout', json={'refresh_token': session_a['refresh_token']}
    )
    assert logout.status_code == 204
    assert _active_refresh_tokens(isolated_db_path, target_id) == 1

    other = client.post(
        '/auth/refresh', json={'refresh_token': session_b['refresh_token']}
    )
    assert other.status_code == 200

    reuse = client.post(
        '/auth/refresh', json={'refresh_token': session_a['refresh_token']}
    )
    assert reuse.status_code == 401
    assert reuse.json()['error']['type'] == 'InvalidRefreshTokenError'


def test_role_loss_revokes_all_sessions(client, isolated_db_path) -> None:
    admin_role_id = _seed_role(isolated_db_path, 'admin')
    admin_id = _seed_user(
        isolated_db_path, email='admin@example.com', role_ids=(admin_role_id,)
    )
    headers = {
        'Authorization': f'Bearer {create_access_token({"sub": admin_id})}'
    }
    target_id = _seed_user(
        isolated_db_path,
        email='demoted@example.com',
        role_ids=(admin_role_id,),
    )

    session_a = _login(client, 'demoted@example.com')
    session_b = _login(client, 'demoted@example.com')
    assert _active_refresh_tokens(isolated_db_path, target_id) == 2

    response = client.put(
        f'/users/{target_id}/roles', headers=headers, json={'role_ids': []}
    )
    assert response.status_code == 200
    assert _active_refresh_tokens(isolated_db_path, target_id) == 0

    for token in (session_a['refresh_token'], session_b['refresh_token']):
        reuse = client.post('/auth/refresh', json={'refresh_token': token})
        assert reuse.status_code == 401
        assert reuse.json()['error']['type'] == 'InvalidRefreshTokenError'


def test_non_sensitive_role_change_keeps_sessions(
    client, isolated_db_path
) -> None:
    headers = _admin_headers(isolated_db_path)
    user_role_id = _seed_role(isolated_db_path, 'user')
    editor_role_id = _seed_role(isolated_db_path, 'editor')
    target_id = _seed_user(
        isolated_db_path,
        email='extended@example.com',
        role_ids=(user_role_id,),
    )

    session_a = _login(client, 'extended@example.com')
    session_b = _login(client, 'extended@example.com')

    response = client.put(
        f'/users/{target_id}/roles',
        headers=headers,
        json={'role_ids': [user_role_id, editor_role_id]},
    )
    assert response.status_code == 200

    assert _active_refresh_tokens(isolated_db_path, target_id) == 2
    for token in (session_a['refresh_token'], session_b['refresh_token']):
        reuse = client.post('/auth/refresh', json={'refresh_token': token})
        assert reuse.status_code == 200


def test_revoke_all_user_sessions_is_centralized(
    client, isolated_db_path, isolated_session_factory
) -> None:
    target_id = _seed_user(isolated_db_path, email='central@example.com')

    session = _login(client, 'central@example.com')
    assert _active_refresh_tokens(isolated_db_path, target_id) == 1

    async def _coro(factory):
        async with factory() as db_session:
            await auth_service.revoke_all_user_sessions(db_session, target_id)
            await db_session.commit()

    run_in_isolated_db(isolated_db_path, _coro)

    assert _active_refresh_tokens(isolated_db_path, target_id) == 0
    reuse = client.post(
        '/auth/refresh', json={'refresh_token': session['refresh_token']}
    )
    assert reuse.status_code == 401
    assert reuse.json()['error']['type'] == 'InvalidRefreshTokenError'


def test_logout_blacklists_access_token(client, isolated_db_path) -> None:
    _seed_user(isolated_db_path, email='blacklist@example.com')
    session = _login(client, 'blacklist@example.com')

    access_token = session['access_token']
    refresh_token = session['refresh_token']

    # Access token works before logout
    me = client.get(
        '/users/me', headers={'Authorization': f'Bearer {access_token}'}
    )
    assert me.status_code == 200

    # Logout passing both refresh token and Bearer access token
    logout = client.post(
        '/auth/logout',
        json={'refresh_token': refresh_token},
        headers={'Authorization': f'Bearer {access_token}'},
    )
    assert logout.status_code == 204

    # Access token is now blacklisted and rejected
    me_after = client.get(
        '/users/me', headers={'Authorization': f'Bearer {access_token}'}
    )
    assert me_after.status_code == 401
    assert me_after.json()['error']['type'] == 'TokenInvalidError'


