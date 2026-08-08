"""Endpoint tests for PUT /users/{id}/roles — #35 alteração de roles."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.error_handlers import register_exception_handlers
from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.models.role import Role
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
                hashed_password=hash_password('password123'),
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


def _user_role_names(isolated_db_path: str, user_id: str) -> list[str]:
    out: dict[str, list[str]] = {}

    async def _coro(factory):
        async with factory() as session:
            result = await session.execute(
                select(User)
                .options(selectinload(User.roles))
                .where(User.id == user_id)
            )
            user = result.scalar_one()
            out['names'] = sorted(role.name for role in user.roles)

    run_in_isolated_db(isolated_db_path, _coro)
    return out['names']


def _headers(token: str) -> dict[str, str]:
    return {'Authorization': f'Bearer {token}'}


def _admin_headers(isolated_db_path: str) -> dict[str, str]:
    admin_role_id = _seed_role(isolated_db_path, 'admin')
    admin_id = _seed_user(
        isolated_db_path, email='admin@example.com', role_ids=(admin_role_id,)
    )
    return _headers(create_access_token({'sub': admin_id}))


def test_admin_assigns_roles(client, isolated_db_path) -> None:
    headers = _admin_headers(isolated_db_path)
    user_role_id = _seed_role(isolated_db_path, 'user')
    target_id = _seed_user(isolated_db_path, email='target@example.com')

    response = client.put(
        f'/users/{target_id}/roles',
        headers=headers,
        json={'role_ids': [user_role_id]},
    )
    assert response.status_code == 200
    assert response.json()['id'] == target_id
    assert _user_role_names(isolated_db_path, target_id) == ['user']


def test_empty_role_ids_removes_all_roles(client, isolated_db_path) -> None:
    headers = _admin_headers(isolated_db_path)
    user_role_id = _seed_role(isolated_db_path, 'user')
    target_id = _seed_user(
        isolated_db_path, email='target@example.com', role_ids=(user_role_id,)
    )
    assert _user_role_names(isolated_db_path, target_id) == ['user']

    response = client.put(
        f'/users/{target_id}/roles', headers=headers, json={'role_ids': []}
    )
    assert response.status_code == 200
    assert _user_role_names(isolated_db_path, target_id) == []


def test_nonexistent_role_returns_404(client, isolated_db_path) -> None:
    headers = _admin_headers(isolated_db_path)
    target_id = _seed_user(isolated_db_path, email='target@example.com')

    response = client.put(
        f'/users/{target_id}/roles',
        headers=headers,
        json={'role_ids': ['00000000-0000-0000-0000-000000000000']},
    )
    assert response.status_code == 404
    assert response.json()['error']['code'] == 'ROLE_NOT_FOUND'


def test_nonexistent_user_returns_404(client, isolated_db_path) -> None:
    headers = _admin_headers(isolated_db_path)
    user_role_id = _seed_role(isolated_db_path, 'user')

    response = client.put(
        '/users/00000000-0000-0000-0000-000000000000/roles',
        headers=headers,
        json={'role_ids': [user_role_id]},
    )
    assert response.status_code == 404
    assert response.json()['error']['code'] == 'USER_NOT_FOUND'


def test_user_gains_access_after_role_assignment(
    client, isolated_db_path
) -> None:
    admin_role_id = _seed_role(isolated_db_path, 'admin')
    admin_id = _seed_user(
        isolated_db_path,
        email='admin@example.com',
        role_ids=(admin_role_id,),
    )
    headers = _headers(create_access_token({'sub': admin_id}))
    user_id = _seed_user(isolated_db_path, email='promoted@example.com')
    user_headers = _headers(create_access_token({'sub': user_id}))

    assert client.get('/users', headers=user_headers).status_code == 403

    response = client.put(
        f'/users/{user_id}/roles',
        headers=headers,
        json={'role_ids': [admin_role_id]},
    )
    assert response.status_code == 200

    assert client.get('/users', headers=user_headers).status_code == 200


def test_user_loses_access_after_role_removal(
    client, isolated_db_path
) -> None:
    admin_role_id = _seed_role(isolated_db_path, 'admin')
    admin_id = _seed_user(
        isolated_db_path,
        email='admin@example.com',
        role_ids=(admin_role_id,),
    )
    headers = _headers(create_access_token({'sub': admin_id}))
    user_id = _seed_user(
        isolated_db_path,
        email='demoted@example.com',
        role_ids=(admin_role_id,),
    )
    user_headers = _headers(create_access_token({'sub': user_id}))

    assert client.get('/users', headers=user_headers).status_code == 200

    response = client.put(
        f'/users/{user_id}/roles', headers=headers, json={'role_ids': []}
    )
    assert response.status_code == 200

    assert client.get('/users', headers=user_headers).status_code == 403
    assert _user_role_names(isolated_db_path, user_id) == []


def test_non_admin_cannot_change_roles(client, isolated_db_path) -> None:
    user_role_id = _seed_role(isolated_db_path, 'user')
    user_id = _seed_user(
        isolated_db_path, email='user@example.com', role_ids=(user_role_id,)
    )
    target_id = _seed_user(isolated_db_path, email='target@example.com')

    response = client.put(
        f'/users/{target_id}/roles',
        headers=_headers(create_access_token({'sub': user_id})),
        json={'role_ids': [user_role_id]},
    )
    assert response.status_code == 403
    assert response.json()['error']['code'] == 'INSUFFICIENT_ROLE'


def test_admin_cannot_remove_own_admin_role(client, isolated_db_path) -> None:
    admin_role_id = _seed_role(isolated_db_path, 'admin')
    admin_id = _seed_user(
        isolated_db_path, email='admin@example.com', role_ids=(admin_role_id,)
    )
    headers = _headers(create_access_token({'sub': admin_id}))

    response = client.put(
        f'/users/{admin_id}/roles', headers=headers, json={'role_ids': []}
    )
    assert response.status_code == 400
    assert response.json()['error']['code'] == 'SELF_ROLE_REMOVAL_NOT_ALLOWED'


def test_unauthenticated_returns_401(client, isolated_db_path) -> None:
    user_role_id = _seed_role(isolated_db_path, 'user')
    target_id = _seed_user(isolated_db_path, email='target@example.com')

    response = client.put(
        f'/users/{target_id}/roles', json={'role_ids': [user_role_id]}
    )
    assert response.status_code == 401
    assert response.json()['error']['code'] == 'NOT_AUTHENTICATED'
