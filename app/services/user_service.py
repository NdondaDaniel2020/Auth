from __future__ import annotations

import logging

from app.core.exceptions import (
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    RoleNotFoundError,
    SelfDeactivationError,
    SelfRoleRemovalError,
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
from app.core.security_logger import log_security_event
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.pagination import PaginatedResponse
from app.schemas.user import UserCreate, UserRead, UserUpdate
from app.services import auth_service
from app.services.audit_service import record_admin_action


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
        log_security_event(
            'LOGIN_RATE_LIMITED',
            ip=client_ip,
            metadata={'email': email},
            level=logging.WARNING,
        )
        raise TooManyLoginAttemptsError(retry_after=blocked_seconds)

    repository = UserRepository(db)
    user = await repository.get_by_email(email)

    if user is None or not user.is_active or not verify_password(
        password, user.hashed_password
    ):
        reason = (
            'account_inactive'
            if user is not None and not user.is_active
            else 'invalid_credentials'
        )
        log_security_event(
            'LOGIN_FAILED',
            user_id=user.id if user is not None else None,
            ip=client_ip,
            metadata={'email': email, 'reason': reason},
            level=logging.WARNING,
        )
        register_failed_login(login_key)
        raise InvalidCredentialsError()

    # MFA_HOOK: verificação de segundo fator entraria aqui, após a senha ter
    # sido validada e antes de emitir o access token final. Quando MFA for
    # ativado (ver docs/mfa-readiness.md), este ponto emitiria um token
    # intermediário de curta duração e retornaria um desafio pendente em vez
    # de seguir direto para a emissão do token.
    reset_login_attempts(login_key)
    log_security_event('LOGIN_SUCCESS', user_id=user.id, ip=client_ip)
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

    action = 'USER_DEACTIVATED' if not is_active else 'USER_ACTIVATED'

    if not is_active and actor is not None and user.id == actor.id:
        await record_admin_action(
            db,
            actor_user_id=actor.id,
            action=action,
            resource_type='user',
            resource_id=user_id,
            result='denied',
            details={'reason': 'self deactivation'},
        )
        await db.commit()
        raise SelfDeactivationError()

    await repository.set_active_status(user_id, is_active)
    if not is_active:
        await auth_service.revoke_all_user_sessions(db, user_id)

    await record_admin_action(
        db,
        actor_user_id=actor.id,
        action=action,
        resource_type='user',
        resource_id=user_id,
    )
    await db.refresh(user)
    await db.commit()
    return UserRead.model_validate(user)


async def deactivate_user(db, *, user_id: str, actor: User) -> UserRead:
    """Deactivate a user account (admin scope)."""
    return await _set_active_status(
        db, user_id=user_id, is_active=False, actor=actor
    )


async def activate_user(db, *, user_id: str, actor: User) -> UserRead:
    """Reactivate a user account (admin scope)."""
    return await _set_active_status(
        db, user_id=user_id, is_active=True, actor=actor
    )


async def update_user_roles(
    db,
    *,
    user_id: str,
    role_ids: list[str],
    actor: User,
) -> UserRead:
    """Replace the user's roles with ``role_ids`` (admin scope).

    Validates that the user and every role exist (404 otherwise). An actor
    cannot remove the ``admin`` role from their own account
    (``SelfRoleRemovalError``). Because ``get_current_user`` always reloads
    the user's roles from the database, the change takes effect on the very
    next authenticated request. If the target user loses a critical role
    (``admin``), all their sessions are revoked (see ``docs/token-policy.md``).
    """
    repository = UserRepository(db)
    user = await repository.get_by_id(user_id)
    if user is None:
        raise UserNotFoundError()

    unique_ids = list(dict.fromkeys(role_ids))
    roles = await repository.get_roles_by_ids(unique_ids)
    if len(roles) != len(unique_ids):
        raise RoleNotFoundError()

    previous_role_names = {role.name for role in user.roles}
    new_role_names = {role.name for role in roles}
    if (
        actor.id == user.id
        and 'admin' in previous_role_names
        and 'admin' not in new_role_names
    ):
        await record_admin_action(
            db,
            actor_user_id=actor.id,
            action='USER_ROLES_UPDATED',
            resource_type='user',
            resource_id=user_id,
            result='denied',
            details={'reason': 'self admin role removal'},
        )
        await db.commit()
        raise SelfRoleRemovalError()

    await repository.set_roles(user, roles)
    await record_admin_action(
        db,
        actor_user_id=actor.id,
        action='USER_ROLES_UPDATED',
        resource_type='user',
        resource_id=user_id,
        details={'role_ids': unique_ids},
    )
    if 'admin' in previous_role_names and 'admin' not in new_role_names:
        await auth_service.revoke_all_user_sessions(db, user_id)
    await db.commit()
    return UserRead.model_validate(user)
