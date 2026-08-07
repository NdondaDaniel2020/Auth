from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.config import get_settings


class UserCreate(BaseModel):
    email: EmailStr = Field(..., description='Valid email address')
    password: str = Field(..., description='Plain-text password')
    full_name: str | None = Field(default=None, max_length=255)

    @field_validator('password')
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        min_length = get_settings().PASSWORD_MIN_LENGTH
        if len(value) < min_length:
            raise ValueError(
                f'Password must be at least {min_length} characters long'
            )
        return value

    @field_validator('email')
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()


class UserUpdate(BaseModel):
    """Fields the authenticated user may change on their own profile.

    Deliberately excludes sensitive fields (``email``, ``hashed_password``,
    ``is_active``, ``is_verified``, ``is_superuser``, roles). ``extra='forbid'``
    makes the API reject payloads that attempt to smuggle them in.
    """

    model_config = ConfigDict(extra='forbid')

    full_name: str | None = Field(default=None, max_length=255)


class UserRoleUpdate(BaseModel):
    """Final set of roles for a user (replace-all semantics).

    ``PUT /users/{user_id}/roles`` replaces the user's roles with exactly
    ``role_ids``. Replace-all is intentional: the desired end state is
    explicit, and the same operation covers both assignment and removal.
    """

    model_config = ConfigDict(extra='forbid')

    role_ids: list[str] = Field(
        ..., description='Role ids that make up the final set'
    )


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    full_name: str | None
    is_active: bool
    is_superuser: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    full_name: str | None
    is_active: bool
    is_verified: bool
    created_at: datetime
