from __future__ import annotations

from app.core.exceptions import (
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    TooManyLoginAttemptsError,
)
from app.core.rate_limiter import (
    build_login_key,
    check_login_blocked,
    register_failed_login,
    reset_login_attempts,
)
from app.core.security import hash_password, verify_password
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate


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
