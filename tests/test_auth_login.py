"""Endpoint tests for POST /auth/login — #17 login com JWT."""

from __future__ import annotations

from app.core.security import (
    decode_access_token,
    decode_refresh_token,
    hash_password,
)
from app.models.user import User
from tests.conftest import run_in_isolated_db


def _register(
    api_client, email: str = 'login@example.com', password: str = 'password123'
):
    response = api_client.post(
        '/auth/register',
        json={'email': email, 'password': password},
    )
    assert response.status_code == 201
    return response.json()


def test_login_success_returns_valid_tokens(api_client) -> None:
    user = _register(api_client)

    response = api_client.post(
        '/auth/login',
        json={'email': 'login@example.com', 'password': 'password123'},
    )
    assert response.status_code == 200

    body = response.json()
    assert body['token_type'] == 'bearer'
    assert body['access_token']
    assert body['refresh_token']

    access_payload = decode_access_token(body['access_token'])
    assert access_payload['sub'] == user['id']
    assert access_payload['type'] == 'access'

    refresh_payload = decode_refresh_token(body['refresh_token'])
    assert refresh_payload['sub'] == user['id']
    assert refresh_payload['jti']


def test_login_wrong_password_rejected(api_client) -> None:
    _register(api_client)
    response = api_client.post(
        '/auth/login',
        json={'email': 'login@example.com', 'password': 'wrongpass'},
    )
    assert response.status_code == 401
    assert response.json()['error']['type'] == 'InvalidCredentialsError'


def test_login_form_success_returns_valid_tokens(api_client) -> None:
    user = _register(api_client, email='form@example.com')

    response = api_client.post(
        '/auth/login-form',
        data={'username': 'form@example.com', 'password': 'password123'},
    )
    assert response.status_code == 200

    body = response.json()
    assert body['token_type'] == 'bearer'
    assert body['access_token']
    assert body['refresh_token']

    access_payload = decode_access_token(body['access_token'])
    assert access_payload['sub'] == user['id']
    assert access_payload['type'] == 'access'


def test_login_form_wrong_password_rejected(api_client) -> None:
    _register(api_client, email='form-wrong@example.com')
    response = api_client.post(
        '/auth/login-form',
        data={'username': 'form-wrong@example.com', 'password': 'wrongpass'},
    )
    assert response.status_code == 401
    assert response.json()['error']['type'] == 'InvalidCredentialsError'


def test_login_form_unknown_email_rejected(api_client) -> None:
    response = api_client.post(
        '/auth/login-form',
        data={'username': 'nobody@example.com', 'password': 'password123'},
    )
    assert response.status_code == 401
    assert response.json()['error']['type'] == 'InvalidCredentialsError'


def test_login_unknown_email_rejected(api_client) -> None:
    response = api_client.post(
        '/auth/login',
        json={'email': 'nobody@example.com', 'password': 'password123'},
    )
    assert response.status_code == 401
    assert response.json()['error']['type'] == 'InvalidCredentialsError'


def test_login_inactive_user_rejected(api_client, isolated_db_path) -> None:
    async def _make_inactive_user(factory):
        async with factory() as session:
            session.add(
                User(
                    email='inactive@example.com',
                    hashed_password=hash_password('password123'),
                    is_active=False,
                )
            )
            await session.commit()

    run_in_isolated_db(isolated_db_path, _make_inactive_user)

    response = api_client.post(
        '/auth/login',
        json={'email': 'inactive@example.com', 'password': 'password123'},
    )
    assert response.status_code == 401


def test_login_blocks_after_repeated_failures(api_client) -> None:
    _register(api_client, email='brute@example.com')

    for _ in range(5):
        attempt = api_client.post(
            '/auth/login',
            json={'email': 'brute@example.com', 'password': 'wrongpass'},
        )
        assert attempt.status_code == 401

    blocked = api_client.post(
        '/auth/login',
        json={'email': 'brute@example.com', 'password': 'password123'},
    )
    assert blocked.status_code == 429
    assert blocked.json()['error']['type'] == 'TooManyLoginAttemptsError'
    assert blocked.headers.get('Retry-After')


def test_successful_login_resets_failed_attempts(api_client) -> None:
    _register(api_client, email='reset-counter@example.com')

    for _ in range(3):
        assert (
            api_client.post(
                '/auth/login',
                json={
                    'email': 'reset-counter@example.com',
                    'password': 'wrongpass',
                },
            ).status_code
            == 401
        )

    ok = api_client.post(
        '/auth/login',
        json={'email': 'reset-counter@example.com', 'password': 'password123'},
    )
    assert ok.status_code == 200

    for _ in range(5):
        assert (
            api_client.post(
                '/auth/login',
                json={
                    'email': 'reset-counter@example.com',
                    'password': 'wrongpass',
                },
            ).status_code
            == 401
        )
