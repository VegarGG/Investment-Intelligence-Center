#!/usr/bin/env bash
# IIC v2.1 — host bootstrap (workflow 01 §5.2)
#
# Idempotent provisioning for a fresh Ubuntu 24.04 LTS Server (Debian 12 OK).
# Re-running on a configured box is a no-op. Marker files in
# /var/lib/iic-bootstrap/ track which steps have completed.
#
# Run as a user with sudo. Root login should remain disabled.
#
#   sudo bash infra/linux/bootstrap.sh             # apply
#   sudo bash infra/linux/bootstrap.sh --dry-run   # show what would be done

set -euo pipefail

DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

MARKER_DIR=/var/lib/iic-bootstrap
mkdir -p "$MARKER_DIR"

step() {
  local name="$1"; shift
  if [[ -f "$MARKER_DIR/$name" ]]; then
    echo "[skip ] $name (already done)"
    return 0
  fi
  echo "[run  ] $name"
  if [[ "$DRY_RUN" == 1 ]]; then
    echo "       (dry-run; would execute)"
    return 0
  fi
  "$@"
  touch "$MARKER_DIR/$name"
}

run() {
  if [[ "$DRY_RUN" == 1 ]]; then
    echo "       + $*"
  else
    "$@"
  fi
}

# ---- 1. apt update + upgrade ------------------------------------------------
do_apt_update() {
  run apt-get update
  run apt-get -y full-upgrade
}

# ---- 2. Docker CE + Compose plugin from official repo -----------------------
do_docker() {
  if command -v docker >/dev/null 2>&1; then
    return 0
  fi
  run apt-get install -y ca-certificates curl gnupg
  run install -m 0755 -d /etc/apt/keyrings
  run bash -c 'curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg'
  run chmod a+r /etc/apt/keyrings/docker.gpg
  run bash -c 'echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" > /etc/apt/sources.list.d/docker.list'
  run apt-get update
  run apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
}

# ---- 3. iic user + docker group --------------------------------------------
do_user() {
  if ! id -u iic >/dev/null 2>&1; then
    run useradd -m -s /bin/bash -G sudo iic
  fi
  run usermod -aG docker iic
  # passwordless sudo for `docker compose` only
  cat > /etc/sudoers.d/iic-docker <<'SUDOEOF'
iic ALL=(ALL) NOPASSWD: /usr/bin/docker compose *
iic ALL=(ALL) NOPASSWD: /usr/bin/systemctl start iic.service, /usr/bin/systemctl stop iic.service, /usr/bin/systemctl restart iic.service
SUDOEOF
  run chmod 440 /etc/sudoers.d/iic-docker
}

# ---- 4. Install supporting tools -------------------------------------------
do_tools() {
  run apt-get install -y \
    tailscale restic ufw fail2ban chrony apcupsd unattended-upgrades \
    prometheus-node-exporter sops age jq rsync zram-tools nfs-common smartmontools
}

# ---- 5. UFW firewall --------------------------------------------------------
do_ufw() {
  run ufw --force reset
  run ufw default deny incoming
  run ufw default allow outgoing
  run ufw allow from 192.168.0.0/16 to any port 22 proto tcp
  run ufw allow from 192.168.0.0/16 to any port 80 proto tcp
  run ufw allow from 192.168.0.0/16 to any port 443 proto tcp
  run ufw allow in on tailscale0
  run ufw --force enable
}

# ---- 6. fail2ban ------------------------------------------------------------
do_fail2ban() {
  cat > /etc/fail2ban/jail.d/sshd.local <<'F2BEOF'
[sshd]
enabled = true
maxretry = 4
findtime = 10m
bantime  = 1h
F2BEOF
  run systemctl enable --now fail2ban
}

# ---- 7. Unattended security upgrades ---------------------------------------
do_unattended() {
  cat > /etc/apt/apt.conf.d/50unattended-upgrades <<'UAEOF'
Unattended-Upgrade::Allowed-Origins {
  "${distro_id}:${distro_codename}-security";
  "${distro_id}ESMApps:${distro_codename}-apps-security";
  "${distro_id}ESM:${distro_codename}-infra-security";
};
Unattended-Upgrade::Automatic-Reboot "false";
UAEOF
  cat > /etc/apt/apt.conf.d/20auto-upgrades <<'AUEOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
AUEOF
  run systemctl enable --now unattended-upgrades
}

# ---- 8. /srv/iic directory tree (bind-mount roots, NAS-ready) --------------
do_srv_tree() {
  for d in pg chroma nats minio redis grafana loki prometheus \
           prompts_versioned advice_ledger backup; do
    run mkdir -p "/srv/iic/$d"
  done
  run chown -R iic:iic /srv/iic
  run chmod -R 750 /srv/iic
}

# ---- 9. External 4 TB USB HDD mounted at /srv/iic/backup-hdd ----------------
do_backup_hdd() {
  run mkdir -p /srv/iic/backup-hdd
  echo "  NOTE: edit /etc/fstab to UUID-pin the external HDD."
  echo "        run \`blkid\` to read the UUID, then add:"
  echo "        UUID=<...> /srv/iic/backup-hdd ext4 defaults,nofail 0 2"
}

# ---- 10. systemd unit -------------------------------------------------------
do_systemd() {
  run install -m 0644 "$(dirname "$0")/iic.service" /etc/systemd/system/iic.service
  run install -m 0755 "$(dirname "$0")/iic-decrypt-secrets.sh" /usr/local/bin/iic-decrypt-secrets.sh
  run mkdir -p /opt/iic
  echo "  NOTE: docker-compose.yml must be deployed to /opt/iic/docker-compose.yml"
  echo "        and the encrypted .env to /opt/iic/.env.sops before iic.service starts."
  run systemctl daemon-reload
  run systemctl enable iic.service
}

# ---- 11. Tailscale (interactive on first run) ------------------------------
do_tailscale() {
  if tailscale status >/dev/null 2>&1; then
    return 0
  fi
  echo "  Run 'tailscale up --ssh --hostname=iic-host' interactively to enroll."
}

# ---- 12. Self-test ----------------------------------------------------------
do_selftest() {
  echo "  docker:        $(docker --version 2>/dev/null || echo MISSING)"
  echo "  compose:       $(docker compose version 2>/dev/null || echo MISSING)"
  echo "  tailscale:     $(tailscale version 2>/dev/null | head -1 || echo NOT-LOGGED-IN)"
  echo "  restic:        $(restic version 2>/dev/null || echo MISSING)"
  echo "  apcupsd:       $(apcaccess status 2>/dev/null | head -1 || echo NOT-CONFIGURED)"
  echo "  node_exporter: $(systemctl is-active prometheus-node-exporter 2>/dev/null || echo INACTIVE)"
}

# ---- main -------------------------------------------------------------------
echo "IIC v2.1 host bootstrap (dry-run=$DRY_RUN)"
echo "----------------------------------------"

step apt-update    do_apt_update
step docker        do_docker
step user          do_user
step tools         do_tools
step ufw           do_ufw
step fail2ban      do_fail2ban
step unattended    do_unattended
step srv-tree      do_srv_tree
step backup-hdd    do_backup_hdd
step systemd       do_systemd
step tailscale     do_tailscale
do_selftest    # always re-run self-test, never marked complete

echo
echo "Done. Markers in $MARKER_DIR. Re-running this script is a no-op."
