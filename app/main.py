from fastapi import FastAPI, Response

from app.api.router import api_router
from app.core.config import get_settings
from app.core.error_handlers import register_exception_handlers
from app.core.lifespan import lifespan
from app.core.middleware import (
    setup_cors_middleware,
    setup_request_logging_middleware,
)
from app.core.observability import (
    MetricsMiddleware,
    get_health_status,
    metrics_response,
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

    app.add_middleware(MetricsMiddleware)
    setup_cors_middleware(app)
    setup_request_logging_middleware(app)
    register_exception_handlers(app)

    app.include_router(api_router, prefix='/api')

    @app.get('/metrics', include_in_schema=False)
    async def metrics():
        data, content_type = metrics_response()
        return Response(content=data, media_type=content_type)

    @app.get('/api/health', include_in_schema=False)
    async def health():
        return await get_health_status()

    return app


app = create_app()
