"""Generic per-route request rate limiting.

Routes that must be protected declare ``dependencies=[Depends(rate_limit(...))]``
in the route decorator. The scope name maps to a ``Settings`` field holding
the limit in ``"N/timeunit"`` format (e.g. ``RATE_LIMIT_REGISTER``); if the
field is missing the ``RATE_LIMIT_DEFAULT`` value is used.

Identifiers are keyed by the client IP; authenticated endpoints can extend
``build_rate_limit_key`` to include the user id so per-user limits apply.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Request

from app.core.config import get_settings
from app.core.exceptions import RateLimitExceededError
from app.core.rate_limiter import parse_rate_limit, request_rate_limiter


def get_client_ip(request: Request) -> str:
    """Return the client IP, or ``'unknown'`` when unavailable."""
    return request.client.host if request.client else 'unknown'


def build_rate_limit_key(scope: str, request: Request) -> str:
    """Build the limiter key for a scope and request."""
    return f'{scope}:{get_client_ip(request)}'


def rate_limit(scope: str) -> Callable[[Request], None]:
    """Build a dependency enforcing the request limit configured for ``scope``.

    Usage: ``dependencies=[Depends(rate_limit('RATE_LIMIT_REGISTER'))]``.
    """

    async def dependency(request: Request) -> None:
        settings = get_settings()
        limit, window_seconds = parse_rate_limit(
            getattr(settings, scope, settings.RATE_LIMIT_DEFAULT)
        )
        key = build_rate_limit_key(scope, request)
        retry_after = request_rate_limiter.check_and_consume(
            key, limit, window_seconds
        )
        if retry_after is not None:
            raise RateLimitExceededError(retry_after=retry_after)

    return dependency
