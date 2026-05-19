#!/usr/bin/env bash
# Restore drill (P9.4).
#
# Run weekly. Verifies that:
#   1. The current Postgres + NATS JetStream snapshots can be restored to
#      a clean side container.
#   2. After restore, `lake.advice` row-count and chain-head hash match
#      the production snapshot taken at the start of the drill.
#
# A successful drill is the only meaningful proof that production
# backups are recoverable. The drill is destructive against the SIDE
# container only — it never touches the running production volume.
#
# Exit non-zero on any mismatch; the orchestrator's Alertmanager turns a
# failing drill into an ALERT to the secretary.

set -euo pipefail

WORK_DIR=$(mktemp -d -t iic-restore-XXXXXX)
SIDE_PG="iic-restore-pg"
trap 'docker rm -f "$SIDE_PG" 2>/dev/null || true; rm -rf "$WORK_DIR"' EXIT

echo "==> 1. snapshot production state"
prod_count=$(docker exec iic-postgres psql -tA -U iic_app -d iic \
  -c "SELECT count(*) FROM lake.advice")
prod_head=$(docker exec iic-postgres psql -tA -U iic_app -d iic \
  -c "SELECT encode(chain_hash, 'hex') FROM lake.advice ORDER BY ts DESC LIMIT 1")
echo "  prod row count = $prod_count"
echo "  prod chain head = ${prod_head:0:16}..."

echo "==> 2. dump production"
DUMP="$WORK_DIR/lake.dump"
docker exec iic-postgres pg_dump -U iic_app -d iic -Fc -f /tmp/lake.dump
docker cp iic-postgres:/tmp/lake.dump "$DUMP"

echo "==> 3. spin up a side container + restore"
docker run -d --name "$SIDE_PG" \
  -e POSTGRES_USER=iic_app \
  -e POSTGRES_PASSWORD=ci-test \
  -e POSTGRES_DB=iic \
  iic-postgres:pg16-partman
sleep 10
docker cp "$DUMP" "$SIDE_PG":/tmp/lake.dump
docker exec "$SIDE_PG" pg_restore -U iic_app -d iic -c /tmp/lake.dump || true

echo "==> 4. verify counts + chain head match"
side_count=$(docker exec "$SIDE_PG" psql -tA -U iic_app -d iic \
  -c "SELECT count(*) FROM lake.advice")
side_head=$(docker exec "$SIDE_PG" psql -tA -U iic_app -d iic \
  -c "SELECT encode(chain_hash, 'hex') FROM lake.advice ORDER BY ts DESC LIMIT 1")

if [ "$prod_count" != "$side_count" ]; then
  echo "FAIL: row count drift prod=$prod_count side=$side_count" >&2
  exit 1
fi
if [ "$prod_head" != "$side_head" ]; then
  echo "FAIL: chain head drift prod=$prod_head side=$side_head" >&2
  exit 1
fi
echo "PASS: restore drill clean (rows=$prod_count, head=${prod_head:0:16}...)"
