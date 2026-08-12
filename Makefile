.PHONY: help local-up local-down local-logs local-ps staging-up staging-down staging-logs staging-swarm-up staging-swarm-down staging-swarm-logs staging-swarm-ps prod-up prod-down prod-logs secrets-gen test lint

STAGING_STACK := auth_staging
STAGING_IMAGE := ghcr.io/${GITHUB_REPOSITORY:-ndondaniel2020/auth}:staging

help:
	@echo "Auth API - Docker Compose Commands"
	@echo ""
	@echo "Local development:"
	@echo "  make local-up              Start local environment (with mailhog, hot reload)"
	@echo "  make local-down            Stop local environment"
	@echo "  make local-logs            Follow logs"
	@echo "  make local-ps              Show running containers"
	@echo ""
	@echo "Staging (docker compose):"
	@echo "  make staging-up            Deploy to staging (requires secrets in Docker/Environment)"
	@echo "  make staging-down          Stop staging"
	@echo "  make staging-logs          Follow logs"
	@echo ""
	@echo "Staging (Docker Swarm):"
	@echo "  make staging-swarm-up      Init swarm, create secrets, build image, deploy stack"
	@echo "  make staging-swarm-down    Remove swarm stack (secrets persist)"
	@echo "  make staging-swarm-logs    Follow swarm service logs"
	@echo "  make staging-swarm-ps      Show swarm services"
	@echo ""
	@echo "Production:"
	@echo "  make prod-up               Deploy to production"
	@echo "  make prod-down             Stop production"
	@echo "  make prod-logs             Follow logs"
	@echo ""
	@echo "Other:"
	@echo "  make secrets-gen           Generate secret templates in secrets/"
	@echo "  make test                  Run tests locally"
	@echo "  make lint                  Run ruff + mypy"

local-up:
	./scripts/compose.sh local up -d --build

local-down:
	./scripts/compose.sh local down

local-logs:
	./scripts/compose.sh local logs -f

local-ps:
	./scripts/compose.sh local ps

staging-up:
	./scripts/compose.sh staging up -d

staging-down:
	./scripts/compose.sh staging down

staging-logs:
	./scripts/compose.sh staging logs -f

staging-swarm-up:
	@echo "==> Initializing Docker Swarm (if needed)..."
	@docker info --format '{{.Swarm.LocalNodeState}}' | grep -q active || docker swarm init
	@echo "==> Creating secrets (skipping existing)..."
	@for secret in app_secret_key app_refresh_secret_key db_user db_password db_name smtp_password google_client_id google_client_secret; do \
		docker secret create $$secret secrets/$$secret.txt 2>/dev/null || true; \
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
	@docker service logs -f "$$(docker service ls --filter 'name=$(STAGING_STACK)_app' --format '{{.Name}}')" 2>&1 || \
		echo "No running services. Run 'make staging-swarm-up' first."

staging-swarm-ps:
	@docker service ls --filter "name=$(STAGING_STACK)"

prod-up:
	./scripts/compose.sh prod up -d

prod-down:
	./scripts/compose.sh prod down

prod-logs:
	./scripts/compose.sh prod logs -f

secrets-gen:
	@echo "Generating secret templates..."
	@mkdir -p secrets
	@openssl rand -base64 32 > secrets/app_secret_key.txt 2>/dev/null || echo "your-secret-key-here" > secrets/app_secret_key.txt
	@openssl rand -base64 32 > secrets/app_refresh_secret_key.txt 2>/dev/null || echo "your-refresh-secret-key-here" > secrets/app_refresh_secret_key.txt
	@echo "auth_user" > secrets/db_user.txt
	@openssl rand -base64 24 > secrets/db_password.txt 2>/dev/null || echo "your-db-password" > secrets/db_password.txt
	@echo "auth_db" > secrets/db_name.txt
	@openssl rand -base64 24 > secrets/smtp_password.txt 2>/dev/null || echo "your-smtp-password" > secrets/smtp_password.txt
	@echo "your-client-id.apps.googleusercontent.com" > secrets/google_client_id.txt
	@openssl rand -base64 24 > secrets/google_client_secret.txt 2>/dev/null || echo "your-google-client-secret" > secrets/google_client_secret.txt
	@echo "Secrets generated in secrets/ (edit with real values for production)"

test:
	uv run pytest -q

lint:
	uv run ruff check . && uv run ruff format --check . && uv run mypy app/
