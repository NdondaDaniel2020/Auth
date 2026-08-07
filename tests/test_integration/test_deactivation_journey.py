"""Deactivation journey: login/access → deactivate → locked out → reactivate — #52."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.models.role import Role
from app.models.user import User
from tests.conftest import run_in_isolated_db

pytestmark = pytest.mark.integration

PASSWORD = 'T3st!Passw0rd'


def _seed_admin(isolated_db_path: str) -> str:
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

    run_in_isolated_db(isolated_db_path, _coro)
    return out['id']


def test_deactivation_journey(
    full_client: TestClient, isolated_db_path
) -> None:
    admin_id = _seed_admin(isolated_db_path)
    admin_headers = {
        'Authorization': f'Bearer {create_access_token({"sub": admin_id})}'
    }

    # 1. Active user logs in and accesses resources
    register = full_client.post(
        '/auth/register',
        json={'email': 'worker@example.com', 'password': PASSWORD},
    )
    assert register.status_code == 201
    user_id = register.json()['id']

    login = full_client.post(
        '/auth/login',
        json={'email': 'worker@example.com', 'password': PASSWORD},
    )
    assert login.status_code == 200
    user_headers = {'Authorization': f'Bearer {login.json()["access_token"]}'}
    assert (
        full_client.get('/users/me', headers=user_headers).status_code == 200
    )

    # 2. Admin deactivates the user
    deactivate = full_client.patch(
        f'/users/{user_id}/deactivate', headers=admin_headers
    )
    assert deactivate.status_code == 200
    assert deactivate.json()['is_active'] is False

    # 3. Old token and fresh login are both rejected
    stale = full_client.get('/users/me', headers=user_headers)
    assert stale.status_code == 401
    assert stale.json()['error']['code'] == 'ACCOUNT_INACTIVE'

    relogin = full_client.post(
        '/auth/login',
        json={'email': 'worker@example.com', 'password': PASSWORD},
    )
    assert relogin.status_code == 401

    # 4. Reactivation restores login
    activate = full_client.patch(
        f'/users/{user_id}/activate', headers=admin_headers
    )
    assert activate.status_code == 200
    assert activate.json()['is_active'] is True

    back = full_client.post(
        '/auth/login',
        json={'email': 'worker@example.com', 'password': PASSWORD},
    )
    assert back.status_code == 200
