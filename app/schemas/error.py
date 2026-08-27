from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Detalhes da exceção retornada pela API."""

    type: str = Field(
        ...,
        description='Nome da classe da exceção tratada.',
        examples=['TokenExpiredError'],
    )
    message: str = Field(
        ...,
        description='Mensagem amigável descrevendo a causa do erro.',
        examples=['Access token expired'],
    )
    code: str | None = Field(
        default=None,
        description='Identificador de erro estável para consumo pelo frontend.',
        examples=['TOKEN_EXPIRED'],
    )
    details: Any | None = Field(
        default=None,
        description='Detalhes adicionais ou lista de erros de validação.',
        examples=None,
    )


class ErrorResponse(BaseModel):
    """Formato padrão de resposta de erro retornado centralmente pela API."""

    error: ErrorDetail
    status: int = Field(
        ...,
        description='Código de status HTTP da resposta.',
        examples=[401],
    )
    path: str = Field(
        ...,
        description='Caminho/URI da requisição.',
        examples=['/api/auth/me'],
    )
    method: str = Field(
        ...,
        description='Método HTTP da requisição.',
        examples=['GET'],
    )
