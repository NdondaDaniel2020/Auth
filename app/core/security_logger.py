from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from app.core.config import get_settings

SECURITY_LOGGER_NAME = 'auth_app.security'


class _JsonFormatter(logging.Formatter):
    """Format security log records as a single searchable JSON line.

    The record's message is the event name (e.g. ``LOGIN_SUCCESS``); extra
    context (user id, IP, metadata) is carried in ``record.security_fields``
    and merged into the payload. Output is deterministic per record so logs
    can be filtered by event type or user id.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            'timestamp': datetime.now(UTC).isoformat(),
            'level': record.levelname,
            'event': record.getMessage(),
        }
        payload.update(getattr(record, 'security_fields', {}))
        return json.dumps(payload, default=str, ensure_ascii=False)


def get_security_logger() -> logging.Logger:
    """Return the security logger, emitting structured JSON to stderr.

    The level follows the app configuration (DEBUG when ``settings.DEBUG`` is
    set, INFO otherwise) so the same knob controls every logger.
    """
    settings = get_settings()
    level = (
        logging.DEBUG if getattr(settings, 'DEBUG', False) else logging.INFO
    )

    logger = logging.getLogger(SECURITY_LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setLevel(level)
        handler.setFormatter(_JsonFormatter())
        logger.addHandler(handler)

    return logger


def log_security_event(
    event: str,
    *,
    user_id: str | None = None,
    ip: str | None = None,
    metadata: dict[str, Any] | None = None,
    level: int = logging.INFO,
) -> None:
    """Emit a structured security event.

    Only safe identifiers/metadata are ever written: ``user_id``, the request
    ``ip`` and caller-provided ``metadata``. Passwords, hashes and full tokens
    must never be passed as metadata.
    """
    fields: dict[str, Any] = {}
    if user_id is not None:
        fields['user_id'] = user_id
    if ip is not None:
        fields['ip'] = ip
    if metadata:
        fields.update(metadata)

    get_security_logger().log(level, event, extra={'security_fields': fields})
