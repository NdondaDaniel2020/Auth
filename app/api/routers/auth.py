from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Request,
    Response,
    status,
)
from fastapi.security import OAuth2PasswordRequestForm

from app.api.dependencies.auth import CurrentUserDep, oauth2_scheme
from app.api.dependencies.database import SessionDep
from app.api.dependencies.rate_limit import rate_limit
from app.api.responses import (
    COMMON_FORBIDDEN_RESPONSES,
    COMMON_RATE_LIMIT_RESPONSES,
    COMMON_UNAUTHORIZED_RESPONSES,
)
from app.core import security
from app.core.device import extract_client_ip, parse_user_agent
from app.schemas.auth import (
    AuthResponse,
    EmailVerificationConfirm,
    LoginRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshRequest,
    ResendVerificationRequest,
    Token,
    UserRBACMetadata,
    WSTicketResponse,
)
from app.schemas.mfa import MfaChallengeRequest
from app.schemas.user import UserCreate, UserRead
from app.services import auth_service, user_service

router = APIRouter(prefix='/auth', tags=['auth'])


@router.post(
    '/register',
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit('RATE_LIMIT_REGISTER'))],
    responses={**COMMON_RATE_LIMIT_RESPONSES},
)
async def register(data: UserCreate, db: SessionDep) -> UserRead:
    user = await user_service.register_user(db, data)
    return UserRead.model_validate(user)


@router.post(
    '/login',
    response_model=AuthResponse,
    responses={**COMMON_UNAUTHORIZED_RESPONSES, **COMMON_RATE_LIMIT_RESPONSES},
)
async def login(
    data: LoginRequest, request: Request, db: SessionDep
) -> AuthResponse:
    client_ip = extract_client_ip(request)
    ua_header = request.headers.get('user-agent')
    device_name = parse_user_agent(ua_header)

    user = await user_service.authenticate_user(
        db,
        email=data.email,
        password=data.password,
        client_ip=client_ip,
    )
    if user.mfa_enabled:
        pending_token = security.create_mfa_pending_token(user.id)
        return AuthResponse(
            mfa_required=True,
            mfa_pending_token=pending_token,
        )

    tokens = await auth_service.create_token_pair(
        db,
        user,
        ip_address=client_ip,
        user_agent=ua_header,
        device_name=device_name,
    )
    user_metadata = user_service.get_user_rbac_metadata(user)
    return AuthResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
        user=user_metadata,
    )


@router.post(
    '/login-form',
    response_model=AuthResponse,
    responses={**COMMON_UNAUTHORIZED_RESPONSES, **COMMON_RATE_LIMIT_RESPONSES},
)
async def login_form(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    request: Request,
    db: SessionDep,
) -> AuthResponse:
    client_ip = extract_client_ip(request)
    ua_header = request.headers.get('user-agent')
    device_name = parse_user_agent(ua_header)

    user = await user_service.authenticate_user(
        db,
        email=form.username,
        password=form.password,
        client_ip=client_ip,
    )
    if user.mfa_enabled:
        pending_token = security.create_mfa_pending_token(user.id)
        return AuthResponse(
            mfa_required=True,
            mfa_pending_token=pending_token,
        )

    tokens = await auth_service.create_token_pair(
        db,
        user,
        ip_address=client_ip,
        user_agent=ua_header,
        device_name=device_name,
    )
    user_metadata = user_service.get_user_rbac_metadata(user)
    return AuthResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
        user=user_metadata,
    )


@router.post(
    '/login/mfa-challenge',
    response_model=AuthResponse,
    responses={**COMMON_UNAUTHORIZED_RESPONSES},
)
async def login_mfa_challenge(
    data: MfaChallengeRequest,
    request: Request,
    db: SessionDep,
) -> AuthResponse:
    """Valida o token intermediário mfa_pending e o código TOTP ou de backup, emitindo o par final de tokens JWT."""
    client_ip = extract_client_ip(request)
    ua_header = request.headers.get('user-agent')
    device_name = parse_user_agent(ua_header)

    tokens, user = await auth_service.authenticate_mfa_challenge(
        db,
        mfa_pending_token=data.mfa_pending_token,
        code=data.code,
        ip_address=client_ip,
        user_agent=ua_header,
        device_name=device_name,
    )
    user_metadata = user_service.get_user_rbac_metadata(user)
    return AuthResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
        user=user_metadata,
    )


