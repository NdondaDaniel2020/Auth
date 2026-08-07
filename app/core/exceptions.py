from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Application-level expected error.

    Use this to raise errors that should be returned to the client
    with a specific HTTP status code and optional payload.
    """

    def __init__(
        self,
        message: str,
        status_code: int = 400,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.payload = payload or {}
        self.headers = headers or {}

    def to_dict(self) -> dict[str, Any]:
        return {'message': self.message, **self.payload}


class NotFoundError(AppError):
    def __init__(
        self, message: str = 'Not found', payload: dict[str, Any] | None = None
    ):
        super().__init__(message=message, status_code=404, payload=payload)


class PermissionDeniedError(AppError):
    def __init__(
        self,
        message: str = 'Permission denied',
        payload: dict[str, Any] | None = None,
    ):
        super().__init__(message=message, status_code=403, payload=payload)


class BusinessRuleError(AppError):
    def __init__(
        self,
        message: str = 'Business rule violation',
        payload: dict[str, Any] | None = None,
    ):
        # 400 Bad Request for business errors; change to 409 if preferred
        super().__init__(message=message, status_code=400, payload=payload)


class DomainValidationError(AppError):
    def __init__(
        self,
        message: str = 'Validation error',
        payload: dict[str, Any] | None = None,
    ):
        super().__init__(message=message, status_code=422, payload=payload)


class EmailAlreadyExistsError(AppError):
    def __init__(
        self,
        message: str = 'Email already registered',
        payload: dict[str, Any] | None = None,
    ):
        super().__init__(message=message, status_code=409, payload=payload)


class InvalidCredentialsError(AppError):
    def __init__(
        self,
        message: str = 'Invalid email or password',
        payload: dict[str, Any] | None = None,
    ):
        super().__init__(message=message, status_code=401, payload=payload)


class InvalidRefreshTokenError(AppError):
    def __init__(
        self,
        message: str = 'Invalid refresh token',
        payload: dict[str, Any] | None = None,
    ):
        super().__init__(message=message, status_code=401, payload=payload)


class InvalidOrExpiredTokenError(AppError):
    def __init__(
        self,
        message: str = 'Invalid or expired token',
        payload: dict[str, Any] | None = None,
    ):
        super().__init__(message=message, status_code=400, payload=payload)


class TokenAlreadyUsedError(AppError):
    def __init__(
        self,
        message: str = 'Token already used',
        payload: dict[str, Any] | None = None,
    ):
        super().__init__(message=message, status_code=400, payload=payload)


class TooManyLoginAttemptsError(AppError):
    def __init__(
        self,
        message: str = 'Too many failed login attempts. Try again later.',
        payload: dict[str, Any] | None = None,
        retry_after: int | None = None,
    ):
        headers = {}
        if retry_after is not None:
            headers['Retry-After'] = str(retry_after)
        super().__init__(
            message=message,
            status_code=429,
            payload=payload,
            headers=headers,
        )
