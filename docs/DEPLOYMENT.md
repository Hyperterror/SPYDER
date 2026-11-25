# Production Deployment Guide

## 1. Prerequisites
- Docker & Docker Compose (`v2+`)
- PostgreSQL 15+, Redis 7+, MinIO, Neo4j 5+ (all managed via `docker-compose.prod.yml`)
- Separate non-default 32+ character secrets for `JWT_SECRET_KEY` and `AUDIT_SIGNING_KEY`

## 2. Production Configuration
Copy `.env.example` to `.env` and populate all required secrets:
- `ENVIRONMENT=production`
- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
- `NEO4J_USER`, `NEO4J_PASSWORD`
- `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`
- `JWT_SECRET_KEY` (must not match dev default)
- `AUDIT_SIGNING_KEY` (must not match `JWT_SECRET_KEY` or dev default)
- `COOKIE_SECURE=true`, `ALLOW_BODY_REFRESH=false`
- `CORS_ORIGINS=https://your-investigator-domain` (no `*` wildcards)
- `NEXT_PUBLIC_API_URL=https://api.your-investigator-domain`
- `NEXT_PUBLIC_SHOW_DEMO_HINT=false`

`validate_security_configuration` enforces fail-fast startup when `ENVIRONMENT=production` detects weak/default secrets or wildcard CORS.

## 3. Starting the Production Stack
```bash
docker compose -f docker-compose.prod.yml up --build -d
```
The production compose topology:
- Isolates `postgres`, `redis`, `neo4j`, and `minio` on internal bridge network `spyder_data` with zero public host ports.
- Runs `alembic upgrade head` prior to Uvicorn startup (`--workers 2`, no `--reload`) inside a non-root container user (`spyder`).
- Runs a dedicated Celery worker container (`spyder_prod_worker`).

## 4. Verification & Health Checks
- Process liveness: `GET /health/live` -> `{"status": "alive"}`
- Dependency readiness: `GET /health/ready` -> verifies PostgreSQL (`SELECT 1`), MinIO/Storage, Redis (`ping`), and optional degraded-safe Neo4j status.
- Validation status on host: `docker compose -f docker-compose.yml config -q` and `docker compose -f docker-compose.prod.yml config -q` both exited `0`. Full multi-container live Docker daemon boot (`up -d`) was not executed in this offline workspace and should be smoke-tested in the target environment.
