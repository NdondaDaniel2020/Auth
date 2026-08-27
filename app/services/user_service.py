from __future__ import annotations

import logging
from datetime import timedelta

from app.core.config import get_settings
from app.core.events.events import (
    Event,
    UserEvents,
    get_event_bus,
)
from app.core.exceptions import (
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    RoleNotFoundError,
    SelfDeactivationError,
    SelfRoleRemovalError,
    TooManyLoginAttemptsError,
    UserNotFoundError,
)
from app.core.security.rate_limiter import (
    build_email_login_key,
    build_ip_login_key,
    check_login_blocked_async,
    register_failed_login_async,
    reset_login_attempts_async,
)
from app.core.security.security import (
    hash_password_async,
    verify_password_async,
)
from app.core.security.security_logger import log_security_event
from app.models.user import User
from app.repositories.email_verification_repository import (
    EmailVerificationTokenRepository,
)
from app.repositories.mfa_repository import MfaRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import UserRBACMetadata
from app.schemas.pagination import PaginatedResponse
from app.schemas.user import UserCreate, UserRead, UserUpdate
from app.services import auth_service
from app.services.audit_service import record_admin_action
from app.services.email_service import send_account_locked_email
from app.utils.datetimes import utcnow
from app.utils.tokens import generate_opaque_token


def get_user_rbac_metadata(user: User) -> UserRBACMetadata:
    """Extract RBAC roles and permissions metadata for a user."""
    roles = sorted({role.name for role in (user.roles or [])})
    permissions = sorted({
        permission.code
        for role in (user.roles or [])
        for permission in (role.permissions or [])
    })

    if user.is_superuser and '*' not in permissions:
        permissions.append('*')
        permissions.sort()

    return UserRBACMetadata(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        is_superuser=user.is_superuser,
        roles=roles,
        permissions=permissions,
    )


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
        hashed_password=await hash_password_async(data.password),
        full_name=data.full_name,
    )

    verify_link: str | None = None
    if not user.is_verified:
        settings = get_settings()
        token = generate_opaque_token()
        expires_at = utcnow() + timedelta(
            minutes=settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES
        )
        verification_repo = EmailVerificationTokenRepository(db)
        await verification_repo.create(
            user_id=user.id, token=token, expires_at=expires_at
        )
        verify_link = (
            f'{settings.APP_BASE_URL}/auth/verify-email?token={token}'
        )

    await db.commit()

    # Publish user.created event
    bus = get_event_bus()
    await bus.publish(
        Event(
            type=UserEvents.CREATED,
            payload={
                'user_id': user.id,
                'email': user.email,
                'full_name': user.full_name,
                'is_verified': user.is_verified,
                'verify_link': verify_link,
            },
        )
    )

    return user


async def authenticate_user(
    db,
    email: str,
    password: str,
    *,
    client_ip: str | None = None,
) -> User:
    """Authenticate a user with e-mail/password.

    Failed attempts are counted per identifier (e-mail and IP separately). When the
    limit is reached for either identifier, access is temporarily blocked and a 429
    is returned, without revealing whether the credentials themselves were wrong.
    """
    email_key = build_email_login_key(email)
    ip_key = build_ip_login_key(client_ip) if client_ip else None

    email_blocked = await check_login_blocked_async(email_key)
    ip_blocked = await check_login_blocked_async(ip_key) if ip_key else None

    if email_blocked is not None or ip_blocked is not None:
        blocked_seconds = max(email_blocked or 0, ip_blocked or 0)
        log_security_event(
            'LOGIN_RATE_LIMITED',
            ip=client_ip,
            metadata={
                'email': email,
                'email_blocked': email_blocked is not None,
                'ip_blocked': ip_blocked is not None,
            },
            level=logging.WARNING,
        )
        raise TooManyLoginAttemptsError(retry_after=blocked_seconds)

    repository = UserRepository(db)
    user = await repository.get_by_email(email)

    password_valid = (
        await verify_password_async(password, user.hashed_password)
        if user is not None and user.hashed_password is not None
        else False
    )

    if user is None or not user.is_active or not password_valid:
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
        if ip_key:
            await register_failed_login_async(ip_key)
        email_just_locked = await register_failed_login_async(email_key)
        if email_just_locked:
            log_security_event(
                'ACCOUNT_TEMPORARILY_LOCKED',
                user_id=user.id if user is not None else None,
                ip=client_ip,
                metadata={'email': email},
                level=logging.WARNING,
            )
            settings = get_settings()
            await send_account_locked_email(
                email, settings.LOGIN_BLOCK_DURATION_MINUTES
            )
        raise InvalidCredentialsError()

    # MFA_HOOK: verificação de segundo fator entraria aqui, após a senha ter
    # sido validada e antes de emitir o access token final. Quando MFA for
    # ativado (ver docs/mfa-readiness.md), este ponto emitiria um token
    # intermediário de curta duração e retornaria um desafio pendente em vez
    # de seguir direto para a emissão do token.
    await reset_login_attempts_async(email_key)
    if ip_key:
        await reset_login_attempts_async(ip_key)
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
        old_values = {k: getattr(user, k) for k in updates}
        user = await UserRepository(db).update(user, updates)
        await db.commit()
        await db.refresh(user)
        new_values = {k: getattr(user, k) for k in updates}

        # Publish user.updated event
        bus = get_event_bus()
        await bus.publish(
            Event(
                type=UserEvents.UPDATED,
                payload={
                    'user_id': user.id,
                    'email': user.email,
                    'changed_fields': list(updates.keys()),
                    'old_values': old_values,
                    'new_values': new_values,
                    'actor_id': user.id,
                },
            )
        )

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
        actor_user_id=actor.id if actor is not None else None,
        action=action,
        resource_type='user',
        resource_id=user_id,
    )
    await db.refresh(user)
    await db.commit()

    # Publish user.activated / user.deactivated event
    bus = get_event_bus()
    await bus.publish(
        Event(
            type=UserEvents.ACTIVATED if is_active else UserEvents.DEACTIVATED,
            payload={
                'user_id': user.id,
                'email': user.email,
                'actor_id': actor.id if actor is not None else None,
            },
        )
    )

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

    # Publish user.roles_changed event
    bus = get_event_bus()
    await bus.publish(
        Event(
            type=UserEvents.ROLES_CHANGED,
            payload={
                'user_id': user.id,
                'email': user.email,
                'old_roles': list(previous_role_names),
                'new_roles': list(new_role_names),
                'actor_id': actor.id,
            },
        )
    )

    return UserRead.model_validate(user)


async def admin_disable_user_mfa(
    db,
    *,
    user_id: str,
    actor: User,
) -> UserRead:
    """Disable MFA for a user (admin scope).

    Deactivates any active MfaMethod, resets user.mfa_enabled to False,
    and logs the action in audit_logs.
    """
    repository = UserRepository(db)
    user = await repository.get_by_id(user_id)
    if user is None:
        raise UserNotFoundError()

    mfa_repo = MfaRepository(db)
    mfa_method = await mfa_repo.get_by_user_and_type(user.id, type='totp')
    if mfa_method:
        await mfa_repo.deactivate_method(mfa_method)

    user.mfa_enabled = False
    user.mfa_type = None

    await record_admin_action(
        db,
        actor_user_id=actor.id,
        action='ADMIN_DISABLE_MFA',
        resource_type='user',
        resource_id=user_id,
        details={'target_email': user.email},
    )
    log_security_event(
        'ADMIN_MFA_DISABLED', user_id=user.id, metadata={'actor_id': actor.id}
    )
    await db.commit()
    await db.refresh(user)

    return UserRead.model_validate(user)
