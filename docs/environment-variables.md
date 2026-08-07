# Variáveis de ambiente

Referência única e centralizada de todas as variáveis de ambiente consumidas
pela aplicação. A fonte de verdade das definições é `app/core/config.py`
(`Settings` via `pydantic-settings`); este documento mantém o `.env.example`
sincronizado com o que o código realmente lê.

## Como as configurações funcionam

- O perfil ativo é escolhido por `ENVIRONMENT` (`development`, `test` ou
  `production`), lido por `EnvironmentSettings` antes de carregar as demais.
- Cada ambiente usa uma classe de `Settings` própria. Valores não informados
  assumem o *default* da classe; **produção** exige `DATABASE_URL`,
  `CORS_ALLOWED_ORIGINS` e `SECRET_KEY` não vazios (falha na inicialização) e
  não lê o arquivo `.env`.
- `development` e `test` leem o arquivo `.env` localmente.
- Nunca commitar valores reais: o `.env` é ignorado pelo git; apenas o
  `.env.example` (com placeholders) é versionado.

## Legenda

- **Obrigatória**: precisa de valor real para o ambiente rodar corretamente.
  Valores sem *default* efetivo estão marcados como obrigatórios em produção.
- **Default**: valor assumido quando a variável não é definida.
- **Muda por ambiente**: sim = precisa ser reavaliada entre dev/staging/prod;
  não = mantém o mesmo valor.

---

## Aplicação

| Variável | Tipo | Default | Obrigatória | Muda por ambiente | Descrição |
|---|---|---|---|---|---|
| `ENVIRONMENT` | `development` \| `test` \| `production` | `development` | sim | sim | Perfil de configuração ativo. |
| `APP_NAME` | string | `Auth API` | não | não | Nome exibido na documentação da API. |
| `APP_VERSION` | string | `0.1.0` | não | não | Versão da API. |
| `APP_DESCRIPTION` | string | `Base FastAPI built with uv.` | não | não | Descrição da API. |
| `DEBUG` | bool | `false` (dev: `true`) | não | sim | Habilita modo de depuração. |

Exemplo:

```env
ENVIRONMENT=development
APP_NAME="Auth API"
DEBUG=true
```

## Banco de dados

| Variável | Tipo | Default | Obrigatória | Muda por ambiente | Descrição |
|---|---|---|---|---|---|
| `DATABASE_URL` | string | `sqlite+aiosqlite:///./.data/app.db` | sim (produção) | sim | URL completa de conexão. Se vazia, é montada a partir das variáveis `DB_*`. |
| `DB_ENGINE` | string | `''` | não | sim | `sqlite`, `postgresql` (ou URL com driver). Usado para montar `DATABASE_URL`. |
| `DB_USER` | string | `''` | não | sim | Utilizador do banco (PostgreSQL). |
| `DB_PASSWORD` | string | `''` | não | sim | Senha do banco (PostgreSQL). **Sensível.** |
| `DB_HOST` | string | `''` | não | sim | Host do banco (`localhost` em dev; nome do serviço `db` no Docker). |
| `DB_PORT` | string | `''` | não | sim | Porta do banco (ex.: `5432`). |
| `DB_NAME` | string | `''` | não | sim | Nome do banco ou caminho do arquivo SQLite. |

A montagem da URL prioriza `DATABASE_URL` quando preenchida; caso contrário
combina as variáveis `DB_*`. Para PostgreSQL, o driver `asyncpg` é
acrescentado automaticamente.

Exemplos:

```env
# SQLite (dev)
DB_ENGINE=sqlite
DB_NAME=./.data/app.db

# PostgreSQL local
DB_ENGINE=postgresql
DB_USER=Auth
DB_PASSWORD=Auth1234
DB_HOST=localhost
DB_PORT=5432
DB_NAME=Auth

# PostgreSQL dentro do docker-compose (host = nome do serviço)
DB_HOST=db
```

## CORS

| Variável | Tipo | Default | Obrigatória | Muda por ambiente | Descrição |
|---|---|---|---|---|---|
| `CORS_ALLOWED_ORIGINS` | string (lista separada por `,`) | `http://localhost:3000,http://localhost:5173` | sim (produção) | sim | Origens autorizadas. Use `*` para permitir todas (sem credenciais). |
| `CORS_ALLOW_CREDENTIALS` | bool | `true` (test: `false`) | não | sim | Permite envio de cookies/credentials. |
| `CORS_ALLOWED_METHODS` | string (lista separada por `,`) | `GET,POST,PUT,PATCH,DELETE,OPTIONS,HEAD` | não | não | Métodos HTTP autorizados. |
| `CORS_ALLOWED_HEADERS` | string (lista separada por `,`) | `Authorization,Content-Type,Origin,Accept` | não | não | Headers autorizados. |

> **Segurança:** em produção `CORS_ALLOWED_ORIGINS` não pode ser `*` com
> `CORS_ALLOW_CREDENTIALS=true` — a combinação é rejeitada na inicialização.

## Autenticação / JWT

