from __future__ import annotations

import contextlib
import logging
import time
from datetime import timedelta
from typing import Any
from uuid import uuid4

import jwt as pyjwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import (
    InvalidMfaChallengeError,
    InvalidMfaPendingTokenError,
    InvalidOrExpiredTokenError,
    InvalidRefreshTokenError,
    TokenAlreadyUsedError,
)
from app.core.infrastructure.redis import get_redis_client
from app.core.security.rate_limiter import (
    build_email_login_key,
    build_ip_login_key,
    build_login_key,
    redis_reset,
    reset_login_attempts_async,
)
from app.core.security.security import (
    blacklist_access_token,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_mfa_pending_token,
    decode_refresh_token,
    hash_password_async,
)
from app.core.security.security_logger import log_security_event
from app.db.session import get_session_factory
from app.messaging import Event
from app.messaging.buses import get_event_bus
from app.messaging.events import AuthEvents, UserEvents
from app.models.user import User
from app.repositories.email_verification_repository import (
    EmailVerificationTokenRepository,
)
from app.repositories.mfa_repository import MfaRepository
from app.repositories.password_reset_repository import (
    PasswordResetTokenRepository,
)
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import Token
from app.services import email_service
from app.services.mfa_service import MfaService
from app.utils.datetimes import ensure_utc, utcnow
from app.utils.tokens import generate_opaque_token

logger = logging.getLogger(__name__)

WS_TICKET_PREFIX = 'ws_ticket:'
WS_TICKET_TTL = 15  # seconds
_fallback_ws_tickets: dict[str, tuple[str, float]] = {}


async def create_ws_ticket(user_id: str) -> str:
    """Generate a one-time WebSocket authentication ticket valid for 15 seconds."""
    ticket = f'ws_tkt_{generate_opaque_token()}'
    key = f'{WS_TICKET_PREFIX}{ticket}'
    redis_client = get_redis_client()

    if redis_client:
        try:
            await redis_client.setex(key, WS_TICKET_TTL, user_id)
            return ticket
        except Exception as e:  # noqa: BLE001
            logger.warning(
                'Redis WS ticket setex failed: %s; using local fallback', e
            )

    now = time.monotonic()
    expired_keys = [
        k for k, (_, exp) in _fallback_ws_tickets.items() if exp < now
    ]
    for k in expired_keys:
        _fallback_ws_tickets.pop(k, None)

    _fallback_ws_tickets[ticket] = (user_id, now + WS_TICKET_TTL)
    return ticket


async def consume_ws_ticket(ticket: str) -> str | None:
    """Atomically consume a one-time WebSocket ticket and return user_id if valid."""
    if not ticket:
        return None

    key = f'{WS_TICKET_PREFIX}{ticket}'
    redis_client = get_redis_client()

    if redis_client:
        try:
            res = await redis_client.getdel(key)
            if res is not None:
                return (
                    res.decode('utf-8') if isinstance(res, bytes) else str(res)
                )
        except Exception as e:  # noqa: BLE001
            logger.warning(
                'Redis WS ticket getdel failed: %s; checking local fallback', e
            )

    now = time.monotonic()
    data = _fallback_ws_tickets.pop(ticket, None)
    if data:
        stored_user_id, expires_at = data
        if now <= expires_at:
            return stored_user_id
    return None


async def create_token_pair(
    db: AsyncSession,
    user: User,
    amr: list[str] | None = None,
) -> Token:
    """Issue an access token and a persistable, revocable refresh token."""
    settings = get_settings()

    access_data: dict[str, Any] = {'sub': user.id}
    if amr:
        access_data['amr'] = amr

    access_token = create_access_token(access_data)

    jti = str(uuid4())
    expires_at = utcnow() + timedelta(days=settings.JWT_REFRESH_DAYS)
    refresh_repository = RefreshTokenRepository(db)
    await refresh_repository.create(
        jti=jti, user_id=user.id, expires_at=expires_at
    )

    refresh_token = create_refresh_token(
        {'sub': user.id, 'jti': jti},
        expires_delta=timedelta(days=settings.JWT_REFRESH_DAYS),
    )

    await db.commit()
    return Token(access_token=access_token, refresh_token=refresh_token)


