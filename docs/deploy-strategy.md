# Deploy Strategy & Readiness

## Overview

This document defines the deployment strategy for the Auth API, covering infrastructure, environments, CI/CD pipeline, rollback procedures, and operational runbooks.

---

## Infrastructure

### Production Requirements

| Component | Specification | Notes |
|-----------|---------------|-------|
| **PostgreSQL** | 16+ (managed: RDS, Cloud SQL, Neon, etc.) | `postgresql+asyncpg://` |
| **Redis** | 7+ (managed: ElastiCache, Memorystore, Upstash) | `redis://` for rate limiter, cache, sessions |
| **Container Runtime** | Docker / containerd / Kubernetes | Multi-arch images (amd64/arm64) |
| **Load Balancer** | HTTPS termination, health checks | Traefik, NGINX, ALB, Cloud Run |
| **DNS** | Wildcard or explicit subdomains | `api.example.com` |

### Optional / Future

- **Object Storage**: S3/GCS for static assets, backups
- **Message Broker**: RabbitMQ/Kafka for async events (EPIC-11)
- **Distributed Tracing**: Jaeger/Tempo for request tracing

---

## Environments

| Environment | Purpose | Compose File | Infra | Secrets |
|-------------|---------|--------------|-------|---------|
| **local** | Dev loop, hot reload | `docker-compose.local.yml` | Local Postgres, Redis, Mailhog | `secrets/*.txt` (dev values) |
| **staging** | Integration testing, preview | `docker-compose.staging.yml` | Staging DB, Redis (managed) | Docker secrets / GitHub Environments |
| **production** | Live traffic | `docker-compose.prod.yml` | Prod DB (HA), Redis (cluster) | Vault / GitHub Environments / Sealed Secrets |

### Environment Differences

| Setting | local | staging | production |
|---------|-------|---------|------------|
| `ENVIRONMENT` | development | staging | production |
| `DEBUG` | true | false | false |
| `CORS_ALLOWED_ORIGINS` | localhost | staging.example.com | example.com, www.example.com |
| `APP_BASE_URL` | http://localhost:8000 | https://staging-api.example.com | https://api.example.com |
| `DB_ENGINE` | postgresql | postgresql | postgresql |
| `REDIS_URL` | redis://redis:6379/0 | redis://redis:6379/0 | redis://redis:6379/0 |
| `SMTP_HOST` | mailhog | smtp.staging | smtp.prod |
| Replicas | 1 | 1 | 2+ |
| Resources | dev limits | staged limits | prod limits + rolling update |

---

## Secrets Management

### Classification

| Category | Variables | Storage |
|----------|-----------|---------|
| **App Secrets** | `SECRET_KEY`, `REFRESH_SECRET_KEY` | Vault / GitHub Environment secrets |
| **Database** | `DB_PASSWORD`, `DB_USER`, `DB_NAME` | Vault / Cloud SQL secrets |
| **SMTP** | `SMTP_PASSWORD` | Vault / GitHub Environment |
| **OAuth** | `GOOGLE_CLIENT_SECRET` | Vault / GitHub Environment |
| **Non-sensitive** | `DB_HOST`, `DB_PORT`, `CORS_*`, `APP_BASE_URL` | `.env` / compose `environment` |

### Local Development

```bash
# Generate local secrets
make secrets-gen
# Edit secrets/*.txt with real values for staging/prod testing
```

### CI/CD (GitHub Actions)

- Store production secrets in **GitHub Environments** (`production`, `staging`)
- Use `secrets` context in workflows
- Never commit secrets to repo (`.gitignore` covers `secrets/`)

---

## CI/CD Pipeline

### Gates (all must pass)

1. **Lint**: `ruff check .` (style, complexity, bugs)
2. **Format**: `ruff format --check .` (consistent formatting)
3. **Type Check**: `mypy app/` (0 errors)
4. **Tests**: `pytest --cov` (357 passed, ≥85% coverage)
5. **Coverage**: HTML artifact uploaded, threshold 85%
6. **Migrations**: `alembic heads` (single), `upgrade head`, `check`, `downgrade base && upgrade head`
7. **Smoke Test**: `/api/health` returns `{"status":"ok"}`

