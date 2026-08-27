from __future__ import annotations

from fastapi import APIRouter, status

from app.api.dependencies.auth import CurrentUserDep
from app.api.dependencies.database import SessionDep
from app.api.responses import (
    COMMON_FORBIDDEN_RESPONSES,
    COMMON_UNAUTHORIZED_RESPONSES,
)
from app.schemas.mfa import (
    MfaDisableRequest,
    MfaEnableRequest,
    MfaEnableResponse,
    MfaRegenerateRequest,
    MfaSetupResponse,
)
from app.services.mfa_service import MfaService

router = APIRouter(prefix='/mfa', tags=['mfa'])


@router.post(
    '/totp/setup',
    response_model=MfaSetupResponse,
    status_code=status.HTTP_200_OK,
    responses={**COMMON_UNAUTHORIZED_RESPONSES, **COMMON_FORBIDDEN_RESPONSES},
)
async def setup_totp_mfa(
    user: CurrentUserDep,
    db: SessionDep,
) -> MfaSetupResponse:
    """Inicia a configuração do MFA gerando o segredo temporário TOTP e a URI otpauth."""
    return await MfaService.setup_totp(db, user)


@router.post(
    '/totp/enable',
    response_model=MfaEnableResponse,
    status_code=status.HTTP_200_OK,
    responses={**COMMON_UNAUTHORIZED_RESPONSES, **COMMON_FORBIDDEN_RESPONSES},
)
async def enable_totp_mfa(
    user: CurrentUserDep,
    db: SessionDep,
    data: MfaEnableRequest,
) -> MfaEnableResponse:
    """Valida o código TOTP fornecido, ativa o MFA e retorna os códigos de backup."""
    return await MfaService.enable_totp(db, user, data.code)


@router.post(
    '/totp/backup-codes/regenerate',
    response_model=MfaEnableResponse,
    status_code=status.HTTP_200_OK,
    responses={**COMMON_UNAUTHORIZED_RESPONSES, **COMMON_FORBIDDEN_RESPONSES},
)
async def regenerate_backup_codes(
    user: CurrentUserDep,
    db: SessionDep,
    data: MfaRegenerateRequest,
) -> MfaEnableResponse:
    """Invalida os códigos de backup antigos e gera um novo lote mediante confirmação de senha."""
    return await MfaService.regenerate_backup_codes(db, user, data.password)


@router.delete(
    '/totp/disable',
    status_code=status.HTTP_200_OK,
    responses={**COMMON_UNAUTHORIZED_RESPONSES, **COMMON_FORBIDDEN_RESPONSES},
)
async def disable_totp_mfa(
    user: CurrentUserDep,
    db: SessionDep,
    data: MfaDisableRequest,
) -> dict[str, str]:
    """Desativa o MFA do usuário mediante confirmação da senha e código TOTP ou de backup."""
    await MfaService.disable_totp(db, user, data.password, data.code)
    return {'message': 'MFA desativado com sucesso'}
