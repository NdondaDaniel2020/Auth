"""RBAC journey: role loss/gain reflects on an already-issued access token — #52.

Because ``get_current_user`` reloads roles from the database on every
authenticated request, a token must not need to be reissued after a role
change.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.security import create_access_token, hash_password
from app.models.role import Role
from app.models.user import User
from tests.conftest import run_in_isolated_db

pytestmark = pytest.mark.integration

PASSWORD = 'T3st!Passw0rd'


def _seed_admin(isolated_db_path: str) -> dict[str, str]:
    out: dict[str, str] = {}

    async def _coro(factory):
        async with factory() as session:
            admin_role = Role(name='admin')
            session.add(admin_role)
            admin = User(
                email='admin@example.com',
                hashed_password=hash_password(PASSWORD),
            )
            admin.roles.append(admin_role)
            session.add(admin)
            await session.commit()
            out['id'] = admin.id
            out['role_id'] = admin_role.id

    run_in_isolated_db(isolated_db_path, _coro)
    return out


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


def test_rbac_journey(full_client: TestClient, isolated_db_path) -> None:
    seeded = _seed_admin(isolated_db_path)
    admin_headers = {
        'Authorization': f'Bearer {create_access_token({"sub": seeded["id"]})}'
    }

    # 1. Register a regular user
    register = full_client.post(
        '/auth/register',
        json={'email': 'promoted@example.com', 'password': PASSWORD},
    )
    assert register.status_code == 201
    user_id = register.json()['id']
    user_headers = {
        'Authorization': f'Bearer {create_access_token({"sub": user_id})}'
    }

    # 2. Regular user is blocked from an admin route (403)
    blocked = full_client.get('/users', headers=user_headers)
    assert blocked.status_code == 403
    assert blocked.json()['error']['code'] == 'INSUFFICIENT_ROLE'

    # 3. Admin grants the admin role
    grant = full_client.put(
        f'/users/{user_id}/roles',
        headers=admin_headers,
        json={'role_ids': [seeded['role_id']]},
    )
    assert grant.status_code == 200
    assert _user_role_names(isolated_db_path, user_id) == ['admin']

    # 4. The SAME access token now reaches the admin route (no re-login)
    allowed = full_client.get('/users', headers=user_headers)
    assert allowed.status_code == 200

    # 5. Admin revokes the role; the same token is denied again
    revoke = full_client.put(
        f'/users/{user_id}/roles', headers=admin_headers, json={'role_ids': []}
    )
    assert revoke.status_code == 200
    assert _user_role_names(isolated_db_path, user_id) == []

    denied_again = full_client.get('/users', headers=user_headers)
    assert denied_again.status_code == 403
