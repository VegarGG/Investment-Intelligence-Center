#!/usr/bin/env bash
# IIC v2.1 — NATS JetStream provisioning (workflow 05 §8.1).
#
# Idempotent: creates the five streams + three KV buckets per workflow 05 §2.
# Re-run safely; existing streams are updated rather than recreated.
#
# Usage:
#   bash infra/nats/init.sh                # uses NATS_URL=nats://localhost:4222
#   NATS_URL=nats://nats:4222 bash infra/nats/init.sh
#
# Requires the `nats` CLI on PATH. Install:
#   curl -fsSL https://github.com/nats-io/natscli/releases/latest/download/nats-...

set -euo pipefail

NATS_URL=${NATS_URL:-nats://localhost:4222}
NATS_BIN=${NATS_BIN:-nats}

log() { echo "[$(date -Iseconds)] [nats-init] $*"; }

if ! command -v "$NATS_BIN" >/dev/null 2>&1; then
  echo "nats CLI not on PATH (set NATS_BIN= or install)" >&2
  exit 1
fi

NATS_CTX=${NATS_CTX:-iic}
"$NATS_BIN" context save "$NATS_CTX" --server "$NATS_URL" --select >/dev/null

# ---- streams (workflow 05 §2 table) ---------------------------------------
ensure_stream() {
  local name="$1" subjects="$2" max_age="$3"
  local args=(stream add "$name"
    --subjects "$subjects"
    --replicas 1
    --storage file
    --retention limits
    --discard old
    --max-msgs=-1
    --max-bytes=-1
    --max-msg-size=-1
    --dupe-window 60s
    --no-deny-delete
    --no-deny-purge
    --no-allow-rollup
    --defaults
  )
  if [[ "$max_age" != "0" ]]; then
    args+=(--max-age "$max_age")
  fi

  if "$NATS_BIN" stream info "$name" >/dev/null 2>&1; then
    log "stream $name exists — updating retention to max-age=$max_age"
    "$NATS_BIN" stream edit "$name" --max-age "$max_age" --force || true
  else
    log "creating stream $name (subjects=$subjects max-age=$max_age)"
    "$NATS_BIN" "${args[@]}"
  fi
}

ensure_stream INTEL     'intel.>'     30d
ensure_stream ADVICE    'advice.>'    0           # forever
ensure_stream BACKTEST  'backtest.>'  365d
ensure_stream SECRETARY 'secretary.>' 7d
ensure_stream OPS       'ops.>'       14d

# ---- KV buckets (workflow 05 §2) ------------------------------------------
ensure_kv() {
  local bucket="$1"
  if "$NATS_BIN" kv info "$bucket" >/dev/null 2>&1; then
    log "kv bucket $bucket exists"
  else
    log "creating kv bucket $bucket"
    "$NATS_BIN" kv add "$bucket" --replicas 1 --storage file
  fi
}

ensure_kv iic_state
ensure_kv iic_locks
ensure_kv iic_versions

# ---- post-flight ----------------------------------------------------------
log "post-flight: stream + bucket inventory"
"$NATS_BIN" stream ls
"$NATS_BIN" kv ls
log "done"
