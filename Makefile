.PHONY: lint format run test html
.PHONY: alembic-init alembic-revision alembic-upgrade alembic-upgrade-head alembic-downgrade alembic-history alembic-current alembic-heads alembic-branches alembic-stamp alembic-show alembic-merge

all:
	uv run task run

lint:
	uv run task lint

format:
	uv run task format

run:
	uv run task runserver

test:
	uv run task test

test-dev:
	uv run task test-dev

test-pg:
	uv run task test-pg

html:
	uv run task html


REV ?= head
MSG ?= "migration"

alembic-init:
	uv run alembic init migrations

alembic-revision:
	uv run alembic revision --autogenerate -m $(MSG)

alembic-upgrade-head:
	uv run alembic upgrade head

alembic-upgrade:
	uv run alembic upgrade $(REV)

alembic-downgrade:
	uv run alembic downgrade $(REV)

alembic-history:
	uv run alembic history --verbose

alembic-current:
	uv run alembic current

alembic-heads:
	uv run alembic heads

alembic-branches:
	uv run alembic branches

alembic-stamp:
	uv run alembic stamp $(REV)

alembic-show:
	uv run alembic show $(REV)

alembic-merge:
	uv run alembic merge -m $(MSG) $(REV)

compose:
	docker compose up -d --build
