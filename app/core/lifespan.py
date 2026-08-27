from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.infrastructure.broker import (
    broker_lifespan,
    get_broker_config_from_settings,
)
from app.core.infrastructure.redis import close_redis, init_redis
from app.core.observability.observability import setup_logging
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
from app.services.cleanup_service import (
    start_token_cleanup_loop,
    stop_token_cleanup_loop,
)
from app.services.notification_service import (
    setup_notifications,
    teardown_notifications,
)
from app.services.websocket_service import (
    setup_ws_event_handlers,
    teardown_ws_event_handlers,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    settings = get_settings()

    engine = get_engine()
    if settings.DB_ENGINE == 'sqlite' and settings.DB_NAME != ':memory:':
        import os

        path = (
            settings.DB_NAME.rsplit('/', 1)[0]
            if '/' in settings.DB_NAME
            else ''
        )
        if path:
            os.makedirs(path, exist_ok=True)

    await init_redis()
    await init_db()

    # Start broker if configured
    broker_config = get_broker_config_from_settings()
    async with broker_lifespan(broker_config):
        await setup_notifications()
        await setup_ws_event_handlers()
        await start_token_cleanup_loop()
        try:
            yield
        finally:
            await stop_token_cleanup_loop()
            await teardown_notifications()
            await teardown_ws_event_handlers()
    await close_redis()
    await engine.dispose()
