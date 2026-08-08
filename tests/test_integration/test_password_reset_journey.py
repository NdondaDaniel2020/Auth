"""Password recovery journey: request → confirm → login with new password — #52."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

OLD_PASSWORD = 'T3st!Passw0rd'
NEW_PASSWORD = 'NewPass456!'


def _capture_reset_email(monkeypatch) -> dict:
    captured: dict = {}

    async def fake_send(to_email: str, reset_link: str) -> None:
        captured['email'] = to_email
        captured['link'] = reset_link

    monkeypatch.setattr(
        'app.services.email_service.send_password_reset_email', fake_send
    )
    return captured


def _token_from_link(link: str) -> str:
    return parse_qs(urlparse(link).query)['token'][0]


def test_password_reset_journey(full_client: TestClient, monkeypatch) -> None:
    captured = _capture_reset_email(monkeypatch)

    # 1. Register and login to obtain a session
    full_client.post(
        '/auth/register',
        json={'email': 'recover@example.com', 'password': OLD_PASSWORD},
    )
    login = full_client.post(
        '/auth/login',
        json={'email': 'recover@example.com', 'password': OLD_PASSWORD},
    )
    assert login.status_code == 200
    refresh_before_reset = login.json()['refresh_token']

    # 2. Request a password reset
    request = full_client.post(
        '/auth/password-reset/request', json={'email': 'recover@example.com'}
    )
    assert request.status_code == 200
    assert captured['email'] == 'recover@example.com'

    # 3. Confirm the reset with the received token
    token = _token_from_link(captured['link'])
    confirm = full_client.post(
        '/auth/password-reset/confirm',
        json={'token': token, 'new_password': NEW_PASSWORD},
    )
    assert confirm.status_code == 200

    # 4. Old password fails, new password works
    old_login = full_client.post(
        '/auth/login',
        json={'email': 'recover@example.com', 'password': OLD_PASSWORD},
    )
    assert old_login.status_code == 401

    new_login = full_client.post(
        '/auth/login',
        json={'email': 'recover@example.com', 'password': NEW_PASSWORD},
    )
    assert new_login.status_code == 200

    # 5. Sessions from before the reset are invalidated
    stale_refresh = full_client.post(
        '/auth/refresh', json={'refresh_token': refresh_before_reset}
    )
    assert stale_refresh.status_code == 401
