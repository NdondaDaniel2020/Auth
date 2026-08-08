# Política de senha

A política é aplicada centralmente em `app/schemas/validators.py`
(`validate_password_strength`) e usada em **todos** os fluxos que definem uma
nova senha:

- Registro de usuário (`POST /api/auth/register` — schema `UserCreate`).
- Redefinição de senha (`POST /api/auth/password-reset/confirm` — schema `PasswordResetConfirm`).

A validação ocorre na camada de schema (Pydantic), **antes** de qualquer
chamada a `hash_password`; senhas inválidas retornam `HTTP 422`.

## Critérios (padrão)

| Critério | Valor padrão | Configuração |
|---|---|---|
| Tamanho mínimo | 8 caracteres | `PASSWORD_MIN_LENGTH` |
| Tamanho máximo | 128 caracteres | `PASSWORD_MAX_LENGTH` |
| Letra maiúscula | obrigatória | `PASSWORD_REQUIRE_UPPERCASE` |
| Letra minúscula | obrigatória | `PASSWORD_REQUIRE_LOWERCASE` |
| Dígito | obrigatório | `PASSWORD_REQUIRE_DIGIT` |
| Caractere especial | obrigatório | `PASSWORD_REQUIRE_SPECIAL` |
| Rejeitar senhas comuns | ativado | `PASSWORD_REJECT_COMMON` |

Senhas na lista de senhas comuns (`COMMON_PASSWORDS` em
`app/schemas/validators.py`) são rejeitadas mesmo quando atendem aos critérios
formais (ex.: `password123`, `admin123`, `qwerty123`, `Password123!`).

## Mensagem de erro

A resposta de validação indica de forma clara o critério não atendido:

```json
{
  "error": {
    "type": "RequestValidationError",
    "message": "Validation error",
    "details": [
      {
        "loc": ["body", "password"],
        "msg": "Value error, Password must contain an uppercase letter, a special character",
        "type": "value_error"
      }
    ]
  },
  "status": 422,
  "path": "/api/auth/register",
  "method": "POST"
}
```

## Configuração por ambiente

Todas as variáveis podem ser ajustadas via `.env` (ver `.env.example`). Por
exemplo, para relaxar os requisitos em desenvolvimento:

```env
PASSWORD_MIN_LENGTH=8
PASSWORD_REQUIRE_UPPERCASE=true
PASSWORD_REQUIRE_LOWERCASE=true
PASSWORD_REQUIRE_DIGIT=true
PASSWORD_REQUIRE_SPECIAL=true
PASSWORD_REJECT_COMMON=true
```

## Fora de escopo

- Verificação de senha vazada via serviços externos (ex.: Have I Been Pwned).
- Histórico de senhas (reuso de senhas anteriores).
- Expiração periódica de senha.
