# Estrutura do projeto

Este projeto segue uma organização em camadas para separar responsabilidades, facilitar testes e manter o crescimento do código previsível.

## Visão geral das pastas

```text
app/
├── main.py
├── api/
│   ├── dependencies/
│   └── routers/
├── core/
├── db/
├── models/
├── repositories/
├── schemas/
├── services/
├── static/
├── templates/
└── utils/
secrets/
migrations/
tests/
```

## Responsabilidade de cada camada

### `app/main.py`
Ponto de entrada da aplicação. Cria a instância do FastAPI, registra rotas, configura middlewares e expõe recursos estáticos quando necessário.

### `app/api/`
Camada de interface HTTP. Recebe as requisições, valida dependências e encaminha a execução para as regras de negócio.

### `app/api/routers/`
Agrupa os endpoints da aplicação por domínio ou funcionalidade. Cada router define as rotas públicas da API e mantém o código de transporte HTTP organizado.

### `app/api/dependencies/`
Centraliza dependências reutilizáveis do FastAPI, como sessão de banco, autenticação, autorização, paginação e outros dados derivados da requisição.

### `app/core/`
Concentra configurações e componentes transversais do projeto, como variáveis de ambiente, segurança, hashing, tokens, logging e utilitários globais de infraestrutura.

### `app/db/`
Responsável pela infraestrutura de persistência. Normalmente contém a configuração da engine, da sessão, da base declarativa e rotinas de inicialização do banco.

### `app/models/`
Define os modelos ORM que representam as tabelas do banco de dados. Essa camada descreve a estrutura persistida, não as regras de uso da API.

### `app/schemas/`
Contém os schemas do Pydantic usados para entrada e saída de dados. Faz a validação e a serialização dos dados que entram e saem da API.

### `app/repositories/`
Isola o acesso a dados. Aqui ficam as consultas e operações de persistência, escondendo detalhes do ORM do restante da aplicação.

### `app/services/`
Implementa as regras de negócio. Essa camada orquestra repositórios, validações e integrações para executar casos de uso da aplicação.

### `app/templates/`
Armazena templates, principalmente para e-mails e conteúdos renderizados dinamicamente.

### `app/static/`
Guarda arquivos estáticos servidos diretamente pela aplicação, como imagens, CSS e outros assets sem processamento.

### `app/utils/`
Reúne funções auxiliares e utilitários compartilhados que não pertencem a uma camada específica.

### `migrations/`
Contém as migrações do banco de dados. Essa pasta versiona a evolução do schema ao longo do tempo.

### `tests/`
Reúne os testes automatizados do projeto, cobrindo rotas, serviços, repositórios e demais comportamentos críticos.

## Fluxo recomendado entre camadas

1. A requisição entra por `app/api/routers/`.
2. O router usa dependências de `app/api/dependencies/` quando necessário.
3. A lógica principal fica em `app/services/`.
4. O acesso ao banco ocorre via `app/repositories/` e `app/db/`.
5. Os dados retornados são validados e serializados por `app/schemas/`.

Essa separação reduz acoplamento e deixa cada parte do sistema com uma responsabilidade clara.

## Configuração da aplicação

As configurações são carregadas com `pydantic-settings` em [app/core/config.py](app/core/config.py).

Variáveis principais:

