from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Notification(Base):
    """Persisted user notification/event record for real-time delivery and catch-up sync.

    Records notifications emitted to users with auto-incrementing ID for strict
    sequence ordering during WebSocket reconnect sync (REST Catch-Up).
    """

    __tablename__ = 'notifications'
    __table_args__ = (
        Index('ix_notifications_user_id_id', 'user_id', 'id'),
        Index('ix_notifications_user_id_created_at', 'user_id', 'created_at'),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
    )
    channel: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default='in_app',
    )
    event_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    message: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
    )
    read: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f'<Notification id={self.id} user_id={self.user_id!r} '
            f'event_type={self.event_type!r} read={self.read}>'
        )