async def authenticate_mfa_challenge(
    db: AsyncSession,
    *,
    mfa_pending_token: str,
    code: str,
) -> tuple[Token, User]:
    """Validate an intermediate mfa_pending token and TOTP or backup code.

    On success, issues the final token pair with claim ``amr: ["pwd", "mfa"]``
    and returns both ``(Token, User)``.
    """
    try:
        payload = decode_mfa_pending_token(mfa_pending_token)
    except pyjwt.PyJWTError:
        raise InvalidMfaPendingTokenError('Token MFA expirado ou inválido.')

    user_id = payload.get('sub')
    if not user_id:
        raise InvalidMfaPendingTokenError('Token MFA inválido.')

    repository = UserRepository(db)
    user = await repository.get_by_id(user_id)
    if not user or not user.is_active or not user.mfa_enabled:
        raise InvalidMfaPendingTokenError(
            'Usuário inválido ou MFA não ativado.'
        )

    mfa_repo = MfaRepository(db)
    mfa_method = await mfa_repo.get_active_by_user_and_type(
        user.id, type='totp'
    )

    if not mfa_method:
        raise InvalidMfaPendingTokenError('Método MFA não configurado.')

    totp_valid = (
        MfaService.verify_totp_code(mfa_method.secret, code)
        if mfa_method.secret
        else False
    )

    backup_valid = False
    if not totp_valid and mfa_method.data:
        hashed_codes = mfa_method.data.get('backup_codes', [])
        backup_valid, updated_codes, remaining_count = (
            MfaService.verify_and_consume_backup_code(code, hashed_codes)
        )
        if backup_valid:
            mfa_method.data = {'backup_codes': updated_codes}
            log_security_event(
                'MFA_BACKUP_CODE_USED',
                user_id=user.id,
                metadata={'remaining_codes': remaining_count},
            )
            await db.commit()
            try:
                await email_service.send_backup_code_used_email(
                    user.email, remaining_count
                )
            except Exception:
                logger.warning(
                    'Falha ao enviar e-mail de alerta de código de backup para %s',
                    user.email,
                    exc_info=True,
                )

    if not totp_valid and not backup_valid:
        log_security_event('LOGIN_MFA_FAILED', user_id=user.id)
        raise InvalidMfaChallengeError(
            'Código TOTP ou código de backup inválido.'
        )

    tokens = await create_token_pair(db, user, amr=['pwd', 'mfa'])
    log_security_event(
        'LOGIN_SUCCESS', user_id=user.id, metadata={'mfa': True}
    )

    return tokens, user


async def revoke_all_user_sessions(db: AsyncSession, user_id: str) -> None:
    """Revoke every active refresh token of a user (total revocation).

    Single source of truth for invalidating all of a user's sessions. Used by
    password reset, user deactivation, token-reuse containment and sensitive
    role changes. Contrast with ``logout``, which revokes a single token
    (selective revocation).
    """
    await RefreshTokenRepository(db).revoke_all_for_user(user_id)


