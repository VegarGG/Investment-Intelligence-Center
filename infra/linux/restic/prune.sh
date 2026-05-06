#!/usr/bin/env bash
# IIC v2.1 — restic forget+prune for both repos.
# Retention policy from workflow 01 §2.7: 7 daily, 4 weekly, 12 monthly, 3 yearly.

set -euo pipefail

if [[ -f /run/iic/.env ]]; then
  set -a; . /run/iic/.env; set +a
fi

for repo in "${RESTIC_REPOSITORY_LOCAL:-/srv/iic/backup-hdd/restic}" "${RESTIC_REPOSITORY_B2:-b2:iic-restic}"; do
  echo "[prune] $repo"
  RESTIC_REPOSITORY="$repo" restic forget \
    --keep-daily 7 --keep-weekly 4 --keep-monthly 12 --keep-yearly 3 \
    --prune --quiet
done
