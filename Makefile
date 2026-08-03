.PHONY: lint format run test html

all:
	uv run task run

lint:
	uv run task lint

format:
	uv run task format

run:
	uv run task runmain

runserver:
	uv run task runserver

test:
	uv run task test

html:
	uv run task html
