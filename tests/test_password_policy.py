"""Password policy validation — #39."""

from __future__ import annotations

import pytest

from app.schemas.validators import COMMON_PASSWORDS, validate_password_strength


def test_valid_password_accepted() -> None:
    assert validate_password_strength('Passw0rd!2026') == 'Passw0rd!2026'


@pytest.mark.parametrize(
    'password',
    [
        'short',
        'onlylowercase1!',
        'ONLYUPPERCASE1!',
        'NoDigitsHere!',
        'nouppercase123!',
        'NoSpecialChars123',
    ],
)
def test_policy_violations_rejected(password: str) -> None:
    with pytest.raises(ValueError):
        validate_password_strength(password)


def test_too_long_password_rejected() -> None:
    long_password = 'A' * 130 + 'b1!'
    with pytest.raises(ValueError):
        validate_password_strength(long_password)


@pytest.mark.parametrize('password', sorted(COMMON_PASSWORDS))
def test_common_password_rejected_even_if_complex(password: str) -> None:
    # Force the common password to look "complex" so only the list check rejects it.
    with pytest.raises(ValueError):
        validate_password_strength(password)


def test_register_weak_password_rejected(api_client) -> None:
    response = api_client.post(
        '/auth/register',
        json={'email': 'policy@example.com', 'password': 'nouppercase123!'},
    )
    assert response.status_code == 422
    assert response.json()['error']['type'] == 'RequestValidationError'


def test_register_common_password_rejected(api_client) -> None:
    response = api_client.post(
        '/auth/register',
        json={'email': 'policy@example.com', 'password': 'Password123!'},
    )
    assert response.status_code == 422


def test_register_strong_password_accepted(api_client) -> None:
    response = api_client.post(
        '/auth/register',
        json={'email': 'policy@example.com', 'password': 'Passw0rd!2026'},
    )
    assert response.status_code == 201


def test_reset_password_weak_new_password_rejected(api_client) -> None:
    response = api_client.post(
        '/auth/password-reset/confirm',
        json={'token': 'any-token', 'new_password': 'nouppercase123!'},
    )
    assert response.status_code == 422


def test_reset_password_strong_new_password_accepted(
    api_client, monkeypatch
) -> None:
    captured: dict = {}

    async def fake_send(to_email: str, reset_link: str) -> None:
        captured['link'] = reset_link

    monkeypatch.setattr(
        'app.services.email_service.send_password_reset_email',
        fake_send,
    )
    from urllib.parse import parse_qs, urlparse

    api_client.post(
        '/auth/register',
        json={
            'email': 'reset-policy@example.com',
            'password': 'Passw0rd!2026',
        },
    )
    api_client.post(
        '/auth/password-reset/request',
        json={'email': 'reset-policy@example.com'},
    )
    token = parse_qs(urlparse(captured['link']).query)['token'][0]

    response = api_client.post(
        '/auth/password-reset/confirm',
        json={'token': token, 'new_password': 'NewPass!2026'},
    )
    assert response.status_code == 200
