"""Tests for generic per-route rate limiting — #38."""

from __future__ import annotations

import pytest

from app.core.security.rate_limiter import (
    parse_rate_limit,
    request_rate_limiter,
)


class _FakeRateLimitSettings:
    RATE_LIMIT_DEFAULT = '60/minute'
    RATE_LIMIT_REGISTER = '2/minute'
    RATE_LIMIT_PASSWORD_RESET = '5/minute'
    RATE_LIMIT_EMAIL_RESEND = '3/minute'


def _register_payload(email: str) -> dict[str, str]:
    return {'email': email, 'password': 'T3st!Passw0rd'}


def test_parse_rate_limit() -> None:
    assert parse_rate_limit('10/minute') == (10, 60.0)
    assert parse_rate_limit('2/second') == (2, 1.0)
    assert parse_rate_limit('100/hour') == (100, 3600.0)
    assert parse_rate_limit('1/day') == (1, 86400.0)
    assert parse_rate_limit(' 5 / minute ') == (5, 60.0)
    assert parse_rate_limit('10/minutes') == (10, 60.0)


@pytest.mark.parametrize(
    'value',
    ['', '10', 'abc/minute', '0/minute', '-1/minute', '10/fortnight'],
)
def test_parse_rate_limit_invalid(value: str) -> None:
    with pytest.raises(ValueError):
        parse_rate_limit(value)


def test_within_limit_is_allowed() -> None:
    assert (
        request_rate_limiter.check_and_consume('k', 2, 60.0, now=1000.0)
        is None
    )
    assert (
        request_rate_limiter.check_and_consume('k', 2, 60.0, now=1001.0)
        is None
    )
    request_rate_limiter.clear()


def test_over_limit_returns_retry_after() -> None:
    request_rate_limiter.check_and_consume('k', 2, 60.0, now=1000.0)
    request_rate_limiter.check_and_consume('k', 2, 60.0, now=1001.0)
    retry_after = request_rate_limiter.check_and_consume(
        'k', 2, 60.0, now=1002.0
    )
    assert retry_after is not None
    assert retry_after > 0
    request_rate_limiter.clear()


def test_allowed_after_window_elapses() -> None:
    request_rate_limiter.check_and_consume('k', 1, 10.0, now=1000.0)
    assert (
        request_rate_limiter.check_and_consume('k', 1, 10.0, now=1011.0)
        is None
    )
    request_rate_limiter.clear()


def test_scopes_are_independent() -> None:
    request_rate_limiter.check_and_consume('scope_a:k', 1, 60.0, now=1000.0)
    assert (
        request_rate_limiter.check_and_consume(
            'scope_b:k', 1, 60.0, now=1001.0
        )
        is None
    )
    assert (
        request_rate_limiter.check_and_consume(
            'scope_a:k', 1, 60.0, now=1002.0
        )
        is not None
    )
    request_rate_limiter.clear()


def test_reset_clears_key() -> None:
    request_rate_limiter.check_and_consume('k', 1, 60.0, now=1000.0)
    assert (
        request_rate_limiter.check_and_consume('k', 1, 60.0, now=1001.0)
        is not None
    )
    request_rate_limiter.reset('k')
    assert (
        request_rate_limiter.check_and_consume('k', 1, 60.0, now=1002.0)
        is None
    )
    request_rate_limiter.clear()


def test_register_exceeds_limit_returns_429(api_client, monkeypatch) -> None:
    monkeypatch.setattr(
        'app.api.dependencies.rate_limit.get_settings',
        lambda: _FakeRateLimitSettings(),
    )

    first = api_client.post(
        '/auth/register', json=_register_payload('rl1@example.com')
    )
    assert first.status_code == 201

    second = api_client.post(
        '/auth/register', json=_register_payload('rl2@example.com')
    )
    assert second.status_code == 201

    third = api_client.post(
        '/auth/register', json=_register_payload('rl3@example.com')
    )
    assert third.status_code == 429
    body = third.json()
    assert body['error']['type'] == 'RateLimitExceededError'
    assert body['error']['code'] == 'RATE_LIMIT_EXCEEDED'
    assert body['status'] == 429
    assert int(third.headers.get('retry-after', '0')) > 0


def test_routes_have_independent_limits(api_client, monkeypatch) -> None:
    monkeypatch.setattr(
        'app.api.dependencies.rate_limit.get_settings',
        lambda: _FakeRateLimitSettings(),
    )

    api_client.post('/auth/register', json=_register_payload('ia@example.com'))
    api_client.post('/auth/register', json=_register_payload('ib@example.com'))
    exceeded = api_client.post(
        '/auth/register', json=_register_payload('ic@example.com')
    )
    assert exceeded.status_code == 429

    reset_request = api_client.post(
        '/auth/password-reset/request',
        json={'email': 'not-registered@example.com'},
    )
    assert reset_request.status_code == 200
