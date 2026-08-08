#!/usr/bin/env bash
# Usage: ./scripts/compose.sh [local|staging|prod] [up|down|logs|ps]

set -euo pipefail

ENVIRONMENT="${1:-local}"
ACTION="${2:-up}"

COMPOSE_FILES=()
case "$ENVIRONMENT" in
  local)
    COMPOSE_FILES=("-f" "docker-compose.yml" "-f" "docker-compose.local.yml")
    ;;
  staging)
    COMPOSE_FILES=("-f" "docker-compose.yml" "-f" "docker-compose.staging.yml")
    ;;
  prod|production)
    COMPOSE_FILES=("-f" "docker-compose.yml" "-f" "docker-compose.prod.yml")
    ;;
  *)
    echo "Usage: $0 [local|staging|prod] [up|down|logs|ps]"
    exit 1
    ;;
esac

echo "Environment: $ENVIRONMENT"
echo "Action: $ACTION"
echo "Compose files: ${COMPOSE_FILES[*]}"

docker compose "${COMPOSE_FILES[@]}" "$ACTION"