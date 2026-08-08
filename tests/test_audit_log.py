"""Tests for audit logging of admin actions — #36."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.core.error_handlers import register_exception_handlers
from app.core.security import create_access_token
from app.db.session import get_db
from app.models.audit_log import AuditLog
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
            user = User(email=email, hashed_password='not-a-real-hash')
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


def _admin_headers(isolated_db_path: str) -> dict[str, str]:
    admin_role_id = _seed_role(isolated_db_path, 'admin')
    admin_id = _seed_user(
        isolated_db_path, email='admin@example.com', role_ids=(admin_role_id,)
    )
    return {
        'Authorization': f'Bearer {create_access_token({"sub": admin_id})}'
    }


def _audit_records(isolated_db_path: str) -> list[dict]:
    out: dict[str, list[dict]] = {}

    async def _coro(factory):
        async with factory() as session:
            result = await session.execute(
                select(AuditLog).order_by(AuditLog.created_at, text('rowid'))
            )
            out['records'] = [
                {
                    'actor': record.actor_user_id,
                    'action': record.action,
                    'resource_type': record.resource_type,
                    'resource_id': record.resource_id,
                    'result': record.result,
                    'details': record.details,
                    'created_at': record.created_at,
                }
                for record in result.scalars()
            ]

    run_in_isolated_db(isolated_db_path, _coro)
    return out['records']


def test_role_change_creates_audit_record(client, isolated_db_path) -> None:
    admin_role_id = _seed_role(isolated_db_path, 'admin')
    admin_id = _seed_user(
        isolated_db_path,
        email='admin@example.com',
        role_ids=(admin_role_id,),
    )
    headers = {
        'Authorization': f'Bearer {create_access_token({"sub": admin_id})}'
    }
    target_id = _seed_user(isolated_db_path, email='target@example.com')

    response = client.put(
        f'/users/{target_id}/roles',
        headers=headers,
        json={'role_ids': [admin_role_id]},
    )
    assert response.status_code == 200

    records = _audit_records(isolated_db_path)
    assert len(records) == 1
    assert records[0]['actor'] == admin_id
    assert records[0]['action'] == 'USER_ROLES_UPDATED'
    assert records[0]['resource_type'] == 'user'
    assert records[0]['resource_id'] == target_id
    assert records[0]['result'] == 'success'
    assert records[0]['details']['role_ids'] == [admin_role_id]
    assert records[0]['created_at'] is not None


def test_deactivate_creates_audit_record(client, isolated_db_path) -> None:
    headers = _admin_headers(isolated_db_path)
    target_id = _seed_user(isolated_db_path, email='target@example.com')

    assert (
        client.patch(
            f'/users/{target_id}/deactivate', headers=headers
        ).status_code
        == 200
    )

    records = _audit_records(isolated_db_path)
    assert len(records) == 1
    assert records[0]['action'] == 'USER_DEACTIVATED'
    assert records[0]['resource_id'] == target_id
    assert records[0]['result'] == 'success'


def test_activate_creates_audit_record(client, isolated_db_path) -> None:
    headers = _admin_headers(isolated_db_path)
    target_id = _seed_user(isolated_db_path, email='target@example.com')

    assert (
        client.patch(
            f'/users/{target_id}/activate', headers=headers
        ).status_code
        == 200
    )

    records = _audit_records(isolated_db_path)
    assert len(records) == 1
    assert records[0]['action'] == 'USER_ACTIVATED'
    assert records[0]['resource_id'] == target_id
    assert records[0]['result'] == 'success'


def test_rejected_self_deactivation_logged_as_denied(
    client, isolated_db_path
) -> None:
    admin_role_id = _seed_role(isolated_db_path, 'admin')
    admin_id = _seed_user(
        isolated_db_path,
        email='admin@example.com',
        role_ids=(admin_role_id,),
    )
    headers = {
        'Authorization': f'Bearer {create_access_token({"sub": admin_id})}'
    }

    response = client.patch(f'/users/{admin_id}/deactivate', headers=headers)
    assert response.status_code == 400
    assert response.json()['error']['code'] == 'SELF_DEACTIVATION_NOT_ALLOWED'

    records = _audit_records(isolated_db_path)
    assert len(records) == 1
    assert records[0]['action'] == 'USER_DEACTIVATED'
    assert records[0]['resource_id'] == admin_id
    assert records[0]['result'] == 'denied'
    assert records[0]['details']['reason'] == 'self deactivation'


def test_rejected_self_role_removal_logged_as_denied(
    client, isolated_db_path
) -> None:
    admin_role_id = _seed_role(isolated_db_path, 'admin')
    admin_id = _seed_user(
        isolated_db_path,
        email='admin@example.com',
        role_ids=(admin_role_id,),
    )
    headers = {
        'Authorization': f'Bearer {create_access_token({"sub": admin_id})}'
    }

    response = client.put(
        f'/users/{admin_id}/roles', headers=headers, json={'role_ids': []}
    )
    assert response.status_code == 400
    assert response.json()['error']['code'] == 'SELF_ROLE_REMOVAL_NOT_ALLOWED'

    records = _audit_records(isolated_db_path)
    assert len(records) == 1
    assert records[0]['action'] == 'USER_ROLES_UPDATED'
    assert records[0]['resource_id'] == admin_id
    assert records[0]['result'] == 'denied'
    assert records[0]['details']['reason'] == 'self admin role removal'


def test_failed_operation_writes_no_audit(client, isolated_db_path) -> None:
    headers = _admin_headers(isolated_db_path)

    response = client.patch(
        '/users/00000000-0000-0000-0000-000000000000/deactivate',
        headers=headers,
    )
    assert response.status_code == 404

    assert _audit_records(isolated_db_path) == []


def test_deactivate_then_activate_logs_both(client, isolated_db_path) -> None:
    headers = _admin_headers(isolated_db_path)
    target_id = _seed_user(isolated_db_path, email='target@example.com')

    client.patch(f'/users/{target_id}/deactivate', headers=headers)
    client.patch(f'/users/{target_id}/activate', headers=headers)

    records = _audit_records(isolated_db_path)
    assert [r['action'] for r in records] == [
        'USER_DEACTIVATED',
        'USER_ACTIVATED',
    ]
    assert all(r['actor'] == records[0]['actor'] for r in records)
