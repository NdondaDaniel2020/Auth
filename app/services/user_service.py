from __future__ import annotations

from app.core.exceptions import (
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    SelfDeactivationError,
    TooManyLoginAttemptsError,
    UserNotFoundError,
)
from app.core.rate_limiter import (
    build_login_key,
    check_login_blocked,
    register_failed_login,
    reset_login_attempts,
)
from app.core.security import hash_password, verify_password
from app.models.user import User
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.schemas.pagination import PaginatedResponse
from app.schemas.user import UserCreate, UserRead, UserUpdate


async def register_user(db, data: UserCreate) -> User:
    """Create a new user account.

    Rejects duplicate e-mails (HTTP 409) and always stores the password as a
    hash. The e-mail is normalized to lowercase.
    """
    repository = UserRepository(db)

    existing = await repository.get_by_email(data.email)
    if existing is not None:
        raise EmailAlreadyExistsError()

    user = await repository.create(
        email=data.email,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
    )
    await db.commit()
    return user


async def authenticate_user(
    db,
    email: str,
    password: str,
    *,
    client_ip: str | None = None,
) -> User:
    """Authenticate a user with e-mail/password.

    Failed attempts are counted per identifier (e-mail/IP). When the limit is
    reached the identifier is temporarily blocked and a 429 is returned,
    without revealing whether the credentials themselves were wrong.
    """
    login_key = build_login_key(email, client_ip)

    blocked_seconds = check_login_blocked(login_key)
    if blocked_seconds is not None:
        raise TooManyLoginAttemptsError(retry_after=blocked_seconds)

    repository = UserRepository(db)
    user = await repository.get_by_email(email)

    if (
        user is None
        or not user.is_active
        or not verify_password(password, user.hashed_password)
    ):
        register_failed_login(login_key)
        raise InvalidCredentialsError()

    reset_login_attempts(login_key)
    return user


async def list_users(
    db,
    *,
    page: int = 1,
    page_size: int = 20,
) -> PaginatedResponse[UserRead]:
    """List users with pagination.

    Orchestrates the repository calls (count + page) and assembles the
    paginated envelope, serializing rows through ``UserRead`` so no sensitive
    field (e.g. ``hashed_password``) ever reaches the response.
    """
    repository = UserRepository(db)
    total = await repository.count_users()
    users = await repository.list_users(
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    items = [UserRead.model_validate(user) for user in users]
    return PaginatedResponse[UserRead](
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


async def get_user(db, *, user_id: str) -> UserRead:
    """Fetch a single user by ``id`` (admin scope).

    Raises ``UserNotFoundError`` (HTTP 404) when no user matches. The result
    is serialized through ``UserRead``, which never exposes ``hashed_password``.
    """
    user = await UserRepository(db).get_by_id(user_id)
    if user is None:
        raise UserNotFoundError()
    return UserRead.model_validate(user)


async def update_profile(db, user: User, data: UserUpdate) -> UserRead:
    """Apply a partial update to the authenticated user's own profile.

    Only fields present in the payload (``model_fields_set``) are applied, so
    omitted optional fields are untouched. Sensitive fields cannot be supplied
    because ``UserUpdate`` forbids unknown keys. ``updated_at`` is bumped by
    the model's ``onupdate`` trigger.
    """
    updates = data.model_dump(exclude_unset=True)
    if updates:
        user = await UserRepository(db).update(user, updates)
    return UserRead.model_validate(user)


async def _set_active_status(
    db,
    *,
    user_id: str,
    is_active: bool,
    actor: User | None = None,
) -> UserRead:
    """Set ``is_active`` for a user (admin scope), persisting the change.

    Raises ``UserNotFoundError`` for unknown ids. Deactivating revokes every
    active refresh token so existing sessions end immediately; the account
    stays in the database (soft delete). An actor cannot deactivate their own
    account (``SelfDeactivationError``).
    """
    repository = UserRepository(db)
    user = await repository.get_by_id(user_id)
    if user is None:
        raise UserNotFoundError()

    if not is_active and actor is not None and user.id == actor.id:
        raise SelfDeactivationError()

    await repository.set_active_status(user_id, is_active)
    if not is_active:
        await RefreshTokenRepository(db).revoke_all_for_user(user_id)

    await db.refresh(user)
    await db.commit()
    return UserRead.model_validate(user)


async def deactivate_user(db, *, user_id: str, actor: User) -> UserRead:
    """Deactivate a user account (admin scope)."""
    return await _set_active_status(
        db, user_id=user_id, is_active=False, actor=actor
    )


async def activate_user(db, *, user_id: str) -> UserRead:
    """Reactivate a user account (admin scope)."""
    return await _set_active_status(db, user_id=user_id, is_active=True)
