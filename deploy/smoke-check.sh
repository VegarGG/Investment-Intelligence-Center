#!/usr/bin/env bash
#
# IIC v2.5 — smoke-test every service's /health endpoint.
#
# Exit 0 only when every required service responds 200 within 10 s.
# `optional` services (board, intelligence) are reported but don't
# fail the script — they're often disabled in dev mode.
#
# Usage:
#   bash deploy/smoke-check.sh
#   bash deploy/smoke-check.sh --strict   # treat optional services as required

set -euo pipefail

STRICT=0
[[ "${1:-}" == "--strict" ]] && STRICT=1

# Service → URL → required-ness.
# format: name|url|required(0|1)
SERVICES=(
  "orchestrator|http://localhost:8080/health|1"
  "agent_intelligence|http://localhost:8081/health|0"
  "agent_fundamental|http://localhost:8082/health|0"
  "agent_quant|http://localhost:8083/health|0"
  "agent_persona|http://localhost:8084/health|0"
  "agent_backtest|http://localhost:8085/health|0"
  "agent_secretary|http://localhost:8086/health|0"
  "agent_futu|http://localhost:8087/health|0"
  "agent_board|http://localhost:8088/health|0"
  "dashboard|http://localhost:4173/|1"
  "grafana|http://localhost:3000/api/health|0"
  "minio_console|http://localhost:9001/|0"
)

# Postgres / Redis / NATS / Chroma — TCP probes (no /health).
TCP_PROBES=(
  "postgres|localhost|5432|1"
  "redis|localhost|6379|1"
  "nats|localhost|4222|1"
  "chroma|localhost|8000|0"
)

GREEN='\033[1;32m'
YELLOW='\033[1;33m'
RED='\033[1;31m'
RESET='\033[0m'

failures=0

probe_http() {
  local name="$1" url="$2" required="$3"
  local code
  code="$(curl -fsS -o /dev/null -w '%{http_code}' --max-time 5 "${url}" 2>/dev/null || echo "fail")"
  if [[ "${code}" =~ ^2[0-9][0-9]$ || "${code}" == "304" ]]; then
    printf "${GREEN}OK${RESET}    %-22s %s\n" "${name}" "${code} ${url}"
  elif [[ "${required}" == "1" || "${STRICT}" == "1" ]]; then
    printf "${RED}FAIL${RESET}  %-22s %s (got ${code:-?})\n" "${name}" "${url}"
    failures=$((failures + 1))
  else
    printf "${YELLOW}skip${RESET}  %-22s %s (optional, got ${code:-?})\n" "${name}" "${url}"
  fi
}

probe_tcp() {
  local name="$1" host="$2" port="$3" required="$4"
  if (echo > "/dev/tcp/${host}/${port}") >/dev/null 2>&1; then
    printf "${GREEN}OK${RESET}    %-22s tcp ${host}:${port}\n" "${name}"
  elif [[ "${required}" == "1" || "${STRICT}" == "1" ]]; then
    printf "${RED}FAIL${RESET}  %-22s tcp ${host}:${port}\n" "${name}"
    failures=$((failures + 1))
  else
    printf "${YELLOW}skip${RESET}  %-22s tcp ${host}:${port} (optional)\n" "${name}"
  fi
}

echo "==> Smoke-checking IIC services"
for entry in "${TCP_PROBES[@]}"; do
  IFS='|' read -r name host port required <<<"${entry}"
  probe_tcp "${name}" "${host}" "${port}" "${required}"
done
for entry in "${SERVICES[@]}"; do
  IFS='|' read -r name url required <<<"${entry}"
  probe_http "${name}" "${url}" "${required}"
done

echo ""
if [[ "${failures}" -gt 0 ]]; then
  printf "${RED}%d required service(s) failed.${RESET}\n" "${failures}"
  echo "  - Try 'docker compose ps' to see which containers are running."
  echo "  - 'docker compose logs <service>' to see why one failed."
  exit 1
fi

printf "${GREEN}All required services healthy.${RESET}\n"
