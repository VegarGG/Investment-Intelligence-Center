# D6 — IIC Architecture Review: Prototype-to-Product

**Audience:** Ziwei (owner / vibe-coder)
**Author:** ai-engineer agent
**Date:** 2026-05-10
**Reviewing:** `VegarGG/Investment-Intelligence-Center` @ `main` (commit baseline) and `fix/deploy-fresh-linux-bringup` (commit `51643a0`)
**Companion plan:** `D7_IIC_Development_Plan_Prototype_to_Product.md`
**Predecessors:** `D3_Architecture_Review.md` (pre-deploy), `D5_IIC_Prototype_Review_and_Next_Iteration.md`

> Tone of this review: blunt. The user explicitly asked for no hiding, no make-up, no polishing. Where the prototype is held together with mocks, this document calls them out by file and line. Praise is reserved for things that actually work end-to-end against real systems. Everything else is a placeholder we should plan to replace.

---

## TL;DR (one screen)

| Topic | Status today | Truth |
| --- | --- | --- |
| Six-agent skeleton + DAG + advice ledger | Shipped | Real. T0 + T1 done. |
| Substrate (Postgres, Timescale, NATS, Redis, alembic) | Shipped | Real, but the bring-up exposed seven distinct deployment bugs (now hotfixed). |
| Hotfix branch | Correct in spirit, dev-mode workaround on shared-package mounting | Land it. Two of the patches must become production fixes, not just dev. |
| **LLM integration** | **None against real APIs** | Routing matrix exists, cost meter exists, but no working `DEEPSEEK_API_KEY`/`ANTHROPIC_API_KEY` plumbing has been exercised end-to-end. Every agent in production runs against a stub or `chat_or_skip` returning the synthetic-skip marker. |
| **Intel data feeds** | **One real source class (RSS)**; everything else is `InMemory*` defaults | No GDELT, no news API, no SEC/EDGAR, no FRED, no FX. Default factory wires `InMemoryCrawler`, `InMemoryHashStore`, `InMemorySemanticIndex`, `InMemoryMacroSource`, `InMemoryEventStore` (`apps/agent_intelligence/intel/factory.py`). |
| **Fundamental / Quant / Backtest endpoints** | **Stubs** | Every `/run/*` endpoint returns `{"status":"queued"}`. No factor library is wired, no filings are fetched, no backtest runs. |
| **Persona agents** | Persona spec loader works; `/run/daily` and `/run/weekly` are stubs | YAML personas load, but no analytical code runs. |
| **Investment Board** | Real LLM pipeline (Bull→Bear→Risk×3→Chair) | First non-stub agent. Calls the router. With no real API keys it short-circuits to synthetic-skip. |
| **Secretary** | One-way **inbound sink only** | Cannot dispatch to other agents. The user's vision (a leader/router agent) is **not** the current architecture. Big gap. |
| **FUTU client** | Read-only enforcement is correct; OpenD is `FakeOpenD`; quotation endpoints not exposed at all | Phase A done, B not started. The user's instinct that FUTU can serve quotations is correct — currently zero of that surface is wired. |
| **Map dashboard** | **Absent** from the codebase | The v1.1 globe / GDELT visualization was deprecated and never carried over. |
| **Configuration UI** | **Absent** | Every knob is YAML, env, or code edit. No GUI for API keys, model picks, cadence, persona prompts, agent enable/disable. |
| **Cost gate** | Hardcoded `$90/month` cap with breaker state-machine in NATS KV | User wants this removed for now. Lives in `packages/llm-client/llm_client/cost_meter.py`; touched from many sites. Removable cleanly. |
| **Mocks / placeholders** | **Pervasive** in agents-that-do-thinking; **real** in substrate, schema, dashboard, board | Inventory below. |

The single most honest sentence about the prototype: it has shipped the **plumbing** of an agentic investment system but not the **agents**. Every node that is supposed to *think* is either canned or routes to a router that returns a synthetic-skip placeholder. The bring-up bug list confirms it has never been exercised end-to-end against real APIs.

---

## 1. Hotfix review — `fix/deploy-fresh-linux-bringup`

The branch is one commit (`51643a0`), 11 files changed. Each fix is small and orthogonal; the bundling is appropriate because they cascade (init-roles must succeed before migrations run before agents come up).

### 1.1 Patch-by-patch verdict

| # | Patch | Verdict | Future-development note |
|---|---|---|---|
| 1 | `init-roles.sql`: `set_config()` / `current_setting()` bridge for `:'app_pw'` inside `DO $$…$$` | **Correct and minimal.** `psql` variable substitution does not cross dollar-quote boundaries; this is the documented workaround. | Keep. Add a comment-test to the smoke check that fails fast if the role passwords end up as the literal string `:'app_pw'`. |
| 2 | `init-roles.sql`: `GRANT USAGE, CREATE ON SCHEMA public TO iic_migration` | **Correct.** Postgres 15+ revoked default `CREATE ON public` from `PUBLIC`. Alembic creates `alembic_version` in `public` by default. | Better long-term: configure Alembic to use `lake.alembic_version` and drop the `public.CREATE` grant. Adds defense-in-depth. |
| 3 | `run-migrations.sh`: `printf '%s'` to strip the trailing newline before `tr -c` | **Correct.** Shell hygiene. | Worth lint-coverage: add `shellcheck` to CI. This class of bug is endemic. |
| 4 | New `infra/postgres/Dockerfile` extending `timescale/timescaledb-ha:pg16` with `postgresql-16-partman` from PGDG | **Correct.** TimescaleDB-HA bundles many extensions but not pg_partman. | Pin the Dockerfile to a `timescale/timescaledb-ha:pg16-ts2.x.x-...` digest, not the floating `pg16` tag. Reproducibility matters more than security-patch convenience for a stateful image. Also add a `RUN pg_partman --version` smoke step in CI build. |
| 5 | Migration 0001: create `partman` schema before the `CREATE EXTENSION` and switch `p_type` `'native'` → `'range'` | **Correct.** Postgres won't auto-create the target schema; pg_partman 5 removed `'native'`. | Pin pg_partman version explicitly (`postgresql-16-partman=5.0.x`). Test against pg_partman 4 and 5 in CI matrix until one is deprecated. |
| 6 | Migrations 0003 / 0004: composite PK `(id, ts)` to satisfy TimescaleDB's hypertable PK rule | **Correct and load-bearing.** TimescaleDB requires the partitioning column in every UNIQUE/PK. | This is a class-of-bug. Add an alembic test fixture that runs `select create_hypertable(...)` against any new `lake.*` table and rejects PRs that PK on a non-partitioning column. |
| 7 | `orchestrator/plan/personas.py`: lazy `parents[4]` + `IIC_PERSONA_DIR` env override | **Correct, but a smell.** `parents[4]` was always brittle — counting parents from `__file__` to compute a project-root-relative path breaks under any non-checkout layout. | Refactor: stop counting `parents[*]` anywhere in the codebase. Standardize on `IIC_REPO_ROOT` env (set by `pyproject.toml` editable install or by Compose) and load all asset-dirs relative to it. Grep for other `parents[N]` in the tree and convert them all in one PR — there will be more. |
| 8 | `dev-entrypoint.sh` + `docker-compose.dev.yml`: bind-mount each `packages/*` over `/app/<pkg>` and pip-install transitive runtime deps at start | **Pragmatic, but the README is right that this is *not* a production fix.** The agent images literally do not have working Python imports without these mounts. In production today, `docker compose up` against the published images would crash-loop on `ImportError` for `featureflags`, `schema`, `llm_client`, `data_bus`, `notifier`, `prompts`, `data_lake`. | **Mandatory follow-up — see development plan §P1.** Either (a) `pip install -e packages/*` in each agent's Dockerfile build stage, or (b) build a single `iic-base` image that contains all internal packages and have each agent's Dockerfile `FROM iic-base`. (b) is the cleaner answer because it gives one place to bump deps. |
| 9 | `docker-compose.dev.yml`: re-state `command:` for every service when `entrypoint:` is overridden | **Correct.** Documented Compose behavior. | Once the shared-package issue is fixed, the `entrypoint` override goes away and most of the `command:` re-statements with it. |

