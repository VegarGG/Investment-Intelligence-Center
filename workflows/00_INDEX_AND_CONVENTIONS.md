# IIC Workflow Index — Master Conventions

> **Active plan:** [`plan/IIC_Development_Plan_v2.5_Combined.md`](../plan/IIC_Development_Plan_v2.5_Combined.md) (T0 + T1 partial shipped — see workflow 32)
> **Origin plan:** [`plan/PLAN_v2.1_Investment_Intelligence_Center.md`](../plan/PLAN_v2.1_Investment_Intelligence_Center.md) (substrate; workflows 00–31)
> **Status:** Final, ready for vibecoding
> **Owner:** Ziwei
> **Scope of this folder:** This index plus the v2.1 sibling workflow docs (00–31) and the v2.5 changelog docs (32–). Each sibling is a self-contained brief for one component of IIC. Time/week tracking has been deliberately removed — sequence is by **dependency**, not calendar.

---

## 0. How to Use These Documents

Each workflow document is structured the same way so a coding agent (Claude / Cursor / Codex / Aider) can be pointed at one file and start producing code with no other context.

Standard structure of every workflow doc:

1. **Purpose** — one paragraph.
2. **Ground Truth** — file paths, env vars, schemas, topic names, port numbers. Immutable.
3. **Architecture** — boxes + arrows + rationale.
4. **Module Layout** — concrete file/directory tree under `apps/` or `packages/`.
5. **Workflow Steps** — ordered list of buildable units. Each unit has clear inputs/outputs.
6. **Vibe Prompts** — paste-ready prompts you can hand to a coding agent.
7. **Acceptance Criteria** — what "done" means. Testable.
8. **Risks & Gotchas** — known traps.
9. **Cross-References** — pointers into other workflow docs.

---

## 1. Document Map — Read Order

Documents are numbered for dependency order. Lower numbers should land before higher numbers.

| # | File | Owns |
|---|------|------|
| 00 | `00_INDEX_AND_CONVENTIONS.md` | This file — master conventions |
| 01 | `01_INFRASTRUCTURE_AND_HOST.md` | Hardware, Linux host, Docker Compose, security, NAS migration |
| 02 | `02_DATA_LAYER.md` | Postgres+Timescale, ChromaDB, MinIO, Redis, schemas, retention, backups |
| 03 | `03_LLM_CLIENT.md` | DeepSeek v4 wrapper, routing matrix, fallbacks, cost gating |
| 04 | `04_PROMPT_REGISTRY.md` | Versioned prompts, eval golden set, drift detection |
| 05 | `05_DATA_BUS_AND_SCHEMAS.md` | NATS JetStream, topic registry, `advice.v1` and friends |
| 06 | `06_ORCHESTRATOR.md` | DAG planning, routing, merging, SLA enforcement |
| 10 | `10_AGENT_INTELLIGENCE.md` | News + macro + sentiment + digest |
| 11 | `11_AGENT_FUNDAMENTAL.md` | Filings + valuation + advice |
| 12 | `12_AGENT_QUANT.md` | Factor library + signal + risk + advice |
| 13 | `13_AGENT_PERSONA.md` | Style-mimic strategists |
| 14 | `14_AGENT_BACKTEST.md` | Live judge — paper trading + leaderboard |
| 15 | `15_AGENT_SECRETARY.md` | Chatbot + briefs + family-friendly tone |
| 20 | `20_NOTIFIER_WECHAT.md` | WeCom bot + WeCom app + Server酱 + ntfy + SMTP |
| 21 | `21_DASHBOARD_UI.md` | React + Tailwind + Recharts dashboard |
| 30 | `30_OBSERVABILITY_AND_EVAL.md` | Grafana + Loki + Prometheus + eval harness + leaderboard math |
| 31 | `31_PRODUCTION_HARDENING.md` | DR drill, NAS migration validation, security review, secrets rotation |
| 32 | `32_V2_5_T0_T1_CHANGELOG.md` | v2.5 T0 + T1 partial — featureflags, persona source-of-truth, ADR-0004, quotes, missing personas, intel startup, DAG coverage, agent breaker |

