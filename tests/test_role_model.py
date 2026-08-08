from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db.base import Base
from app.db.init_db import DEFAULT_ROLES, seed_roles_and_permissions
from app.models.role import Role


def _run(coro):
    return asyncio.run(coro)


def test_create_and_persist_role(tmp_path) -> None:
    database_url = f'sqlite+aiosqlite:///{tmp_path / "role-test.db"}'

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

            async with session_factory() as db_session:
                role = Role(name='tester', description='Test role')
                db_session.add(role)
                await db_session.commit()
                await db_session.refresh(role)

                assert role.id is not None
                assert role.name == 'tester'
                assert role.description == 'Test role'
                assert role.created_at is not None
                assert role.updated_at is not None

                result = await db_session.execute(
                    select(Role).where(Role.name == 'tester')
                )
                persisted_role = result.scalar_one()
                assert persisted_role.id == role.id
        finally:
            await engine.dispose()

    _run(scenario())


def test_seed_default_roles(tmp_path, monkeypatch) -> None:
    database_url = f'sqlite+aiosqlite:///{tmp_path / "seed-test.db"}'

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

            monkeypatch.setattr(
                'app.db.init_db.get_session_factory', lambda: session_factory
            )

            await seed_roles_and_permissions(
                roles=DEFAULT_ROLES, permissions=[]
            )

            async with session_factory() as session:
                result = await session.execute(
                    select(Role.name).order_by(Role.name)
                )
                names = [row[0] for row in result.all()]

            assert names == ['admin', 'user']
        finally:
            await engine.dispose()

    _run(scenario())
