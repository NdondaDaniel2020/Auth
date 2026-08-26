from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.validators import validate_password_strength


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    email: EmailStr
    password: str = Field(min_length=1)

    @field_validator('email')
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = 'bearer'


class UserRBACMetadata(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    full_name: str | None = None
    is_active: bool = True
    is_superuser: bool = False
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = 'bearer'
    user: UserRBACMetadata


class RefreshRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    refresh_token: str = Field(min_length=1)


class PasswordResetRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    email: EmailStr

    @field_validator('email')
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class PasswordResetConfirm(BaseModel):
    model_config = ConfigDict(extra='forbid')

    token: str = Field(min_length=1)
    new_password: str

    @field_validator('new_password')
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        return validate_password_strength(value)


class EmailVerificationConfirm(BaseModel):
    model_config = ConfigDict(extra='forbid')

    token: str = Field(min_length=1)


class ResendVerificationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    email: EmailStr

    @field_validator('email')
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class WSTicketResponse(BaseModel):
    ticket: str
    expires_in: int = 15