---

## 2. Ground Truth — Repo Layout

This layout is contractual. Do not rename without bumping the document major version.

```
intelligence-center/
├── docker-compose.yml
├── .env.example
├── pyproject.toml             # Poetry monorepo root
├── apps/
│   ├── orchestrator/
│   ├── agent_intelligence/
│   ├── agent_fundamental/
│   ├── agent_quant/
│   ├── agent_persona/
│   ├── agent_backtest/
│   ├── agent_secretary/
│   └── dashboard/             # React + Vite
├── packages/
│   ├── llm-client/            # DeepSeek wrapper
│   ├── data-bus/              # NATS adapter
│   ├── data-lake/             # DB clients
│   ├── prompts/               # Versioned prompts
│   ├── notifier/              # WeCom + Server酱 + ntfy + SMTP
│   └── schema/                # Pydantic + TS shared types
├── infra/
│   ├── linux/                 # bootstrap.sh, systemd units, restic
│   ├── nas/                   # migrate.sh (dry-run from day 1)
│   └── observability/         # Grafana / Loki / Prometheus configs
├── docs/
│   ├── runbooks/
│   ├── adr/
│   └── prompts/persona/       # Persona YAML files
└── workflows/                 # ← these documents
```

Two consumption boundaries:

- **`apps/`** — long-running processes (one container each).
- **`packages/`** — importable libraries shared across `apps/`. No process state.

---

## 3. Ground Truth — Host Filesystem (Bind-Mount Roots)

Every container's persistent volume is a **bind mount** under `/srv/iic/<service>`. No Docker named volumes. This is the single most important decision in the system because it is what makes the NAS migration zero-touch.

```
/srv/iic/
├── pg/                        # Postgres + TimescaleDB data dir
├── chroma/                    # Vector store
├── nats/                      # JetStream durable storage
├── minio/                     # Object store
├── redis/                     # Redis AOF
├── grafana/, loki/, prometheus/
├── prompts_versioned/         # Append-only prompt history
├── advice_ledger/             # Hash-chained advice records
└── backup/                    # restic repo target
```

If a future workflow doc proposes a new persistent service, its volume mount **must** live under `/srv/iic/<service>` and be a bind mount.

---

## 4. Ground Truth — Naming Conventions

| Layer | Rule | Example |
|-------|------|---------|
| Python module names | `snake_case` | `agent_intelligence` |
| File names | `snake_case.py` | `intel_synth.py` |
| Class names | `PascalCase` | `AdviceV1` |
| Pydantic schema versions | `name.v{n}` lowercase | `advice.v1` |
| NATS subjects | dotted, lowercase, ends with `.v{n}` | `intel.digest.v1` |
| Env vars | `UPPER_SNAKE` | `DEEPSEEK_API_KEY` |
| ADRs | `docs/adr/ADR-XXXX-slug.md` | `ADR-0002-nats-jetstream.md` |
| Branches | `feat/<doc-num>-<slug>` | `feat/12-quant-momentum` |

---

## 5. Ground Truth — Versioning Policy

- **Schemas** (anything with `.v{n}` suffix) are append-only. Adding a field is fine; renaming/removing requires `.v{n+1}` and a parallel-publish migration window.
- **Prompts** are SemVer-tagged in `packages/prompts/registry/`. Every change bumps. CI fails if a prompt diff lands without a version bump.
- **Workflow docs** (these files) are versioned at the top of each file. Breaking changes require a minor bump and a `## Changelog` entry at the bottom.

---

## 6. Conventions for Vibe Prompts

When you paste a vibe prompt into a coding agent:

