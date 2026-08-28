"""Email event consumer - subscribes to domain events and sends emails."""

from __future__ import annotations

import logging

from app.messaging.base import Event
from app.messaging.buses import get_event_bus
from app.messaging.events.auth_events import AuthEvents
from app.messaging.events.user_events import UserEvents
from app.schemas.notification import (
    EmailNotification,
    EmailVerificationRequestedPayload,
    EmailVerifiedPayload,
    PasswordChangedPayload,
    PasswordResetCompletedPayload,
    PasswordResetRequestedPayload,
    UserCreatedPayload,
    UserDeactivatedPayload,
    UserRolesChangedPayload,
    UserUpdatedPayload,
)
from app.services.notification_service import (
    create_deactivation_email,
    create_password_changed_email,
    create_password_reset_completed_email,
    create_profile_updated_email,
    create_roles_changed_email,
    create_welcome_email,
)

logger = logging.getLogger(__name__)


class EmailConsumer:
    """Consumes domain events and triggers email notifications."""

    def __init__(self) -> None:
        self._subscribed = False

    async def subscribe(self) -> None:
        """Subscribe to relevant domain events."""
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
        await bus.subscribe(
            AuthEvents.EMAIL_VERIFICATION_REQUESTED,
            self._handle_email_verification_requested,
        )

        self._subscribed = True
        logger.info('EmailConsumer subscribed to domain events')

    async def unsubscribe(self) -> None:
        """Unsubscribe from events."""
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
        await bus.unsubscribe(
            AuthEvents.EMAIL_VERIFICATION_REQUESTED,
            self._handle_email_verification_requested,
        )

        self._subscribed = False
        logger.info('EmailConsumer unsubscribed from domain events')

    async def _handle_user_created(self, event: Event) -> None:
        payload = UserCreatedPayload(**event.payload)
        logger.info('Sending welcome email for user %s', payload.user_id)
        email = create_welcome_email(payload)
        await self._send_email(email)

    async def _handle_user_updated(self, event: Event) -> None:
        payload = UserUpdatedPayload(**event.payload)
        logger.info(
            'Sending profile updated email for user %s', payload.user_id
        )
        email = create_profile_updated_email(payload)
        await self._send_email(email)

    async def _handle_user_deactivated(self, event: Event) -> None:
        payload = UserDeactivatedPayload(**event.payload)
        logger.info('Sending deactivation email for user %s', payload.user_id)
        email = create_deactivation_email(payload)
        await self._send_email(email)

    async def _handle_user_roles_changed(self, event: Event) -> None:
        payload = UserRolesChangedPayload(**event.payload)
        logger.info('Sending roles changed email for user %s', payload.user_id)
        email = create_roles_changed_email(payload)
        await self._send_email(email)

    async def _handle_password_changed(self, event: Event) -> None:
        payload = PasswordChangedPayload(**event.payload)
        logger.info(
            'Sending password changed email for user %s', payload.user_id
        )
        email = create_password_changed_email(payload)
        await self._send_email(email)

    async def _handle_email_verified(self, event: Event) -> None:
        payload = EmailVerifiedPayload(**event.payload)
        logger.info('Email verified for user %s', payload.user_id)

    async def _handle_password_reset_requested(self, event: Event) -> None:
        from app.core.config import get_settings
        from app.services import email_service

        payload = PasswordResetRequestedPayload(**event.payload)
        logger.info(
            'Sending password reset email for user %s',
            payload.user_id,
        )
        settings = get_settings()
        base_url = getattr(settings, 'APP_BASE_URL', 'http://localhost:8000')
        reset_link = f'{base_url}/auth/password-reset/confirm?token={payload.reset_token}'
        await email_service.send_password_reset_email(
            payload.email, reset_link
        )

    async def _handle_password_reset_completed(self, event: Event) -> None:
        payload = PasswordResetCompletedPayload(**event.payload)
        logger.info(
            'Sending password reset completed email for user %s',
            payload.user_id,
        )
        email = create_password_reset_completed_email(payload)
        await self._send_email(email)

    async def _handle_email_verification_requested(self, event: Event) -> None:
        from app.core.config import get_settings
        from app.services import email_service

        payload = EmailVerificationRequestedPayload(**event.payload)
        logger.info(
            'Sending email verification link for user %s',
            payload.user_id,
        )
        settings = get_settings()
        base_url = getattr(settings, 'APP_BASE_URL', 'http://localhost:8000')
        verify_link = (
            f'{base_url}/auth/verify-email?token={payload.verify_token}'
        )
        await email_service.send_verification_email(payload.email, verify_link)

    async def _send_email(self, email: EmailNotification) -> None:
        from app.services.email_service import _send_via_smtp, render_template

        html_content = email.html_body
        if not html_content and email.template_id:
            template_data = getattr(email, 'template_data', {}) or {}
            html_content = render_template(email.template_id, **template_data)

        await _send_via_smtp(email.to_email, email.subject, html_content or '')


_email_consumer: EmailConsumer | None = None


def get_email_consumer() -> EmailConsumer:
    """Get global EmailConsumer instance."""
    global _email_consumer
    if _email_consumer is None:
        _email_consumer = EmailConsumer()
    return _email_consumer
