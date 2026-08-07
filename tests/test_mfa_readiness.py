"""MFA readiness tests — #42."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import selectinload

from app.db.base import Base
from app.models.mfa_method import MfaMethod
from app.models.user import User

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_user_defaults_mfa_disabled(tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'mfa-defaults.db'}"

    async def scenario() -> None:
        engine = create_async_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            session_factory = async_sessionmaker(
                bind=engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
            async with session_factory() as session:
                user = User(
                    email='mfa-defaults@example.com',
                    hashed_password='not-a-real-hash',
                )
                session.add(user)
                await session.flush()
                assert user.mfa_enabled is False
                assert user.mfa_type is None
        finally:
            await engine.dispose()

    _run(scenario())


def test_mfa_method_can_be_created_and_associated(tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'mfa-method.db'}"

    async def scenario() -> None:
        engine = create_async_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            session_factory = async_sessionmaker(
                bind=engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
            async with session_factory() as session:
                user = User(
                    email='mfa-method@example.com',
                    hashed_password='not-a-real-hash',
                )
                session.add(user)
                await session.flush()

                method = MfaMethod(
                    user=user,
                    type='totp',
                    secret='JBSWY3DPEHPK3PXP',
                    data={
                        'issuer': 'Auth',
                        'account': 'mfa-method@example.com',
                    },
                    is_active=True,
                )
                session.add(method)
                await session.flush()

                stored = (
                    await session.execute(
                        select(MfaMethod).where(MfaMethod.user_id == user.id)
                    )
                ).scalar_one()
                assert stored.type == 'totp'
                assert stored.secret == 'JBSWY3DPEHPK3PXP'
                assert stored.data == {
                    'issuer': 'Auth',
                    'account': 'mfa-method@example.com',
                }
                assert stored.is_active is True
                assert stored.user is not None

                loaded = (
                    await session.execute(
                        select(User)
                        .options(selectinload(User.mfa_methods))
                        .where(User.id == user.id)
                    )
                ).scalar_one()
                assert [m.id for m in loaded.mfa_methods] == [stored.id]
        finally:
            await engine.dispose()

    _run(scenario())


def test_register_and_login_still_work(api_client) -> None:
    response = api_client.post(
        '/auth/register',
        json={'email': 'mfa-regression@example.com', 'password': 'T3st!Passw0rd'},
    )
    assert response.status_code == 201
    assert response.json()['mfa_enabled'] is False

    login = api_client.post(
        '/auth/login',
        json={'email': 'mfa-regression@example.com', 'password': 'T3st!Passw0rd'},
    )
    assert login.status_code == 200
    assert login.json()['access_token']


def test_migration_upgrade_and_downgrade(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / 'mfa_migration.db'
    monkeypatch.setenv('DATABASE_URL', f'sqlite+aiosqlite:///{db_path}')

    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        from alembic import command
        from alembic.config import Config

        cfg = Config(str(_REPO_ROOT / 'alembic.ini'))

        command.upgrade(cfg, 'head')
        with sqlite3.connect(db_path) as conn:
            users_columns = {
                row[1] for row in conn.execute('PRAGMA table_info(users)')
            }
            assert 'mfa_enabled' in users_columns
            assert 'mfa_type' in users_columns
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            assert 'mfa_methods' in tables

        command.downgrade(cfg, 'base')
        with sqlite3.connect(db_path) as conn:
            users_columns = {
                row[1] for row in conn.execute('PRAGMA table_info(users)')
            }
            assert 'mfa_enabled' not in users_columns
            assert 'mfa_type' not in users_columns
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            assert 'mfa_methods' not in tables
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize(
    'field,expected',
    [
        ('mfa_enabled', False),
        ('mfa_type', None),
    ],
)
def test_user_read_serialization_includes_mfa_defaults(
    api_client, field, expected
) -> None:
    response = api_client.post(
        '/auth/register',
        json={'email': 'mfa-serial@example.com', 'password': 'T3st!Passw0rd'},
    )
    assert response.status_code == 201
    assert response.json()[field] == expected
