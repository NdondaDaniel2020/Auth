"""Business-rule tests for auth_service — #51 (no HTTP layer)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.exceptions import (
    InvalidOrExpiredTokenError,
    InvalidRefreshTokenError,
    TokenAlreadyUsedError,
)
from app.core.security import (
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from app.models.password_reset_token import PasswordResetToken
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.repositories.password_reset_repository import (
    PasswordResetTokenRepository,
)
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.services import auth_service
from app.utils.datetimes import utcnow

PASSWORD = 'T3st!Passw0rd'


async def _make_user(session, *, email: str) -> User:
    repository = UserRepository(session)
    return await repository.create(
        email=email,
        hashed_password=hash_password(PASSWORD),
    )


async def _login(session, user: User) -> dict[str, str]:
    tokens = await auth_service.create_token_pair(session, user)
    return {
        'access_token': tokens.access_token,
        'refresh_token': tokens.refresh_token,
    }


@pytest.mark.asyncio
async def test_create_token_pair_persists_refresh_token(
    isolated_session_factory,
) -> None:
    async with isolated_session_factory() as session:
        user = await _make_user(session, email='pair@example.com')

        tokens = await auth_service.create_token_pair(session, user)

        payload = decode_refresh_token(tokens.refresh_token)
        jti = payload['jti']
        record = await RefreshTokenRepository(session).get_by_jti(jti)
        assert record is not None
        assert record.user_id == user.id
        assert record.revoked is False


@pytest.mark.asyncio
async def test_refresh_tokens_rotates(isolated_session_factory) -> None:
    async with isolated_session_factory() as session:
        user = await _make_user(session, email='rotate@example.com')
        tokens = await _login(session, user)

        new_tokens = await auth_service.refresh_tokens(
            session, tokens['refresh_token']
        )
        assert new_tokens.access_token
        assert new_tokens.refresh_token != tokens['refresh_token']

        old_jti = decode_refresh_token(tokens['refresh_token'])['jti']
        old_record = await RefreshTokenRepository(session).get_by_jti(old_jti)
        assert old_record.revoked is True


@pytest.mark.asyncio
async def test_refresh_tokens_rejects_revoked_and_revokes_all(
    isolated_session_factory,
) -> None:
    async with isolated_session_factory() as session:
        user = await _make_user(session, email='contain@example.com')
        first = await _login(session, user)
        second = await _login(session, user)

        first_jti = decode_refresh_token(first['refresh_token'])['jti']
        await RefreshTokenRepository(session).revoke(first_jti)
        first_record = await RefreshTokenRepository(session).get_by_jti(
            first_jti
        )
        if first_record:
            first_record.revoked_at = utcnow() - timedelta(seconds=30)
        await session.commit()

        with pytest.raises(InvalidRefreshTokenError):
            await auth_service.refresh_tokens(session, first['refresh_token'])

        await session.commit()
        second_jti = decode_refresh_token(second['refresh_token'])['jti']
        second_record = await RefreshTokenRepository(session).get_by_jti(
            second_jti
        )
        assert second_record.revoked is True


@pytest.mark.asyncio
async def test_refresh_tokens_rejects_unknown_token(
    isolated_session_factory,
) -> None:
    async with isolated_session_factory() as session:
        unknown = create_refresh_token({'sub': 'ghost', 'jti': 'ghost-jti'})
        with pytest.raises(InvalidRefreshTokenError):
            await auth_service.refresh_tokens(session, unknown)


@pytest.mark.asyncio
async def test_logout_revokes_single_token(isolated_session_factory) -> None:
    async with isolated_session_factory() as session:
        user = await _make_user(session, email='logout@example.com')
        tokens = await _login(session, user)

        await auth_service.logout(session, tokens['refresh_token'])

        jti = decode_refresh_token(tokens['refresh_token'])['jti']
        record = await RefreshTokenRepository(session).get_by_jti(jti)
        assert record.revoked is True


@pytest.mark.asyncio
async def test_logout_keeps_other_sessions(isolated_session_factory) -> None:
    async with isolated_session_factory() as session:
        user = await _make_user(session, email='multi@example.com')
        first = await _login(session, user)
        second = await _login(session, user)

        await auth_service.logout(session, first['refresh_token'])

        second_jti = decode_refresh_token(second['refresh_token'])['jti']
        record = await RefreshTokenRepository(session).get_by_jti(second_jti)
        assert record.revoked is False


@pytest.mark.asyncio
async def test_reset_password_changes_password_and_revokes_sessions(
    isolated_session_factory,
) -> None:
    async with isolated_session_factory() as session:
        user = await _make_user(session, email='reset@example.com')
        await _login(session, user)
        await _login(session, user)

        reset_repo = PasswordResetTokenRepository(session)
        await reset_repo.create(
            user_id=user.id,
            token='valid-reset-token',
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
        await session.commit()

        await auth_service.reset_password(
            session, 'valid-reset-token', 'NewPass456!'
        )

        reloaded = await UserRepository(session).get_by_id(user.id)
        assert verify_password('NewPass456!', reloaded.hashed_password) is True

        rows = (await session.execute(select(RefreshToken))).scalars().all()
        assert all(row.revoked for row in rows)


@pytest.mark.asyncio
async def test_reset_password_rejects_used_token(
    isolated_session_factory,
) -> None:
    async with isolated_session_factory() as session:
        user = await _make_user(session, email='single@example.com')
        reset_repo = PasswordResetTokenRepository(session)
        record = await reset_repo.create(
            user_id=user.id,
            token='one-shot-token',
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
        await reset_repo.mark_used(record, used_at=datetime.now(UTC))
        await session.commit()

        with pytest.raises(TokenAlreadyUsedError):
            await auth_service.reset_password(
                session, 'one-shot-token', 'NewPass456!'
            )


@pytest.mark.asyncio
async def test_reset_password_rejects_expired_token(
    isolated_session_factory,
) -> None:
    async with isolated_session_factory() as session:
        user = await _make_user(session, email='expired@example.com')
        await PasswordResetTokenRepository(session).create(
            user_id=user.id,
            token='expired-token',
            expires_at=datetime.now(UTC) - timedelta(minutes=5),
        )
        await session.commit()

        with pytest.raises(InvalidOrExpiredTokenError):
            await auth_service.reset_password(
                session, 'expired-token', 'NewPass456!'
            )


@pytest.mark.asyncio
async def test_verify_email_marks_user_verified(
    isolated_session_factory,
) -> None:
    async with isolated_session_factory() as session:
        from app.repositories.email_verification_repository import (
            EmailVerificationTokenRepository,
        )

        user = await _make_user(session, email='verify@example.com')
        await EmailVerificationTokenRepository(session).create(
            user_id=user.id,
            token='verify-token',
            expires_at=datetime.now(UTC) + timedelta(minutes=30),
        )
        await session.commit()

        await auth_service.verify_email(session, 'verify-token')

        reloaded = await UserRepository(session).get_by_id(user.id)
        assert reloaded.is_verified is True


@pytest.mark.asyncio
async def test_request_password_reset_creates_token(
    isolated_session_factory,
) -> None:
    async with isolated_session_factory() as session:
        user = await _make_user(session, email='request@example.com')

        await auth_service.request_password_reset(
            session, 'request@example.com'
        )

        rows = (
            (
                await session.execute(
                    select(PasswordResetToken).where(
                        PasswordResetToken.user_id == user.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1


@pytest.mark.asyncio
async def test_request_password_reset_for_unknown_email_is_noop(
    isolated_session_factory,
) -> None:
    async with isolated_session_factory() as session:
        await auth_service.request_password_reset(session, 'ghost@example.com')

        rows = (await session.execute(select(PasswordResetToken))).all()
        assert rows == []


@pytest.mark.asyncio
async def test_request_password_reset_bg_uses_isolated_session(
    isolated_session_factory,
) -> None:
    from unittest.mock import patch

    async with isolated_session_factory() as session:
        user = await _make_user(session, email='bg_reset@example.com')
        await session.commit()

    with patch(
        'app.services.auth_service.get_session_factory',
        return_value=isolated_session_factory,
    ):
        await auth_service.request_password_reset_bg('bg_reset@example.com')

    async with isolated_session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(PasswordResetToken).where(
                        PasswordResetToken.user_id == user.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1


@pytest.mark.asyncio
async def test_resend_verification_email_bg_uses_isolated_session(
    isolated_session_factory,
) -> None:
    from unittest.mock import patch

    from app.models.email_verification_token import EmailVerificationToken

    async with isolated_session_factory() as session:
        user = await _make_user(session, email='bg_verify@example.com')
        await session.commit()

    with patch(
        'app.services.auth_service.get_session_factory',
        return_value=isolated_session_factory,
    ):
        await auth_service.resend_verification_email_bg('bg_verify@example.com')

    async with isolated_session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(EmailVerificationToken).where(
                        EmailVerificationToken.user_id == user.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1



