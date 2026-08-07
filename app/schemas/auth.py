from __future__ import annotations

from pydantic import BaseModel, EmailStr, field_validator

from app.core.config import get_settings


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = 'bearer'


class RefreshRequest(BaseModel):
    refresh_token: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str

    @field_validator('new_password')
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        min_length = get_settings().PASSWORD_MIN_LENGTH
        if len(value) < min_length:
            raise ValueError(
                f'Password must be at least {min_length} characters long'
            )
        return value


class EmailVerificationConfirm(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr
