"""Generic paginated response envelope reused by every list endpoint."""

from __future__ import annotations

from pydantic import BaseModel


class PaginatedResponse[T](BaseModel):
    """Envelope for paginated collections.

    ``items`` holds the serialized rows of the current page, ``total`` is the
    count across all pages (clients can derive ``page_count``), and
    ``page``/``page_size`` echo the requested pagination parameters.
    """

    items: list[T]
    total: int
    page: int
    page_size: int
