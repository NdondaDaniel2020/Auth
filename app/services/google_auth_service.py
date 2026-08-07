from __future__ import annotations

import json
import logging
import time
from datetime import timedelta
from functools import lru_cache
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

import httpx
import jwt as pyjwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import (
    GoogleAuthError,
    GoogleLoginDisabledError,
    InvalidGoogleTokenError,
)
from app.core.security import create_signed_token, decode_token
from app.core.security_logger import log_security_event
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import Token
from app.schemas.google import GoogleLoginRequest
from app.services import auth_service

logger = logging.getLogger(__name__)


def ensure_google_login_enabled() -> None:
    """Raise ``GoogleLoginDisabledError`` when Google login is turned off."""
    if not get_settings().GOOGLE_LOGIN_ENABLED:
        raise GoogleLoginDisabledError()


def create_google_state() -> str:
    """Return a short-lived signed state token (CSRF protection).

    The state is a signed JWT bound to a random ``nonce``; the callback
    validates its signature and expiry before exchanging the authorization
    code, preventing login-CSRF/replay against the callback.
    """
    settings = get_settings()
    return create_signed_token(
        {'nonce': str(uuid4())},
        token_type='google_state',
        expires_delta=timedelta(minutes=settings.GOOGLE_STATE_TTL_MINUTES),
    )


def verify_google_state(state: str) -> None:
    """Validate the signed ``state`` produced by ``create_google_state``."""
    try:
        payload = decode_token(state, expected_type='google_state')
    except pyjwt.InvalidTokenError:
        raise InvalidGoogleTokenError(
            message='Invalid or expired OAuth state'
        ) from None

    if not payload.get('nonce'):
        raise InvalidGoogleTokenError(message='Invalid or expired OAuth state')


def build_authorization_url(state: str) -> str:
    """Build the consent-screen URL the browser must be redirected to."""
    settings = get_settings()
    params = {
        'client_id': settings.GOOGLE_CLIENT_ID,
        'redirect_uri': settings.GOOGLE_REDIRECT_URI,
        'response_type': 'code',
        'scope': 'openid email profile',
        'access_type': 'online',
        'prompt': 'select_account',
        'state': state,
    }
    return f'{settings.GOOGLE_AUTH_URL}?{urlencode(params)}'


class GoogleIdentityProvider:
    """Client for Google's OAuth token endpoint and OIDC JWKS.

    ``exchange_code_for_id_token`` swaps the authorization code for an ID
    Token; ``verify_id_token`` validates the signature, issuer, audience and
    claims. Signing keys (JWKS) are fetched from Google and cached briefly on
    the instance (the app shares a single provider, so the cache is effective
    across requests).
    """

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client if client is not None else httpx.AsyncClient()
        self._owns_client = client is None
        self._certs: dict[str, Any] | None = None
        self._certs_fetched_at: float | None = None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def exchange_code_for_id_token(self, code: str) -> str:
        """POST the authorization code to Google's token endpoint."""
        settings = get_settings()
        data = {
            'code': code,
            'client_id': settings.GOOGLE_CLIENT_ID,
            'client_secret': settings.GOOGLE_CLIENT_SECRET,
            'redirect_uri': settings.GOOGLE_REDIRECT_URI,
            'grant_type': 'authorization_code',
        }
        try:
            response = await self._client.post(
                settings.GOOGLE_TOKEN_URL, data=data, timeout=10.0
            )
        except httpx.HTTPError:
            raise GoogleAuthError() from None

        if response.status_code != 200:
            raise InvalidGoogleTokenError(
                message='Invalid or expired authorization code'
            )

        try:
            body = response.json()
        except ValueError:
            raise GoogleAuthError() from None

        id_token = body.get('id_token')
        if not id_token:
            raise InvalidGoogleTokenError(
                message='Google did not return an id_token'
            )
        return id_token

    async def verify_id_token(self, id_token: str) -> dict[str, Any]:
        """Verify the ID Token signature/claims and return its payload."""
        settings = get_settings()

        try:
            header = pyjwt.get_unverified_header(id_token)
        except pyjwt.InvalidTokenError:
            raise InvalidGoogleTokenError(
                message='Invalid or expired id_token'
            ) from None
        if header.get('alg') != 'RS256':
            raise InvalidGoogleTokenError(message='Unsupported token algorithm')

        certs = await self._fetch_certs()
        signing_key = _signing_key_for_header(certs, header.get('kid'))
        if signing_key is None:
            raise InvalidGoogleTokenError(message='Unknown token signing key')

        try:
            payload = pyjwt.decode(
                id_token,
                signing_key,
                algorithms=['RS256'],
                audience=settings.GOOGLE_CLIENT_ID,
                issuer=settings.GOOGLE_ISSUER,
                options={
                    'verify_aud': True,
                    'require': ['sub', 'email', 'exp', 'iss', 'aud'],
                },
            )
        except pyjwt.InvalidTokenError:
            raise InvalidGoogleTokenError(
                message='Invalid or expired id_token'
            ) from None

        email = payload.get('email')
        if not email or not _is_email_verified(payload):
            raise InvalidGoogleTokenError(
                message='Google account does not have a verified e-mail'
            )

        return payload

    async def _fetch_certs(self) -> dict[str, Any]:
        now = time.monotonic()
        settings = get_settings()
        if (
            self._certs is not None
            and self._certs_fetched_at is not None
            and now - self._certs_fetched_at
            < settings.GOOGLE_CERTS_CACHE_TTL_SECONDS
        ):
            return self._certs

        try:
            response = await self._client.get(
                settings.GOOGLE_CERTS_URL, timeout=10.0
            )
        except httpx.HTTPError:
            raise GoogleAuthError() from None

        if response.status_code != 200:
            raise GoogleAuthError()

        try:
            self._certs = response.json()
        except ValueError:
            raise GoogleAuthError() from None

        self._certs_fetched_at = now
        return self._certs


