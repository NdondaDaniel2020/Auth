from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.dependencies.auth import CurrentUserDep
from app.api.dependencies.database import SessionDep
from app.api.dependencies.pagination import PaginationParamsDep
from app.api.dependencies.permissions import AdminUserDep
from app.api.responses import (
    COMMON_FORBIDDEN_RESPONSES,
    COMMON_NOT_FOUND_RESPONSES,
    COMMON_UNAUTHORIZED_RESPONSES,
)
from app.schemas.pagination import PaginatedResponse
from app.schemas.session import SessionListResponse, SessionRevokeResponse
from app.schemas.user import UserPublic, UserRead, UserRoleUpdate, UserUpdate
from app.services import auth_service, session_service
from app.services.user_service import (
    activate_user,
    admin_disable_user_mfa,
    deactivate_user,
    get_user,
    list_users,
    update_profile,
    update_user_roles,
)

router = APIRouter(prefix='/users', tags=['users'])


@router.get(
    '/me',
    response_model=UserPublic,
    responses={**COMMON_UNAUTHORIZED_RESPONSES, **COMMON_FORBIDDEN_RESPONSES},
)
async def read_current_user(user: CurrentUserDep) -> UserPublic:
    """Return the profile of the currently authenticated user.

    The user is resolved entirely from the access token; no parameters are
    accepted. Only public fields are exposed (never ``hashed_password``).
    """
    return UserPublic.model_validate(user)


@router.patch(
    '/me',
    response_model=UserRead,
    responses={**COMMON_UNAUTHORIZED_RESPONSES, **COMMON_FORBIDDEN_RESPONSES},
)
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


@router.get(
    '',
    response_model=PaginatedResponse[UserRead],
    responses={**COMMON_UNAUTHORIZED_RESPONSES, **COMMON_FORBIDDEN_RESPONSES},
)
async def list_all_users(
    db: SessionDep,
    admin_user: AdminUserDep,
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


@router.get(
    '/{user_id}',
    response_model=UserRead,
    responses={
        **COMMON_UNAUTHORIZED_RESPONSES,
        **COMMON_FORBIDDEN_RESPONSES,
        **COMMON_NOT_FOUND_RESPONSES,
    },
)
async def get_user_by_id(
    db: SessionDep,
    admin_user: AdminUserDep,
    user_id: uuid.UUID,
) -> UserRead:
    """Return a single user by ``id`` (admin only).

    The ``id`` is validated as a UUID (malformed values yield HTTP 422);
    unknown users yield HTTP 404 via ``UserNotFoundError``.
    """
    return await get_user(db, user_id=str(user_id))


@router.patch(
    '/{user_id}/deactivate',
    response_model=UserRead,
    responses={
        **COMMON_UNAUTHORIZED_RESPONSES,
        **COMMON_FORBIDDEN_RESPONSES,
        **COMMON_NOT_FOUND_RESPONSES,
    },
)
async def deactivate_user_account(
    db: SessionDep,
    admin_user: AdminUserDep,
    user_id: uuid.UUID,
) -> UserRead:
    """Deactivate a user account (admin only).

    Soft delete via ``is_active``: the record is preserved, the user can no
    longer log in and active refresh tokens are revoked. Admins cannot
    deactivate their own account.
    """
    return await deactivate_user(db, user_id=str(user_id), actor=admin_user)


@router.patch(
    '/{user_id}/activate',
    response_model=UserRead,
    responses={
        **COMMON_UNAUTHORIZED_RESPONSES,
        **COMMON_FORBIDDEN_RESPONSES,
        **COMMON_NOT_FOUND_RESPONSES,
    },
)
async def activate_user_account(
    db: SessionDep,
    admin_user: AdminUserDep,
    user_id: uuid.UUID,
) -> UserRead:
    """Reactivate a previously deactivated user account (admin only)."""
    return await activate_user(db, user_id=str(user_id), actor=admin_user)


@router.put(
    '/{user_id}/roles',
    response_model=UserRead,
    responses={
        **COMMON_UNAUTHORIZED_RESPONSES,
        **COMMON_FORBIDDEN_RESPONSES,
        **COMMON_NOT_FOUND_RESPONSES,
    },
)
async def replace_user_roles(
    db: SessionDep,
    admin_user: AdminUserDep,
    user_id: uuid.UUID,
    data: UserRoleUpdate,
) -> UserRead:
    """Replace the user's roles (admin only).

    Replace-all semantics: the final role set is exactly ``role_ids``. Unknown
    roles or users yield HTTP 404; removing one's own ``admin`` role is
    blocked (HTTP 400).
    """
    return await update_user_roles(
        db,
        user_id=str(user_id),
        role_ids=data.role_ids,
        actor=admin_user,
    )


@router.get(
    '/me/sessions',
    response_model=SessionListResponse,
    responses={**COMMON_UNAUTHORIZED_RESPONSES, **COMMON_FORBIDDEN_RESPONSES},
)
async def read_current_user_sessions(
    user: CurrentUserDep,
    db: SessionDep,
) -> SessionListResponse:
    """Lista todas as sessões ativas (dispositivos conectados) do usuário autenticado."""
    return await session_service.list_user_sessions(db, user_id=user.id)


@router.delete(
    '/me/sessions/{jti}',
    response_model=SessionRevokeResponse,
    responses={
        **COMMON_UNAUTHORIZED_RESPONSES,
        **COMMON_FORBIDDEN_RESPONSES,
        **COMMON_NOT_FOUND_RESPONSES,
    },
)
async def revoke_current_user_session(
    jti: str,
    user: CurrentUserDep,
    db: SessionDep,
) -> SessionRevokeResponse:
    """Encerra remotamente uma sessão ativa específica do usuário autenticado."""
    return await session_service.revoke_user_session(
        db, user_id=user.id, target_jti=jti
    )


@router.delete(
    '/me/sessions',
    response_model=SessionRevokeResponse,
    responses={**COMMON_UNAUTHORIZED_RESPONSES, **COMMON_FORBIDDEN_RESPONSES},
)
async def revoke_other_user_sessions(
    user: CurrentUserDep,
    db: SessionDep,
    current_jti: str | None = None,
) -> SessionRevokeResponse:
    """Encerra todas as outras sessões ativas do usuário, preservando a atual se fornecida."""
    if current_jti:
        return await session_service.revoke_all_other_sessions(
            db, user_id=user.id, current_jti=current_jti
        )
    # Se não especificou current_jti, revoga todas
    await auth_service.revoke_all_user_sessions(db, user_id=user.id)
    await db.commit()
    return SessionRevokeResponse(
        message='Todas as sessões foram revogadas com sucesso.',
        revoked_count=1,
    )


@router.delete(
    '/{user_id}/mfa',
    response_model=UserRead,
    responses={
        **COMMON_UNAUTHORIZED_RESPONSES,
        **COMMON_FORBIDDEN_RESPONSES,
        **COMMON_NOT_FOUND_RESPONSES,
    },
)
async def admin_disable_mfa(
    db: SessionDep,
    admin_user: AdminUserDep,
    user_id: uuid.UUID,
) -> UserRead:
    """Desativa administrativamente o MFA de um usuário (apenas superusuários/admins).

    Utilizado em suporte para perda total de acesso. Registra obrigatoriamente
    a ação na tabela audit_logs.
    """
    return await admin_disable_user_mfa(
        db, user_id=str(user_id), actor=admin_user
    )
