from __future__ import annotations

from pydantic import BaseModel, Field


class MfaSetupResponse(BaseModel):
    secret: str = Field(
        ...,
        description='Segredo Base32 do TOTP para inclusão manual no aplicativo',
    )
    otpauth_uri: str = Field(
        ...,
        description='URI no padrão otpauth:// para geração de QR Code no frontend',
    )


class MfaEnableRequest(BaseModel):
    code: str = Field(
        ...,
        min_length=6,
        max_length=6,
        pattern=r'^\d{6}$',
        description='Código TOTP de 6 dígitos gerado pelo aplicativo autenticador',
    )


class MfaEnableResponse(BaseModel):
    message: str = Field(
        'MFA ativado com sucesso',
        description='Mensagem de confirmação de ativação do MFA',
    )
    backup_codes: list[str] = Field(
        ...,
        description='Códigos de recuperação de uso único (salve em local seguro)',
    )


class MfaDisableRequest(BaseModel):
    password: str = Field(
        ...,
        description='Senha atual do usuário para confirmação de segurança',
    )
    code: str = Field(
        ...,
        description='Código TOTP de 6 dígitos ou código de backup',
    )


class MfaChallengeRequest(BaseModel):
    mfa_pending_token: str = Field(
        ...,
        description='Token intermediário de curta duração recebido no login',
    )
    code: str = Field(
        ...,
        description='Código TOTP de 6 dígitos ou código de backup de recuperação',
    )
