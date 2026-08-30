from fastapi import FastAPI, Response

from app.api.router import api_router
from app.core.config import get_settings
from app.core.lifespan import lifespan
from app.core.observability.observability import (
    MetricsMiddleware,
    get_health_status,
    metrics_response,
)
from app.core.web.error_handlers import register_exception_handlers
from app.core.web.middleware import (
    setup_correlation_id_middleware,
    setup_cors_middleware,
    setup_request_logging_middleware,
    setup_security_headers_middleware,
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
    setup_security_headers_middleware(app)
    setup_cors_middleware(app)
    setup_request_logging_middleware(app)
    setup_correlation_id_middleware(app)
    register_exception_handlers(app)

    app.include_router(api_router, prefix='/api')

    @app.get('/metrics', include_in_schema=False)
    async def metrics():
        data, content_type = metrics_response()
        return Response(content=data, media_type=content_type)

    @app.get('/live', include_in_schema=False)
    @app.get('/api/live', include_in_schema=False)
    async def live():
        return {'status': 'alive'}

    @app.get('/api/health', include_in_schema=False)
    async def health():
        return await get_health_status()

    return app


app = create_app()
