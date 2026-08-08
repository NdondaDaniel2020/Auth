# Guia de validação de entrada (schemas)

Convenções para criar novos schemas Pydantic de entrada e revisar os
existentes. O objetivo é rejeitar dados inválidos na camada de schema,
**antes** de qualquer lógica de negócio ou consulta ao banco.

## Regras gerais

1. **Schemas de entrada sempre com `model_config = ConfigDict(extra='forbid')`.**
   Campos não esperados no payload geram `HTTP 422` em vez de serem ignorados
   silenciosamente. Aplica-se a `*Create`, `*Update`, login, refresh e demais
   schemas que recebem dados do cliente. Schemas de resposta (`*Read`,
   `*Public`) não precisam.

2. **E-mails: usar `EmailStr`** (exige a dependência `email-validator`).
   Normalizar com um `field_validator` que aplica `strip().lower()`.

3. **Strings livres: definir limites.** Use `Field(min_length=..., max_length=...)`
   sensatos (ex.: `full_name` com `min_length=1` e `max_length=255`). Campos
   opcionais usam `T | None`, não valores mágicos.

4. **Campos de valor fixo (status, tipo): usar `Enum`** do Python com o tipo
   correspondente do Pydantic, nunca `str` livre.

5. **IDs: validar o formato** (ex.: UUID) via `field_validator`, não aceitar
   qualquer string. A validação de existência no banco continua no service.

6. **Normalizar entrada no schema:** remover espaços extras (`strip()`) e
   normalizar caixa onde fizer sentido (e-mail), para que dados "sujos" não
   cheguem à camada de serviço.

7. **Validação de negócio simples vai no schema;** validação que depende do
   banco (ex.: unicidade de e-mail, existência de role) permanece no service.

## Exemplo

```python
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class ProfileCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    email: EmailStr = Field(..., description='Valid email address')
    full_name: str | None = Field(default=None, min_length=1, max_length=255)

    @field_validator('email')
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()
```

## Formato de erro de validação

O handler global (`app/core/error_handlers.py`) responde `HTTP 422` com
`details` no formato:

```json
{
  "error": {
    "type": "RequestValidationError",
    "message": "Validation error",
    "details": [
      {"field": "email", "message": "value is not a valid email address: ..."}
    ]
  },
  "status": 422,
  "path": "/api/auth/register",
  "method": "POST"
}
```

O campo `field` indica o(s) campo(s) problemático(s); `message` traz a razão
legível, sem dados sensíveis.
