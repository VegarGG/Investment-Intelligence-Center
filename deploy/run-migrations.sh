#!/usr/bin/env bash
#
# IIC v2.5 — apply Postgres role bootstrap + alembic migrations.
#
# Idempotent: re-running on a fully-migrated DB is a no-op.
#
# Steps:
#   1. Wait for the postgres container to be healthy.
#   2. Run init-roles.sql with the generated app/ro/migration passwords.
#   3. Run `alembic upgrade head` from a one-off python:3.12-slim container
#      that bind-mounts the repo and joins the compose network.
#
# Usage:
#   bash deploy/run-migrations.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

POSTGRES_ENV="${REPO_ROOT}/.deploy/postgres.env"
if [[ ! -f "${POSTGRES_ENV}" ]]; then
  echo "Missing ${POSTGRES_ENV}. Did bootstrap-secrets.sh run?" >&2
  exit 1
fi
# shellcheck disable=SC1090
source "${POSTGRES_ENV}"

POSTGRES_USER_VAL="${POSTGRES_USER:-iic}"
POSTGRES_DB_VAL="${POSTGRES_DB:-iic}"

# Sanity check: can we talk to docker? If not, fail with a useful hint
# instead of a confusing error from the next docker compose call.
if ! docker info >/dev/null 2>&1; then
  echo "ERROR: cannot reach the docker daemon as $(id -un)." >&2
  echo "       If you just ran setup.sh, log out + log back in (or run" >&2
  echo "       'newgrp docker' in this shell) and re-run 'make migrate'." >&2
  exit 1
fi

# Resolve compose project name (matches the dir name by default).
PROJECT_NAME="$(basename "${REPO_ROOT}" | tr -c '[:alnum:]_-' '_' | tr '[:upper:]' '[:lower:]')"
NETWORK="${PROJECT_NAME}_default"

echo "==> Waiting for Postgres to be healthy..."
for _ in $(seq 1 60); do
  if docker compose ps postgres 2>/dev/null | grep -q "healthy"; then
    echo "OK Postgres healthy"
    break
  fi
  sleep 5
done

# 1. Roles. Pass the passwords as psql variables so they never touch
# the shell history.
echo "==> Applying init-roles.sql"
docker compose exec -T \
  -e PGPASSWORD="${POSTGRES_PASSWORD:-}" \
  postgres psql \
    -v ON_ERROR_STOP=1 \
    -v "app_pw=${POSTGRES_PASSWORD}" \
    -v "ro_pw=${POSTGRES_PASSWORD_RO}" \
    -v "mig_pw=${POSTGRES_PASSWORD_MIGRATION}" \
    -U "${POSTGRES_USER_VAL}" \
    -d "${POSTGRES_DB_VAL}" \
  < infra/postgres/init-roles.sql >/dev/null
echo "OK roles bootstrapped"

# 2. Alembic migrations from an ad-hoc python:3.12-slim container that
# bind-mounts the repo + joins the compose network so it can resolve
# the `postgres` service hostname.
echo "==> Running alembic upgrade head"
docker run --rm \
  --network "${NETWORK}" \
  -v "${REPO_ROOT}:/app:ro" \
  -v "${REPO_ROOT}/.deploy/migrate-cache:/cache" \
  -e PIP_NO_CACHE_DIR=1 \
  -e POSTGRES_HOST=postgres \
  -e POSTGRES_PORT=5432 \
  -e POSTGRES_DB="${POSTGRES_DB_VAL}" \
  -e POSTGRES_USER="${POSTGRES_USER_VAL}" \
  -e POSTGRES_PASSWORD="${POSTGRES_PASSWORD}" \
  -e POSTGRES_USER_MIGRATION=iic_migration \
  -e POSTGRES_PASSWORD_MIGRATION="${POSTGRES_PASSWORD_MIGRATION}" \
  -e POSTGRES_USER_RO=iic_ro \
  -e POSTGRES_PASSWORD_RO="${POSTGRES_PASSWORD_RO}" \
  -e CHROMA_HOST=chroma \
  -e CHROMA_PORT=8000 \
  -e MINIO_ENDPOINT=minio:9000 \
  -e MINIO_ROOT_USER="${MINIO_ROOT_USER:-iic}" \
  -e MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:-changeme}" \
  -e REDIS_URL="redis://redis:6379/0" \
  -e PYTHONPATH=/app/packages/data-lake \
  --workdir /app/packages/data-lake/data_lake/migrations \
  python:3.12-slim \
  bash -c '
    set -euo pipefail
    pip install -q alembic==1.13.3 sqlalchemy==2.0.36 \
      psycopg2-binary==2.9.10 asyncpg==0.30.0 \
      orjson==3.10.10 sqlglot==25.30.0
    alembic upgrade head
  '

echo "OK migrations applied"
