"""Integration tests for Distributed Brute Force protection & Account Lockout (#116)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.core.exceptions import (
    InvalidCredentialsError,
    TooManyLoginAttemptsError,
)
from app.core.security.rate_limiter import rate_limiter
from app.core.security.security import hash_password
from app.repositories.user_repository import UserRepository
from app.services.user_service import authenticate_user

PASSWORD = 'CorrectPassword123!'


@pytest.fixture(autouse=True)
def _clean_rate_limiter_state():
    rate_limiter.clear()
    yield
    rate_limiter.clear()


async def _make_user(session, email: str = 'target_user@example.com'):
    repo = UserRepository(session)
    user = await repo.create(
        email=email,
        hashed_password=hash_password(PASSWORD),
    )
    await session.commit()
    return user


@pytest.mark.asyncio
async def test_distributed_brute_force_triggers_account_lockout(
    isolated_session_factory,
) -> None:
    """Simulate brute force attack on a single account across 5 different IPs.

    The 5th failed attempt must trigger Account Lockout, emit the
    ACCOUNT_TEMPORARILY_LOCKED security event, send a security alert email,
    and block subsequent attempts from ANY IP.
    """
    async with isolated_session_factory() as session:
        user = await _make_user(session, 'target_user@example.com')
        target_email = user.email
        ips = [f'192.168.1.{i}' for i in range(1, 6)]

        with (
            patch(
                'app.services.user_service.send_account_locked_email',
                new_callable=AsyncMock,
            ) as mock_send_email,
            patch(
                'app.services.user_service.log_security_event'
            ) as mock_log_security,
        ):
            # First 4 failed attempts from 4 distinct IPs
            for i in range(4):
                with pytest.raises(InvalidCredentialsError):
                    await authenticate_user(
                        session,
                        target_email,
                        'WrongPassword!',
                        client_ip=ips[i],
                    )

            # Confirm email alert was NOT sent yet
            mock_send_email.assert_not_called()

            # 5th failed attempt from 5th distinct IP
            with pytest.raises(InvalidCredentialsError):
                await authenticate_user(
                    session,
                    target_email,
                    'WrongPassword!',
                    client_ip=ips[4],
                )

            # 5th attempt triggers account lockout email notification & security event
            mock_send_email.assert_called_once_with(target_email, 30)

            # Verify ACCOUNT_TEMPORARILY_LOCKED security event log
            event_names = [
                call.args[0] for call in mock_log_security.call_args_list
            ]
            assert 'ACCOUNT_TEMPORARILY_LOCKED' in event_names

            # 6th attempt from a brand new IP (IP 6) should immediately raise TooManyLoginAttemptsError
            with pytest.raises(TooManyLoginAttemptsError) as exc_info:
                await authenticate_user(
                    session,
                    target_email,
                    'WrongPassword!',
                    client_ip='10.0.0.99',
                )

            assert 'Retry-After' in exc_info.value.headers
            assert int(exc_info.value.headers['Retry-After']) > 0


@pytest.mark.asyncio
async def test_successful_login_resets_both_email_and_ip_counters(
    isolated_session_factory,
) -> None:
    """Failed attempts followed by a successful login reset counters for both IP and Email."""
    async with isolated_session_factory() as session:
        user = await _make_user(session, 'reset_user@example.com')
        target_email = user.email
        ip = '172.16.0.5'

        for _ in range(3):
            with pytest.raises(InvalidCredentialsError):
                await authenticate_user(
                    session,
                    target_email,
                    'WrongPassword!',
                    client_ip=ip,
                )

        # Successful login
        authenticated = await authenticate_user(
            session,
            target_email,
            PASSWORD,
            client_ip=ip,
        )
        assert authenticated.id == user.id

        # 4 more failed attempts should be allowed without lockout (since counter was reset)
        for _ in range(4):
            with pytest.raises(InvalidCredentialsError):
                await authenticate_user(
                    session,
                    target_email,
                    'WrongPassword!',
                    client_ip=ip,
                )
