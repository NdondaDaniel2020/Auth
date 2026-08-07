import pytest
from sqlalchemy import text

from app.db.session import get_engine, get_session_factory


@pytest.mark.asyncio
async def test_engine_connection():
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        assert result.scalar() == 1


@pytest.mark.asyncio
async def test_session_close_and_pool_release():
    engine = get_engine()

    # Use a session context to ensure the session is closed at exit
    session_factory = get_session_factory()
    async with session_factory() as session:
        await session.execute(text("SELECT 1"))

    # After the session context exits, the pool should not have checked-out connections
    pool = engine.sync_engine.pool
    assert pool.checkedout() == 0