1. Always pass **this index file plus the relevant workflow doc** as context. Do not pass the entire `PLAN_v2.1` — it is too long and not chunked for the AI window.
2. End every prompt with: *"Honor every block marked GROUND TRUTH literally. Ask before deviating."*
3. After the agent generates code, run the doc's "Acceptance Criteria" as the diff review checklist before merging.

---

## 7. Conventions for Phase Sequencing

The original v2.1 plan listed 9 phases (Phase 0 → 8). In these workflow docs we drop calendar weeks entirely; instead each doc declares a `Depends On:` line at the top. The dependency graph (see §1 above) yields a natural build order without needing a Gantt chart.

A coding agent can pick the next doc to work on by:

1. Find any doc whose dependencies are all marked **complete**.
2. Pick the one with the lowest number among them.

That's the entire scheduling rule.

---

## 8. Conventions for Acceptance Criteria

Every workflow doc ends with a checklist. The rule: a checklist item must be **runnable as a command** or **observable in a dashboard**. No prose-only acceptance.

Bad: "Intelligence Agent works correctly."
Good: `curl localhost:8000/health` returns `{"status":"ok","feeds_active":90}` and the WeCom briefs bot has received ≥ 1 brief in the last 24 h.

---

## 9. Anti-Goals (Things These Docs Do Not Cover)

- **Auto-trading.** No broker integrations anywhere. If a doc proposes one, reject it.
- **Multi-tenant.** Single principal. No user-management doc exists by design.
- **Local LLM hosting.** Out of scope until DeepSeek-V4-distill ships open weights.
- **Mobile app development.** WeChat is the mobile UX. No native apps.
- **Tax / accounting integration.** Out of scope.

---

## 10. Glossary

| Term | Definition |
|------|------------|
| **PIT** | Point-in-time. As-of correctness for backtests and factor builds. |
| **R-multiple** | `(exit − entry) / |entry − stop|`. Position-size-normalized P&L. |
| **Regime** | Market-state classification: risk-on, risk-off, stagflation, recession, crisis. |
| **Reflexivity** | Soros's principle that prices change fundamentals (used by `persona.soros`). |
| **Bias balance** | Distribution of news sources across regions and political lean. |
| **Smart-passive benchmark** | Risk-parity blend used as the leaderboard's neutral comparator. |
| **WeCom (企业微信)** | WeChat Work; provides webhooks and OAuth-based self-built apps. |
| **Server酱** | Service that pushes messages to a personal WeChat 服务号. Backup channel only. |
| **Advice** | Any record matching `advice.v1`. Immutable once published. |
| **Brief** | Human-readable WeChat message produced by the Secretary. |
| **Digest** | Machine-readable event ranking produced by Intelligence. |
| **NAS-Ready** | A property of file paths and Compose config: switching `/srv/iic` from local to NFS is a `mount` change, nothing else. |

---

## 11. Quick Reference Card

```
Ports:
  4222 NATS · 5432 Postgres · 8000 Chroma · 9000 MinIO · 6379 Redis
  3000 Grafana · 3100 Loki · 9090 Prometheus
  8080 Orchestrator · 8081–8086 Agents (Intel, Fund, Quant, Persona, Backtest, Secretary)
  5173 Dashboard dev · 4173 Dashboard preview

Topics:
  intel.{digest|dashboard|brief}.v1
  advice.{fundamental|quant|persona.<slug>}.v1
  backtest.{fill|daily|leaderboard}.v1
  secretary.notify.v1
  ops.{heartbeat|alert}.v1

LLM tiers:
  DeepSeek-V4-Pro    → orchestrator plan, intel.synth, fund.valuation, persona.*, deep secretary
  DeepSeek-V4-Flash  → ingest, translation, classification, narration, default chat
  Fallback Pro       → Anthropic Claude Sonnet 4.6
  Fallback Flash     → Groq Llama-3.3-70B
```

---

## Changelog

- **v1.0** — Created from `PLAN_v2.1_Investment_Intelligence_Center.md`. Time/week tracking removed; replaced with dependency ordering.
