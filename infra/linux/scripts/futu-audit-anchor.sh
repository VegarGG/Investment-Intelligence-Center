#!/usr/bin/env bash
#
# v2.5 N3.0c — Daily OpenTimestamps anchor for the lake.futu_audit chain head.
#
# The audit chain is hash-linked Python-side and trigger-enforced
# server-side, but neither protects against a coordinated DBA + writer
# rewriting the chain in place. OpenTimestamps anchors each daily chain
# head into the Bitcoin blockchain (via commits.opentimestamps.org)
# producing a `.ots` proof. The proof is verifiable against Bitcoin
# without the OTS server — so even if `commits.opentimestamps.org`
# disappears, an existing `.ots` file is still trustworthy.
#
# Output: /srv/iic/futu-audit-anchors/<YYYY-MM-DD>.head + .ots
#   .head — the SHA-256 chain head we anchored (so verification can
#           recompute it from the DB and compare).
#   .ots  — the OTS proof file produced by `ots stamp`.
#
# Failure modes:
#   - DB unreachable                → exit 2
#   - OTS CLI missing               → exit 3
#   - OTS stamp fails               → exit 4
# All non-zero exits are picked up by the systemd timer's OnFailure unit.

set -euo pipefail

ANCHOR_DIR="${IIC_FUTU_AUDIT_ANCHOR_DIR:-/srv/iic/futu-audit-anchors}"
PG_DSN="${IIC_PG_DSN_RO:-${IIC_PG_DSN_APP:-}}"
DATE_ISO="$(date -u +%Y-%m-%d)"

mkdir -p "${ANCHOR_DIR}"

if [ -z "${PG_DSN}" ]; then
  echo "futu-audit-anchor: IIC_PG_DSN_{RO,APP} not set" >&2
  exit 2
fi

if ! command -v ots >/dev/null 2>&1; then
  echo "futu-audit-anchor: 'ots' (opentimestamps-client) not on PATH" >&2
  exit 3
fi

# Compute the global chain head: the SHA-256 of the concatenated per-fid
# heads, sorted by futu_id_hash, so a single anchor covers every chain.
HEAD_SQL=$(cat <<'SQL'
WITH heads AS (
  SELECT DISTINCT ON (futu_id_hash) futu_id_hash, entry_hash
  FROM lake.futu_audit
  ORDER BY futu_id_hash, id DESC
)
SELECT encode(
  digest(string_agg(futu_id_hash || ':' || entry_hash, E'\n' ORDER BY futu_id_hash), 'sha256'),
  'hex'
) FROM heads;
SQL
)

HEAD_HEX="$(psql "${PG_DSN}" -At -c "${HEAD_SQL}")"
if [ -z "${HEAD_HEX}" ] || [ "${HEAD_HEX}" = "" ]; then
  # Empty chain (no FUTU calls have ever been recorded) — stamp the
  # zero head so the anchor cron is observable from day 1.
  HEAD_HEX="$(printf '0%.0s' {1..64})"
fi

HEAD_FILE="${ANCHOR_DIR}/${DATE_ISO}.head"
printf '%s\n' "${HEAD_HEX}" > "${HEAD_FILE}"

if ! ots stamp "${HEAD_FILE}"; then
  echo "futu-audit-anchor: 'ots stamp' failed for ${HEAD_FILE}" >&2
  exit 4
fi

echo "futu-audit-anchor: ${DATE_ISO} head=${HEAD_HEX} → ${HEAD_FILE}.ots"
