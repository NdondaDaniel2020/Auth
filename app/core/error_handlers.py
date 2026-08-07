from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exceptions import AppError

logger = logging.getLogger(__name__)


def _error_payload(
    request: Request, *, exc_type: str, message: str, status_code: int, details: Any | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "error": {
            "type": exc_type,
            "message": message,
        },
        "status": status_code,
        "path": str(request.url.path),
        "method": request.method,
    }

    if details is not None:
        payload["error"]["details"] = details

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
    logger.info("AppError: %s %s %s", exc.status_code, request.method, request.url.path)
    content = _error_payload(
        request,
        exc_type=exc.__class__.__name__,
        message=exc.message,
        status_code=exc.status_code,
        details=exc.payload or None,
    )
    return JSONResponse(status_code=exc.status_code, content=content, headers=exc.headers)


async def handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
    # FastAPI/Starlette HTTPException handler
    detail = getattr(exc, "detail", "")
    logger.info("HTTPException: %s %s %s", exc.status_code, request.method, request.url.path)
    content = _error_payload(
        request,
        exc_type="HTTPException",
        message=str(detail),
        status_code=exc.status_code,
    )
    return JSONResponse(status_code=exc.status_code, content=content)


async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    logger.info("RequestValidationError: %s %s", request.method, request.url.path)
    content = _error_payload(
        request,
        exc_type="RequestValidationError",
        message="Validation error",
        status_code=422,
        details=_json_safe(exc.errors()),
    )
    return JSONResponse(status_code=422, content=content)


async def handle_generic_exception(request: Request, exc: Exception) -> JSONResponse:
    # Log full details for internal debugging, but do not expose internals to clients.
    logger.exception("Unhandled exception during request: %s %s", request.method, request.url)
    content = _error_payload(
        request,
        exc_type="InternalServerError",
        message="Internal server error",
        status_code=500,
    )
    return JSONResponse(status_code=500, content=content)


def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers on the FastAPI app."""
    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(HTTPException, handle_http_exception)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(Exception, handle_generic_exception)
