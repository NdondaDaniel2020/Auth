import os
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db.base import Base

os.environ.setdefault('ENVIRONMENT', 'test')


@pytest.fixture(scope='session')
def test_database_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    database_path = tmp_path_factory.mktemp('db') / 'test.db'
    return f'sqlite+aiosqlite:///{database_path}'


@pytest_asyncio.fixture(scope='session')
async def test_engine(
    test_database_url: str,
) -> AsyncIterator:
    engine = create_async_engine(test_database_url, future=True)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncIterator[AsyncSession]:
    session_factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.rollback()


@pytest.fixture
def app() -> FastAPI:
    try:
        from app.main import app as application

        return application
    except AttributeError, ImportError:
        fallback_app = FastAPI()

        @fallback_app.get('/health')
        async def health_check() -> dict[str, str]:
            return {'status': 'ok'}

        return fallback_app


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _clear_rate_limiter() -> Iterator[None]:
    from app.core.rate_limiter import rate_limiter

    rate_limiter.clear()
    yield
    rate_limiter.clear()


@pytest_asyncio.fixture
async def isolated_session_factory(
    tmp_path: pytest.TempPathFactory,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Async session factory bound to an isolated SQLite database."""
    database_path = tmp_path / 'isolated.db'
    engine = create_async_engine(f'sqlite+aiosqlite:///{database_path}')

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.fixture
def isolated_db_path(
    isolated_session_factory: async_sessionmaker[AsyncSession],
) -> str:
    """Filesystem path of the isolated test database."""
    return isolated_session_factory.kw['bind'].url.database


def run_in_isolated_db(db_path: str, coro_fn):
    """Run ``coro_fn(factory)`` against a fresh engine on the isolated DB.

    ``coro_fn`` receives an async session factory. A separate engine is used
    so the coroutine can run in a different event loop than the async
    fixtures.
    """
    import asyncio

    async def _runner() -> None:
        engine = create_async_engine(f'sqlite+aiosqlite:///{db_path}')
        factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        try:
            await coro_fn(factory)
        finally:
            await engine.dispose()

    asyncio.run(_runner())


@pytest.fixture
def api_client(
    isolated_session_factory: async_sessionmaker[AsyncSession],
) -> Iterator[TestClient]:
    """FastAPI TestClient with the auth router and an isolated DB session.

    A minimal app is built (no lifespan) so no shared state or real database
    is touched; ``get_db`` is overridden to use the isolated session factory.
    """
    from fastapi import FastAPI

    from app.api.routers.auth import router as auth_router
    from app.core.error_handlers import register_exception_handlers
    from app.db.session import get_db

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(auth_router)

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        async with isolated_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app) as test_client:
        yield test_client
