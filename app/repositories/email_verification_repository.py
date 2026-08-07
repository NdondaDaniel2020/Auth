from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update

from app.models.email_verification_token import EmailVerificationToken
from app.repositories.base import BaseRepository
from app.utils.tokens import hash_token


class EmailVerificationTokenRepository(BaseRepository[EmailVerificationToken]):
    def __init__(self, session):
        super().__init__(session, EmailVerificationToken)

    async def create(  # type: ignore[override]
        self,
        *,
        user_id: str,
        token: str,
        expires_at: datetime,
    ) -> EmailVerificationToken:
        record = EmailVerificationToken(
            user_id=user_id,
            token_hash=hash_token(token),
            expires_at=expires_at,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def get_by_token(self, token: str) -> EmailVerificationToken | None:
        result = await self.session.execute(
            select(EmailVerificationToken).where(
                EmailVerificationToken.token_hash == hash_token(token)
            )
        )
        return result.scalar_one_or_none()

    async def mark_used(
        self, record: EmailVerificationToken, *, used_at: datetime
    ) -> None:
        await self.session.execute(
            update(EmailVerificationToken)
            .where(EmailVerificationToken.id == record.id)
            .values(used=True, used_at=used_at)
        )
