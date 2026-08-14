"""Security event logging tests — #41."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator

import pytest

from app.core.security_logger import SECURITY_LOGGER_NAME, get_security_logger


class _RecordHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def security_logs() -> Iterator[list[logging.LogRecord]]:
    logger = get_security_logger()
    handler = _RecordHandler()
    previous_level = logger.level
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    try:
        yield handler.records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)


def _events(records: list[logging.LogRecord]) -> list[dict]:
    return [
        {'event': r.getMessage(), **getattr(r, 'security_fields', {})}
        for r in records
        if r.name == SECURITY_LOGGER_NAME
    ]


def _formatted(records: list[logging.LogRecord]) -> str:
    formatter = get_security_logger().handlers[0].formatter
    return '\n'.join(formatter.format(r) for r in records)


def _register(api_client, email: str = 'events@example.com'):
    response = api_client.post(
        '/auth/register',
        json={'email': email, 'password': 'T3st!Passw0rd'},
    )
    assert response.status_code == 201
    return response.json()


def test_login_success_logs_event(api_client, security_logs) -> None:
    user = _register(api_client)

    response = api_client.post(
        '/auth/login',
        json={'email': 'events@example.com', 'password': 'T3st!Passw0rd'},
    )
    assert response.status_code == 200

    events = _events(security_logs)
    success = [e for e in events if e['event'] == 'LOGIN_SUCCESS']
    assert success
    assert success[0]['user_id'] == user['id']
    assert success[0]['ip'] == 'testclient'


def test_login_failure_logs_event(api_client, security_logs) -> None:
    _register(api_client)

    response = api_client.post(
        '/auth/login',
        json={'email': 'events@example.com', 'password': 'wrongpass'},
    )
    assert response.status_code == 401

    events = _events(security_logs)
    failed = [e for e in events if e['event'] == 'LOGIN_FAILED']
    assert failed
    assert failed[0]['reason'] == 'invalid_credentials'
    assert failed[0]['ip'] == 'testclient'


def test_login_rate_limited_logs_event(api_client, security_logs) -> None:
    _register(api_client, email='brute-events@example.com')

    for _ in range(5):
        api_client.post(
            '/auth/login',
            json={
                'email': 'brute-events@example.com',
                'password': 'wrongpass',
            },
        )

    blocked = api_client.post(
        '/auth/login',
        json={
            'email': 'brute-events@example.com',
            'password': 'T3st!Passw0rd',
        },
    )
    assert blocked.status_code == 429

    events = _events(security_logs)
    limited = [e for e in events if e['event'] == 'LOGIN_RATE_LIMITED']
    assert limited
    assert limited[0]['ip'] == 'testclient'


def test_logout_logs_event(api_client, security_logs) -> None:
    user = _register(api_client)

    login = api_client.post(
        '/auth/login',
        json={'email': 'events@example.com', 'password': 'T3st!Passw0rd'},
    ).json()
    refresh_token = login['refresh_token']

    response = api_client.post(
        '/auth/logout', json={'refresh_token': refresh_token}
    )
    assert response.status_code == 204

    events = _events(security_logs)
    logout = [e for e in events if e['event'] == 'LOGOUT']
    assert logout
    assert logout[0]['user_id'] == user['id']
    assert 'token_id' in logout[0]


def test_password_reset_events_logged(
    api_client, monkeypatch, security_logs
) -> None:
    from urllib.parse import parse_qs, urlparse

    captured: dict = {}

    async def fake_send(to_email: str, reset_link: str) -> None:
        captured['link'] = reset_link

    monkeypatch.setattr(
        'app.services.email_service.send_password_reset_email',
        fake_send,
    )

    _register(api_client, email='reset-events@example.com')
    api_client.post(
        '/auth/password-reset/request',
        json={'email': 'reset-events@example.com'},
    )
    token = parse_qs(urlparse(captured['link']).query)['token'][0]
    api_client.post(
        '/auth/password-reset/confirm',
        json={'token': token, 'new_password': 'NewPass456!'},
    )

    events = _events(security_logs)
    assert any(e['event'] == 'PASSWORD_RESET_REQUESTED' for e in events)
    completed = [e for e in events if e['event'] == 'PASSWORD_RESET_COMPLETED']
    assert completed
    assert 'user_id' in completed[0]


def test_verify_email_logs_event(
    api_client, monkeypatch, security_logs
) -> None:
    from urllib.parse import parse_qs, urlparse

    captured: dict = {}

    async def fake_send_smtp(to_email: str, subject: str, html: str) -> None:
        if 'href="' in html:
            start = html.find('href="') + 6
            end = html.find('"', start)
            captured['link'] = html[start:end]

    async def fake_send(to_email: str, verify_link: str) -> None:
        captured['link'] = verify_link

    monkeypatch.setattr(
        'app.services.email_service._send_via_smtp',
        fake_send_smtp,
    )
    monkeypatch.setattr(
        'app.services.email_service.send_verification_email',
        fake_send,
    )

    _register(api_client, email='verify-events@example.com')
    token = parse_qs(urlparse(captured['link']).query)['token'][0]
    api_client.post('/auth/verify-email', json={'token': token})

    events = _events(security_logs)
    verified = [e for e in events if e['event'] == 'EMAIL_VERIFIED']
    assert verified
    assert 'user_id' in verified[0]


def test_security_logs_are_valid_json_and_searchable(
    api_client, security_logs
) -> None:
    _register(api_client, email='events-json@example.com')
    api_client.post(
        '/auth/login',
        json={'email': 'events-json@example.com', 'password': 'T3st!Passw0rd'},
    )

    output = _formatted(security_logs)
    for line in output.splitlines():
        json.loads(line)
    assert '"event": "LOGIN_SUCCESS"' in output


def test_security_logs_never_contain_sensitive_data(
    api_client, monkeypatch, security_logs
) -> None:
    user = _register(api_client, email='sensitive@example.com')
    login = api_client.post(
        '/auth/login',
        json={'email': 'sensitive@example.com', 'password': 'T3st!Passw0rd'},
    )
    assert login.status_code == 200
    access_token = login.json()['access_token']
    refresh_token = login.json()['refresh_token']

    api_client.post('/auth/logout', json={'refresh_token': refresh_token})

    output = _formatted(security_logs)
    assert 'T3st!Passw0rd' not in output
    assert user['id'] in output  # identifiers are expected
    assert access_token not in output
    assert refresh_token not in output
    assert 'hashed_password' not in output