@lru_cache(maxsize=1)
def _get_default_provider() -> GoogleIdentityProvider:
    """Return the process-wide identity provider.

    A single instance is reused by every request: the underlying HTTP client
    keeps its connection pool and the JWKS cache stays effective across
    logins instead of being re-fetched per request.
    """
    return GoogleIdentityProvider()


def _signing_key_for_header(
    certs: dict[str, Any], kid: str | None
) -> Any | None:
    """Return the JWK-derived public key matching the token's ``kid``."""
    keys = certs.get('keys', []) if isinstance(certs, dict) else []
    for key in keys:
        if key.get('kid') == kid and key.get('kty') == 'RSA':
            try:
                return pyjwt.algorithms.RSAAlgorithm.from_jwk(
                    json.dumps(key)
                )
            except pyjwt.PyJWTError:
                logger.warning(
                    'Could not build signing key from JWK', exc_info=True
                )
                return None
    return None


def _is_email_verified(payload: dict[str, Any]) -> bool:
    value = payload.get('email_verified')
    if isinstance(value, bool):
        return value
    return isinstance(value, str) and value.lower() == 'true'


def _link_oauth_identity(user: User, claims: dict[str, Any]) -> None:
    """Associate an existing user with their Google identity."""
    user.is_verified = True
    if user.google_id is None:
        user.oauth_provider = 'google'
        user.google_id = claims['sub']
    if user.full_name is None and claims.get('name'):
        user.full_name = claims['name']


async def google_login(
    db: AsyncSession,
    *,
    data: GoogleLoginRequest,
    client_ip: str | None = None,
) -> Token:
    """Authenticate a user through Google OAuth and issue app tokens.

    ``data`` carries exactly one credential (``code`` or ``id_token``),
    enforced by ``GoogleLoginRequest``. New e-mails are auto-registered as
    verified users without a local password; existing e-mails are linked to
    the Google identity.
    """
    if not get_settings().GOOGLE_LOGIN_ENABLED:
        log_security_event(
            'GOOGLE_LOGIN_FAILED',
            ip=client_ip,
            metadata={'reason': 'disabled'},
            level=logging.WARNING,
        )
        raise GoogleLoginDisabledError()

    provider = _get_default_provider()
    try:
        if data.id_token is None:
            verify_google_state(data.state)
            id_token = await provider.exchange_code_for_id_token(data.code)
        else:
            id_token = data.id_token
        claims = await provider.verify_id_token(id_token)
    except (InvalidGoogleTokenError, GoogleAuthError) as exc:
        reason = (
            'invalid_token'
            if isinstance(exc, InvalidGoogleTokenError)
            else 'upstream_error'
        )
        log_security_event(
            'GOOGLE_LOGIN_FAILED',
            ip=client_ip,
            metadata={'reason': reason, 'error': exc.message},
            level=logging.WARNING,
        )
        raise

    email = claims['email'].lower()
    repository = UserRepository(db)
    user = await repository.get_by_email(email)

    if user is None:
        user = await repository.create(
            email=email,
            full_name=claims.get('name'),
            oauth_provider='google',
            google_id=claims['sub'],
            is_verified=True,
        )
    else:
        _link_oauth_identity(user, claims)

    await db.commit()
    log_security_event('GOOGLE_LOGIN_SUCCESS', user_id=user.id, ip=client_ip)
    return await auth_service.create_token_pair(db, user)
