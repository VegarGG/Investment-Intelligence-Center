#!/usr/bin/env bash
# IIC v2.1 — restic restore.
#
# Used by the DR drill in workflow 31 §5. Accepts:
#   --repo local|b2     (default: local)
#   --snapshot <id>     (default: latest)
#   --target <path>     (required)

set -euo pipefail

REPO_KIND=local
SNAPSHOT=latest
TARGET=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)     REPO_KIND="$2"; shift 2 ;;
    --snapshot) SNAPSHOT="$2";  shift 2 ;;
    --target)   TARGET="$2";    shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

[[ -z "$TARGET" ]] && { echo "--target is required" >&2; exit 2; }

if [[ -f /run/iic/.env ]]; then
  set -a; . /run/iic/.env; set +a
fi

case "$REPO_KIND" in
  local) export RESTIC_REPOSITORY="${RESTIC_REPOSITORY_LOCAL:-/srv/iic/backup-hdd/restic}" ;;
  b2)    export RESTIC_REPOSITORY="${RESTIC_REPOSITORY_B2:-b2:iic-restic}" ;;
  *) echo "--repo must be 'local' or 'b2'" >&2; exit 2 ;;
esac

mkdir -p "$TARGET"
restic restore "$SNAPSHOT" --target "$TARGET"
echo "Restored snapshot=$SNAPSHOT from $REPO_KIND -> $TARGET"
