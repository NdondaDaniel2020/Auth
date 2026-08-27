from __future__ import annotations

import secrets
import string
from datetime import UTC, datetime
from typing import Any

import pyotp
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import (
    InvalidCredentialsError,
    InvalidMfaConfirmationError,
    InvalidTotpCodeError,
    MfaNotActiveError,
    MfaNotSetupError,
)
from app.core.security.security import (
    hash_password,
    verify_password,
    verify_password_async,
)
from app.core.security.security_logger import log_security_event
from app.models.user import User
from app.repositories.mfa_repository import MfaRepository
from app.schemas.mfa import MfaEnableResponse, MfaSetupResponse


class MfaService:
    """Service providing TOTP generation, validation, and backup code handling."""

    @staticmethod
    def generate_totp_secret() -> str:
        """Generate a random Base32 TOTP secret key."""
        return pyotp.random_base32()

    @staticmethod
    def get_totp_uri(
        user_email: str,
        secret: str,
        issuer_name: str | None = None,
    ) -> str:
        """Build the otpauth:// URI for QR code generation in authenticator apps."""
        if issuer_name is None:
            settings = get_settings()
            issuer_name = getattr(settings, 'PROJECT_NAME', 'AuthApp')
        totp = pyotp.TOTP(secret)
        return totp.provisioning_uri(name=user_email, issuer_name=issuer_name)

    @staticmethod
    def verify_totp_code(
        secret: str,
        code: str,
        valid_window: int = 1,
    ) -> bool:
        """Validate a 6-digit TOTP code against a secret key with clock drift tolerance."""
        if not secret or not code:
            return False
        # Remove any spaces or hyphens from input code
        cleaned_code = code.replace(' ', '').replace('-', '').strip()
        if not cleaned_code.isdigit() or len(cleaned_code) != 6:
            return False

        totp = pyotp.TOTP(secret)
        return totp.verify(cleaned_code, valid_window=valid_window)

    @staticmethod
    def generate_backup_codes(count: int = 8) -> list[str]:
        """Generate a list of unique 10-character alphanumeric backup codes."""
        alphabet = string.ascii_uppercase + string.digits
        # Avoid visually ambiguous characters like O, 0, I, 1
        safe_alphabet = ''.join(c for c in alphabet if c not in 'O0I1')
        codes: set[str] = set()
        while len(codes) < count:
            raw = ''.join(secrets.choice(safe_alphabet) for _ in range(10))
            formatted = f'{raw[:5]}-{raw[5:]}'
            codes.add(formatted)
        return sorted(codes)

    @staticmethod
    def hash_backup_codes(codes: list[str]) -> list[dict[str, Any]]:
        """Hash a list of plain-text backup codes with metadata for storage."""
        now_iso = datetime.now(UTC).isoformat()
        return [
            {
                'code_hash': hash_password(code),
                'used_at': None,
                'created_at': now_iso,
            }
            for code in codes
        ]

    @staticmethod
    def verify_and_consume_backup_code(
        plain_code: str,
        hashed_codes: list[Any],
    ) -> tuple[bool, list[dict[str, Any]], int]:
        """Verify a backup code against a list of structured or legacy hashed codes.

        If valid, marks the code with used_at=timestamp (Burn on Use) and returns
        (True, updated_hashed_codes, remaining_active_count).
        """
        if not plain_code or not hashed_codes:
            return False, [], 0

        cleaned_input = plain_code.strip().upper()
        if len(cleaned_input) == 10 and '-' not in cleaned_input:
            cleaned_input = f'{cleaned_input[:5]}-{cleaned_input[5:]}'

        updated_list: list[dict[str, Any]] = []
        code_matched = False
        now_iso = datetime.now(UTC).isoformat()

        for item in hashed_codes:
            if isinstance(item, dict):
                code_hash = item.get('code_hash', '')
                used_at = item.get('used_at')
                created_at = item.get('created_at', now_iso)
                if (
                    not code_matched
                    and used_at is None
                    and verify_password(cleaned_input, code_hash)
                ):
                    code_matched = True
                    updated_list.append({
                        'code_hash': code_hash,
                        'used_at': now_iso,
                        'created_at': created_at,
                    })
                else:
                    updated_list.append({
                        'code_hash': code_hash,
                        'used_at': used_at,
                        'created_at': created_at,
                    })
            elif isinstance(item, str):
                # Legacy format support
                if not code_matched and verify_password(cleaned_input, item):
                    code_matched = True
                    updated_list.append({
                        'code_hash': item,
                        'used_at': now_iso,
                        'created_at': now_iso,
                    })
                else:
                    updated_list.append({
                        'code_hash': item,
                        'used_at': None,
                        'created_at': now_iso,
                    })

        remaining_active = sum(
            1 for item in updated_list if item.get('used_at') is None
        )
        return code_matched, updated_list, remaining_active

    @classmethod
    async def setup_totp(
        cls,
        db: AsyncSession,
        user: User,
    ) -> MfaSetupResponse:
        """Inicia a configuração do MFA gerando o segredo temporário TOTP e a URI otpauth."""
        secret = cls.generate_totp_secret()
        otpauth_uri = cls.get_totp_uri(user.email, secret)

        mfa_repo = MfaRepository(db)
        await mfa_repo.upsert_pending_secret(user.id, secret, type='totp')
        await db.commit()

        return MfaSetupResponse(secret=secret, otpauth_uri=otpauth_uri)

    @classmethod
    async def enable_totp(
        cls,
        db: AsyncSession,
        user: User,
        code: str,
    ) -> MfaEnableResponse:
        """Valida o primeiro código TOTP, ativa o MFA no usuário e retorna os códigos de backup."""
        mfa_repo = MfaRepository(db)
        mfa_method = await mfa_repo.get_by_user_and_type(user.id, type='totp')

        if not mfa_method or not mfa_method.secret:
            raise MfaNotSetupError()

        if not cls.verify_totp_code(mfa_method.secret, code):
            raise InvalidTotpCodeError()

        plain_backup_codes = cls.generate_backup_codes(count=8)
        hashed_backup_codes = cls.hash_backup_codes(plain_backup_codes)

        await mfa_repo.activate_method(
            mfa_method, data={'backup_codes': hashed_backup_codes}
        )

        user.mfa_enabled = True
        user.mfa_type = 'totp'

        log_security_event('MFA_ENABLED', user_id=user.id)
        await db.commit()

        return MfaEnableResponse(
            message='MFA ativado com sucesso',
            backup_codes=plain_backup_codes,
        )

    @classmethod
    async def regenerate_backup_codes(
        cls,
        db: AsyncSession,
        user: User,
        password: str,
    ) -> MfaEnableResponse:
        """Invalida os códigos de backup antigos e gera um novo lote após confirmação de senha."""
        if not user.hashed_password or not await verify_password_async(
            password, user.hashed_password
        ):
            raise InvalidCredentialsError(message='Senha incorreta.')

        mfa_repo = MfaRepository(db)
        mfa_method = await mfa_repo.get_by_user_and_type(user.id, type='totp')

        if not user.mfa_enabled or not mfa_method or not mfa_method.is_active:
            raise MfaNotActiveError()

        plain_backup_codes = cls.generate_backup_codes(count=8)
        hashed_backup_codes = cls.hash_backup_codes(plain_backup_codes)

        await mfa_repo.activate_method(
            mfa_method, data={'backup_codes': hashed_backup_codes}
        )

        log_security_event('MFA_BACKUP_CODES_REGENERATED', user_id=user.id)
        await db.commit()

        return MfaEnableResponse(
            message='Novos códigos de backup gerados com sucesso',
            backup_codes=plain_backup_codes,
        )

    @classmethod
    async def disable_totp(
        cls,
        db: AsyncSession,
        user: User,
        password: str,
        code: str,
    ) -> None:
        """Desativa o MFA do usuário mediante confirmação da senha atual e código TOTP ou de backup."""
        if not user.hashed_password or not await verify_password_async(
            password, user.hashed_password
        ):
            raise InvalidCredentialsError(message='Senha incorreta.')

        mfa_repo = MfaRepository(db)
        mfa_method = await mfa_repo.get_by_user_and_type(user.id, type='totp')

        if not user.mfa_enabled or not mfa_method or not mfa_method.is_active:
            raise MfaNotActiveError()

        totp_valid = (
            cls.verify_totp_code(mfa_method.secret, code)
            if mfa_method.secret
            else False
        )

        backup_valid = False
        if not totp_valid and mfa_method.data:
            hashed_codes = mfa_method.data.get('backup_codes', [])
            backup_valid, updated_codes, _ = (
                cls.verify_and_consume_backup_code(code, hashed_codes)
            )
            if backup_valid:
                mfa_method.data = {'backup_codes': updated_codes}

        if not totp_valid and not backup_valid:
            raise InvalidMfaConfirmationError()

        await mfa_repo.deactivate_method(mfa_method)

        user.mfa_enabled = False
        user.mfa_type = None

        log_security_event('MFA_DISABLED', user_id=user.id)
        await db.commit()
