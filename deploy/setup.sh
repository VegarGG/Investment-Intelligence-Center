#!/usr/bin/env bash
#
# IIC v2.5 — fresh-Ubuntu prototype installer.
#
# Tested on: Ubuntu Desktop 26.04 LTS (Server should also work).
# Audience:  young developers, first-time deployers.
# Goal:      from a fresh Ubuntu install to a running IIC dashboard in < 15 min.
#
# This script is IDEMPOTENT — re-running it is safe and skips finished steps.
# Markers under /var/lib/iic-deploy/ track which steps are done.
#
# Usage:
#   bash deploy/setup.sh                # do it for real
#   bash deploy/setup.sh --dry-run      # show what would happen
#   bash deploy/setup.sh --uninstall    # tear down (keeps /srv/iic data)
#   bash deploy/setup.sh --reset        # tear down AND wipe /srv/iic data
#
# Prerequisites:
#   - Ubuntu Desktop 26.04 LTS (or 24.04 LTS) on a machine with ≥ 16 GB RAM
#     and ≥ 30 GB free disk.
#   - A user account with `sudo` access (NOT root login).
#   - Internet access (to pull Docker images).
#
# What this script does NOT do:
#   - It does NOT configure UFW / fail2ban / Tailscale / Cloudflare. Those are
#     production-hardening concerns; see `infra/linux/bootstrap.sh` for the
#     production posture. For prototype testing on a trusted LAN, the dev mode
#     here is enough.
#   - It does NOT obtain DeepSeek / WeChat / market-data API keys. The
#     containers will boot without them; calls to those services will simply
#     short-circuit (LLM cost-skip, notifier durable-redelivery on the queue).
#   - It does NOT light up FUTU or the Investment Board real-API surfaces.
#     Those are flag-gated and stay OFF by default.

set -euo pipefail

# --- locate repo root --------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

# --- options -----------------------------------------------------------------
DRY_RUN=0
ACTION=install
for arg in "$@"; do
  case "${arg}" in
    --dry-run)   DRY_RUN=1 ;;
    --uninstall) ACTION=uninstall ;;
    --reset)     ACTION=reset ;;
    -h|--help)
      sed -n '2,40p' "${BASH_SOURCE[0]}" | sed 's/^# \?//'
      exit 0
      ;;
    *)
      echo "Unknown argument: ${arg}" >&2
      exit 64
      ;;
  esac
done

MARKER_DIR="${IIC_DEPLOY_MARKER_DIR:-/var/lib/iic-deploy}"
DATA_ROOT="${IIC_DATA_ROOT:-/srv/iic}"
ENV_FILE="${REPO_ROOT}/.env"
COMPOSE_FILES=("-f" "${REPO_ROOT}/docker-compose.yml" "-f" "${REPO_ROOT}/docker-compose.dev.yml")

# --- helpers -----------------------------------------------------------------
COLOR_RESET='\033[0m'
COLOR_BLUE='\033[1;34m'
COLOR_GREEN='\033[1;32m'
COLOR_YELLOW='\033[1;33m'
COLOR_RED='\033[1;31m'

say()   { printf "${COLOR_BLUE}==>${COLOR_RESET} %s\n" "$*"; }
ok()    { printf "${COLOR_GREEN}OK${COLOR_RESET}  %s\n" "$*"; }
warn()  { printf "${COLOR_YELLOW}WARN${COLOR_RESET} %s\n" "$*"; }
fail()  { printf "${COLOR_RED}FAIL${COLOR_RESET} %s\n" "$*" >&2; exit 1; }

run() {
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    printf "  [dry-run] %s\n" "$*"
  else
    "$@"
  fi
}

step() {
  local name="$1"; shift
  if [[ -f "${MARKER_DIR}/${name}" ]]; then
    printf "${COLOR_GREEN}skip${COLOR_RESET} %s (already done)\n" "${name}"
    return 0
  fi
  say "[${name}]"
  "$@"
  if [[ "${DRY_RUN}" -eq 0 ]]; then
    sudo mkdir -p "${MARKER_DIR}"
    sudo touch "${MARKER_DIR}/${name}"
  fi
  ok "${name}"
}

require_sudo() {
  if ! sudo -n true 2>/dev/null; then
    say "This script needs sudo for OS-level installs (Docker, /srv/iic)."
    sudo -v || fail "sudo required"
  fi
}

