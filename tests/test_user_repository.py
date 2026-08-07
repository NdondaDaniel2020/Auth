"""Tests for app/repositories/user_repository.py — #15 registro, #51 repos."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.role import Role
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


@pytest.mark.asyncio
async def test_get_by_id(isolated_session_factory) -> None:
    async with isolated_session_factory() as session:
        repository = UserRepository(session)
        user = await repository.create(
            email='by-id@example.com', hashed_password='hashed'
        )
        await session.commit()

        found = await repository.get_by_id(user.id)
        assert found is not None
        assert found.email == 'by-id@example.com'


@pytest.mark.asyncio
async def test_get_by_id_missing(isolated_session_factory) -> None:
    async with isolated_session_factory() as session:
        repository = UserRepository(session)
        assert (
            await repository.get_by_id('00000000-0000-0000-0000-000000000000')
            is None
        )


@pytest.mark.asyncio
async def test_list_users_orders_by_creation(isolated_session_factory) -> None:
    async with isolated_session_factory() as session:
        repository = UserRepository(session)
        for index in range(5):
            await repository.create(
                email=f'order-{index}@example.com', hashed_password='hashed'
            )
        await session.commit()

        page = await repository.list_users(offset=0, limit=20)
        assert len(page) == 5
        assert [user.email for user in page] == [
            f'order-{index}@example.com' for index in range(5)
        ]


@pytest.mark.asyncio
async def test_list_users_respects_limit_and_offset(isolated_session_factory) -> None:
    async with isolated_session_factory() as session:
        repository = UserRepository(session)
        for index in range(5):
            await repository.create(
                email=f'page-{index}@example.com', hashed_password='hashed'
            )
        await session.commit()

        page = await repository.list_users(offset=2, limit=2)
        assert [user.email for user in page] == [
            'page-2@example.com',
            'page-3@example.com',
        ]


@pytest.mark.asyncio
async def test_count_users(isolated_session_factory) -> None:
    async with isolated_session_factory() as session:
        repository = UserRepository(session)
        for index in range(4):
            await repository.create(
                email=f'count-{index}@example.com', hashed_password='hashed'
            )
        await session.commit()

        assert await repository.count_users() == 4


@pytest.mark.asyncio
async def test_duplicate_email_violates_unique_constraint(
    isolated_session_factory,
) -> None:
    async with isolated_session_factory() as session:
        repository = UserRepository(session)
        await repository.create(email='dup@example.com', hashed_password='a')

        with pytest.raises(IntegrityError):
            await repository.create(email='dup@example.com', hashed_password='b')


@pytest.mark.asyncio
async def test_set_active_status_updates_only_flag(isolated_session_factory) -> None:
    async with isolated_session_factory() as session:
        repository = UserRepository(session)
        user = await repository.create(
            email='flag@example.com', hashed_password='hashed'
        )
        await session.commit()

        await repository.set_active_status(user.id, is_active=False)
        await session.commit()

        updated = await repository.get_by_id(user.id)
        assert updated.is_active is False


@pytest.mark.asyncio
async def test_get_roles_by_ids_returns_existing_only(isolated_session_factory) -> None:
    async with isolated_session_factory() as session:
        session.add(Role(name='user'))
        await session.commit()
        existing = (
            await session.execute(select(Role).where(Role.name == 'user'))
        ).scalar_one()

        repository = UserRepository(session)
        roles = await repository.get_roles_by_ids(
            [existing.id, '00000000-0000-0000-0000-000000000000']
        )
        assert len(roles) == 1
        assert roles[0].id == existing.id


@pytest.mark.asyncio
async def test_get_roles_by_ids_empty_returns_empty_list(
    isolated_session_factory,
) -> None:
    async with isolated_session_factory() as session:
        roles = await UserRepository(session).get_roles_by_ids([])
        assert roles == []


@pytest.mark.asyncio
async def test_set_roles_replaces_association(isolated_session_factory) -> None:
    async with isolated_session_factory() as session:
        session.add(Role(name='user'))
        session.add(Role(name='editor'))
        await session.commit()
        roles = (await session.execute(select(Role))).scalars().all()

        repository = UserRepository(session)
        user = await repository.create(
            email='roles@example.com', hashed_password='hashed'
        )
        await session.commit()
        user = await repository.get_by_id(user.id)
        await repository.set_roles(user, roles)
        await session.commit()

        loaded = await repository.get_by_id(user.id)
        assert sorted(role.name for role in loaded.roles) == ['editor', 'user']
