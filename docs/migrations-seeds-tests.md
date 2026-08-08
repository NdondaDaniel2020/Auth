# Migrações, seeds e testes

Guia operacional dos processos de banco de dados e testes da aplicação:
Alembic, seeds idempotentes e a suíte de testes automatizados. Corresponde à
issue `[EPIC-8][DOCS] Documentar migrações, seeds e testes`.

## Fluxo recomendado — setup local do zero

```bash
# 1. Subir o banco (PostgreSQL via Docker) — opcional; SQLite não precisa
docker compose up -d

# 2. Copiar as variáveis de ambiente
cp .env.example .env

# 3. Aplicar as migrações
uv run alembic upgrade head

# 4. Rodar o seed (roles, permissões e admin)
uv run python -m app.db.init_db

# 5. Rodar a suíte de testes
uv run task test

# 6. Subir a aplicação
uv run task run
```

---

## Migrações (Alembic)

O Alembic lê automaticamente o `DATABASE_URL` do ambiente local
(`.env` ou variáveis exportadas). A configuração está em `alembic.ini` e
`migrations/env.py`.

### Comandos principais

| Comando | Efeito |
|---|---|
| `uv run alembic revision --autogenerate -m "descrição"` | Gera uma nova migração a partir dos models. |
| `uv run alembic upgrade head` | Aplica todas as migrações pendentes. |
| `uv run alembic downgrade -1` | Reverte a última migração aplicada. |
| `uv run alembic downgrade base` | Reverte tudo (banco limpo). |
| `uv run alembic history --verbose` | Histórico das migrações. |
| `uv run alembic current` | Revisão atual do banco. |
| `uv run alembic heads` | Última(s) revisão(ões). |
| `uv run alembic branches` | Revisões divergentes (merge pendente). |

### Boas práticas

- **Sempre revise o arquivo autogerado** em `migrations/versions/` antes de
  aplicar, principalmente operações destrutivas (drops, alteração de
  constraints).
- **Nunca edite uma migração já aplicada em produção** — crie uma nova
  migração com as alterações.
- **Nomeie migrações de forma descritiva** (`-m "add tabela X"`).
- Se o autogenerate não capturar uma mudança (ex.: troca de tipo), escreva
  a migração manualmente e valide com `upgrade`/`downgrade` de ponta a ponta.

### Comportamento por banco

- **SQLite (dev/teste):** arquivo local `./.data/app.db` (ou `:memory:` em
  testes). Simples, mas com limitações (alterações de coluna podem exigir
  recrear a tabela — revise o autogenerate).
- **PostgreSQL (produção):** URL `postgresql+asyncpg://...`. O autogenerate
  é mais completo; use `docker compose up -d` e o host `db` dentro da rede
  do Compose.

---

## Seeds

O seed fica em `app/db/init_db.py` e é **idempotente**: pode ser executado
múltiplas vezes sem duplicar dados nem lançar erros.

### O que o seed cria

| Entidade | Valores padrão |
|---|---|
| Roles | `admin`, `user` |
| Permissões | `users:create`, `users:read`, `users:update`, `users:delete`, `roles:read`, `roles:manage` |
| Atribuições | `admin` → todas as permissões; `user` → `users:read` |
| Utilizador admin | `ADMIN_EMAIL` (default `admin@example.com`) com a role `admin` |

### Como executar

```bash
# Standalone (recomendado para CI/CD e produção)
uv run python -m app.db.init_db
```

```env
# Automático no arranque (desenvolvimento)
RUN_SEED_ON_STARTUP=true
```

> **Segurança:** altere `ADMIN_PASSWORD` antes de rodar o seed em produção.

### Quando executar

| Contexto | Método recomendado |
|---|---|
| Desenvolvimento local | `RUN_SEED_ON_STARTUP=true` no `.env` |
| CI/CD (staging/produção) | `uv run python -m app.db.init_db` após `alembic upgrade head` |
| Reset de base local | `alembic downgrade base && alembic upgrade head && python -m app.db.init_db` |

### Como estender o seed

Para adicionar uma nova permissão ou role, edite `DEFAULT_PERMISSIONS` e
`DEFAULT_ROLES` em `app/db/init_db.py`, seguindo o padrão
`("recurso:ação", "descrição", ["role1", "role2"])`. O seed usa *get-or-create*
(consulta antes de inserir) e `ON CONFLICT DO NOTHING` nas tabelas de
associação — por isso é seguro re-executar.

---

## Testes

### Dependências

As dependências de teste estão no grupo `dev` do `pyproject.toml`
(gerenciado via `uv`). Instale tudo com:

```bash
uv sync --group dev
```

### Como rodar

| Comando | O quê |
|---|---|
| `uv run task lint` | Ruff (linte + formato). |
| `uv run task test` | Suíte completa com cobertura (`pytest -s -x --cov=app -vv`) e gera `htmlcov/`. |
| `uv run pytest -m integration` | Apenas testes de integração (jornadas ponta a ponta). |
| `uv run pytest -m "not integration"` | Apenas os demais (rápidos). |
| `uv run pytest tests/test_auth_login.py -k "test_login_success"` | Arquivo ou teste específico. |

### Cobertura

- A suíte roda com `--cov=app`; o relatório HTML é gerado em `htmlcov/`
  (`uv run task html` abre no navegador).
- Configuração de cobertura em `pyproject.toml` (`[tool.coverage]`).

### Isolamento do banco de teste

- Cada teste usa um **SQLite isolado por teste** (`tmp_path`), sem estado
  compartilhado entre testes — a suíte não afeta dados de dev/produção.
- Camadas de service/repository usam o `isolated_session_factory`
  diretamente; a camada HTTP usa `TestClient` com `get_db` sobrescrito.
- Integrações externas (e-mail, relógio) são mockadas via `monkeypatch`;
  senha e tokens usam o fluxo real.

Convenções detalhadas: [docs/testing-conventions.md](testing-conventions.md).

---

## Referências

- Variáveis de ambiente (comandos e defaults): [docs/environment-variables.md](environment-variables.md)
- Convenções de teste: [docs/testing-conventions.md](testing-conventions.md)
- Fluxo de autenticação: [docs/authentication-flow.md](authentication-flow.md)
