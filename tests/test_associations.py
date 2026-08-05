from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.user import User
from app.models.role import Role
from app.models.permission import Permission


def _run(coro):
    return asyncio.run(coro)


def test_user_roles_permissions_associations(tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'associations-test.db'}"

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
                # Create user
                user = User(email="test@example.com", hashed_password="hashed")
                
                # Create roles
                role1 = Role(name="manager", description="Manager role")
                role2 = Role(name="auditor", description="Auditor role")
                
                # Create permissions
                perm1 = Permission(code="reports:read", description="Read reports")
                perm2 = Permission(code="reports:write", description="Write reports")
                perm3 = Permission(code="logs:read", description="Read logs")
                
                # Associate multiple permissions to roles
                role1.permissions.extend([perm1, perm2])
                role2.permissions.append(perm3)
                
                # Associate multiple roles to user
                user.roles.extend([role1, role2])
                
                db_session.add_all([user, role1, role2, perm1, perm2, perm3])
                await db_session.commit()
                
            # Verify associations (Consulta reversa: user -> roles -> permissions)
            async with session_factory() as db_session:
                result = await db_session.execute(
                    select(User)
                    .options(selectinload(User.roles).selectinload(Role.permissions))
                    .where(User.email == "test@example.com")
                )
                persisted_user = result.scalar_one()
                
                assert len(persisted_user.roles) == 2
                
                role_names = {r.name for r in persisted_user.roles}
                assert "manager" in role_names
                assert "auditor" in role_names
                
                manager_role = next(r for r in persisted_user.roles if r.name == "manager")
                assert len(manager_role.permissions) == 2
                
                manager_perm_codes = {p.code for p in manager_role.permissions}
                assert "reports:read" in manager_perm_codes
                assert "reports:write" in manager_perm_codes
                
                auditor_role = next(r for r in persisted_user.roles if r.name == "auditor")
                assert len(auditor_role.permissions) == 1
                assert auditor_role.permissions[0].code == "logs:read"
                
        finally:
            await engine.dispose()

    _run(scenario())
