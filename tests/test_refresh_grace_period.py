"""Tests for refresh token rotation grace period & race condition handling."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from app.models.refresh_token import RefreshToken


def _login(api_client, email: str, password: str = 'T3st!Passw0rd'):
    api_client.post(
        '/auth/register',
        json={'email': email, 'password': password},
    )
    response = api_client.post(
        '/auth/login',
        json={'email': email, 'password': password},
    )
    assert response.status_code == 200
    return response.json()


def test_refresh_reuse_within_grace_period_does_not_revoke_other_sessions(
    api_client, isolated_db_path
) -> None:
    # 1. User logs in twice to create 2 distinct active refresh sessions
    session_a = _login(api_client, email='grace1@example.com')
    session_b = _login(api_client, email='grace1@example.com')

    # 2. Session A performs /refresh (revokes session_a refresh_token)
    refreshed_a = api_client.post(
        '/auth/refresh',
        json={'refresh_token': session_a['refresh_token']},
    )
    assert refreshed_a.status_code == 200

    # 3. Session A reuses the revoked token immediately (simulating fast retry / race condition)
    retry_a = api_client.post(
        '/auth/refresh',
        json={'refresh_token': session_a['refresh_token']},
    )
    # Reused request fails with 401
    assert retry_a.status_code == 401

    # 4. Session B should still be valid! (Not revoked due to grace period)
    refreshed_b = api_client.post(
        '/auth/refresh',
        json={'refresh_token': session_b['refresh_token']},
    )
    assert refreshed_b.status_code == 200


@pytest.mark.asyncio
async def test_refresh_reuse_outside_grace_period_revokes_all_sessions(
    api_client, isolated_session_factory
) -> None:
    # 1. User logs in twice to create 2 distinct active refresh sessions
    session_a = _login(api_client, email='grace2@example.com')
    session_b = _login(api_client, email='grace2@example.com')

    # 2. Session A performs /refresh
    refreshed_a = api_client.post(
        '/auth/refresh',
        json={'refresh_token': session_a['refresh_token']},
    )
    assert refreshed_a.status_code == 200

    # 3. Simulate passage of time outside grace period (> 10 seconds)
    # Update revoked_at for session_a's refresh token to 30 seconds ago
    from app.core.security import decode_refresh_token

    jti_a = decode_refresh_token(session_a['refresh_token'])['jti']

    async with isolated_session_factory() as db:
        old_time = datetime.now(UTC) - timedelta(seconds=30)
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.jti == jti_a)
            .values(revoked_at=old_time)
        )
        await db.commit()

    # 4. Session A reuses the revoked token outside grace period
    retry_a = api_client.post(
        '/auth/refresh',
        json={'refresh_token': session_a['refresh_token']},
    )
    assert retry_a.status_code == 401

    # 5. Session B MUST now be revoked as a security containment measure!
    refreshed_b = api_client.post(
        '/auth/refresh',
        json={'refresh_token': session_b['refresh_token']},
    )
    assert refreshed_b.status_code == 401
