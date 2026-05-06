# ADR-0002 — Inter-agent bus: NATS JetStream

- **Status:** Accepted
- **Date:** 2026-05-06

## Context

Six agents + an orchestrator + a backtester need a durable, fan-out message bus. All run on a single 32 GB mini-PC. The backtester must subscribe to every `advice.*.v1` topic and replay reliably; the orchestrator must enforce idempotency. We considered:

1. **Redis Streams.** Lightest. Single binary. Limited durability story; KV bolt-on.
2. **NATS JetStream.** Durable streams + KV + clean fan-out semantics. Single binary, < 100 MB resident.
3. **Kafka.** Overkill. ZooKeeper / KRaft tax; tuning is its own job.
4. **RabbitMQ.** Mature but the fan-out story is heavier than NATS for this volume.

## Decision

NATS JetStream, single-node, on-host. Topics defined by `packages/data-bus/topics.py` and named per the convention in `workflows/00 §4`: lowercase dotted, ending in `.v{n}`.

The full topic registry (PLAN §7):

```
intel.{digest|dashboard|brief}.v1
advice.{fundamental|quant|persona.<slug>}.v1
backtest.{fill|daily|leaderboard}.v1
secretary.notify.v1
ops.{heartbeat|alert}.v1
```

JetStream durable storage at `/srv/iic/nats/` (bind mount, NAS-ready). Single replica is acceptable for v2.1; clustering is a v3 concern.

## Consequences

- ✅ Single binary, low memory, simple operability.
- ✅ Durable subjects survive restart — backtest replay works.
- ✅ Built-in KV + Object Store reduces the need to grow Redis.
- ⚠️ Single-node = no HA. Mitigated: the box is UPS-backed and restic-snapshotted; cold restore is < 60 min (success metric R6).
- ⚠️ Topic versioning is enforced socially (the trailing `.v{n}`) and structurally (PR review). Schema renames bump to `.v{n+1}` with parallel publish.