- `ENVIRONMENT`: seleciona o perfil da aplicação (`development`, `test` ou `production`).
- `APP_NAME`, `APP_VERSION`, `APP_DESCRIPTION`: metadados da aplicação.
- `DEBUG`: ativa ou desativa modo de depuração.
- `DATABASE_URL`: URL do banco de dados.
- `DB_ENGINE`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`: permitem montar a URL dinamicamente para SQLite e PostgreSQL sem alterar o código.
- `CORS_ALLOWED_ORIGINS`: origens permitidas pelo CORS (lista separada por vírgulas).
- `SECRET_KEY`: chave usada para recursos de autenticação e segurança.
- `ALGORITHM`: algoritmo de assinatura JWT.
- `JWT_ACCESS_MINUTES` e `JWT_REFRESH_DAYS`: tempos de expiração dos tokens.

Comportamento por ambiente:

- `development`: usa defaults seguros para desenvolvimento e lê o arquivo `.env`.
- `test`: usa defaults próprios para testes e também pode ler `.env`.
- `production`: exige que `DATABASE_URL`, `CORS_ALLOWED_ORIGINS` e `SECRET_KEY` sejam informados por variáveis de ambiente.

### CORS por ambiente

O CORS é controlado por `CORS_ALLOWED_ORIGINS` (origens separadas por vírgulas). Opcionalmente, `CORS_ALLOW_CREDENTIALS`, `CORS_ALLOWED_METHODS` e `CORS_ALLOWED_HEADERS` ajustam credenciais, métodos e headers permitidos.

Exemplo para desenvolvimento:

```env
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173
CORS_ALLOW_CREDENTIALS=true
```

Exemplo para produção (apenas os domínios reais da aplicação):

```env
CORS_ALLOWED_ORIGINS=https://app.meudominio.com
CORS_ALLOW_CREDENTIALS=true
```

> **Segurança:** em produção, `CORS_ALLOWED_ORIGINS` nunca deve ser `*` quando `CORS_ALLOW_CREDENTIALS=true` — a combinação é rejeitada na inicialização.

## Alternar entre SQLite e PostgreSQL

A aplicação pode trocar de banco apenas alterando variáveis de ambiente.

### SQLite (desenvolvimento/teste)

Use:

```env
DB_ENGINE=sqlite
DB_NAME=./.data/app.db
DATABASE_URL=
```

Para banco em memória durante testes:

```env
DB_ENGINE=sqlite
DB_NAME=:memory:
DATABASE_URL=
```

### PostgreSQL local (Docker)

Use:

```env
DB_ENGINE=postgresql
DB_USER=Auth
DB_PASSWORD=Auth1234
DB_HOST=localhost
DB_PORT=5432
DB_NAME=Auth
DATABASE_URL=
```

O `DATABASE_URL` é montado automaticamente a partir desses campos e será algo como:

```text
postgresql+asyncpg://Auth:Auth1234@localhost:5432/Auth
```

### PostgreSQL via Docker Compose com a aplicação em container

Se a aplicação também estiver rodando em um container no mesmo `docker-compose.yml`,
use o nome do serviço do banco como host. Neste projeto, o serviço do banco se chama
`db`, então a configuração correta é:

```env
DB_ENGINE=postgresql
DB_USER=Auth
DB_PASSWORD=Auth1234
DB_HOST=db
DB_PORT=5432
DB_NAME=Auth
DATABASE_URL=
```

Nesse cenário, `localhost` aponta para o próprio container da aplicação, não para o
container do PostgreSQL. O hostname `db` funciona porque o Docker Compose cria uma
rede interna e resolve o nome do serviço automaticamente.

## PostgreSQL com Docker Compose e secrets

O arquivo [docker-compose.yml](docker-compose.yml) usa secrets para injetar as credenciais do PostgreSQL no container do banco. Por isso, o diretório `secrets/` precisa existir na raiz do projeto com estes arquivos:

```text
secrets/
├── db_user.txt
├── db_password.txt
└── db_name.txt
```

Cada arquivo deve conter apenas o valor do secret correspondente, sem aspas nem espaços extras.

Exemplo:

- `secrets/db_user.txt` -> `Auth`
- `secrets/db_password.txt` -> `Auth1234`
- `secrets/db_name.txt` -> `Auth`

Quando a aplicação rodar em um container no mesmo compose, use:

```env
DB_HOST=db
DB_PORT=5432
```

Com isso, a aplicação acessa o banco pelo nome do serviço `db` dentro da rede interna do Docker Compose.

Se você trocar credenciais do container, recrie também o volume do Postgres para reaplicar `POSTGRES_USER`, `POSTGRES_PASSWORD` e `POSTGRES_DB`.

## Migrações (Alembic)

O controle de versão do schema do banco de dados é feito com o [Alembic](https://alembic.sqlalchemy.org/). A configuração central está em `alembic.ini` e `migrations/env.py`. O Alembic foi configurado para ler automaticamente o `DATABASE_URL` do seu ambiente local, então basta definir as variáveis de ambiente corretas (via `.env` ou exportando-as).

### Gerar uma nova migração (autogenerate)
Quando adicionar ou modificar tabelas no seu `app/models/`, gere a migração correspondente:
```bash
uv run alembic revision --autogenerate -m "descrição da migração"
```
*Sempre revise o arquivo gerado em `migrations/versions/` antes de aplicar, especialmente para operações destrutivas como drops ou alteração de restrições (constraints).*

### Aplicar as migrações (upgrade)
Para atualizar o banco de dados até a última migração:
```bash
uv run alembic upgrade head
```

### Reverter migrações (downgrade)
Para desfazer a última migração aplicada:
```bash
uv run alembic downgrade -1
```
Ou para reverter todas as migrações até o estado inicial (banco limpo):
```bash
uv run alembic downgrade base
```

## Seed de dados iniciais

O módulo `app/db/init_db.py` contém toda a lógica de seed do projecto. Ele é **idempotente**: pode ser executado múltiplas vezes sem criar duplicados nem lançar erros.

### O que o seed cria

| Entidade | Valores padrão |
|---|---|
| Roles | `admin` (acesso total), `user` (somente leitura) |
| Permissões | `users:create/read/update/delete`, `roles:read`, `roles:manage` |
| Atribuições | Todas as permissões → `admin`; apenas `users:read` → `user` |
| Utilizador admin | `ADMIN_EMAIL` (default: `admin@example.com`) com a role `admin` |

### Variáveis de ambiente relevantes

```env
# Ativa o seed automático no arranque da aplicação (default: false)
RUN_SEED_ON_STARTUP=true

