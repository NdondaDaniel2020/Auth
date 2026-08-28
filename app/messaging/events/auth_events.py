"""Strongly typed domain events for authentication lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.messaging.base import DomainEvent


class AuthEvents:
    """Constants for authentication event types."""

    LOGIN = 'auth.login'
    LOGOUT = 'auth.logout'
    LOGIN_FAILED = 'auth.login_failed'
    TOKEN_REFRESHED = 'auth.token_refreshed'
    PASSWORD_RESET_REQUESTED = 'auth.password_reset_requested'
    PASSWORD_RESET_COMPLETED = 'auth.password_reset_completed'
    ACCOUNT_TEMPORARILY_LOCKED = 'auth.account_temporarily_locked'


@dataclass
class PasswordResetRequestedEvent(DomainEvent):
    """Event emitted when a password reset is requested."""

    type: str = field(default=AuthEvents.PASSWORD_RESET_REQUESTED, init=False)


@dataclass
class PasswordResetCompletedEvent(DomainEvent):
    """Event emitted when a password reset is completed successfully."""

    type: str = field(default=AuthEvents.PASSWORD_RESET_COMPLETED, init=False)
