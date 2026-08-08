# Usando este projeto como boilerplate

Guia de extensibilidade para quem quer usar esta base como template de um
novo projeto FastAPI. Distingue as partes **estruturais** (mantidas) das
partes **específicas do domínio** (adaptadas/removidas), e documenta o fluxo
para adicionar novas entidades, rotas protegidas e roles/permissões.
Corresponde à issue `[EPIC-8][DOCS] Documentar extensibilidade do boilerplate`.

## Checklist — primeiros passos ao clonar

- [ ] Copiar `.env.example` para `.env` e ajustar `ENVIRONMENT`, `DATABASE_URL`
      (ou `DB_*`), `SECRET_KEY` e `ADMIN_PASSWORD`.
- [ ] Subir o banco e aplicar as migrações:
      ```bash
      uv run alembic upgrade head
      ```
- [ ] Rodar o seed (roles/permissões/admin):
      ```bash
      uv run python -m app.db.init_db
      ```
- [ ] Rodar a suíte de testes para validar o ambiente:
      ```bash
      uv run task test
      ```
- [ ] Iniciar a aplicação:
      ```bash
      uv run task run
      # ou: uvicorn app.main:app --reload --port 8001
      ```
- [ ] Ver a documentação automática em <http://localhost:8001/docs>.

## Filosofia arquitetural

O template segue uma separação em camadas com responsabilidade única, sempre
fluindo em uma direção:

```text
api (routers + dependencies)
   ↓
services (regras de negócio)
   ↓
repositories (acesso a dados)
   ↓
models (ORM)
```

| Camada | Papel | "Porquê" |
|---|---|---|
| `app/api/routers/` | Transporte HTTP (endpoints) | Mantém a API fina; delega toda regra ao service. |
| `app/api/dependencies/` | Dependências reutilizáveis (auth, permissions, pagination, rate limit) | Autorização e validação ficam **centralizadas**, nunca inline nas rotas. |
| `app/services/` | Regras de negócio e orquestração | Testável sem a camada HTTP. |
| `app/repositories/` | Consultas e persistência | Esconde detalhes do ORM do resto da aplicação. |
| `app/models/` | Estrutura das tabelas | Representa o banco, não regras de uso. |
| `app/schemas/` | Validação/serialização Pydantic | Contrato de entrada/saída da API. |
| `app/core/` | Config, security, exceptions, logging | Transversal; sem dependência de domínio. |

Princípios transversais:

- **Erros centralizados:** toda resposta de erro usa `AppError` e o handler
  em `app/core/error_handlers.py` com o formato `{error, status, path,
  method}` (ver [docs/error-codes.md](error-codes.md)).
- **Autorização centralizada:** rotas não implementam checagens ad-hoc; elas
  compõem `get_current_user`, `require_role` e `check_permission` (ver
  [docs/rbac-model.md](rbac-model.md)).
- **Config por ambiente:** `ENVIRONMENT` seleciona o perfil de `Settings`
  (ver [docs/environment-variables.md](environment-variables.md)).
- **Banco async SQLAlchemy 2.0 + Alembic + seeds idempotentes**
  (ver [docs/migrations-seeds-tests.md](migrations-seeds-tests.md)).

## Estrutural vs. específico do domínio

### Estrutural — manter em qualquer novo projeto

- `app/core/` — `config.py` (Settings), `security.py` (hash + JWT),
  `exceptions.py`, `logging.py`, `security_logger.py`, rate limiter.
- `app/db/` — `base.py`, `session.py`, `init_db.py` (o *padrão* do seed; os
  dados seedados são específicos do domínio).
- `app/api/dependencies/` — `database.py`, `auth.py`, `permissions.py`,
  `pagination.py`, `rate_limit.py`.
- `app/repositories/base.py` — repositório genérico (`get`, `list`, `create`,
  `update`, `delete`).
- `app/utils/` — helpers transversais (datas, tokens opacos).
- Estrutura de testes (`tests/`, `tests/test_services/`,
  `tests/test_repositories/`, `tests/test_integration/`) e `conftest.py`.
- Alembic (`alembic.ini`, `migrations/`), `pyproject.toml`, `.env.example`,
  `docker-compose.yml` (PostgreSQL).

