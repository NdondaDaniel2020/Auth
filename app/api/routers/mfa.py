from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.dependencies.auth import CurrentUserDep
from app.api.dependencies.database import SessionDep
from app.core.security import verify_password_async
from app.core.security_logger import log_security_event
from app.models.mfa_method import MfaMethod
from app.schemas.mfa import (
    MfaDisableRequest,
    MfaEnableRequest,
    MfaEnableResponse,
    MfaSetupResponse,
)
from app.services.mfa_service import MfaService

router = APIRouter(prefix='/mfa', tags=['mfa'])


@router.post(
    '/totp/setup',
    response_model=MfaSetupResponse,
    status_code=status.HTTP_200_OK,
)
async def setup_totp_mfa(
    user: CurrentUserDep,
    db: SessionDep,
) -> MfaSetupResponse:
    """Inicia a configuração do MFA gerando o segredo temporário TOTP e a URI otpauth."""
    secret = MfaService.generate_totp_secret()
    otpauth_uri = MfaService.get_totp_uri(user.email, secret)

    stmt = select(MfaMethod).where(
        MfaMethod.user_id == user.id, MfaMethod.type == 'totp'
    )
    result = await db.execute(stmt)
    mfa_method = result.scalar_one_or_none()

    if mfa_method:
        mfa_method.secret = secret
        mfa_method.is_active = False
    else:
        mfa_method = MfaMethod(
            user_id=user.id,
            type='totp',
            secret=secret,
            is_active=False,
        )
        db.add(mfa_method)

    await db.commit()

    return MfaSetupResponse(secret=secret, otpauth_uri=otpauth_uri)


@router.post(
    '/totp/enable',
    response_model=MfaEnableResponse,
    status_code=status.HTTP_200_OK,
)
async def enable_totp_mfa(
    user: CurrentUserDep,
    db: SessionDep,
    data: MfaEnableRequest,
) -> MfaEnableResponse:
    """Valida o código TOTP fornecido, ativa o MFA e retorna os códigos de backup."""
    stmt = select(MfaMethod).where(
        MfaMethod.user_id == user.id, MfaMethod.type == 'totp'
    )
    result = await db.execute(stmt)
    mfa_method = result.scalar_one_or_none()

    if not mfa_method or not mfa_method.secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Configuração de MFA não iniciada. Execute /setup primeiro.',
        )

    if not MfaService.verify_totp_code(mfa_method.secret, data.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Código TOTP inválido ou expirado.',
        )

    plain_backup_codes = MfaService.generate_backup_codes(count=8)
    hashed_backup_codes = MfaService.hash_backup_codes(plain_backup_codes)

    mfa_method.is_active = True
    mfa_method.data = {'backup_codes': hashed_backup_codes}

    user.mfa_enabled = True
    user.mfa_type = 'totp'

    log_security_event('MFA_ENABLED', user_id=user.id)
    await db.commit()

    return MfaEnableResponse(
        message='MFA ativado com sucesso',
        backup_codes=plain_backup_codes,
    )


@router.delete(
    '/totp/disable',
    status_code=status.HTTP_200_OK,
)
async def disable_totp_mfa(
    user: CurrentUserDep,
    db: SessionDep,
    data: MfaDisableRequest,
) -> dict[str, str]:
    """Desativa o MFA do usuário mediante confirmação da senha e código TOTP ou de backup."""
    if not user.hashed_password or not await verify_password_async(
        data.password, user.hashed_password
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Senha incorreta.',
        )

    stmt = select(MfaMethod).where(
        MfaMethod.user_id == user.id, MfaMethod.type == 'totp'
    )
    result = await db.execute(stmt)
    mfa_method = result.scalar_one_or_none()

    if not user.mfa_enabled or not mfa_method or not mfa_method.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='MFA não está ativado.',
        )

    totp_valid = (
        MfaService.verify_totp_code(mfa_method.secret, data.code)
        if mfa_method.secret
        else False
    )

    backup_valid = False
    if not totp_valid and mfa_method.data:
        hashed_codes = mfa_method.data.get('backup_codes', [])
        backup_valid, _ = MfaService.verify_and_consume_backup_code(
            data.code, hashed_codes
        )

    if not totp_valid and not backup_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Código de confirmação inválido.',
        )

    mfa_method.is_active = False
    mfa_method.secret = None
    mfa_method.data = None

    user.mfa_enabled = False
    user.mfa_type = None

    log_security_event('MFA_DISABLED', user_id=user.id)
    await db.commit()

    return {'message': 'MFA desativado com sucesso'}
