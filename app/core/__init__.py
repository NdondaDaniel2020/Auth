"""Core application package containing security, infrastructure, web, observability, and events subpackages."""

from __future__ import annotations

import sys

import app.messaging as messaging
import app.messaging.buses as messaging_buses
import app.messaging.events as messaging_events
from app.core.infrastructure import redis
from app.core.observability import logging, observability
from app.core.security import rate_limiter, security, security_logger
from app.core.web import error_handlers, middleware

# Create legacy aliases for app.core.events and app.core.broker
class LegacyEventsModule:
    Event = messaging.Event
    EventBus = messaging.EventBus
    InMemoryEventBus = messaging_buses.InMemoryEventBus
    UserEvents = messaging_events.UserEvents
    AuthEvents = messaging_events.AuthEvents
    get_event_bus = messaging_buses.get_event_bus
    set_event_bus = messaging_buses.set_event_bus


legacy_events = LegacyEventsModule()

# Populate sys.modules aliases for legacy imports
sys.modules['app.core.error_handlers'] = error_handlers
sys.modules['app.core.middleware'] = middleware
sys.modules['app.core.rate_limiter'] = rate_limiter
sys.modules['app.core.redis'] = redis
sys.modules['app.core.broker'] = messaging_buses
sys.modules['app.core.security'] = security
sys.modules['app.core.security_logger'] = security_logger
sys.modules['app.core.logging'] = logging
sys.modules['app.core.observability'] = observability
sys.modules['app.core.events'] = legacy_events
sys.modules['app.core.events.events'] = legacy_events
