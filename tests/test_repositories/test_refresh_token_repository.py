"""Repository tests: refresh tokens (revocation/rotation backbone) — #51."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.refresh_token import RefreshToken
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository


async def _make_user(session, email: str) -> str:
    user = await UserRepository(session).create(
        email=email, hashed_password='hashed-value'
    )
    await session.commit()
    return user.id


async def _make_token(session, user_id: str, *, jti: str) -> RefreshToken:
    return await RefreshTokenRepository(session).create(
        jti=jti,
        user_id=user_id,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )


@pytest.mark.asyncio
async def test_create_and_get_by_jti(isolated_session_factory) -> None:
    async with isolated_session_factory() as session:
        user_id = await _make_user(session, 'tokens@example.com')
        await _make_token(session, user_id, jti='jti-1')
        await session.commit()

        found = await RefreshTokenRepository(session).get_by_jti('jti-1')
        assert found is not None
        assert found.user_id == user_id
        assert found.revoked is False


@pytest.mark.asyncio
async def test_get_by_jti_missing(isolated_session_factory) -> None:
    async with isolated_session_factory() as session:
        assert (
            await RefreshTokenRepository(session).get_by_jti('never-created')
            is None
        )


@pytest.mark.asyncio
async def test_revoke_sets_revoked_flag(isolated_session_factory) -> None:
    async with isolated_session_factory() as session:
        user_id = await _make_user(session, 'revoke@example.com')
        await _make_token(session, user_id, jti='jti-revoke')
        await session.commit()

        repo = RefreshTokenRepository(session)
        await repo.revoke('jti-revoke')
        await session.commit()

        record = (await session.execute(select(RefreshToken))).scalar_one()
        assert record.revoked is True
        assert record.revoked_at is not None


@pytest.mark.asyncio
async def test_revoke_is_idempotent(isolated_session_factory) -> None:
    async with isolated_session_factory() as session:
        user_id = await _make_user(session, 'idem@example.com')
        await _make_token(session, user_id, jti='jti-idem')
        await session.commit()

        repo = RefreshTokenRepository(session)
        await repo.revoke('jti-idem')
        await repo.revoke('jti-idem')  # second call is a no-op
        await session.commit()

        record = (await session.execute(select(RefreshToken))).scalar_one()
        assert record.revoked is True


@pytest.mark.asyncio
async def test_revoke_all_for_user_revokes_every_active_token(
    isolated_session_factory,
) -> None:
    async with isolated_session_factory() as session:
        user_id = await _make_user(session, 'total@example.com')
        repo = RefreshTokenRepository(session)
        for jti in ('jti-a', 'jti-b', 'jti-c'):
            await _make_token(session, user_id, jti=jti)
        await session.commit()

        await repo.revoke_all_for_user(user_id)
        await session.commit()

        rows = (await session.execute(select(RefreshToken))).scalars().all()
        assert len(rows) == 3
        assert all(row.revoked for row in rows)


@pytest.mark.asyncio
async def test_revoke_all_for_user_only_affects_that_user(
    isolated_session_factory,
) -> None:
    async with isolated_session_factory() as session:
        first = await _make_user(session, 'first@example.com')
        second = await _make_user(session, 'second@example.com')
        repo = RefreshTokenRepository(session)
        await _make_token(session, first, jti='jti-first')
        await _make_token(session, second, jti='jti-second')
        await session.commit()

        await repo.revoke_all_for_user(first)
        await session.commit()

        first_record = await repo.get_by_jti('jti-first')
        second_record = await repo.get_by_jti('jti-second')
        assert first_record.revoked is True
        assert second_record.revoked is False
