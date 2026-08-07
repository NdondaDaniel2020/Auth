from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from app.models.role import Role
from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, session):
        super().__init__(session, User)

    async def get_by_id(self, user_id: str) -> User | None:
        result = await self.session.execute(
            select(User)
            .options(selectinload(User.roles).selectinload(Role.permissions))
            .where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(
            select(User)
            .options(selectinload(User.roles))
            .where(User.email == email.lower())
        )
        return result.scalar_one_or_none()

    async def create(
        self, *, email: str, hashed_password: str, full_name: str | None = None
    ) -> User:
        user = User(
            email=email.lower(),
            hashed_password=hashed_password,
            full_name=full_name,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def list_users(
        self, *, offset: int = 0, limit: int = 20
    ) -> list[User]:
        """Return a page of users ordered by creation date (oldest first).

        Explicit ordering keeps pagination deterministic between requests.
        """
        result = await self.session.execute(
            select(User).order_by(User.created_at).offset(offset).limit(limit)
        )
        return list(result.scalars().all())

    async def count_users(self) -> int:
        """Return the total number of users, for pagination metadata."""
        result = await self.session.execute(
            select(func.count()).select_from(User)
        )
        return int(result.scalar_one())

    async def set_active_status(self, user_id: str, is_active: bool) -> None:
        """Update only the ``is_active`` flag (soft activate/deactivate)."""
        await self.session.execute(
            update(User).where(User.id == user_id).values(is_active=is_active)
        )