async def refresh_tokens(db: AsyncSession, refresh_token: str) -> Token:
    """Rotate a refresh token and issue a fresh pair.

    The used refresh token is revoked and replaced. If a revoked/rotated
    token is reused, all active refresh tokens of the user are revoked as a
    containment measure (possible token compromise).
    """
    try:
        payload = decode_refresh_token(refresh_token)
    except pyjwt.InvalidTokenError:
        raise InvalidRefreshTokenError() from None

    jti = payload.get('jti')
    subject = payload.get('sub')
    if not jti or not subject:
        raise InvalidRefreshTokenError()

    refresh_repository = RefreshTokenRepository(db)
    record = await refresh_repository.get_by_jti_for_update(jti)

    if record is None:
        raise InvalidRefreshTokenError()

    if record.revoked:
        revoked_at = (
            ensure_utc(record.revoked_at) if record.revoked_at else None
        )
        settings = get_settings()
        grace_period = settings.JWT_REFRESH_GRACE_PERIOD_SECONDS

        time_since_revocation = (
            (utcnow() - revoked_at).total_seconds() if revoked_at else None
        )

        if (
            time_since_revocation is None
            or time_since_revocation > grace_period
        ):
            await revoke_all_user_sessions(db, record.user_id)
            await db.commit()

        raise InvalidRefreshTokenError()

    if ensure_utc(record.expires_at) <= utcnow():
        raise InvalidRefreshTokenError()

    user_repository = UserRepository(db)
    user = await user_repository.get(record.user_id)
    if user is None or not user.is_active:
        raise InvalidRefreshTokenError()

    await refresh_repository.revoke(jti)
    return await create_token_pair(db, user)


async def logout(
    db: AsyncSession,
    refresh_token: str,
    *,
    client_ip: str | None = None,
    access_token: str | None = None,
) -> None:
    """Revoke the given refresh token and blacklist the active access token.

    Idempotent for tokens that are or were valid; malformed or unknown
    tokens are rejected.
    """
    try:
        payload = decode_refresh_token(refresh_token)
    except pyjwt.InvalidTokenError:
        raise InvalidRefreshTokenError() from None

    jti = payload.get('jti')
    if not jti:
        raise InvalidRefreshTokenError()

    refresh_repository = RefreshTokenRepository(db)
    record = await refresh_repository.get_by_jti(jti)
    if record is None:
        raise InvalidRefreshTokenError()

    if not record.revoked:
        await refresh_repository.revoke(jti)
        await db.commit()

    if access_token:
        with contextlib.suppress(pyjwt.InvalidTokenError):
            access_payload = decode_access_token(access_token)
            access_jti = access_payload.get('jti')
            if access_jti:
                await blacklist_access_token(access_jti)

    log_security_event(
        'LOGOUT',
        user_id=record.user_id,
        ip=client_ip,
        metadata={'token_id': jti},
    )


async def request_password_reset(
    db: AsyncSession, email: str, *, client_ip: str | None = None
) -> None:
    """Generate a short-lived reset token and e-mail the reset link.

    The response never reveals whether the e-mail is registered.
    """
    settings = get_settings()

    user_repository = UserRepository(db)
    user = await user_repository.get_by_email(email)
    if user is None or not user.is_active:
        return

    token = generate_opaque_token()
    expires_at = utcnow() + timedelta(
        minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES
    )

    reset_repository = PasswordResetTokenRepository(db)
    await reset_repository.create(
        user_id=user.id, token=token, expires_at=expires_at
    )
    await db.commit()

    log_security_event(
        'PASSWORD_RESET_REQUESTED', user_id=user.id, ip=client_ip
    )

    reset_link = (
        f'{settings.APP_BASE_URL}/auth/password-reset/confirm?token={token}'
    )
    await email_service.send_password_reset_email(user.email, reset_link)

    # Publish auth.password_reset_requested event
    bus = get_event_bus()

    await bus.publish(
        Event(
            type=AuthEvents.PASSWORD_RESET_REQUESTED,
            payload={
                'user_id': user.id,
                'email': user.email,
                'expires_at': expires_at.isoformat(),
                'client_ip': client_ip,
            },
        )
    )


