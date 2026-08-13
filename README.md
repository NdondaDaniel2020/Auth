# Auth API

API de autenticação e autorização construída com FastAPI (assíncrono).
Serve de base para projetos que precisam de **registro e login de
utilizadores, gestão de sessão com tokens JWT rotativos, RBAC
(roles/permissões), recuperação de senha, verificação de e-mail e login
social com Google** — com testes, migrações e seeds prontos.

## Visão geral

- **Autenticação:** registro, login (e-mail/senha e OAuth2 password form),
  refresh com rotação de tokens, logout idempotente, recuperação de senha,
  verificação de e-mail e login social com Google.
- **Autorização (RBAC):** roles e permissões com checagem centralizada em
  dependências (`require_role`, `check_permission`).
- **Gestão de utilizadores:** perfil próprio, listagem/consulta e
  ativação/desativação administrativa, atribuição de roles.
- **Segurança:** política de senha forte, rate limiting por rota, bloqueio
  por tentativas de login falhas, tokens revogáveis, eventos de segurança.

### Stack

| Camada | Tecnologia |
|---|---|
| Framework | FastAPI (async) |
| ORM | SQLAlchemy 2.0 (async) |
| Migrações | Alembic |
| Banco | PostgreSQL (produção) / SQLite (dev e testes) |
| Validação | Pydantic v2 + pydantic-settings |
| Contêineres | Docker / Docker Compose |
| Gerenciador de dependências | `uv` |

## Estrutura do projeto

```text
app/
├── main.py                     # Ponto de entrada (FastAPI app)
├── api/
│   ├── dependencies/           # Auth, permissions, pagination, rate limit, db
│   ├── routers/                # auth.py, google_auth.py, users.py
│   └── router.py               # Agrega os routers
├── core/                       # Config, security, exceptions, logging, limiter
├── db/                         # base.py, session.py, init_db.py (seed)
├── models/                     # ORM: user, role, permission, tokens, etc.
├── schemas/                    # Pydantic de entrada/saída
├── repositories/               # Acesso a dados (base.py genérico + específicos)
├── services/                   # Regras de negócio (auth, user, email, google)
├── templates/emails/           # Templates de e-mail
├── static/                     # Assets estáticos
└── utils/                      # Helpers transversais
migrations/                     # Migrações Alembic (versions/)
tests/                          # Suíte: raiz (HTTP), services, repositories, integration
```

### Fluxo recomendado entre camadas

1. A requisição entra por `app/api/routers/`.
2. O router usa dependências de `app/api/dependencies/` (auth, autorização,
   paginação, rate limit).
3. A lógica principal fica em `app/services/`.
4. O acesso ao banco ocorre via `app/repositories/` e `app/db/`.
5. Os dados são validados/serializados por `app/schemas/`.

## Requisitos

- **Python 3.14+** (definido em `pyproject.toml`)
- **`uv`** como gerenciador de dependências
- **Docker + Docker Compose** (opcional, para PostgreSQL)
- **Make** (opcional, atalhos do `Makefile`)

## Instalação

```bash
# 1. Clonar o repositório
git clone <url-do-repo>
cd Auth

# 2. Instalar dependências (inclui grupo dev)
uv sync --group dev

# 3. Copiar as variáveis de ambiente
cp .env.example .env
```

> O `.env.example` contém placeholders — nenhum valor real está versionado.

## Configuração de ambiente

As variáveis são carregadas via `pydantic-settings` em
`app/core/config.py`. O perfil ativo é escolhido por `ENVIRONMENT`
(`development`, `test` ou `production`).

Principais grupos:

- **Aplicação:** `ENVIRONMENT`, `APP_NAME`, `DEBUG`
- **Banco:** `DATABASE_URL` ou `DB_ENGINE`/`DB_NAME`/`DB_USER`/`DB_PASSWORD`/
  `DB_HOST`/`DB_PORT`
- **JWT:** `SECRET_KEY`, `REFRESH_SECRET_KEY`, `ALGORITHM`,
  `JWT_ACCESS_MINUTES`, `JWT_REFRESH_DAYS`
- **SMTP:** `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`,
  `SMTP_FROM`
- **CORS:** `CORS_ALLOWED_ORIGINS`, `CORS_ALLOW_CREDENTIALS` e demais
- **Rate limiting:** `RATE_LIMIT_DEFAULT`, `RATE_LIMIT_REGISTER`, ...
- **Login social:** `GOOGLE_LOGIN_ENABLED`, `GOOGLE_CLIENT_ID`, ...

Referência completa de todas as variáveis (nome, tipo, default,
obrigatoriedade e segurança): [docs/environment-variables.md](docs/environment-variables.md).

## Execução local

### Via `uvicorn` (desenvolvimento)

```bash
uv run task run
# ou, com hot-reload:
uv run task runserver
```

### Via Docker Compose

```bash
# Subir o PostgreSQL (serviço `db`)
docker compose up -d
```

> O `docker-compose.yml` usa `secrets/` para as credenciais do PostgreSQL.
> Crie `secrets/db_user.txt`, `secrets/db_password.txt` e `secrets/db_name.txt`
> na raiz antes de subir o banco.

### Aplicar migrações e seeds

```bash
uv run alembic upgrade head
uv run python -m app.db.init_db   # idempotente
```

Documentação completa do banco (migrações, seeds, testes):
[docs/migrations-seeds-tests.md](docs/migrations-seeds-tests.md).

### Documentação automática

Com a aplicação a correr, acesse:

- **Swagger UI:** <http://localhost:8001/docs>
- **ReDoc:** <http://localhost:8001/redoc>

