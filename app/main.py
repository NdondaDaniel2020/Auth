from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import get_settings
from app.core.error_handlers import register_exception_handlers
from app.core.lifespan import lifespan
from app.core.middleware import (
    setup_cors_middleware,
    setup_request_logging_middleware,
)


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=settings.APP_DESCRIPTION,
        debug=settings.DEBUG,
        lifespan=lifespan,
    )

    setup_cors_middleware(app)
    setup_request_logging_middleware(app)
    register_exception_handlers(app)

    app.include_router(api_router, prefix='/api')

    return app


app = create_app()
