# Deploy Readiness Checklist

## Infrastructure
- [ ] PostgreSQL 16+ provisioned (managed or self-hosted)
- [ ] Redis (if using rate limiter / caching)
- [ ] Object storage for static files (if applicable)

## Environment Variables
- [ ] `ENVIRONMENT=production`
- [ ] `DATABASE_URL=postgresql+asyncpg://...` (or DB_* parts)
- [ ] `SECRET_KEY` (strong, unique, rotated)
- [ ] `REFRESH_SECRET_KEY` (strong, unique)
- [ ] `CORS_ALLOWED_ORIGINS` (comma-separated, no wildcards with credentials)
- [ ] `APP_BASE_URL` (public HTTPS URL)
- [ ] SMTP settings if emails enabled: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`
- [ ] Google OAuth settings if enabled: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`

## Database
- [ ] `alembic upgrade head` succeeds against target DB
- [ ] Seed data: `RUN_SEED_ON_STARTUP=true` on first deploy (creates admin user)

## Security
- [ ] HTTPS enforced (reverse proxy / load balancer)
- [ ] Rate limits configured per endpoint
- [ ] `CORS_ALLOW_CREDENTIALS=false` if origins use wildcard
- [ ] Secrets stored in vault / GitHub Environments (not .env)

## Observability
- [ ] Health endpoint `/api/health` returns 200
- [ ] Logging to stdout/stderr (JSON preferred)
- [ ] Metrics endpoint (if Prometheus)
- [ ] Alerting on 5xx / high latency

## CI/CD Gates (all must pass)
- [ ] Ruff lint
- [ ] Ruff format
- [ ] Test suite (357 passed, 89% coverage)
- [ ] Coverage >= 85%
- [ ] Migrations: single head, no drift, downgrade/re-upgrade works
- [ ] Mypy type check (0 errors)
- [ ] Smoke test `/api/health` passes

## Rollback Plan
- [ ] Previous image tag recorded
- [ ] `alembic downgrade -1` tested (if migrations are reversible)
- [ ] Deployment script supports rollback
