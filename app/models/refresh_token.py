from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class RefreshToken(Base):
    """Persisted refresh token used for revocation and rotation.

    The JWT itself carries a unique ``jti`` claim; this table tracks which
    ``jti`` values are still valid so they can be revoked on logout, on
    rotation and on password reset.
    """

    __tablename__ = 'refresh_tokens'
    __table_args__ = (
        Index('ix_refresh_tokens_user_id', 'user_id'),
        Index('ix_refresh_tokens_expires_at', 'expires_at'),
    )

    jti: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    revoked: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        server_default='0',
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    ip_address: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
    )
    user_agent: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )
    device_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    location: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        server_default=func.now(),
    )

    user: Mapped[User] = relationship(back_populates='refresh_tokens')

    def __repr__(self) -> str:  # pragma: no cover
        return f'<RefreshToken jti={self.jti!r} revoked={self.revoked}>'
