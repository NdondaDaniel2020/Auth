from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.validators import validate_password_strength


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
    except ValueError:
        return False
    return True


class UserCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    email: EmailStr = Field(..., description='Valid email address')
    password: str = Field(..., description='Plain-text password')
    full_name: str | None = Field(default=None, min_length=1, max_length=255)

    @field_validator('password')
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        return validate_password_strength(value)

    @field_validator('email')
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator('full_name')
    @classmethod
    def strip_full_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError('full_name must not be empty')
        return stripped


class UserUpdate(BaseModel):
    """Fields the authenticated user may change on their own profile.

    Deliberately excludes sensitive fields (``email``, ``hashed_password``,
    ``is_active``, ``is_verified``, ``is_superuser``, roles). ``extra='forbid'``
    makes the API reject payloads that attempt to smuggle them in.
    """

    model_config = ConfigDict(extra='forbid')

    full_name: str | None = Field(default=None, min_length=1, max_length=255)

    @field_validator('full_name')
    @classmethod
    def strip_full_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError('full_name must not be empty')
        return stripped


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

    @field_validator('role_ids')
    @classmethod
    def validate_role_ids(cls, value: list[str]) -> list[str]:
        invalid = [role_id for role_id in value if not _is_uuid(role_id)]
        if invalid:
            raise ValueError(f'Invalid role id format: {invalid!r}')
        return value


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    full_name: str | None
    is_active: bool
    is_superuser: bool
    is_verified: bool
    mfa_enabled: bool
    mfa_type: str | None
    created_at: datetime
    updated_at: datetime


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    full_name: str | None
    is_active: bool
    is_verified: bool
    mfa_enabled: bool
    mfa_type: str | None
    created_at: datetime
