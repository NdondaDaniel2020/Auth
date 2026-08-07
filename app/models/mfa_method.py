from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class MfaMethod(Base):
    """A registered multi-factor authentication method for a user.

    Prepared structurally for future MFA support: a user may register
    multiple factors (e.g. ``totp``, ``sms``, ``email``) over time. ``secret``
    holds the factor-specific secret and ``data`` (DB column ``metadata``)
    any extra, method-specific data as JSON, so no single factor type is
    coupled into the schema. No functional MFA flow exists yet (see
    ``docs/mfa-readiness.md``).
    """

    __tablename__ = 'mfa_methods'
    __table_args__ = (
        Index('ix_mfa_methods_user_id', 'user_id'),
        Index('ix_mfa_methods_user_type', 'user_id', 'type'),
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
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    secret: Mapped[str | None] = mapped_column(String(512), nullable=True)
    data: Mapped[dict[str, Any] | None] = mapped_column(
        'metadata', JSON, nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=func.false(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user: Mapped[User] = relationship(
        'User',
        back_populates='mfa_methods',
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f'<MfaMethod id={self.id!r} user_id={self.user_id!r} '
            f'type={self.type!r} active={self.is_active}>'
        )
