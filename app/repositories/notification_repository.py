from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification
from app.repositories.base import BaseRepository


class NotificationRepository(BaseRepository[Notification]):
    """Repository for managing persisted user notifications and catch-up sync queries."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Notification)

    async def add_notification(
        self,
        *,
        user_id: str,
        event_type: str,
        title: str,
        message: str,
        channel: str = 'in_app',
        details: dict[str, Any] | None = None,
    ) -> Notification:
        """Create and persist a notification record."""
        notification = Notification(
            user_id=user_id,
            event_type=event_type,
            title=title,
            message=message,
            channel=channel,
            details=details,
        )
        self.session.add(notification)
        await self.session.commit()
        await self.session.refresh(notification)
        return notification

    async def get_missed_notifications(
        self,
        user_id: str,
        *,
        since_id: int | None = None,
        since_timestamp: datetime | None = None,
        limit: int = 50,
    ) -> list[Notification]:
        """Fetch notifications for a user created after since_id or since_timestamp."""
        stmt = select(Notification).where(Notification.user_id == user_id)

        if since_id is not None:
            stmt = stmt.where(Notification.id > since_id)
        elif since_timestamp is not None:
            stmt = stmt.where(Notification.created_at > since_timestamp)

        stmt = stmt.order_by(Notification.id.asc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
