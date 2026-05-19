# D7 — IIC Development Plan: Prototype → Product

**Audience:** Ziwei (vibe-coder)
**Author:** ai-engineer agent
**Date:** 2026-05-10
**Companion review:** `D6_Architecture_Review_Prototype_to_Product.md`
**Mode:** function-by-function to-do list. Each item has ground-truth file paths, the function/class to write or change, the acceptance criteria, and a "vibe prompt" you can paste at the agent that codes the task.

> **How to read this plan**
>
> - **Phases P0…P9** are ordered by dependency, not by calendar week. Land them serially unless flagged "parallel-ok".
> - **Items inside a phase** are individually small (≤ 1 day of agent-pair work each). Each one ends with an acceptance criterion that must be CI-checkable, not vibes.
> - **No time estimates.** The user asked for a detailed to-do list; cadence is whatever you pick. The dependency graph is the budget.
> - **"Replaces M-A1"** etc. references the mock inventory in `D6 §10`.
> - **Definition of done for the whole plan:** first end-to-end live trace from a real news event → real intel digest → real trading-room fanout → real Investment Board decision → real persisted advice → real WeChat brief, with no synthetic-skip in the chain. Everything else is in service of this.

---

## Phase index

| Phase | Title | Depends on |
|---|---|---|
| **P0** | Disable cost gate, expose real failures | nothing (do first) |
| **P1** | Production-grade packaging fix (close the hotfix gap) | P0 |
| **P2** | Real intel pipeline (live RSS + GDELT + dedupe + embeddings + macro) | P0, P1 |
| **P3** | Configuration UI / admin API | P1 |
| **P4** | FUTU portal + quotation client | P1 |
| **P5** | Map / geo dashboard | P2, P3 |
| **P6** | Secretary as leader-router agent | P2, P3 |
| **P7** | Fundamental + Quant + Backtest agents (the thinking nodes) | P2, P4 |
| **P8** | Persona agents (analytical) | P2, P3, P7 |
| **P9** | Production hardening — observability, CI gates, runbooks | all of the above |

---

## P0 — Disable cost gate, expose real failures

**Goal:** stop suppressing real LLM/API failures with synthetic-skip placeholders. From now on, when something doesn't work, we want to *see* it.

### P0.1 — Add `cost_breaker.enabled` feature flag, default `false`

**File:** `packages/featureflags/featureflags/registry.py`

Add:

```python
register_flag(
    name="cost_breaker.enabled",
    default=False,
    description="When true, LLM router gates calls on cost cap. Default off.",
)
```

**Acceptance:** `featureflags.flag("cost_breaker.enabled")` returns `False` on a fresh install. Test: `tests/featureflags/test_defaults.py::test_cost_breaker_disabled_by_default`.

**Vibe prompt:** *"Add a feature flag `cost_breaker.enabled` to `packages/featureflags/featureflags/registry.py` with default False, and add a unit test in `tests/featureflags/test_defaults.py` asserting it's off out-of-the-box."*

### P0.2 — Add `chat_or_raise` to `LlmRouter`; gate `chat_or_skip` on the flag

**File:** `packages/llm-client/llm_client/router.py`

Change:

```python
async def chat_or_raise(self, caller_id: str, messages: list[ChatMessage], **kw) -> ChatResponse:
    """Like chat() — never returns synthetic-skip. Raises on provider failure."""
    return await self._chat_internal(caller_id, messages, allow_skip=False, **kw)

async def chat_or_skip(self, caller_id: str, messages: list[ChatMessage], **kw) -> ChatResponse:
    if not flag("cost_breaker.enabled"):
        return await self.chat_or_raise(caller_id, messages, **kw)
    # ... existing breaker logic ...
```

**Acceptance:** with `cost_breaker.enabled=False`, `chat_or_skip` calls a real provider and either returns a real `ChatResponse` or raises. Add test: stub the adapter to raise; assert `chat_or_skip` propagates the exception.

**Vibe prompt:** *"In `packages/llm-client/llm_client/router.py`, add `LlmRouter.chat_or_raise()` and rewrite `chat_or_skip()` to call `chat_or_raise()` when `cost_breaker.enabled` is False. Add unit tests covering both flag states."*

### P0.3 — Default `LLM_MONTHLY_CAP_USD` to `inf`

**File:** `packages/llm-client/llm_client/cost_meter.py:DEFAULT_MONTHLY_CAP_USD`

Change `90.0` → `float("inf")`. Keep the constant overridable via env so future tightening is one env var away.

**Acceptance:** `tests/llm_client/test_cost_meter.py::test_default_cap_unbounded` passes.

### P0.4 — Add per-provider rate-limiter with token bucket

**File (new):** `packages/llm-client/llm_client/rate_limit.py`

```python
class TokenBucketRateLimiter:
    def __init__(self, rate_per_sec: float, burst: int): ...
    async def acquire(self) -> None: ...
```

Wire into the adapter base class so each provider has one bucket per (provider, key). Configure from env: `IIC_RATE_DEEPSEEK_PRO=8`, etc.

