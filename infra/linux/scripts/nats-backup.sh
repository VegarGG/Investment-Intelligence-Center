#!/usr/bin/env bash
#
# v2.5 T1.7 — Daily NATS JetStream backup.
#
# Cron: 03:00 local. Calls `nats stream backup --all <out_dir>` against the
# running JetStream container, then rotates anything older than RETENTION_DAYS
# off local disk and into MinIO via the existing restic config.
#
# Failure modes:
# - NATS unreachable → exit 2, alertmanager fires runbook-backup-failed.
# - Disk full → exit 3, restic alerts catch this via the existing prune timer.
# - Stream backup partial → exit 4 with the per-stream error log.

set -euo pipefail

BACKUP_ROOT="${BACKUP_ROOT:-/srv/iic/nats-backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
NATS_URL="${NATS_URL:-nats://nats:4222}"
NATS_BIN="${NATS_BIN:-nats}"

today="$(date -u +%F)"
out_dir="${BACKUP_ROOT}/${today}"
log_file="${BACKUP_ROOT}/last-backup.log"

mkdir -p "${BACKUP_ROOT}" "${out_dir}"
echo "[$(date -uIs)] starting nats-backup → ${out_dir}" | tee -a "${log_file}"

# Run the actual backup. `--all` covers every JetStream stream + its consumers.
if ! "${NATS_BIN}" --server="${NATS_URL}" stream backup --all "${out_dir}" 2>>"${log_file}"; then
  echo "[$(date -uIs)] FAILED nats stream backup" | tee -a "${log_file}"
  exit 4
fi

# Rotate old day-folders into MinIO via restic. We keep the last RETENTION_DAYS
# days on local disk for fast restore.
if [ -x /usr/local/bin/restic-iic.sh ]; then
  /usr/local/bin/restic-iic.sh backup "${BACKUP_ROOT}" --tag nats-backup --tag "${today}"
fi

# Drop folders older than RETENTION_DAYS off local disk.
find "${BACKUP_ROOT}" -mindepth 1 -maxdepth 1 -type d -mtime "+${RETENTION_DAYS}" \
     -print -exec rm -rf {} +

echo "[$(date -uIs)] nats-backup complete" | tee -a "${log_file}"
