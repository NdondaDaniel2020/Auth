"""Repository tests: password-reset tokens (hashing + single-use) — #51."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.password_reset_token import PasswordResetToken
from app.repositories.password_reset_repository import (
    PasswordResetTokenRepository,
)
from app.repositories.user_repository import UserRepository
from app.utils.tokens import hash_token


@pytest.mark.asyncio
async def test_create_stores_hash_not_plain_token(
    isolated_session_factory,
) -> None:
    async with isolated_session_factory() as session:
        user = await UserRepository(session).create(
            email='reset-repo@example.com', hashed_password='hashed'
        )
        await session.commit()

        await PasswordResetTokenRepository(session).create(
            user_id=user.id,
            token='raw-secret-token',
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
        await session.commit()

        row = (await session.execute(select(PasswordResetToken))).scalar_one()
        assert row.token_hash != 'raw-secret-token'
        assert row.token_hash == hash_token('raw-secret-token')


@pytest.mark.asyncio
async def test_get_by_token_uses_hash(isolated_session_factory) -> None:
    async with isolated_session_factory() as session:
        user = await UserRepository(session).create(
            email='lookup@example.com', hashed_password='hashed'
        )
        await session.commit()
        repo = PasswordResetTokenRepository(session)
        await repo.create(
            user_id=user.id,
            token='raw-secret-token',
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
        await session.commit()

        found = await repo.get_by_token('raw-secret-token')
        assert found is not None
        assert found.user_id == user.id


@pytest.mark.asyncio
async def test_get_by_token_missing(isolated_session_factory) -> None:
    async with isolated_session_factory() as session:
        repo = PasswordResetTokenRepository(session)
        assert await repo.get_by_token('unknown-token') is None


@pytest.mark.asyncio
async def test_mark_used_sets_flag_and_timestamp(
    isolated_session_factory,
) -> None:
    async with isolated_session_factory() as session:
        user = await UserRepository(session).create(
            email='markused@example.com', hashed_password='hashed'
        )
        await session.commit()
        repo = PasswordResetTokenRepository(session)
        record = await repo.create(
            user_id=user.id,
            token='single-use-token',
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
        await session.commit()

        used_at = datetime.now(UTC)
        await repo.mark_used(record, used_at=used_at)
        await session.commit()

        refreshed = (
            await session.execute(
                select(PasswordResetToken).where(
                    PasswordResetToken.id == record.id
                )
            )
        ).scalar_one()
        assert refreshed.used is True
        assert refreshed.used_at is not None
