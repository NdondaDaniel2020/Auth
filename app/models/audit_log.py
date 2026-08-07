from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditLog(Base):
    """Immutable trail of sensitive administrative actions.

    Every record identifies who acted (``actor_user_id``), what was done
    (``action``), on which resource (``resource_type``/``resource_id``), when
    (``created_at``) and with which outcome (``result``). ``details`` carries
    optional extra context (e.g. the new role set).
    """

    __tablename__ = 'audit_logs'
    __table_args__ = (
        Index('ix_audit_logs_actor_user_id', 'actor_user_id'),
        Index('ix_audit_logs_resource', 'resource_type', 'resource_id'),
        Index('ix_audit_logs_created_at', 'created_at'),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    actor_user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(64), nullable=False)
    result: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default='success',
    )
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f'<AuditLog id={self.id!r} action={self.action!r} '
            f'resource={self.resource_type}:{self.resource_id} '
            f'result={self.result!r}>'
        )
