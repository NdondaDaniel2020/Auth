"""Notification payload factories (re-exports from notification_service)."""

from __future__ import annotations

from app.services.notification_service import (
    create_deactivation_email,
    create_password_changed_email,
    create_password_reset_completed_email,
    create_password_reset_email,
    create_profile_updated_email,
    create_roles_changed_email,
    create_welcome_email,
)

__all__ = [
    'create_deactivation_email',
    'create_password_changed_email',
    'create_password_reset_completed_email',
    'create_password_reset_email',
    'create_profile_updated_email',
    'create_roles_changed_email',
    'create_welcome_email',
]