### Específico do domínio — adaptar/remover num novo projeto

- Entidades e fluxos atuais: `users`, `auth` (login/refresh/logout/reset),
  login social Google — mantenha o *padrão*, troque o *conteúdo*.
- Roles e permissões em `DEFAULT_ROLES`/`DEFAULT_PERMISSIONS`
  (`admin`/`user`, `users:*`, `roles:*`).
- Templates de e-mail em `app/templates/emails/` com conteúdo do domínio.
- Regras de negócio dos services atuais.
- Schemas de request/response atuais (`app/schemas/user.py`, `auth.py`).
- `APP_DESCRIPTION` e metadados em `app/core/config.py`.

## Passo a passo — adaptar para um novo domínio

1. **Renomear o pacote raiz (`app`), se necessário.** Ajuste os imports,
   `app/main.py`, `app/api/router.py`, `alembic.ini`, `pyproject.toml`
   (`pythonpath`) e o `alembic`/`env.py` que referencia `app.models`.
2. **Remover/renomear entidades de exemplo.** Apague models, schemas,
   repositories, services e routers do domínio antigo, e as migrações
   correspondentes (ou gere um `downgrade base` + novo autogenerate).
3. **Ajustar `.env.example` e `README.md`** para o novo domínio
   (metadados, e-mail de admin, etc.).
4. **Redefinir roles/permissões iniciais** em `DEFAULT_ROLES`/
   `DEFAULT_PERMISSIONS` em `app/db/init_db.py`.
5. **Atualizar templates de e-mail** e documentação específica.

## Como adicionar uma nova entidade de domínio

Siga o fluxo na ordem, reutilizando as estruturas existentes:

1. **Model** — crie `app/models/<entidade>.py` (classe `Base` do
   `app/db/base.py`).
2. **Schema** — crie `app/schemas/<entidade>.py` (schemas de criação,
   leitura, atualização).
3. **Migration** — gere e revise:
   ```bash
   uv run alembic revision --autogenerate -m "add <entidade>"
   uv run alembic upgrade head
   ```
4. **Repository** — herde de `BaseRepository` em
   `app/repositories/base.py`:
   ```python
   class ItemRepository(BaseRepository[Item]):
       def __init__(self, session: AsyncSession) -> None:
           super().__init__(session, model=Item)
   ```
5. **Service** — implemente as regras de negócio em `app/services/`.
6. **Router** — crie `app/api/routers/<entidade>.py` (prefixo e tags).
7. **Registrar** — importe e inclua o router em `app/api/router.py`.
8. **Testes** — adicione testes de service, repository e endpoint
   (ver [docs/testing-conventions.md](testing-conventions.md)).

## Como adicionar uma nova rota protegida

Reutilize as dependências prontas — nunca escreva checagens inline:

```python
from typing import Annotated
from fastapi import APIRouter, Depends

from app.api.dependencies.auth import CurrentUserDep
from app.api.dependencies.permissions import require_role, check_permission
from app.models.user import User

router = APIRouter(prefix='/items', tags=['items'])


@router.get('/my-items')
async def my_items(user: CurrentUserDep) -> list[dict]:
    """Qualquer utilizador autenticado."""
    ...


@router.post('/admin/items')
async def create_item(
    _: Annotated[User, Depends(require_role('admin'))],
) -> dict:
    """Só admins."""
    ...


@router.delete('/items/{item_id}')
async def delete_item(
    _: Annotated[User, Depends(check_permission('items:delete'))],
) -> None:
    """Só quem tem a permissão granular items:delete."""
    ...
```

Decisões de escolha entre `require_role` e `check_permission`:
[docs/rbac-model.md](rbac-model.md).

## Referências

- Variáveis de ambiente: [docs/environment-variables.md](environment-variables.md)
- Fluxo de autenticação: [docs/authentication-flow.md](authentication-flow.md)
- Modelo RBAC: [docs/rbac-model.md](rbac-model.md)
- Migrações, seeds e testes: [docs/migrations-seeds-tests.md](migrations-seeds-tests.md)
- Convenções de teste: [docs/testing-conventions.md](testing-conventions.md)
