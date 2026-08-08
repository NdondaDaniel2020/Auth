# Matriz de autorização (endpoint-a-endpoint)

Fonte de verdade **por rota** das exigências de autenticação e autorização da
API. Para o modelo conceitual (roles, permissões, convenção `recurso:ação`),
consulte [docs/rbac-model.md](rbac-model.md).

> Autenticação = provar quem é (access token válido). Autorização = decidir o
> que pode fazer (roles/permissões). Esta matriz cobre ambas.

## Legenda

- **Público** — sem token; pode exigir rate limit.
- **Auth** — exige access token válido via `Authorization: Bearer` (resolvido
  por `get_current_user`).
- **Role** — exige uma das roles listadas via `require_role(...)`.
- **Perm** — exige a permissão via `check_permission(...)`.
- Falha de autenticação → `401`; autenticado mas sem autorização → `403`
  (ver [docs/error-codes.md](error-codes.md)).

## Rotas de autenticação (`/api/auth`)

| Método | Rota | Exigência | `code` em caso de falha |
|---|---|---|---|
| `POST` | `/api/auth/register` | Público (rate limit `RATE_LIMIT_REGISTER`) | — |
| `POST` | `/api/auth/login` | Público | `INVALID_CREDENTIALS`, `ACCOUNT_INACTIVE`, `TOO_MANY_ATTEMPTS` |
| `POST` | `/api/auth/login-form` | Público (OAuth2 password form) | idem |
| `POST` | `/api/auth/refresh` | Público (refresh token no corpo) | `INVALID_REFRESH_TOKEN` |
| `POST` | `/api/auth/logout` | Público (refresh token no corpo) | `INVALID_REFRESH_TOKEN` |
| `POST` | `/api/auth/password-reset/request` | Público (rate limit `RATE_LIMIT_PASSWORD_RESET`) | — |
| `POST` | `/api/auth/password-reset/confirm` | Público (token temporário) | `INVALID_OR_EXPIRED_TOKEN`, `TOKEN_ALREADY_USED` |
| `POST` | `/api/auth/verify-email` | Público (token temporário) | `INVALID_OR_EXPIRED_TOKEN`, `TOKEN_ALREADY_USED` |
| `POST` | `/api/auth/verify-email/resend` | Público (rate limit `RATE_LIMIT_EMAIL_RESEND`) | — |

## Rotas de login social (`/api/auth/google`)

| Método | Rota | Exigência | `code` em caso de falha |
|---|---|---|---|
| `GET` | `/api/auth/google/url` | Público (rate limit `RATE_LIMIT_DEFAULT`) | `GOOGLE_LOGIN_DISABLED` |
| `POST` | `/api/auth/google/callback` | Público (rate limit `RATE_LIMIT_DEFAULT`) | `GOOGLE_LOGIN_DISABLED`, `INVALID_GOOGLE_TOKEN`, `GOOGLE_AUTH_ERROR` |

## Rotas de utilizadores (`/api/users`)

| Método | Rota | Exigência | `code` em caso de falha |
|---|---|---|---|
| `GET` | `/api/users/me` | Auth | `NOT_AUTHENTICATED`, `TOKEN_INVALID`, `TOKEN_EXPIRED`, `ACCOUNT_INACTIVE` |
| `PATCH` | `/api/users/me` | Auth | idem |
| `GET` | `/api/users` | Auth + Role `admin` | `INSUFFICIENT_ROLE` |
| `GET` | `/api/users/{user_id}` | Auth + Role `admin` | `INSUFFICIENT_ROLE`, `USER_NOT_FOUND` |
| `PATCH` | `/api/users/{user_id}/deactivate` | Auth + Role `admin` | `INSUFFICIENT_ROLE`, `USER_NOT_FOUND`, `SELF_DEACTIVATION_NOT_ALLOWED` |
| `PATCH` | `/api/users/{user_id}/activate` | Auth + Role `admin` | `INSUFFICIENT_ROLE`, `USER_NOT_FOUND` |
| `PUT` | `/api/users/{user_id}/roles` | Auth + Role `admin` | `INSUFFICIENT_ROLE`, `USER_NOT_FOUND`, `ROLE_NOT_FOUND`, `SELF_ROLE_REMOVAL_NOT_ALLOWED` |

> Nota: as rotas administrativas atuais usam `require_role('admin')`. O
> mecanismo `check_permission` está disponível em
> `app/api/dependencies/permissions.py` e é a opção recomendada para exigir
> permissões granulares (`users:delete`, etc.) em rotas novas — ver
> [docs/rbac-model.md](rbac-model.md).

## Outros

| Método | Rota | Exigência |
|---|---|---|
| `GET` | `/api/health` | Público |

## Regras transversais

- Toda resposta de erro segue o formato `{error: {type, message, code},
  status, path, method}` (ver [docs/error-codes.md](error-codes.md)).
- Autenticação é sempre resolvida antes da autorização; `401` tem prioridade
  sobre `403`.
- Rotas sensíveis aplicam rate limit por IP (`RATE_LIMIT_*`); o excesso
  devolve `429 RATE_LIMIT_EXCEEDED` com header `Retry-After`.
