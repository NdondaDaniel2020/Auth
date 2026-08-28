"""Notification message contracts (Pydantic models).

Defines the schema for all notification messages sent via the event bus.
These contracts are versioned and can be evolved over time.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class NotificationChannel(str, Enum):
    """Delivery channel for notification."""

    EMAIL = 'email'
    PUSH = 'push'
    IN_APP = 'in_app'
    SMS = 'sms'


class NotificationPriority(str, Enum):
    """Priority level for notification delivery."""

    LOW = 'low'
    NORMAL = 'normal'
    HIGH = 'high'
    URGENT = 'urgent'


class BaseNotification(BaseModel):
    """Base notification envelope."""

    model_config = ConfigDict(
        extra='forbid',
        use_enum_values=True,
        json_encoders={datetime: lambda v: v.isoformat(), UUID: str},
    )

    notification_id: str = Field(
        ..., description='Unique notification identifier'
    )
    channel: NotificationChannel
    priority: NotificationPriority = NotificationPriority.NORMAL
    recipient_id: str = Field(
        ..., description='Internal user ID or external identifier'
    )
    correlation_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EmailNotification(BaseNotification):
    """Email notification payload."""

    channel: Literal[NotificationChannel.EMAIL] = NotificationChannel.EMAIL

    to_email: EmailStr
    from_email: EmailStr | None = None
    from_name: str | None = None
    subject: str
    html_body: str | None = None
    text_body: str | None = None
    template_id: str | None = None
    template_data: dict[str, Any] = Field(default_factory=dict)
    reply_to: EmailStr | None = None
    headers: dict[str, str] = Field(default_factory=dict)


class PushNotification(BaseNotification):
    """Push notification payload (FCM/APNs)."""

    channel: Literal[NotificationChannel.PUSH] = NotificationChannel.PUSH

    device_tokens: list[str] = Field(..., min_length=1)
    title: str
    body: str
    icon: str | None = None
    image: str | None = None
    click_action: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    badge: int | None = None
    sound: str | None = None


class InAppNotification(BaseNotification):
    """In-app notification payload (stored in DB, shown in UI)."""

    channel: Literal[NotificationChannel.IN_APP] = NotificationChannel.IN_APP

    title: str
    message: str
    action_url: str | None = None
    action_label: str | None = None
    icon: str | None = None
    category: str | None = None
    read: bool = False


class SMSNotification(BaseNotification):
    """SMS notification payload."""

    channel: Literal[NotificationChannel.SMS] = NotificationChannel.SMS

    to_phone: str = Field(..., pattern=r'^\+?[1-9]\d{1,14}$')
    body: str
    from_number: str | None = None


# --- Event payloads that trigger notifications ---


class UserCreatedPayload(BaseModel):
    """Payload for user.created event."""

    model_config = ConfigDict(extra='forbid')

    user_id: str
    email: EmailStr
    full_name: str | None = None
    is_verified: bool = False
    temporary_password: str | None = None  # Only for admin-created users
    verify_link: str | None = None


class UserUpdatedPayload(BaseModel):
    """Payload for user.updated event."""

    model_config = ConfigDict(extra='forbid')

    user_id: str
    email: EmailStr
    changed_fields: list[str] = Field(
        ..., description='List of field names that changed'
    )
    old_values: dict[str, Any] = Field(default_factory=dict)
    new_values: dict[str, Any] = Field(default_factory=dict)
    actor_id: str | None = Field(
        None, description='ID of user who made the change'
    )


class UserDeactivatedPayload(BaseModel):
    """Payload for user.deactivated event."""

    model_config = ConfigDict(extra='forbid')

    user_id: str
    email: EmailStr
    actor_id: str | None = None
    reason: str | None = None


class UserRolesChangedPayload(BaseModel):
    """Payload for user.roles_changed event."""

    model_config = ConfigDict(extra='forbid')

    user_id: str
    email: EmailStr
    old_roles: list[str]
    new_roles: list[str]
    actor_id: str | None = None


class PasswordChangedPayload(BaseModel):
    """Payload for user.password_changed event."""

    model_config = ConfigDict(extra='forbid')

    user_id: str
    email: EmailStr
    changed_by_self: bool = True
    actor_id: str | None = None
    reason: str | None = None  # e.g., "reset", "admin_reset", "security"


class EmailVerifiedPayload(BaseModel):
    """Payload for user.email_verified event."""

    model_config = ConfigDict(extra='forbid')

    user_id: str
    email: EmailStr


class PasswordResetRequestedPayload(BaseModel):
    """Payload for auth.password_reset_requested event."""

    model_config = ConfigDict(extra='forbid')

    user_id: str
    email: EmailStr
    reset_token: str
    expires_at: datetime
    client_ip: str | None = None


class EmailVerificationRequestedPayload(BaseModel):
    """Payload for auth.email_verification_requested event."""

    model_config = ConfigDict(extra='forbid')

    user_id: str
    email: EmailStr
    verify_token: str
    expires_at: datetime
    client_ip: str | None = None


class PasswordResetCompletedPayload(BaseModel):
    """Payload for auth.password_reset_completed event."""

    model_config = ConfigDict(extra='forbid')

    user_id: str
    email: EmailStr
    client_ip: str | None = None


# --- Union type for all notification payloads ---

NotificationPayload = (
    EmailNotification | PushNotification | InAppNotification | SMSNotification
)


# --- REST Catch-Up Sync schemas ---


class NotificationRead(BaseModel):
    """Notification item representation for Catch-Up sync."""

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={datetime: lambda v: v.isoformat()},
    )

    id: int
    user_id: str
    channel: str = 'in_app'
    event_type: str
    title: str
    message: str
    read: bool = False
    details: dict[str, Any] | None = None
    created_at: datetime


class NotificationSyncResponse(BaseModel):
    """Response payload for REST Catch-Up notification sync."""

    events: list[NotificationRead]
    total: int
    has_more: bool = False
    last_id: int | None = None
