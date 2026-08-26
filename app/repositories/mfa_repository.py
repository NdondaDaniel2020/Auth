from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.models.mfa_method import MfaMethod
from app.repositories.base import BaseRepository


class MfaRepository(BaseRepository[MfaMethod]):
    def __init__(self, session):
        super().__init__(session, MfaMethod)

    async def get_by_user_and_type(
        self, user_id: str, type: str = 'totp'
    ) -> MfaMethod | None:
        """Fetch the MFA method record for a specific user and type."""
        stmt = select(MfaMethod).where(
            MfaMethod.user_id == user_id, MfaMethod.type == type
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_by_user_and_type(
        self, user_id: str, type: str = 'totp'
    ) -> MfaMethod | None:
        """Fetch the active MFA method record for a specific user and type."""
        stmt = select(MfaMethod).where(
            MfaMethod.user_id == user_id,
            MfaMethod.type == type,
            MfaMethod.is_active.is_(True),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_pending_secret(
        self, user_id: str, secret: str, type: str = 'totp'
    ) -> MfaMethod:
        """Create or update a pending (inactive) MFA method secret for a user."""
        mfa_method = await self.get_by_user_and_type(user_id, type=type)
        if mfa_method:
            mfa_method.secret = secret
            mfa_method.is_active = False
        else:
            mfa_method = MfaMethod(
                user_id=user_id,
                type=type,
                secret=secret,
                is_active=False,
            )
            self.session.add(mfa_method)
        await self.session.flush()
        return mfa_method

    async def activate_method(
        self,
        mfa_method: MfaMethod,
        data: dict[str, Any] | None = None,
    ) -> MfaMethod:
        """Activate an MFA method record and store its metadata."""
        mfa_method.is_active = True
        if data is not None:
            mfa_method.data = data
        await self.session.flush()
        return mfa_method

    async def deactivate_method(self, mfa_method: MfaMethod) -> None:
        """Deactivate an MFA method record and clear sensitive fields."""
        mfa_method.is_active = False
        mfa_method.secret = None
        mfa_method.data = None
        await self.session.flush()
