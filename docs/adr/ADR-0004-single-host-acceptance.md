# ADR-0004 — Single-host SPOF acceptance for IIC v2.5

- **Status:** Accepted
- **Date:** 2026-05-08
- **Plan reference:** `plan/IIC_Development_Plan_v2.5_Combined.md` §T0.3

## Context

IIC v2.1 ships on a single Linux mini-PC by deliberate design (ADR-0003). The architecture review prior to v2.5 surfaced four single-points-of-failure (SPOFs) that the deployment shape inherently has:

1. **Orchestrator.** One container, one host. If it crashes mid-DAG, in-flight runs lose state above the idempotency cache.
2. **Postgres.** One Postgres instance. Loss = full restore from restic + re-replay of NATS streams since last RPO.
3. **NATS JetStream.** Single-node JetStream with file-backed streams. Loss = re-bootstrap + replay-from-backup (T1.7) but consumer state for in-flight messages is lost.
4. **Dashboard.** One Vite + FastAPI proxy. Loss = no UI, no `/why-plain`, no `/audit`. Functionally degrading, not catastrophic.

The v2.5 plan made an explicit choice: **document and accept these SPOFs rather than introduce HA early.** The first user (Ziwei) is one person on one home network. Two-node HA would require ≥ 1 additional box, mTLS between hosts, Patroni / etcd, NATS clustering, and operational expertise for which there is no upside until a second person depends on the system.

## Decision

We accept the four SPOFs above for IIC v2.5 (T0–T2). The acceptance is contingent on the following recovery story being kept green:

### Recovery substrate

- **`/srv/iic/*` bind-mount layout** (ADR-0003) — every stateful container's data is on the host filesystem, not inside the container.
- **Hourly restic snapshot** to external 4 TB USB-C HDD; nightly offsite to Backblaze B2. Restic is content-addressed so multi-host restore is a `restic restore` invocation, not a per-database playbook.
- **NATS JetStream backup cron** (v2.5 T1.7) — daily 03:00 local `nats stream backup --all /srv/iic/nats-backups/$(date +%F)`, rotated into MinIO under restic after 14 days.
- **Hash-chained advice ledger** with hourly chain-head verification (`runbook-advice-ledger-broken.md`).
- **Idempotency cache** in Redis with 24 h TTL per `(dag_id, trigger, fired_at)`; allows safe re-firing of DAGs after orchestrator crash without duplicating side effects.

### Stated RPO and RTO

| Component | RPO (data loss window) | RTO (recovery time) | Notes |
|---|---|---|---|
| Orchestrator | 0 (stateless) | ≤ 2 min | `docker compose up -d orchestrator`. In-flight DAG state is lost — re-fire from cron or `/run/<dag_id>?force=true`. |
| Postgres (advice ledger + `lake.*`) | ≤ 1 h | ≤ 15 min on a fresh box | Last hourly restic snapshot; restore via `infra/linux/restic/restore.sh`. |
| NATS JetStream | ≤ 24 h | ≤ 15 min | Streams reseeded from `infra/nats/init.sh` then replayed from T1.7 backup. In-flight consumer offsets are lost. |
| MinIO (briefs + transcripts) | ≤ 1 h | ≤ 15 min | restic-backed; bind-mount restore. |
| Chroma (persona memory) | ≤ 1 h | ≤ 15 min | restic-backed; rebuild from raw decision-log markdown if corruption is suspected. |
| Dashboard | 0 (stateless UI) | ≤ 2 min | Pulls latest from MinIO + Postgres on boot. |

**Combined cold-start on a fresh Linux box:** NAS bind-mount + `docker compose up -d` is ≤ 15 min wall-clock. DR drill (`infra/linux/dr-drill.sh`) is run quarterly and recorded in `docs/postmortems/`.

### Promotion triggers

The single-host posture is **revisited (not automatically replaced)** if any of:

1. **Second human user.** Adding a family-share read-only surface (T3.7c) keeps the SPOF posture; promoting any non-Ziwei user to write/notify level forces a re-evaluation.
2. **Compliance or audit obligation.** If IIC's audit log is ever required as primary evidence in a regulatory context, the hash-chain anchored to OpenTimestamps (C10) becomes load-bearing and we likely need a second-host hot replica of Postgres at minimum.
3. **Multi-region listener load.** Today the workload is bounded by Ziwei's watchlist (≤ 50 tickers). A 10× expansion + tick-driven trading-room (T3.2) may cause sustained > 60 % CPU; promote either the host (vertical) or the layout (horizontal) at that point.
4. **Persistent host-down events.** > 1 unplanned outage / quarter that exceeds RTO triggers an explicit re-evaluation of the single-host bet.

### Out of scope for this ADR

- **Active-active HA**. Not a v2.5 goal. Reconsidered post-T3 if any promotion trigger fires.
- **Postgres physical replication / Patroni**. Same — would require a second host.
- **NATS clustering**. Same. The cost of getting raft / JetStream HA right for one user does not pencil.
- **Application-level HA inside one host** (multiple orchestrator replicas behind a local load balancer). Would not protect against the host-level failure modes that drive RTO.

## Consequences

- ✅ The SPOFs are now documented, not implicit. Every runbook references this ADR for "what's the recovery story?"
- ✅ The recovery substrate is testable in CI (restic dry-run, NATS backup restore drill in `infra/linux/dr-drill.sh`).
- ✅ Future "do we need HA?" conversations have a written baseline to push against — adding HA must clear at least one promotion trigger.
- ⚠️ The system is honest about its failure modes; users (today: Ziwei) accept that an unrecoverable Postgres event has up to 1 h data loss.
- ⚠️ Operators must run the quarterly DR drill or this ADR's RTO numbers degrade silently.

## References

- `docs/runbooks/runbook-host-down.md`
- `docs/runbooks/runbook-advice-ledger-broken.md`
- `docs/runbooks/runbook-backup-failed.md`
- `infra/linux/dr-drill.sh`
- `infra/nas/migrate.sh`
- `plan/IIC_Development_Plan_v2.5_Combined.md` §T0.3, §T1.7, §C10