### 1.2 Class-of-bug summary

The bring-up exposed **three patterns**, not seven independent bugs:

1. **Substitution that does not cross boundaries** — `:'var'` doesn't cross `DO $$…$$`; `entrypoint:` clears `CMD`; `parents[N]` doesn't survive a different filesystem layout. **Lesson:** every interpolation should be tested against its destructured environment, not its source environment.
2. **Default tags hide upgrades** — `timescale/timescaledb-ha:pg16` quietly missed pg_partman; pg_partman 5 quietly removed `'native'`. **Lesson:** pin everything in the substrate by digest. Add a CI matrix that builds against the digest you've pinned and one digest newer.
3. **Per-agent `requirements.txt` lists what each agent imports directly, not what it imports transitively** — every shared package brought a hidden dep set with it. **Lesson:** one `requirements.txt` per agent is fine, but the build must pip-install the union of internal packages and transitive deps. Today's bind-mount workaround papers over an architectural gap.

### 1.3 Things the hotfix did **not** address

- The bring-up smoke check is `13/13 services healthy`, but **healthy ≠ working**. None of the agents are being asked to do anything against real APIs at smoke-time. Healthy here means the container started and `/health` returned `200`. We have learned nothing about whether the LLM router can actually reach DeepSeek, whether intel can crawl real RSS, whether FUTU can reach a real OpenD.
- `agent_futu` is intentionally off in dev (profile `futu`). Until the `lake.futu_audit` Postgres trigger ships (see `D5` §B3.3a→B3.3b), Phase B real-OpenD cannot be turned on. The hotfix branch correctly avoided touching that.
- No CI step was added that re-runs `make setup` from a clean Ubuntu 26.04 to prove the hotfixes hold against a future change. **Add it.** Otherwise we'll re-discover the same seven bugs in three months.

**Net:** land the hotfix on `main`. Open an immediate follow-up PR for the shared-package packaging (the structural one) and for shellcheck / hypertable-PK lint (the regression nets).

---

## 2. The "prototype is very prototype" gap — what is actually shipped vs what runs

You said: *"The prototype is very prototype, which simply testifying the system can 'work' in most basic way. The system now has no LLM API, no intel APIs, no actual function we can run as planned."*

You are correct. Concretely:

### 2.1 What is shipped and **real**

- **Substrate.** Postgres + TimescaleDB + pg_partman + NATS JetStream + Redis + Alembic migrations + Compose orchestration. Now with a clean bring-up after the hotfix.
- **Schemas.** `advice.v1`, `plan.v1`, `board.decision.v1`, `triage.decision.v1`. Pinned, versioned, tested with goldens.
- **DAG runtime.** `apps/orchestrator/orchestrator/execute/runner.py`, SLA executor, per-agent breaker, request-reply NATS shim, hash-chained advice ledger. T1 acceptance criteria met.
- **Persona spec loader.** `docs/prompts/persona/*.yaml` is the single source of truth and loads successfully.
- **Routing matrix.** Every caller_id is registered. Tier resolution + escalation rules work and are tested.
- **Cost-breaker state machine.** OPEN / HALF_OPEN / CLOSED, persisted to NATS KV, integrated into `chat_or_skip()`.
- **Investment Board.** First and only fully-wired thinking agent — Bull/Bear → Risk×3 → Chair. Calls the router for real.
- **FUTU read-only enforcement.** `FutuReadOnlyClient` `__getattr__` allow-list, `FORBIDDEN_METHODS` blocklist, lint, and audit chain. Tested.
- **Dashboard scaffolding.** React 19 + Vite, route shells for Home / Leaderboard / Trade Tape / Intel / Quant / Fundamental / Personas / Chat / Health.
- **Notifier.** WeCom OAuth verify, slash-command parser (catalog of `leaderboard`, `explain`, `why`, `disagree`, `quiet`, `tone`, `help`), Alertmanager → `secretary.notify.v1` bridge.

### 2.2 What is shipped and **not real** (mock / placeholder / stub)

The blunt list, file by file:

