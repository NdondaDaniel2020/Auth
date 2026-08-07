from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable

from passlib.context import CryptContext
from sqlalchemy import insert, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import selectinload

from app.db.session import get_engine, get_session_factory
from app.models.permission import Permission, role_permissions
from app.models.role import Role
from app.models.user import User, user_roles


logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


DEFAULT_ROLES: tuple[tuple[str, str], ...] = (
    ("admin", "Administrative role with full access"),
    ("user", "Default authenticated user role"),
)

DEFAULT_PERMISSIONS: tuple[tuple[str, str, list[str]], ...] = (
    ("users:create", "Create users",  ["admin"]),
    ("users:read",   "Read users",    ["admin", "user"]),
    ("users:update", "Update users",  ["admin"]),
    ("users:delete", "Delete users",  ["admin"]),
    ("roles:read",   "Read roles",    ["admin"]),
    ("roles:manage", "Manage roles",  ["admin"]),
)


async def _get_or_create_permission(session, code: str, description: str) -> Permission:
    """Return existing permission or create a new one (idempotent)."""
    result = await session.execute(
        select(Permission).where(Permission.code == code)
    )
    perm = result.scalar_one_or_none()
    if perm is None:
        perm = Permission(code=code, description=description)
        session.add(perm)
        logger.debug("Created permission: %s", code)
    return perm


async def _get_or_create_role(session, name: str, description: str) -> Role:
    """Return existing role or create a new one (idempotent)."""
    result = await session.execute(
        select(Role)
        .options(selectinload(Role.permissions))
        .where(Role.name == name)
    )
    role = result.scalar_one_or_none()
    if role is None:
        role = Role(name=name, description=description)
        session.add(role)
        logger.debug("Created role: %s", name)
    return role


async def _get_or_create_user(
    session,
    email: str,
    hashed_password: str,
    full_name: str,
    *,
    is_superuser: bool = False,
    is_active: bool = True,
) -> User:
    """Return existing user or create a new one (idempotent)."""
    result = await session.execute(
        select(User)
        .options(selectinload(User.roles))
        .where(User.email == email)
    )
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            email=email,
            hashed_password=hashed_password,
            full_name=full_name,
            is_superuser=is_superuser,
            is_active=is_active,
        )
        session.add(user)
        logger.debug("Created user: %s", email)
    return user


async def seed_roles_and_permissions(
    roles: Iterable[tuple[str, str]] = DEFAULT_ROLES,
    permissions: Iterable[tuple[str, str, list[str]]] = DEFAULT_PERMISSIONS,
    *,
    admin_email: str = "admin@example.com",
    admin_password: str = "admin123",
) -> None:
    # Materialise the iterables once so we can iterate them multiple times
    roles_list = list(roles)
    permissions_list = list(permissions)

    session_factory = get_session_factory()

    async with session_factory() as session:
        # 1. Seed roles — get or create by name
        role_map: dict[str, str] = {}  # name -> id

        for name, description in roles_list:
            result = await session.execute(
                select(Role.id).where(Role.name == name)
            )
            existing_id = result.scalar_one_or_none()
            if existing_id is None:
                role_obj = Role(name=name, description=description)
                session.add(role_obj)
                await session.flush()  # get generated id
                role_map[name] = role_obj.id
            else:
                role_map[name] = existing_id

        # 2. Seed permissions and assign to roles via direct INSERT into
        #    the association table — avoids ORM relationship lazy-loading.
        for code, description, assigned_roles in permissions_list:
            perm = await _get_or_create_permission(session, code, description)
            await session.flush()  # ensure perm.id exists

            for role_name in assigned_roles:
                role_id = role_map.get(role_name)
                if role_id is None:
                    continue
                # Use INSERT OR IGNORE (SQLite) / ON CONFLICT DO NOTHING to
                # keep this idempotent without querying the association table.
                stmt = (
                    sqlite_insert(role_permissions)
                    .values(role_id=role_id, permission_id=perm.id)
                    .on_conflict_do_nothing()
                )
                await session.execute(stmt)

        await session.commit()
        logger.info(
            "Seeded %d role(s) and %d permission(s).",
            len(role_map),
            len(permissions_list),
        )

    # 3. Seed admin user in a fresh session (roles already committed above)
    async with session_factory() as session:
        admin_role_id_result = await session.execute(
            select(Role.id).where(Role.name == "admin")
        )
        admin_role_id = admin_role_id_result.scalar_one_or_none()

        if admin_role_id is None:
            logger.warning("Admin role not found; skipping admin user seed.")
            return

        result = await session.execute(
            select(User).where(User.email == admin_email)
        )
        admin_user = result.scalar_one_or_none()

        if admin_user is None:
            admin_user = User(
                email=admin_email,
                hashed_password=get_password_hash(admin_password),
                full_name="Administrator",
                is_superuser=True,
                is_active=True,
            )
            session.add(admin_user)
            await session.flush()

        # Insert into user_roles with ON CONFLICT DO NOTHING (idempotent)
        stmt = (
            sqlite_insert(user_roles)
            .values(user_id=admin_user.id, role_id=admin_role_id)
            .on_conflict_do_nothing()
        )
        await session.execute(stmt)
        await session.commit()
        logger.info("Admin user seeded: %s", admin_email)


async def init_db() -> None:
    from app.core.config import get_settings

    settings = get_settings()
    engine = get_engine()

    async with engine.begin() as connection:
        from app.db.base import Base  # noqa: PLC0415

        await connection.run_sync(Base.metadata.create_all)

    if settings.RUN_SEED_ON_STARTUP:
        logger.info("RUN_SEED_ON_STARTUP=true — running seed…")
        await seed_roles_and_permissions(
            admin_email=settings.ADMIN_EMAIL,
            admin_password=settings.ADMIN_PASSWORD,
        )
    else:
        logger.debug("RUN_SEED_ON_STARTUP=false — skipping seed.")


async def _main() -> None:
    from app.core.config import EnvironmentSettings, get_settings
    from app.db.session import get_engine

    logging.basicConfig(level=logging.INFO)
    settings = get_settings()

    logger.info("Running seed standalone (env=%s)…", EnvironmentSettings().ENVIRONMENT)
    await seed_roles_and_permissions(
        admin_email=settings.ADMIN_EMAIL,
        admin_password=settings.ADMIN_PASSWORD,
    )
    logger.info("Seed complete.")

    engine = get_engine()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
