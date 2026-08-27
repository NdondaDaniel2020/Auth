from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pyotp
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.main import create_app
from app.models.audit_log import AuditLog
from app.models.mfa_method import MfaMethod
from app.models.role import Role
from app.models.user import User
from app.repositories.user_repository import UserRepository

PASSWORD = 'StrongPassword123!'


@pytest.fixture
def app_with_db(isolated_session_factory):
    application = create_app()

    async def _override_get_db():
        async with isolated_session_factory() as session:
            yield session

    application.dependency_overrides[get_db] = _override_get_db
    yield application
    application.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_backup_code_structured_hashing_and_single_use(
    app_with_db, isolated_session_factory
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app_with_db), base_url='http://test'
    ) as client:
        # Register user
        email = f'backupuser_{uuid4().hex[:8]}@example.com'
        reg_res = await client.post(
            '/api/auth/register',
            json={'email': email, 'password': PASSWORD},
        )
        assert reg_res.status_code == 201

        # Login -> get access_token
        login_res = await client.post(
            '/api/auth/login',
            json={'email': email, 'password': PASSWORD},
        )
        token = login_res.json()['access_token']
        headers = {'Authorization': f'Bearer {token}'}

        # 1. Setup & Enable MFA
        setup_resp = await client.post('/api/mfa/totp/setup', headers=headers)
        secret = setup_resp.json()['secret']

        totp_code = pyotp.TOTP(secret).now()
        enable_resp = await client.post(
            '/api/mfa/totp/enable',
            headers=headers,
            json={'code': totp_code},
        )
        assert enable_resp.status_code == 200
        backup_codes = enable_resp.json()['backup_codes']
        assert len(backup_codes) == 8

        # Check DB for structured format
        async with isolated_session_factory() as session:
            user_res = await session.execute(
                select(User).where(User.email == email)
            )
            db_user = user_res.scalar_one()

            stmt = select(MfaMethod).where(
                MfaMethod.user_id == db_user.id, MfaMethod.type == 'totp'
            )
            res = await session.execute(stmt)
            mfa_method = res.scalar_one()
            stored_codes = mfa_method.data['backup_codes']
            assert len(stored_codes) == 8
            assert 'code_hash' in stored_codes[0]
            assert stored_codes[0]['used_at'] is None
            assert 'created_at' in stored_codes[0]

        # 2. Login via MFA challenge with a backup code
        login_mfa_resp = await client.post(
            '/api/auth/login',
            json={'email': email, 'password': PASSWORD},
        )
        mfa_token = login_mfa_resp.json()['mfa_pending_token']

        used_code = backup_codes[0]
        with patch(
            'app.services.email_service.send_backup_code_used_email',
            new_callable=AsyncMock,
        ) as mock_email:
            challenge_resp = await client.post(
                '/api/auth/login/mfa-challenge',
                json={'mfa_pending_token': mfa_token, 'code': used_code},
            )
            assert challenge_resp.status_code == 200
            assert 'access_token' in challenge_resp.json()
            mock_email.assert_called_once_with(email, 7)

        # 3. Verify Single-Use burn (used_at timestamp set)
        async with isolated_session_factory() as session:
            res = await session.execute(stmt)
            mfa_method = res.scalar_one()
            used_items = [
                item
                for item in mfa_method.data['backup_codes']
                if item['used_at'] is not None
            ]
            assert len(used_items) == 1

        # Re-use attempt must fail
        login_mfa_resp2 = await client.post(
            '/api/auth/login',
            json={'email': email, 'password': PASSWORD},
        )
        mfa_token2 = login_mfa_resp2.json()['mfa_pending_token']

        reuse_resp = await client.post(
            '/api/auth/login/mfa-challenge',
            json={'mfa_pending_token': mfa_token2, 'code': used_code},
        )
        assert reuse_resp.status_code == 401


