"""Tests for critical vulnerability fixes."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import ProductionSettings
from app.core.infrastructure.redis import rate_limit_check
from app.core.web.middleware import setup_security_headers_middleware
from app.messaging.events import AuthEvents
from app.schemas.user import UserCreate
from app.services import auth_service, user_service


def test_production_settings_rejects_weak_secrets() -> None:
    """Ensure ProductionSettings rejects weak default secrets and duplicate keys."""
    with pytest.raises(ValidationError):
        ProductionSettings(
            DATABASE_URL='sqlite+aiosqlite:///:memory:',
            CORS_ALLOWED_ORIGINS='https://example.com',
            SECRET_KEY='dev-only-secret-change-me',
            REFRESH_SECRET_KEY='prod-refresh-secret-1234567890',
            ADMIN_PASSWORD='StrongAdminPassword123!',
        )

    with pytest.raises(ValidationError):
        ProductionSettings(
            DATABASE_URL='sqlite+aiosqlite:///:memory:',
            CORS_ALLOWED_ORIGINS='https://example.com',
            SECRET_KEY='prod-secret-1234567890',
            REFRESH_SECRET_KEY='prod-secret-1234567890',  # Same key
            ADMIN_PASSWORD='StrongAdminPassword123!',
        )

    with pytest.raises(ValidationError):
        ProductionSettings(
            DATABASE_URL='sqlite+aiosqlite:///:memory:',
            CORS_ALLOWED_ORIGINS='https://example.com',
            SECRET_KEY='prod-secret-1234567890',
            REFRESH_SECRET_KEY='prod-refresh-secret-1234567890',
            ADMIN_PASSWORD='admin123',  # Insecure default password
        )


def test_security_headers_present() -> None:
    """Ensure HTTP security headers are set on API responses."""
    app = FastAPI()
    setup_security_headers_middleware(app)

    @app.get('/test')
    async def sample_endpoint() -> dict[str, bool]:
        return {'ok': True}

    with TestClient(app) as test_client:
        response = test_client.get('/test')
        assert response.headers.get('X-Frame-Options') == 'DENY'
        assert response.headers.get('X-Content-Type-Options') == 'nosniff'
        assert response.headers.get('Referrer-Policy') == 'no-referrer'
        assert 'Strict-Transport-Security' in response.headers


@pytest.mark.asyncio
async def test_password_reset_event_does_not_contain_reset_token(
    isolated_session_factory,
) -> None:
    """Ensure AuthEvents.PASSWORD_RESET_REQUESTED payload excludes reset_token."""
    async with isolated_session_factory() as session:
        user = await user_service.register_user(
            session,
            UserCreate(
                email='reset-no-token@example.com',
                password='T3st!Password123',
            ),
        )

        mock_bus = AsyncMock()
        with patch(
            'app.services.auth_service.get_event_bus', return_value=mock_bus
        ):
            await auth_service.request_password_reset(
                session, 'reset-no-token@example.com'
            )

        assert mock_bus.publish.called
        event = mock_bus.publish.call_args[0][0]
        assert event.type == AuthEvents.PASSWORD_RESET_REQUESTED
        assert 'reset_token' not in event.payload
        assert event.payload['user_id'] == user.id


@pytest.mark.asyncio
async def test_rate_limit_fails_closed_in_production_when_redis_unavailable(
    monkeypatch,
) -> None:
    """Ensure rate_limit_check fails closed (returns retry_after) when Redis is down in production."""
    with (
        patch('app.core.redis.get_redis_client', return_value=None),
        patch('app.core.redis.get_settings') as mock_settings,
    ):
        mock_settings.return_value.ENVIRONMENT = 'production'

        retry_after = await rate_limit_check(
            key='login:test', limit=5, window_seconds=60
        )
        assert retry_after == 60


def test_password_reset_token_expiration_minutes_is_15() -> None:
    """Ensure password reset token expiration default is set to 15 minutes."""
    from app.core.config import get_settings

    get_settings.cache_clear()
    assert get_settings().PASSWORD_RESET_TOKEN_EXPIRE_MINUTES == 15


def test_in_memory_rate_limiter_prune_all_stale() -> None:
    """Ensure prune_all_stale clears expired keys in rate limiters."""
    from app.core.rate_limiter import rate_limiter, request_rate_limiter

    rate_limiter.register_failed_attempt('user1@example.com', now=100.0)
    assert rate_limiter.prune_all_stale(now=2000.0) == 1

    request_rate_limiter.check_and_consume(
        'ip:127.0.0.1', limit=1, window_seconds=60.0, now=100.0
    )
    assert (
        request_rate_limiter.prune_all_stale(window_seconds=60.0, now=200.0)
        == 1
    )


@pytest.mark.asyncio
async def test_password_reset_request_timing_mitigation_unknown_email(
    isolated_session_factory,
) -> None:
    """Ensure password reset request for non-existent email returns gracefully without persisting tokens or sending emails."""
    from sqlalchemy import select

    from app.models.password_reset_token import PasswordResetToken

    async with isolated_session_factory() as session:
        mock_bus = AsyncMock()
        with (
            patch(
                'app.services.auth_service.get_event_bus',
                return_value=mock_bus,
            ),
            patch(
                'app.services.email_service.send_password_reset_email',
                new_callable=AsyncMock,
            ) as mock_send_email,
        ):
            await auth_service.request_password_reset(
                session, 'nonexistent@example.com'
            )

        assert not mock_send_email.called
        assert not mock_bus.publish.called

        tokens = (
            (await session.execute(select(PasswordResetToken))).scalars().all()
        )
        assert tokens == []


def test_password_reset_request_user_enumeration_responses_are_identical(
    api_client,
) -> None:
    """Ensure responses for existing vs non-existing emails in password reset request are identical (anti-enumeration)."""
    api_client.post(
        '/auth/register',
        json={'email': 'known@example.com', 'password': 'T3st!Password123'},
    )

    resp_known = api_client.post(
        '/auth/password-reset/request',
        json={'email': 'known@example.com'},
    )
    resp_unknown = api_client.post(
        '/auth/password-reset/request',
        json={'email': 'unknown@example.com'},
    )

    assert resp_known.status_code == 200
    assert resp_unknown.status_code == 200
    assert resp_known.json() == resp_unknown.json()
    assert resp_known.json() == {
        'message': 'If the e-mail is registered, a password reset link has been sent.'
    }