| Surface | File | What it actually does |
|---|---|---|
| `agent_fundamental` `/run/cover`, `/run/digest` | `apps/agent_fundamental/fund/main.py` | Returns `{"status": "queued"}`. No SEC/EDGAR call, no parser, no valuation. |
| `agent_quant` `/run/factors`, `/run/signal`, `/run/walk_forward` | `apps/agent_quant/quant/main.py` | Returns `{"status": "queued"}`. No factor library, no price ingest. |
| `agent_backtest` all `/run/*` | `apps/agent_backtest/backtest/main.py` | Returns canned. No simulator, no portfolio book. |
| `agent_persona` `/run/daily`, `/run/weekly` | `apps/agent_persona/persona/main.py` | Returns canned. The persona YAML is loaded but never used by an LLM call. |
| `agent_secretary` `/run/morning_brief`, `/run/midday_check`, `/run/evening_recap` | `apps/agent_secretary/secretary/main.py` | Returns `{"status": "queued"}`. The actual brief composition does not run. |
| Slash command bodies | `apps/agent_secretary/secretary/inbound/slash_commands.py` | Hand-coded markdown placeholders ("`pending lake.advice query`"). |
| Intel pipeline backends | `apps/agent_intelligence/intel/factory.py` | Defaults to `InMemoryCrawler`, `InMemoryHashStore`, `InMemorySemanticIndex`, `InMemoryMacroSource`, `InMemoryEventStore`. Production switches via env vars that have no documented production values. |
| Embeddings | `apps/agent_intelligence/intel/factory.py:_default_embed` | `hash_embed(text)` — a deterministic non-semantic hash. Comment says "Production replaces this with the LLM router's `embed()`." It hasn't. |
| `agent_futu` OpenD | `apps/agent_futu/futu/main.py:61–63` | `FakeOpenD` pair, hardwired. Phase B switches in real OpenD; the migration is unbuilt. |
| Quotation source | (nowhere) | The system has no working market-quote source today. Intel doesn't fetch quotes. Fundamental doesn't fetch quotes. There is no `lake.quotes` writer. |
| LLM keys | env-driven, untested in production | `DEEPSEEK_API_KEY`, `ANTHROPIC_API_KEY`, `GROQ_API_KEY` are read from env but the system has never been brought up with valid keys; `chat_or_skip` defaults to synthetic-skip on the first failure. |
| `chat_or_skip` synthetic-skip path | `packages/llm-client/llm_client/router.py:synthetic_skip_response` | When the cost breaker is open OR the router cannot reach a provider, returns the literal string `"[cost-breaker open: synthetic skip]"`. Many DAG nodes accept this and continue. **In production today this is the modal response.** |

### 2.3 What honesty looks like

We should treat the prototype as a **substrate-and-schema demo**, not an investment system. The DAG plumbing, the schemas, the breaker, the FUTU read-only walls, the persona-spec discipline — those are real and worth defending. Every analytical claim downstream of those is currently mock. The user's framing — "we cannot test the actual performance of how the system will run" — is exactly correct.

The prototype-to-product plan in `D7` reorders work around **"first end-to-end live trace"** as the gating milestone — not feature counts.

---

## 3. The map / dashboard regression — bringing v1.1 visualization back

**Finding:** zero geo / map / globe / GDELT code is present in the repo today. The v1.1 plan (`PLAN-intelligence-center-v1.1.md`) called for a world-map dashboard fed by GDELT events; this was deprecated in v2.0 in favor of the trading-room-and-leaderboard layout, and never re-introduced.

**Diagnosis:** the v2.x dashboard is correct for the new product (trading-room first, brief second, leaderboard third) but it dropped the *single most visually distinctive* feature of v1.1 — the geographic-event map. That map is what makes the system feel like an *intelligence center* rather than just another stock-picker.

**Recommendation:** add it back as a **read-only embed**, not a re-implementation. Concretely:

1. **Data source** — GDELT 2.0 GKG (Global Knowledge Graph) DOC API + Events table. CSV pull every 15 minutes, write to `lake.geo_events(ts, lat, lon, theme, tone, src_url, urls TEXT[])`. ~30 MB/day raw; we already have a partitioned `lake.events` pattern to model on.
2. **Renderer** — embed an open-source globe. **Pick one** of: (a) `react-globe.gl` (Three.js based, MIT, easy), (b) Kepler.gl (heavier, slicker filters, MIT), (c) Datawrapper/MapTiler self-host (heavyweight). Recommend (a) — three days of work, fits in the existing React 19 dashboard.
3. **Wire it as an Intel agent output** — the intel agent already has a `dashboard.py` that produces a digest; add a `geo_dashboard.py` that emits the last-N-hours geo event payload. Render with React Query, refresh every 60s. No round-trip through advice.
4. **Filtering** — universe overlap, theme (`ECON_*`, `TAX_*`, `WB_*`), tone band, time window. Same persistence pattern as the disagreement table.
5. **Privacy/legal** — GDELT is public, no authentication, but rate-limit politely (their docs say ≤ 1 req/sec). Cache the 15-min CSV in `lake.geo_events`; serve the dashboard from the cache, not the live API.

**Cost:** $0 incremental — GDELT is free, the renderer is MIT-licensed, the cache lives in our existing Postgres.

**Why this matters beyond aesthetics:** geo-tagged event flow gives the Intel agent a **second axis of context** that pure-news synthesis lacks. A Yemen-Saudi tension cluster on the map is a meaningful prior for energy persona analysis even if no single news article triggers the trading-room gate. Add it as a *signal*, not just a viz.

See development plan §P5.

---

## 4. The configuration UI gap — replacing YAML/env/code-edit with a GUI

**Finding:** every knob in the system today is one of (a) a YAML file under `docs/prompts/` or `packages/featureflags/flags.yaml`, (b) an env var, or (c) a literal in source. There is **no** admin UI. Configuring the system means SSH-ing in, editing a file, and bouncing a container.

This is acceptable for a prototype run by the author. It will be unbearable for a mature product — even one with one user — because the things that need configuring change weekly: API keys, model choices, persona prompts, cadence, push channels, watchlist, agent enable/disable, cost behavior, FUTU account credentials.

### 4.1 Inventory of knobs that need a UI

