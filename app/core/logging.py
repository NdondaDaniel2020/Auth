from __future__ import annotations

import logging
from typing import Optional

from app.core.config import get_settings


def configure_logger(name: str = 'auth_app', level: Optional[int] = None) -> logging.Logger:
    """Configure and return a logger for the application.

    If the logger already has handlers, it is returned as-is. The level
    defaults to INFO unless overridden by settings.DEBUG.
    """
    settings = get_settings()

    logger = logging.getLogger(name)

    if level is None:
        level = logging.DEBUG if getattr(settings, 'DEBUG', False) else logging.INFO

    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setLevel(level)
        fmt = '%(asctime)s - %(levelname)s - %(name)s - %(message)s'
        formatter = logging.Formatter(fmt)
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


def get_logger() -> logging.Logger:
    return configure_logger()
