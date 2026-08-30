import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.observability.context import (
    get_request_id,
    request_id_ctx,
    set_request_id,
    set_user_id,
    user_id_ctx,
)
from app.core.observability.logging import get_logger


def setup_correlation_id_middleware(app: FastAPI) -> None:
    """Register Correlation ID (X-Request-ID) middleware on the FastAPI app.

    Extracts X-Request-ID from incoming request headers or generates a new UUID4.
    Sets the ID into contextvars and injects X-Request-ID into response headers.
    """

    @app.middleware('http')
    async def _handle_correlation_id(request, call_next):
        request_id = request.headers.get('X-Request-ID') or uuid.uuid4().hex
        token_req = set_request_id(request_id)
        token_user = set_user_id(None)
        try:
            response = await call_next(request)
            response.headers['X-Request-ID'] = request_id
            return response
        finally:
            request_id_ctx.reset(token_req)
            user_id_ctx.reset(token_user)


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

    @app.middleware('http')
    async def _log_requests(request, call_next):
        import time

        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start

        client = (
            request.client.host if getattr(request, 'client', None) else None
        )
        request_id = get_request_id()
        logger.info(
            '%s %s %s %.3fs client=%s request_id=%s',
            request.method,
            request.url.path,
            response.status_code,
            elapsed,
            client,
            request_id,
        )

        return response


def setup_security_headers_middleware(app: FastAPI) -> None:
    """Register HTTP security headers middleware on the FastAPI app.

    Enforces defensive HTTP headers: X-Frame-Options, X-Content-Type-Options,
    Referrer-Policy, and Strict-Transport-Security.
    """

    @app.middleware('http')
    async def _add_security_headers(request, call_next):
        response = await call_next(request)
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Strict-Transport-Security'] = (
            'max-age=31536000; includeSubDomains'
        )
        return response
