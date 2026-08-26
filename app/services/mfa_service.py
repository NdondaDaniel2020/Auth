from __future__ import annotations

import secrets
import string
from typing import Any

import pyotp

from app.core.config import get_settings
from app.core.security import hash_password, verify_password


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
        return sorted(list(codes))

    @staticmethod
    def hash_backup_codes(codes: list[str]) -> list[str]:
        """Hash a list of plain-text backup codes for storage."""
        return [hash_password(code) for code in codes]

    @staticmethod
    def verify_and_consume_backup_code(
        plain_code: str,
        hashed_codes: list[str],
    ) -> tuple[bool, list[str]]:
        """Verify a backup code against a list of hashed codes.

        If valid, returns (True, updated_hashed_codes) with the consumed code removed.
        Otherwise returns (False, original_hashed_codes).
        """
        if not plain_code or not hashed_codes:
            return False, hashed_codes

        cleaned_input = plain_code.strip().upper()
        # Ensure code is formatted correctly if hyphen was omitted
        if len(cleaned_input) == 10 and '-' not in cleaned_input:
            cleaned_input = f'{cleaned_input[:5]}-{cleaned_input[5:]}'

        for idx, hashed_code in enumerate(hashed_codes):
            if verify_password(cleaned_input, hashed_code):
                remaining = (
                    hashed_codes[:idx] + hashed_codes[idx + 1 :]
                )
                return True, remaining

        return False, hashed_codes
