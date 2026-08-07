from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class PasswordResetToken(Base):
    """Single-use token for resetting a user's password.

    The raw token (high-entropy, short-lived) is only shown to the caller;
    the database stores its SHA-256 hash so a leaked database cannot be used
    to reset passwords directly.
    """

    __tablename__ = 'password_reset_tokens'
    __table_args__ = (
        Index('ix_password_reset_tokens_token_hash', 'token_hash', unique=True),
        Index('ix_password_reset_tokens_user_id', 'user_id'),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    used: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default='0',
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="password_reset_tokens")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PasswordResetToken user_id={self.user_id!r} used={self.used}>"
