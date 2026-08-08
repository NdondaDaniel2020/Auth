"""Google OAuth 2.0 / OpenID Connect login tests — ISSUES_GOOGLE_LOGIN.md.

External calls to Google are never made: the identity provider is either
replaced by a fake or exercised through ``httpx.MockTransport`` and real
cryptography (RS256) for signature verification.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator

import httpx
import jwt as pyjwt
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.exceptions import (
    GoogleAuthError,
    InvalidGoogleTokenError,
)
from app.core.security import decode_access_token
from app.core.security_logger import SECURITY_LOGGER_NAME, get_security_logger
from app.models.user import User
from tests.conftest import run_in_isolated_db

GOOGLE_TEST_EMAIL = 'google.user@example.com'
GOOGLE_TEST_SUB = 'google-sub-123456'


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


class FakeGoogleProvider:
    """Drop-in replacement for ``GoogleIdentityProvider``.

    ``exchange_code_for_id_token``/``verify_id_token`` return canned values
    unless an error is configured via ``exchange_error``/``verify_error``.
    """

    def __init__(self, *, client=None) -> None:
        self.claims: dict = {
            'iss': 'https://accounts.google.com',
            'aud': 'test-client-id',
            'sub': GOOGLE_TEST_SUB,
            'email': GOOGLE_TEST_EMAIL,
            'email_verified': True,
            'name': 'Google Test User',
            'exp': int(time.time()) + 3600,
            'iat': int(time.time()),
        }
        self.exchange_error: Exception | None = None
        self.verify_error: Exception | None = None

    async def exchange_code_for_id_token(self, code: str) -> str:
        if self.exchange_error is not None:
            raise self.exchange_error
        return 'fake-google-id-token'

    async def verify_id_token(self, id_token: str) -> dict:
        if self.verify_error is not None:
            raise self.verify_error
        return self.claims

    async def aclose(self) -> None:
        return None


def _enable_google(monkeypatch, **overrides) -> None:
    settings = get_settings()
    values = {
        'GOOGLE_LOGIN_ENABLED': True,
        'GOOGLE_CLIENT_ID': 'test-client-id',
        'GOOGLE_CLIENT_SECRET': 'test-client-secret',
        'GOOGLE_REDIRECT_URI': (
            'http://localhost:8001/api/auth/google/callback'
        ),
        'GOOGLE_AUTH_URL': 'https://accounts.google.com/o/oauth2/v2/auth',
        'GOOGLE_TOKEN_URL': 'https://oauth2.googleapis.com/token',
        'GOOGLE_CERTS_URL': 'https://www.googleapis.com/oauth2/v3/certs',
        'GOOGLE_ISSUER': 'https://accounts.google.com',
    }
    values.update(overrides)
    for key, value in values.items():
        monkeypatch.setattr(settings, key, value)


def _patch_provider(monkeypatch, provider: FakeGoogleProvider) -> None:
    monkeypatch.setattr(
        'app.services.google_auth_service._get_default_provider',
        lambda: provider,
    )


def _fetch_state(google_client) -> tuple[str, str]:
    response = google_client.get('/auth/google/url')
    assert response.status_code == 200
    body = response.json()
    return body['authorization_url'], body['state']


# ---------------------------------------------------------------------------
# GET /auth/google/url
# ---------------------------------------------------------------------------


def test_google_url_returns_consent_screen_url(
    google_client, monkeypatch
) -> None:
    from urllib.parse import parse_qs, urlparse

    _enable_google(monkeypatch)

    authorization_url, state = _fetch_state(google_client)

    parsed = urlparse(authorization_url)
    query = parse_qs(parsed.query)
    assert parsed.netloc == 'accounts.google.com'
    assert parsed.path == '/o/oauth2/v2/auth'
    assert query['response_type'] == ['code']
    assert query['client_id'] == ['test-client-id']
    assert query['redirect_uri'] == [
        'http://localhost:8001/api/auth/google/callback'
    ]
    assert query['scope'] == ['openid email profile']
    assert 'openid' in query['scope'][0]
    assert query['state'] == [state]

    payload = pyjwt.decode(
        state, get_settings().SECRET_KEY, algorithms=['HS256']
    )
    assert payload['type'] == 'google_state'
    assert payload['nonce']


def test_google_url_disabled_returns_403(google_client, monkeypatch) -> None:
    _enable_google(monkeypatch, GOOGLE_LOGIN_ENABLED=False)

    response = google_client.get('/auth/google/url')
    assert response.status_code == 403
    assert response.json()['error']['code'] == 'GOOGLE_LOGIN_DISABLED'


# ---------------------------------------------------------------------------
# POST /auth/google/callback — end-to-end flows
# ---------------------------------------------------------------------------


def test_google_login_creates_new_verified_user(
    google_client, monkeypatch, isolated_db_path
) -> None:
    _enable_google(monkeypatch)
    _patch_provider(monkeypatch, FakeGoogleProvider())
    _, state = _fetch_state(google_client)

    response = google_client.post(
        '/auth/google/callback',
        json={'code': 'auth-code', 'state': state},
    )
    assert response.status_code == 200
    body = response.json()
    assert body['token_type'] == 'bearer'
    assert body['access_token']
    assert body['refresh_token']

    payload = decode_access_token(body['access_token'])
    assert payload['type'] == 'access'
    assert payload['sub']

    async def _check_user(factory):
        async with factory() as session:
            user = (
                await session.execute(
                    select(User).where(User.email == GOOGLE_TEST_EMAIL)
                )
            ).scalar_one()
            assert user is not None
            assert user.is_verified is True
            assert user.hashed_password is None
            assert user.oauth_provider == 'google'
            assert user.google_id == GOOGLE_TEST_SUB
            assert user.full_name == 'Google Test User'
            assert user.id == payload['sub']

    run_in_isolated_db(isolated_db_path, _check_user)


def test_google_login_links_existing_user_without_duplicate(
    google_client, monkeypatch, isolated_db_path
) -> None:
    _enable_google(monkeypatch)
    _patch_provider(monkeypatch, FakeGoogleProvider())

    registration = google_client.post(
        '/auth/register',
        json={'email': GOOGLE_TEST_EMAIL, 'password': 'T3st!Passw0rd'},
    )
    assert registration.status_code == 201
    original_id = registration.json()['id']

    _, state = _fetch_state(google_client)
    response = google_client.post(
        '/auth/google/callback',
        json={'code': 'auth-code', 'state': state},
    )
    assert response.status_code == 200

    async def _check_user(factory):
        async with factory() as session:
            rows = (await session.execute(select(User))).scalars().all()
            assert len(rows) == 1
            user = rows[0]
            assert user.id == original_id
            assert user.is_verified is True
            assert user.google_id == GOOGLE_TEST_SUB
            assert user.oauth_provider == 'google'
            assert user.hashed_password is not None

    run_in_isolated_db(isolated_db_path, _check_user)


def test_google_login_user_without_local_password_cannot_password_login(
    google_client, monkeypatch
) -> None:
    _enable_google(monkeypatch)
    _patch_provider(monkeypatch, FakeGoogleProvider())
    _, state = _fetch_state(google_client)

    response = google_client.post(
        '/auth/google/callback',
        json={'code': 'auth-code', 'state': state},
    )
    assert response.status_code == 200

    password_login = google_client.post(
        '/auth/login',
        json={'email': GOOGLE_TEST_EMAIL, 'password': 'T3st!Passw0rd'},
    )
    assert password_login.status_code == 401
    assert password_login.json()['error']['code'] == 'INVALID_CREDENTIALS'


def test_google_login_accepts_id_token_directly(
    google_client, monkeypatch
) -> None:
    _enable_google(monkeypatch)
    _patch_provider(monkeypatch, FakeGoogleProvider())

    response = google_client.post(
        '/auth/google/callback',
        json={'id_token': 'direct-id-token'},
    )
    assert response.status_code == 200
    body = response.json()
    assert body['access_token']
    assert body['refresh_token']


# ---------------------------------------------------------------------------
# POST /auth/google/callback — error handling
# ---------------------------------------------------------------------------


def test_google_login_invalid_code_rejected(
    google_client, monkeypatch, security_logs
) -> None:
    _enable_google(monkeypatch)
    provider = FakeGoogleProvider()
    provider.exchange_error = InvalidGoogleTokenError(
        message='Invalid or expired authorization code'
    )
    _patch_provider(monkeypatch, provider)
    _, state = _fetch_state(google_client)

    response = google_client.post(
        '/auth/google/callback',
        json={'code': 'bad-code', 'state': state},
    )
    assert response.status_code == 400
    assert response.json()['error']['code'] == 'INVALID_GOOGLE_TOKEN'

    failed = [
        e
        for e in _events(security_logs)
        if e['event'] == 'GOOGLE_LOGIN_FAILED'
    ]
    assert failed
    assert failed[0]['reason'] == 'invalid_token'


def test_google_login_invalid_id_token_rejected(
    google_client, monkeypatch
) -> None:
    _enable_google(monkeypatch)
    provider = FakeGoogleProvider()
    provider.verify_error = InvalidGoogleTokenError(
        message='Invalid or expired id_token'
    )
    _patch_provider(monkeypatch, provider)

    response = google_client.post(
        '/auth/google/callback',
        json={'id_token': 'bad-id-token'},
    )
    assert response.status_code == 400
    assert response.json()['error']['code'] == 'INVALID_GOOGLE_TOKEN'


def test_google_login_invalid_state_rejected(
    google_client, monkeypatch
) -> None:
    _enable_google(monkeypatch)
    _patch_provider(monkeypatch, FakeGoogleProvider())

    response = google_client.post(
        '/auth/google/callback',
        json={'code': 'auth-code', 'state': 'forged-state-token'},
    )
    assert response.status_code == 400
    assert response.json()['error']['code'] == 'INVALID_GOOGLE_TOKEN'


def test_google_login_disabled_returns_403(
    google_client, monkeypatch, security_logs
) -> None:
    _enable_google(monkeypatch, GOOGLE_LOGIN_ENABLED=False)
    _patch_provider(monkeypatch, FakeGoogleProvider())

    response = google_client.post(
        '/auth/google/callback',
        json={'id_token': 'direct-id-token'},
    )
    assert response.status_code == 403
    assert response.json()['error']['code'] == 'GOOGLE_LOGIN_DISABLED'

    failed = [
        e
        for e in _events(security_logs)
        if e['event'] == 'GOOGLE_LOGIN_FAILED'
    ]
    assert failed
    assert failed[0]['reason'] == 'disabled'


def test_google_login_emits_success_security_event(
    google_client, monkeypatch, security_logs
) -> None:
    _enable_google(monkeypatch)
    _patch_provider(monkeypatch, FakeGoogleProvider())
    _, state = _fetch_state(google_client)

    response = google_client.post(
        '/auth/google/callback',
        json={'code': 'auth-code', 'state': state},
    )
    assert response.status_code == 200

    success = [
        e
        for e in _events(security_logs)
        if e['event'] == 'GOOGLE_LOGIN_SUCCESS'
    ]
    assert success
    assert success[0]['user_id']
    assert success[0]['ip'] == 'testclient'


# ---------------------------------------------------------------------------
# Request validation (GoogleLoginRequest)
# ---------------------------------------------------------------------------


def test_google_login_requires_code_or_id_token(
    google_client, monkeypatch
) -> None:
    _enable_google(monkeypatch)
    _patch_provider(monkeypatch, FakeGoogleProvider())

    neither = google_client.post('/auth/google/callback', json={})
    assert neither.status_code == 422

    both = google_client.post(
        '/auth/google/callback',
        json={'code': 'code', 'id_token': 'token', 'state': 'state'},
    )
    assert both.status_code == 422

    code_without_state = google_client.post(
        '/auth/google/callback', json={'code': 'code'}
    )
    assert code_without_state.status_code == 422


# ---------------------------------------------------------------------------
# Unit tests — GoogleIdentityProvider (real crypto / HTTP contract)
# ---------------------------------------------------------------------------


def _rsa_keypair():
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048
    )
    return private_key, private_key.public_key()


def _make_jwks(public_key, kid: str = 'test-kid') -> dict:
    jwk = json.loads(pyjwt.algorithms.RSAAlgorithm.to_jwk(public_key))
    jwk['kid'] = kid
    jwk['alg'] = 'RS256'
    return {'keys': [jwk]}


def _sign_id_token(private_key, *, kid: str = 'test-kid', **claims) -> str:
    default = {
        'iss': 'https://accounts.google.com',
        'aud': 'test-client-id',
        'sub': GOOGLE_TEST_SUB,
        'email': GOOGLE_TEST_EMAIL,
        'email_verified': True,
        'name': 'Google Test User',
        'exp': int(time.time()) + 3600,
        'iat': int(time.time()),
    }
    default.update(claims)
    return pyjwt.encode(
        default, private_key, algorithm='RS256', headers={'kid': kid}
    )


def _provider_with_certs(public_key) -> tuple:
    from app.services.google_auth_service import GoogleIdentityProvider

    provider = GoogleIdentityProvider()
    if public_key is not None:

        async def _fake_fetch_certs() -> dict:
            return _make_jwks(public_key)

        provider._fetch_certs = _fake_fetch_certs
    return provider


async def test_verify_id_token_accepts_valid_token(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, 'GOOGLE_CLIENT_ID', 'test-client-id')

    private_key, public_key = _rsa_keypair()
    provider = _provider_with_certs(public_key)

    payload = await provider.verify_id_token(_sign_id_token(private_key))
    assert payload['email'] == GOOGLE_TEST_EMAIL
    assert payload['sub'] == GOOGLE_TEST_SUB
    assert payload['iss'] == 'https://accounts.google.com'
    assert payload['aud'] == 'test-client-id'

    await provider.aclose()


@pytest.mark.parametrize(
    'claims',
    [
        {'exp': int(time.time()) - 3600},
        {'aud': 'some-other-client'},
        {'iss': 'https://other.example.com'},
        {'email_verified': False},
        {'email': ''},
    ],
)
async def test_verify_id_token_rejects_invalid_claims(
    monkeypatch, claims
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, 'GOOGLE_CLIENT_ID', 'test-client-id')

    private_key, public_key = _rsa_keypair()
    provider = _provider_with_certs(public_key)

    with pytest.raises(InvalidGoogleTokenError):
        await provider.verify_id_token(_sign_id_token(private_key, **claims))

    await provider.aclose()


async def test_verify_id_token_rejects_unknown_signing_key(
    monkeypatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, 'GOOGLE_CLIENT_ID', 'test-client-id')

    private_key, public_key = _rsa_keypair()
    provider = _provider_with_certs(public_key)

    token = _sign_id_token(private_key, kid='unknown-kid')
    with pytest.raises(InvalidGoogleTokenError):
        await provider.verify_id_token(token)

    await provider.aclose()


@pytest.mark.parametrize(
    'malformed',
    ['not-a-jwt', 'header.payload', 'aaa.bbb.ccc.ddd'],
)
async def test_verify_id_token_rejects_malformed_token(monkeypatch, malformed):
    """Regression: a malformed token must map to 400, never to a 500."""
    settings = get_settings()
    monkeypatch.setattr(settings, 'GOOGLE_CLIENT_ID', 'test-client-id')

    provider = _provider_with_certs(None)
    with pytest.raises(InvalidGoogleTokenError):
        await provider.verify_id_token(malformed)

    await provider.aclose()


async def test_fetch_certs_is_cached_across_calls(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, 'GOOGLE_CERTS_CACHE_TTL_SECONDS', 300)

    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={'keys': []})

    transport = httpx.MockTransport(handler)
    from app.services.google_auth_service import GoogleIdentityProvider

    async with httpx.AsyncClient(transport=transport) as client:
        provider = GoogleIdentityProvider(client=client)

        first = await provider._fetch_certs()
        second = await provider._fetch_certs()

    assert first == {'keys': []}
    assert second is first
    assert calls == 1


async def test_exchange_code_posts_credentials_to_token_endpoint(
    monkeypatch,
) -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured['url'] = str(request.url)
        captured['body'] = request.content.decode()
        return httpx.Response(200, json={'id_token': 'google-issued-id-token'})

    transport = httpx.MockTransport(handler)
    from app.services.google_auth_service import GoogleIdentityProvider

    async with httpx.AsyncClient(transport=transport) as client:
        provider = GoogleIdentityProvider(client=client)
        _enable_google(monkeypatch)

        id_token = await provider.exchange_code_for_id_token('the-auth-code')

    assert id_token == 'google-issued-id-token'
    assert 'oauth2.googleapis.com' in captured['url']
    assert 'code=the-auth-code' in captured['body']
    assert 'client_id=test-client-id' in captured['body']
    assert 'client_secret=test-client-secret' in captured['body']
    assert 'redirect_uri=' in captured['body']
    assert 'grant_type=authorization_code' in captured['body']


async def test_exchange_code_rejects_non_200_response(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={'error': 'invalid_grant'})

    transport = httpx.MockTransport(handler)
    from app.services.google_auth_service import GoogleIdentityProvider

    async with httpx.AsyncClient(transport=transport) as client:
        provider = GoogleIdentityProvider(client=client)
        _enable_google(monkeypatch)

        with pytest.raises(InvalidGoogleTokenError):
            await provider.exchange_code_for_id_token('bad-code')


async def test_exchange_code_maps_network_error_to_google_auth_error(
    monkeypatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError('connection refused')

    transport = httpx.MockTransport(handler)
    from app.services.google_auth_service import GoogleIdentityProvider

    async with httpx.AsyncClient(transport=transport) as client:
        provider = GoogleIdentityProvider(client=client)
        _enable_google(monkeypatch)

        with pytest.raises(GoogleAuthError):
            await provider.exchange_code_for_id_token('the-auth-code')


async def test_verify_id_token_maps_certs_fetch_failure_to_upstream_error(
    monkeypatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, 'GOOGLE_CLIENT_ID', 'test-client-id')

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError('connection refused')

    transport = httpx.MockTransport(handler)
    from app.services.google_auth_service import GoogleIdentityProvider

    private_key, _ = _rsa_keypair()
    token = _sign_id_token(private_key)

    async with httpx.AsyncClient(transport=transport) as client:
        provider = GoogleIdentityProvider(client=client)
        with pytest.raises(GoogleAuthError):
            await provider.verify_id_token(token)
