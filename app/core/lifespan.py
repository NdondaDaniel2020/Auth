import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db.base import Base
from app.db.session import get_engine
from app.core.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    if settings.DB_ENGINE == 'sqlite' and 'memory' not in settings.DB_NAME:
        path = settings.DB_NAME.split('/')[:-1]
        path='/'.join(path)
        os.makedirs(path, exist_ok=True)

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield
    await engine.dispose()
