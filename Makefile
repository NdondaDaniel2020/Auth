.PHONY: lint format run test html

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
