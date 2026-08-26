# Eventos de segurança

Logs estruturados de eventos de segurança relevantes (autenticação, logout,
redefinição de senha, verificação de e-mail). Complementam o logging genérico
e são **distintos** da auditoria administrativa (`app/services/audit_service.py`),
que registra ações de gestão sobre outros usuários.

## Como funciona

`app/core/security_logger.py` expõe `log_security_event(event, *, user_id=None,
ip=None, metadata=None, level=INFO)` e um logger dedicado
(`auth_app.security`) que emite **uma linha JSON por evento**, filtrada por
tipo de evento ou por `user_id` (ex.: `grep '"event": "LOGIN_FAILED"'`).

Formato:

```json
{
  "timestamp": "2026-01-01T12:00:00+00:00",
  "level": "INFO",
  "event": "LOGIN_SUCCESS",
  "user_id": "4e1f...",
  "ip": "203.0.113.9"
}
```

Nível por evento: sucesso → `INFO`; falha/bloqueio → `WARNING`.

## Lista de eventos

| Evento                     | Quando                                                          | Nível    |
| -------------------------- | -------------------------------------------------------------- | -------- |
| `LOGIN_SUCCESS`            | Autenticação bem-sucedida                                       | `INFO`   |
| `LOGIN_FAILED`             | Credenciais inválidas ou conta inativa (motivo genérico em `reason`) | `WARNING` |
| `LOGIN_RATE_LIMITED`       | Identificador bloqueado por excesso de tentativas               | `WARNING` |
| `ACCOUNT_TEMPORARILY_LOCKED` | Bloqueio temporário da conta devido a múltiplas tentativas falhas | `WARNING` |
| `LOGOUT`                   | Refresh token revogado no logout                                | `INFO`   |
| `PASSWORD_RESET_REQUESTED` | Link de redefinição de senha gerado (usuário existente)         | `INFO`   |
| `PASSWORD_RESET_COMPLETED` | Senha redefinida com sucesso                                    | `INFO`   |
| `EMAIL_VERIFIED`           | E-mail confirmado com token de verificação                      | `INFO`   |
| `GOOGLE_LOGIN_SUCCESS`     | Login via Google OAuth bem-sucedido (novo ou existente)         | `INFO`   |
| `GOOGLE_LOGIN_FAILED`      | Falha no login Google (`reason`: disabled/invalid_token/upstream_error) | `WARNING` |

## Restrições

Nenhum evento inclui dados sensíveis: senha em texto puro, hash de senha ou
token completo. Identificadores aceitos: `user_id`, IP de origem, e-mail
(apenas no fluxo de login, para correlação) e `token_id` (o `jti` do refresh
token, um UUID, não o token JWT em si).

## Pontos de integração

- `app/services/user_service.py` — `authenticate_user` (sucesso, falha, bloqueio).
- `app/services/auth_service.py` — `logout`, `request_password_reset`,
  `reset_password`, `verify_email`.
- `app/services/google_auth_service.py` — `google_login` (sucesso/falha no login
  via Google OAuth).
- Rotas passam o IP de origem (`request.client.host`) via `client_ip`.

## Fora de escopo

Integração com SIEM/observabilidade externa e alertas em tempo real serão
tratados em issues futuras.
