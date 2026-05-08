# Architecture Decision Records

| # | Decision |
|---|----------|
| [ADR-0001](ADR-0001-deepseek-v4-routing.md) | LLM strategy — DeepSeek v4 (Pro + Flash) with API-first routing |
| [ADR-0002](ADR-0002-nats-jetstream.md) | Inter-agent bus — NATS JetStream |
| [ADR-0003](ADR-0003-minipc-linux-nas-ready.md) | Host — single Linux mini-PC with NAS-ready storage |
| [ADR-0004](ADR-0004-single-host-acceptance.md) | Single-host SPOF acceptance for v2.5 — RPO/RTO + promotion triggers |

New ADRs use the filename convention `ADR-XXXX-slug.md` (workflows/00 §4). Each ADR lists Status / Date / Context / Decision / Consequences. Once accepted, ADRs are append-only — supersession is recorded in the new ADR's "Supersedes" field, never by editing history.
