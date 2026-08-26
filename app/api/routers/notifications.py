"""Router for notifications and real-time event catch-up sync."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.api.dependencies.auth import CurrentUserDep
from app.api.dependencies.database import SessionDep
from app.api.dependencies.rate_limit import rate_limit
from app.repositories.notification_repository import NotificationRepository
from app.schemas.notification import NotificationRead, NotificationSyncResponse

router = APIRouter(prefix='/notifications', tags=['notifications'])


@router.get(
    '/sync',
    response_model=NotificationSyncResponse,
    dependencies=[Depends(rate_limit('RATE_LIMIT_DEFAULT'))],
)
async def sync_notifications(
    user: CurrentUserDep,
    db: SessionDep,
    since_id: int | None = Query(
        None,
        description='Last known notification ID processed by the client',
    ),
    since_timestamp: datetime | None = Query(
        None,
        description='UTC timestamp of the last client synchronization',
    ),
    limit: int = Query(
        50,
        ge=1,
        le=100,
        description='Maximum number of notifications to return (1-100)',
    ),
) -> NotificationSyncResponse:
    """Fetch missed notifications and events for REST Catch-Up synchronization.

    Called by WebSocket clients upon reconnection to catch up on missed events
    during temporary disconnections or ping/pong heartbeat timeouts.
    """
    repo = NotificationRepository(db)
    items = await repo.get_missed_notifications(
        user_id=user.id,
        since_id=since_id,
        since_timestamp=since_timestamp,
        limit=limit + 1,
    )

    has_more = len(items) > limit
    returned_items = items[:limit]

    events = [NotificationRead.model_validate(item) for item in returned_items]
    last_id = events[-1].id if events else since_id

    return NotificationSyncResponse(
        events=events,
        total=len(events),
        has_more=has_more,
        last_id=last_id,
    )
