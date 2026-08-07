"""Tests for app/repositories/user_repository.py — #15 registro de usuário."""

from __future__ import annotations

import pytest

from app.repositories.user_repository import UserRepository


@pytest.mark.asyncio
async def test_create_and_get_by_email(isolated_session_factory) -> None:
    async with isolated_session_factory() as session:
        repository = UserRepository(session)
        user = await repository.create(
            email='Test@Example.com',
            hashed_password='hashed-value',
            full_name='Test User',
        )
        await session.commit()

        found = await repository.get_by_email('test@example.com')
        assert found is not None
        assert found.id == user.id
        assert found.email == 'test@example.com'
        assert found.full_name == 'Test User'
        assert found.is_active is True
        assert found.is_verified is False


@pytest.mark.asyncio
async def test_get_by_email_missing(isolated_session_factory) -> None:
    async with isolated_session_factory() as session:
        repository = UserRepository(session)
        assert await repository.get_by_email('missing@example.com') is None
