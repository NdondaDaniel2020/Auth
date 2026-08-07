from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GoogleAuthUrlResponse(BaseModel):
    """URL to redirect the browser to Google's consent screen.

    ``state`` is the signed CSRF token the frontend must send back alongside
    the authorization ``code`` in ``GoogleLoginRequest``.
    """

    authorization_url: str
    state: str


class GoogleLoginRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    code: str | None = Field(default=None, min_length=1)
    state: str | None = Field(default=None, min_length=1)
    id_token: str | None = Field(default=None, min_length=1)

    @model_validator(mode='after')
    def _require_exactly_one_credential(self) -> GoogleLoginRequest:
        has_code = self.code is not None
        has_id_token = self.id_token is not None

        if has_code == has_id_token:
            raise ValueError('Provide exactly one of "code" or "id_token"')

        if has_code and self.state is None:
            raise ValueError('"state" is required when using "code"')

        return self
