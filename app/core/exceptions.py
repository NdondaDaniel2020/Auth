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