# Credenciais do utilizador admin criado pelo seed
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=admin123
```

> **Aviso de segurança**: Altere sempre `ADMIN_PASSWORD` antes de correr o seed em produção.

### Execução standalone (recomendado para CI/CD e produção)

```bash
uv run python -m app.db.init_db
```

Use esta forma em pipelines de deploy, após aplicar as migrações:

```bash
# Pipeline típico
uv run alembic upgrade head
uv run python -m app.db.init_db
```

### Execução automática no arranque (desenvolvimento)

Defina `RUN_SEED_ON_STARTUP=true` no `.env`. O seed será chamado pelo lifespan da aplicação cada vez que ela arrancar.

```env
RUN_SEED_ON_STARTUP=true
```

Este modo é conveniente em desenvolvimento mas **não é recomendado em produção**, pois o seed corre antes de aceitar tráfego e pode atrasar o arranque.

### Quando executar o seed

| Contexto | Método recomendado |
|---|---|
| Desenvolvimento local | `RUN_SEED_ON_STARTUP=true` no `.env` |
| CI/CD (staging/produção) | `uv run python -m app.db.init_db` após `alembic upgrade head` |
| Reset de base local | `alembic downgrade base && alembic upgrade head && python -m app.db.init_db` |

## Fluxo de autenticação

Os endpoints de autenticação estão agrupados em `app/api/routers/auth.py` sob o prefixo `/api/auth`.

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/api/auth/register` | Regista um novo utilizador (devuelve os dados públicos; a senha é guardada como hash e nunca é devolvida). |
| `POST` | `/api/auth/login` | Autentica com e-mail/senha e devolve `access_token` + `refresh_token`. |
| `POST` | `/api/auth/refresh` | Rota o refresh token e devolve um novo par de tokens. |
| `POST` | `/api/auth/logout` | Revoga o refresh token (idempotente, HTTP 204). |
| `POST` | `/api/auth/password-reset/request` | Envia e-mail de recuperação de senha (resposta genérica). |
| `POST` | `/api/auth/password-reset/confirm` | Redefine a senha com o token recebido por e-mail. |
| `POST` | `/api/auth/verify-email` | Confirma o e-mail com o token de verificação. |
| `POST` | `/api/auth/verify-email/resend` | Reenvia o token de verificação. |

