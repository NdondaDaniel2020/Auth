from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.dependencies.auth import oauth2_scheme
from app.api.dependencies.database import SessionDep

from app.api.dependencies.rate_limit import rate_limit
from app.schemas.auth import (
    EmailVerificationConfirm,
    LoginRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshRequest,
    ResendVerificationRequest,
    Token,
)
from app.schemas.user import UserCreate, UserRead
from app.services import auth_service, user_service

router = APIRouter(prefix='/auth', tags=['auth'])


@router.post(
    '/register',
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit('RATE_LIMIT_REGISTER'))],
)
async def register(data: UserCreate, db: SessionDep) -> UserRead:
    user = await user_service.register_user(db, data)
    await auth_service.send_verification_email_for_user(db, user)
    return UserRead.model_validate(user)


@router.post('/login', response_model=Token)
async def login(data: LoginRequest, request: Request, db: SessionDep) -> Token:
    client_ip = request.client.host if request.client else None
    user = await user_service.authenticate_user(
        db,
        email=data.email,
        password=data.password,
        client_ip=client_ip,
    )
    return await auth_service.create_token_pair(db, user)


@router.post('/login-form', response_model=Token)
async def login_form(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    request: Request,
    db: SessionDep,
) -> Token:
    client_ip = request.client.host if request.client else None
    user = await user_service.authenticate_user(
        db,
        email=form.username,
        password=form.password,
        client_ip=client_ip,
    )
    return await auth_service.create_token_pair(db, user)


@router.post('/refresh', response_model=Token)
async def refresh(data: RefreshRequest, db: SessionDep) -> Token:
    return await auth_service.refresh_tokens(db, data.refresh_token)



@router.post('/logout', status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    data: RefreshRequest,
    request: Request,
    db: SessionDep,
    access_token: str | None = Depends(oauth2_scheme),
) -> Response:
    client_ip = request.client.host if request.client else None
    await auth_service.logout(
        db, data.refresh_token, client_ip=client_ip, access_token=access_token
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)



@router.post(
    '/password-reset/request',
    dependencies=[Depends(rate_limit('RATE_LIMIT_PASSWORD_RESET'))],
)
async def request_password_reset(
    data: PasswordResetRequest, request: Request, db: SessionDep
) -> dict[str, str]:
    client_ip = request.client.host if request.client else None
    await auth_service.request_password_reset(
        db, data.email, client_ip=client_ip
    )
    return {
        'message': 'If the e-mail is registered, a password reset link has been sent.'
    }


@router.post('/password-reset/confirm')
async def confirm_password_reset(
    data: PasswordResetConfirm, request: Request, db: SessionDep
) -> dict[str, str]:
    client_ip = request.client.host if request.client else None
    await auth_service.reset_password(
        db, data.token, data.new_password, client_ip=client_ip
    )
    return {'message': 'Password has been reset successfully.'}


@router.post('/verify-email')
async def verify_email(
    data: EmailVerificationConfirm, request: Request, db: SessionDep
) -> dict[str, str]:
    client_ip = request.client.host if request.client else None
    await auth_service.verify_email(db, data.token, client_ip=client_ip)
    return {'message': 'E-mail verified successfully.'}


@router.post(
    '/verify-email/resend',
    dependencies=[Depends(rate_limit('RATE_LIMIT_EMAIL_RESEND'))],
)
async def resend_verification(
    data: ResendVerificationRequest, db: SessionDep
) -> dict[str, str]:
    await auth_service.resend_verification_email(db, data.email)
    return {
        'message': 'If the e-mail is registered and unverified, a new link has been sent.'
    }
