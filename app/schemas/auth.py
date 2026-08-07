from __future__ import annotations

from pydantic import BaseModel, EmailStr, field_validator

from app.schemas.validators import validate_password_strength


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
        return validate_password_strength(value)


class EmailVerificationConfirm(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr
