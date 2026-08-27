"""Core application package containing security, infrastructure, web, observability, and events subpackages."""

from __future__ import annotations

import sys

from app.core.events import events
from app.core.infrastructure import broker, redis
from app.core.observability import logging, observability
from app.core.security import rate_limiter, security, security_logger
from app.core.web import error_handlers, middleware

# Populate sys.modules aliases for legacy imports
sys.modules['app.core.error_handlers'] = error_handlers
sys.modules['app.core.middleware'] = middleware
sys.modules['app.core.rate_limiter'] = rate_limiter
sys.modules['app.core.redis'] = redis
sys.modules['app.core.broker'] = broker
sys.modules['app.core.security'] = security
sys.modules['app.core.security_logger'] = security_logger
sys.modules['app.core.logging'] = logging
sys.modules['app.core.observability'] = observability
sys.modules['app.core.events'] = events