@pytest.mark.asyncio
async def test_backup_codes_regeneration(
    app_with_db, isolated_session_factory
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app_with_db), base_url='http://test'
    ) as client:
        email = f'regenuser_{uuid4().hex[:8]}@example.com'
        await client.post(
            '/api/auth/register',
            json={'email': email, 'password': PASSWORD},
        )
        login_res = await client.post(
            '/api/auth/login',
            json={'email': email, 'password': PASSWORD},
        )
        token = login_res.json()['access_token']
        headers = {'Authorization': f'Bearer {token}'}

        # Setup & enable MFA
        setup_resp = await client.post('/api/mfa/totp/setup', headers=headers)
        secret = setup_resp.json()['secret']

        totp_code = pyotp.TOTP(secret).now()
        enable_resp = await client.post(
            '/api/mfa/totp/enable',
            headers=headers,
            json={'code': totp_code},
        )
        old_backup_codes = enable_resp.json()['backup_codes']

        # Regenerate backup codes with wrong password (401 InvalidCredentialsError)
        bad_password_resp = await client.post(
            '/api/mfa/totp/backup-codes/regenerate',
            headers=headers,
            json={'password': 'WrongPassword123!'},
        )
        assert bad_password_resp.status_code == 401

        # Regenerate backup codes with correct password
        regen_resp = await client.post(
            '/api/mfa/totp/backup-codes/regenerate',
            headers=headers,
            json={'password': PASSWORD},
        )
        assert regen_resp.status_code == 200
        new_backup_codes = regen_resp.json()['backup_codes']
        assert len(new_backup_codes) == 8
        assert new_backup_codes != old_backup_codes

        # Old code should no longer work
        login_mfa = await client.post(
            '/api/auth/login',
            json={'email': email, 'password': PASSWORD},
        )
        mfa_token = login_mfa.json()['mfa_pending_token']

        old_code_resp = await client.post(
            '/api/auth/login/mfa-challenge',
            json={'mfa_pending_token': mfa_token, 'code': old_backup_codes[0]},
        )
        assert old_code_resp.status_code == 401

        # New code works
        new_code_resp = await client.post(
            '/api/auth/login/mfa-challenge',
            json={'mfa_pending_token': mfa_token, 'code': new_backup_codes[0]},
        )
        assert new_code_resp.status_code == 200


@pytest.mark.asyncio
async def test_admin_disable_user_mfa_with_audit_log(
    app_with_db, isolated_session_factory
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app_with_db), base_url='http://test'
    ) as client:
        # Register user
        user_email = f'targetuser_{uuid4().hex[:8]}@example.com'
        await client.post(
            '/api/auth/register',
            json={'email': user_email, 'password': PASSWORD},
        )
        user_login = await client.post(
            '/api/auth/login',
            json={'email': user_email, 'password': PASSWORD},
        )
        user_token = user_login.json()['access_token']
        user_headers = {'Authorization': f'Bearer {user_token}'}

        # User enables MFA
        setup_resp = await client.post(
            '/api/mfa/totp/setup', headers=user_headers
        )
        secret = setup_resp.json()['secret']
        totp_code = pyotp.TOTP(secret).now()
        await client.post(
            '/api/mfa/totp/enable',
            headers=user_headers,
            json={'code': totp_code},
        )

        # Register and promote admin
        admin_email = f'admin_{uuid4().hex[:8]}@example.com'
        await client.post(
            '/api/auth/register',
            json={'email': admin_email, 'password': PASSWORD},
        )
        async with isolated_session_factory() as session:
            res = await session.execute(
                select(User)
                .options(selectinload(User.roles))
                .where(User.email == admin_email)
            )
            admin_obj = res.scalar_one()
            admin_role_res = await session.execute(
                select(Role).where(Role.name == 'admin')
            )
            admin_role = admin_role_res.scalar_one_or_none()
            if not admin_role:
                admin_role = Role(name='admin', description='Administrator')
                session.add(admin_role)
                await session.flush()
            user_repo = UserRepository(session)
            await user_repo.set_roles(admin_obj, [admin_role])

            target_res = await session.execute(
                select(User).where(User.email == user_email)
            )
            target_obj = target_res.scalar_one()
            target_user_id = target_obj.id
            await session.commit()

        # Admin logs in
        admin_login = await client.post(
            '/api/auth/login',
            json={'email': admin_email, 'password': PASSWORD},
        )
        admin_token = admin_login.json()['access_token']
        admin_headers = {'Authorization': f'Bearer {admin_token}'}

        # Admin disables target_user's MFA
        disable_resp = await client.delete(
            f'/api/users/{target_user_id}/mfa',
            headers=admin_headers,
        )
        assert disable_resp.status_code == 200
        assert disable_resp.json()['mfa_enabled'] is False

        # Verify AuditLog entry
        async with isolated_session_factory() as session:
            stmt = select(AuditLog).where(
                AuditLog.action == 'ADMIN_DISABLE_MFA',
                AuditLog.resource_id == target_user_id,
            )
            res = await session.execute(stmt)
            audit_record = res.scalar_one_or_none()
            assert audit_record is not None
            assert audit_record.actor_user_id == admin_obj.id
