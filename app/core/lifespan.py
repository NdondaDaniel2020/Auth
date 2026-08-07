from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.db.init_db import init_db
from app.db.session import get_engine
from app.models import (
    email_verification_token,  # noqa: F401
    password_reset_token,  # noqa: F401
    permission,  # noqa: F401
    refresh_token,  # noqa: F401
    role,  # noqa: F401
    user,  # noqa: F401
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    engine = get_engine()
    if settings.DB_ENGINE == 'sqlite' and settings.DB_NAME != ':memory:':
        import os

        path = settings.DB_NAME.rsplit('/', 1)[0] if '/' in settings.DB_NAME else ''
        if path:
            os.makedirs(path, exist_ok=True)

    await init_db()

    yield
    await engine.dispose()
