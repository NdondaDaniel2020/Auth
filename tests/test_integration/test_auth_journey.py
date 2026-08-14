"""Full authentication journey: register → verify → login → refresh → logout — #52.

This is the canonical happy path across every auth endpoint, protecting
against regressions that isolated per-feature tests could miss.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

PASSWORD = 'T3st!Passw0rd'


def _capture_verification_email(monkeypatch) -> dict:
    captured: dict = {}

    async def fake_send_smtp(to_email: str, subject: str, html: str) -> None:
        captured['email'] = to_email
        if 'href="' in html:
            start = html.find('href="') + 6
            end = html.find('"', start)
            captured['link'] = html[start:end]

    async def fake_send(to_email: str, verify_link: str) -> None:
        captured['email'] = to_email
        captured['link'] = verify_link

    monkeypatch.setattr(
        'app.services.email_service._send_via_smtp', fake_send_smtp
    )
    monkeypatch.setattr(
        'app.services.email_service.send_verification_email', fake_send
    )
    return captured


def _token_from_link(link: str) -> str:
    return parse_qs(urlparse(link).query)['token'][0]


def test_full_authentication_journey(
    full_client: TestClient, monkeypatch
) -> None:
    captured = _capture_verification_email(monkeypatch)

    # 1. Register
    register = full_client.post(
        '/auth/register',
        json={'email': 'journey@example.com', 'password': PASSWORD},
    )
    assert register.status_code == 201
    user_id = register.json()['id']
    assert captured['email'] == 'journey@example.com'

    # 2. Verify e-mail with the token embedded in the sent link
    token = _token_from_link(captured['link'])
    verify = full_client.post('/auth/verify-email', json={'token': token})
    assert verify.status_code == 200

    # 3. Login
    login = full_client.post(
        '/auth/login',
        json={'email': 'journey@example.com', 'password': PASSWORD},
    )
    assert login.status_code == 200
    access_token = login.json()['access_token']
    refresh_token = login.json()['refresh_token']

    # 4. Access a protected route
    me = full_client.get(
        '/users/me', headers={'Authorization': f'Bearer {access_token}'}
    )
    assert me.status_code == 200
    assert me.json()['id'] == user_id
    assert me.json()['is_verified'] is True

    # 5. Refresh (rotation)
    refreshed = full_client.post(
        '/auth/refresh', json={'refresh_token': refresh_token}
    )
    assert refreshed.status_code == 200
    assert refreshed.json()['refresh_token'] != refresh_token

    # 6. Logout
    logout = full_client.post(
        '/auth/logout', json={'refresh_token': refresh_token}
    )
    assert logout.status_code == 204

    # 7. Refresh after logout is rejected
    stale = full_client.post(
        '/auth/refresh', json={'refresh_token': refresh_token}
    )
    assert stale.status_code == 401
    assert stale.json()['error']['code'] == 'INVALID_REFRESH_TOKEN'
