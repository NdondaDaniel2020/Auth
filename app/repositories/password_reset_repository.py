from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select, update

from app.models.password_reset_token import PasswordResetToken
from app.repositories.base import BaseRepository
from app.utils.tokens import hash_token


class PasswordResetTokenRepository(BaseRepository[PasswordResetToken]):
    def __init__(self, session):
        super().__init__(session, PasswordResetToken)

    async def create(  # type: ignore[override]
        self,
        *,
        user_id: str,
        token: str,
        expires_at: datetime,
    ) -> PasswordResetToken:
        record = PasswordResetToken(
            user_id=user_id,
            token_hash=hash_token(token),
            expires_at=expires_at,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def get_by_token(self, token: str) -> PasswordResetToken | None:
        result = await self.session.execute(
            select(PasswordResetToken).where(
                PasswordResetToken.token_hash == hash_token(token)
            )
        )
        return result.scalar_one_or_none()

    async def mark_used(
        self, record: PasswordResetToken, *, used_at: datetime
    ) -> None:
        await self.session.execute(
            update(PasswordResetToken)
            .where(PasswordResetToken.id == record.id)
            .values(used=True, used_at=used_at)
        )

    async def delete_expired(self, before: datetime | None = None) -> int:
        cutoff = before or datetime.now(UTC)
        result = await self.session.execute(
            delete(PasswordResetToken).where(
                PasswordResetToken.expires_at < cutoff
            )
        )
        return result.rowcount  # type: ignore[attr-defined]
