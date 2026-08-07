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
        code: str | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.payload = payload or {}
        self.headers = headers or {}
        self.code = code or self.__class__.__name__

    def to_dict(self) -> dict[str, Any]:
        return {
            'message': self.message,
            'code': self.code,
            **self.payload,
        }


class NotFoundError(AppError):
    def __init__(
        self, message: str = 'Not found', payload: dict[str, Any] | None = None
    ):
        super().__init__(
            message=message, status_code=404, payload=payload, code='NOT_FOUND'
        )


class UserNotFoundError(NotFoundError):
    def __init__(
        self,
        message: str = 'User not found',
        payload: dict[str, Any] | None = None,
    ):
        super().__init__(message=message, payload=payload)
        self.code = 'USER_NOT_FOUND'


class RoleNotFoundError(NotFoundError):
    def __init__(
        self,
        message: str = 'Role not found',
        payload: dict[str, Any] | None = None,
    ):
        super().__init__(message=message, payload=payload)
        self.code = 'ROLE_NOT_FOUND'


class PermissionDeniedError(AppError):
    def __init__(
        self,
        message: str = 'Permission denied',
        payload: dict[str, Any] | None = None,
        code: str = 'PERMISSION_DENIED',
    ):
        super().__init__(
            message=message,
            status_code=403,
            payload=payload,
            code=code,
        )


class BusinessRuleError(AppError):
    def __init__(
        self,
        message: str = 'Business rule violation',
        payload: dict[str, Any] | None = None,
    ):
        # 400 Bad Request for business errors; change to 409 if preferred
        super().__init__(
            message=message,
            status_code=400,
            payload=payload,
            code='BUSINESS_RULE_ERROR',
        )


class DomainValidationError(AppError):
    def __init__(
        self,
        message: str = 'Validation error',
        payload: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=message,
            status_code=422,
            payload=payload,
            code='VALIDATION_ERROR',
        )


class SelfDeactivationError(BusinessRuleError):
    def __init__(
        self,
        message: str = 'You cannot deactivate your own account',
        payload: dict[str, Any] | None = None,
    ):
        super().__init__(message=message, payload=payload)
        self.code = 'SELF_DEACTIVATION_NOT_ALLOWED'


class SelfRoleRemovalError(BusinessRuleError):
    def __init__(
        self,
        message: str = 'You cannot remove your own admin role',
        payload: dict[str, Any] | None = None,
    ):
        super().__init__(message=message, payload=payload)
        self.code = 'SELF_ROLE_REMOVAL_NOT_ALLOWED'


class EmailAlreadyExistsError(AppError):
    def __init__(
        self,
        message: str = 'Email already registered',
        payload: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=message,
            status_code=409,
            payload=payload,
            code='EMAIL_ALREADY_EXISTS',
        )


class InvalidCredentialsError(AppError):
    def __init__(
        self,
        message: str = 'Invalid email or password',
        payload: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=message,
            status_code=401,
            payload=payload,
            code='INVALID_CREDENTIALS',
        )


class NotAuthenticatedError(AppError):
    def __init__(
        self,
        message: str = 'Not authenticated',
        payload: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=message,
            status_code=401,
            payload=payload,
            headers={'WWW-Authenticate': 'Bearer'},
            code='NOT_AUTHENTICATED',
        )


class TokenInvalidError(NotAuthenticatedError):
    def __init__(
        self,
        message: str = 'Invalid access token',
        payload: dict[str, Any] | None = None,
    ):
        super().__init__(message=message, payload=payload)
        self.code = 'TOKEN_INVALID'


class TokenExpiredError(NotAuthenticatedError):
    def __init__(
        self,
        message: str = 'Access token expired',
        payload: dict[str, Any] | None = None,
    ):
        super().__init__(message=message, payload=payload)
        self.code = 'TOKEN_EXPIRED'


class AccountInactiveError(NotAuthenticatedError):
    def __init__(
        self,
        message: str = 'Account is inactive',
        payload: dict[str, Any] | None = None,
    ):
        super().__init__(message=message, payload=payload)
        self.code = 'ACCOUNT_INACTIVE'


class InvalidRefreshTokenError(AppError):
    def __init__(
        self,
        message: str = 'Invalid refresh token',
        payload: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=message,
            status_code=401,
            payload=payload,
            code='INVALID_REFRESH_TOKEN',
        )


class InvalidOrExpiredTokenError(AppError):
    def __init__(
        self,
        message: str = 'Invalid or expired token',
        payload: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=message,
            status_code=400,
            payload=payload,
            code='INVALID_OR_EXPIRED_TOKEN',
        )


class TokenAlreadyUsedError(AppError):
    def __init__(
        self,
        message: str = 'Token already used',
        payload: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=message,
            status_code=400,
            payload=payload,
            code='TOKEN_ALREADY_USED',
        )


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
            code='TOO_MANY_ATTEMPTS',
        )


class RateLimitExceededError(AppError):
    def __init__(
        self,
        message: str = 'Too many requests. Try again later.',
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
            code='RATE_LIMIT_EXCEEDED',
        )


class GoogleLoginDisabledError(AppError):
    def __init__(
        self,
        message: str = 'Google login is not enabled',
        payload: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=message,
            status_code=403,
            payload=payload,
            code='GOOGLE_LOGIN_DISABLED',
        )


class InvalidGoogleTokenError(AppError):
    def __init__(
        self,
        message: str = 'Invalid Google token',
        payload: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=message,
            status_code=400,
            payload=payload,
            code='INVALID_GOOGLE_TOKEN',
        )


class GoogleAuthError(AppError):
    def __init__(
        self,
        message: str = 'Google authentication service error',
        payload: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=message,
            status_code=502,
            payload=payload,
            code='GOOGLE_AUTH_ERROR',
        )
