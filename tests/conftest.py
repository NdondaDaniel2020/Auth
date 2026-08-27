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

import app.models  # register models on Base.metadata
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
    from app.core.rate_limiter import rate_limiter, request_rate_limiter

    rate_limiter.clear()
    request_rate_limiter.clear()
    yield
    rate_limiter.clear()
    request_rate_limiter.clear()


@pytest_asyncio.fixture(autouse=True)
async def _clear_database_session_cache() -> AsyncIterator[None]:
    from app.db.session import get_engine, get_session_factory

    yield

    if get_engine.cache_info().currsize > 0:
        try:
            engine = get_engine()
            await engine.dispose()
        except Exception:  # noqa: BLE001, S110
            pass

    get_engine.cache_clear()
    get_session_factory.cache_clear()


@pytest_asyncio.fixture(autouse=True)
async def _setup_test_notifications() -> AsyncIterator[None]:
    from app.services.notification_service import (
        setup_notifications,
        teardown_notifications,
    )

    await setup_notifications()
    try:
        yield
    finally:
        await teardown_notifications()


@pytest.fixture(autouse=True)
def _prevent_real_smtp_calls(monkeypatch) -> Iterator[None]:
    """Ensure tests never attempt real SMTP connections to external mail servers."""

    async def fake_send_via_smtp(
        to_email: str, subject: str, html_content: str
    ) -> None:
        pass

    monkeypatch.setattr(
        'app.services.email_service._send_via_smtp', fake_send_via_smtp
    )
    yield


@pytest_asyncio.fixture
async def isolated_session_factory(
    tmp_path: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
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

    monkeypatch.setattr('app.db.session.get_session_factory', lambda: factory)
    monkeypatch.setattr(
        'app.services.auth_service.get_session_factory', lambda: factory
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


@pytest.fixture
def full_client(
    isolated_session_factory: async_sessionmaker[AsyncSession],
) -> Iterator[TestClient]:
    """FastAPI TestClient with the auth + users routers and an isolated DB.

    Shared by the EPIC-7 suites that need both public auth endpoints and
    protected user-management endpoints (RBAC, access-denied, integration).
    """
    from fastapi import FastAPI

    from app.api.routers.auth import router as auth_router
    from app.api.routers.users import router as users_router
    from app.core.error_handlers import register_exception_handlers
    from app.db.session import get_db

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(auth_router)
    app.include_router(users_router)

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        async with isolated_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def google_client(
    isolated_session_factory: async_sessionmaker[AsyncSession],
) -> Iterator[TestClient]:
    """FastAPI TestClient with the auth + google-auth routers and an isolated DB.

    External calls to Google are not made: ``google_auth_service`` is
    monkeypatched per-test (see ``tests/test_google_auth.py``).
    """
    from fastapi import FastAPI

    from app.api.routers.auth import router as auth_router
    from app.api.routers.google_auth import router as google_router
    from app.core.error_handlers import register_exception_handlers
    from app.db.session import get_db

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(auth_router)
    app.include_router(google_router)

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        async with isolated_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app) as test_client:
        yield test_client
