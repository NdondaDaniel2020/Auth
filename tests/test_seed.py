"""Tests for app/db/init_db.py — seed logic.

Covers:
- First run creates all roles, permissions and admin user.
- Second run (idempotency) produces no duplicates and raises no errors.
- Role-permission assignments are correct for admin and user roles.
- Admin user is linked to the admin role.
"""
from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.db.base import Base
from app.db.init_db import (
    DEFAULT_PERMISSIONS,
    DEFAULT_ROLES,
    seed_roles_and_permissions,
)
from app.models.permission import Permission
from app.models.role import Role
from app.models.user import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.run(coro)


def _make_engine(tmp_path, name: str = "seed-test.db"):
    url = f"sqlite+aiosqlite:///{tmp_path / name}"
    return create_async_engine(url)


async def _setup_schema(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _count(session, model):
    result = await session.execute(select(func.count()).select_from(model))
    return result.scalar_one()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSeedFirstRun:
    """Verify that the first execution populates the database correctly."""

    def test_roles_are_created(self, tmp_path, monkeypatch) -> None:
        async def scenario():
            engine = _make_engine(tmp_path, "first-run-roles.db")
            try:
                await _setup_schema(engine)
                sf = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
                monkeypatch.setattr("app.db.init_db.get_session_factory", lambda: sf)

                await seed_roles_and_permissions()

                async with sf() as session:
                    result = await session.execute(select(Role.name).order_by(Role.name))
                    names = [r[0] for r in result.all()]

                assert names == ["admin", "user"]
            finally:
                await engine.dispose()

        _run(scenario())

    def test_permissions_are_created(self, tmp_path, monkeypatch) -> None:
        async def scenario():
            engine = _make_engine(tmp_path, "first-run-perms.db")
            try:
                await _setup_schema(engine)
                sf = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
                monkeypatch.setattr("app.db.init_db.get_session_factory", lambda: sf)

                await seed_roles_and_permissions()

                async with sf() as session:
                    count = await _count(session, Permission)

                expected = len(DEFAULT_PERMISSIONS)
                assert count == expected
            finally:
                await engine.dispose()

        _run(scenario())

    def test_admin_role_has_all_permissions(self, tmp_path, monkeypatch) -> None:
        async def scenario():
            engine = _make_engine(tmp_path, "first-run-admin-perms.db")
            try:
                await _setup_schema(engine)
                sf = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
                monkeypatch.setattr("app.db.init_db.get_session_factory", lambda: sf)

                await seed_roles_and_permissions()

                async with sf() as session:
                    result = await session.execute(
                        select(Role)
                        .options(selectinload(Role.permissions))
                        .where(Role.name == "admin")
                    )
                    admin_role = result.scalar_one()

                admin_perm_codes = {p.code for p in admin_role.permissions}
                expected_admin_codes = {
                    code
                    for code, _, role_names in DEFAULT_PERMISSIONS
                    if "admin" in role_names
                }
                assert expected_admin_codes == admin_perm_codes
            finally:
                await engine.dispose()

        _run(scenario())

    def test_user_role_has_read_permissions_only(self, tmp_path, monkeypatch) -> None:
        async def scenario():
            engine = _make_engine(tmp_path, "first-run-user-perms.db")
            try:
                await _setup_schema(engine)
                sf = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
                monkeypatch.setattr("app.db.init_db.get_session_factory", lambda: sf)

                await seed_roles_and_permissions()

                async with sf() as session:
                    result = await session.execute(
                        select(Role)
                        .options(selectinload(Role.permissions))
                        .where(Role.name == "user")
                    )
                    user_role = result.scalar_one()

                user_perm_codes = {p.code for p in user_role.permissions}
                expected_user_codes = {
                    code
                    for code, _, role_names in DEFAULT_PERMISSIONS
                    if "user" in role_names
                }
                assert user_perm_codes == expected_user_codes
                # Destructive permissions must NOT be in user role
                assert "users:delete" not in user_perm_codes
                assert "users:create" not in user_perm_codes
            finally:
                await engine.dispose()

        _run(scenario())

    def test_admin_user_is_created_and_linked(self, tmp_path, monkeypatch) -> None:
        async def scenario():
            engine = _make_engine(tmp_path, "first-run-admin-user.db")
            try:
                await _setup_schema(engine)
                sf = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
                monkeypatch.setattr("app.db.init_db.get_session_factory", lambda: sf)

                await seed_roles_and_permissions(admin_email="admin@test.com", admin_password="secret")

                async with sf() as session:
                    result = await session.execute(
                        select(User)
                        .options(selectinload(User.roles))
                        .where(User.email == "admin@test.com")
                    )
                    admin_user = result.scalar_one()

                assert admin_user.is_superuser is True
                assert admin_user.is_active is True
                role_names = {r.name for r in admin_user.roles}
                assert "admin" in role_names
            finally:
                await engine.dispose()

        _run(scenario())


class TestSeedIdempotency:
    """Verify that running the seed twice does not create duplicates."""

    def test_no_duplicate_roles(self, tmp_path, monkeypatch) -> None:
        async def scenario():
            engine = _make_engine(tmp_path, "idem-roles.db")
            try:
                await _setup_schema(engine)
                sf = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
                monkeypatch.setattr("app.db.init_db.get_session_factory", lambda: sf)

                await seed_roles_and_permissions()
                await seed_roles_and_permissions()  # second run

                async with sf() as session:
                    count = await _count(session, Role)

                assert count == len(DEFAULT_ROLES)
            finally:
                await engine.dispose()

        _run(scenario())

    def test_no_duplicate_permissions(self, tmp_path, monkeypatch) -> None:
        async def scenario():
            engine = _make_engine(tmp_path, "idem-perms.db")
            try:
                await _setup_schema(engine)
                sf = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
                monkeypatch.setattr("app.db.init_db.get_session_factory", lambda: sf)

                await seed_roles_and_permissions()
                await seed_roles_and_permissions()  # second run

                async with sf() as session:
                    count = await _count(session, Permission)

                assert count == len(DEFAULT_PERMISSIONS)
            finally:
                await engine.dispose()

        _run(scenario())

    def test_no_duplicate_admin_user(self, tmp_path, monkeypatch) -> None:
        async def scenario():
            engine = _make_engine(tmp_path, "idem-user.db")
            try:
                await _setup_schema(engine)
                sf = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
                monkeypatch.setattr("app.db.init_db.get_session_factory", lambda: sf)

                await seed_roles_and_permissions(admin_email="admin@idem.com")
                await seed_roles_and_permissions(admin_email="admin@idem.com")  # second run

                async with sf() as session:
                    count = await _count(session, User)

                assert count == 1
            finally:
                await engine.dispose()

        _run(scenario())

    def test_no_duplicate_role_permissions(self, tmp_path, monkeypatch) -> None:
        async def scenario():
            engine = _make_engine(tmp_path, "idem-role-perms.db")
            try:
                await _setup_schema(engine)
                sf = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
                monkeypatch.setattr("app.db.init_db.get_session_factory", lambda: sf)

                await seed_roles_and_permissions()
                await seed_roles_and_permissions()  # second run

                async with sf() as session:
                    result = await session.execute(
                        select(Role)
                        .options(selectinload(Role.permissions))
                        .where(Role.name == "admin")
                    )
                    admin_role = result.scalar_one()

                # Count unique permission codes — duplicates would inflate this
                codes = [p.code for p in admin_role.permissions]
                assert len(codes) == len(set(codes))
            finally:
                await engine.dispose()

        _run(scenario())