# --- step: preflight checks --------------------------------------------------
do_preflight() {
  if [[ ! -f /etc/os-release ]]; then
    if [[ "${DRY_RUN}" -eq 1 ]]; then
      warn "/etc/os-release missing (dry-run on non-Linux host); continuing."
      PRETTY_NAME="(non-Linux dry-run)"
      ID="dry-run"
    else
      fail "/etc/os-release missing — is this Ubuntu?"
    fi
  else
    . /etc/os-release
  fi
  if [[ "${ID:-}" != "ubuntu" && "${ID_LIKE:-}" != *"debian"* && "${DRY_RUN}" -eq 0 ]]; then
    warn "OS is ${ID:-unknown} — script tested on Ubuntu; proceeding anyway."
  fi
  say "OS:        ${PRETTY_NAME:-unknown}"
  say "kernel:    $(uname -r)"
  say "user:      $(id -un) (uid $(id -u))"
  say "repo:      ${REPO_ROOT}"
  say "data dir:  ${DATA_ROOT}"
  say "env file:  ${ENV_FILE}"
  echo ""

  if [[ "$(id -u)" -eq 0 ]]; then
    warn "Running as root. Recommend running as a regular user with sudo."
  fi

  local mem_gb=""
  local disk_gb=""
  if command -v free >/dev/null 2>&1; then
    mem_gb="$(free -g 2>/dev/null | awk '/^Mem:/ {print $2}' || true)"
  fi
  disk_gb="$(df -BG --output=avail "${REPO_ROOT}" 2>/dev/null | tail -1 | tr -dc '0-9' || true)"
  if [[ -n "${mem_gb}" && "${mem_gb}" =~ ^[0-9]+$ && "${mem_gb}" -lt 12 ]]; then
    warn "Only ${mem_gb} G RAM detected; the full stack wants ≥ 16 G."
  fi
  if [[ -n "${disk_gb}" && "${disk_gb}" =~ ^[0-9]+$ && "${disk_gb}" -lt 25 ]]; then
    warn "Only ${disk_gb} G free disk on this partition; want ≥ 30 G."
  fi
}

# --- step: apt + base packages ----------------------------------------------
do_apt_base() {
  run sudo apt-get update -qq
  run sudo apt-get install -y --no-install-recommends \
    ca-certificates curl gnupg make git jq openssl python3-pip \
    apt-transport-https
}

# --- step: Docker Engine + Compose plugin ------------------------------------
do_docker() {
  # PHASE 1 — install (skipped if docker + compose are already present).
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    say "Docker + compose plugin already installed; skipping install."
  else
    # Try the official Docker apt repo first (latest stable). If the
    # codename has no Docker release yet (Ubuntu 26.04 may be too new),
    # fall back to the universe `docker.io` package which is older but
    # always available.
    local codename=""
    if [[ -f /etc/os-release ]]; then
      . /etc/os-release
      codename="${VERSION_CODENAME:-}"
    fi
    local repo_url="https://download.docker.com/linux/ubuntu"

    if curl -fsS -o /dev/null "${repo_url}/dists/${codename}/Release"; then
      say "Installing Docker CE from official repo (${codename})."
      run sudo install -m 0755 -d /etc/apt/keyrings
      run sudo bash -c "curl -fsSL ${repo_url}/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg"
      run sudo chmod a+r /etc/apt/keyrings/docker.gpg
      local arch; arch="$(dpkg --print-architecture)"
      run sudo bash -c "echo 'deb [arch=${arch} signed-by=/etc/apt/keyrings/docker.gpg] ${repo_url} ${codename} stable' > /etc/apt/sources.list.d/docker.list"
      run sudo apt-get update -qq
      run sudo apt-get install -y \
        docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin
    else
      warn "Docker has no apt release for ${codename} yet; falling back to docker.io from universe."
      run sudo apt-get install -y docker.io docker-compose-v2
    fi
  fi

  # PHASE 2 — group + service. Always runs, even when Docker was
  # pre-installed before setup.sh did. This is the load-bearing fix
  # for the "permission denied connecting to /var/run/docker.sock"
  # case on machines where Docker came with the OS image.
  local user; user="${SUDO_USER:-$(id -un)}"

  # Make sure the docker group exists (it normally does on Ubuntu, but
  # not always on minimal images).
  if ! getent group docker >/dev/null 2>&1; then
    run sudo groupadd docker
  fi

  # Add the user only if not already a member, to keep the run output quiet.
  if ! getent group docker | tr ',' '\n' | grep -qx "${user}"; then
    say "Adding '${user}' to the docker group."
    run sudo usermod -aG docker "${user}"
  else
    say "User '${user}' is already in the docker group."
  fi

  # Ensure the daemon is enabled + running.
  run sudo systemctl enable --now docker

  say "Docker ready. NOTE: if this is your first add to the docker group,"
  say "      the new membership isn't active in this shell yet — the"
  say "      script will auto-re-exec under 'sg docker' below."
}