### Regras relevantes

- **Registo**: e-mails duplicados são rejeitados com HTTP 409
  (`EmailAlreadyExistsError`). A senha é armazenada apenas como hash
  (`argon2`).
- **Login**: credenciais inválidas devolvem HTTP 401 com mensagem genérica.
  Tentativas falhas consecutivas bloqueiam temporariamente o identificador
  (HTTP 429) — ver `LOGIN_MAX_ATTEMPTS`,
  `LOGIN_ATTEMPT_WINDOW_MINUTES` e `LOGIN_BLOCK_DURATION_MINUTES`.
- **Refresh**: cada refresh token é de utilização única (rotação). O reuso de
  um token já rotacionado revoga todas as sessões do utilizador.
- **Recuperação de senha**: tokens temporários de alta entropia, com expiração
  curta (`PASSWORD_RESET_TOKEN_EXPIRE_MINUTES`) e de utilização única. Após a
  redefinição, todos os refresh tokens do utilizador são revogados.
- **Verificação de e-mail**: o registo cria um token de verificação e envia o
  e-mail. `is_verified` não bloqueia o login (apenas fica registado).

### Envio de e-mails

Se `SMTP_HOST` não estiver configurado, os e-mails são apenas registados nos
logs (modo de desenvolvimento). Para envio real, configure as variáveis
`SMTP_*`. Os templates estão em `app/templates/emails/`.

### Política de tokens

TTLs, rotação, revogação e estrutura de claims dos tokens estão documentados
em [docs/token-policy.md](docs/token-policy.md).

## Autorização (RBAC)

Toda a autorização está centralizada em `app/api/dependencies/` — as rotas
**não** implementam verificações ad-hoc:

| Dependência | Uso | Sem acesso |
|---|---|---|
| `get_current_user` (`auth.py`) | Extrai e valida o access token, resolve o utilizador ativo | HTTP 401 `NotAuthenticatedError` |
| `require_role('admin')` (`permissions.py`) | Exige uma das roles listadas | HTTP 403 `PermissionDeniedError` |
| `check_permission('users:delete')` (`permissions.py`) | Exige uma permissão específica (via roles do utilizador) | HTTP 403 `PermissionDeniedError` |

Exemplo:

```python
from app.api.dependencies.auth import CurrentUserDep
from app.api.dependencies.permissions import require_role, check_permission
from fastapi import Depends

@router.get('/users/me')
async def profile(user: CurrentUserDep) -> UserRead:
    ...

@router.get('/users')
async def list_users(
    user=Depends(require_role('admin')),
    db: SessionDep,
) -> list[UserRead]:
    ...
```

- `get_current_user` carrega as roles e permissões do utilizador de forma
  antecipada (`selectinload`), para que `require_role`/`check_permission`
  funcionem em contexto assíncrono.
- O `OAuth2PasswordBearer` aponta para `/api/auth/login-form` (o endpoint
  OAuth2 com `OAuth2PasswordRequestForm`).
- As roles/permissões seedadas estão em `app/db/init_db.py`
  (`DEFAULT_ROLES`/`DEFAULT_PERMISSIONS`): a role `admin` tem todas as
  permissões; a role `user` apenas `users:read`.

### Códigos de erro de acesso

Todas as respostas de erro seguem o formato `{error: {type, message, code},
status, path, method}`. O campo `code` é um identificador estável que o
frontend usa para distinguir cenários (ex: `TOKEN_EXPIRED`,
`INSUFFICIENT_ROLE`) — ver [docs/error-codes.md](docs/error-codes.md).
