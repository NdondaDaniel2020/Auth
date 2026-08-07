"""Shared pagination dependency for list endpoints.

Endpoints that return collections declare ``pagination: PaginationParamsDep``
instead of repeating ``page``/``page_size`` query parameters inline. Default
and maximum page sizes are read from settings (``PAGE_SIZE_DEFAULT``,
``PAGE_SIZE_MAX``) so the API can tune limits without code changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query

from app.core.config import get_settings

_settings = get_settings()

PAGE_DEFAULT = 1
PAGE_SIZE_DEFAULT = _settings.PAGE_SIZE_DEFAULT
PAGE_SIZE_MAX = _settings.PAGE_SIZE_MAX


@dataclass(frozen=True)
class PaginationParams:
    """Resolved pagination parameters (1-based ``page``, bounded ``page_size``)."""

    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def get_pagination_params(
    page: Annotated[int, Query(ge=1)] = PAGE_DEFAULT,
    page_size: Annotated[
        int, Query(ge=1, le=PAGE_SIZE_MAX)
    ] = PAGE_SIZE_DEFAULT,
) -> PaginationParams:
    """Validate and bundle ``page``/``page_size`` query parameters."""
    return PaginationParams(page=page, page_size=page_size)


PaginationParamsDep = Annotated[
    PaginationParams, Depends(get_pagination_params)
]
