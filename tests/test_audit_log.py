"""Tests for audit logging of admin actions — #36."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.core.exceptions import AuditImmutabilityError
from app.core.security.audit import compute_audit_hash
from app.core.security.security import create_access_token
from app.core.web.error_handlers import register_exception_handlers
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.role import Role
from app.models.user import User
from app.repositories.audit_repository import AuditRepository
from app.services.audit_service import (
    record_admin_action,
    verify_audit_trail_integrity,
)
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


def test_audit_record_generates_valid_hash_chain(isolated_db_path) -> None:
    async def _coro(factory):
        async with factory() as session:
            repo = AuditRepository(session)
            rec1 = await repo.add_record(
                actor_user_id='user-1',
                action='USER_CREATED',
                resource_type='user',
                resource_id='user-1',
            )
            rec2 = await repo.add_record(
                actor_user_id='user-1',
                action='ROLE_ASSIGNED',
                resource_type='role',
                resource_id='role-admin',
            )
            rec3 = await repo.add_record(
                actor_user_id='user-1',
                action='USER_ACTIVATED',
                resource_type='user',
                resource_id='user-2',
            )
            await session.commit()

            assert rec1.previous_hash is None
            assert rec1.hash is not None
            assert rec2.previous_hash == rec1.hash
            assert rec3.previous_hash == rec2.hash

            assert rec1.hash == compute_audit_hash(
                id=rec1.id,
                actor_user_id=rec1.actor_user_id,
                action=rec1.action,
                resource_type=rec1.resource_type,
                resource_id=rec1.resource_id,
                result=rec1.result,
                details=rec1.details,
                created_at=rec1.created_at,
                previous_hash=rec1.previous_hash,
            )

    run_in_isolated_db(isolated_db_path, _coro)


def test_audit_trail_integrity_verification_success(isolated_db_path) -> None:
    async def _coro(factory):
        async with factory() as session:
            await record_admin_action(
                session,
                actor_user_id='admin-1',
                action='ACTION_1',
                resource_type='system',
                resource_id='sys-1',
            )
            await record_admin_action(
                session,
                actor_user_id='admin-1',
                action='ACTION_2',
                resource_type='system',
                resource_id='sys-2',
            )
            await session.commit()

            is_valid, errors = await verify_audit_trail_integrity(session)
            assert is_valid is True
            assert errors == []

    run_in_isolated_db(isolated_db_path, _coro)


def test_audit_trail_detects_data_tampering(isolated_db_path) -> None:
    async def _coro(factory):
        async with factory() as session:
            await record_admin_action(
                session,
                actor_user_id='admin-1',
                action='ACTION_ORIGINAL',
                resource_type='system',
                resource_id='sys-1',
            )
            await session.commit()

            repo = AuditRepository(session)
            records = await repo.list_all_chronological()
            original = records[0]

            # 1. Simular adulteração de campo (hash mismatch)
            tampered_record = AuditLog(
                id=original.id,
                actor_user_id=original.actor_user_id,
                action='ACTION_CORRUPTED',
                resource_type=original.resource_type,
                resource_id=original.resource_id,
                result=original.result,
                details=original.details,
                created_at=original.created_at,
                previous_hash=original.previous_hash,
                hash=original.hash,
            )

            is_valid, errors = await verify_audit_trail_integrity(
                session, records=[tampered_record]
            )
            assert is_valid is False
            assert len(errors) == 1
            assert 'hash mismatch' in errors[0]

            # 2. Simular quebra de cadeia (previous_hash adulterado)
            broken_chain_record = AuditLog(
                id=original.id,
                actor_user_id=original.actor_user_id,
                action=original.action,
                resource_type=original.resource_type,
                resource_id=original.resource_id,
                result=original.result,
                details=original.details,
                created_at=original.created_at,
                previous_hash='invalid-previous-hash',
                hash=original.hash,
            )
            is_valid, errors = await verify_audit_trail_integrity(
                session, records=[broken_chain_record]
            )
            assert is_valid is False
            assert any('broken previous_hash chain' in e for e in errors)

    run_in_isolated_db(isolated_db_path, _coro)


def test_audit_repository_blocks_mutations(isolated_db_path) -> None:
    async def _coro(factory):
        async with factory() as session:
            repo = AuditRepository(session)
            rec = await repo.add_record(
                actor_user_id='admin-1',
                action='USER_BLOCKED',
                resource_type='user',
                resource_id='u-1',
            )
            await session.commit()

            with pytest.raises(AuditImmutabilityError) as exc_update:
                await repo.update(rec, {'action': 'HACKED'})
            assert exc_update.value.code == 'AUDIT_LOG_IMMUTABLE'

            with pytest.raises(AuditImmutabilityError) as exc_delete:
                await repo.delete(rec)
            assert exc_delete.value.code == 'AUDIT_LOG_IMMUTABLE'

    run_in_isolated_db(isolated_db_path, _coro)


def test_database_trigger_prevents_direct_sql_update(isolated_db_path) -> None:
    async def _coro(factory):
        async with factory() as session:
            repo = AuditRepository(session)
            rec = await repo.add_record(
                actor_user_id='admin-1',
                action='SAFE_ACTION',
                resource_type='user',
                resource_id='u-1',
            )
            await session.commit()

            with pytest.raises(DBAPIError) as exc:
                await session.execute(
                    text(
                        "UPDATE audit_logs SET action = 'HACKED' WHERE id = :id"
                    ),
                    {'id': rec.id},
                )
                await session.commit()

            assert 'append-only' in str(exc.value)

    run_in_isolated_db(isolated_db_path, _coro)


def test_database_trigger_prevents_direct_sql_delete(isolated_db_path) -> None:
    async def _coro(factory):
        async with factory() as session:
            repo = AuditRepository(session)
            rec = await repo.add_record(
                actor_user_id='admin-1',
                action='SAFE_ACTION',
                resource_type='user',
                resource_id='u-1',
            )
            await session.commit()

            with pytest.raises(DBAPIError) as exc:
                await session.execute(
                    text('DELETE FROM audit_logs WHERE id = :id'),
                    {'id': rec.id},
                )
                await session.commit()

            assert 'append-only' in str(exc.value)

    run_in_isolated_db(isolated_db_path, _coro)


def test_orm_event_listener_prevents_session_delete(isolated_db_path) -> None:
    async def _coro(factory):
        async with factory() as session:
            repo = AuditRepository(session)
            rec = await repo.add_record(
                actor_user_id='admin-1',
                action='SAFE_ACTION',
                resource_type='user',
                resource_id='u-1',
            )
            await session.commit()

            with pytest.raises(AuditImmutabilityError):
                await session.delete(rec)
                await session.flush()

    run_in_isolated_db(isolated_db_path, _coro)
