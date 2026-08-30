from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.exceptions import SessionNotFoundError
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.schemas.session import (
    SessionListResponse,
    SessionResponse,
    SessionRevokeResponse,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def list_user_sessions(
    db: AsyncSession,
    user_id: str,
    current_jti: str | None = None,
) -> SessionListResponse:
    """Lista todas as sessões ativas (não revogadas e não expiradas) do usuário."""
    repo = RefreshTokenRepository(db)
    tokens = await repo.list_active_by_user(user_id)

    sessions = [
        SessionResponse(
            jti=token.jti,
            device_name=token.device_name,
            ip_address=token.ip_address,
            location=token.location,
            created_at=token.created_at,
            last_seen_at=token.last_seen_at,
            is_current=(token.jti == current_jti) if current_jti else False,
        )
        for token in tokens
    ]

    return SessionListResponse(sessions=sessions, total=len(sessions))


async def revoke_user_session(
    db: AsyncSession,
    user_id: str,
    target_jti: str,
) -> SessionRevokeResponse:
    """Revoga uma sessão específica do usuário."""
    repo = RefreshTokenRepository(db)
    revoked = await repo.revoke_by_jti_and_user(target_jti, user_id)
    if not revoked:
        raise SessionNotFoundError('Sessão não encontrada ou já encerrada.')

    await db.commit()
    return SessionRevokeResponse(
        message='Sessão revogada com sucesso.',
        revoked_count=1,
    )


async def revoke_all_other_sessions(
    db: AsyncSession,
    user_id: str,
    current_jti: str,
) -> SessionRevokeResponse:
    """Revoga todas as outras sessões ativas do usuário, mantendo apenas a atual."""
    repo = RefreshTokenRepository(db)
    count = await repo.revoke_other_sessions(user_id, current_jti)
    await db.commit()
    return SessionRevokeResponse(
        message=f'{count} outra(s) sessão(ões) revogada(s) com sucesso.',
        revoked_count=count,
    )
