"""Audit service for sensitive administrative actions."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.audit import compute_audit_hash
from app.repositories.audit_repository import AuditRepository


async def record_admin_action(
    db: AsyncSession,
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


async def verify_audit_trail_integrity(
    db: AsyncSession,
) -> tuple[bool, list[str]]:
    """Verify cryptographic integrity and continuity of the audit trail.

    Returns:
        (True, []) if the hash chain is fully intact.
        (False, errors) if any record was tampered with, deleted or out-of-order.
    """
    records = await AuditRepository(db).list_all_chronological()
    errors: list[str] = []
    expected_previous_hash: str | None = None

    for idx, record in enumerate(records):
        if record.previous_hash != expected_previous_hash:
            errors.append(
                f'Record {record.id} (index {idx}): broken previous_hash chain. '
                f'Expected {expected_previous_hash!r}, found {record.previous_hash!r}.'
            )

        computed_hash = compute_audit_hash(
            id=record.id,
            actor_user_id=record.actor_user_id,
            action=record.action,
            resource_type=record.resource_type,
            resource_id=record.resource_id,
            result=record.result,
            details=record.details,
            created_at=record.created_at,
            previous_hash=record.previous_hash,
        )
        if record.hash != computed_hash:
            errors.append(
                f'Record {record.id} (index {idx}): hash mismatch. '
                f'Stored {record.hash!r}, computed {computed_hash!r}.'
            )

        expected_previous_hash = record.hash

    return (len(errors) == 0, errors)
