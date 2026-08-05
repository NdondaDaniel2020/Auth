from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Application-level expected error.

    Use this to raise errors that should be returned to the client
    with a specific HTTP status code and optional payload.
    """

    def __init__(self, message: str, status_code: int = 400, payload: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.payload = payload or {}

    def to_dict(self) -> dict[str, Any]:
        return {"message": self.message, **self.payload}


class NotFoundError(AppError):
    def __init__(self, message: str = "Not found", payload: dict[str, Any] | None = None):
        super().__init__(message=message, status_code=404, payload=payload)


class PermissionDeniedError(AppError):
    def __init__(self, message: str = "Permission denied", payload: dict[str, Any] | None = None):
        super().__init__(message=message, status_code=403, payload=payload)


class BusinessRuleError(AppError):
    def __init__(self, message: str = "Business rule violation", payload: dict[str, Any] | None = None):
        # 400 Bad Request for business errors; change to 409 if preferred
        super().__init__(message=message, status_code=400, payload=payload)


class DomainValidationError(AppError):
    def __init__(self, message: str = "Validation error", payload: dict[str, Any] | None = None):
        super().__init__(message=message, status_code=422, payload=payload)
