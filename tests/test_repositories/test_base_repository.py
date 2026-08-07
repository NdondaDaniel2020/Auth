"""Tests for the generic BaseRepository CRUD — #51."""

from __future__ import annotations

import pytest

from app.models.user import User
from app.repositories.base import BaseRepository
from app.repositories.user_repository import UserRepository


@pytest.mark.asyncio
async def test_create_and_get_by_id(isolated_session_factory) -> None:
    async with isolated_session_factory() as session:
        repo = BaseRepository(session, User)
        created = await repo.create(
            {'email': 'base@example.com', 'hashed_password': 'hash'}
        )

        fetched = await repo.get(created.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.email == 'base@example.com'


@pytest.mark.asyncio
async def test_get_missing_returns_none(isolated_session_factory) -> None:
    async with isolated_session_factory() as session:
        repo = BaseRepository(session, User)
        assert await repo.get('00000000-0000-0000-0000-000000000000') is None


@pytest.mark.asyncio
async def test_list_returns_all_rows(isolated_session_factory) -> None:
    async with isolated_session_factory() as session:
        repo = BaseRepository(session, User)
        for index in range(3):
            await repo.create(
                {'email': f'list-{index}@example.com', 'hashed_password': 'hash'}
            )

        rows = await repo.list(offset=0, limit=10)
        assert len(rows) == 3


@pytest.mark.asyncio
async def test_update_changes_only_given_fields(isolated_session_factory) -> None:
    async with isolated_session_factory() as session:
        repo = BaseRepository(session, User)
        created = await repo.create(
            {'email': 'upd@example.com', 'hashed_password': 'old-hash'}
        )

        updated = await repo.update(created, {'full_name': 'Renamed'})
        assert updated.full_name == 'Renamed'
        assert updated.email == 'upd@example.com'
        assert updated.hashed_password == 'old-hash'


@pytest.mark.asyncio
async def test_delete_removes_row(isolated_session_factory) -> None:
    async with isolated_session_factory() as session:
        repo = BaseRepository(session, User)
        created = await repo.create(
            {'email': 'del@example.com', 'hashed_password': 'hash'}
        )

        await repo.delete(created)

        assert await repo.get(created.id) is None


@pytest.mark.asyncio
async def test_subclass_binds_its_model(isolated_session_factory) -> None:
    async with isolated_session_factory() as session:
        repo = UserRepository(session)
        assert repo.model is User