## Banco de dados

A aplicação alterna entre bancos apenas via variáveis de ambiente — sem
mudança de código.

### SQLite (desenvolvimento/teste)

```env
DB_ENGINE=sqlite
DB_NAME=./.data/app.db
```

### PostgreSQL local (Docker)

```env
DB_ENGINE=postgresql
DB_USER=Auth
DB_PASSWORD=Auth1234
DB_HOST=localhost
DB_PORT=5432
DB_NAME=Auth
```

Com a aplicação no mesmo `docker-compose.yml`, use `DB_HOST=db` (nome do
serviço na rede interna do Compose).

### Criar novas migrações

```bash
uv run alembic revision --autogenerate -m "descrição da migração"
uv run alembic upgrade head
```

## Testes

A suíte é organizada por camada:

- `tests/` — comportamento via HTTP dos fluxos de auth/RBAC.
- `tests/test_services/` — regras de negócio sem a camada HTTP.
- `tests/test_repositories/` — acesso a dados (CRUD, constraints).
- `tests/test_integration/` — jornadas ponta a ponta (marcadas com
  `@pytest.mark.integration`).

```bash
uv run task lint        # ruff
uv run task test        # suíte completa com cobertura (gera htmlcov/)
uv run pytest -m integration          # apenas integração
uv run pytest -m "not integration"    # apenas os demais
uv run pytest tests/test_auth_login.py -k "test_login_success"  # teste específico
```

O relatório de cobertura é gerado em `htmlcov/`. Convenções:
[docs/testing-conventions.md](docs/testing-conventions.md).

## Autenticação e autorização

### Fluxo de autenticação

Endpoints sob `/api/auth`:

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/api/auth/register` | Regista utilizador e envia e-mail de verificação |
| `POST` | `/api/auth/login` | Login com e-mail/senha; devolve `access_token` + `refresh_token` |
| `POST` | `/api/auth/login-form` | Login via OAuth2 password form |
| `POST` | `/api/auth/refresh` | Roda o refresh token (novo par emitido) |
| `POST` | `/api/auth/logout` | Revoga o refresh token (idempotente, 204) |
| `POST` | `/api/auth/password-reset/request` | Envia e-mail de recuperação |
| `POST` | `/api/auth/password-reset/confirm` | Redefine a senha com o token |
| `POST` | `/api/auth/verify-email` | Confirma o e-mail com o token |
| `POST` | `/api/auth/verify-email/resend` | Reenvia o token de verificação |
| `GET` | `/api/auth/google/url` | URL de autorização do login Google |
| `POST` | `/api/auth/google/callback` | Completa o login com Google |

Documentação detalhada (diagramas, tokens, estados do utilizador, erros):
[docs/authentication-flow.md](docs/authentication-flow.md).

### Política de tokens

TTLs, rotação, revogação e claims: [docs/token-policy.md](docs/token-policy.md).

### RBAC (roles e permissões)

Toda a autorização está centralizada em `app/api/dependencies/` — as rotas
**não** implementam verificações ad-hoc:

| Dependência | Uso | Sem acesso |
|---|---|---|
| `get_current_user` | Extrai e valida o access token | HTTP 401 `NOT_AUTHENTICATED` |
| `require_role('admin')` | Exige uma das roles listadas | HTTP 403 `INSUFFICIENT_ROLE` |
| `check_permission('users:delete')` | Exige uma permissão granular | HTTP 403 `INSUFFICIENT_PERMISSION` |

Roles padrão (seed): `admin` (acesso total) e `user` (`users:read`).
Permissões: `users:create/read/update/delete`, `roles:read`, `roles:manage`.

Modelo conceitual: [docs/rbac-model.md](docs/rbac-model.md).
Matriz endpoint-a-endpoint: [docs/authorization-matrix.md](docs/authorization-matrix.md).

## Usando este projeto como template

Guia para reaproveitar esta base em novos projetos (o que manter, o que
adaptar, como adicionar entidades e rotas protegidas):
[docs/boilerplate-guide.md](docs/boilerplate-guide.md).

## Contribuição

- **Lint/formatação:** `uv run task lint` (ruff).
- **Testes:** `uv run task test` (cobertura).
- **Padrão de commits:** convencional, com referência à issue quando
  aplicável (ex.: `feat: ... (#53)`).
- **PRs:** abertos contra a `main`; a suíte completa deve passar.

## Links úteis

- Documentação automática: <http://localhost:8001/docs>
- [docs/environment-variables.md](docs/environment-variables.md) — variáveis de ambiente
- [docs/authentication-flow.md](docs/authentication-flow.md) — fluxo de autenticação
- [docs/token-policy.md](docs/token-policy.md) — política de tokens
- [docs/rbac-model.md](docs/rbac-model.md) — modelo de roles e permissões
- [docs/authorization-matrix.md](docs/authorization-matrix.md) — matriz de autorização
- [docs/error-codes.md](docs/error-codes.md) — formato e códigos de erro
- [docs/security-events.md](docs/security-events.md) — eventos de segurança
- [docs/password-policy.md](docs/password-policy.md) — política de senha
- [docs/validation-guidelines.md](docs/validation-guidelines.md) — validação de entrada
- [docs/mfa-readiness.md](docs/mfa-readiness.md) — preparação para MFA
- [docs/migrations-seeds-tests.md](docs/migrations-seeds-tests.md) — migrações, seeds e testes
- [docs/testing-conventions.md](docs/testing-conventions.md) — convenções de teste
- [docs/boilerplate-guide.md](docs/boilerplate-guide.md) — extensibilidade
