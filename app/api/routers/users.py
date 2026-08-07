from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies.auth import CurrentUserDep
from app.api.dependencies.database import SessionDep
from app.api.dependencies.pagination import PaginationParamsDep
from app.api.dependencies.permissions import require_role
from app.models.user import User
from app.schemas.pagination import PaginatedResponse
from app.schemas.user import UserPublic, UserRead, UserUpdate
from app.services.user_service import get_user, list_users, update_profile

router = APIRouter(prefix='/users', tags=['users'])


@router.get('/me', response_model=UserPublic)
async def read_current_user(user: CurrentUserDep) -> User:
    """Return the profile of the currently authenticated user.

    The user is resolved entirely from the access token; no parameters are
    accepted. Only public fields are exposed (never ``hashed_password``).
    """
    return UserPublic.model_validate(user)


@router.patch('/me', response_model=UserRead)
async def update_current_user(
    user: CurrentUserDep,
    data: UserUpdate,
    db: SessionDep,
) -> UserRead:
    """Partially update the authenticated user's own profile.

    Only fields defined in ``UserUpdate`` are accepted (currently
    ``full_name``); unknown keys, including sensitive fields such as
    ``is_active`` or ``hashed_password``, are rejected with HTTP 422.
    """
    return await update_profile(db, user, data)


@router.get('', response_model=PaginatedResponse[UserRead])
async def list_all_users(
    db: SessionDep,
    admin_user: Annotated[User, Depends(require_role('admin'))],
    pagination: PaginationParamsDep,
) -> PaginatedResponse[UserRead]:
    """List all users with pagination (admin only).

    Default ``page_size`` is 20 (max 100); pages are ordered by creation
    date. Each item is serialized through ``UserRead`` (no sensitive fields).
    """
    return await list_users(
        db,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get('/{user_id}', response_model=UserRead)
async def get_user_by_id(
    db: SessionDep,
    admin_user: Annotated[User, Depends(require_role('admin'))],
    user_id: uuid.UUID,
) -> UserRead:
    """Return a single user by ``id`` (admin only).

    The ``id`` is validated as a UUID (malformed values yield HTTP 422);
    unknown users yield HTTP 404 via ``UserNotFoundError``.
    """
    return await get_user(db, user_id=str(user_id))
