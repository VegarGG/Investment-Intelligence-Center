# Investment Intelligence Center (IIC)

> Personal, always-on, agentic investment-advisory system. Six AI agents (Intelligence, Fundamental, Quant, Persona, Backtest, Secretary) collaborate and compete on a single Linux mini-PC. Suggestion-only — no real-money trading.
>
> **v2.1 substrate is in production. v2.5 (Investment Board, FUTU read-only, event-flow) is fully shipped. v2.6 — prototype-to-product via the [D7 plan](plan/D7_IIC_Development_Plan_Prototype_to_Product.md), phases P0–P9 — has landed end-to-end on `feat/v2.6-d7-prototype-to-product`, plus the [D7.1 hotfix](plan/D7.1_IIC_Hotfix_Plan_v2.6.1.md) that closes the wiring gap the 2026-05-19 fresh bring-up exposed.**

## Quick start (fresh Ubuntu 26.04 LTS)

```bash
git clone https://github.com/VegarGG/Investment-Intelligence-Center
cd Investment-Intelligence-Center
make setup
# open http://localhost:4173 when it finishes
```

See [`DEPLOYMENT.md`](DEPLOYMENT.md) for the full walkthrough, troubleshooting, and how to add API keys later.

## v2.6 — prototype to product (the D7 iteration)

After the v2.5 hotfixes brought up clean on a fresh Ubuntu box, [D6](plan/D6_Architecture_Review_Prototype_to_Product.md) audited the prototype and named the gap: the substrate worked, but every *thinking* node was a stub. [D7](plan/D7_IIC_Development_Plan_Prototype_to_Product.md) closes that gap function-by-function. Highlights of what landed:

| Phase | What it did | Where to look |
|---|---|---|
| **P0** | Cost gate off by default; `chat_or_raise()`; per-`caller_id` concurrency cap; env-driven rate limits; every outcome (incl. `skipped`) logged to `lake.llm_calls`. | [packages/llm-client/llm_client/router.py](packages/llm-client/llm_client/router.py), migration [0006](packages/data-lake/data_lake/migrations/versions/0006_llm_calls_outcome_skipped.py) |
| **P1** | New `iic-base` image with every `packages/*` editable-installed → kills the dev bind-mount workaround. `IIC_REPO_ROOT` replaces `parents[N]` arithmetic. Two new CI workflows (static-checks + fresh-bringup). | [infra/iic-base/Dockerfile](infra/iic-base/Dockerfile), [packages/featureflags/featureflags/paths.py](packages/featureflags/featureflags/paths.py), [tools/lint_hypertable_pk.py](tools/lint_hypertable_pk.py) |
| **P2** | Real intel pipeline: GDELT crawler, FRED macro source, Redis hash gate, pgvector semantic index, Postgres event store, `intel.context.v1` schema, all five cron jobs registered. | [apps/agent_intelligence/intel/crawler/gdelt.py](apps/agent_intelligence/intel/crawler/gdelt.py), migration [0007](packages/data-lake/data_lake/migrations/versions/0007_pgvector_intel_embeds.py) |
| **P3** | New [admin API](apps/admin_api/) on :8090 — YAML editor, sops-sealed secrets, connector test, schedules, hash-chained `lake.config_audit`. Five new Settings pages in the dashboard. | [apps/admin_api](apps/admin_api/), migration [0008](packages/data-lake/data_lake/migrations/versions/0008_config_audit.py) |
| **P4** | `RealOpenD` adapter + `FutuQuoteClient` allow-list, `lake.quotes` writer, subscription manager with NATS-KV reconciliation, brokers admin UI, ccxt crypto + FRED FX writers. | [apps/agent_futu/futu/quote_client.py](apps/agent_futu/futu/quote_client.py), [apps/agent_market/](apps/agent_market/), migration [0009](packages/data-lake/data_lake/migrations/versions/0009_lake_quotes.py) |
| **P5** | Geo dashboard restored: `lake.geo_events`, `/api/geo/events`, react-globe.gl viewer, `intel.event.geo_cluster.v1` → trading room. | [apps/dashboard/src/routes/Map.tsx](apps/dashboard/src/routes/Map.tsx), migration [0010](packages/data-lake/data_lake/migrations/versions/0010_lake_geo_events.py) |
| **P6** | Secretary becomes the leader-router: outbound dispatcher, `secretary.plan` LLM caller, `/chat`, `/rerun`, `/prefs/{user}/{key}`, real morning/midday/evening brief composition, slash commands now mutate state. | [apps/agent_secretary/secretary/](apps/agent_secretary/secretary/), migrations [0011](packages/data-lake/data_lake/migrations/versions/0011_user_prefs.py) + [0012](packages/data-lake/data_lake/migrations/versions/0012_secretary_thread.py) |
| **P7** | Fundamental / Quant / Backtest `/run/*` endpoints wired to the (already-existing) factor/valuation/book code. Quant regime detector. `lake.bt_positions` book. | [apps/agent_quant/quant/regime.py](apps/agent_quant/quant/regime.py), migration [0013](packages/data-lake/data_lake/migrations/versions/0013_bt_positions.py) |
| **P8** | Persona daily/weekly/rerun endpoints wired to the real reasoner with disclaimer enforcement. | [apps/agent_persona/persona/main.py](apps/agent_persona/persona/main.py) |
| **P9** | OTel spans per chat call; `restore_drill.sh`; five runbooks; in-process topology-regression e2e + live-trace gate (`IIC_E2E_LIVE=1`). | [docs/runbooks/](docs/runbooks/), [tests/e2e/](tests/e2e/), [deploy/drills/restore_drill.sh](deploy/drills/restore_drill.sh) |

