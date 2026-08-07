"""Strict input validation tests — #40."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.error_handlers import register_exception_handlers
from app.db.session import get_db


@pytest.fixture
def full_client(
    isolated_session_factory: async_sessionmaker[AsyncSession],
) -> Iterator[TestClient]:
    """TestClient with auth + users routers and an isolated DB session."""
    from app.api.routers.auth import router as auth_router
    from app.api.routers.users import router as users_router

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(auth_router)
    app.include_router(users_router)

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        async with isolated_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app) as test_client:
        yield test_client


def test_invalid_email_rejected(api_client) -> None:
    response = api_client.post(
        '/auth/register',
        json={'email': 'not-an-email', 'password': 'T3st!Passw0rd'},
    )
    assert response.status_code == 422
    details = response.json()['error']['details']
    assert any(d['field'] == 'email' for d in details)


def test_string_over_max_length_rejected(api_client) -> None:
    response = api_client.post(
        '/auth/register',
        json={
            'email': 'long@example.com',
            'password': 'T3st!Passw0rd',
            'full_name': 'A' * 300,
        },
    )
    assert response.status_code == 422
    details = response.json()['error']['details']
    assert any('full_name' in d['field'] for d in details)


def test_wrong_type_rejected(api_client) -> None:
    response = api_client.post(
        '/auth/register',
        json={
            'email': 'type@example.com',
            'password': 'T3st!Passw0rd',
            'full_name': 42,
        },
    )
    assert response.status_code == 422
    details = response.json()['error']['details']
    assert any('full_name' in d['field'] for d in details)


def test_extra_field_rejected(api_client) -> None:
    response = api_client.post(
        '/auth/register',
        json={
            'email': 'extra@example.com',
            'password': 'T3st!Passw0rd',
            'is_admin': True,
        },
    )
    assert response.status_code == 422


def test_whitespace_full_name_rejected(api_client) -> None:
    response = api_client.post(
        '/auth/register',
        json={
            'email': 'ws@example.com',
            'password': 'T3st!Passw0rd',
            'full_name': '   ',
        },
    )
    assert response.status_code == 422


def test_login_rejects_extra_field(api_client) -> None:
    response = api_client.post(
        '/auth/login',
        json={
            'email': 'x@example.com',
            'password': 'whatever',
            'remember_me': True,
        },
    )
    assert response.status_code == 422


def test_email_normalized_on_register(api_client) -> None:
    response = api_client.post(
        '/auth/register',
        json={
            'email': '  Mixed.Case@Example.COM ',
            'password': 'T3st!Passw0rd',
        },
    )
    assert response.status_code == 201
    assert response.json()['email'] == 'mixed.case@example.com'


def test_partial_update_accepts_only_sent_fields(
    full_client, isolated_db_path
) -> None:
    response = full_client.post(
        '/auth/register',
        json={'email': 'partial@example.com', 'password': 'T3st!Passw0rd'},
    )
    assert response.status_code == 201

    access_token = full_client.post(
        '/auth/login',
        json={'email': 'partial@example.com', 'password': 'T3st!Passw0rd'},
    ).json()['access_token']
    headers = {'Authorization': f'Bearer {access_token}'}

    update = full_client.patch(
        '/users/me', json={'full_name': 'Partial User'}, headers=headers
    )
    assert update.status_code == 200
    assert update.json()['full_name'] == 'Partial User'


def test_invalid_role_id_format_rejected(
    full_client, isolated_db_path
) -> None:
    from app.core.security import create_access_token
    from app.models.role import Role
    from app.models.user import User
    from tests.conftest import run_in_isolated_db

    admin_id: dict[str, str] = {}

    async def _seed(factory):
        async with factory() as session:
            role = Role(name='admin')
            session.add(role)
            await session.flush()
            user = User(
                email='admin-roles@example.com',
                hashed_password='not-a-real-hash',
            )
            user.roles.append(role)
            session.add(user)
            await session.commit()
            admin_id['id'] = user.id

    run_in_isolated_db(isolated_db_path, _seed)

    headers = {
        'Authorization': f'Bearer {create_access_token({"sub": admin_id["id"]})}'
    }

    response = full_client.put(
        f'/users/{admin_id["id"]}/roles',
        json={'role_ids': ['not-a-uuid']},
        headers=headers,
    )
    assert response.status_code == 422
    details = response.json()['error']['details']
    assert any('role_ids' in d['field'] for d in details)
