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
  "admin_api|http://localhost:8090/admin/health|1"
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

# ---------------------------------------------------------------------------
# Dashboard SPA-route smoke (D9 §4.2 / §5.8 L1) — nginx must serve index.html
# for non-API paths, not the default 404. Without this, /map (and every other
# React Router sub-route) breaks on hard refresh.
# ---------------------------------------------------------------------------
echo ""
echo "==> Dashboard SPA-route smoke"
spa_failures=0
for path in /map /trading-room /admin/connectors; do
  resp="$(curl -fsS --max-time 5 "http://localhost:4173${path}" 2>/dev/null || echo "")"
  if echo "${resp}" | grep -q 'id="root"'; then
    printf "${GREEN}OK${RESET}    %-22s %s served SPA index\n" "spa${path}" "${path}"
  else
    printf "${RED}FAIL${RESET}  %-22s %s did not serve SPA index\n" "spa${path}" "${path}"
    spa_failures=$((spa_failures + 1))
  fi
done
if [[ "${spa_failures}" -gt 0 ]]; then
  printf "${RED}%d SPA-route check(s) failed.${RESET}\n" "${spa_failures}"
  echo "  - Check infra/nginx/dashboard.conf has 'try_files \$uri \$uri/ /index.html;'"
  echo "  - D9 §4.2 has the canonical config."
  exit 1
fi

# ---------------------------------------------------------------------------
# Wiring smoke (D7.1 §H0.3) — prove at least one LLM round-trip got recorded.
#
# Structural /health checks above only assert "the container started and
# returned 200." They do NOT exercise the LLM bind. Without this block, an
# unbound LlmRouter passes the smoke gate and `lake.llm_calls` stays at 0
# in production (the v2.6 bringup state).
#
# The three checks are intentionally separable so a failure points at one
# root cause:
#   1. Connector test  → key reaches the provider
#   2. /chat/echo      → router is bound, end-to-end LLM dispatch works
#   3. lake.llm_calls  → telemetry persistence works
# ---------------------------------------------------------------------------
ADMIN_API="${ADMIN_API:-http://localhost:8090}"
SECRETARY="${SECRETARY:-http://localhost:8086}"

if [[ -n "${DEEPSEEK_API_KEY:-}" || -n "${ANTHROPIC_API_KEY:-}" || -n "${GROQ_API_KEY:-}" ]]; then
  echo ""
  echo "==> Wiring smoke"
  wiring_failures=0

  if [[ -n "${DEEPSEEK_API_KEY:-}" ]]; then
    if curl -fsS -X POST "${ADMIN_API}/admin/connectors/deepseek/test" 2>/dev/null \
       | grep -q '"state"\s*:\s*"ok"'; then
      printf "${GREEN}OK${RESET}    %-22s deepseek connector test\n" "wiring.connector"
    else
      printf "${RED}FAIL${RESET}  %-22s deepseek connector test\n" "wiring.connector"
      wiring_failures=$((wiring_failures + 1))
    fi
  fi

  echo_body='{"text":"ping"}'
  echo_resp="$(curl -fsS -X POST "${SECRETARY}/chat/echo" \
    -H 'Content-Type: application/json' \
    -d "${echo_body}" 2>/dev/null || echo "")"
  if echo "${echo_resp}" | grep -q '"llm_call_id"'; then
    printf "${GREEN}OK${RESET}    %-22s /chat/echo produced llm_call_id\n" "wiring.echo"
  else
    printf "${RED}FAIL${RESET}  %-22s /chat/echo produced no llm_call_id (resp=%s)\n" \
      "wiring.echo" "${echo_resp:0:120}"
    wiring_failures=$((wiring_failures + 1))
  fi

  if [[ -n "${LAKE_DSN:-}" ]] && command -v psql >/dev/null 2>&1; then
    cnt="$(psql "${LAKE_DSN}" -tAc \
      "SELECT COUNT(*) FROM lake.llm_calls WHERE outcome='ok' AND ts > now() - interval '5 minutes';" \
      2>/dev/null || echo 0)"
    if [[ "${cnt:-0}" -ge 1 ]]; then
      printf "${GREEN}OK${RESET}    %-22s lake.llm_calls ok rows=%s in last 5m\n" \
        "wiring.lake" "${cnt}"
    else
      printf "${RED}FAIL${RESET}  %-22s lake.llm_calls has no recent ok row\n" "wiring.lake"
      wiring_failures=$((wiring_failures + 1))
    fi
  else
    printf "${YELLOW}skip${RESET}  %-22s lake.llm_calls check (need LAKE_DSN + psql)\n" \
      "wiring.lake"
  fi

  if [[ "${wiring_failures}" -gt 0 ]]; then
    printf "${RED}%d wiring smoke step(s) failed.${RESET}\n" "${wiring_failures}"
    echo "  - Router unbound? Check D7.1 §H0 (each agent must call llm_client.bootstrap)."
    echo "  - See D7.1 §H0.3 for the meaning of each step."
    exit 1
  fi
  printf "${GREEN}Wiring smoke passed.${RESET}\n"
else
  echo ""
  printf "${YELLOW}skip${RESET}  wiring smoke (no LLM key configured — substrate-only OK)\n"
fi