The full plan, item-by-item with acceptance criteria, is in [`plan/D7`](plan/D7_IIC_Development_Plan_Prototype_to_Product.md). The blunt prototype audit that motivated it is [`plan/D6`](plan/D6_Architecture_Review_Prototype_to_Product.md).

## Notes from the fresh-Linux bring-up (2026-05-10) + D7 resolution

The first-time `make setup` on a clean Ubuntu Desktop 26.04 box surfaced several issues that don't show up on the development machine. The hotfix branch patched the bring-up; D7 then turned the structural items below into real fixes rather than dev workarounds.

| Layer | Bug | Status |
|---|---|---|
| **psql substitution** | `:'app_pw'` doesn't expand inside `DO $$ ... $$` blocks; use `set_config()` + `current_setting()` to bridge psql variables into PL/pgSQL. | ✅ Fixed in hotfix • [init-roles.sql](infra/postgres/init-roles.sql) |
| **Postgres 15+ default ACL** | `iic_migration` needed explicit `GRANT USAGE, CREATE ON SCHEMA public`. | ✅ Fixed in hotfix |
| **shell hygiene** | `tr -c` consumed the trailing newline as a separator; wrap with `printf '%s'`. | ✅ Fixed in hotfix • P1.5 added a [`shellcheck` CI gate](.github/workflows/static-checks.yml) |
| **image lineage** | `timescale/timescaledb-ha:pg16` doesn't ship `pg_partman`; thin Dockerfile installs `postgresql-16-partman` from PGDG. | ✅ Fixed in hotfix • P1.4 made the upstream image pinnable by digest via `IIC_PG_BASE_IMAGE` |
| **migration ordering** | `CREATE EXTENSION pg_partman SCHEMA partman` ran before `CREATE SCHEMA partman`. | ✅ Fixed in hotfix |
| **pg_partman 5.x API change** | `partman.create_parent(p_type := 'native', ...)` was removed; declarative partitioning is the only mode and the value is `'range'`. | ✅ Fixed in hotfix |
| **TimescaleDB hypertable PK** | Composite `(id, ts)` PK required when partitioning by `ts`. | ✅ Fixed in hotfix • P1.5 added a [`lint_hypertable_pk.py`](tools/lint_hypertable_pk.py) CI gate to catch regressions |
| **container layout assumption** | `Path(__file__).resolve().parents[4]` crashed in containers because there are fewer parents. | ✅ Made lazy in hotfix • P1.6 replaced *all* such arithmetic with [`featureflags.paths.repo_root()`](packages/featureflags/featureflags/paths.py); CI gate forbids `parents[N>=2]` in production code |
| **shared-package packaging** | The agent Dockerfiles `COPY`'d only their own dir; agents imported `schema`, `featureflags`, `llm_client`, etc. without those being installed. | ✅ **Structurally fixed in P1.1–P1.3** • new [`infra/iic-base/Dockerfile`](infra/iic-base/Dockerfile) editable-installs every package; agent Dockerfiles `FROM iic-base:latest`; dev compose drops the bind-mount workaround and the `dev-entrypoint.sh` is deleted |
| **Compose CMD/entrypoint interaction** | Setting `entrypoint:` cleared the image's CMD. | ✅ Obsolete after P1.3 — no agent overrides entrypoint any more |

