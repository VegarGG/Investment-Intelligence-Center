#!/usr/bin/env bash
# IIC v2.1 — clean rollback of bootstrap.sh changes.
#
# Tears down systemd, removes UFW rules, removes the iic user from docker
# group, removes the sudoers snippet. **Leaves /srv/iic data alone.** If you
# really want to wipe data, do so explicitly with rm -rf afterwards.

set -euo pipefail

if systemctl list-unit-files | grep -q '^iic.service'; then
  systemctl disable --now iic.service || true
  rm -f /etc/systemd/system/iic.service
  systemctl daemon-reload
fi

rm -f /usr/local/bin/iic-decrypt-secrets.sh
rm -f /etc/sudoers.d/iic-docker
rm -f /etc/fail2ban/jail.d/sshd.local

if id -u iic >/dev/null 2>&1; then
  gpasswd -d iic docker || true
fi

if command -v ufw >/dev/null; then
  ufw --force reset
fi

rm -rf /var/lib/iic-bootstrap

echo "Uninstall complete. /srv/iic data preserved."
