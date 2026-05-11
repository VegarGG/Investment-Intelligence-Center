#!/bin/sh
# IIC v2.5 — dev-mode entrypoint wrapper.
#
# The shared packages under /app/<pkg> are bind-mounted from packages/<pkg>
# at runtime (see docker-compose.dev.yml). They have transitive deps that
# the per-agent requirements.txt files don't list because each agent only
# pulled in the deps it directly imports — not the ones reached through
# the shared packages. Install the union here so any agent that imports
# any shared module gets a working environment.
#
# This runs every container start. Pip is fast when packages are already
# satisfied; first-run takes ~30s.

set -e

PYTHONWARNINGS="${PYTHONWARNINGS:-ignore}" \
pip install --no-cache-dir --disable-pip-version-check -q \
  packaging \
  jinja2 \
  structlog \
  redis \
  'sqlalchemy[asyncio]' \
  asyncpg \
  psycopg2-binary \
  opentelemetry-api \
  pyyaml \
  nats-py \
  || echo "warn: pip install of shared-package extras failed — continuing"

exec "$@"
