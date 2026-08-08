"""Business-rule tests for user_service — #51 (no HTTP layer)."""

from __future__ import annotations

import pytest

from app.core.exceptions import (
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    RoleNotFoundError,
    SelfRoleRemovalError,
    UserNotFoundError,
)
from app.core.security import hash_password, verify_password
from app.models.role import Role
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate
from app.services import user_service

PASSWORD = 'T3st!Passw0rd'


async def _make_user(
    session, *, email: str, role_names: list[str] | None = None
) -> User:
    repository = UserRepository(session)
    user = await repository.create(
        email=email, hashed_password=hash_password(PASSWORD)
    )
    await session.commit()
    if role_names:
        user = await repository.get_by_id(user.id)
        for name in role_names:
            role = Role(name=name)
            session.add(role)
            user.roles.append(role)
        await session.commit()
    return user


@pytest.mark.asyncio
async def test_register_user_creates_account(isolated_session_factory) -> None:
    async with isolated_session_factory() as session:
        user = await user_service.register_user(
            session,
            UserCreate(email='register@example.com', password=PASSWORD),
        )

        assert user.email == 'register@example.com'
        stored = await UserRepository(session).get_by_email(
            'register@example.com'
        )
        assert stored is not None
        assert stored.hashed_password != PASSWORD
        assert verify_password(PASSWORD, stored.hashed_password) is True


@pytest.mark.asyncio
async def test_register_user_rejects_duplicate_email(
    isolated_session_factory,
) -> None:
    async with isolated_session_factory() as session:
        await _make_user(session, email='dup@example.com')

        with pytest.raises(EmailAlreadyExistsError):
            await user_service.register_user(
                session,
                UserCreate(email='dup@example.com', password=PASSWORD),
            )


@pytest.mark.asyncio
async def test_register_user_normalizes_email_case(
    isolated_session_factory,
) -> None:
    async with isolated_session_factory() as session:
        await user_service.register_user(
            session, UserCreate(email='MiXeD@Example.com', password=PASSWORD)
        )

        stored = await UserRepository(session).get_by_email(
            'mixed@example.com'
        )
        assert stored is not None


@pytest.mark.asyncio
async def test_authenticate_user_success(isolated_session_factory) -> None:
    async with isolated_session_factory() as session:
        user = await _make_user(session, email='login@example.com')

        authenticated = await user_service.authenticate_user(
            session, 'login@example.com', PASSWORD
        )
        assert authenticated.id == user.id


@pytest.mark.asyncio
async def test_authenticate_user_wrong_password(
    isolated_session_factory,
) -> None:
    async with isolated_session_factory() as session:
        await _make_user(session, email='wrong@example.com')

        with pytest.raises(InvalidCredentialsError):
            await user_service.authenticate_user(
                session, 'wrong@example.com', 'not-the-password'
            )


@pytest.mark.asyncio
async def test_authenticate_user_inactive(isolated_session_factory) -> None:
    async with isolated_session_factory() as session:
        user = await _make_user(session, email='inactive@example.com')
        await UserRepository(session).set_active_status(
            user.id, is_active=False
        )
        await session.commit()

        with pytest.raises(InvalidCredentialsError):
            await user_service.authenticate_user(
                session, 'inactive@example.com', PASSWORD
            )


@pytest.mark.asyncio
async def test_authenticate_user_unknown_email(
    isolated_session_factory,
) -> None:
    async with isolated_session_factory() as session:
        with pytest.raises(InvalidCredentialsError):
            await user_service.authenticate_user(
                session, 'ghost@example.com', PASSWORD
            )


@pytest.mark.asyncio
async def test_update_user_roles_applies_association(
    isolated_session_factory,
) -> None:
    async with isolated_session_factory() as session:
        actor = await _make_user(session, email='admin@example.com')
        target = await _make_user(session, email='target@example.com')
        role = Role(name='editor')
        session.add(role)
        await session.commit()

        result = await user_service.update_user_roles(
            session,
            user_id=target.id,
            role_ids=[role.id],
            actor=actor,
        )
        assert result.id == target.id

        stored = await UserRepository(session).get_by_id(target.id)
        assert [r.name for r in stored.roles] == ['editor']


@pytest.mark.asyncio
async def test_update_user_roles_nonexistent_role(
    isolated_session_factory,
) -> None:
    async with isolated_session_factory() as session:
        actor = await _make_user(session, email='admin@example.com')
        target = await _make_user(session, email='target@example.com')

        with pytest.raises(RoleNotFoundError):
            await user_service.update_user_roles(
                session,
                user_id=target.id,
                role_ids=['00000000-0000-0000-0000-000000000000'],
                actor=actor,
            )


@pytest.mark.asyncio
async def test_update_user_roles_nonexistent_user(
    isolated_session_factory,
) -> None:
    async with isolated_session_factory() as session:
        actor = await _make_user(session, email='admin@example.com')
        role = Role(name='editor')
        session.add(role)
        await session.commit()

        with pytest.raises(UserNotFoundError):
            await user_service.update_user_roles(
                session,
                user_id='00000000-0000-0000-0000-000000000000',
                role_ids=[role.id],
                actor=actor,
            )


@pytest.mark.asyncio
async def test_actor_cannot_remove_own_admin_role(
    isolated_session_factory,
) -> None:
    async with isolated_session_factory() as session:
        actor = await _make_user(
            session, email='admin@example.com', role_names=['admin']
        )

        with pytest.raises(SelfRoleRemovalError):
            await user_service.update_user_roles(
                session,
                user_id=actor.id,
                role_ids=[],
                actor=actor,
            )


@pytest.mark.asyncio
async def test_deactivate_user_marks_inactive(
    isolated_session_factory,
) -> None:
    async with isolated_session_factory() as session:
        actor = await _make_user(session, email='admin@example.com')
        target = await _make_user(session, email='target@example.com')

        result = await user_service.deactivate_user(
            session, user_id=target.id, actor=actor
        )
        assert result.is_active is False

        stored = await UserRepository(session).get_by_id(target.id)
        assert stored.is_active is False


@pytest.mark.asyncio
async def test_activate_user_marks_active(isolated_session_factory) -> None:
    async with isolated_session_factory() as session:
        actor = await _make_user(session, email='admin@example.com')
        target = await _make_user(session, email='target@example.com')
        await UserRepository(session).set_active_status(
            target.id, is_active=False
        )
        await session.commit()

        result = await user_service.activate_user(
            session, user_id=target.id, actor=actor
        )
        assert result.is_active is True


@pytest.mark.asyncio
async def test_list_users_builds_paginated_envelope(
    isolated_session_factory,
) -> None:
    async with isolated_session_factory() as session:
        for index in range(3):
            await _make_user(session, email=f'page-{index}@example.com')

        page = await user_service.list_users(session, page=1, page_size=2)
        assert page.total == 3
        assert page.page == 1
        assert page.page_size == 2
        assert len(page.items) == 2
        assert all(not hasattr(item, 'hashed_password') for item in page.items)
