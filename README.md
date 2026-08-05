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
- `CORS_ORIGINS`: origens permitidas pelo CORS.
- `SECRET_KEY`: chave usada para recursos de autenticação e segurança.
- `ALGORITHM`: algoritmo de assinatura JWT.
- `JWT_ACCESS_MINUTES` e `JWT_REFRESH_DAYS`: tempos de expiração dos tokens.

Comportamento por ambiente:

- `development`: usa defaults seguros para desenvolvimento e lê o arquivo `.env`.
- `test`: usa defaults próprios para testes e também pode ler `.env`.
- `production`: exige que `DATABASE_URL`, `CORS_ORIGINS` e `SECRET_KEY` sejam informados por variáveis de ambiente.

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

Se você trocar credenciais do container, recrie também o volume do Postgres para reaplicar `POSTGRES_USER`, `POSTGRES_PASSWORD` e `POSTGRES_DB`.