| Domain | Today | Should be |
|---|---|---|
| **API keys** | `.env.example`, manually `cp .env.example .env` and edit | "Connectors" page in dashboard. One row per provider (DeepSeek, Anthropic, Groq, Polygon, Tradier, FRED, GDELT, Tushare, FUTU OpenD). Test-button per row. Encrypted at rest with sops or libsodium-sealed. |
| **Model picks** | `packages/llm-client/llm_client/_matrix.py` source | Same connectors page, second column: which model and tier per caller_id. Default views (`Pro for synthesis`, `Flash for ingest`) with override-rows. |
| **Cadence / cron** | `apps/orchestrator/orchestrator/cron/registry.py` Python | Settings → Schedules. Time-of-day, time-zone, enable/disable, manual-trigger button. (Cron-string editing in YAML is fine but the UI should generate the YAML.) |
| **Persona prompts** | `docs/prompts/persona/*.yaml` | Personas page already exists in the dashboard but is read-only. Add an edit mode that writes back to YAML and triggers a hot-reload via the existing `force_reload` parameter. Diff-and-confirm before save. |
| **Watchlist (50 tickers)** | hardcoded in fundamental agent | Fundamental page → Watchlist tab. CRUD with ticker validation against the quotation provider. |
| **Agent enable/disable** | `featureflags/flags.yaml` | Settings → Agents. Per-agent toggle, per-caller-id rate limit, per-agent cost cap. Already half-implemented in featureflags; just needs a UI. |
| **Notifier preferences** | env (`WECOM_TOKEN`, `WECOM_BOT_URL`) | Settings → Notifications. Channel × event-type matrix. Quiet hours. |
| **Output cadence (advice push frequency)** | source | Settings → Briefs. Brief times, push-on-event-impact ≥ X, "send me everything" / "only confirmed by board" toggle. |
| **FUTU account binding** | env, read-only by design | Settings → Brokers. List of Futu IDs. Per-account: OpenD endpoint, port, encryption. Verify button (read-only handshake). |

### 4.2 Architecture for the config UI

Keep YAML as the **persistence format**; the UI is just an editor. This preserves git-as-audit-trail and the smoke-test discipline. Concretely:

- Add `apps/admin_api/` — FastAPI service on port 8090. Reads/writes the YAML files under `docs/prompts/` and `packages/featureflags/`, plus a `secrets/sealed/*.yaml.enc` for sops-encrypted API keys.
- Every write goes through a **commit-style diff** (`PUT /admin/personas/dalio` returns the proposed YAML; `POST /admin/personas/dalio/apply` writes it and triggers reload).
- Every write is audited to `lake.config_audit(ts, actor, path, before_hash, after_hash, reason)`. Hash-chained like `lake.advice`.
- React dashboard adds three new routes: `Settings/Connectors`, `Settings/Schedules`, `Settings/Agents`.
- API keys are sops-encrypted with an age key checked into the host's keyring; the admin API decrypts on read, encrypts on write, and never returns the plaintext to the dashboard (the UI shows `••••` and a "rotate" button).

**Estimate:** 3 weeks for the API + 2 weeks for the React side. See development plan §P3.

---

## 5. FUTU portal + quotation simplification

**Finding:** you are right on both counts.

1. **There is no FUTU "portal"** — no UI to bind a Futu ID, no test-button, no audit visibility. The only configuration is env-vars consumed by the (currently mocked) `agent_futu`.
2. **FUTU OpenAPI does provide quotations** (level-1 free, level-2 paid). The current architecture treats FUTU as positions-only and was planning a separate market-data feed. Consolidating onto FUTU for quotations is a real simplification.

### 5.1 Verifying FUTU quotation capability

FUTU OpenAPI exposes:

- **`OpenQuoteContext`** — quotes, depth, K-line history, snapshots, subscriptions, market state. **Free tier covers HK + US level-1 real-time** with sub-account quotation rights; A-share L1 requires paid quote rights. (Source: FUTU OpenAPI v9.x docs.)
- **`OpenSecTradeContext`** — orders, positions. We currently use only this surface and limit to read-only.

The current `FutuReadOnlyClient` allow-list (`get_acc_list`, `accinfo_query`, `position_list_query`, `order_list_query`, `history_order_list_query`, `history_deal_list_query`) covers **only trading context** and should be extended to a **second client** wrapping `OpenQuoteContext` with its own allow-list (`get_market_snapshot`, `get_cur_kline`, `get_order_book`, `subscribe`, `unsubscribe`, `get_global_state`).

### 5.2 Why this simplifies the system

Today the implicit plan has separate quote sources per asset class (Polygon for US equities, Tushare for A, ccxt for crypto, Yahoo for fallback). That is N integrations, N billing relationships, N rate-limit logics, and N consistency problems for the backtester.

If FUTU covers HK + US for free and A at modest cost, we collapse three of those integrations into one:

- **Quotes** — `FutuQuoteClient` writing to `lake.quotes(ts, ticker, exch, bid, ask, last, vol, src='futu')`.
- **Subscription manager** — one place to track "which N tickers do we have a live quote subscription for", because FUTU caps simultaneous subscriptions per account (default 100 / 200 / 500 by tier).
- **Crypto and FX** — left for ccxt and a free FX feed (FRED for end-of-day or OANDA for tick); FUTU does not cover these.

This is not "FUTU for everything" — it is "FUTU for the assets it covers, one feed less for everything it doesn't."

### 5.3 What the FUTU portal should look like

Settings → Brokers → FUTU:

1. **OpenD endpoint table** — per Futu ID, host:port, TLS cert path, last-seen-online, last-snapshot-time. Add / edit / verify (verify = read-only `get_global_state` round-trip).
2. **Quotation tier** — free / level-2 / level-2 + A-share quotes. Selected tier drives what subjects we allow subscribing to.
3. **Subscription budget** — max simultaneous subs (read from FUTU `get_history_kl_quota`), current used, current pending. Visualized as a bar.
4. **Audit head** — last `lake.futu_audit` head hash + tip timestamp. Click to view the chain.
5. **Multi-account view** — same form repeated per Futu ID. No cross-account bleed.
6. **Hard rule rendered in UI** — "READ-ONLY ENFORCED. The trade-unlock surface is permanently disabled." Link to the audit-chain view.

### 5.4 Architecture changes to support this

- New file: `apps/agent_futu/futu/quote_client.py` — second `FutuReadOnlyClient` wrapping `OpenQuoteContext`. Same `__getattr__` allow-list pattern.
- New schema: `lake.quotes` (Timescale-hyperlinked, `(ticker, ts)` PK, partition by month).
- New routing: `agent_futu` exposes `/quote/snapshot`, `/quote/kline`, `/quote/depth` (read-only, internal-only).
- Subscription manager keeps state in NATS KV `iic_state/futu_subs` so reboots don't cost money to re-handshake.
- `agent_quant` and `agent_fundamental` switch their (currently nonexistent) price reads to `FUTU_QUOTE_CLIENT.snapshot()`.

See development plan §P4.

---

## 6. Intelligence agent — what it should fetch, how, and what it emits

You asked to review how the intel agent collects info and translates it for downstream agents. Today: it collects almost nothing (RSS only, mostly tested with `InMemoryCrawler`) and emits a digest that nobody downstream actually consumes (the consumers are stubs).

### 6.1 Real data sources we should wire