| Variável | Tipo | Default | Obrigatória | Muda por ambiente | Descrição |
|---|---|---|---|---|---|
| `SECRET_KEY` | string | `dev-only-secret-change-me` | sim (produção) | sim | Chave de assinatura dos access tokens e fallback do refresh. **Sensível.** |
| `REFRESH_SECRET_KEY` | string | `''` | não | sim | Chave dedicada aos refresh tokens. Se vazia, usa `SECRET_KEY`. **Sensível.** |
| `ALGORITHM` | string | `HS256` | não | não | Algoritmo de assinatura JWT. |
| `JWT_ACCESS_MINUTES` | int | `15` | não | não | TTL do access token (minutos). |
| `JWT_REFRESH_DAYS` | int | `7` | não | não | TTL do refresh token (dias). |

Exemplo:

```env
SECRET_KEY="troque-este-valor-por-algo-aleatorio"
REFRESH_SECRET_KEY="outra-chave-aleatoria"
JWT_ACCESS_MINUTES=15
JWT_REFRESH_DAYS=7
```

Gerar chaves com entropia suficiente:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

## Política de senha

| Variável | Tipo | Default | Obrigatória | Muda por ambiente | Descrição |
|---|---|---|---|---|---|
| `PASSWORD_HASH_SCHEME` | string | `argon2` | não | não | Esquema de hashing de senha. |
| `PASSWORD_MIN_LENGTH` | int | `8` | não | não | Comprimento mínimo. |
| `PASSWORD_MAX_LENGTH` | int | `128` | não | não | Comprimento máximo. |
| `PASSWORD_REQUIRE_UPPERCASE` | bool | `true` | não | não | Exige letra maiúscula. |
| `PASSWORD_REQUIRE_LOWERCASE` | bool | `true` | não | não | Exige letra minúscula. |
| `PASSWORD_REQUIRE_DIGIT` | bool | `true` | não | não | Exige dígito. |
| `PASSWORD_REQUIRE_SPECIAL` | bool | `true` | não | não | Exige caractere especial. |
| `PASSWORD_REJECT_COMMON` | bool | `true` | não | não | Rejeita senhas comuns. |

Regras detalhadas: [docs/password-policy.md](password-policy.md).

## Login (bloqueio por tentativas falhas)

| Variável | Tipo | Default | Obrigatória | Muda por ambiente | Descrição |
|---|---|---|---|---|---|
| `LOGIN_MAX_ATTEMPTS` | int | `5` | não | não | Tentativas falhas antes do bloqueio. |
| `LOGIN_ATTEMPT_WINDOW_MINUTES` | int | `15` | não | não | Janela de contagem das tentativas. |
| `LOGIN_BLOCK_DURATION_MINUTES` | int | `30` | não | não | Duração do bloqueio. |

## Rate limiting genérico por rota

Formato: `"N/timeunit"`, unidades: `second`, `minute`, `hour`, `day`.

| Variável | Tipo | Default | Obrigatória | Muda por ambiente | Descrição |
|---|---|---|---|---|---|
| `RATE_LIMIT_DEFAULT` | string | `60/minute` | não | não | Limite padrão aplicado quando a rota não tem um escopo específico. |
| `RATE_LIMIT_REGISTER` | string | `10/minute` | não | não | `POST /api/auth/register`. |
| `RATE_LIMIT_PASSWORD_RESET` | string | `5/minute` | não | não | `POST /api/auth/password-reset/request`. |
| `RATE_LIMIT_EMAIL_RESEND` | string | `3/minute` | não | não | `POST /api/auth/verify-email/resend`. |

> As rotas do login Google (`/api/auth/google/url` e
> `/api/auth/google/callback`) usam o escopo `RATE_LIMIT_DEFAULT`.

Ao exceder o limite a API responde `429 Too Many Requests` com
`code: "RATE_LIMIT_EXCEEDED"` e o header `Retry-After`.

> **Nota de escalabilidade:** o backend de rate limit é em memória (por
> processo). Com múltiplas instâncias, use um backend distribuído (ex.: Redis).

## Duração de tokens de verificação

| Variável | Tipo | Default | Obrigatória | Muda por ambiente | Descrição |
|---|---|---|---|---|---|
| `PASSWORD_RESET_TOKEN_EXPIRE_MINUTES` | int | `30` | não | não | TTL do token de redefinição de senha. |
| `EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES` | int | `1440` | não | não | TTL do token de verificação de e-mail (1 dia). |

## Paginação

| Variável | Tipo | Default | Obrigatória | Muda por ambiente | Descrição |
|---|---|---|---|---|---|
| `PAGE_SIZE_DEFAULT` | int | `20` | não | não | Tamanho de página padrão dos endpoints paginados. |
| `PAGE_SIZE_MAX` | int | `100` | não | não | Tamanho máximo aceito (valores acima são rejeitados com 422). |

## Aplicação / links

