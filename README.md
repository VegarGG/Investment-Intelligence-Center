# Investment Intelligence Center (IIC)

> Personal, always-on, agentic investment-advisory system. Six AI agents (Intelligence, Fundamental, Quant, Persona, Backtest, Secretary) collaborate and compete on a single Linux mini-PC. Suggestion-only — no real-money trading.
>
> **v2.1 substrate is in production. v2.5 — Investment Board, FUTU read-only multi-account, event-flow workflow, tier-staged delivery — is in progress (T0 + T1 partial shipped).**

## Specs

- [`plan/EXECUTIVE_SUMMARY_bilingual.md`](plan/EXECUTIVE_SUMMARY_bilingual.md) — bilingual elevator pitch.
- [`plan/IIC_Development_Plan_v2.5_Combined.md`](plan/IIC_Development_Plan_v2.5_Combined.md) — **active plan**.
- [`plan/PLAN_v2.1_Investment_Intelligence_Center.md`](plan/PLAN_v2.1_Investment_Intelligence_Center.md) — origin plan; substrate v2.5 builds on.
- [`workflows/`](workflows/) — self-contained vibe-coding briefs ([`00_INDEX_AND_CONVENTIONS.md`](workflows/00_INDEX_AND_CONVENTIONS.md) first).
- [`workflows/32_V2_5_T0_T1_CHANGELOG.md`](workflows/32_V2_5_T0_T1_CHANGELOG.md) — what's already shipped from v2.5 in this iteration.

## Build order

The v2.5 plan supersedes v2.1's phase mapping with a tier-staged contract: T0 prereqs → T1 correctness → T2 architecture (Investment Board + FUTU + event-flow) → T3 research depth. T1 must be in production ≥ 14 days before T2 begins.

| Tier | Items | Status |
|------|-------|--------|
| **T0 — Rollback substrate** | T0.1 featureflags • T0.2 persona source-of-truth • T0.3 SPOF ADR | ✅ Shipped |
| **T1 — Correctness, reliability, DAG coverage** | T1.1 live mark • T1.1d persona band derivation • T1.2 missing personas • T1.3 intel pipeline at startup • T1.4 notifier durable redelivery • T1.5 DAG coverage closure • T1.6 per-agent breaker • T1.7 NATS backup + restore drill • T1.8 memory caps • T1.9 cost-breaker behaviour • T1.10 PIT ingest • T1.11 markdown decision log + Backtest reflection • T1.12 walk-forward CI gate | ✅ Shipped |
| **Synthetic burn-in regime** | 4-phase replacement for the 14-day production-burn gate (chaos + walk-forward + observability + real-API cost-cap) | ✅ Shipped (phases 1–2 default; phases 3–4 real-integration-gated) |
| **T2 — Investment Board + FUTU + event-flow** | T2.0 NATS request-reply substrate • T2.2 plan.v1 schema • T2.7 FUTU mock-OpenD (B3.3a) | ✅ B3.1 + B3.2 + B3.3a shipped |
| T2 (remaining) | T2.1 Event-Triage Gate • T2.3 team_plan endpoints • T2.4 Investment Board • T2.5 live benchmarking • T2.6 trading-room brief • T2.7 real OpenD / B3.3b • T2.8 trading-room DAG • T2.9–T2.10 prompt upgrades | ⏳ Next iteration |
| **T3 — Research depth** | Options-flow team, on-chain, geopolitics, BL portfolio, mobile app, … | ⏳ Gated on T2 + 30 d soak |

For the v2.1 phase mapping (still relevant — it documents the substrate v2.5 builds on), see workflow 00.

## Disclaimer

For personal research only. Not investment advice. IIC is not a registered investment advisor.
