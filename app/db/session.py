from __future__ import annotations

from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings


def _build_async_database_url(database_url: str) -> str:
    if database_url.startswith('postgresql://'):
        return database_url.replace(
            'postgresql://',
            'postgresql+asyncpg://',
            1,
        )

    if database_url.startswith('sqlite:///'):
        return database_url.replace(
            'sqlite:///',
            'sqlite+aiosqlite:///',
            1,
        )

    return database_url


@lru_cache(maxsize=1)
def get_engine():
    settings = get_settings()

    return create_async_engine(
        _build_async_database_url(settings.database_url),
        echo=settings.debug,
    )


@lru_cache(maxsize=1)
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    session_factory = get_session_factory()

    async with session_factory() as session:
        yield session