| Variável | Tipo | Default | Obrigatória | Muda por ambiente | Descrição |
|---|---|---|---|---|---|
| `APP_BASE_URL` | string | `http://localhost:8001` | sim | sim | URL pública base usada nos links embutidos nos e-mails (ex.: link de redefinição de senha). |

## SMTP (e-mail)

| Variável | Tipo | Default | Obrigatória | Muda por ambiente | Descrição |
|---|---|---|---|---|---|
| `SMTP_HOST` | string | `''` | não | sim | Host SMTP. Vazio = e-mails apenas registados nos logs (modo dev). |
| `SMTP_PORT` | int | `587` | não | não | Porta SMTP. |
| `SMTP_USER` | string | `''` | não | sim | Utilizador SMTP. **Sensível.** |
| `SMTP_PASSWORD` | string | `''` | não | sim | Senha SMTP. **Sensível.** |
| `SMTP_FROM` | string | `''` | não | sim | Remetente padrão dos e-mails. |
| `SMTP_TLS` | bool | `true` | não | não | Habilita TLS (STARTTLS). |

Exemplo:

```env
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=no-reply@example.com
SMTP_PASSWORD=senha-smtp
SMTP_FROM="Auth <no-reply@example.com>"
```

## Login social — Google OAuth 2.0 / OpenID Connect

| Variável | Tipo | Default | Obrigatória | Muda por ambiente | Descrição |
|---|---|---|---|---|---|
| `GOOGLE_LOGIN_ENABLED` | bool | `false` | não | sim | Habilita o login social com Google. |
| `GOOGLE_CLIENT_ID` | string | `''` | sim (se habilitado) | sim | Client ID do OAuth 2.0. **Sensível.** |
| `GOOGLE_CLIENT_SECRET` | string | `''` | sim (se habilitado) | sim | Client secret do OAuth 2.0. **Sensível.** |
| `GOOGLE_REDIRECT_URI` | string | `''` | sim (se habilitado) | sim | URI de redirecionamento; precisa constar nas URIs autorizadas do console do Google. |
| `GOOGLE_AUTH_URL` | string | `https://accounts.google.com/o/oauth2/v2/auth` | não | não | Endpoint de autorização. |
| `GOOGLE_TOKEN_URL` | string | `https://oauth2.googleapis.com/token` | não | não | Endpoint de troca de código por tokens. |
| `GOOGLE_CERTS_URL` | string | `https://www.googleapis.com/oauth2/v3/certs` | não | não | Endpoint das chaves públicas (JWKS). |
| `GOOGLE_ISSUER` | string | `https://accounts.google.com` | não | não | Emissor esperado nos id_tokens. |
| `GOOGLE_STATE_TTL_MINUTES` | int | `10` | não | não | Tempo de vida do token `state` (anti-CSRF). |
| `GOOGLE_CERTS_CACHE_TTL_SECONDS` | int | `300` | não | não | Cache das chaves públicas (JWKS). |

Exemplo:

```env
GOOGLE_LOGIN_ENABLED=true
GOOGLE_CLIENT_ID=xxxxxxxxxxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxx
GOOGLE_REDIRECT_URI=http://localhost:8001/api/auth/google/callback
```

## Seed e utilizador administrador

| Variável | Tipo | Default | Obrigatória | Muda por ambiente | Descrição |
|---|---|---|---|---|---|
| `RUN_SEED_ON_STARTUP` | bool | `false` | não | sim | Executa o seed no arranque da aplicação (recomendado apenas em dev). |
| `ADMIN_EMAIL` | string | `admin@example.com` | não | sim | E-mail do utilizador admin criado pelo seed. |
| `ADMIN_PASSWORD` | string | `admin123` | não | sim | Senha do admin criado pelo seed. **Sensível — altere sempre antes de produção.** |

Exemplo:

```env
RUN_SEED_ON_STARTUP=true
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=troque-esta-senha
```

---

## Orientações de segurança

- **Nunca commitar valores reais.** O `.env` está no `.gitignore`; versionar
  apenas `.env.example` com placeholders.
- **`SECRET_KEY` e `REFRESH_SECRET_KEY`:** gere com entropia suficiente
  (`secrets.token_urlsafe(64)`) e mantenha `REFRESH_SECRET_KEY` distinta de
  `SECRET_KEY` em produção.
- **Senhas de banco, credenciais SMTP, `GOOGLE_CLIENT_SECRET`, `ADMIN_PASSWORD`**
  são segredos: use um gerenciador de segredos (variáveis de ambiente do
  provedor, Vault, AWS Secrets Manager, etc.) em produção, em vez de arquivos
  versionados.
- Rotacione chaves regularmente e nunca as registe nos logs.

## Comandos úteis

```bash
# Gerar uma SECRET_KEY aleatória
python -c "import secrets; print(secrets.token_urlsafe(64))"

# Rodar a aplicação apontando para um ambiente específico
ENVIRONMENT=production python -m app.main

# Validar que o .env carrega corretamente (imprime a configuração)
python -c "from app.core.config import get_settings; s = get_settings(); print(s.APP_NAME, s.ENVIRONMENT)"
```
