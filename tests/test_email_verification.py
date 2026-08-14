"""Endpoint tests for e-mail verification — #22 verificação de e-mail."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from sqlalchemy import select

from app.models.user import User
from tests.conftest import run_in_isolated_db


def _capture_verification_email(monkeypatch) -> dict:
    captured: dict = {}

    async def fake_send_smtp(to_email: str, subject: str, html: str) -> None:
        captured['email'] = to_email
        if 'href="' in html:
            start = html.find('href="') + 6
            end = html.find('"', start)
            captured['link'] = html[start:end]

    async def fake_send_verification(to_email: str, verify_link: str) -> None:
        captured['email'] = to_email
        captured['link'] = verify_link

    monkeypatch.setattr(
        'app.services.email_service._send_via_smtp',
        fake_send_smtp,
    )
    monkeypatch.setattr(
        'app.services.email_service.send_verification_email',
        fake_send_verification,
    )
    return captured


def _token_from_link(link: str) -> str:
    return parse_qs(urlparse(link).query)['token'][0]


def _register(api_client, email: str = 'verify@example.com') -> None:
    response = api_client.post(
        '/auth/register',
        json={'email': email, 'password': 'T3st!Passw0rd'},
    )
    assert response.status_code == 201


def test_register_sends_verification_email(api_client, monkeypatch) -> None:
    captured = _capture_verification_email(monkeypatch)
    _register(api_client)
    assert captured['email'] == 'verify@example.com'
    assert 'token=' in captured['link']


def test_user_starts_unverified(api_client, isolated_db_path) -> None:
    _register(api_client)

    async def _check(factory):
        async with factory() as session:
            user = (await session.execute(select(User))).scalar_one()
            assert user.is_verified is False

    run_in_isolated_db(isolated_db_path, _check)


def test_verify_email_success(
    api_client, monkeypatch, isolated_db_path
) -> None:
    captured = _capture_verification_email(monkeypatch)
    _register(api_client)
    token = _token_from_link(captured['link'])

    response = api_client.post('/auth/verify-email', json={'token': token})
    assert response.status_code == 200

    async def _check(factory):
        async with factory() as session:
            user = (await session.execute(select(User))).scalar_one()
            assert user.is_verified is True

    run_in_isolated_db(isolated_db_path, _check)


def test_verify_email_token_is_single_use(api_client, monkeypatch) -> None:
    captured = _capture_verification_email(monkeypatch)
    _register(api_client)
    token = _token_from_link(captured['link'])

    assert (
        api_client.post(
            '/auth/verify-email', json={'token': token}
        ).status_code
        == 200
    )
    second = api_client.post('/auth/verify-email', json={'token': token})
    assert second.status_code == 400
    assert second.json()['error']['type'] == 'TokenAlreadyUsedError'
    assert second.json()['error']['code'] == 'TOKEN_ALREADY_USED'


def test_verify_email_with_invalid_token_rejected(api_client) -> None:
    response = api_client.post(
        '/auth/verify-email', json={'token': 'garbage-token'}
    )
    assert response.status_code == 400
    assert response.json()['error']['type'] == 'InvalidOrExpiredTokenError'
    assert response.json()['error']['code'] == 'INVALID_OR_EXPIRED_TOKEN'


def test_resend_verification_for_unverified_user(
    api_client, monkeypatch
) -> None:
    captured = _capture_verification_email(monkeypatch)
    _register(api_client)
    captured.clear()

    response = api_client.post(
        '/auth/verify-email/resend',
        json={'email': 'verify@example.com'},
    )
    assert response.status_code == 200
    assert captured['email'] == 'verify@example.com'


def test_resend_verification_skips_verified_user(
    api_client, monkeypatch
) -> None:
    captured = _capture_verification_email(monkeypatch)
    _register(api_client)
    token = _token_from_link(captured['link'])
    assert (
        api_client.post(
            '/auth/verify-email', json={'token': token}
        ).status_code
        == 200
    )
    captured.clear()

    response = api_client.post(
        '/auth/verify-email/resend',
        json={'email': 'verify@example.com'},
    )
    assert response.status_code == 200
    assert captured == {}


def test_resend_verification_for_unknown_email_is_generic(
    api_client, monkeypatch
) -> None:
    captured = _capture_verification_email(monkeypatch)

    response = api_client.post(
        '/auth/verify-email/resend',
        json={'email': 'ghost@example.com'},
    )
    assert response.status_code == 200
    assert captured == {}
