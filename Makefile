.DEFAULT_GOAL := help

.PHONY: help \
	local-up local-down local-logs local-ps \
	staging-up staging-down staging-logs staging-ps \
	staging-swarm-up staging-swarm-down staging-swarm-logs staging-swarm-ps \
	prod-up prod-down prod-logs prod-ps \
	secrets-gen test lint container fclean

STAGING_STACK := auth_staging
STAGING_IMAGE := ghcr.io/${GITHUB_REPOSITORY:-ndondaniel2020/auth}:staging

# Colors
CYAN  := \033[36m
GREEN := \033[32m
YELLOW:= \033[33m
BOLD  := \033[1m
RESET := \033[0m

help:
	@echo "$(BOLD)Auth API - Makefile Commands$(RESET)"
	@echo ""
	@echo "$(CYAN)Local Development:$(RESET)"
	@echo "  $(GREEN)make local-up$(RESET)              Start local environment (mailhog, hot reload)"
	@echo "  $(GREEN)make local-down$(RESET)            Stop local environment"
	@echo "  $(GREEN)make local-logs$(RESET)            Follow local container logs"
	@echo "  $(GREEN)make local-ps$(RESET)              Show running local containers"
	@echo ""
	@echo "$(CYAN)Staging (Docker Compose):$(RESET)"
	@echo "  $(GREEN)make staging-up$(RESET)            Deploy staging environment"
	@echo "  $(GREEN)make staging-down$(RESET)          Stop staging environment"
	@echo "  $(GREEN)make staging-logs$(RESET)          Follow staging logs"
	@echo "  $(GREEN)make staging-ps$(RESET)            Show staging containers"
	@echo ""
	@echo "$(CYAN)Staging (Docker Swarm):$(RESET)"
	@echo "  $(GREEN)make staging-swarm-up$(RESET)      Init swarm, create secrets, build image, deploy stack"
	@echo "  $(GREEN)make staging-swarm-down$(RESET)    Remove swarm stack"
	@echo "  $(GREEN)make staging-swarm-logs$(RESET)    Follow swarm service logs"
	@echo "  $(GREEN)make staging-swarm-ps$(RESET)      Show swarm services"
	@echo ""
	@echo "$(CYAN)Production:$(RESET)"
	@echo "  $(GREEN)make prod-up$(RESET)               Deploy to production"
	@echo "  $(GREEN)make prod-down$(RESET)             Stop production environment"
	@echo "  $(GREEN)make prod-logs$(RESET)             Follow production logs"
	@echo "  $(GREEN)make prod-ps$(RESET)               Show production containers"
	@echo ""
	@echo "$(CYAN)Testing & Quality:$(RESET)"
	@echo "  $(GREEN)make test$(RESET)                  Run tests locally (pytest)"
	@echo "  $(GREEN)make lint$(RESET)                  Run linters (ruff + mypy)"
	@echo ""
	@echo "$(CYAN)Standalone Containers:$(RESET)"
	@echo "  $(GREEN)make container$(RESET)             Start standalone Redis + Postgres containers"
	@echo ""
	@echo "$(CYAN)Utilities & Maintenance:$(RESET)"
	@echo "  $(GREEN)make secrets-gen$(RESET)           Generate secret templates in secrets/ (preserves existing)"
	@echo "  $(GREEN)make fclean$(RESET)                Remove all Docker containers, images, volumes, networks"
	@echo ""

local-up: secrets-gen
	./scripts/compose.sh local up -d --build

local-down:
	./scripts/compose.sh local down

local-logs:
	./scripts/compose.sh local logs -f

local-ps:
	./scripts/compose.sh local ps

staging-up: secrets-gen
	./scripts/compose.sh staging up -d

staging-down:
	./scripts/compose.sh staging down

staging-logs:
	./scripts/compose.sh staging logs -f

staging-ps:
	./scripts/compose.sh staging ps

staging-swarm-up: secrets-gen
	@echo "==> Initializing Docker Swarm (if needed)..."
	@docker info --format '{{.Swarm.LocalNodeState}}' | grep -q active || docker swarm init
	@echo "==> Creating secrets (skipping existing)..."
	@for secret in app_secret_key app_refresh_secret_key db_user db_password db_name smtp_password google_client_id google_client_secret; do \
		if [ -f secrets/$$secret.txt ]; then \
			docker secret create $$secret secrets/$$secret.txt 2>/dev/null || true; \
		fi \
	done
	@echo "==> Building image $(STAGING_IMAGE)..."
	docker build -t $(STAGING_IMAGE) -f Dockerfile .
	@echo "==> Deploying stack $(STAGING_STACK)..."
	docker stack deploy -c docker-compose.staging.yml $(STAGING_STACK)
	@echo "==> Done. Run 'make staging-swarm-logs' to follow logs."

staging-swarm-down:
	docker stack rm $(STAGING_STACK)
	@echo "Stack removed. Secrets still exist — remove with: docker secret ls"

staging-swarm-logs:
	@docker service logs -f $(STAGING_STACK)_app 2>/dev/null || \
		docker service logs -f "$$(docker service ls --filter 'name=$(STAGING_STACK)' --format '{{.Name}}' | head -n 1)" 2>/dev/null || \
		echo "No running services. Run 'make staging-swarm-up' first."

staging-swarm-ps:
	@docker service ls --filter "name=$(STAGING_STACK)"

prod-up:
	./scripts/compose.sh prod up -d

prod-down:
	./scripts/compose.sh prod down

prod-logs:
	./scripts/compose.sh prod logs -f

prod-ps:
	./scripts/compose.sh prod ps

secrets-gen:
	@echo "Checking/Generating secret templates in secrets/..."
	@mkdir -p secrets
	@[ -f secrets/app_secret_key.txt ] || (openssl rand -base64 32 > secrets/app_secret_key.txt 2>/dev/null || echo "your-secret-key-here" > secrets/app_secret_key.txt)
	@[ -f secrets/app_refresh_secret_key.txt ] || (openssl rand -base64 32 > secrets/app_refresh_secret_key.txt 2>/dev/null || echo "your-refresh-secret-key-here" > secrets/app_refresh_secret_key.txt)
	@[ -f secrets/db_user.txt ] || echo "auth_user" > secrets/db_user.txt
	@[ -f secrets/db_password.txt ] || (openssl rand -base64 24 > secrets/db_password.txt 2>/dev/null || echo "your-db-password" > secrets/db_password.txt)
	@[ -f secrets/db_name.txt ] || echo "auth_db" > secrets/db_name.txt
	@[ -f secrets/smtp_password.txt ] || (openssl rand -base64 24 > secrets/smtp_password.txt 2>/dev/null || echo "your-smtp-password" > secrets/smtp_password.txt)
	@[ -f secrets/google_client_id.txt ] || echo "your-client-id.apps.googleusercontent.com" > secrets/google_client_id.txt
	@[ -f secrets/google_client_secret.txt ] || (openssl rand -base64 24 > secrets/google_client_secret.txt 2>/dev/null || echo "your-google-client-secret" > secrets/google_client_secret.txt)
	@echo "Secrets checked. Existing files were preserved."

test:
	uv run pytest -q

lint:
	uv run ruff check . && uv run ruff format --check . && uv run mypy app/

container:
	@echo "Starting Redis container..."
	@docker start redis 2>/dev/null || docker run -d --name redis -p 6379:6379 redis:7-alpine
	@echo "Starting Postgres container..."
	@docker start postgres 2>/dev/null || docker run -d --name postgres -p 5432:5432 -e POSTGRES_DB=Auth -e POSTGRES_USER=Auth -e POSTGRES_PASSWORD=Auth1234 -v postgres_data:/var/lib/postgresql/data postgres:16-alpine

fclean:
	@echo "🗑️  Removing all Docker data..."
	@if [ -n "$$(docker ps -qa)" ]; then docker stop $$(docker ps -qa) 2>/dev/null || true; fi
	@if [ -n "$$(docker ps -qa)" ]; then docker rm $$(docker ps -qa) 2>/dev/null || true; fi
	@if [ -n "$$(docker images -qa)" ]; then docker rmi -f $$(docker images -qa) 2>/dev/null || true; fi
	@if [ -n "$$(docker volume ls -q)" ]; then docker volume rm $$(docker volume ls -q) 2>/dev/null || true; fi
	@if [ -n "$$(docker network ls -q)" ]; then docker network rm $$(docker network ls -q) 2>/dev/null || true; fi
	@echo "✅ All Docker data removed!"
