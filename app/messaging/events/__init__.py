"""Strongly typed domain events package."""

from app.messaging.events.auth_events import (
    AuthEvents,
    PasswordResetCompletedEvent,
    PasswordResetRequestedEvent,
)
from app.messaging.events.user_events import (
    EmailVerifiedEvent,
    PasswordChangedEvent,
    UserCreatedEvent,
    UserDeactivatedEvent,
    UserEvents,
    UserRolesChangedEvent,
    UserUpdatedEvent,
)

__all__ = [
    'AuthEvents',
    'EmailVerifiedEvent',
    'PasswordChangedEvent',
    'PasswordResetCompletedEvent',
    'PasswordResetRequestedEvent',
    'UserCreatedEvent',
    'UserDeactivatedEvent',
    'UserEvents',
    'UserRolesChangedEvent',
    'UserUpdatedEvent',
]
