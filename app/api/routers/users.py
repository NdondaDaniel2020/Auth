from __future__ import annotations

from fastapi import APIRouter

from app.api.dependencies.auth import CurrentUserDep
from app.models.user import User
from app.schemas.user import UserPublic

router = APIRouter(prefix='/users', tags=['users'])


@router.get('/me', response_model=UserPublic)
async def read_current_user(user: CurrentUserDep) -> User:
    """Return the profile of the currently authenticated user.

    The user is resolved entirely from the access token; no parameters are
    accepted. Only public fields are exposed (never ``hashed_password``).
    """
    return UserPublic.model_validate(user)
