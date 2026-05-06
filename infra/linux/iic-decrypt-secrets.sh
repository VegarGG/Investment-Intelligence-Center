#!/usr/bin/env bash
# IIC v2.1 — sops + age decrypt of /opt/iic/.env.sops -> /run/iic/.env (tmpfs).
#
# Run as ExecStartPre of iic.service. Plaintext .env never touches disk.

set -euo pipefail

SOPS_FILE=/opt/iic/.env.sops
TARGET_DIR=/run/iic
TARGET=$TARGET_DIR/.env
AGE_KEY=/etc/iic/age.key

if [[ ! -f "$SOPS_FILE" ]]; then
  echo "decrypt-secrets: $SOPS_FILE missing — refusing to start" >&2
  exit 1
fi
if [[ ! -f "$AGE_KEY" ]]; then
  echo "decrypt-secrets: $AGE_KEY missing — refusing to start" >&2
  exit 1
fi

mkdir -p "$TARGET_DIR"
chmod 700 "$TARGET_DIR"

SOPS_AGE_KEY_FILE="$AGE_KEY" sops --decrypt "$SOPS_FILE" > "$TARGET"
chmod 600 "$TARGET"

# Compose reads .env from CWD by default. Symlink so /opt/iic/.env -> tmpfs.
ln -sf "$TARGET" /opt/iic/.env

echo "decrypt-secrets: ok"
