"""Strongly typed domain events for user lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.messaging.base import DomainEvent


class UserEvents:
    """Constants for user event types."""

    CREATED = 'user.created'
    UPDATED = 'user.updated'
    DELETED = 'user.deleted'
    ACTIVATED = 'user.activated'
    DEACTIVATED = 'user.deactivated'
    ROLES_CHANGED = 'user.roles_changed'
    PASSWORD_CHANGED = 'user.password_changed'
    EMAIL_VERIFIED = 'user.email_verified'


@dataclass
class UserCreatedEvent(DomainEvent):
    """Event emitted when a new user is created."""

    type: str = field(default=UserEvents.CREATED, init=False)


@dataclass
class UserUpdatedEvent(DomainEvent):
    """Event emitted when a user profile is updated."""

    type: str = field(default=UserEvents.UPDATED, init=False)


@dataclass
class UserDeactivatedEvent(DomainEvent):
    """Event emitted when a user account is deactivated."""

    type: str = field(default=UserEvents.DEACTIVATED, init=False)


@dataclass
class UserRolesChangedEvent(DomainEvent):
    """Event emitted when user roles/permissions are updated."""

    type: str = field(default=UserEvents.ROLES_CHANGED, init=False)


@dataclass
class PasswordChangedEvent(DomainEvent):
    """Event emitted when a user password is changed."""

    type: str = field(default=UserEvents.PASSWORD_CHANGED, init=False)


@dataclass
class EmailVerifiedEvent(DomainEvent):
    """Event emitted when a user verifies their email address."""

    type: str = field(default=UserEvents.EMAIL_VERIFIED, init=False)
