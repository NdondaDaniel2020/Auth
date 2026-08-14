"""Unit tests for notification_factory_service payload creators."""

from __future__ import annotations

from datetime import UTC, datetime

from app.schemas.notification import (
    NotificationPriority,
    PasswordChangedPayload,
    PasswordResetCompletedPayload,
    PasswordResetRequestedPayload,
    UserCreatedPayload,
    UserDeactivatedPayload,
    UserRolesChangedPayload,
    UserUpdatedPayload,
)
from app.services.notification_factory_service import (
    create_deactivation_email,
    create_password_changed_email,
    create_password_reset_completed_email,
    create_password_reset_email,
    create_profile_updated_email,
    create_roles_changed_email,
    create_welcome_email,
)


def test_create_welcome_email_with_full_name() -> None:
    payload = UserCreatedPayload(
        user_id='usr-123',
        email='john.doe@example.com',
        full_name='John Doe',
        is_verified=False,
    )
    notification = create_welcome_email(payload)

    assert notification.notification_id == 'welcome-usr-123'
    assert notification.recipient_id == 'usr-123'
    assert notification.to_email == 'john.doe@example.com'
    assert notification.priority == NotificationPriority.NORMAL
    assert notification.template_id == 'welcome'
    assert notification.template_data['full_name'] == 'John Doe'
    assert notification.template_data['is_verified'] is False


def test_create_welcome_email_with_verify_link() -> None:
    payload = UserCreatedPayload(
        user_id='usr-789',
        email='bob@example.com',
        full_name='Bob',
        is_verified=False,
        verify_link='http://localhost:8000/auth/verify-email?token=xyz',
    )
    notification = create_welcome_email(payload)

    assert (
        notification.template_data['verify_link']
        == 'http://localhost:8000/auth/verify-email?token=xyz'
    )


def test_create_welcome_email_without_full_name_uses_email_prefix() -> None:
    payload = UserCreatedPayload(
        user_id='usr-456',
        email='alice@example.com',
        full_name=None,
        is_verified=True,
    )
    notification = create_welcome_email(payload)

    assert notification.template_data['full_name'] == 'alice'
    assert notification.template_data['is_verified'] is True


def test_create_profile_updated_email() -> None:
    payload = UserUpdatedPayload(
        user_id='usr-123',
        email='john.doe@example.com',
        changed_fields=['full_name'],
        old_values={'full_name': 'John'},
        new_values={'full_name': 'John Doe'},
        actor_id='actor-001',
    )
    notification = create_profile_updated_email(payload)

    assert notification.notification_id == 'profile-updated-usr-123'
    assert notification.recipient_id == 'usr-123'
    assert notification.to_email == 'john.doe@example.com'
    assert notification.template_id == 'profile_updated'
    assert notification.template_data['changed_fields'] == ['full_name']
    assert notification.template_data['actor_id'] == 'actor-001'


def test_create_deactivation_email() -> None:
    payload = UserDeactivatedPayload(
        user_id='usr-123',
        email='user@example.com',
        actor_id='admin-1',
        reason='Violated terms of service',
    )
    notification = create_deactivation_email(payload)

    assert notification.notification_id == 'deactivated-usr-123'
    assert notification.priority == NotificationPriority.HIGH
    assert notification.template_id == 'deactivated'
    assert notification.template_data['reason'] == 'Violated terms of service'
    assert notification.template_data['actor_id'] == 'admin-1'


def test_create_roles_changed_email() -> None:
    payload = UserRolesChangedPayload(
        user_id='usr-123',
        email='user@example.com',
        old_roles=['user'],
        new_roles=['user', 'admin'],
        actor_id='admin-1',
    )
    notification = create_roles_changed_email(payload)

    assert notification.notification_id == 'roles-changed-usr-123'
    assert notification.template_id == 'roles_changed'
    assert notification.template_data['old_roles'] == ['user']
    assert notification.template_data['new_roles'] == ['user', 'admin']
    assert notification.template_data['actor_id'] == 'admin-1'


def test_create_password_changed_email() -> None:
    payload = PasswordChangedPayload(
        user_id='usr-123',
        email='user@example.com',
        changed_by_self=True,
        actor_id='usr-123',
        reason='User updated password in security settings',
    )
    notification = create_password_changed_email(payload)

    assert notification.notification_id == 'password-changed-usr-123'
    assert notification.priority == NotificationPriority.HIGH
    assert notification.template_id == 'password_changed'
    assert notification.template_data['changed_by_self'] is True
    assert notification.template_data['actor_id'] == 'usr-123'


def test_create_password_reset_email() -> None:
    now = datetime.now(UTC)
    payload = PasswordResetRequestedPayload(
        user_id='usr-123',
        email='user@example.com',
        reset_token='reset-token-xyz',
        expires_at=now,
        client_ip='127.0.0.1',
    )
    notification = create_password_reset_email(payload)

    assert notification.notification_id == 'password-reset-usr-123'
    assert notification.priority == NotificationPriority.HIGH
    assert notification.template_id == 'password_reset'
    assert 'reset-token-xyz' in notification.template_data['reset_link']
    assert notification.template_data['expires_at'] == now.isoformat()
    assert notification.template_data['client_ip'] == '127.0.0.1'


def test_create_password_reset_completed_email() -> None:
    payload = PasswordResetCompletedPayload(
        user_id='usr-123',
        email='user@example.com',
        client_ip='192.168.1.1',
    )
    notification = create_password_reset_completed_email(payload)

    assert notification.notification_id == 'password-reset-completed-usr-123'
    assert notification.priority == NotificationPriority.NORMAL
    assert notification.template_id == 'password_reset_completed'
    assert notification.template_data['client_ip'] == '192.168.1.1'
