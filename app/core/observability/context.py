from __future__ import annotations

import contextvars

request_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    'request_id_ctx', default=None
)
user_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    'user_id_ctx', default=None
)


def get_request_id() -> str | None:
    """Retrieve the current request/correlation ID from context."""
    return request_id_ctx.get()


def set_request_id(request_id: str | None) -> contextvars.Token[str | None]:
    """Set the current request/correlation ID in context."""
    return request_id_ctx.set(request_id)


def get_user_id() -> str | None:
    """Retrieve the current authenticated user ID from context."""
    return user_id_ctx.get()


def set_user_id(user_id: str | None) -> contextvars.Token[str | None]:
    """Set the current authenticated user ID in context."""
    return user_id_ctx.set(user_id)
