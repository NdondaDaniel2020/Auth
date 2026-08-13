"""Notification service - subscribes to domain events and sends notifications."""

from __future__ import annotations

import logging
from typing import Any

from app.core.events import (
    AuthEvents,
    UserEvents,
    get_event_bus,
)
from app.schemas.notification import (
    EmailVerifiedPayload,
    PasswordChangedPayload,
    PasswordResetCompletedPayload,
    PasswordResetRequestedPayload,
    UserCreatedPayload,
    UserDeactivatedPayload,
    UserRolesChangedPayload,
    UserUpdatedPayload,
)
from app.services.email_service import (
    send_password_reset_email,
)
from app.services.notification_factory_service import (
    create_deactivation_email,
    create_password_changed_email,
    create_password_reset_completed_email,
    create_profile_updated_email,
    create_roles_changed_email,
    create_welcome_email,
)

logger = logging.getLogger(__name__)


class NotificationService:
    """Handles notification delivery for domain events."""

    def __init__(self) -> None:
        self._subscribed = False

    async def subscribe(self) -> None:
        """Subscribe to all relevant domain events."""
        if self._subscribed:
            return

        bus = get_event_bus()

        # User lifecycle events
        await bus.subscribe(UserEvents.CREATED, self._handle_user_created)
        await bus.subscribe(UserEvents.UPDATED, self._handle_user_updated)
        await bus.subscribe(
            UserEvents.DEACTIVATED, self._handle_user_deactivated
        )
        await bus.subscribe(
            UserEvents.ROLES_CHANGED, self._handle_user_roles_changed
        )
        await bus.subscribe(
            UserEvents.PASSWORD_CHANGED, self._handle_password_changed
        )
        await bus.subscribe(
            UserEvents.EMAIL_VERIFIED, self._handle_email_verified
        )

        # Auth events
        await bus.subscribe(
            AuthEvents.PASSWORD_RESET_REQUESTED,
            self._handle_password_reset_requested,
        )
        await bus.subscribe(
            AuthEvents.PASSWORD_RESET_COMPLETED,
            self._handle_password_reset_completed,
        )

        self._subscribed = True
        logger.info('NotificationService subscribed to domain events')

    async def unsubscribe(self) -> None:
        """Unsubscribe from all events."""
        if not self._subscribed:
            return

        bus = get_event_bus()

        await bus.unsubscribe(UserEvents.CREATED, self._handle_user_created)
        await bus.unsubscribe(UserEvents.UPDATED, self._handle_user_updated)
        await bus.unsubscribe(
            UserEvents.DEACTIVATED, self._handle_user_deactivated
        )
        await bus.unsubscribe(
            UserEvents.ROLES_CHANGED, self._handle_user_roles_changed
        )
        await bus.unsubscribe(
            UserEvents.PASSWORD_CHANGED, self._handle_password_changed
        )
        await bus.unsubscribe(
            UserEvents.EMAIL_VERIFIED, self._handle_email_verified
        )
        await bus.unsubscribe(
            AuthEvents.PASSWORD_RESET_REQUESTED,
            self._handle_password_reset_requested,
        )
        await bus.unsubscribe(
            AuthEvents.PASSWORD_RESET_COMPLETED,
            self._handle_password_reset_completed,
        )

        self._subscribed = False
        logger.info('NotificationService unsubscribed from domain events')

    # --- Event handlers ---

    async def _handle_user_created(self, event: dict[str, Any]) -> None:
        """Handle user.created - send welcome email."""
        payload = UserCreatedPayload(**event['payload'])
        logger.info('Sending welcome email for user %s', payload.user_id)
        email = create_welcome_email(payload)
        await self._send_email(email)

    async def _handle_user_updated(self, event: dict[str, Any]) -> None:
        """Handle user.updated - send profile updated email."""
        payload = UserUpdatedPayload(**event['payload'])
        logger.info(
            'Sending profile updated email for user %s', payload.user_id
        )
        email = create_profile_updated_email(payload)
        await self._send_email(email)

    async def _handle_user_deactivated(self, event: dict[str, Any]) -> None:
        """Handle user.deactivated - send deactivation email."""
        payload = UserDeactivatedPayload(**event['payload'])
        logger.info('Sending deactivation email for user %s', payload.user_id)
        email = create_deactivation_email(payload)
        await self._send_email(email)

    async def _handle_user_roles_changed(self, event: dict[str, Any]) -> None:
        """Handle user.roles_changed - send roles changed email."""
        payload = UserRolesChangedPayload(**event['payload'])
        logger.info('Sending roles changed email for user %s', payload.user_id)
        email = create_roles_changed_email(payload)
        await self._send_email(email)

    async def _handle_password_changed(self, event: dict[str, Any]) -> None:
        """Handle user.password_changed - send password changed email."""
        payload = PasswordChangedPayload(**event['payload'])
        logger.info(
            'Sending password changed email for user %s', payload.user_id
        )
        email = create_password_changed_email(payload)
        await self._send_email(email)

    async def _handle_email_verified(self, event: dict[str, Any]) -> None:
        """Handle user.email_verified - could send confirmation."""
        payload = EmailVerifiedPayload(**event['payload'])
        logger.info('Email verified for user %s', payload.user_id)
        # Optionally send confirmation email

    async def _handle_password_reset_requested(
        self, event: dict[str, Any]
    ) -> None:
        """Handle auth.password_reset_requested - log notification event."""
        payload = PasswordResetRequestedPayload(**event['payload'])
        logger.info(
            'Password reset requested notification event processed for user %s', payload.user_id
        )


    async def _handle_password_reset_completed(
        self, event: dict[str, Any]
    ) -> None:
        """Handle auth.password_reset_completed - send confirmation email."""
        payload = PasswordResetCompletedPayload(**event['payload'])
        logger.info(
            'Sending password reset completed email for user %s',
            payload.user_id,
        )
        email = create_password_reset_completed_email(payload)
        await self._send_email(email)

    async def _send_email(self, email) -> None:
        """Send email via email_service (which handles SMTP or logging)."""
        from app.services.email_service import _send_via_smtp, render_template

        html_content = email.html_body
        if not html_content and getattr(email, 'template_id', None):
            template_data = getattr(email, 'template_data', {}) or {}
            html_content = render_template(email.template_id, **template_data)

        await _send_via_smtp(email.to_email, email.subject, html_content or '')


_notification_service: NotificationService | None = None


def get_notification_service() -> NotificationService:
    """Get the global notification service instance."""
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service


async def setup_notifications() -> None:
    """Initialize and subscribe notification service."""
    service = get_notification_service()
    await service.subscribe()


async def teardown_notifications() -> None:
    """Cleanup notification service."""
    global _notification_service
    if _notification_service:
        await _notification_service.unsubscribe()
        _notification_service = None
