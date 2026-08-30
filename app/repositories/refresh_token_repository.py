from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select, update

from app.models.refresh_token import RefreshToken
from app.repositories.base import BaseRepository


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    def __init__(self, session):
        super().__init__(session, RefreshToken)

    async def get_by_jti(self, jti: str) -> RefreshToken | None:
        result = await self.session.execute(
            select(RefreshToken).where(RefreshToken.jti == jti)
        )
        return result.scalar_one_or_none()

    async def get_by_jti_for_update(self, jti: str) -> RefreshToken | None:
        result = await self.session.execute(
            select(RefreshToken)
            .where(RefreshToken.jti == jti)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def create(  # type: ignore[override]
        self,
        *,
        jti: str,
        user_id: str,
        expires_at: datetime,
        ip_address: str | None = None,
        user_agent: str | None = None,
        device_name: str | None = None,
        location: str | None = None,
        last_seen_at: datetime | None = None,
    ) -> RefreshToken:
        token = RefreshToken(
            jti=jti,
            user_id=user_id,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
            device_name=device_name,
            location=location,
            last_seen_at=last_seen_at,
        )
        self.session.add(token)
        await self.session.flush()
        return token

    async def list_active_by_user(self, user_id: str) -> list[RefreshToken]:
        """Retorna todas as sessões ativas (não revogadas e não expiradas) do usuário."""
        now = datetime.now(UTC)
        result = await self.session.execute(
            select(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked.is_(False),
                RefreshToken.expires_at > now,
            )
            .order_by(RefreshToken.created_at.desc())
        )
        return list(result.scalars().all())

    async def revoke(self, jti: str) -> None:
        await self.session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.jti == jti,
                RefreshToken.revoked.is_(False),
            )
            .values(revoked=True, revoked_at=datetime.now(UTC))
        )

    async def revoke_by_jti_and_user(self, jti: str, user_id: str) -> bool:
        """Revoga uma sessão específica pertencente ao usuário. Retorna True se revogada com sucesso."""
        result = await self.session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.jti == jti,
                RefreshToken.user_id == user_id,
                RefreshToken.revoked.is_(False),
            )
            .values(revoked=True, revoked_at=datetime.now(UTC))
        )
        rowcount: int = result.rowcount  # type: ignore[attr-defined]
        return (rowcount or 0) > 0

    async def revoke_other_sessions(
        self, user_id: str, current_jti: str
    ) -> int:
        """Revoga todas as outras sessões ativas do usuário, exceto a atual."""
        result = await self.session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.jti != current_jti,
                RefreshToken.revoked.is_(False),
            )
            .values(revoked=True, revoked_at=datetime.now(UTC))
        )
        return result.rowcount or 0  # type: ignore[attr-defined]

    async def revoke_all_for_user(self, user_id: str) -> None:
        await self.session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked.is_(False),
            )
            .values(revoked=True, revoked_at=datetime.now(UTC))
        )

    async def delete_expired(self, before: datetime | None = None) -> int:
        cutoff = before or datetime.now(UTC)
        result = await self.session.execute(
            delete(RefreshToken).where(RefreshToken.expires_at < cutoff)
        )
        return result.rowcount  # type: ignore[attr-defined]