| Source | Type | License/Cost | API | Purpose |
|---|---|---|---|---|
| **GDELT 2.0** | Geopolitical events + GKG | Free, public | GDELT-DOC API + 15-min files | Map dashboard, regime-change-score, event volume by region. **Highest-priority new feed.** |
| **Reuters / AP via NewsAPI.org** | Headline news | $449/mo Business or free dev tier (1k/day) | REST | Replaces ad-hoc RSS for high-volume news. |
| **RSS / Atom feeds** | Same publishers + niche sources (FT Alphaville, Stratechery, ZeroHedge, etc.) | Free | (Already shipped) | Long tail. Keep. |
| **SEC EDGAR** | Filings | Free | RSS + REST | Fundamental agent input. 10-K, 10-Q, 8-K, 13F, S-1. |
| **HKEX disclosures** | HK filings | Free | REST | Same purpose for HK universe. |
| **Tushare or akshare** | A-share filings + econ | Free with rate limit | REST + ws | A-share filings + macro. |
| **FRED** | US macro | Free, key | REST | CPI, NFP, yield curve, money supply, IP, ISM. |
| **BLS** | US labor | Free | REST | NFP details. |
| **ECB / BOE / BOJ / PBOC** | Non-US macro | Free | REST | Macro coverage. |
| **CoinGecko** | Crypto prices + sentiment | Free Demo / $129 Pro | REST | Crypto persona inputs. |
| **CME Group** | Treasuries / equity-index futures + COT | Free (delayed) / paid (real-time) | FTP + REST | Curve and positioning. |
| **FUTU OpenAPI** | Quotations (HK / US / A) | Free L1 / paid L2 | TCP | Replaces Polygon/Tushare for the assets FUTU covers. (Section 5.) |
| **OpenSky / Marine Traffic / Flightradar24** | Alternative data | Free dev tier | REST | Optional, T3-tier. |

The intel agent should **not** consume all of these directly. Splitting:

- **Intel agent** = news + GDELT + sentiment + dedupe + ranking + brief synthesis.
- **Fundamental agent** = SEC + HKEX + Tushare filings + valuation.
- **Macro agent (new)** = FRED + BLS + CB + ECB. Today this is a stub `InMemoryMacroSource`. Either fold into intel as a sub-pipeline or split out — see development plan §P2.
- **Quant agent** = quotes (via FUTU) + factor library.

### 6.2 The "feed-in frequency" question

Your point: "configuring the intel feed-in frequency [is hard]." Today it's not configured at all — the cron registry has `morning_brief` only. Five other cron jobs are mentioned in the plan and **not registered** (see `D3 Architecture Review` §1).

Recommended cadence per source:

| Source | Cadence | Why |
|---|---|---|
| GDELT GKG | every 15 min | matches GDELT's 15-min file release cycle |
| RSS | every 5 min | balance freshness vs polite |
| NewsAPI / Reuters | every 5 min | rate-limited, batch by since-cursor |
| SEC EDGAR | every 15 min | filings are bursty; 8-Ks within a session matter |
| HKEX | every 15 min | same |
| FRED | hourly during US/EU business hours | macro releases happen on calendar slots |
| FUTU quotes (subscribed) | live (ws) | subscription is push, not poll |
| FUTU quotes (snapshot for non-subscribed) | every 60s during market hours | poll budget |
| Crypto | every 60s during weekdays / every 5 min weekends | always-on market |
| CME COT | weekly Friday 15:30 ET | release schedule |

Make this configurable via the Settings → Schedules UI (§4.1).

### 6.3 What intel emits to the rest of the fleet

Today the pipeline emits:
- `result.accepted_events` — list of deduped events
- `result.digest` — markdown brief
- `result.brief` — synthesized morning brief

