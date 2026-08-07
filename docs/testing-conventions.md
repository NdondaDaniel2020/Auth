# Convenções de teste

Este documento define como os testes são organizados e quando usar banco de
teste real vs. mocks, garantindo consistência entre os arquivos da suíte.

## Estrutura

| Pasta | Camada testada | Exemplos |
|---|---|---|
| `tests/` (raiz) | Comportamento via HTTP (endpoints) | `test_auth_register.py`, `test_user_roles.py` |
| `tests/test_services/` | Regras de negócio (sem camada HTTP) | `test_user_service.py`, `test_auth_service.py` |
| `tests/test_repositories/` | Acesso a dados (CRUD, constraints) | `test_user_repository.py`, `test_refresh_token_repository.py` |
| `tests/test_integration/` | Jornadas ponta a ponta (múltiplos endpoints em sequência) | `test_auth_journey.py`, `test_rbac_journey.py` |

Arquivos de raiz com nomes de fluxo (ex: `test_auth_login.py`) seguem as
issues de EPIC-7 e completam a cobertura de cada fluxo via API.

## Banco real vs. mocks

- **Banco de teste real (padrão):** a grande maioria dos testes usa o
  `isolated_session_factory` (SQLite isolado por teste) diretamente (camadas
  de service/repository) ou via `TestClient` com `get_db` sobrescrito
  (camada HTTP). Cada teste recebe um banco novo (`tmp_path`), sem estado
  compartilhado.
- **`run_in_isolated_db`:** usado para correr uma coroutine contra um engine
  separado no mesmo arquivo SQLite (por exemplo, para *seed* de dados antes de
  uma requisição HTTP), porque fixtures `asyncio` rodam em outro event loop.
- **Mocks:** apenas para integrações externas sem efeito local — envio de
  e-mails (`monkeypatch` em `email_service`) e relógio (parâmetro `now` dos
  rate limiters). Nunca mockar `hash_password`/`verify_password`: os testes
  devem validar o fluxo real ponta a ponta.
- **Senha padrão de testes:** `T3st!Passw0rd` (atende à política de senha
  forte). Seed direto no banco usa `hash_password(...)`.

## Isolamento

- Cada teste cria seus próprios dados (usuários, roles, tokens); não há
  dependência de ordem de execução.
- Fixture autouse `_clear_rate_limiter` zera os contadores de rate limit
  antes e depois de cada teste.
- Tokens JWT são gerados por `create_access_token({'sub': ...})` /
  `create_refresh_token(...)` da aplicação — nunca tokens fixos.

## Rodando os testes

```bash
uv run task lint      # ruff
uv run task test      # suíte completa com cobertura
uv run pytest -m integration  # apenas os testes de integração
```
