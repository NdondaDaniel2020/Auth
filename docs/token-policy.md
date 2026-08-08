# Política de expiração e rotação de tokens

Documento de referência da estratégia de gestão de sessão (TTL, rotação e
revogação) aplicada aos tokens de acesso e refresh. Corresponde à issue
`[EPIC-3][SECURITY] Definir política de expiração e rotação de tokens`.

## Tipos de token

| Token | Algoritmo | Chave | TTL padrão | Claim de tipo |
|---|---|---|---|---|
| Access | `ALGORITHM` (HS256) | `SECRET_KEY` | `JWT_ACCESS_MINUTES` (15 min) | `type: "access"` |
| Refresh | `ALGORITHM` (HS256) | `REFRESH_SECRET_KEY` (fallback `SECRET_KEY`) | `JWT_REFRESH_DAYS` (7 dias) | `type: "refresh"` |

### Claims mínimos

Todos os tokens emitidos contêm:

- `sub` — id do utilizador.
- `exp` — expiração (Unix timestamp UTC).
- `iat` — emissão (Unix timestamp UTC).
- `type` — `access` ou `refresh`.

O refresh token contém ainda `jti` — identificador único persistido na tabela
`refresh_tokens`, usado para rotação e revogação.

## Rotação do refresh token

A cada chamada a `POST /auth/refresh`:

1. O refresh token recebido é validado (assinatura, expiração, claim `type`).
2. O `jti` é procurado em `refresh_tokens` e deve existir e não estar revogado.
3. O token usado é **revogado** (`revoked=True`).
4. Um novo par (access + refresh) é emitido, com um novo `jti`.

Ou seja, cada refresh token é **de utilização única**: depois de usado deixa
de funcionar.

## Reuso de um token já rotacionado/revogado

Se um refresh token revogado (ou já rotacionado) voltar a ser usado em
`/auth/refresh`, isso é tratado como possível indício de comprometimento:

- **Contenção**: todos os refresh tokens ativos do utilizador são revogados.
- O pedido é rejeitado com HTTP 401 (`InvalidRefreshTokenError`).

Isto força novo login em todas as sessões quando um token vazado é reutilizado.

## Condições de revogação

| Evento | Efeito |
|---|---|
| `POST /auth/logout` | Revoga o refresh token enviado (idempotente; HTTP 204). |
| `POST /auth/refresh` | Revoga o refresh token usado (rotação). |
| Redefinição de senha (`/auth/password-reset/confirm`) | Revoga **todos** os refresh tokens do utilizador. |
| Desativação de conta (`PATCH /users/{id}/deactivate`) | Revoga **todos** os refresh tokens do utilizador. |
| Remoção da role crítica `admin` de um utilizador | Revoga **todos** os refresh tokens do utilizador. |
| Reuso de token revogado | Revoga **todos** os refresh tokens do utilizador (contenção). |

> Os access tokens não são colocados em denylist; permanecem válidos até a
> expiração natural (15 min), conforme o fluxo atual.

## Estratégia de revogação

A revogação opera apenas sobre refresh tokens (os access tokens expiram
naturalmente em 15 minutos). Há dois níveis, com funções distintas:

- **Revogação seletiva (uma sessão):** `logout` revoga apenas o refresh token
  enviado; `refresh` revoga o token usado na rotação. Outras sessões do mesmo
  utilizador permanecem ativas.
- **Revogação total (todas as sessões):** redefinição de senha, desativação de
  conta, remoção da role `admin` e contenção por reuso de token revogado
  invalidam **todos** os refresh tokens ativos do utilizador.

### Mecanismo centralizado

Toda revogação total passa por
`auth_service.revoke_all_user_sessions(db, user_id)` — a única fonte de
verdade para invalidar todas as sessões de um utilizador. Fluxos que precisam
apenas encerrar uma sessão continuam usando a revogação seletiva (`revoke` do
repository / `logout`). Isto evita lógica de revogação duplicada e garante que
novos gatilhos adotem o mesmo comportamento.

### Decisão sobre roles

Alterações de role sensíveis forçam revogação **apenas quando a role `admin` é
removida** de um utilizador: a remoção do privilégio máximo invalida as sessões
em que ele ainda poderia atuar como admin. Outras alterações de role não
revogam sessões, pois os privilégios são sempre relidos do banco a cada
requisição autenticada (`get_current_user`), aplicando-se imediatamente. Um
admin não pode remover a própria role `admin` (HTTP 400), então a revogação por
role aplica-se a utilizadores distintos do ator.

## Configuração

Todas as políticas são configuráveis por ambiente via `Settings`
(`app/core/config.py`), sem alteração de código:

```env
JWT_ACCESS_MINUTES=15
JWT_REFRESH_DAYS=7
REFRESH_SECRET_KEY=""
PASSWORD_RESET_TOKEN_EXPIRE_MINUTES=30
EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES=1440
```

Para produção, defina `REFRESH_SECRET_KEY` distinta de `SECRET_KEY`.
