from __future__ import annotations

from typing import Annotated

import jwt as pyjwt
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer

from app.api.dependencies.database import SessionDep
from app.core.exceptions import (
    AccountInactiveError,
    NotAuthenticatedError,
    TokenExpiredError,
    TokenInvalidError,
)
from app.core.security import decode_access_token
from app.models.user import User
from app.repositories.user_repository import UserRepository

# The dependency for retrieving the current authenticated user. Every
# protected endpoint declares ``user: CurrentUserDep`` (or composes
# ``require_role``/``check_permission`` from ``permissions.py``). This module
# is the single source of truth for extracting the access token.
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl='/api/auth/login-form',
    auto_error=False,
)


async def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    db: SessionDep,
) -> User:
    """Resolve the authenticated user from the JWT access token.

    Maps each failure scenario to a stable error ``code`` (HTTP 401):
    missing token → ``NOT_AUTHENTICATED``, malformed token →
    ``TOKEN_INVALID``, expired token → ``TOKEN_EXPIRED``, inactive/unknown
    account → ``ACCOUNT_INACTIVE``.
    """
    if token is None:
        raise NotAuthenticatedError()

    try:
        payload = decode_access_token(token)
    except pyjwt.ExpiredSignatureError:
        raise TokenExpiredError() from None
    except pyjwt.InvalidTokenError:
        raise TokenInvalidError() from None

    user_id = payload.get('sub')
    if not user_id:
        raise TokenInvalidError()

    jti = payload.get('jti')
    if jti and await is_access_token_blacklisted(jti):
        raise TokenInvalidError()

    user = await UserRepository(db).get_by_id(user_id)
    if user is None or not user.is_active:
        raise AccountInactiveError()

    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]
