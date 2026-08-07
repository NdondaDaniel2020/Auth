"""Reusable password policy validation.

The exact criteria are read from ``Settings`` so the policy can be tuned
without code changes. ``validate_password_strength`` is called from every
schema that sets a new password (registration, password reset).
"""

from __future__ import annotations

import re

from app.core.config import get_settings

_UPPERCASE_RE = re.compile(r'[A-Z]')
_LOWERCASE_RE = re.compile(r'[a-z]')
_DIGIT_RE = re.compile(r'[0-9]')
_SPECIAL_RE = re.compile(r'[^A-Za-z0-9]')

# Commonly used (and therefore weak) passwords, checked case-insensitively.
COMMON_PASSWORDS = frozenset({
    'password',
    'password1',
    'password123',
    'password1234',
    '12345678',
    '123456789',
    '1234567890',
    'qwerty123',
    'qwertyuiop',
    'abc12345',
    'letmein',
    'admin123',
    'admin1234',
    'welcome1',
    'iloveyou',
    'monkey123',
    'dragon123',
    'football1',
    'whatever1',
    'superman1',
    'password123!',
    'passw0rd',
    'qwerty123!',
    'admin123!',
})


def validate_password_strength(password: str) -> str:
    """Validate ``password`` against the configured password policy.

    Returns the password unchanged when it complies; raises ``ValueError``
    (mapped by Pydantic to a 422 validation error) otherwise.
    """
    settings = get_settings()

    if len(password) < settings.PASSWORD_MIN_LENGTH:
        raise ValueError(
            f'Password must be at least {settings.PASSWORD_MIN_LENGTH} '
            'characters long'
        )

    if len(password) > settings.PASSWORD_MAX_LENGTH:
        raise ValueError(
            f'Password must be at most {settings.PASSWORD_MAX_LENGTH} '
            'characters long'
        )

    if (
        settings.PASSWORD_REJECT_COMMON
        and password.lower() in COMMON_PASSWORDS
    ):
        raise ValueError(
            'Password is too common. Choose a more unique password'
        )

    missing: list[str] = []
    if settings.PASSWORD_REQUIRE_UPPERCASE and not _UPPERCASE_RE.search(
        password
    ):
        missing.append('an uppercase letter')
    if settings.PASSWORD_REQUIRE_LOWERCASE and not _LOWERCASE_RE.search(
        password
    ):
        missing.append('a lowercase letter')
    if settings.PASSWORD_REQUIRE_DIGIT and not _DIGIT_RE.search(password):
        missing.append('a digit')
    if settings.PASSWORD_REQUIRE_SPECIAL and not _SPECIAL_RE.search(password):
        missing.append('a special character')

    if missing:
        raise ValueError(f'Password must contain {", ".join(missing)}')

    return password
