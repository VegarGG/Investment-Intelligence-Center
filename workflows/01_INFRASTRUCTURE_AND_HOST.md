# Workflow 01 — Infrastructure & Host

> **Depends On:** none (this is the substrate).
> **Owns:** the physical machine, the Linux OS layer, the Docker substrate, and every conventions that lets future workflows land cleanly.
> **Status:** Final.

---

## 1. Purpose

Stand up a single Linux mini PC that runs the full IIC stack with the following non-negotiable properties:

1. **Always-on.** UPS-backed, auto-recovering, monitored.
2. **Zero-touch NAS migration.** Day-1 storage layout is identical to the layout we'd want post-NAS, so adding a NAS later is a `mount` change, not a refactor.
3. **No public attack surface.** Remote access is exclusively Tailscale (or WireGuard).
4. **Idempotent host provisioning.** A single shell script (`infra/linux/bootstrap.sh`) takes a freshly-installed Ubuntu Server to "ready for `docker compose up`" with no manual steps.

This document is the entire substrate brief. After you finish it, every other workflow doc assumes its outputs.

---

## 2. Ground Truth

### 2.1 Recommended Hardware

📌 **Reference build (the assumed one in all sizing tables):**

| Component | Spec | Approx. price |
|-----------|------|---------------|
| Mini PC | Beelink SER8 — Ryzen 7 8845HS · 32 GB DDR5-5600 · 1 TB NVMe (slot 1) · empty NVMe slot 2 · 2× 2.5 GbE | $700 |
| External backup | 4 TB USB-C HDD (Seagate Backup Plus or WD Elements) | $110 |
| UPS | CyberPower CP1500PFCLCD (1000 W AVR, USB-to-host) | $180 |
| Networking | Reserved DHCP at `192.168.1.50`, Cat-6 patch | n/a |

**Idle ≈ 10 W · Load ≈ 35 W · Headroom for 2× workload growth.**

📌 **Minimum spec to run everything (do not go below):** 4-core modern CPU, 16 GB RAM, 1 TB NVMe, gigabit Ethernet, UPS.

### 2.2 Operating System

- **Distro:** Ubuntu 24.04 LTS Server. Debian 12 acceptable.
- **Install profile:** headless, OpenSSH only, no snaps, no GUI.
- **Filesystem:** single ext4 partition on NVMe. `/srv/iic` is a directory, not its own partition (easier to resize).
- **Swap:** 8 GB zram-swap.
- **Time:** `chrony` synced to local-region NTP pool.

### 2.3 Privilege Model

- User `iic` with `sudo`. Password sudo for everything **except** `docker compose` (passwordless via a `sudoers.d` snippet).
- Root login disabled (`PermitRootLogin no` in `sshd_config`).
- SSH key only — `PasswordAuthentication no`.

### 2.4 Networking & Security

- Static internal IP `192.168.1.50` reserved on the router DHCP table.
- **No port forwarding.** All inbound to the box is Tailscale-only.
- `ufw` policy: deny incoming by default; allow `22, 80, 443` from `192.168.0.0/16`; Tailscale interface (`tailscale0`) fully allowed.
- `fail2ban` enabled with the `sshd` jail.
- `unattended-upgrades` for security patches.
- Optional Cloudflare Tunnel for the dashboard (TLS terminated at Cloudflare; no inbound holes on the box).

### 2.5 Container Runtime

- Docker Engine 26+ from the official Docker apt repo (not the distro package).
- `docker-compose-plugin` (Compose v2 CLI). All services defined in a single root `docker-compose.yml`.
- Compose **must use bind mounts**, not Docker named volumes. Every persistent path is `/srv/iic/<service>:/var/lib/<service>` (or whatever the service expects internally).

### 2.6 Filesystem Layout (the NAS-Ready contract)

📌 **GROUND TRUTH — every persistent service writes here:**

