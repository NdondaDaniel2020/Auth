# Contrato de erros de acesso

Formato padrão de resposta de erro, aplicado centralmente por
`app/core/error_handlers.py` para **todas** as exceções de acesso
(autenticação e autorização):

```json
{
  "error": {
    "type": "TokenExpiredError",
    "message": "Access token expired",
    "code": "TOKEN_EXPIRED"
  },
  "status": 401,
  "path": "/api/users/me",
  "method": "GET"
}
```

| Campo | Descrição |
|---|---|
| `error.type` | Nome da classe da exceção (para debug interno). |
| `error.message` | Mensagem legível. Nunca revela dados sensíveis. |
| `error.code` | **Identificador estável** consumido pelo frontend. Não depende do texto. |
| `error.details` | Presente apenas quando há detalhes adicionais. |
| `status` | Código HTTP. |
| `path` / `method` | Rota e verbo da requisição. |

## Códigos de autenticação (HTTP 401)

| `code` | Cenário | Exceção |
|---|---|---|
| `NOT_AUTHENTICATED` | Token em falta na requisição. | `NotAuthenticatedError` |
| `TOKEN_INVALID` | Token malformado/inválido, ou `sub` ausente. | `TokenInvalidError` |
| `TOKEN_EXPIRED` | Token expirado. | `TokenExpiredError` |
| `ACCOUNT_INACTIVE` | Token válido, mas utilizador inexistente ou inativo. | `AccountInactiveError` |
| `INVALID_CREDENTIALS` | Login com e-mail/senha errados (mensagem genérica). | `InvalidCredentialsError` |
| `INVALID_REFRESH_TOKEN` | Refresh token inválido/expirado/revogado. | `InvalidRefreshTokenError` |

## Códigos de autorização (HTTP 403)

| `code` | Cenário | Exceção |
|---|---|---|
| `INSUFFICIENT_ROLE` | Autenticado, mas sem nenhuma das roles exigidas. | `PermissionDeniedError` |
| `INSUFFICIENT_PERMISSION` | Autenticado, mas sem a permissão exigida. | `PermissionDeniedError` |

## Outros códigos relacionados

| `code` | Cenário | Status | Exceção |
|---|---|---|---|
| `INVALID_OR_EXPIRED_TOKEN` | Token de redefinição/verificação inválido ou expirado. | 400 | `InvalidOrExpiredTokenError` |
| `TOKEN_ALREADY_USED` | Token de utilização única já consumido. | 400 | `TokenAlreadyUsedError` |
| `TOO_MANY_ATTEMPTS` | Limite de tentativas de login excedido (header `Retry-After`). | 429 | `TooManyLoginAttemptsError` |
| `EMAIL_ALREADY_EXISTS` | E-mail já registado. | 409 | `EmailAlreadyExistsError` |
| `NOT_FOUND` | Recurso não encontrado. | 404 | `NotFoundError` |
| `USER_NOT_FOUND` | Utilizador não encontrado pelo `id`. | 404 | `UserNotFoundError` |

## Como o frontend deve reagir

- `TOKEN_EXPIRED` / `TOKEN_INVALID` → tentar renovar via `POST /api/auth/refresh`; se falhar, redirecionar para o login.
- `NOT_AUTHENTICATED` → redirecionar para o login.
- `ACCOUNT_INACTIVE` → informar que a conta está desativada.
- `INSUFFICIENT_ROLE` / `INSUFFICIENT_PERMISSION` → exibir mensagem de acesso negado (sem redirecionar).
- `TOO_MANY_ATTEMPTS` → aguardar o valor de `Retry-After` antes de tentar novamente.