# --- ensure: docker socket is reachable as the current user ------------------
# After `do_docker` adds us to the docker group, the new group is NOT yet
# active in this shell — `usermod -aG` only takes effect on next login.
# That's the "permission denied connecting to docker.sock" error a fresh
# `make setup` always hits.
#
# Fix: detect the case and re-exec ourselves under `sg docker -c …`, which
# spawns a subprocess with `docker` as a supplementary group right now.
# Markers under MARKER_DIR mean previously-finished steps (apt, docker,
# data_tree, secrets, flags) are skipped on the re-exec, so we pick up
# exactly where we left off.
ensure_docker_access() {
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    return 0
  fi

  # If docker info works as the current user, we're golden.
  if docker info >/dev/null 2>&1; then
    return 0
  fi

  # Maybe the daemon isn't running yet (rare — do_docker ran systemctl).
  if ! [ -S /var/run/docker.sock ]; then
    fail "/var/run/docker.sock is missing — is the docker daemon running? Try 'sudo systemctl start docker'."
  fi

  # Daemon is up but our session can't reach it.
  local user; user="${SUDO_USER:-$(id -un)}"

  # If the user isn't in the docker group at all (e.g., do_docker
  # short-circuited on a system where docker was pre-installed and an
  # older version of this script never added the user), self-heal: add
  # them now and proceed to the re-exec path.
  if ! getent group docker 2>/dev/null | tr ',' '\n' | grep -qx "${user}"; then
    say "User '${user}' is not in the docker group; adding now."
    run sudo usermod -aG docker "${user}"
  fi

  # Now they're in the group on disk; re-exec under sg docker so the
  # supplementary group becomes active for the rest of the run.
  if [[ -z "${IIC_SETUP_REEXEC_DONE:-}" ]]; then
    say "Docker group membership not active in this shell yet."
    say "Re-executing under 'sg docker' to pick up the new group..."
    export IIC_SETUP_REEXEC_DONE=1
    # `sg <group> -c "<cmd>"` runs <cmd> with <group> as the primary
    # group of the spawned process. Quote argv via printf %q so paths
    # with spaces (the common case — repo dir has spaces) survive.
    local quoted=""
    for a in "$@"; do
      quoted+="$(printf '%q ' "${a}")"
    done
    exec sg docker -c "bash $(printf '%q' "${BASH_SOURCE[0]}") ${quoted}"
  fi

  fail "Re-exec under 'sg docker' still can't reach /var/run/docker.sock. Log out, log back in, then re-run 'make setup'."
}

# --- step: data dir tree under /srv/iic --------------------------------------
do_data_tree() {
  local user; user="${SUDO_USER:-$(id -un)}"
  local subdirs=(
    pg chroma nats minio redis grafana loki prometheus
    prompts_versioned advice_ledger backup
    featureflags futu-audit-anchors
  )
  for d in "${subdirs[@]}"; do
    run sudo mkdir -p "${DATA_ROOT}/${d}"
  done
  run sudo chown -R "${user}":"${user}" "${DATA_ROOT}"
  run sudo chmod -R 750 "${DATA_ROOT}"
}

# --- step: secrets bootstrap (random pw + .env from template) ---------------
do_secrets() {
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    bash "${SCRIPT_DIR}/bootstrap-secrets.sh" --print-only > /dev/null
    say "[dry-run] would write ${ENV_FILE} + .deploy/postgres.env"
    return 0
  fi
  bash "${SCRIPT_DIR}/bootstrap-secrets.sh"
}

# --- step: write a default flags.yaml under /srv/iic/featureflags ------------
do_flags() {
  local flags_path="${DATA_ROOT}/featureflags/flags.yaml"
  if [[ -f "${flags_path}" ]]; then
    say "${flags_path} already exists; leaving it alone."
    return 0
  fi
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    printf "  [dry-run] would write %s\n" "${flags_path}"
    return 0
  fi
  cat > "${flags_path}" <<'YAML'
# IIC feature flags — dev defaults. Toggle values, then bounce
# `docker compose restart orchestrator agent_*` to pick them up
# (mtime-cached; takes effect within 2 s of the file change).
#
# Production checks each flag at every call site, defaulting to the
# value declared in packages/featureflags/featureflags/registry.py.

iic.featureflags.bootstrap: true
persona.live_mark.enabled: true
notifier.durable_redelivery.enabled: false
orchestrator.agent_breaker.enabled: true
orchestrator.use_nats_for_agent_calls: false

# Trading-room features — leave OFF for first-run testing. Flip ON
# after you've smoke-tested the substrate.
trading_room.event_triage.enabled: false
trading_room.investment_board.enabled: false

# FUTU — stays OFF until the Phase B security review is signed off.
agent_futu.enabled: false
YAML
  ok "Wrote dev defaults to ${flags_path}"
}

