from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from jwt import InvalidTokenError
from passlib.context import CryptContext

from app.core.config import get_settings


def _get_pwd_context() -> CryptContext:
    settings = get_settings()
    return CryptContext(
        schemes=[settings.PASSWORD_HASH_SCHEME], deprecated='auto'
    )


def hash_password(password: str) -> str:
    """Generate a salted hash for a plain-text password.

    This is the single source of truth for password hashing.
    """
    return _get_pwd_context().hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Validate a plain-text password against a stored hash."""
    return _get_pwd_context().verify(plain_password, hashed_password)


def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT access token with the given claims."""
    settings = get_settings()

    payload = dict(data)
    now = datetime.now(UTC)
    expire = now + (
        expires_delta or timedelta(minutes=settings.JWT_ACCESS_MINUTES)
    )
    payload['exp'] = expire
    payload['iat'] = now
    payload['type'] = 'access'

    return jwt.encode(
        payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM
    )


def create_refresh_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT refresh token with a distinct type claim."""
    settings = get_settings()

    payload = dict(data)
    now = datetime.now(UTC)
    expire = now + (expires_delta or timedelta(days=settings.JWT_REFRESH_DAYS))
    payload['exp'] = expire
    payload['iat'] = now
    payload['type'] = 'refresh'

    return jwt.encode(
        payload,
        settings.REFRESH_SECRET_KEY_ACTIVE,
        algorithm=settings.ALGORITHM,
    )


def create_signed_token(
    data: dict[str, Any],
    *,
    token_type: str,
    expires_delta: timedelta,
) -> str:
    """Create a signed JWT with a custom type claim and expiry.

    Signed with ``SECRET_KEY``. The matching verification is
    ``decode_token(token, expected_type=token_type)``.
    """
    settings = get_settings()

    payload = dict(data)
    now = datetime.now(UTC)
    payload['type'] = token_type
    payload['iat'] = now
    payload['exp'] = now + expires_delta

    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(
    token: str, *, expected_type: str | None = None
) -> dict[str, Any]:
    """Decode and validate a JWT.

    Validates signature and expiration. When ``expected_type`` is given,
    the ``type`` claim must match, otherwise ``InvalidTokenError`` is raised.
    """
    settings = get_settings()

    if expected_type == 'refresh':
        secret = settings.REFRESH_SECRET_KEY_ACTIVE
    else:
        secret = settings.SECRET_KEY

    payload = jwt.decode(token, secret, algorithms=[settings.ALGORITHM])

    if expected_type is not None and payload.get('type') != expected_type:
        raise InvalidTokenError('Token type mismatch')

    return payload


def decode_access_token(token: str) -> dict[str, Any]:
    return decode_token(token, expected_type='access')


def decode_refresh_token(token: str) -> dict[str, Any]:
    return decode_token(token, expected_type='refresh')
