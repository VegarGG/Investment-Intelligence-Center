# Investment Intelligence Center (IIC)

> Personal, always-on, agentic investment-advisory system. Six AI agents (Intelligence, Fundamental, Quant, Persona, Backtest, Secretary) collaborate and compete on a single Linux mini-PC. Suggestion-only — no real-money trading.
>
> **v2.1 substrate is in production. v2.5 — Investment Board, FUTU read-only multi-account, event-flow workflow, tier-staged delivery — is in progress (T0 + T1 partial shipped).**

## Quick start (fresh Ubuntu 26.04 LTS)

```bash
git clone https://github.com/VegarGG/Investment-Intelligence-Center
cd Investment-Intelligence-Center
make setup
# open http://localhost:4173 when it finishes
```

See [`DEPLOYMENT.md`](DEPLOYMENT.md) for the full walkthrough, troubleshooting, and how to add API keys later.

## Notes from a fresh-Linux bring-up (2026-05-10)

A first-time `make setup` on a clean Ubuntu Desktop 26.04 box surfaced several
issues that don't show up on the development machine. They're patched on the
`fix/deploy-fresh-linux-bringup` branch but are worth knowing about for future
iterations — most of them are class-of-bug rather than one-shot typos.

| Layer | Bug | Where it lived |
|---|---|---|
| **psql substitution** | `:'app_pw'` doesn't expand inside `DO $$ ... $$` blocks. The `:` was sent verbatim and Postgres errored at parse time. Use `set_config()` + `current_setting()` to bridge psql variables into PL/pgSQL. | [infra/postgres/init-roles.sql](infra/postgres/init-roles.sql) |
| **Postgres 15+ default ACL** | `iic_migration` had `CREATE ON DATABASE` but not on schema `public`. Alembic's `alembic_version` table lands in `public`, so the role needs explicit `GRANT USAGE, CREATE ON SCHEMA public`. | [infra/postgres/init-roles.sql](infra/postgres/init-roles.sql) |
| **shell hygiene** | `basename "$dir" \| tr -c '[:alnum:]_-' '_'` converts the trailing newline to `_`, producing a doubled separator (`investment-intelligence-center__default`). Wrap with `printf '%s'` before `tr -c`. | [deploy/run-migrations.sh:43](deploy/run-migrations.sh#L43) |
| **image lineage** | `timescale/timescaledb-ha:pg16` ships timescaledb / pgvector / vectorscale / hypopg / pgaudit but **not** `pg_partman`, which migration 0001 needs. Added a thin `infra/postgres/Dockerfile` that installs `postgresql-16-partman` from PGDG and updated compose to build it. | [infra/postgres/Dockerfile](infra/postgres/Dockerfile) + [docker-compose.yml](docker-compose.yml) |
| **migration ordering** | `CREATE EXTENSION pg_partman SCHEMA partman` ran before `CREATE SCHEMA partman`. Postgres does not auto-create the target schema for `EXTENSION ... SCHEMA`. | [packages/data-lake/data_lake/migrations/versions/0001_init_lake.py](packages/data-lake/data_lake/migrations/versions/0001_init_lake.py) |
| **pg_partman 5.x API change** | `partman.create_parent(p_type := 'native', ...)` was removed in pg_partman 5 — declarative partitioning is the only mode now and the value renamed to `'range'`. | [packages/data-lake/data_lake/migrations/versions/0001_init_lake.py](packages/data-lake/data_lake/migrations/versions/0001_init_lake.py) |
| **TimescaleDB hypertable PK** | `id UUID PRIMARY KEY` on a table hypertabled on `ts` fails: TimescaleDB requires the partitioning column in any UNIQUE/PK. Hit twice (`lake.llm_calls`, `lake.eval_runs`); both fixed to composite `(id, ts)`. | [0003_llm_telemetry.py](packages/data-lake/data_lake/migrations/versions/0003_llm_telemetry.py), [0004_eval_runs.py](packages/data-lake/data_lake/migrations/versions/0004_eval_runs.py) |
| **container layout assumption** | `Path(__file__).resolve().parents[4]` works in the source tree (`apps/orchestrator/orchestrator/plan/personas.py` → repo root) but the container layout (`/app/orchestrator/plan/personas.py`) has fewer parents and `IndexError`s at module import. Made the path lazy and honour `IIC_PERSONA_DIR`. | [apps/orchestrator/orchestrator/plan/personas.py](apps/orchestrator/orchestrator/plan/personas.py) |
| **shared-package packaging** | The agent Dockerfiles `COPY` only their own dir, but the agents import `schema`, `featureflags`, `llm_client`, `data_bus`, `notifier`, `prompts`, `data_lake`. None of those are pip-installable from the agent images, and their transitive deps (`packaging`, `jinja2`, `structlog`, `redis`, `sqlalchemy`, `asyncpg`, `psycopg2-binary`, `opentelemetry-api`) aren't in the per-agent `requirements.txt`. **This is the structural one** — worth a real fix in T2.x rather than the dev-mode workaround that ships here (bind-mount each shared package over `/app/<pkg>` + a `dev-entrypoint.sh` that pip-installs the union of transitive deps). | [docker-compose.dev.yml](docker-compose.dev.yml) + [deploy/dev-entrypoint.sh](deploy/dev-entrypoint.sh) |
| **Compose CMD/entrypoint interaction** | When you set `entrypoint:` in Compose, the image's `CMD` is also cleared. Each agent that overrides entrypoint must therefore also restate its `command:` explicitly. | [docker-compose.dev.yml](docker-compose.dev.yml) |

The smoke-check passes 13/13 required services after these patches; agent_futu
and grafana skip lines are intentional (profile-disabled in dev). The largest
follow-up worth doing in a future iteration is the shared-package one: each
agent should either `pip install -e ./packages/<pkg>` at build time or share a
pre-built base image with all internal packages baked in. The dev bind-mount
approach works, but it means the production image still has the import-time
crash-loop.

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
