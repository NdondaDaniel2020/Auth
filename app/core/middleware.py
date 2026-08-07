from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.logging import get_logger


def setup_cors_middleware(app: FastAPI) -> None:
    settings = get_settings()

    origins = settings.CORS_ALLOWED_ORIGINS_LIST
    allow_credentials = settings.CORS_ALLOW_CREDENTIALS

    if '*' in origins and allow_credentials:
        raise RuntimeError(
            "CORS_ALLOWED_ORIGINS cannot contain '*' when "
            'CORS_ALLOW_CREDENTIALS is enabled'
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=allow_credentials,
        allow_methods=settings.CORS_ALLOWED_METHODS_LIST,
        allow_headers=settings.CORS_ALLOWED_HEADERS_LIST,
    )


def setup_request_logging_middleware(app: FastAPI) -> None:
    """Register a simple request-logging middleware on the FastAPI app.

    Logs: method, path, status code, duration (s), and client host when available.
    """
    logger = get_logger()

    @app.middleware("http")
    async def _log_requests(request, call_next):
        import time

        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start

        client = request.client.host if getattr(request, 'client', None) else None
        logger.info(
            "%s %s %s %.3fs client=%s",
            request.method,
            request.url.path,
            response.status_code,
            elapsed,
            client,
        )

        return response
