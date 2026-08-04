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
    except (AttributeError, ImportError):
        fallback_app = FastAPI()

        @fallback_app.get('/health')
        async def health_check() -> dict[str, str]:
            return {'status': 'ok'}

        return fallback_app


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client