async def request_password_reset_bg(
    email: str, *, client_ip: str | None = None
) -> None:
    """Background task entry point for requesting password reset with an isolated DB session."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        await request_password_reset(session, email, client_ip=client_ip)


async def reset_password(
    db: AsyncSession,
    token: str,
    new_password: str,
    *,
    client_ip: str | None = None,
) -> None:
    """Validate a reset token and replace the user's password.

    The token can only be used once and expires after a short window. All
    active refresh tokens of the user are revoked so other sessions must
    log in again.
    """
    now = utcnow()

    reset_repository = PasswordResetTokenRepository(db)
    record = await reset_repository.get_by_token(token)
    if record is None:
        raise InvalidOrExpiredTokenError()

    if record.used:
        raise TokenAlreadyUsedError()

    if ensure_utc(record.expires_at) <= now:
        raise InvalidOrExpiredTokenError()

    user_repository = UserRepository(db)
    user = await user_repository.get(record.user_id)
    if user is None:
        raise InvalidOrExpiredTokenError()

    user.hashed_password = await hash_password_async(new_password)
    await reset_repository.mark_used(record, used_at=now)

    await revoke_all_user_sessions(db, user.id)

    # Clear rate limiter keys for user's email and client IP
    email_key = build_email_login_key(user.email)
    await reset_login_attempts_async(email_key)
    await redis_reset(email_key)
    await redis_reset(f'rate_limit:{email_key}')

    legacy_email_key = build_login_key(user.email, None)
    await reset_login_attempts_async(legacy_email_key)
    await redis_reset(legacy_email_key)

    if client_ip:
        ip_key = build_ip_login_key(client_ip)
        await reset_login_attempts_async(ip_key)
        await redis_reset(ip_key)
        await redis_reset(f'rate_limit:{ip_key}')

        legacy_ip_key = build_login_key(user.email, client_ip)
        await reset_login_attempts_async(legacy_ip_key)
        await redis_reset(legacy_ip_key)

    await db.commit()

    log_security_event(
        'PASSWORD_RESET_COMPLETED', user_id=user.id, ip=client_ip
    )

    # Publish auth.password_reset_completed event
    bus = get_event_bus()
    await bus.publish(
        Event(
            type=AuthEvents.PASSWORD_RESET_COMPLETED,
            payload={
                'user_id': user.id,
                'email': user.email,
                'client_ip': client_ip,
            },
        )
    )


async def verify_email(
    db: AsyncSession, token: str, *, client_ip: str | None = None
) -> None:
    """Confirm a user's e-mail address using a single-use token."""
    now = utcnow()

    verification_repository = EmailVerificationTokenRepository(db)
    record = await verification_repository.get_by_token(token)
    if record is None:
        raise InvalidOrExpiredTokenError()

    if record.used:
        raise TokenAlreadyUsedError()

    if ensure_utc(record.expires_at) <= now:
        raise InvalidOrExpiredTokenError()

    user_repository = UserRepository(db)
    user = await user_repository.get(record.user_id)
    if user is None:
        raise InvalidOrExpiredTokenError()

    user.is_verified = True
    await verification_repository.mark_used(record, used_at=now)
    await db.commit()

    log_security_event('EMAIL_VERIFIED', user_id=user.id, ip=client_ip)

    # Publish user.email_verified event
    bus = get_event_bus()
    await bus.publish(
        Event(
            type=UserEvents.EMAIL_VERIFIED,
            payload={
                'user_id': user.id,
                'email': user.email,
            },
        )
    )


async def send_verification_email_for_user(
    db: AsyncSession, user: User
) -> None:
    """Create a verification token and e-mail it to the user (if unverified)."""
    settings = get_settings()

    if user.is_verified:
        return

    token = generate_opaque_token()
    expires_at = utcnow() + timedelta(
        minutes=settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES
    )

    verification_repository = EmailVerificationTokenRepository(db)
    await verification_repository.create(
        user_id=user.id, token=token, expires_at=expires_at
    )
    await db.commit()

    verify_link = f'{settings.APP_BASE_URL}/auth/verify-email?token={token}'
    await email_service.send_verification_email(user.email, verify_link)


async def resend_verification_email(db: AsyncSession, email: str) -> None:
    """Send a fresh verification link to a registered, unverified user."""
    user_repository = UserRepository(db)
    user = await user_repository.get_by_email(email)
    if user is None or user.is_verified or not user.is_active:
        return

    await send_verification_email_for_user(db, user)


async def resend_verification_email_bg(email: str) -> None:
    """Background task entry point for resending verification email with an isolated DB session."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        await resend_verification_email(session, email)
