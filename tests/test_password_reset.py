"""Endpoint tests for password reset flow — #20 recuperação, #21 redefinição."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

from sqlalchemy import select

from app.models.password_reset_token import PasswordResetToken
from app.utils.tokens import hash_token
from tests.conftest import run_in_isolated_db


def _capture_reset_email(monkeypatch) -> dict:
    captured: dict = {}

    async def fake_send(to_email: str, reset_link: str) -> None:
        captured['email'] = to_email
        captured['link'] = reset_link

    monkeypatch.setattr(
        'app.services.email_service.send_password_reset_email',
        fake_send,
    )
    return captured


def _token_from_link(link: str) -> str:
    return parse_qs(urlparse(link).query)['token'][0]


def test_request_reset_for_existing_email_sends_email(
    api_client,
    monkeypatch,
) -> None:
    captured = _capture_reset_email(monkeypatch)

    assert (
        api_client.post(
            '/auth/register',
            json={'email': 'reset@example.com', 'password': 'password123'},
        ).status_code
        == 201
    )

    response = api_client.post(
        '/auth/password-reset/request',
        json={'email': 'reset@example.com'},
    )
    assert response.status_code == 200
    assert captured['email'] == 'reset@example.com'
    assert 'token=' in captured['link']


def test_request_reset_for_unknown_email_is_generic(
    api_client, monkeypatch
) -> None:
    captured = _capture_reset_email(monkeypatch)

    response = api_client.post(
        '/auth/password-reset/request',
        json={'email': 'ghost@example.com'},
    )
    assert response.status_code == 200
    assert captured == {}


def test_reset_password_with_valid_token(api_client, monkeypatch) -> None:
    captured = _capture_reset_email(monkeypatch)

    api_client.post(
        '/auth/register',
        json={'email': 'reset@example.com', 'password': 'password123'},
    )
    api_client.post(
        '/auth/password-reset/request',
        json={'email': 'reset@example.com'},
    )
    token = _token_from_link(captured['link'])

    response = api_client.post(
        '/auth/password-reset/confirm',
        json={'token': token, 'new_password': 'newpassword456'},
    )
    assert response.status_code == 200

    old_login = api_client.post(
        '/auth/login',
        json={'email': 'reset@example.com', 'password': 'password123'},
    )
    assert old_login.status_code == 401

    new_login = api_client.post(
        '/auth/login',
        json={'email': 'reset@example.com', 'password': 'newpassword456'},
    )
    assert new_login.status_code == 200


def test_reset_password_revokes_refresh_tokens(
    api_client, monkeypatch
) -> None:
    captured = _capture_reset_email(monkeypatch)

    api_client.post(
        '/auth/register',
        json={'email': 'reset@example.com', 'password': 'password123'},
    )
    login = api_client.post(
        '/auth/login',
        json={'email': 'reset@example.com', 'password': 'password123'},
    ).json()
    api_client.post(
        '/auth/password-reset/request',
        json={'email': 'reset@example.com'},
    )
    token = _token_from_link(captured['link'])
    api_client.post(
        '/auth/password-reset/confirm',
        json={'token': token, 'new_password': 'newpassword456'},
    )

    stale_refresh = api_client.post(
        '/auth/refresh',
        json={'refresh_token': login['refresh_token']},
    )
    assert stale_refresh.status_code == 401


def test_reset_password_with_expired_token_rejected(
    api_client, isolated_db_path
) -> None:
    async def _make_expired_token(factory):
        async with factory() as session:
            from app.core.security import hash_password
            from app.models.user import User

            session.add(
                User(
                    email='expired@example.com',
                    hashed_password=hash_password('password123'),
                )
            )
            await session.flush()
            user = (await session.execute(select(User))).scalar_one()
            session.add(
                PasswordResetToken(
                    user_id=user.id,
                    token_hash=hash_token('expired-token'),
                    expires_at=datetime.now(UTC) - timedelta(minutes=5),
                )
            )
            await session.commit()

    run_in_isolated_db(isolated_db_path, _make_expired_token)

    response = api_client.post(
        '/auth/password-reset/confirm',
        json={'token': 'expired-token', 'new_password': 'newpassword456'},
    )
    assert response.status_code == 400
    assert response.json()['error']['type'] == 'InvalidOrExpiredTokenError'


def test_reset_password_with_invalid_token_rejected(api_client) -> None:
    response = api_client.post(
        '/auth/password-reset/confirm',
        json={'token': 'garbage-token', 'new_password': 'newpassword456'},
    )
    assert response.status_code == 400
    assert response.json()['error']['type'] == 'InvalidOrExpiredTokenError'


def test_reset_password_token_is_single_use(api_client, monkeypatch) -> None:
    captured = _capture_reset_email(monkeypatch)

    api_client.post(
        '/auth/register',
        json={'email': 'reset@example.com', 'password': 'password123'},
    )
    api_client.post(
        '/auth/password-reset/request',
        json={'email': 'reset@example.com'},
    )
    token = _token_from_link(captured['link'])

    first = api_client.post(
        '/auth/password-reset/confirm',
        json={'token': token, 'new_password': 'newpassword456'},
    )
    assert first.status_code == 200

    second = api_client.post(
        '/auth/password-reset/confirm',
        json={'token': token, 'new_password': 'anotherpass789'},
    )
    assert second.status_code == 400
    assert second.json()['error']['type'] == 'TokenAlreadyUsedError'
