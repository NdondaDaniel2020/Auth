"""Observability utilities: structured logging, metrics, health checks."""

from __future__ import annotations

import logging
import sys
import time
from collections.abc import Callable
from typing import Any

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from pythonjsonlogger import jsonlogger
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import get_session_factory


class JSONFormatter(jsonlogger.JsonFormatter):
    """JSON log formatter with standard fields."""

    def add_fields(
        self, log_record: dict, record: logging.LogRecord, message_dict: dict
    ) -> None:
        super().add_fields(log_record, record, message_dict)
        log_record.setdefault('timestamp', time.time())
        log_record.setdefault('level', record.levelname)
        log_record.setdefault('logger', record.name)
        log_record.setdefault('service', 'auth-api')


def setup_logging() -> None:
    """Configure structured JSON logging for production."""
    handler = logging.StreamHandler(sys.stdout)
    formatter = JSONFormatter(
        '%(timestamp)s %(level)s %(logger)s %(service)s %(message)s',
        timestamp=True,
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO if not get_settings().DEBUG else logging.DEBUG)

    logging.getLogger('uvicorn.access').handlers = [handler]
    logging.getLogger('uvicorn.error').handlers = [handler]
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)


# Prometheus metrics
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status'],
)
REQUEST_LATENCY = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency in seconds',
    ['method', 'endpoint'],
)
ACTIVE_REQUESTS = Gauge(
    'http_requests_active',
    'Currently active HTTP requests',
)
DB_CONNECTIONS = Gauge(
    'db_connections_active',
    'Active database connections',
)
DB_QUERY_LATENCY = Histogram(
    'db_query_duration_seconds',
    'Database query latency in seconds',
    ['query_type'],
)


class MetricsMiddleware:
    """ASGI middleware for Prometheus metrics."""

    def __init__(self, app: Callable) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return

        method = scope.get('method', 'UNKNOWN')
        path = scope.get('path', '/')
        ACTIVE_REQUESTS.inc()
        start = time.perf_counter()

        async def send_wrapper(message):
            if message['type'] == 'http.response.start':
                status = message['status']
                REQUEST_COUNT.labels(
                    method=method, endpoint=path, status=status
                ).inc()
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            ACTIVE_REQUESTS.dec()
            REQUEST_LATENCY.labels(method=method, endpoint=path).observe(
                time.perf_counter() - start
            )


async def get_health_status() -> dict[str, Any]:
    """Comprehensive health check including DB connectivity."""
    health: dict[str, Any] = {
        'status': 'ok',
        'checks': {},
    }

    try:
        session_factory = get_session_factory()
        async with session_factory() as session:
            await session.execute(text('SELECT 1'))
        health['checks']['database'] = {'status': 'ok'}
    except OSError:
        health['checks']['database'] = {
            'status': 'fail',
            'error': 'Connection refused',
        }
        health['status'] = 'degraded'
    except Exception as e:  # noqa: BLE001
        health['checks']['database'] = {'status': 'fail', 'error': str(e)}
        health['status'] = 'degraded'

    return health


def metrics_response() -> tuple[bytes, str]:
    """Return Prometheus metrics payload and content type."""
    return generate_latest(), CONTENT_TYPE_LATEST
