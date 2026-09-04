from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuditImmutabilityError
from app.core.security.audit import compute_audit_hash
from app.models.audit_log import AuditLog
from app.repositories.base import BaseRepository


class AuditRepository(BaseRepository[AuditLog]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, AuditLog)

    async def update(self, *args: Any, **kwargs: Any) -> AuditLog:
        """Prevent updates to audit logs."""
        raise AuditImmutabilityError(
            'A tabela audit_logs é append-only. Operações de UPDATE são proibidas.'
        )

    async def delete(self, *args: Any, **kwargs: Any) -> None:
        """Prevent deletion of audit logs."""
        raise AuditImmutabilityError(
            'A tabela audit_logs é append-only. Operações de DELETE são proibidas.'
        )

    async def add_record(
        self,
        *,
        actor_user_id: str | None,
        action: str,
        resource_type: str,
        resource_id: str,
        result: str = 'success',
        details: dict[str, Any] | None = None,
    ) -> AuditLog:
        """Create an audit record within the caller's transaction."""
        """Create an audit record with cryptographic hash chain."""
        # Query the latest hash in the audit chain
        last_hash_stmt = (
            select(AuditLog.hash)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(1)
        )
        previous_hash = await self.session.scalar(last_hash_stmt)

        record_id = str(uuid4())
        created_at = datetime.now(UTC)
        record_hash = compute_audit_hash(
            id=record_id,
            actor_user_id=actor_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            result=result,
            details=details,
            created_at=created_at,
            previous_hash=previous_hash,
        )

        record = AuditLog(
            id=record_id,
            actor_user_id=actor_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            result=result,
            details=details,
            created_at=created_at,
            previous_hash=previous_hash,
            hash=record_hash,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def list_all_chronological(self) -> list[AuditLog]:
        """Fetch all audit logs in chronological order for integrity verification."""
        stmt = select(AuditLog).order_by(
            AuditLog.created_at.asc(), AuditLog.id.asc()
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
