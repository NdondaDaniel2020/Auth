from __future__ import annotations

from typing import Any

from app.models.audit_log import AuditLog
from app.repositories.base import BaseRepository


class AuditRepository(BaseRepository[AuditLog]):
    def __init__(self, session):
        super().__init__(session, AuditLog)

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
        record = AuditLog(
            actor_user_id=actor_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            result=result,
            details=details,
        )
        self.session.add(record)
        await self.session.flush()
        return record