Downstream:
- The **digest** is the only structured output; it should be the primary contract. Define it in `packages/schema/schema/intel/digest.v1.py` (today it's a Pydantic ad-hoc).
- Each accepted event should produce a `intel.event.high_impact.v1` if it crosses thresholds (already used by the Event-Triage Gate).
- For the trading room, intel should also emit `intel.context.v1` (per-ticker rolling 24h sentiment + event count + regime-change score) so the persona/quant/fundamental teams can attach context to plans without re-fetching.

`intel.context.v1` does not exist today. **It should be the first new schema added** post-hotfix. See development plan §P2.

---

## 7. Secretary agent re-architecture — making it the leader, not a sink

You are right to flag this as a major gap. Your vision: secretary is the **bridge between user and agent fleets**, can route user requests, can ask agents to redo their analysis. Today's reality: secretary is a one-way notification surface that cannot dispatch anything.

### 7.1 The exact scope of the gap

`apps/agent_secretary/secretary/main.py` — endpoints in increasing competence:

- `GET /health` — works.
- `POST /run/morning_brief|midday_check|evening_recap` — return `{"status":"queued"}`. **Stubs.**
- `GET /leaderboard` — returns hardcoded markdown.
- `POST /notifier/wecom/callback` — receives WeCom messages, parses slash commands. **Inbound only.**
- `POST /notifier/alertmanager` — receives Alertmanager webhooks, returns parsed counts. **Inbound only.**

Slash command bodies (`apps/agent_secretary/secretary/inbound/slash_commands.py`):
- `/leaderboard` → `"_(populated when backtester emits)_"` (hardcoded, no fetch)
- `/explain <id>` → `"deep-explain plan queued."` (hardcoded, no dispatch)
- `/why <ticker>` → `"pending lake.advice query."` (hardcoded, no DB read)
- `/disagree <ticker>` → "rendering pending advice scan." (hardcoded, no DB read)
- `/quiet <minutes>` → `"muted for {minutes} minutes"` — **no actual mute applied**, no state mutation.
- `/tone <terse|conv|edu>` → string echo, no state.

Every "do" verb is a placeholder. Secretary today cannot:

- Read from `lake.advice`.
- Issue a request to any other agent (intel, fundamental, quant, persona, board, backtest).
- Mutate any system state (mute, tone, watchlist, schedule).
- Queue work.
- Report on work it queued.

### 7.2 What the leader-secretary should look like

Five new responsibilities, in order of importance:

1. **Outbound dispatcher.** Inject `HttpxAgentClient` (already exists in orchestrator) + `BusClient` (NATS request-reply). On `/explain`, dispatch a deep-explain job to persona/board/intel as appropriate; track the trace ID; reply when complete.
2. **State holder.** `secretary.user_prefs.v1` — quiet hours, tone, watchlist priorities, opt-in/out per agent. Persisted in `lake.user_prefs` (small table). Slash commands mutate this; outbound notifier reads it before pushing.
3. **Conversational planner (LLM-powered).** Today's slash commands cover seven verbs. Real users will ask things like "What changed about Yemen since yesterday?" or "Why did Burry go short on $XYZ?" Secretary needs a planner LLM call (`secretary.plan` caller, Pro tier) that turns natural language into a sequence of agent-RPCs and stitches the results.
4. **Conversation memory.** Per-WeCom-user-id rolling context. `lake.secretary_thread(thread_id, ts, role, content)`. Cap at 100 turns / 30 days.
5. **Agent-of-agents handoff.** When the user says "have Buffett rework his analysis with this new earnings release", secretary issues a `persona.daily/weekly` re-run with the override context. Today there is no such interface; needs a `re_run(caller, override_signals)` endpoint on each agent.

### 7.3 Position in workflow — proposed change

Today's flow (events left to right):

```
intel → event-triage → trading room (quant/fund/persona) → board → advice ledger → notifier → user (one-way)
                                                                            ↓
                                                                   user replies via WeCom
                                                                            ↓
                                                                   secretary parses /slash → returns canned text
```

The secretary is downstream. Outbound flows do not pass through it. User replies dead-end at the secretary (nothing dispatches).

Proposed flow:

```
                          ┌───────────────────────────────────────────┐
                          │              SECRETARY (router)            │
                          │  • inbound: WeCom, web chat, alertmanager │
                          │  • outbound dispatcher to all agents      │
                          │  • LLM planner for natural language       │
                          │  • user prefs + conversation memory       │
                          └─────────────┬─────────────────────────────┘
                                        │  RPC fanout
       ┌────────────────────────────────┼──────────────────────────────────────┐
       ▼                ▼               ▼                ▼                   ▼
     intel         fundamental        quant         persona×N             board
       │                │               │                │                   │
       └────────────────┴───────────────┴────────────────┴───────────────────┘
                                        │
                                        ▼
                              advice ledger / lake
                                        │
                                        ▼
                           secretary composes brief, pushes
```

The secretary stays at the **edge** for user contact but gains **outbound RPC** in both directions (push notifications and on-demand fanout to agents). The orchestrator keeps the *event-driven* path (intel → event-triage → trading-room → board); the secretary owns the *user-driven* path.

This is essentially making secretary a "front-of-house" plus a "concierge" — but with code, not chat.

### 7.4 Implementation sketch

- Inject `agents` registry into the secretary at startup (the orchestrator's `agent_client.HttpxAgentClient` table).
- Add `secretary.plan` LLM caller (Pro tier when the question is multi-step, Flash for single-shot).
- Add three new endpoints:
  - `POST /chat` — plain-language user input → planner → fanout → reply (with trace ID).
  - `POST /rerun` — explicit "have agent X redo job Y with override Z."
  - `POST /prefs/{key}` — set user prefs (mute, tone, push-cadence).
- Replace every "queued" placeholder in slash commands with real fanouts.
- Add `lake.secretary_thread` and `lake.user_prefs` migrations.

See development plan §P6.

---

## 8. LLM API allocation — one key vs many, pro vs flash

You asked: "how many LLM APIs should I prepare? Will a separate API per agent work better theoretically? Which task should use pro, which flash?"

### 8.1 The architectural-purity answer (separate keys per agent)

**Theoretical wins** — these are real:

- **Quotas** — DeepSeek, Anthropic, OpenAI all rate-limit per API key. Separate keys give each agent its own bucket. One agent in a hot loop can't starve another.
- **Cost attribution** — billing per key shows exactly which agent burned which dollars. The cost-meter today aggregates per-caller-id post-hoc; provider-side billing is more authoritative.
- **Blast radius** — a leaked key affects only one agent's surface.
- **Concurrency limits** — Anthropic and DeepSeek both cap concurrent in-flight requests per org, but rate limits often differ per key.

**Theoretical losses** — also real:

- **Operational surface** — N keys means N rotation tasks and N "is this the right key" debug paths.
- **No spillover** — if intel doesn't use its quota, persona can't borrow it.
- **Cache/duplication** — embedding / translation cache hits across agents are harder when keys differ.
- **Provider min-spend / volume discounts** — Anthropic and DeepSeek offer tiered pricing on aggregate volume; splitting keys can lose the discount.

**The honest answer:** **separate keys per *agent group*, not per agent**. Three keys total:

1. `intel-and-ingest` — high-volume cheap calls. Intel crawler/translate/sentiment, fundamental filings extract, persona-daily, secretary-chat default. Mostly Flash.
2. `synthesis-and-reasoning` — low-volume expensive calls. Intel.synth, fund.valuation, board.chair, orchestrator.plan, persona.weekly, secretary.brief.morning. Mostly Pro.
3. `dev-and-eval` — for scripted backfills, eval-runs, golden tests. Same provider, separate billing alarms. Keep the prod key out of CI.

This gives the rate-isolation benefit without N rotation tasks. The router already supports caller-scoped routing; just add a `key_pool` field to the matrix.

### 8.2 Which tasks should be Pro vs Flash

Reading the existing matrix is most of the answer; it's mostly correct. The places where I'd revise:

| Caller | Today | Recommended | Why |
|---|---|---|---|
| `intel.synth` | Pro always | Pro always | Correct. Synthesis quality is the product. |
| `intel.crawler.translate` | Flash, 24h cache | Flash, 7d cache | Translations of static news bodies don't go stale; longer cache cuts cost without harming quality. |
| `intel.sentiment.classify` | Flash, 1h cache | Flash, 24h cache + dedupe-by-hash | Same. |
| `intel.dedupe.embed` | Embed model | Embed (small, e.g. text-embedding-3-small) | Don't escalate. Quality of dedupe at this scale is fine with the cheap embed. |
| `fund.valuation` | Pro always | Pro always | Correct. |
| `fund.filings.extract` | Flash, escalate >200pp | Flash, escalate >100pp **OR** filing_type ∈ {10-K, 13F-HR, S-1} | 200pp threshold is too coarse — many 8-Ks under 50pp need Pro because they're regime-changing. |
| `quant.writer` | Flash, escalate on regime change | Flash, escalate on regime change | Correct. |
| `persona.daily` | Flash | Flash | Correct. |
| `persona.weekly` | Pro always | Pro always | Correct. |
| `secretary.chat` | Flash, escalate on explain_deeply | Flash, escalate on `multi_step_question` OR question contains "why" / "explain" | Add keyword-triggered escalation to catch users who don't say "explain deeply". |
| `secretary.brief.morning` | Pro always | Pro always | Correct. |
| `secretary.brief.midday` | Flash | Flash | Correct. |
| `secretary.plan` (new) | — | Pro on multi-step, Flash on single-RPC | New caller for the leader-secretary. |
| `orchestrator.plan` | Pro always | Pro always | Correct. |
| `event_triage` | Flash | Flash with `temperature=0.0`, `max_tokens=8` | Correct. The deterministic shape protects budget. |
| `board.bull/bear/risk_*` | Flash | Flash | Correct. |
| `board.chair` | Pro always | Pro always | Correct. |
| `backtest.narrate` | Flash | Flash | Correct. Don't escalate post-hoc narration. |

### 8.3 What providers to register

Recommended provider matrix (no "if you only had one key" caveat — set up all three from day one):

- **Primary Pro:** DeepSeek-V4 Pro (cheap synthesis at acceptable quality; good ZH support for the WeChat brief).
- **Primary Flash:** DeepSeek-V4 Flash (fastest cheap path, same vendor).
- **Fallback Pro:** Anthropic Claude Sonnet 4.6.
- **Fallback Flash:** Groq Llama-3.3-70B.
- **Embeddings:** OpenAI `text-embedding-3-small` (cheapest reliable). Keep a self-hosted bge-large fallback for sovereignty if you ever go fully offline.

This is what the current matrix targets; just configure all four keys instead of running on synthetic-skip.

### 8.4 Bottom line

Theoretically separate keys per agent helps with isolation. **Pragmatically, three key-pools (ingest / synthesis / dev) capture 90% of the benefit at 30% of the operational cost.** Implement this first; promote to per-agent only if rate-limit collisions become real.

---

## 9. Cost gate posture — remove for now, keep rate-limit

You are right. The cost gate is premature.

### 9.1 What to remove

- `DEFAULT_MONTHLY_CAP_USD = 90.0` in `packages/llm-client/llm_client/cost_meter.py`. Set to **`float("inf")`** by default.
- The breaker state machine in `apps/orchestrator/orchestrator/state/kv.py` (`get_cost_breaker_state` / `set_cost_breaker_state`). Don't *delete* the code — gate it on a feature flag `cost_breaker.enabled` defaulting to `false`.
- The `chat_or_skip` synthetic-skip return path. Replace with `chat_or_raise`: if the breaker is disabled, errors out loud (timeout / rate-limit / auth failure) instead of returning a placeholder. We *want* to know when calls fail.
- Synthetic-skip-tainted advice tagging. With the breaker off, this never triggers.

### 9.2 What to keep (and what to *add*)

Keep:

- **Per-provider rate-limit handling.** Exponential backoff + jitter on 429s. Provider already has hard quotas; don't fight them.
- **Per-call timeout.** Keep, with sane defaults (60s for Pro synthesis, 15s for Flash, 5s for embed).
- **Per-caller observability.** Keep logging cost per call to `lake.llm_calls`. We *want* to measure spend, just not block on it.

Add:

- **Hard provider rate-limit.** A token-bucket rate-limiter per (provider, key) that throttles requests *before* the provider 429s. Saves goodwill with the provider and prevents 429 storms.
- **Per-caller_id concurrency cap.** Prevents one runaway agent from consuming all in-flight slots.

### 9.3 Why this is the right move now

Three reasons:

1. We don't know what the system actually costs at full speed because no agent has ever run end-to-end against real APIs. Setting a $90 cap before measurement is guesswork.
2. The `chat_or_skip` synthetic-skip path is currently the **modal response** — meaning the gate is suppressing every call we'd want to see in development. Removing it converts silent failures into loud failures.
3. Once the system actually runs and we have a week of `lake.llm_calls` data, we can reintroduce a budget aware of real consumption.

See development plan §P0 (immediate, before P1).

---

## 10. Mocks / placeholders inventory — full list with disposition

Listed in priority order (highest-priority = "blocks first end-to-end live trace").

### Tier A — must replace before any meaningful test

| ID | File | Today | Replace with |
|---|---|---|---|
| M-A1 | `packages/llm-client/llm_client/router.py:synthetic_skip_response` | Returns synthetic-skip marker on cost-breaker open OR provider failure | Real provider call, `chat_or_raise` semantics. (§9) |
| M-A2 | `apps/agent_intelligence/intel/factory.py` defaults | `InMemoryCrawler`, `InMemoryHashStore`, `InMemorySemanticIndex`, `InMemoryMacroSource`, `InMemoryEventStore` | Live RSS+GDELT crawler; Redis hash store; pgvector semantic index; FRED macro; Postgres `lake.events` event store. (§6, dev-plan P2) |
| M-A3 | `apps/agent_intelligence/intel/factory.py:_default_embed:hash_embed` | Deterministic hash, **no semantic content** | LLM router `embed()` call against `text-embedding-3-small`. |
| M-A4 | `apps/agent_futu/futu/main.py:FakeOpenD` | Hardcoded fake | Real OpenD per Futu ID, plus `FutuQuoteClient` for quotation. (§5, dev-plan P4) |
| M-A5 | `apps/agent_secretary/secretary/main.py:/run/morning_brief` etc. | `{"status":"queued"}` | Real composition: query `lake.advice`, query `lake.intel.digest`, render markdown via `secretary.brief.morning` LLM call. (§7) |
| M-A6 | `apps/agent_secretary/secretary/inbound/slash_commands.py:_render` | Hardcoded strings | Real fanout dispatch. (§7) |

### Tier B — must replace before claiming each agent works

| ID | File | Today | Replace with |
|---|---|---|---|
| M-B1 | `apps/agent_fundamental/fund/main.py:run_cover, run_digest` | Stub returns | EDGAR/HKEX/Tushare fetch, parse, valuate, emit `fund.cover.v1` / `fund.digest.v1`. |
| M-B2 | `apps/agent_quant/quant/main.py:run_factors, run_signal, run_walk_forward` | Stub returns | Factor library (momentum, mean reversion, vol risk premium, PEAD, insider clusters, sector strength, crypto basis, FX carry); walk-forward backtest. |
| M-B3 | `apps/agent_persona/persona/main.py:run_daily, run_weekly` | Stub returns | LLM-driven persona analysis with the loaded YAML spec; emits `advice.v1` with persona disclaimer. |
| M-B4 | `apps/agent_backtest/backtest/main.py:*` | All stubs | Virtual portfolio book + paper-trade simulator + leaderboard. |

### Tier C — known cosmetic/dev shortcuts

| ID | File | Today | Replace with |
|---|---|---|---|
| M-C1 | `deploy/dev-entrypoint.sh` + `docker-compose.dev.yml` bind-mounts | Workaround for missing per-agent install of internal packages | Build-time `pip install -e packages/*` in each agent Dockerfile, or shared `iic-base` image. (§1.1 patch #8) |
| M-C2 | Multiple `parents[N]` path computations | Brittle | Standardize on `IIC_REPO_ROOT`. (§1.1 patch #7) |
| M-C3 | Stub LLM routers in test suites (`apps/*/tests/conftest.py`) | Test-only `StubLlmRouter` | Keep — these are correct test doubles. **No action**, listed for completeness. |

### Tier D — items that look like mocks but are actually correct

For honesty's sake, also call out things that *look* like mocks but are real:

- `FakeOpenD` in `agent_futu` is a *correct* test double during Phase A. The architecture says this stays until Phase B real-OpenD lands. Not a bug.
- The `chat_or_skip` API itself is *correct as a shape*; the bug is its default behavior. With the breaker disabled it should call through to `chat()`.
- The dashboard's React Query placeholders (`(populated when …)`) are *correct empty states* — they render real data once present.

---

## 11. Closing assessment — readiness scorecard

A 1–5 score where 1 = mock/empty and 5 = production-quality:

| Area | Score | Comment |
|---|---|---|
| Substrate (Postgres/Timescale/NATS/Redis/Compose) | **4** | After hotfix. Pin digests. |
| Schemas + advice ledger | **4** | Real, versioned, tested. |
| DAG runtime + breaker + SLA executor | **4** | Real. |
| Routing matrix + tier escalation | **4** | Real. |
| Investment Board pipeline | **3** | Code real, but every call short-circuits to synthetic-skip without keys. |
| FUTU read-only enforcement | **4** | Walls are correct. Phase B unbuilt. |
| Intel pipeline | **2** | RSS path real; everything else `InMemory*`. |
| Fundamental / Quant / Backtest agents | **1** | Pure stubs. |
| Persona agents (analytical) | **1** | Spec loader real; analysis stub. |
| Secretary | **1** | Notification sink only; no dispatch, no state, no LLM. |
| Dashboard | **3** | Scaffolding real; many panes wired to empty data. |
| Configuration / admin UI | **0** | Does not exist. |
| Map / geo dashboard | **0** | Does not exist. |
| Cost breaker (as currently configured) | **2** | Working but actively harmful — short-circuits everything. Disable. |
| Real LLM API integration end-to-end | **1** | Code paths exist; never run with real keys. |
| Real intel API integration | **1** | RSS-only; no GDELT, no SEC, no FRED. |
| Real quote ingest | **0** | Does not exist. |
| Documentation (plans, summary) | **5** | Excellent — overdocumented, if anything. |

**Aggregate read:** the system is ~25% of a product. The missing 75% is concentrated in *agent thinking* (1s on the scorecard) and *user-facing configuration / map* (0s). The development plan re-orders the next iteration around closing those gaps in the order that gives the fastest first-end-to-end-live-trace.

---

## 12. Companion development plan

See `D7_IIC_Development_Plan_Prototype_to_Product.md` — phases P0 through P9, function-by-function, with acceptance criteria.

---

## Appendix A — Hotfix branch file list (for the record)

```
README.md                                                            (+28)
apps/orchestrator/orchestrator/plan/personas.py                      (+22 -6)
deploy/dev-entrypoint.sh                                             (new, +30)
deploy/run-migrations.sh                                             (+4 -1)
docker-compose.dev.yml                                               (+131 -18)
docker-compose.yml                                                   (+7 -1)
infra/postgres/Dockerfile                                            (new, +21)
infra/postgres/init-roles.sql                                        (+15 -4)
packages/data-lake/data_lake/migrations/versions/0001_init_lake.py   (+10 -5)
packages/data-lake/data_lake/migrations/versions/0003_llm_telemetry.py (+5 -2)
packages/data-lake/data_lake/migrations/versions/0004_eval_runs.py     (+5 -2)
```

## Appendix B — Repo state references

Inspected files (non-exhaustive):

- `apps/orchestrator/orchestrator/{app.py,plan/event_triage.py,plan/personas.py,plan/agent_client.py,execute/runner.py,execute/sla.py,state/kv.py,merge/advice_merger.py}`
- `apps/agent_secretary/secretary/{main.py,inbound/{slash_commands.py,wecom_callback.py,alertmanager.py,disagreement.py},auth.py}`
- `apps/agent_intelligence/intel/{main.py,factory.py,pipeline.py,crawler/rss.py,sources.py,brief.py,sentiment.py,bias_balance.py,synth.py,translate.py,publish.py,persistence.py,dashboard.py,dedupe/{hash_gate.py,semantic_gate.py},macro/protocol.py,types.py}`
- `apps/agent_fundamental/fund/main.py`
- `apps/agent_quant/quant/main.py`
- `apps/agent_persona/persona/main.py`
- `apps/agent_backtest/backtest/main.py`
- `apps/agent_board/board/{main.py,chair.py,bull.py,bear.py,risk_aggressive.py,risk_conservative.py,risk_neutral.py}`
- `apps/agent_futu/futu/{main.py,readonly_client.py,fake_opend.py,aggregator.py,audit.py}`
- `apps/dashboard/src/{App.tsx,components/Shell.tsx,routes/*.tsx,types/{iic,plan,board}.ts,lib/{nats,tone}.ts}`
- `packages/llm-client/llm_client/{_matrix.py,router.py,cost_meter.py,types.py,exceptions.py,adapters/base.py}`
- `packages/{schema,featureflags,data-bus,notifier,prompts,data-lake}/...`
- `infra/postgres/{Dockerfile,init-roles.sql}`
- `deploy/{dev-entrypoint.sh,run-migrations.sh}`
- `docker-compose.{yml,dev.yml}`
- `packages/data-lake/data_lake/migrations/versions/000{1,3,4}_*.py`
- `plan/{EXECUTIVE_SUMMARY_bilingual.md,IIC_Development_Plan_v2.5_Combined.md,PLAN_v2.1_Investment_Intelligence_Center.md,D5_IIC_Prototype_Review_and_Next_Iteration.md}`

— end of D6 —
