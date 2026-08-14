"""Housekeeping service for periodic database cleanup of expired tokens."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.repositories.email_verification_repository import (
    EmailVerificationTokenRepository,
)
from app.repositories.password_reset_repository import (
    PasswordResetTokenRepository,
)
from app.repositories.refresh_token_repository import RefreshTokenRepository

logger = logging.getLogger(__name__)

_cleanup_task: asyncio.Task | None = None


async def cleanup_expired_tokens(db: AsyncSession) -> dict[str, int]:
    """Delete expired refresh, password reset, and email verification tokens."""
    now = datetime.now(UTC)
    refresh_repo = RefreshTokenRepository(db)
    reset_repo = PasswordResetTokenRepository(db)
    verify_repo = EmailVerificationTokenRepository(db)

    deleted_refresh = await refresh_repo.delete_expired(now)
    deleted_reset = await reset_repo.delete_expired(now)
    deleted_verify = await verify_repo.delete_expired(now)

    await db.commit()

    total_deleted = deleted_refresh + deleted_reset + deleted_verify
    if total_deleted > 0:
        logger.info(
            'Cleaned up %d expired tokens (refresh: %d, reset: %d, verify: %d)',
            total_deleted,
            deleted_refresh,
            deleted_reset,
            deleted_verify,
        )

    return {
        'refresh_tokens': deleted_refresh,
        'password_reset_tokens': deleted_reset,
        'email_verification_tokens': deleted_verify,
    }


async def _run_cleanup_loop(interval_minutes: int) -> None:
    interval_seconds = max(10, interval_minutes * 60)
    logger.info(
        'Token cleanup background loop started (interval: %d minutes)',
        interval_minutes,
    )
    try:
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                session_factory = get_session_factory()
                async with session_factory() as session:
                    await cleanup_expired_tokens(session)
            except Exception as e:  # noqa: BLE001
                logger.warning('Token cleanup loop execution failed: %s', e)
    except asyncio.CancelledError:
        logger.info('Token cleanup background loop stopped')


async def start_token_cleanup_loop() -> None:
    global _cleanup_task
    settings = get_settings()
    interval = getattr(settings, 'TOKEN_CLEANUP_INTERVAL_MINUTES', 60)
    if interval <= 0:
        logger.info('Token cleanup background loop disabled')
        return
    if _cleanup_task is None or _cleanup_task.done():
        _cleanup_task = asyncio.create_task(_run_cleanup_loop(interval))


async def stop_token_cleanup_loop() -> None:
    global _cleanup_task
    if _cleanup_task is not None and not _cleanup_task.done():
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass
        _cleanup_task = None