### Workflows

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `lint.yml` | PR, push main | Code style |
| `format.yml` | PR, push main | Formatting |
| `tests.yml` | PR, push main | Test suite + Postgres |
| `coverage.yml` | PR, push main | Coverage gate + artifact |
| `migrations.yml` | PR, push main | Migration integrity |
| `type-check.yml` | PR, push main | Static types |
| `smoke.yml` | PR, push main | App boots + health |
| `build-deploy.yml` | `workflow_dispatch` | Build image, deploy to env |

### Branch Protection (main)

- Required status checks: all 7 workflows above
- Required PR reviews: 1 approval
- Dismiss stale reviews on new commits
- Enforce admins: true
- No force pushes, no deletions

---

## Deployment Procedures

### Staging (manual trigger)

```bash
# Via GitHub Actions UI
workflow_dispatch:
  environment: staging
  tag: optional  # defaults to SHA
```

Or locally:
```bash
./scripts/compose.sh staging up -d
```

### Production (manual trigger)

```bash
# Via GitHub Actions UI (requires approval)
workflow_dispatch:
  environment: production
  tag: v1.2.3  # semantic version tag
```

### Image Building

```dockerfile
# Multi-stage: build -> runtime
FROM python:3.14-slim AS builder
# ... uv sync --frozen

FROM python:3.14-slim AS runtime
# ... copy from builder, uv sync --frozen --no-dev
```

Images pushed to `ghcr.io/{repo}:<sha>` and `ghcr.io/{repo}:<tag>`.

---

## Rollback Plan

| Scenario | Action |
|----------|--------|
| **Bad deploy (app)** | `gh workflow run build-deploy.yml -f environment=production -f tag=<previous-sha>` |
| **Bad migration** | `alembic downgrade -1` (test in staging first) |
| **Config error** | Revert env vars / secrets, restart app |
| **DB issue** | Restore from snapshot (RDS/Cloud SQL point-in-time) |

### Migration Reversibility

- All migrations should have `downgrade()` implemented
- Test `alembic downgrade -1` in staging before production
- Destructive changes (column drops) require multi-step deploy:
  1. Deploy code compatible with old + new schema
  2. Run migration
  3. Deploy code using new schema only

---

## Observability

| Signal | Endpoint / Tool | Alert Threshold |
|--------|-----------------|-----------------|
| **Health** | `GET /api/health` | 5xx > 1% / 5m |
| **Metrics** | `GET /metrics` (Prometheus) | latency p99 > 2s |
| **Logs** | JSON stdout → Loki/Elastic | error rate > 5% |
| **DB** | `pg_stat_activity` | connections > 80% pool |
| **Redis** | `INFO memory` | used > 80% maxmemory |

### Key Dashboards

- **RED**: Rate, Errors, Duration (per endpoint)
- **USE**: Utilization, Saturation, Errors (DB, Redis, CPU, Mem)

---

## Runbooks

### App Won't Start

1. Check `docker compose logs app`
2. Verify secrets exist: `docker secret ls`
3. Check DB connectivity: `docker compose exec app pg_isready -h db`
4. Check Redis: `docker compose exec app redis-cli ping`

### High Latency / 5xx

1. Check `/metrics` for `http_request_duration_seconds` spike
2. Check DB: `pg_stat_activity` for long queries
3. Check Redis: `INFO stats` for hit rate, memory
4. Scale app replicas if CPU saturated

### Rate Limiter Blocking Legitimate Traffic

1. Check Redis keys: `redis-cli KEYS "ratelimit:*"`
2. Tune `RATE_LIMIT_*` env vars
3. Verify client IP detection (proxy headers)

### Migration Stuck / Failed

1. Check `alembic current` and `alembic heads`
2. If partial: `alembic stamp head` (if safe) or manual SQL fix
3. Never run migrations concurrently (use advisory lock)

---

## Future Considerations

- **Kubernetes**: Helm chart with Deployment, Service, Ingress, ConfigMap, Secret
- **Blue/Green**: Two namespaces, switch Ingress
- **Canary**: Istio/Linkerd traffic split
- **Serverless**: Cloud Run / Fly.io / Railway for auto-scaling
- **Database**: Read replicas, connection pooling (PgBouncer)

---

## Quick Reference

```bash
# Local dev
make local-up
make local-logs

# Staging deploy
gh workflow run build-deploy.yml -f environment=staging

# Prod deploy (with tag)
gh workflow run build-deploy.yml -f environment=production -f tag=v1.0.0

# Rollback
gh workflow run build-deploy.yml -f environment=production -f tag=<prev-sha>

# View logs
./scripts/compose.sh prod logs -f app
```