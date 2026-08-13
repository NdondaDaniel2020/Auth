"""Notification payload factories.

Functions for constructing notification objects from event payloads.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.schemas.notification import (
    EmailNotification,
    NotificationPriority,
    PasswordChangedPayload,
    PasswordResetCompletedPayload,
    PasswordResetRequestedPayload,
    UserCreatedPayload,
    UserDeactivatedPayload,
    UserRolesChangedPayload,
    UserUpdatedPayload,
)



def create_welcome_email(user: UserCreatedPayload) -> EmailNotification:
    """Create welcome email for new user."""
    return EmailNotification(
        notification_id=f'welcome-{user.user_id}',
        priority=NotificationPriority.NORMAL,
        recipient_id=user.user_id,
        to_email=user.email,
        subject='Welcome to Auth API',
        template_id='welcome',
        template_data={
            'full_name': user.full_name or user.email.split('@')[0],
            'is_verified': user.is_verified,
            'temporary_password': user.temporary_password,
        },
    )


def create_profile_updated_email(
    user: UserUpdatedPayload,
) -> EmailNotification:
    """Create profile updated notification email."""
    return EmailNotification(
        notification_id=f'profile-updated-{user.user_id}',
        priority=NotificationPriority.NORMAL,
        recipient_id=user.user_id,
        to_email=user.email,
        subject='Your profile was updated',
        template_id='profile_updated',
        template_data={
            'changed_fields': user.changed_fields,
            'old_values': user.old_values,
            'new_values': user.new_values,
            'actor_id': user.actor_id,
        },
    )


def create_deactivation_email(
    user: UserDeactivatedPayload,
) -> EmailNotification:
    """Create account deactivation email."""
    return EmailNotification(
        notification_id=f'deactivated-{user.user_id}',
        priority=NotificationPriority.HIGH,
        recipient_id=user.user_id,
        to_email=user.email,
        subject='Your account has been deactivated',
        template_id='deactivated',
        template_data={
            'reason': user.reason,
            'actor_id': user.actor_id,
        },
    )


def create_roles_changed_email(
    user: UserRolesChangedPayload,
) -> EmailNotification:
    """Create roles changed notification email."""
    return EmailNotification(
        notification_id=f'roles-changed-{user.user_id}',
        priority=NotificationPriority.NORMAL,
        recipient_id=user.user_id,
        to_email=user.email,
        subject='Your account roles have been updated',
        template_id='roles_changed',
        template_data={
            'old_roles': user.old_roles,
            'new_roles': user.new_roles,
            'actor_id': user.actor_id,
        },
    )


def create_password_changed_email(
    user: PasswordChangedPayload,
) -> EmailNotification:
    """Create password changed notification email."""
    return EmailNotification(
        notification_id=f'password-changed-{user.user_id}',
        priority=NotificationPriority.HIGH,
        recipient_id=user.user_id,
        to_email=user.email,
        subject='Your password was changed',
        template_id='password_changed',
        template_data={
            'changed_by_self': user.changed_by_self,
            'actor_id': user.actor_id,
            'reason': user.reason,
        },
    )



def create_password_reset_email(
    reset: PasswordResetRequestedPayload,
) -> EmailNotification:
    """Create password reset email with reset link."""
    settings = get_settings()
    base_url = getattr(settings, 'APP_BASE_URL', 'http://localhost:8000')
    reset_link = f'{base_url}/auth/password-reset/confirm?token={reset.reset_token}'
    return EmailNotification(
        notification_id=f'password-reset-{reset.user_id}',
        priority=NotificationPriority.HIGH,
        recipient_id=reset.user_id,
        to_email=reset.email,
        subject='Reset your password',
        template_id='password_reset',
        template_data={
            'reset_link': reset_link,
            'expires_at': reset.expires_at.isoformat(),
            'client_ip': reset.client_ip,
        },
    )



def create_password_reset_completed_email(
    reset: PasswordResetCompletedPayload,
) -> EmailNotification:
    """Create password reset completed confirmation email."""
    return EmailNotification(
        notification_id=f'password-reset-completed-{reset.user_id}',
        priority=NotificationPriority.NORMAL,
        recipient_id=reset.user_id,
        to_email=reset.email,
        subject='Your password has been reset',
        template_id='password_reset_completed',
        template_data={
            'client_ip': reset.client_ip,
        },
    )
