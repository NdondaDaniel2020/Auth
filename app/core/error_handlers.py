from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exceptions import AppError

logger = logging.getLogger(__name__)


def _error_payload(
    request: Request,
    *,
    exc_type: str,
    message: str,
    status_code: int,
    details: Any | None = None,
    code: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        'error': {
            'type': exc_type,
            'message': message,
        },
        'status': status_code,
        'path': str(request.url.path),
        'method': request.method,
    }

    if code is not None:
        payload['error']['code'] = code

    if details is not None:
        payload['error']['details'] = details

    return payload


def _json_safe(value: Any) -> Any:
    """Recursively convert non-JSON-serializable values (e.g. exceptions)."""
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, Exception):
        return str(value)
    try:
        import json

        json.dumps(value)
        return value
    except TypeError:
        return str(value)


async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    logger.info(
        'AppError: %s %s %s', exc.status_code, request.method, request.url.path
    )
    content = _error_payload(
        request,
        exc_type=exc.__class__.__name__,
        message=exc.message,
        status_code=exc.status_code,
        details=exc.payload or None,
        code=exc.code,
    )
    return JSONResponse(
        status_code=exc.status_code, content=content, headers=exc.headers
    )


async def handle_http_exception(
    request: Request, exc: HTTPException
) -> JSONResponse:
    # FastAPI/Starlette HTTPException handler
    detail = getattr(exc, 'detail', '')
    logger.info(
        'HTTPException: %s %s %s',
        exc.status_code,
        request.method,
        request.url.path,
    )
    content = _error_payload(
        request,
        exc_type='HTTPException',
        message=str(detail),
        status_code=exc.status_code,
    )
    return JSONResponse(status_code=exc.status_code, content=content)


def _normalize_validation_details(errors: Sequence[Any]) -> list[dict[str, str]]:
    """Flatten pydantic errors into ``{"field": ..., "message": ...}`` items."""
    location_parts = {'body', 'query', 'path', 'header', 'cookie'}

    normalized: list[dict[str, str]] = []
    for error in errors:
        loc = error.get('loc', [])
        field = '.'.join(
            str(part) for part in loc if part not in location_parts
        )
        message = error.get('msg', '')
        message = message.removeprefix('Value error, ')
        normalized.append({'field': field or 'request', 'message': message})
    return normalized


async def handle_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    logger.info(
        'RequestValidationError: %s %s', request.method, request.url.path
    )
    content = _error_payload(
        request,
        exc_type='RequestValidationError',
        message='Validation error',
        status_code=422,
        details=_normalize_validation_details(exc.errors()),
    )
    return JSONResponse(status_code=422, content=content)


async def handle_generic_exception(
    request: Request, exc: Exception
) -> JSONResponse:
    # Log full details for internal debugging, but do not expose internals to clients.
    logger.exception(
        'Unhandled exception during request: %s %s',
        request.method,
        request.url,
    )
    content = _error_payload(
        request,
        exc_type='InternalServerError',
        message='Internal server error',
        status_code=500,
    )
    return JSONResponse(status_code=500, content=content)


def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers on the FastAPI app."""
    app.add_exception_handler(AppError, handle_app_error)  # type: ignore[arg-type]
    app.add_exception_handler(HTTPException, handle_http_exception)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, handle_validation_error)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, handle_generic_exception)