The smoke-check passes 13/13 required services on the hotfix branch; agent_futu and grafana skip lines are intentional (profile-disabled in dev). After D7, a 14th container (`iic-admin-api` on :8090) joins the default profile.

## D7.1 — wiring-gap hotfix (2026-05-19)

The next fresh-Ubuntu bring-up after D7 landed proved D7 had shipped the *adapters* (router, agents, schema, dashboard) but never the *bootstrap* that connects them: `lake.llm_calls` stayed at 0 after a full smoke matrix because no agent ever called `set_router()`. The [D7.1 plan](plan/D7.1_IIC_Hotfix_Plan_v2.6.1.md) sits inside D7 as a sub-version and closes that hole.

| Phase | Item | What it does | Where |
|---|---|---|---|
| **H0** (P0) | R1 — `llm_client.bootstrap` | `router_from_env()` + `bootstrap_router_or_die()` build an `LlmRouter` from `DEEPSEEK_API_KEY`/`ANTHROPIC_API_KEY`/`GROQ_API_KEY` and call `set_router()` once at startup. `lifespan_bootstrap(strict=…)` lets the strict-mode contract coexist with the `set_router(stub)` test-fixture pattern. | [packages/llm-client/llm_client/bootstrap.py](packages/llm-client/llm_client/bootstrap.py) • lifespan added/extended in all 8 agent main.py files |
| **H0** (P0) | R2 — wiring smoke | `deploy/smoke-check.sh` gains a 3-step wiring assertion (connector test → `POST /chat/echo` → `lake.llm_calls` row in last 5 min) that catches "router unbound" the next time it regresses. Falls back to substrate-only when no LLM key is configured. | [deploy/smoke-check.sh](deploy/smoke-check.sh) • [.github/workflows/fresh-bringup.yml](.github/workflows/fresh-bringup.yml) |
| **H1** (P1) | R3 — `/chat` user passthrough | Secretary `/chat` accepts `X-User-Id` header (preferred) or `user`/`user_id` in body, lowercases, falls back to `"anon"`. Allow-list enforced when `SECRETARY_ALLOWED_USERS` is set; permissive otherwise. | [apps/agent_secretary/secretary/main.py](apps/agent_secretary/secretary/main.py) |
| **H1** (P1) | R4 — `POST /chat/echo` | Always-LLM demo endpoint. Bypasses planner + allow-list, calls Flash via `chat_or_raise`, returns `{echo, llm_call_id, model, latency_ms}` — the one endpoint the wiring smoke can correlate end-to-end. Off-switch via `SECRETARY_DEMO_ENDPOINTS=off`. | secretary `main.py` + `secretary.echo` registered in [`_matrix.py`](packages/llm-client/llm_client/_matrix.py) |
| **H2** (P2) | R5 — `restart` → `up -d --force-recreate` | DEPLOYMENT.md §4 callout: `docker compose restart` does **not** reload `.env`. Recreate is required. | [DEPLOYMENT.md](DEPLOYMENT.md) |
| **H2** (P2) | R6 — `admin_api:8090` in smoke | Smoke script now probes the 14th container that's been in DEPLOYMENT.md §2 since D7. | [deploy/smoke-check.sh](deploy/smoke-check.sh) |
| **H2** (P2) | R7 — `package-mode=false` lint | CI fails any PR that re-adds `package-mode = false` to `packages/*` (the latent notifier-installability bug). Also removed the existing `package-mode = false` in `packages/notifier/pyproject.toml`. | [.github/workflows/static-checks.yml](.github/workflows/static-checks.yml) |
| **H2** (P2) | R8 — hypertable-index lint | Twin of P1.5's hypertable-PK lint. Forbids hand-created indexes that collide with the one `create_hypertable()` auto-creates on the time column. | [tools/lint_hypertable_indexes.py](tools/lint_hypertable_indexes.py) |
| **H2** (P2) | R9 — pinned dashboard deps | Dockerfile switches `npm install` → `npm ci` against `package-lock.json`; new `apps/dashboard/.dockerignore` keeps host `node_modules` out of the build context. A transitive bump (e.g. `react-globe.gl`) can no longer break our build until it's committed to the lockfile. | [apps/dashboard/Dockerfile](apps/dashboard/Dockerfile) |
| **H2** (P3) | R10 — LLM-bound vs data-gated table | DEPLOYMENT.md §2 documents which `/run/*` paths call the LLM, which gate on data, and what each returns on a fresh deploy — so the next bring-up reads `filings_n=0` as a feature, not a wiring bug. | [DEPLOYMENT.md](DEPLOYMENT.md) |

