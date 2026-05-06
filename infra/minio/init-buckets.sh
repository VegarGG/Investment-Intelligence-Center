#!/usr/bin/env bash
# IIC v2.1 — MinIO bucket bootstrap (workflow 02 §5.7, §7.5).
#
# Idempotent: creates the four canonical buckets, applies lifecycle rules,
# and mints an `iic-app` user with bucket-scoped access. Run once after
# `docker compose up -d minio`.

set -euo pipefail

MC=${MC:-mc}
ALIAS=${MINIO_ALIAS:-iic}
ENDPOINT=${MINIO_ENDPOINT:-http://localhost:9000}
ROOT_USER=${MINIO_ROOT_USER:?must be set}
ROOT_PASSWORD=${MINIO_ROOT_PASSWORD:?must be set}

log() { echo "[$(date -Iseconds)] [minio-init] $*"; }

log "configuring mc alias $ALIAS -> $ENDPOINT"
"$MC" alias set "$ALIAS" "$ENDPOINT" "$ROOT_USER" "$ROOT_PASSWORD" >/dev/null

ensure_bucket() {
  local name="$1"
  if ! "$MC" ls "$ALIAS/$name" >/dev/null 2>&1; then
    log "creating bucket $name"
    "$MC" mb --ignore-existing "$ALIAS/$name"
  else
    log "bucket $name exists"
  fi
}

ensure_lifecycle_expire() {
  local name="$1" days="$2"
  log "lifecycle: $name expires after ${days}d"
  "$MC" ilm rule add --expire-days "$days" "$ALIAS/$name" >/dev/null 2>&1 || true
}

ensure_lifecycle_transition() {
  local name="$1" days="$2"
  log "lifecycle: $name transitions to cold after ${days}d (placeholder — define cold tier on NAS)"
  # Real transition needs a remote tier configured on the MinIO server.
  # Placeholder rule to document intent until the cold tier exists.
  "$MC" ilm rule add --tags "iic-cold-after=$days" "$ALIAS/$name" >/dev/null 2>&1 || true
}

# ----- the four canonical buckets ------------------------------------------
ensure_bucket iic-filings
ensure_lifecycle_transition iic-filings 90      # hot 90d, cold thereafter

ensure_bucket iic-news-html
ensure_lifecycle_expire iic-news-html 365       # expire after 365d

ensure_bucket iic-snapshots-parquet
log "lifecycle: iic-snapshots-parquet — no expiry (factor matrices kept forever)"

ensure_bucket iic-charts
ensure_lifecycle_expire iic-charts 180          # expire after 180d

# ----- application user ----------------------------------------------------
APP_USER=${MINIO_APP_USER:-iic-app}
APP_PASSWORD=${MINIO_APP_PASSWORD:-}
if [[ -n "$APP_PASSWORD" ]]; then
  if ! "$MC" admin user info "$ALIAS" "$APP_USER" >/dev/null 2>&1; then
    log "creating app user $APP_USER"
    "$MC" admin user add "$ALIAS" "$APP_USER" "$APP_PASSWORD"
  fi

  POLICY=/tmp/iic-app-policy.json
  cat > "$POLICY" <<'JSON'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:*"],
      "Resource": [
        "arn:aws:s3:::iic-filings/*",
        "arn:aws:s3:::iic-news-html/*",
        "arn:aws:s3:::iic-snapshots-parquet/*",
        "arn:aws:s3:::iic-charts/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::iic-filings",
        "arn:aws:s3:::iic-news-html",
        "arn:aws:s3:::iic-snapshots-parquet",
        "arn:aws:s3:::iic-charts"
      ]
    }
  ]
}
JSON
  "$MC" admin policy create "$ALIAS" iic-app "$POLICY" >/dev/null 2>&1 || true
  "$MC" admin policy attach "$ALIAS" iic-app --user "$APP_USER" >/dev/null 2>&1 || true
  rm -f "$POLICY"
else
  log "MINIO_APP_PASSWORD not set — skipping app user creation"
fi

log "done"
