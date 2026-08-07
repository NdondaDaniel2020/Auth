from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import selectinload

from app.db.base import Base
from app.models.permission import Permission
from app.models.role import Role


def _run(coro):
    return asyncio.run(coro)


def test_create_and_associate_permission(tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'permission-test.db'}"

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
                # Create and persist a role and a permission
                role = Role(name='admin', description='Admin role')
                permission = Permission(code='users:write', description='Write users')
                
                # Associate
                role.permissions.append(permission)
                
                db_session.add(role)
                db_session.add(permission)
                await db_session.commit()
                await db_session.refresh(role)
                await db_session.refresh(permission)

                assert permission.id is not None
                assert permission.code == 'users:write'
                assert permission.description == 'Write users'
                assert permission.created_at is not None
                assert permission.updated_at is not None

                # Fetch from db to verify association
                result = await db_session.execute(
                    select(Role).options(selectinload(Role.permissions)).where(Role.name == 'admin')
                )
                persisted_role = result.scalar_one()
                
                assert len(persisted_role.permissions) == 1
                assert persisted_role.permissions[0].code == 'users:write'
                assert persisted_role.permissions[0].id == permission.id
        finally:
            await engine.dispose()

    _run(scenario())
