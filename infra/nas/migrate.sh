#!/usr/bin/env bash
# IIC v2.1 — NAS migration (workflow 01 §5.6, PLAN §8.4).
#
# The single most load-bearing decision in the system: every persistent path
# is a bind mount under /srv/iic. Migrating to a NAS means rsync + an fstab
# edit, with zero changes to docker-compose.yml.
#
#   bash infra/nas/migrate.sh                 # default --dry-run, exits 0
#   bash infra/nas/migrate.sh --dry-run       # explicit dry-run
#   bash infra/nas/migrate.sh --apply         # do it for real
#
# Env knobs:
#   NAS_HOST        — NAS hostname (default: nas.local)
#   NAS_PATH        — NFS export path on the NAS (default: /volume1/iic)
#   KEEP_PG_LOCAL=1 — leave Postgres data dir on local NVMe, only move the rest
#                     (NFSv4.1+ Postgres is OK with hard,nolock but if unsure
#                      use this — see workflow 01 §5.6 caveat)

set -euo pipefail

MODE="${1:---dry-run}"
NAS_HOST="${NAS_HOST:-nas.local}"
NAS_PATH="${NAS_PATH:-/volume1/iic}"
KEEP_PG_LOCAL="${KEEP_PG_LOCAL:-0}"
SRV="/srv/iic"
COMPOSE=/opt/iic/docker-compose.yml

log() { echo "[$(date -Iseconds)] [migrate] $*"; }

# Linux rsync (3.x) supports -A (ACLs), -X (xattrs), and --info=progress2;
# BSD rsync on macOS (2.6.9) supports none. Probe once.
RSYNC_FLAGS="-aH"
RSYNC_PROGRESS="--progress"
if rsync --version 2>/dev/null | head -1 | grep -qE 'version 3\.'; then
  RSYNC_FLAGS="-aHAX"
  RSYNC_PROGRESS="--info=progress2"
fi

preflight() {
  command -v rsync >/dev/null
  if [[ "$MODE" == "--apply" ]]; then
    command -v showmount >/dev/null
    if ! showmount -e "$NAS_HOST" 2>/dev/null | grep -q "$NAS_PATH"; then
      echo "NFS export $NAS_HOST:$NAS_PATH not found"; exit 1
    fi
    df --output=avail "$SRV" | tail -1
  fi
}

stop_stack() {
  if [[ "$MODE" == "--apply" ]] && systemctl list-unit-files | grep -q '^iic.service'; then
    sudo systemctl stop iic.service
  fi
}

start_stack() {
  if [[ "$MODE" == "--apply" ]] && systemctl list-unit-files | grep -q '^iic.service'; then
    sudo systemctl start iic.service
  fi
}

migrate() {
  local rsync_excludes=""
  if [[ "$KEEP_PG_LOCAL" == "1" ]]; then
    rsync_excludes="--exclude /pg"
  fi

  if [[ "$MODE" == "--dry-run" ]]; then
    log "dry-run: simulating rsync to /tmp/iic-dryrun/"
    mkdir -p /tmp/iic-dryrun
    if [[ -d "$SRV" ]]; then
      # shellcheck disable=SC2086
      rsync $RSYNC_FLAGS --dry-run $RSYNC_PROGRESS $rsync_excludes "$SRV/" "/tmp/iic-dryrun/"
    else
      log "(/srv/iic does not exist on this host — synthesizing layout for CI)"
      mkdir -p "/tmp/iic-fixture"/{pg,chroma,nats,minio,redis,grafana,loki,prometheus,prompts_versioned,advice_ledger,backup}
      # shellcheck disable=SC2086
      rsync $RSYNC_FLAGS --dry-run $RSYNC_PROGRESS $rsync_excludes "/tmp/iic-fixture/" "/tmp/iic-dryrun/"
    fi
  else
    log "applying: rsync $SRV -> $NAS_HOST:$NAS_PATH"
    # shellcheck disable=SC2086
    rsync $RSYNC_FLAGS $RSYNC_PROGRESS $rsync_excludes "$SRV/" "$NAS_HOST:$NAS_PATH/"
    if ! grep -q "$NAS_PATH" /etc/fstab; then
      log "fstab: adding NFS mount entry"
      echo "$NAS_HOST:$NAS_PATH $SRV nfs vers=4.1,_netdev,hard,timeo=600,retrans=2 0 0" \
        | sudo tee -a /etc/fstab >/dev/null
    fi
    sudo umount "$SRV" 2>/dev/null || true
    sudo mount "$SRV"
  fi
}

postflight() {
  if [[ "$MODE" != "--apply" ]]; then return 0; fi
  for c in nats postgres chroma minio redis orchestrator agent_intelligence \
           agent_fundamental agent_quant agent_persona agent_backtest agent_secretary; do
    docker compose -f "$COMPOSE" ps "$c" | grep -q "Up" || {
      echo "postflight: $c is not Up"; exit 1
    }
  done
}

case "$MODE" in
  --dry-run|--apply) ;;
  *) echo "usage: $0 [--dry-run|--apply]" >&2; exit 2 ;;
esac

preflight
stop_stack
migrate
start_stack
postflight
log "done in mode: $MODE"