# --- step: build Docker images ----------------------------------------------
do_build() {
  run docker compose "${COMPOSE_FILES[@]}" build --pull
}

# --- step: bring up substrate + wait for postgres healthy --------------------
do_up_substrate() {
  run docker compose "${COMPOSE_FILES[@]}" up -d \
    nats postgres redis chroma minio
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    return 0
  fi
  say "Waiting for Postgres to be healthy..."
  local tries=60
  until docker compose "${COMPOSE_FILES[@]}" ps postgres 2>/dev/null \
        | grep -q "healthy"; do
    tries=$((tries - 1))
    if [[ ${tries} -le 0 ]]; then
      fail "Postgres did not reach healthy state in 5 minutes"
    fi
    sleep 5
  done
  ok "Postgres healthy"
}

# --- step: postgres roles + alembic migrations -------------------------------
do_migrate() {
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    say "[dry-run] would run deploy/run-migrations.sh (psql + alembic upgrade head)"
    return 0
  fi
  bash "${SCRIPT_DIR}/run-migrations.sh"
}

# --- step: bring up agents + dashboard ---------------------------------------
do_up_agents() {
  run docker compose "${COMPOSE_FILES[@]}" up -d
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    return 0
  fi
  say "Waiting 10 s for agents to settle..."
  sleep 10
}

# --- step: smoke-check every agent's /health --------------------------------
do_smoke() {
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    say "[dry-run] would run deploy/smoke-check.sh"
    return 0
  fi
  bash "${SCRIPT_DIR}/smoke-check.sh"
}

# --- step: print where to go next -------------------------------------------
do_next_steps() {
  cat <<'BANNER'

============================================================
  IIC is up.
============================================================

  Dashboard           http://localhost:4173
  Orchestrator API    http://localhost:8080/health
  Grafana (admin/admin) http://localhost:3000
  MinIO console       http://localhost:9001
  Postgres            localhost:5432  (user/pw in .env)

  Useful commands (from the repo root):
    make logs          # tail all container logs
    make logs SVC=orchestrator   # tail one service
    make health        # re-run smoke check
    make ps            # show container status
    make down          # stop everything (data preserved)
    make test          # run the Python test suite locally
    make migrate       # re-run alembic upgrade head

  To enable a real LLM:
    1. Get a DeepSeek API key (https://platform.deepseek.com)
    2. Edit .env: set DEEPSEEK_API_KEY=sk-...
    3. docker compose restart orchestrator agent_intelligence

  To enable the Investment Board (research-only, simulated):
    1. Edit /srv/iic/featureflags/flags.yaml:
         trading_room.event_triage.enabled: true
         trading_room.investment_board.enabled: true
    2. docker compose restart orchestrator agent_board

  Read DEPLOYMENT.md for the full walkthrough.

BANNER
}

# --- uninstall / reset modes -------------------------------------------------
do_uninstall() {
  say "Stopping IIC containers (data preserved)..."
  run docker compose "${COMPOSE_FILES[@]}" down --remove-orphans || true
  say "Done. Run 'bash deploy/setup.sh' again to bring it back up."
}

do_reset() {
  warn "RESET will DELETE all IIC data under ${DATA_ROOT}."
  warn "Press Ctrl-C in the next 10 seconds to abort."
  if [[ "${DRY_RUN}" -eq 0 ]]; then
    sleep 10
  fi
  run docker compose "${COMPOSE_FILES[@]}" down -v --remove-orphans || true
  run sudo rm -rf "${DATA_ROOT}"
  run sudo rm -rf "${MARKER_DIR}"
  run rm -f "${ENV_FILE}"
  ok "Reset complete. Run 'bash deploy/setup.sh' to start fresh."
}

# --- main --------------------------------------------------------------------
case "${ACTION}" in
  uninstall) do_uninstall; exit 0 ;;
  reset)     do_reset;     exit 0 ;;
  install)   ;;
esac

if [[ "${DRY_RUN}" -eq 0 ]]; then
  require_sudo
fi
do_preflight
echo ""

step apt_base       do_apt_base
step docker         do_docker

# After do_docker installs and adds us to the group, the rest of the
# script needs to talk to /var/run/docker.sock. The new group isn't
# active in *this* shell yet, so we may need to re-exec under sg docker.
ensure_docker_access "$@"

step data_tree      do_data_tree
step secrets        do_secrets
step flags          do_flags
step build          do_build
step up_substrate   do_up_substrate
step migrate        do_migrate
step up_agents      do_up_agents
step smoke          do_smoke

do_next_steps