@router.get(
    '/me',
    response_model=UserRBACMetadata,
    responses={**COMMON_UNAUTHORIZED_RESPONSES, **COMMON_FORBIDDEN_RESPONSES},
)
async def get_auth_me(current_user: CurrentUserDep) -> UserRBACMetadata:
    """Return authenticated user profile and RBAC metadata for frontend rehydration."""
    return user_service.get_user_rbac_metadata(current_user)


@router.post(
    '/refresh',
    response_model=Token,
    responses={**COMMON_UNAUTHORIZED_RESPONSES},
)
async def refresh(
    data: RefreshRequest, request: Request, db: SessionDep
) -> Token:
    client_ip = extract_client_ip(request)
    ua_header = request.headers.get('user-agent')
    device_name = parse_user_agent(ua_header)
    return await auth_service.refresh_tokens(
        db,
        data.refresh_token,
        ip_address=client_ip,
        user_agent=ua_header,
        device_name=device_name,
    )


@router.post(
    '/logout',
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**COMMON_UNAUTHORIZED_RESPONSES},
)
async def logout(
    data: RefreshRequest,
    request: Request,
    db: SessionDep,
    access_token: Annotated[str | None, Depends(oauth2_scheme)],
) -> Response:
    client_ip = request.client.host if request.client else None
    await auth_service.logout(
        db, data.refresh_token, client_ip=client_ip, access_token=access_token
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    '/password-reset/request',
    dependencies=[Depends(rate_limit('RATE_LIMIT_PASSWORD_RESET'))],
    responses={**COMMON_RATE_LIMIT_RESPONSES},
)
async def request_password_reset(
    data: PasswordResetRequest,
    request: Request,
    db: SessionDep,
) -> dict[str, str]:
    client_ip = request.client.host if request.client else None
    await auth_service.request_password_reset(
        db, data.email, client_ip=client_ip
    )
    return {
        'message': 'If the e-mail is registered, a password reset link has been sent.'
    }


@router.post(
    '/password-reset/confirm',
    responses={**COMMON_UNAUTHORIZED_RESPONSES},
)
async def confirm_password_reset(
    data: PasswordResetConfirm, request: Request, db: SessionDep
) -> dict[str, str]:
    client_ip = request.client.host if request.client else None
    await auth_service.reset_password(
        db, data.token, data.new_password, client_ip=client_ip
    )
    return {'message': 'Password has been reset successfully.'}


@router.post(
    '/verify-email',
    responses={**COMMON_UNAUTHORIZED_RESPONSES},
)
async def verify_email(
    data: EmailVerificationConfirm, request: Request, db: SessionDep
) -> dict[str, str]:
    client_ip = request.client.host if request.client else None
    await auth_service.verify_email(db, data.token, client_ip=client_ip)
    return {'message': 'E-mail verified successfully.'}


@router.post(
    '/verify-email/resend',
    dependencies=[Depends(rate_limit('RATE_LIMIT_EMAIL_RESEND'))],
    responses={**COMMON_RATE_LIMIT_RESPONSES},
)
async def resend_verification(
    data: ResendVerificationRequest,
    request: Request,
    db: SessionDep,
) -> dict[str, str]:
    client_ip = request.client.host if request.client else None
    await auth_service.resend_verification_email(
        db, data.email, client_ip=client_ip
    )
    return {
        'message': 'If the e-mail is registered and unverified, a new link has been sent.'
    }


@router.post(
    '/ws-ticket',
    response_model=WSTicketResponse,
    responses={**COMMON_UNAUTHORIZED_RESPONSES, **COMMON_FORBIDDEN_RESPONSES},
)
async def request_ws_ticket(
    current_user: CurrentUserDep,
) -> WSTicketResponse:
    """Issue a short-lived (15s) single-use ticket for WebSocket authentication."""
    ticket = await auth_service.create_ws_ticket(current_user.id)
    return WSTicketResponse(ticket=ticket, expires_in=15)
