"""Router for notifications and real-time event catch-up sync."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

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
    since_id: Annotated[
        int | None,
        Query(
            description='Last known notification ID processed by the client',
        ),
    ] = None,
    since_timestamp: Annotated[
        datetime | None,
        Query(
            description='UTC timestamp of the last client synchronization',
        ),
    ] = None,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=100,
            description='Maximum number of notifications to return (1-100)',
        ),
    ] = 50,
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