**Acceptance:** integration test fires 100 concurrent calls; observes ≤ rate per second; no provider 429s.

### P0.5 — Per-caller_id concurrency cap

**File:** `packages/llm-client/llm_client/router.py`

Add a `Semaphore` per `caller_id` (configurable, default 4). Prevents a single agent from saturating the rate limit and starving others.

**Acceptance:** unit test with 16 concurrent calls to `intel.synth` shows max-in-flight ≤ 4.

### P0.6 — Audit-log call outcomes (whether or not the cap was tripped)

**File:** `packages/llm-client/llm_client/router.py:_audit_call`

Continue logging every call to `lake.llm_calls` regardless of breaker state. Add `outcome ∈ {ok, error, timeout, rate_limit, skipped}` (already in schema; just ensure the path is exercised).

**Acceptance:** integration test posts 5 calls; `SELECT count(*) FROM lake.llm_calls` = 5.

---

## P1 — Production-grade packaging fix

**Goal:** make the agent images self-contained so production `docker compose up` works without bind mounts. Closes the hotfix's residual structural debt.

### P1.1 — Create `iic-base` image

**File (new):** `infra/iic-base/Dockerfile`

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY packages/ /app/packages/
RUN uv pip install --system -e packages/schema -e packages/featureflags \
    -e packages/llm-client -e packages/data-bus -e packages/notifier \
    -e packages/prompts -e packages/data-lake
