#!/usr/bin/env bash
# IIC v2.1 — daily restic backup (workflow 01 §5.5).
#
# Run by systemd timer at 03:00 local. Backs up /srv/iic to BOTH a local
# repo on the external HDD and an offsite B2 repo. Postgres and ChromaDB
# get pre-hooks so the backup is consistent.

set -euo pipefail

# Load creds (RESTIC_PASSWORD, B2_ACCOUNT_ID, B2_ACCOUNT_KEY) from /run/iic/.env.
if [[ -f /run/iic/.env ]]; then
  set -a; . /run/iic/.env; set +a
fi

LOCAL_REPO="${RESTIC_REPOSITORY_LOCAL:-/srv/iic/backup-hdd/restic}"
B2_REPO="${RESTIC_REPOSITORY_B2:-b2:iic-restic}"
SOURCE=/srv/iic
EXCLUDES=(--exclude /srv/iic/pg/wal --exclude /srv/iic/backup --exclude /srv/iic/backup-hdd)

log() { echo "[$(date -Iseconds)] $*"; }

# ---- Postgres pre-hook: pg_dump every database --------------------------
pg_pre_hook() {
  log "pg_dump pre-hook"
  mkdir -p /srv/iic/pg/dumps
  docker exec iic-postgres pg_dumpall -U "${POSTGRES_USER:-iic}" \
    | gzip -9 > "/srv/iic/pg/dumps/all-$(date +%F).sql.gz"
}

# ---- ChromaDB pre-hook: filesystem snapshot -----------------------------
chroma_pre_hook() {
  log "chroma snapshot pre-hook"
  local snap="/srv/iic/chroma-snapshot-$(date +%F)"
  rsync -a --delete /srv/iic/chroma/ "$snap/"
}

run_repo() {
  local repo="$1"
  log "restic backup -> $repo"
  RESTIC_REPOSITORY="$repo" restic backup "$SOURCE" "${EXCLUDES[@]}" \
    --tag "iic-$(date +%F)" --quiet
  RESTIC_REPOSITORY="$repo" restic forget --keep-daily 7 --keep-weekly 4 \
    --keep-monthly 12 --keep-yearly 3 --prune --quiet
}

main() {
  pg_pre_hook
  chroma_pre_hook
  run_repo "$LOCAL_REPO"
  run_repo "$B2_REPO"
  log "done"
}

main "$@"
