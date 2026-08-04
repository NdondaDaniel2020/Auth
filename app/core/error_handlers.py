from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exceptions import AppError

logger = logging.getLogger(__name__)


async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    logger.info("AppError: %s %s", exc.status_code, exc.message)
    content: dict[str, Any] = {"error": exc.message}
    content.update(exc.payload or {})
    return JSONResponse(status_code=exc.status_code, content=content)


async def handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
    # FastAPI/Starlette HTTPException handler
    detail = getattr(exc, "detail", "")
    logger.info("HTTPException: %s %s", exc.status_code, detail)
    return JSONResponse(status_code=exc.status_code, content={"error": detail})


async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    logger.info("RequestValidationError: %s", exc.errors())
    return JSONResponse(
        status_code=422,
        content={"error": "Validation error", "details": exc.errors()},
    )


async def handle_generic_exception(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception during request: %s %s", request.method, request.url)
    return JSONResponse(status_code=500, content={"error": "Internal server error"})


def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers on the FastAPI app."""
    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(HTTPException, handle_http_exception)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(Exception, handle_generic_exception)