```

**Acceptance:** `docker build -t iic-base:latest infra/iic-base/` succeeds; `docker run --rm iic-base python -c "import schema, featureflags, llm_client, data_bus, notifier, prompts, data_lake"` exits 0.

### P1.2 — Migrate each agent Dockerfile to `FROM iic-base`

**Files:** `apps/{agent_intelligence,agent_fundamental,agent_quant,agent_persona,agent_backtest,agent_secretary,agent_board,agent_futu,orchestrator}/Dockerfile`

Each becomes:

```dockerfile
FROM iic-base:latest
COPY apps/<agent_name>/ /app/<agent_name>/
WORKDIR /app
CMD ["uvicorn", "<agent_name>.main:app", "--host", "0.0.0.0", "--port", "<port>"]
```

**Acceptance:** for each agent, `docker run --rm <image> python -c "import <agent_name>.main"` exits 0. CI matrix runs this for all nine agents.

### P1.3 — Drop the dev bind-mounts and `dev-entrypoint.sh`

**File:** `docker-compose.dev.yml`

Remove the `volumes:` lines that mount `./packages/*` and the `entrypoint: dev-entrypoint`. Keep one volume for live source-mounting of `apps/<agent>/<module>/` so code-edits don't require rebuild.

**Acceptance:** `make setup` on a fresh box passes the smoke check (13/13 healthy) without the dev-entrypoint workaround.

### P1.4 — Pin Postgres image by digest

**Files:** `infra/postgres/Dockerfile`, `docker-compose.yml`

Replace `FROM timescale/timescaledb-ha:pg16` with the digest-pinned form `FROM timescale/timescaledb-ha@sha256:<digest>`. Same for the resulting `iic-postgres:pg16-partman` — pin the tag.

**Acceptance:** `make setup` succeeds; `docker compose config` shows the digest.

### P1.5 — Add shellcheck + dockerfile linting + alembic-hypertable lint to CI

**File (new):** `.github/workflows/static-checks.yml`

- Runs `shellcheck deploy/*.sh` (catches the `tr -c` newline class).
- Runs `hadolint infra/**/Dockerfile apps/**/Dockerfile`.
- Runs a custom Python check that imports every alembic migration and verifies any table later passed to `create_hypertable` has the partitioning column in its PK (catches the `lake.llm_calls` / `lake.eval_runs` class).

**Acceptance:** CI passes today; CI fails on a deliberately re-broken regression PR.

### P1.6 — Standardize on `IIC_REPO_ROOT`; remove all `parents[N]` arithmetic

**Files:** `apps/orchestrator/orchestrator/plan/personas.py`, plus all other call sites (grep for `parents\[`).

Replace each computation with `repo_root() / "docs/prompts/persona"` where `repo_root()` reads `IIC_REPO_ROOT` env (set in compose / smoke / CI / pyproject's `[tool.iic]` config).

**Acceptance:** `git grep "parents\[" apps/ packages/` returns no results outside of test fixtures.

### P1.7 — CI step: re-run `make setup` from a clean Ubuntu 26.04 image

**File (new):** `.github/workflows/fresh-bringup.yml`

Spin a clean `ubuntu:24.04` GH runner-equivalent (or self-hosted), `git clone`, `make setup`, run the smoke check. Daily.

**Acceptance:** workflow passes today and remains green; flakes get a `flaky-bringup` label and a bug.

---

## P2 — Real intel pipeline

**Goal:** replace every `InMemory*` default with a working real-data path. Add a second high-priority feed (GDELT). Add a real embedding model. Add a working macro source.

### P2.1 — Live RSS source loader from `INTEL_SOURCES_PATH`

**File:** `apps/agent_intelligence/intel/sources.py:load_sources`

Already exists; verify it actually loads and that there's a default `infra/intel/sources.yaml` shipped with ~50 publishers.

**Acceptance:** `make seed-intel-sources` populates the config; `INTEL_AUTOSTART=1` brings up intel and `/run/synthesize` returns >10 events from real RSS within 60s of startup.

### P2.2 — Redis hash-gate for de-dup

**File:** `apps/agent_intelligence/intel/dedupe/hash_gate.py`

Add `RedisHashStore(redis_client, ttl=7d)` implementation alongside `InMemoryHashStore`. Switch the factory on `INTEL_HASH_STORE_BACKEND=redis`.

**Acceptance:** integration test posts 1000 events with 50% near-duplicates; `RedisHashStore` rejects the duplicates; survives a process restart.

### P2.3 — pgvector semantic gate

**Files:**
- `packages/data-lake/data_lake/migrations/versions/0006_pgvector.py` — `CREATE EXTENSION vector;` + `lake.intel_embeds(event_id UUID, embedding VECTOR(1536), ts TIMESTAMPTZ, PRIMARY KEY (event_id, ts))` (composite PK; this is hypertabled on `ts`).
- `apps/agent_intelligence/intel/dedupe/semantic_gate.py:PgvectorSemanticIndex`

**Acceptance:** integration test inserts 100 events; semantically-near-duplicate rejection rate ≥ 80% on a labeled mini-corpus.

### P2.4 — Real LLM embedding call

**File:** `apps/agent_intelligence/intel/factory.py:_default_embed`

Replace `hash_embed(text)` with `await llm_router.embed(caller_id="intel.dedupe.embed", input=text)`. The router already has `embed()` — wire it.

**Acceptance:** unit test mocks the adapter to return a known vector; pipeline calls it; matches.

### P2.5 — GDELT 2.0 GKG crawler

**Files (new):**
- `apps/agent_intelligence/intel/crawler/gdelt.py` — pulls the 15-min CSV, parses, emits `RawEvent` per row with `theme`, `tone`, `geo`.
- `infra/intel/gdelt-config.yaml` — themes-to-watch, tone bands, geo-overlap-with-universe rules.

**Acceptance:** integration test fetches the latest GDELT file (or a checked-in fixture), produces ≥ 100 events, dedupes correctly.

### P2.6 — Postgres `EventStore` implementation

**Files:**
- `apps/agent_intelligence/intel/persistence.py:PostgresEventStore`
- Migration: `lake.events` already exists from migration 0001. Wire it.

**Acceptance:** integration test seeds 50 events; `SELECT count(*) FROM lake.events` returns 50.

### P2.7 — `intel.context.v1` schema (per-ticker rolling context)

**Files (new):**
- `packages/schema/schema/intel/context.py` — `IntelContextV1` Pydantic.
- `apps/agent_intelligence/intel/context.py:build_context(ticker)` — windowed query over `lake.events`, returns sentiment EMA, event count, regime-change score.

**Acceptance:** unit test builds context for a ticker with 50 events; matches expected aggregates.

### P2.8 — Macro source from FRED

**Files (new):**
- `apps/agent_intelligence/intel/macro/fred.py:FredMacroSource` — pull-on-cadence per series.
- `infra/intel/macro-series.yaml` — ~30 series (CPI, Core CPI, NFP, UMCSENT, GS10, GS2, M2, ISM, ICE BofA HY OAS, DXY, etc.).

**Acceptance:** integration test (key in env) pulls live; persisted to `lake.macro_series(ts, series_id, value, src)`.

### P2.9 — Cron registry: register all five cron jobs

**File:** `apps/orchestrator/orchestrator/cron/registry.py`

Today only `morning_brief` is registered. Add: `intel_rss_pull`, `intel_gdelt_pull`, `intel_macro_pull`, `midday_check`, `evening_recap`. Each one bound to a real handler.

**Acceptance:** `GET /admin/crons` returns all five; smoke check verifies each fires at least once in a 1-hour synthetic window with simulated time.

### P2.10 — Intel digest schema versioning

**File:** `packages/schema/schema/intel/digest.py`

Promote the ad-hoc digest dataclass to `IntelDigestV1`. Pin in goldens.

**Acceptance:** golden test passes; backwards-compat guard rejects breaking changes.

### P2.11 — Wire intel → event-triage end-to-end

**Files:** intel publishes `intel.event.high_impact.v1` to NATS; orchestrator's `event_triage` already subscribes.

**Acceptance:** integration test seeds a high-impact event in intel; verifies trading-room is woken (or recorded as woken) within 2s.

---

## P3 — Configuration UI / admin API

**Goal:** replace YAML/env/code-edit with a web UI. Keep YAML as persistence (git-as-audit).

### P3.1 — `apps/admin_api/` skeleton

**Files (new):**
- `apps/admin_api/admin_api/main.py` — FastAPI app on port 8090.
- `apps/admin_api/admin_api/config_io.py` — read/write YAML files under `docs/prompts/`, `packages/featureflags/`, `infra/intel/`.
- `apps/admin_api/admin_api/audit.py` — append every write to `lake.config_audit` (hash-chained like advice).
- `Dockerfile`, compose entry.

**Acceptance:** `curl localhost:8090/health` → `{"status":"ok"}`. `GET /admin/personas/dalio` returns the YAML.

### P3.2 — Migration: `lake.config_audit`

**File (new):** `packages/data-lake/data_lake/migrations/versions/0007_config_audit.py`

```sql
CREATE TABLE lake.config_audit (
  id UUID NOT NULL,
  ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  actor TEXT NOT NULL,
  path TEXT NOT NULL,
  before_hash BYTEA,
  after_hash BYTEA NOT NULL,
  prev_chain_hash BYTEA,
  chain_hash BYTEA NOT NULL,
  reason TEXT,
  PRIMARY KEY (id, ts)
);
SELECT create_hypertable('lake.config_audit', 'ts');
```

**Acceptance:** migration applies cleanly; insertion test validates chain-hash continuity.

### P3.3 — Sealed secrets (sops + age)

**Files:**
- `apps/admin_api/admin_api/secrets.py` — load/save sops-encrypted YAML under `secrets/sealed/`.
- Existing `.sops.yaml` already configures key recipients — verify the wired path.

**Acceptance:** `POST /admin/secrets/deepseek_api_key` with plaintext writes encrypted; `GET` returns `••••` not plaintext; agents at boot read decrypted via the admin API or a sidecar.

### P3.4 — Connectors UI page

**Files (new):**
- `apps/dashboard/src/routes/SettingsConnectors.tsx` — list of connectors (DeepSeek, Anthropic, Groq, OpenAI-embeddings, FRED, NewsAPI, GDELT, Tushare, FUTU OpenD, WeCom). Per row: provider name, key field (write-only `••••`), model picker (where applicable), status pill, "Test" button that calls `POST /admin/connectors/<name>/test`.
- Backend: `apps/admin_api/admin_api/connectors.py:test_connector(name)` — per-connector live handshake.

**Acceptance:** clicking "Test DeepSeek" with a valid key returns a live `chat()` ping result.

### P3.5 — Schedules UI page

**Files (new):**
- `apps/dashboard/src/routes/SettingsSchedules.tsx` — list of cron jobs from §P2.9; per row: cron expression, time zone, enable toggle, manual-fire button.
- Backend: `apps/admin_api/admin_api/schedules.py` reads/writes `infra/cron/schedules.yaml`.

**Acceptance:** changing the morning-brief time persists in YAML and rebinds the cron without container restart.

### P3.6 — Personas UI (write mode)

**Files:** `apps/dashboard/src/routes/Personas.tsx` (already read-only; extend to edit).

Add a Monaco-based YAML editor; save calls `PUT /admin/personas/<slug>`; diff-and-confirm modal before commit; persona agent receives a hot-reload signal.

**Acceptance:** edit Dalio's `system_prompt`; click save; agent's next `/run/daily` uses the new prompt.

### P3.7 — Watchlist UI

**Files:** `apps/dashboard/src/routes/SettingsWatchlist.tsx`

Editable 50-ticker watchlist; on save, validates each ticker against the FUTU quote client (§P4.4); persists to `infra/quant/watchlist.yaml`.

**Acceptance:** adding `BABA` accepts; adding `XYZNOTREAL` rejects with the validation error.

### P3.8 — Agent enable/disable + per-caller rate-limit UI

**Files:** `apps/dashboard/src/routes/SettingsAgents.tsx`

Per-agent toggle (writes to `flags.yaml`); per-caller_id concurrency / rate-limit overrides.

**Acceptance:** disabling `agent_persona` causes orchestrator's next fanout to skip it; `lake.runs` reflects.

### P3.9 — Notifications UI

**Files:** `apps/dashboard/src/routes/SettingsNotifications.tsx`

Channel × event-type matrix (WeCom group, WeCom DM, ntfy, email). Quiet hours (e.g., suppress all non-critical pushes 22:00–07:00). Push-frequency: morning brief only / brief + event triggers / everything.

**Acceptance:** user's quiet-hours setting suppresses an `intel.event.high_impact` push at 02:00 local.

### P3.10 — Brokers (FUTU) UI

**Files:** `apps/dashboard/src/routes/SettingsBrokers.tsx`

See §P4.2.

---

## P4 — FUTU portal + quotation client

**Goal:** real OpenD connection with proper read-only walls AND quotation feed; UI to manage Futu IDs.

### P4.1 — Real `RealOpenD` adapter (Phase B / B3.3b)

**Files:**
- `apps/agent_futu/futu/real_opend.py` — wrap `futu.OpenSecTradeContext`; uses `FutuReadOnlyClient` allow-list.
- Update `main.py` to switch on `FUTU_OPEND_BACKEND=real|fake`.

**Pre-requisite (already flagged in D5):** ship `lake.futu_audit` Postgres trigger + revoked UPDATE/DELETE *before* enabling real OpenD. This is non-negotiable. **File:** `packages/data-lake/data_lake/migrations/versions/0008_futu_audit_trigger.py`.

**Acceptance:** with a valid OpenD running on `127.0.0.1:11111`, `/portfolio/snapshot` returns real positions; `lake.futu_audit` head advances; revoked grants prevent UPDATE/DELETE on the chain.

### P4.2 — Brokers UI

**Files (new):**
- `apps/dashboard/src/routes/SettingsBrokers.tsx`
- `apps/admin_api/admin_api/brokers.py`

Per-Futu-ID form: host, port, TLS path, encryption, last-online, last-snapshot. "Verify" button performs a read-only `get_global_state` round-trip.

**Acceptance:** verify button on a working OpenD returns success; on a wrong port returns the error.

### P4.3 — `FutuQuoteClient` (quotation context)

**Files (new):**
- `apps/agent_futu/futu/quote_client.py` — `OpenQuoteContext` wrapper with allow-list (`get_market_snapshot`, `get_cur_kline`, `get_order_book`, `subscribe`, `unsubscribe`, `get_global_state`, `get_history_kl_quota`).

**Acceptance:** unit test verifies allow-list rejects `unlock_trade`-equivalent quotation methods (none exist, but defense-in-depth pattern).

### P4.4 — `lake.quotes` schema + writer

**Files:**
- Migration: `packages/data-lake/data_lake/migrations/versions/0009_quotes.py` — `lake.quotes(ts, ticker, exch, bid, ask, last, vol, src)`, hypertabled on `ts`, `(ticker, ts)` PK.
- Writer: `apps/agent_futu/futu/quote_writer.py` — subscribe live quotes, write on each tick (batched per second).

**Acceptance:** subscribe to `HK.00700`; `lake.quotes` populates; writer survives subscription gap reconnects.

### P4.5 — Subscription manager

**File (new):** `apps/agent_futu/futu/sub_manager.py`

Tracks active subscriptions in NATS KV `iic_state/futu_subs`; respects FUTU's tier-based cap; reconciles on restart.

**Acceptance:** subscribing 50 tickers + restart + reading KV shows 50 active subs reconciled in <5s.

### P4.6 — Replace placeholder quote reads in quant + fundamental + persona

**Files:** any TODO that reads "fetch price" — wire to `FutuQuoteClient.snapshot(tickers)`.

**Acceptance:** `agent_quant` `/run/factors` actually computes momentum from real quotes.

### P4.7 — Crypto + FX (out-of-FUTU) writers

**Files:**
- `apps/agent_market/crypto.py` — ccxt against Binance/Coinbase; write to `lake.quotes` with `src='binance'`.
- `apps/agent_market/fx.py` — FRED daily for major pairs; same target table.

**Acceptance:** lake.quotes contains rows with src ∈ {futu, binance, fred}.

---

## P5 — Map / geo dashboard

**Goal:** restore the v1.1 visual centerpiece.

### P5.1 — `lake.geo_events` schema

**File:** migration `0010_geo_events.py` — `(ts, lat, lon, theme, tone, src_url, urls TEXT[], event_id UUID)`, hypertabled on `ts`, indexes on `theme`, `(lat, lon)`.

**Acceptance:** migration applies; `INSERT` smoke test passes.

### P5.2 — GDELT crawler writes geo_events

**File:** extend `apps/agent_intelligence/intel/crawler/gdelt.py` to write `lake.geo_events` in addition to emitting `RawEvent`.

**Acceptance:** 15-min pull populates ~5k rows; spot-check coords are valid.

### P5.3 — Globe component

**Files (new):**
- `apps/dashboard/src/routes/Map.tsx`
- `apps/dashboard/src/components/EventGlobe.tsx` — `react-globe.gl` integration; arcs/heat/points on toggle.

Filters: theme, tone band, time window, universe overlap.

**Acceptance:** rendering 5k points performs at 30fps on the dev box; theme filter works.

### P5.4 — `/api/geo/events` endpoint on admin API or a separate read API

**File:** `apps/admin_api/admin_api/geo.py` — windowed query.

**Acceptance:** `GET /api/geo/events?window=24h&themes=ECON_*` returns ≤ 10MB JSON; cached 60s.

### P5.5 — Brief integration

When a geo cluster crosses a threshold (e.g., > 100 high-tone events from a region in 4h), intel emits `intel.event.geo_cluster.v1`. Trading-room treats it as high-impact.

**Acceptance:** synthetic cluster test triggers triage's `trading_room` route.

---

## P6 — Secretary as leader-router agent

**Goal:** secretary becomes the bridge between user and agent fleet. Outbound dispatch, conversational planner, state, memory.

### P6.1 — Inject `AgentRegistry` into secretary

**Files:**
- `packages/data-bus/data_bus/registry.py` — already exists in orchestrator; promote to shared package.
- `apps/agent_secretary/secretary/main.py` — at startup, inject `HttpxAgentClient` table.

**Acceptance:** secretary on boot can call `agents.intel.health()` and get 200.

### P6.2 — `secretary.plan` LLM caller

**Files:**
- `packages/llm-client/llm_client/_matrix.py` — register `secretary.plan` (Pro on multi-step, Flash on single-RPC).
- `apps/agent_secretary/secretary/planner.py:plan(text)` — returns `[("intel.search", {...}), ("persona.rerun", {...}), ...]`.

System prompt format: "Given user request X, output JSON list of agent RPCs needed; one per object with `caller`, `endpoint`, `args`."

**Acceptance:** unit test with five prompts produces valid plan JSON; goldens.

### P6.3 — `POST /chat` endpoint

**File:** `apps/agent_secretary/secretary/main.py`

Pseudo:

```python
@app.post("/chat")
async def chat(req: ChatRequest):
    plan = await planner.plan(req.text)
    results = await asyncio.gather(*[
        agents.dispatch(step.caller, step.endpoint, step.args) for step in plan
    ])
    answer = await router.chat_or_raise("secretary.brief.midday", _stitch(results))
    save_thread(req.user_id, req.text, answer)
    return {"answer": answer.text, "trace_id": req.trace_id}
```

**Acceptance:** `POST /chat {"user_id":"u1","text":"why did Buffett go long $XYZ?"}` returns a real markdown answer that quotes the persona's most recent advice.

### P6.4 — `lake.user_prefs` + slash command real wiring

**Files:**
- Migration `0011_user_prefs.py` — `(user_id, key, value, updated_at)` PK on `(user_id, key)`.
- `apps/agent_secretary/secretary/inbound/slash_commands.py:_render` — replace each canned string with a real handler that reads/writes prefs and dispatches when needed.

**Acceptance:** `/quiet 30` writes a row; outbound notifier reads it before pushing; subsequent push at minute 5 is suppressed.

### P6.5 — `lake.secretary_thread` for conversation memory

**Files:**
- Migration `0012_secretary_thread.py` — `(thread_id UUID, ts, role, content, PRIMARY KEY (thread_id, ts))`, hypertabled on `ts`.
- `apps/agent_secretary/secretary/memory.py:append`, `last_n`.

**Acceptance:** 10 chat turns persisted; planner sees the rolling context on turn 11.

### P6.6 — `POST /rerun` endpoint

**File:** `apps/agent_secretary/secretary/main.py`

```python
@app.post("/rerun")
async def rerun(req: RerunRequest):
    return await agents.dispatch(req.agent, "/run/rerun", req.override_signals)
```

Each agent (intel/fund/quant/persona/board) gets a `/run/rerun` endpoint that takes `override_signals: dict` and replays the last job with overrides.

**Acceptance:** `POST /rerun {"agent":"persona","slug":"buffett","override_signals":{"focus":"AAPL Q3 earnings"}}` triggers a new persona run that respects the override.

### P6.7 — Replace stubbed `/run/morning_brief` etc. with real composition

**File:** `apps/agent_secretary/secretary/main.py`

Real morning_brief: query `lake.advice WHERE issued_at > now() - 18h AND persisted_in_lake`, group by ticker, render via `secretary.brief.morning` LLM call, push to WeCom group bot.

**Acceptance:** `POST /run/morning_brief` returns within 30s; WeCom (or test stub) receives the markdown.

### P6.8 — Re-route in workflow: secretary owns user-driven path

**File:** orchestrator + secretary documentation, plus a single test that asserts the topology.

Update the trading-room DAG so push notifications go through secretary (not direct from notifier package). Keep the event-driven (intel→board→advice) path on the orchestrator.

**Acceptance:** the dual-path test passes: an event triggers via orchestrator AND a user `/chat` triggers via secretary; both produce advice without conflict.

---

## P7 — Fundamental + Quant + Backtest agents

**Goal:** turn the three biggest stubs into real thinking nodes.

### P7.1 — Fundamental: SEC EDGAR client + filings parser

**Files (new):**
- `apps/agent_fundamental/fund/sources/edgar.py` — REST + RSS, daily pull of new filings for the watchlist.
- `apps/agent_fundamental/fund/sources/hkex.py` — same for HKEX.
- `apps/agent_fundamental/fund/sources/tushare.py` — A-share filings.
- `apps/agent_fundamental/fund/parsing/xbrl.py` — XBRL extract; reuse `arelle` if needed.

**Acceptance:** for AAPL's last 10-K, parser extracts revenue, opex, FCF, debt, EPS within ±0.5% of the published values.

### P7.2 — Fundamental: valuation engine

**File (new):** `apps/agent_fundamental/fund/valuation/dcf.py` + `comps.py` + `multiples.py`

Compute DCF, comps, multiples with explicit assumption-table (WACC, growth, margin); output ranges with sensitivities.

**Acceptance:** unit tests match published valuations within ±10% on five calibration tickers.

### P7.3 — Fundamental: `/run/cover` + `/run/digest` real

**File:** `apps/agent_fundamental/fund/main.py`

`/run/cover` — for each watchlist ticker, fetch latest filings + quotes, run valuation, emit `advice.v1` if signal exceeds threshold.
`/run/digest` — render the daily fund-team digest (markdown).

**Acceptance:** `POST /run/cover` produces ≥ 3 advices for a day with three notable filings; goldens fixture exercises this.

### P7.4 — Quant: factor library

**Files (new):**
- `apps/agent_quant/quant/factors/momentum.py`
- `…/mean_reversion.py`
- `…/vol_risk_premium.py`
- `…/pead.py` — post-earnings announcement drift
- `…/insider_clusters.py`
- `…/sector_strength.py`
- `…/crypto_basis.py`
- `…/fx_carry.py`

Each factor: `compute(universe, asof) -> dict[ticker, score]`. Pure function; no I/O except the price/earnings DB.

**Acceptance:** unit tests validate against known historical hits (e.g., March 2020 mean-reversion bonanza).

### P7.5 — Quant: regime detector

**File (new):** `apps/agent_quant/quant/regime.py`

Compute regime label (bull / bear / chop / shock) from VIX EMA + breadth + correlation cluster.

**Acceptance:** for the 2008, 2020, 2022 dates, regime correctly labels.

### P7.6 — Quant: `/run/factors`, `/run/signal`, `/run/walk_forward` real

**File:** `apps/agent_quant/quant/main.py`

`/run/signal` — combine factor scores per regime, emit `advice.v1`.
`/run/walk_forward` — historical backtest over the last 5 years; emit `quant.walk_forward.v1` to the dashboard.

**Acceptance:** end-to-end: `/run/signal` for `AAPL` on a known date emits an advice with a non-trivial confidence and an evidence array citing 3 factors.

### P7.7 — Backtest: virtual portfolio book

**Files (new):**
- `apps/agent_backtest/backtest/book.py` — opens a virtual position for every published advice; marks-to-market against `lake.quotes` every minute.
- `apps/agent_backtest/backtest/sim/walk_forward.py`
- Migration `0013_backtest_positions.py` — `lake.bt_positions(advice_id, opened_at, status, fills, pnl)`.

**Acceptance:** publishing an advice opens a `bt_positions` row in <2s; `pnl` updates over the next quote cycle.

### P7.8 — Backtest: leaderboard

**File:** `apps/agent_backtest/backtest/leaderboard.py`

Ranks advisors by Sharpe / win-rate / max-DD over rolling 30/90/365 days. Emits `backtest.leaderboard.v1` to dashboard.

**Acceptance:** `GET /leaderboard` on dashboard shows real numbers from `bt_positions`.

### P7.9 — Backtest: feedback to source agent

**File:** `apps/agent_backtest/backtest/feedback.py`

When an advice closes (target hit / stop hit / horizon expired), publish `backtest.feedback.v1` so the source agent's prompt can include "your last 10 advices had Sharpe X" in its system prompt.

**Acceptance:** persona's next daily run includes a recent-performance snippet in the system prompt.

---

## P8 — Persona agents (analytical)

**Goal:** the persona slug is no longer just a YAML — it actually runs an LLM analysis with that persona's prompt against the day's intel + fundamental + quant context.

### P8.1 — `persona.daily` real

**File:** `apps/agent_persona/persona/run_daily.py`

Pseudo:

```python
async def run_daily(slug: str):
    spec = load_persona(slug)
    intel_ctx = await intel_client.context(universe=spec.universe)
    quant_ctx = await quant_client.signals(universe=spec.universe)
    fund_ctx = await fund_client.recent_advice(universe=spec.universe)
    advice = await router.chat_or_raise(
        f"persona.{slug}.daily",
        [
            ChatMessage(role="system", content=spec.system_prompt),
            ChatMessage(role="user", content=stitch_context(intel_ctx, quant_ctx, fund_ctx)),
        ],
        max_tokens=1200,
        response_format={"type": "json_schema", "schema": ADVICE_V1_SCHEMA},
    )
    enforce_disclaimer(advice)
    return persist_advice(advice)
```

**Acceptance:** `POST /run/daily?slug=buffett` produces a valid `advice.v1` with `disclaimer="style mimic, not the real person"` and at least 2 citations.

### P8.2 — `persona.weekly` real

**File:** `apps/agent_persona/persona/run_weekly.py`

Same shape but: weekly context window, Pro tier, longer max_tokens, a "thesis update" section comparing to the persona's last 3 weekly advices.

**Acceptance:** weekly output cites the previous weekly run.

### P8.3 — Persona disclaimer enforcement

**File:** `apps/agent_persona/persona/disclaimer.py`

Validates that every persona advice includes the disclaimer; rejects with HTTP 400 if absent.

**Acceptance:** unit test feeds a stripped-disclaimer LLM response; gets rejected.

### P8.4 — Persona `/run/rerun` (powers secretary §P6.6)

**File:** `apps/agent_persona/persona/main.py`

`POST /run/rerun {"slug": "...", "override_signals": {...}}` — replays daily/weekly with overrides.

**Acceptance:** rerun with `focus=AAPL` produces an advice scoped to AAPL.

---

## P9 — Production hardening

**Goal:** ship-ready ops.

### P9.1 — Per-agent + per-call OpenTelemetry traces

**Files:** adapter base in `packages/llm-client/llm_client/adapters/base.py`; orchestrator runner.

Tag every span with `caller_id`, `tier`, `model`, `tokens_in/out`, `cost_usd`, `outcome`.

**Acceptance:** Jaeger / Tempo shows a complete trace from intel → board → advice.

### P9.2 — Grafana dashboards

**Files:** `infra/grafana/dashboards/{advice_throughput,llm_cost,error_rate,futu_audit_chain,backtest_leaderboard}.json`

**Acceptance:** all five render against live data.

### P9.3 — Alerts (Prometheus / Alertmanager)

**Files:** `infra/alertmanager/alerts.yml`

Alerts: provider error rate > 5%, FUTU audit chain stalled, backtest book-PnL diverging from leaderboard, intel ingest latency > 30 min, no advice published in 24h.

**Acceptance:** synthetic-fail tests trigger each alert; routes via Alertmanager → secretary `/notifier/alertmanager`.

### P9.4 — Restore drill (NATS + Postgres)

**File:** `deploy/drills/restore_drill.sh`

Once a week, snapshot Postgres + NATS JetStream stream files, restore to a side container, verify `lake.advice` count and chain head match.

**Acceptance:** drill passes on the first scheduled run.

### P9.5 — Runbooks

**Files (new):** `docs/runbooks/{provider_outage,futu_offline,cost_breaker_trip,advice_chain_break,brief_failed_to_send}.md`

**Acceptance:** each runbook fits in one screen and has a `1. Detect → 2. Mitigate → 3. Verify` template.

### P9.6 — End-to-end live trace gate (the "definition of done")

**File:** `tests/e2e/test_first_live_trace.py`

Reproduces a real news event (fixture from a recorded GDELT/RSS pull), runs through the full pipeline with real LLM keys (or recorded VCR fixtures), expects:
- intel digest produced
- event-triage routes to trading_room
- quant + fund + persona each emit a plan.v1
- board renders a decision.v1
- advice ledger persists
- secretary renders + pushes brief

**Acceptance:** test passes nightly. **This is the single gating milestone for "no longer a prototype."**

---

## Cross-cutting acceptance criteria

These apply to the whole plan and should be tested at each phase boundary:

1. **No synthetic-skip in production paths.** Grep `lake.llm_calls WHERE model LIKE 'synthetic-skip:%'` returns 0 rows over a 24h window.
2. **No `InMemory*` defaults active.** A startup probe enumerates intel collaborators and asserts none are `InMemory*` in production env.
3. **No `parents[N]` in `apps/` or `packages/`.** Static check.
4. **Hotfix CI green.** Daily fresh-bringup workflow passes.
5. **FUTU audit chain unbroken.** `lake.futu_audit` chain validates from genesis to head.
6. **All cron jobs registered.** `/admin/crons` shows the full set; each fired ≥ once in 24h.
7. **Every UI write produces a `lake.config_audit` row** with valid chain hash.

---

## Appendix A — Vibe prompt template (paste into your coding agent)

```
You are working in the IIC repo at <path>. Read D6 §<x.y> for context.

Task: <copy phase-item title>

File(s): <copy from item>

Acceptance: <copy from item>

Constraints:
- Do not introduce new mocks or stubs. If you cannot complete the task,
  raise an explicit NotImplementedError with a TODO comment, do not
  return canned data.
- Every new schema must be versioned (e.g., advice.v1) and have a golden
  test under tests/<area>/goldens/.
- Every migration must be tested against pg16 + timescaledb-ha + pg_partman
  with the composite-PK rule for hypertables.
- Any DAG change must update the topology test in tests/orchestrator.

Open a PR with:
- the implementation
- the failing test added before the impl, the passing test after
- a one-paragraph "what changed" entry in workflows/32_V2_5_T0_T1_CHANGELOG.md
```

---

## Appendix B — Phase-to-mock-inventory crosswalk

| Phase | Replaces |
|---|---|
| P0 | M-A1 (synthetic-skip default) |
| P1 | M-C1, M-C2 |
| P2 | M-A2, M-A3 |
| P3 | (no mocks; new surface) |
| P4 | M-A4 |
| P5 | (no mocks; new surface) |
| P6 | M-A5, M-A6 |
| P7 | M-B1, M-B2, M-B4 |
| P8 | M-B3 |
| P9 | (hardening) |

— end of D7 —
