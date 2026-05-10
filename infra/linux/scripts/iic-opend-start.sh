#!/usr/bin/env bash
#
# v2.5 N3.6 — Start one Futu OpenD container in SIMULATE mode for a given
# futu_id_hash. Refuses to start with OPEND_TRD_ENV=LIVE.
#
# This is the load-bearing pre-flight check on the read-only safety
# property: the wrapper, the firewall, the audit log, and this script
# all enforce read-only at different layers.

set -euo pipefail

FUTU_ID_HASH="${1:?usage: iic-opend-start.sh <futu_id_hash>}"
TRD_ENV="${OPEND_TRD_ENV:-SIMULATE}"

if [ "${TRD_ENV}" != "SIMULATE" ]; then
  echo "iic-opend-start: refusing to start OpenD with OPEND_TRD_ENV=${TRD_ENV}" >&2
  echo "iic-opend-start: only SIMULATE is supported by IIC's read-only path" >&2
  exit 64  # EX_USAGE
fi

CONFIG_DIR="/srv/iic/futu/${FUTU_ID_HASH}/openD-config"
SECRET_FILE="/run/iic/futu-${FUTU_ID_HASH}/secret"

if [ ! -d "${CONFIG_DIR}" ]; then
  echo "iic-opend-start: config dir missing: ${CONFIG_DIR}" >&2
  exit 65
fi
if [ ! -f "${SECRET_FILE}" ]; then
  echo "iic-opend-start: secret file missing: ${SECRET_FILE}" >&2
  exit 66
fi

exec docker run --rm \
  --name "iic-opend-${FUTU_ID_HASH}" \
  --network iic_futu_${FUTU_ID_HASH} \
  -v "${CONFIG_DIR}:/etc/futu-opend:ro" \
  -v "${SECRET_FILE}:/etc/futu-opend/secret:ro" \
  -e FUTU_TRD_ENV=SIMULATE \
  -p "127.0.0.1:11111:11111" \
  futu/opend:latest