**Definition of done:** a fresh checkout + `make setup` + `curl -X POST :8080/chat/echo` produces a row in `lake.llm_calls` with `outcome='ok'` and a non-empty `llm_call_id`. The fresh-bringup CI workflow now exercises this end-to-end when `DEEPSEEK_API_KEY` is available in repo secrets.

## Specs

- [`plan/EXECUTIVE_SUMMARY_bilingual.md`](plan/EXECUTIVE_SUMMARY_bilingual.md) — bilingual elevator pitch.
- [`plan/IIC_Development_Plan_v2.5_Combined.md`](plan/IIC_Development_Plan_v2.5_Combined.md) — v2.5 plan (substrate + Investment Board).
- [`plan/D6_Architecture_Review_Prototype_to_Product.md`](plan/D6_Architecture_Review_Prototype_to_Product.md) — blunt prototype audit (what's mock, what's real).
- [`plan/D7_IIC_Development_Plan_Prototype_to_Product.md`](plan/D7_IIC_Development_Plan_Prototype_to_Product.md) — **active plan** (P0–P9 function-by-function).
- [`plan/PLAN_v2.1_Investment_Intelligence_Center.md`](plan/PLAN_v2.1_Investment_Intelligence_Center.md) — origin plan; substrate v2.5 builds on.
- [`workflows/`](workflows/) — self-contained vibe-coding briefs ([`00_INDEX_AND_CONVENTIONS.md`](workflows/00_INDEX_AND_CONVENTIONS.md) first).
- [`workflows/32_V2_5_T0_T1_CHANGELOG.md`](workflows/32_V2_5_T0_T1_CHANGELOG.md) — what shipped from v2.5.
- [`docs/runbooks/`](docs/runbooks/) — five P9 runbooks (provider outage, FUTU offline, cost-breaker trip, advice-chain break, brief failed to send).

## Build order

The v2.5 plan supersedes v2.1's phase mapping with a tier-staged contract: T0 prereqs → T1 correctness → T2 architecture (Investment Board + FUTU + event-flow) → T3 research depth. v2.6 is D7 — converting every thinking node from a stub into a real implementation.

| Tier | Items | Status |
|------|-------|--------|
| **T0 — Rollback substrate** | T0.1 featureflags • T0.2 persona source-of-truth • T0.3 SPOF ADR | ✅ Shipped |
| **T1 — Correctness, reliability, DAG coverage** | T1.1 live mark • T1.1d persona band derivation • T1.2 missing personas • T1.3 intel pipeline at startup • T1.4 notifier durable redelivery • T1.5 DAG coverage closure • T1.6 per-agent breaker • T1.7 NATS backup + restore drill • T1.8 memory caps • T1.9 cost-breaker behaviour • T1.10 PIT ingest • T1.11 markdown decision log + Backtest reflection • T1.12 walk-forward CI gate | ✅ Shipped |
| **Synthetic burn-in regime** | 4-phase replacement for the 14-day production-burn gate (chaos + walk-forward + observability + real-API cost-cap) | ✅ Shipped (phases 1–2 default; phases 3–4 real-integration-gated) |
| **T2 — Investment Board + FUTU + event-flow** | T2.0 NATS request-reply substrate • T2.2 plan.v1 schema • T2.4 Investment Board • T2.7 FUTU mock-OpenD (B3.3a) • T2.8 trading-room DAG | ✅ Shipped |
| **v2.6 / D7 — Prototype-to-product** | P0 cost-gate posture • P1 production packaging • P2 real intel pipeline • P3 admin API + UI • P4 FUTU portal + quotation • P5 geo dashboard • P6 secretary leader-router • P7 fundamental/quant/backtest thinking nodes • P8 persona analytical • P9 production hardening | ✅ Shipped on `feat/v2.6-d7-prototype-to-product` |
| **T3 — Research depth** | Options-flow team, on-chain, geopolitics, BL portfolio, mobile app, … | ⏳ Gated on D7 merge + 30 d soak |

For the v2.1 phase mapping (still relevant — it documents the substrate v2.5 builds on), see workflow 00.

## Disclaimer

For personal research only. Not investment advice. IIC is not a registered investment advisor. The FUTU integration is read-only by construction; see [`docs/security/FUTU_readonly_review.md`](docs/security/FUTU_readonly_review.md) for the defence-in-depth story.
