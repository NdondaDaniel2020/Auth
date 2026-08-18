#!/usr/bin/env bash
# Script para carregar e exportar variáveis de ambiente do .env para o ambiente do SO.
# Simula com precisão o ambiente de produção (Vercel/Docker/K8s) onde as variáveis são injetadas no SO.
#
# Uso:
#   ./scripts/env_run.sh <comando> [argumentos...]
#
# Exemplos:
#   ./scripts/env_run.sh uv run alembic upgrade head
#   ./scripts/env_run.sh uv run python -m app.db.init_db
#   ./scripts/env_run.sh uv run uvicorn app.main:app

set -euo pipefail

ENV_FILE="${ENV_FILE:-.env}"

if [ ! -f "$ENV_FILE" ]; then
    echo "⚠️  Arquivo ${ENV_FILE} não encontrado. Executando comando com o ambiente atual."
    exec "$@"
fi

echo "🔐 Exportando variáveis de ambiente de ${ENV_FILE}..."

exec uv run python -c "
import os
import sys
from dotenv import load_dotenv

env_file = os.environ.get('ENV_FILE', '.env')
load_dotenv(env_file, override=True)
os.execvp(sys.argv[1], sys.argv[1:])
" "$@"
