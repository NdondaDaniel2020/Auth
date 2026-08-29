"""Unit tests for expired tokens housekeeping cleanup service."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.email_verification_token import EmailVerificationToken
from app.models.password_reset_token import PasswordResetToken
from app.models.refresh_token import RefreshToken
from app.services.cleanup_service import cleanup_expired_tokens
from app.utils.tokens import hash_token
from tests.conftest import run_in_isolated_db


def test_cleanup_expired_tokens_deletes_expired_and_retains_valid(
    isolated_db_path,
) -> None:
    async def _setup_data(factory):
        async with factory() as session:
            from app.core.security import hash_password
            from app.models.user import User

            user = User(
                email='cleanup@example.com',
                hashed_password=hash_password('T3st!Passw0rd'),
            )
            session.add(user)
            await session.flush()

            now = datetime.now(UTC)

            # Expired tokens
            session.add(
                RefreshToken(
                    jti='expired-refresh',
                    user_id=user.id,
                    expires_at=now - timedelta(hours=1),
                )
            )
            session.add(
                PasswordResetToken(
                    user_id=user.id,
                    token_hash=hash_token('expired-reset'),
                    expires_at=now - timedelta(hours=1),
                )
            )
            session.add(
                EmailVerificationToken(
                    user_id=user.id,
                    token_hash=hash_token('expired-verify'),
                    expires_at=now - timedelta(hours=1),
                )
            )

            # Active/valid tokens
            session.add(
                RefreshToken(
                    jti='active-refresh',
                    user_id=user.id,
                    expires_at=now + timedelta(hours=1),
                )
            )
            session.add(
                PasswordResetToken(
                    user_id=user.id,
                    token_hash=hash_token('active-reset'),
                    expires_at=now + timedelta(hours=1),
                )
            )
            session.add(
                EmailVerificationToken(
                    user_id=user.id,
                    token_hash=hash_token('active-verify'),
                    expires_at=now + timedelta(hours=1),
                )
            )

            await session.commit()

    run_in_isolated_db(isolated_db_path, _setup_data)

    async def _run_cleanup(factory):
        async with factory() as session:
            res = await cleanup_expired_tokens(session)
            assert res['refresh_tokens'] == 1
            assert res['password_reset_tokens'] == 1
            assert res['email_verification_tokens'] == 1

            # Verify database state after cleanup
            refreshes = (
                (await session.execute(select(RefreshToken))).scalars().all()
            )
            resets = (
                (await session.execute(select(PasswordResetToken)))
                .scalars()
                .all()
            )
            verifies = (
                (await session.execute(select(EmailVerificationToken)))
                .scalars()
                .all()
            )

            assert len(refreshes) == 1
            assert refreshes[0].jti == 'active-refresh'

            assert len(resets) == 1
            assert resets[0].token_hash == hash_token('active-reset')

            assert len(verifies) == 1
            assert verifies[0].token_hash == hash_token('active-verify')

    run_in_isolated_db(isolated_db_path, _run_cleanup)


@pytest.mark.asyncio
async def test_start_and_stop_token_cleanup_loop() -> None:
    """Test start_token_cleanup_loop and stop_token_cleanup_loop when Redis is not available."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.services.cleanup_service import (
        start_token_cleanup_loop,
        stop_token_cleanup_loop,
    )

    mock_session = AsyncMock()
    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    with (
        patch('app.services.cleanup_service.get_settings') as mock_settings,
        patch(
            'app.services.cleanup_service.get_redis_client',
            return_value=None,
        ),
        patch(
            'app.services.cleanup_service.get_session_factory',
            return_value=mock_factory,
        ),
        patch(
            'app.services.cleanup_service.cleanup_expired_tokens',
            new_callable=AsyncMock,
        ) as mock_cleanup,
    ):
        mock_settings.return_value.TOKEN_CLEANUP_INTERVAL_MINUTES = 60
        await start_token_cleanup_loop()
        await asyncio.sleep(0.05)
        await stop_token_cleanup_loop()

    assert mock_cleanup.called


@pytest.mark.asyncio
async def test_start_token_cleanup_loop_disabled() -> None:
    """Test start_token_cleanup_loop when interval is <= 0."""
    from unittest.mock import patch

    from app.services.cleanup_service import start_token_cleanup_loop

    with patch('app.services.cleanup_service.get_settings') as mock_settings:
        mock_settings.return_value.TOKEN_CLEANUP_INTERVAL_MINUTES = 0
        await start_token_cleanup_loop()


@pytest.mark.asyncio
async def test_token_cleanup_loop_with_redis_lock_acquired() -> None:
    """Test token cleanup loop when Redis lock is successfully acquired."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.services.cleanup_service import (
        start_token_cleanup_loop,
        stop_token_cleanup_loop,
    )

    mock_redis = MagicMock()
    mock_lock = MagicMock()
    mock_lock.acquire = AsyncMock(return_value=True)
    mock_lock.release = AsyncMock()
    mock_redis.lock.return_value = mock_lock

    mock_session = AsyncMock()
    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    with (
        patch('app.services.cleanup_service.get_settings') as mock_settings,
        patch(
            'app.services.cleanup_service.get_redis_client',
            return_value=mock_redis,
        ),
        patch(
            'app.services.cleanup_service.get_session_factory',
            return_value=mock_factory,
        ),
        patch(
            'app.services.cleanup_service.cleanup_expired_tokens',
            new_callable=AsyncMock,
        ) as mock_cleanup,
    ):
        mock_settings.return_value.TOKEN_CLEANUP_INTERVAL_MINUTES = 60
        await start_token_cleanup_loop()
        await asyncio.sleep(0.05)
        await stop_token_cleanup_loop()

    mock_redis.lock.assert_called_once_with('lock:token_cleanup', timeout=300)
    mock_lock.acquire.assert_called_once_with(blocking=False)
    mock_cleanup.assert_called_once()
    mock_lock.release.assert_called_once()


@pytest.mark.asyncio
async def test_token_cleanup_loop_with_redis_lock_not_acquired() -> None:
    """Test token cleanup loop when Redis lock cannot be acquired by replica."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.services.cleanup_service import (
        start_token_cleanup_loop,
        stop_token_cleanup_loop,
    )

    mock_redis = MagicMock()
    mock_lock = MagicMock()
    mock_lock.acquire = AsyncMock(return_value=False)
    mock_lock.release = AsyncMock()
    mock_redis.lock.return_value = mock_lock

    mock_factory = MagicMock()

    with (
        patch('app.services.cleanup_service.get_settings') as mock_settings,
        patch(
            'app.services.cleanup_service.get_redis_client',
            return_value=mock_redis,
        ),
        patch(
            'app.services.cleanup_service.get_session_factory',
            return_value=mock_factory,
        ),
        patch(
            'app.services.cleanup_service.cleanup_expired_tokens',
            new_callable=AsyncMock,
        ) as mock_cleanup,
    ):
        mock_settings.return_value.TOKEN_CLEANUP_INTERVAL_MINUTES = 60
        await start_token_cleanup_loop()
        await asyncio.sleep(0.05)
        await stop_token_cleanup_loop()

    mock_redis.lock.assert_called_once_with('lock:token_cleanup', timeout=300)
    mock_lock.acquire.assert_called_once_with(blocking=False)
    mock_cleanup.assert_not_called()
    mock_factory.assert_not_called()
    mock_lock.release.assert_not_called()
