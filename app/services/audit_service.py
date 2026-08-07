"""Audit service for sensitive administrative actions."""

from __future__ import annotations

from typing import Any

from app.repositories.audit_repository import AuditRepository


async def record_admin_action(
    db,
    *,
    actor_user_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str,
    result: str = 'success',
    details: dict[str, Any] | None = None,
) -> None:
    """Persist an audit record in the caller's transaction (atomic).

    The record shares the transaction of the operation it describes, so a
    failure rolls both back: an audit entry can never exist for a change that
    did not happen, and a successful change always carries its entry.
    """
    await AuditRepository(db).add_record(
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        result=result,
        details=details,
    )