```
/srv/iic/
├── pg/                  # Postgres + TimescaleDB data dir
├── chroma/              # Vector store
├── nats/                # JetStream durable storage
├── minio/               # Object store
├── redis/               # Redis AOF
├── grafana/, loki/, prometheus/
├── prompts_versioned/   # Append-only prompt history
├── advice_ledger/       # Hash-chained advice records
└── backup/              # restic repo target
```

🔁 **NAS-READY:** this directory is the entire migration boundary. Switching to a NAS = `rsync /srv/iic/ nas:/volume1/iic/` then `mount -t nfs nas:/volume1/iic /srv/iic`. **The Compose file is never touched.**

### 2.7 Backups

- **Primary:** `restic` daily at 03:00 local on `/srv/iic`, excluding `pg/wal` (Postgres has its own WAL archive).
- **Local repo:** `/srv/iic/backup-hdd` (mounted from the 4 TB external USB drive — separate physical disk from `/srv/iic` so a single-disk failure doesn't kill both).
- **Offsite:** Backblaze B2 (`B2_ACCOUNT_ID`, `B2_ACCOUNT_KEY`), encrypted by restic. Cost ≈ $6/TB/mo.
- **Retention:** 7 daily, 4 weekly, 12 monthly, 3 yearly.
- **Postgres extras:** logical `pg_dump` weekly + WAL archiving daily into `/srv/iic/pg/wal-archive`.

### 2.8 Auto-Boot & Recovery

- Single systemd unit: `/etc/systemd/system/iic.service`.
- `ExecStartPre=/usr/local/bin/iic-decrypt-secrets.sh` (sops decrypt of `.env`).
- `ExecStart=/usr/bin/docker compose -f /opt/iic/docker-compose.yml up -d`.
- `ExecStop=/usr/bin/docker compose -f /opt/iic/docker-compose.yml down`.
- `Restart=always`, `RestartSec=15s`.
- UPS daemon (`apcupsd` or `nut`) signals the box to shut down at ≤ 20% battery.

### 2.9 Hardware Telemetry

- `node_exporter` exposes CPU temp, NVMe SMART, fan RPM, RAM, network counters to Prometheus.
- Alert rules (defined in `30_OBSERVABILITY_AND_EVAL.md`) fire on:
  - NVMe wear > 80%
  - NVMe temp sustained > 70 °C
  - CPU sustained > 90 °C for 5 min
  - UPS battery ≤ 50%
  - Disk free on `/srv/iic` < 15%

---

## 3. Architecture

```
┌──────────────────────────────────────────────┐
│           Beelink SER8 (Ubuntu 24.04)        │
│                                              │
│   ┌────────────────────────────────────┐    │
│   │ systemd → docker compose up        │    │
│   └────────────────────────────────────┘    │
│   ┌──────┐ ┌──────┐ ┌────────┐ ┌───────┐   │
│   │ NATS │ │  PG  │ │Chroma  │ │ MinIO │   │
│   └──────┘ └──────┘ └────────┘ └───────┘   │
│   (each → bind-mount under /srv/iic/...)    │
│                                              │
│   ┌──────────────────────────────────┐      │
│   │ orchestrator + 6 agent containers│      │
│   └──────────────────────────────────┘      │
│                                              │
│   ┌────────┐  ┌──────┐  ┌────────┐          │
│   │Grafana │  │ Loki │  │Prometh.│          │
│   └────────┘  └──────┘  └────────┘          │
│                                              │
│   restic → /srv/iic/backup-hdd → B2 nightly │
└──────────────────────────────────────────────┘
            │ (Tailscale only)
            ▼
   ┌──────────────────────┐
   │ Ziwei laptop / phone │
   └──────────────────────┘
```

---

## 4. Module Layout

```
infra/
├── linux/
│   ├── bootstrap.sh           # idempotent provisioning
│   ├── uninstall.sh           # clean rollback
│   ├── iic.service            # systemd unit
│   ├── iic-decrypt-secrets.sh # sops decrypt
│   ├── ufw-rules.sh
│   ├── apcupsd.conf
│   └── restic/
│       ├── backup.sh
│       ├── prune.sh
│       └── restore.sh
├── nas/
│   ├── migrate.sh             # dry-run by default
│   └── README.md
└── observability/
    └── (see 30_OBSERVABILITY_AND_EVAL.md)

docker-compose.yml              ← root of repo; built incrementally per workflow doc
.env.example                    ← root of repo
```

---

## 5. Workflow Steps

### Step 5.1 — Hardware bring-up

1. Unbox SER8. Install second NVMe if you bought one (slot 2). Plug into UPS, not wall.
2. Boot from a Ubuntu 24.04 Server USB. Choose minimal install + OpenSSH.
3. Set hostname to `iic-host`. Create user `iic`.
4. After first boot, copy your SSH public key to `~iic/.ssh/authorized_keys`. Disable password SSH.
5. On the router: reserve DHCP for the box's MAC at `192.168.1.50`.
6. Confirm `ssh iic@192.168.1.50` works from your laptop.

### Step 5.2 — `infra/linux/bootstrap.sh`

The script must be **idempotent**. Re-running it should be a no-op if the box is already configured. Required actions in order:

1. `apt update && apt full-upgrade -y`.
2. Install Docker CE + Compose plugin from the official Docker apt repo.
3. Add `iic` to the `docker` group.
4. Install: `tailscale`, `restic`, `ufw`, `fail2ban`, `chrony`, `apcupsd` (or `nut`), `unattended-upgrades`, `prometheus-node-exporter`, `sops`, `age`, `jq`, `rsync`.
5. Configure `ufw` per §2.4 (idempotent: `ufw --force reset` first).
6. Configure `fail2ban` with the `sshd` jail enabled.
7. Configure `unattended-upgrades` for security patches only.
8. Create the directory tree:
   ```
   /srv/iic/{pg,chroma,nats,minio,redis,grafana,loki,prometheus,prompts_versioned,advice_ledger,backup}
   ```
   `chown -R iic:iic /srv/iic`.
9. Mount the 4 TB USB drive at `/srv/iic/backup-hdd` via `/etc/fstab` (UUID-pinned).
10. Install `iic.service` and `iic-decrypt-secrets.sh` to `/etc/systemd/system/` and `/usr/local/bin/` respectively.
11. Enable + start: `systemctl enable --now iic.service`.
12. Run `tailscale up --ssh --hostname=iic-host` (interactive; print URL).
13. Run a self-test: `docker --version`, `docker compose version`, `tailscale status`, `restic version`, `apcaccess status` — fail loudly if any returns non-zero.

🧪 **VIBE-PROMPT — bootstrap.sh:**
> Generate `infra/linux/bootstrap.sh` per §5.2 of `01_INFRASTRUCTURE_AND_HOST.md`. Idempotent, runnable from a fresh Ubuntu 24.04 install. Use `set -euo pipefail` and a `step()` helper that echoes a banner before each phase. Detect previously-completed steps via marker files in `/var/lib/iic-bootstrap/`. Provide a matching `infra/linux/uninstall.sh` that rolls back cleanly (down systemd unit, remove iic user from docker group, remove UFW rules, leave `/srv/iic` data alone). Honor every block marked GROUND TRUTH literally. Ask before deviating.

### Step 5.3 — Compose skeleton

The root `docker-compose.yml` has the substrate services only at this point. Agent services will be added by their respective workflow docs.

```yaml
version: "3.9"

x-iic-base: &iic-base
  restart: unless-stopped
  env_file: .env

services:
  nats:
    <<: *iic-base
    image: nats:2.10-alpine
    command: ["-js", "-sd", "/data"]
    volumes: ["/srv/iic/nats:/data"]
    ports: ["4222:4222", "8222:8222"]

  postgres:
    <<: *iic-base
    image: timescale/timescaledb-ha:pg16
    environment:
      POSTGRES_PASSWORD_FILE: /run/secrets/pg_pw
    volumes: ["/srv/iic/pg:/var/lib/postgresql/data"]
    ports: ["5432:5432"]

  chroma:
    <<: *iic-base
    image: chromadb/chroma:0.5
    volumes: ["/srv/iic/chroma:/chroma/.chroma"]
    ports: ["8000:8000"]

  minio:
    <<: *iic-base
    image: minio/minio:RELEASE.2026-04-01T00-00-00Z
    command: server /data --console-address ":9001"
    volumes: ["/srv/iic/minio:/data"]
    ports: ["9000:9000", "9001:9001"]

  redis:
    <<: *iic-base
    image: redis:7-alpine
    command: ["redis-server", "--appendonly", "yes"]
    volumes: ["/srv/iic/redis:/data"]

  grafana:
    <<: *iic-base
    image: grafana/grafana:11
    ports: ["3000:3000"]
    volumes: ["/srv/iic/grafana:/var/lib/grafana"]

  loki:
    <<: *iic-base
    image: grafana/loki:3
    ports: ["3100:3100"]
    volumes: ["/srv/iic/loki:/loki"]

  prometheus:
    <<: *iic-base
    image: prom/prometheus:v2.55
    volumes:
      - "./infra/observability/prometheus.yml:/etc/prometheus/prometheus.yml"
      - "/srv/iic/prometheus:/prometheus"
    ports: ["9090:9090"]

  cadvisor:
    <<: *iic-base
    image: gcr.io/cadvisor/cadvisor:v0.49.1
    privileged: true
    volumes:
      - "/:/rootfs:ro"
      - "/var/run:/var/run:ro"
      - "/sys:/sys:ro"
      - "/var/lib/docker:/var/lib/docker:ro"
```

### Step 5.4 — Secrets via sops + age

1. Generate an age key on the host: `age-keygen -o /etc/iic/age.key` (root-owned, mode 600).
2. Author `.env.example` with every key the system needs, all values stubbed.
3. Author `.env.sops.yaml` (sops config) listing the age recipient.
4. Encrypt the production `.env` with sops; commit the encrypted version, never the plaintext.
5. `iic-decrypt-secrets.sh` (run as `ExecStartPre` of `iic.service`) decrypts to `/run/iic/.env` (tmpfs) so the file is never on disk in plaintext.

### Step 5.5 — Backups

1. Author `infra/linux/restic/backup.sh`. Initialize two repos: `local` at `/srv/iic/backup-hdd/restic` and `b2` at `b2:iic-restic`. Both are restic-encrypted.
2. Backup runs daily at 03:00 local (cron or systemd timer).
3. Postgres pre-backup hook: `pg_dump --format=custom` of every database to `/srv/iic/pg/dumps/`.
4. ChromaDB pre-backup hook: `cp -a /srv/iic/chroma /srv/iic/chroma-snapshot-$(date +%F)`.
5. Author `infra/linux/restic/restore.sh` — accepts `--repo local|b2`, `--snapshot ID`, `--target PATH`. The DR drill in workflow `31_PRODUCTION_HARDENING.md` runs this end-to-end.

### Step 5.6 — NAS migration script (dry-run only at this stage)

Build `infra/nas/migrate.sh` even before any NAS is purchased. It runs in `--dry-run` mode by default, simulating the migration into `/tmp/iic-dryrun/`. CI executes the dry-run on every commit so we know it stays valid as the system grows.

```bash
#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---dry-run}"
NAS_HOST="${NAS_HOST:-nas.local}"
NAS_PATH="${NAS_PATH:-/volume1/iic}"
SRV="/srv/iic"

preflight() {
  command -v rsync >/dev/null
  if [[ "$MODE" == "--apply" ]]; then
    command -v showmount >/dev/null
    showmount -e "$NAS_HOST" | grep -q "$NAS_PATH" || { echo "NFS export not found"; exit 1; }
    df --output=avail "$SRV" | tail -1
  fi
}

stop_stack() { sudo systemctl stop iic.service; }
start_stack(){ sudo systemctl start iic.service; }

migrate() {
  if [[ "$MODE" == "--dry-run" ]]; then
    rsync -aHAX --dry-run --info=progress2 "$SRV/" "/tmp/iic-dryrun/"
  else
    rsync -aHAX --info=progress2 "$SRV/" "$NAS_HOST:$NAS_PATH/"
    grep -q "$NAS_PATH" /etc/fstab || \
      echo "$NAS_HOST:$NAS_PATH $SRV nfs vers=4.1,_netdev,hard,timeo=600,retrans=2 0 0" \
      | sudo tee -a /etc/fstab
    sudo umount "$SRV" || true
    sudo mount "$SRV"
  fi
}

postflight() {
  for c in nats postgres chroma minio redis orchestrator agent_intelligence \
           agent_fundamental agent_quant agent_persona agent_backtest agent_secretary; do
    docker compose -f /opt/iic/docker-compose.yml ps "$c" | grep -q "Up"
  done
}

preflight
stop_stack
migrate
[[ "$MODE" == "--apply" ]] && start_stack && postflight || true
echo "Done in mode: $MODE"
```

⚠️ **NFS + Postgres caveat.** Postgres on NFS is fine on NFSv4.1+ with `hard,nolock` semantics, but only if the NAS storage layer is reliable. If unsure, run a hybrid mode where Postgres data dir stays at `/srv/iic-local/pg` while everything else moves to NFS. The migrate script supports this via `KEEP_PG_LOCAL=1`.

### Step 5.7 — Disaster recovery drill (rehearse before going live)

1. Pick a scratch USB SSD or a second mini PC.
2. Boot Ubuntu, run `bootstrap.sh`.
3. `restic restore --repo b2:iic-restic --target /srv/iic latest`.
4. `systemctl start iic.service`.
5. Confirm: WeCom briefs bot delivers a test brief within 60 minutes; orchestrator heartbeat present; leaderboard renders.

The drill must succeed unattended end-to-end inside one hour. Document the actual elapsed time in `docs/runbooks/dr-2026-XX-XX.md`.

### Step 5.8 — Tailscale and remote access

1. `tailscale up --ssh --hostname=iic-host`.
2. Optional: enable subnet routing if you want LAN devices reachable through Tailscale: `tailscale up --advertise-routes=192.168.1.0/24`.
3. (Optional) Cloudflare Tunnel for the dashboard, scoped to `dashboard.iic.<your-domain>`. The tunnel terminates TLS at Cloudflare and POSTs to `localhost:5173` over the tunnel — zero inbound holes on the box.

---

## 6. Vibe Prompts (paste-ready)

🧪 **Repo bootstrap (one-shot):**
> Create the IIC monorepo per `00_INDEX_AND_CONVENTIONS.md` §2. Python 3.12 with Poetry; `apps/` and `packages/`. Wire Ruff, Black, Mypy strict. Stub each agent under `apps/` with `health()` and `process(event)`. Build `docker-compose.yml` per `01_INFRASTRUCTURE_AND_HOST.md` §5.3. ALL volumes are bind mounts under `/srv/iic/<service>` — no Docker named volumes. Add `.env.example` mirroring the GROUND TRUTH env keys referenced in any workflow doc. Commit message: `feat: scaffold monorepo`.

🧪 **Host bootstrap script:**
> Generate `infra/linux/bootstrap.sh` per §5.2. Idempotent. Use marker files in `/var/lib/iic-bootstrap/` to skip completed steps. Include a self-test phase at the end. Provide a `--dry-run` mode that prints what it *would* do.

🧪 **NAS migrate (dry-run gate):**
> Generate `infra/nas/migrate.sh` per §5.6 and a GitHub Actions workflow `.github/workflows/nas-dryrun.yml` that runs `infra/nas/migrate.sh --dry-run` on every push, using a synthetic `/srv/iic` populated by the test fixture. Fail the build on non-zero exit.

🧪 **Backup + restore scripts:**
> Generate `infra/linux/restic/backup.sh`, `prune.sh`, and `restore.sh` per §5.5. Backup script must include Postgres `pg_dump` + ChromaDB snapshot pre-hooks. Restore script accepts `--repo local|b2`, `--snapshot ID`, `--target PATH`. All three are systemd-timer-friendly (no interactive prompts, exit codes are correct).

---

## 7. Acceptance Criteria

A coding agent (or you) is **done with this workflow** when every line below is true:

- [ ] `ssh iic@iic-host` works from a Tailscale-only laptop. Password SSH is disabled, root SSH is disabled.
- [ ] `bootstrap.sh` is fully idempotent — re-running it on a configured box yields zero changes.
- [ ] `systemctl status iic.service` shows `active (running)` and the unit auto-starts after `reboot`.
- [ ] `docker compose ps` shows nats, postgres, chroma, minio, redis, grafana, loki, prometheus, cadvisor all `Up (healthy)`.
- [ ] `ufw status verbose` matches the §2.4 rules byte-for-byte.
- [ ] `restic snapshots --repo /srv/iic/backup-hdd/restic` shows a snapshot from the last 24 h. Same for the B2 repo.
- [ ] `restic restore` of yesterday's snapshot to `/tmp/restore-test` completes in < 30 min.
- [ ] `bash infra/nas/migrate.sh --dry-run` exits zero in CI.
- [ ] `apcaccess status` shows the UPS attached, ON-LINE, with battery > 90%.
- [ ] Grafana **Host** dashboard panel "NVMe wear" reads < 5% on day 1.

---

## 8. Risks & Gotchas

⚠️ **Consumer NVMe wear.** The shipped 1 TB SSD is consumer-grade. Monitor `nvme smart-log` weekly; replace before crossing 80% wear. Alert at 70%.

⚠️ **Non-ECC RAM.** SER8 is non-ECC. Run `memtester` for 2 hours at install time and after any RAM upgrade. Re-run yearly during the DR drill.

⚠️ **Compose v1 vs v2.** Always `docker compose` (space). The legacy `docker-compose` (hyphen) binary should NOT be installed; it has different volume semantics in edge cases.

⚠️ **fstab UUID drift.** When swapping the external HDD, the UUID changes — `iic.service` will fail at boot. Provide a runbook to update `/etc/fstab` after any drive swap.

⚠️ **`/srv/iic` permissions on NAS.** Synology/QNAP default to UID 1024+ and squash root. The migrate script handles this with `--no-perms --chown=iic:iic` rsync flags, but verify after first apply.

⚠️ **Unattended upgrades and Postgres major versions.** `unattended-upgrades` is configured for security patches only — never major Postgres or kernel upgrades, which we want manual control over.

⚠️ **Tailscale key expiry.** Default key lifetime is 180 days. Use a tagged auth key with `--ssh` and disable expiry for the host node.

---

## 9. Cross-References

- Storage volumes by service: `02_DATA_LAYER.md` §2.
- Container additions to Compose: every `apps/agent_*` workflow doc adds its own service block.
- Observability sidecars (`node_exporter`, `cadvisor`, `postgres_exporter`, `nats_exporter`): `30_OBSERVABILITY_AND_EVAL.md`.
- Secrets management deep dive (sops + age): `31_PRODUCTION_HARDENING.md` §3.
- DR drill runbook: `31_PRODUCTION_HARDENING.md` §5.

---

## Changelog

- **v1.0** — Extracted from `PLAN_v2.1` §0, §8, parts of §13, and Appendices B and C. Calendar-week references removed; replaced with dependency ordering and step sequence.
