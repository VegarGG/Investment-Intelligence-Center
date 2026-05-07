#!/usr/bin/env bash
# Workflow 31 §5 + §10 — automate DR drill steps 5–8.
#
# Steps 1-4 (acquire scratch hardware, boot Ubuntu, sync age key, place
# .env.sops) remain human-driven. From step 5 onward this script:
#
#   5. restic restore --repo "$RESTIC_REPOSITORY" --target /srv/iic latest
#   6. systemctl start iic.service
#   7. wait for `docker compose ps` all Up
#   8. POST /run/morning_brief, assert orchestrator heartbeat present
#
# Idempotent. Outputs elapsed seconds at the end. Designed to run unattended
# in the rehearsal VM (DRY_RUN=1 prints what would happen without acting).

set -euo pipefail

DRY_RUN=${DRY_RUN:-0}
SRV_ROOT=${SRV_ROOT:-/srv/iic}
COMPOSE_FILE=${COMPOSE_FILE:-/opt/iic/docker-compose.yml}
ORCH_URL=${ORCH_URL:-http://localhost:8080}
SECRETARY_URL=${SECRETARY_URL:-http://localhost:8086}
ELAPSED_TARGET_S=${ELAPSED_TARGET_S:-3600}
LOG_TAG=${LOG_TAG:-dr_drill}

log() { printf '[dr-drill %s] %s\n' "$(date -Is)" "$*" >&2; }
run() {
  if [[ "$DRY_RUN" == "1" ]]; then
    log "DRY_RUN: $*"
  else
    log "EXEC: $*"
    "$@"
  fi
}

require() {
  command -v "$1" >/dev/null 2>&1 || {
    log "ERROR: missing required tool '$1'"
    exit 1
  }
}

require date
[[ "$DRY_RUN" == "1" ]] || require docker
[[ "$DRY_RUN" == "1" ]] || require restic
[[ "$DRY_RUN" == "1" ]] || require curl

start_s=$(date +%s)

# Step 5 — restore from B2.
log "step 5/4: restic restore latest -> $SRV_ROOT"
mkdir -p "$SRV_ROOT" || true
run restic restore --target "$SRV_ROOT" latest

# Step 6 — bring up the stack.
log "step 6: systemctl start iic.service"
if [[ "$DRY_RUN" == "1" ]]; then
  log "DRY_RUN: would start iic.service"
else
  if command -v systemctl >/dev/null 2>&1; then
    systemctl start iic.service
  else
    log "no systemctl — falling back to docker compose up -d"
    docker compose -f "$COMPOSE_FILE" up -d
  fi
fi

# Step 7 — wait for all services up (cap 5m).
log "step 7: waiting for compose stack"
deadline=$(( $(date +%s) + 300 ))
until [[ "$DRY_RUN" == "1" ]] || \
      ! docker compose -f "$COMPOSE_FILE" ps --status=exited --status=created 2>/dev/null \
        | grep -qE 'exited|created'; do
  if (( $(date +%s) > deadline )); then
    log "ERROR: services did not converge within 5 min"
    exit 1
  fi
  sleep 5
done

# Step 8 — kick a brief and assert heartbeat.
log "step 8: POST /run/morning_brief + heartbeat probe"
run curl -fsS -X POST "$SECRETARY_URL/run/morning_brief"
run curl -fsS "$ORCH_URL/health"

end_s=$(date +%s)
elapsed=$(( end_s - start_s ))
log "elapsed=${elapsed}s target=${ELAPSED_TARGET_S}s tag=$LOG_TAG"
if (( elapsed > ELAPSED_TARGET_S )); then
  log "WARN: drill exceeded target — file an issue"
fi
echo "$elapsed"
