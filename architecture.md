meu_projeto/
├── app/
│   ├── __init__.py
│   ├── main.py                            # Cria a instância FastAPI, monta routers e static
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py                      # Settings (pydantic-settings): DB, SMTP, JWT, etc.
│   │   ├── security.py                    # Hash de senha, criação/validação de JWT
│   │   └── logging.py                     # Configuração de logs
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── router.py                      # Agrega todas as rotas da v1
│   │   ├── dependencies/                  # Dependências HTTP (Depends) — uma por responsabilidade
│   │   │   ├── __init__.py
│   │   │   ├── database.py                # get_db
│   │   │   ├── auth.py                    # get_current_user, get_current_active_superuser
│   │   │   ├── permissions.py             # require_role, check_permission
│   │   │   └── pagination.py              # get_pagination_params
│   │   └── routers/
│   │       ├── __init__.py
│   │       ├── auth.py
│   │       ├── users.py
│   │       └── items.py
│   │
│   ├── models/                            # ORM (SQLAlchemy) — representação das tabelas
│   │   ├── __init__.py
│   │   ├── user.py
│   │   └── item.py
│   │
│   ├── schemas/                           # Pydantic — validação de entrada/saída da API
│   │   ├── __init__.py
│   │   ├── user.py
│   │   └── item.py
│   │
│   ├── repositories/                      # Acesso a dados (queries) — abstrai o ORM
│   │   ├── __init__.py
│   │   ├── base.py                        # Repositório genérico (get, create, update, delete)
│   │   ├── user_repository.py
│   │   └── item_repository.py
│   │
│   ├── services/                          # Regras de negócio — usa repositories
│   │   ├── __init__.py
│   │   ├── user_service.py
│   │   ├── item_service.py
│   │   └── email_service.py               # Monta e envia e-mails (usa templates/)
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py                        # Base declarativa do SQLAlchemy
│   │   ├── session.py                     # Engine + SessionLocal
│   │   └── init_db.py                     # Seed inicial de dados
│   │
│   ├── templates/
│   │   └── emails/
│   │       ├── base_email.html            # Layout reutilizável (header/footer)
│   │       ├── account_created.html
│   │       └── password_reset.html
│   │
│   ├── static/                            # Arquivos fixos servidos direto (sem processar)
│   │   ├── images/
│   │   │   └── logo.png
│   │   └── css/
│   │       └── email_styles.css
│   │
│   └── utils/
│       ├── __init__.py
│       └── helpers.py
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                        # Fixtures (db de teste, client, etc.)
│   ├── test_users.py
│   ├── test_items.py
│   └── test_repositories/
│       └── test_user_repository.py
│
├── alembic/                                # Migrações de banco
│   ├── versions/
│   └── env.py
├── alembic.ini
│
├── .env
├── .env.example
├── .gitignore
├── requirements.txt                        # ou pyproject.toml (Poetry/uv)
├── Dockerfile
├── docker-compose.yml
└── README.md
